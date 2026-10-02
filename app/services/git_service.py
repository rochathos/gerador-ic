from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re
import git
from git.exc import InvalidGitRepositoryError, NoSuchPathError
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.logger import logger
from app.models.commit import Commit
from app.models.execution_history import ExecutionHistory


class GitService:
    """Service to interact with local Git repositories using GitPython."""

    IC_NODE_TAGS = {
        "node",
        "task-node",
        "decision",
        "state",
        "fork",
        "join",
        "process-state",
    }
    IC_TRANSITION_TAGS = {"transition"}
    EXCLUDED_XML_TAGS = {
        "end-state",
        "process-definition",
        "start-state",
        "assignment",
        "controller",
        "task",
        "script",
        "event",
        "action",
        "swimlane",
        "description",
        "variable",
        "field",
        "property",
        "exception-handler",
        "timer",
    }
    TAG_REGEX = re.compile(r"^[+-]\s*<([a-zA-Z_:][a-zA-Z0-9_.:-]*)(\s+[^>]*)?")
    DIFF_GIT_REGEX = re.compile(r'diff --git (?:\"a/|a/)(.*) (?:\"b/|b/)(.*)')
    NAME_ATTR_REGEX = re.compile(r'name=["\']([^"\']+)["\']')
    TO_ATTR_REGEX = re.compile(r'to=["\']([^"\']+)["\']')

    @classmethod
    def analyze_commit_xml_tags(cls, repo: git.Repo, commit_hash: str) -> Dict[str, Any]:
        """Extract XML tag metrics (both added and removed) globally and per flow from commit diff with smart pairing."""
        flows: Dict[str, Dict[str, Any]] = {}
        current_flow: Optional[str] = None

        flow_del_nodes: List[Tuple[str, str]] = []
        flow_add_nodes: List[Tuple[str, str]] = []
        flow_del_trans: List[Tuple[str, str]] = []
        flow_add_trans: List[Tuple[str, str]] = []
        in_del_node = False
        in_add_node = False

        def finalize_flow():
            nonlocal current_flow, flow_del_nodes, flow_add_nodes, flow_del_trans, flow_add_trans
            if not current_flow:
                return

            # Match nodes: if a node was merely renamed or tweaked, it's not a new/deleted IC
            unmatched_del_nodes: List[Tuple[str, str]] = []
            matched_nodes: List[Tuple[str, str, str]] = []
            for dt, dn in flow_del_nodes:
                matched = False
                for at, an in list(flow_add_nodes):
                    if dt == at:
                        if dn == an or (dn and an and (dn in an or an in dn)):
                            matched_nodes.append((dt, dn, an))
                            flow_add_nodes.remove((at, an))
                            matched = True
                            break
                if not matched:
                    unmatched_del_nodes.append((dt, dn))

            # Match transitions: if a transition points to the same target or has same name, it's a modified adjustment
            unmatched_del_trans: List[Tuple[str, str]] = []
            matched_trans: List[Tuple[str, str, str, str]] = []
            for dto, dna in flow_del_trans:
                matched = False
                for ato, ana in list(flow_add_trans):
                    if (dto and ato and dto == ato) or (dna and ana and dna == ana):
                        matched_trans.append((dto, dna, ato, ana))
                        flow_add_trans.remove((ato, ana))
                        matched = True
                        break
                if not matched:
                    unmatched_del_trans.append((dto, dna))

            f_added: Dict[str, int] = {}
            f_removed: Dict[str, int] = {}
            f_modified: Dict[str, int] = {}

            # Unmatched deletions -> removals
            for dt, _ in unmatched_del_nodes:
                f_removed[dt] = f_removed.get(dt, 0) + 1
            for _ in unmatched_del_trans:
                f_removed["transition"] = f_removed.get("transition", 0) + 1

            # Unmatched additions -> additions
            for at, _ in flow_add_nodes:
                f_added[at] = f_added.get(at, 0) + 1
            for _ in flow_add_trans:
                f_added["transition"] = f_added.get("transition", 0) + 1

            # Matched pairs -> modifications (adjustments: 1 addition + 1 deletion = 1 adjustment)
            for dt, _, _ in matched_nodes:
                f_modified[dt] = f_modified.get(dt, 0) + 1
            for _ in matched_trans:
                f_modified["transition"] = f_modified.get("transition", 0) + 1

            f_tot_add = sum(f_added.values())
            f_tot_rem = sum(f_removed.values())
            f_tot_mod = sum(f_modified.values())
            f_tot_ics = f_tot_add + f_tot_rem + f_tot_mod

            if f_tot_ics > 0:
                flows[current_flow] = {
                    "flow_name": current_flow.split("/")[-1].split("\\")[-1],
                    "path": current_flow,
                    "added": f_added,
                    "removed": f_removed,
                    "modified": f_modified,
                    "total_added": f_tot_add,
                    "total_removed": f_tot_rem,
                    "total_modified": f_tot_mod,
                    "total_ics": f_tot_ics,
                }

            flow_del_nodes = []
            flow_add_nodes = []
            flow_del_trans = []
            flow_add_trans = []

        try:
            patch_output = repo.git.show(commit_hash, "--pretty=format:", "-p", "-M", "--", "*.xml")
            if patch_output:
                for line in patch_output.splitlines():
                    if line.startswith("diff --git "):
                        finalize_flow()
                        m = cls.DIFF_GIT_REGEX.match(line)
                        if m:
                            raw_target = m.group(2).rstrip('"')
                            current_flow = cls.decode_git_path(raw_target)
                        else:
                            current_flow = "arquivo.xml"
                        in_del_node = False
                        in_add_node = False
                        continue

                    if line.startswith("+++") or line.startswith("---"):
                        continue

                    if line.startswith("@@"):
                        in_del_node = False
                        in_add_node = False
                        continue

                    sign = line[0] if line else ""
                    if sign not in ("+", "-"):
                        continue

                    content = line[1:].strip()
                    m = cls.TAG_REGEX.match(line)
                    if not m:
                        if sign == "-" and any(f"</{t}>" in content for t in cls.IC_NODE_TAGS):
                            in_del_node = False
                        elif sign == "+" and any(f"</{t}>" in content for t in cls.IC_NODE_TAGS):
                            in_add_node = False
                        continue

                    tag = m.group(1).lower()
                    attrs = m.group(2) or ""

                    if tag in cls.EXCLUDED_XML_TAGS:
                        continue

                    m_name = cls.NAME_ATTR_REGEX.search(attrs)
                    name_val = m_name.group(1) if m_name else ""
                    m_to = cls.TO_ATTR_REGEX.search(attrs)
                    to_val = m_to.group(1) if m_to else ""

                    is_self_closing = attrs.strip().endswith("/") or line.strip().endswith("/>")

                    if tag in cls.IC_NODE_TAGS:
                        if sign == "-":
                            if not is_self_closing:
                                in_del_node = True
                            flow_del_nodes.append((tag, name_val))
                        else:
                            if not is_self_closing:
                                in_add_node = True
                            flow_add_nodes.append((tag, name_val))
                    elif tag in cls.IC_TRANSITION_TAGS:
                        if sign == "-":
                            if in_del_node:
                                continue
                            flow_del_trans.append((to_val, name_val))
                        else:
                            if in_add_node:
                                continue
                            flow_add_trans.append((to_val, name_val))

            finalize_flow()
        except Exception as exc:
            logger.debug(f"Erro ao extrair diff de tags XML para o commit {commit_hash[:7]}: {exc}")

        total_added = sum(f["total_added"] for f in flows.values())
        total_removed = sum(f["total_removed"] for f in flows.values())
        total_modified = sum(f["total_modified"] for f in flows.values())
        total_ics = total_added + total_removed + total_modified

        commit_added: Dict[str, int] = {}
        commit_removed: Dict[str, int] = {}
        commit_modified: Dict[str, int] = {}
        for f in flows.values():
            for t, c in f["added"].items():
                commit_added[t] = commit_added.get(t, 0) + c
            for t, c in f["removed"].items():
                commit_removed[t] = commit_removed.get(t, 0) + c
            for t, c in f["modified"].items():
                commit_modified[t] = commit_modified.get(t, 0) + c

        return {
            "added": commit_added,
            "removed": commit_removed,
            "modified": commit_modified,
            "total_added": total_added,
            "total_removed": total_removed,
            "total_modified": total_modified,
            "total_ics": total_ics,
            "flows": flows,
        }

    @staticmethod
    def decode_git_path(path: str) -> str:
        """Decode Git quoted paths containing octal escape sequences (e.g. \\303\\255 -> í)."""
        if not path:
            return ""
        clean = str(path).strip("\"'")
        if "\\" in clean:
            try:
                return clean.encode("latin1").decode("unicode_escape").encode("latin1").decode("utf-8")
            except Exception:
                return clean
        return clean

    @classmethod
    def get_commit_files(cls, repo: git.Repo, commit_hash: str) -> List[Dict[str, Any]]:
        """Extract changed files using git diff-tree with rename detection (-M) and exact numstat."""
        files_changed: List[Dict[str, Any]] = []
        try:
            num_output = repo.git.diff_tree("-M", "--root", "--no-commit-id", "--numstat", "-r", commit_hash)
            name_output = repo.git.diff_tree("-M", "--root", "--no-commit-id", "--name-status", "-r", commit_hash)

            num_lines = num_output.splitlines() if num_output else []
            name_lines = name_output.splitlines() if name_output else []

            for num_l, name_l in zip(num_lines, name_lines):
                n_parts = num_l.split("\t")
                ins = int(n_parts[0]) if (n_parts and n_parts[0].isdigit()) else 0
                dels = int(n_parts[1]) if (len(n_parts) > 1 and n_parts[1].isdigit()) else 0

                st_parts = name_l.split("\t")
                status = st_parts[0] if st_parts else "M"

                is_rename = status.startswith("R") and len(st_parts) >= 3
                if is_rename:
                    old_path = cls.decode_git_path(st_parts[1])
                    new_path = cls.decode_git_path(st_parts[2])
                    display_path = new_path
                else:
                    old_path = ""
                    new_path = cls.decode_git_path(st_parts[1] if len(st_parts) > 1 else "")
                    display_path = new_path

                if not display_path:
                    continue

                filename = display_path.replace("\\", "/").split("/")[-1]
                is_xml = display_path.lower().endswith(".xml")

                files_changed.append({
                    "path": display_path,
                    "old_path": old_path,
                    "filename": filename,
                    "is_xml": is_xml,
                    "is_rename": is_rename,
                    "status": status[0] if status else "M",
                    "insertions": ins,
                    "deletions": dels,
                    "lines": ins + dels,
                })
        except Exception as exc:
            logger.debug(f"Erro ao extrair diff_tree para commit {commit_hash[:7]}: {exc}")
        return files_changed

    @staticmethod
    def validate_repository(repo_path: str | Path) -> Tuple[bool, str]:
        """Validate if the given path is a valid Git repository."""
        path = Path(repo_path).resolve()
        if not path.exists():
            return False, f"Caminho não encontrado: {path}"
        if not path.is_dir():
            return False, f"Caminho não é um diretório: {path}"

        try:
            repo = git.Repo(path)
            # Ensure it's not a bare repository with no head
            if repo.bare and not list(repo.heads):
                return False, "Repositório Git está vazio (bare/sem branches)."
            return True, f"Repositório válido: {path.name}"
        except InvalidGitRepositoryError:
            return False, f"O diretório não é um repositório Git válido: {path}"
        except NoSuchPathError:
            return False, f"Caminho inexistente: {path}"
        except Exception as exc:
            return False, f"Erro ao acessar repositório: {str(exc)}"

    @staticmethod
    def get_repo_name(repo_path: str | Path) -> str:
        """Extract a friendly repository name."""
        path = Path(repo_path).resolve()
        try:
            repo = git.Repo(path)
            for remote in repo.remotes:
                for url in remote.urls:
                    name = url.rstrip("/").split("/")[-1]
                    if name.endswith(".git"):
                        name = name[:-4]
                    if name:
                        return name
        except Exception:
            pass
        return path.name

    @classmethod
    def get_commit_url(cls, repo_path: str | Path, commit_hash: str) -> Optional[str]:
        """Generate web URL for viewing the commit on GitHub, GitLab, etc."""
        path = Path(repo_path).resolve()
        try:
            repo = git.Repo(path)
            for remote in repo.remotes:
                for raw_url in remote.urls:
                    url = raw_url.strip()
                    # Convert SSH syntax: git@domain:org/repo.git -> https://domain/org/repo
                    if url.startswith("git@"):
                        url = url.replace(":", "/", 1).replace("git@", "https://")
                    if url.endswith(".git"):
                        url = url[:-4]
                    url = url.rstrip("/")

                    # Detect platform URL structure
                    url_lower = url.lower()
                    if "gitlab" in url_lower or "git.tjce" in url_lower or "git.cnj" in url_lower:
                        return f"{url}/-/commit/{commit_hash}"
                    elif "bitbucket" in url_lower:
                        return f"{url}/commits/{commit_hash}"
                    elif "dev.azure.com" in url_lower or "visualstudio.com" in url_lower:
                        return f"{url}/commit/{commit_hash}"
                    else:
                        # Default standard (GitHub, Gitea, etc.)
                        return f"{url}/commit/{commit_hash}"
        except Exception:
            pass
        return None


    @classmethod
    def get_branches(cls, repo_path: str | Path) -> Dict[str, Any]:
        """Return active branch, list of local branches, and list of remote branches."""
        path = Path(repo_path).resolve()
        is_valid, _ = cls.validate_repository(path)
        if not is_valid:
            return {"active": "", "local": [], "remote": []}

        try:
            repo = git.Repo(path)
            active = ""
            try:
                if not repo.head.is_detached:
                    active = cls.decode_git_path(repo.active_branch.name)
            except Exception:
                pass

            local_set = set()
            for h in repo.heads:
                b_name = cls.decode_git_path(h.name)
                if b_name:
                    local_set.add(b_name)

            remote_set = set()
            for r in repo.remotes:
                try:
                    for ref in r.refs:
                        r_name = cls.decode_git_path(ref.name)
                        if not r_name.endswith("/HEAD"):
                            remote_set.add(r_name)
                except Exception:
                    pass

            return {
                "active": active,
                "local": sorted(list(local_set), key=str.lower),
                "remote": sorted(list(remote_set), key=str.lower),
            }
        except Exception as exc:
            logger.warning(f"Erro ao listar branches do repositório {path}: {exc}")
            return {"active": "", "local": [], "remote": []}

    _COMMIT_BRANCH_CACHE: Dict[str, str] = {}

    @classmethod
    def get_commit_branch(cls, repo_path: str | Path, commit_hash: str) -> str:
        """Resolve the primary origin branch containing this commit (issue matching, active if near, or closest topological branch)."""
        if not commit_hash:
            return ""
        if commit_hash in cls._COMMIT_BRANCH_CACHE:
            return cls._COMMIT_BRANCH_CACHE[commit_hash]

        path = Path(repo_path).resolve()
        try:
            repo = git.Repo(path)
            active = ""
            if not repo.head.is_detached:
                try:
                    active = cls.decode_git_path(repo.active_branch.name)
                except Exception:
                    pass

            raw_local: List[str] = []
            try:
                raw_local = [cls.decode_git_path(b.strip("* ").strip()) for b in repo.git.branch("--contains", commit_hash).splitlines() if b.strip()]
            except Exception:
                pass

            raw_rem: List[str] = []
            try:
                raw_rem = [
                    cls.decode_git_path(b.strip().replace("origin/", ""))
                    for b in repo.git.branch("-r", "--contains", commit_hash).splitlines()
                    if b.strip() and "HEAD" not in b
                ]
            except Exception:
                pass

            # 1. Check if commit message contains a task/issue number matching a branch name
            try:
                msg = repo.commit(commit_hash).message
                m_issue = re.search(r"#?(\d{5,7})", msg)
                if m_issue:
                    issue_num = m_issue.group(1)
                    for b in raw_local:
                        if issue_num in b:
                            cls._COMMIT_BRANCH_CACHE[commit_hash] = b
                            return b
                    for b in raw_rem:
                        if issue_num in b:
                            cls._COMMIT_BRANCH_CACHE[commit_hash] = b
                            return b
            except Exception:
                pass

            # 2. Check if active branch is immediate ancestor (within 10 commits)
            if active and active in raw_local:
                try:
                    dist = int(repo.git.rev_list("--count", f"{commit_hash}..{active}"))
                    if dist <= 10:
                        cls._COMMIT_BRANCH_CACHE[commit_hash] = active
                        return active
                except Exception:
                    pass

            # 3. Find closest branch by topological distance (preferring local and release/feature branches)
            candidate_pool = raw_local + [b for b in raw_rem if b.startswith("releases/") or b.startswith("hotfix/") or b.startswith("feature/")]
            if not candidate_pool:
                candidate_pool = raw_local + raw_rem

            best_branch = ""
            min_distance = float("inf")
            for b in candidate_pool[:20]:
                try:
                    dist = int(repo.git.rev_list("--count", f"{commit_hash}..{b}"))
                    if dist < min_distance:
                        min_distance = dist
                        best_branch = b
                except Exception:
                    pass

            if best_branch:
                cls._COMMIT_BRANCH_CACHE[commit_hash] = best_branch
                return best_branch

            if raw_local:
                chosen = raw_local[0]
                cls._COMMIT_BRANCH_CACHE[commit_hash] = chosen
                return chosen

            if raw_rem:
                chosen = raw_rem[0]
                cls._COMMIT_BRANCH_CACHE[commit_hash] = chosen
                return chosen
        except Exception:
            pass

        cls._COMMIT_BRANCH_CACHE[commit_hash] = ""
        return ""

    @classmethod
    def get_commits(
        cls,
        repo_path: str | Path,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        author: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch commits in the specified period, optionally filtered by author and branch."""
        path = Path(repo_path).resolve()
        is_valid, msg = cls.validate_repository(path)
        if not is_valid:
            logger.error(f"Validação de repositório falhou: {msg}")
            raise ValueError(msg)

        logger.info(
            f"Buscando commits no repositório '{path}' entre {start_date} e {end_date} (autor: {author or 'TODOS'}, branch: {branch or 'ALL'})"
        )

        repo = git.Repo(path)

        start_date_tz = None
        if start_date is not None:
            start_date_tz = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date

        end_date_tz = None
        if end_date is not None:
            end_date_tz = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date

        commits_found: List[Dict[str, Any]] = []

        try:
            clean_b = (branch or "").strip()
            if clean_b and clean_b.upper() not in ["ALL", "TODAS"]:
                iter_kwargs: Dict[str, Any] = {"rev": clean_b}
            else:
                iter_kwargs: Dict[str, Any] = {"all": True}
            if start_date_tz is not None:
                iter_kwargs["since"] = int(start_date_tz.timestamp())
            if end_date_tz is not None:
                iter_kwargs["until"] = int(end_date_tz.timestamp())

            try:
                commit_iter = repo.iter_commits(**iter_kwargs)
            except Exception as iter_err:
                logger.warning(f"Branch '{clean_b}' não pôde ser iterada diretamente ({iter_err}). Buscando com all=True.")
                iter_kwargs.pop("rev", None)
                iter_kwargs["all"] = True
                commit_iter = repo.iter_commits(**iter_kwargs)

            for commit in commit_iter:
                commit_dt = commit.committed_datetime

                # Safety check against time boundaries
                if start_date_tz is not None and commit_dt < start_date_tz:
                    continue
                if end_date_tz is not None and commit_dt > end_date_tz:
                    continue

                # Filter by author if provided
                if author:
                    author_query = author.strip().lower()
                    author_name = (commit.author.name or "").lower()
                    author_email = (commit.author.email or "").lower()
                    if author_query not in author_name and author_query not in author_email:
                        continue

                # Get changed files with diff metrics (insertions, deletions, lines) using -M rename detection
                files_changed = cls.get_commit_files(repo, commit.hexsha)

                # Check for XML changes and analyze tags using icf.sh rules
                has_xml = any(
                    f.get("is_xml") or cls.decode_git_path(str(f.get("path", ""))).lower().endswith(".xml")
                    for f in files_changed
                    if isinstance(f, dict)
                )
                xml_analysis = cls.analyze_commit_xml_tags(repo, commit.hexsha) if has_xml else {
                    "added": {},
                    "removed": {},
                    "total_added": 0,
                    "total_removed": 0,
                    "total_ics": 0,
                    "flows": {},
                }

                commit_author_display = f"{commit.author.name} <{commit.author.email}>" if commit.author.email else commit.author.name
                commit_url = cls.get_commit_url(path, commit.hexsha)
                commit_branch = clean_b if (clean_b and clean_b.upper() not in ["ALL", "TODAS"]) else cls.get_commit_branch(path, commit.hexsha)

                commits_found.append(
                    {
                        "hash": commit.hexsha,
                        "author": commit_author_display,
                        "author_name": commit.author.name or "",
                        "author_email": commit.author.email or "",
                        "commit_date": commit_dt,
                        "message": commit.message.strip(),
                        "files_changed": files_changed,
                        "repo_name": cls.get_repo_name(path),
                        "repo_path": str(path),
                        "branch": commit_branch,
                        "commit_url": commit_url,
                        "xml_tags_metrics": xml_analysis,
                        "ic_count": xml_analysis["total_ics"],
                    }
                )

            # Sort chronologically (oldest to newest)
            commits_found.sort(key=lambda c: c["commit_date"])
            logger.info(f"Busca finalizada: {len(commits_found)} commits encontrados.")
            return commits_found

        except Exception as exc:
            logger.error(f"Erro ao buscar commits no Git: {exc}")
            raise

    @classmethod
    def get_commit_by_hash(cls, repo_path: str | Path, commit_hash: str) -> Optional[Dict[str, Any]]:
        """Look up a single commit directly from Git repository by full or abbreviated hash."""
        path = Path(repo_path).resolve()
        is_valid, _ = cls.validate_repository(path)
        if not is_valid:
            return None
        try:
            repo = git.Repo(path)
            c = repo.commit(commit_hash.strip())
            files_changed = cls.get_commit_files(repo, c.hexsha)

            has_xml = any(f.get("is_xml") for f in files_changed)
            xml_analysis = cls.analyze_commit_xml_tags(repo, c.hexsha) if has_xml else {
                "added": {},
                "removed": {},
                "total_added": 0,
                "total_removed": 0,
                "total_ics": 0,
                "flows": {},
            }
            author_display = f"{c.author.name} <{c.author.email}>" if c.author.email else c.author.name
            return {
                "hash": c.hexsha,
                "author": author_display,
                "author_name": c.author.name or "",
                "author_email": c.author.email or "",
                "commit_date": c.committed_datetime,
                "message": c.message.strip(),
                "files_changed": files_changed,
                "repo_name": cls.get_repo_name(path),
                "repo_path": str(path),
                "branch": cls.get_commit_branch(path, c.hexsha),
                "commit_url": cls.get_commit_url(path, c.hexsha),
                "xml_tags_metrics": xml_analysis,
                "ic_count": xml_analysis["total_ics"],
            }
        except Exception as exc:
            logger.debug(f"Commit {commit_hash} não encontrado diretamente no Git: {exc}")
            return None

    @classmethod
    def get_commits_paged(
        cls,
        repo_path: str | Path,
        author: Optional[str] = None,
        q: Optional[str] = None,
        branch: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        only_xml: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Fetch a page of commits directly from Git with lazy-loading support without saving to database."""
        path = Path(repo_path).resolve()
        is_valid, msg = cls.validate_repository(path)
        if not is_valid:
            logger.error(f"Validação de repositório falhou: {msg}")
            raise ValueError(msg)

        repo = git.Repo(path)

        # 1. Direct hash lookup if q is provided and matches a commit
        if q and len(q.strip()) >= 4:
            clean_q = q.strip()
            single_commit = cls.get_commit_by_hash(path, clean_q)
            if single_commit:
                if only_xml and not any(f.get("is_xml") for f in single_commit.get("files_changed", [])):
                    return [], False
                return [single_commit], False

        # 2. Iterate commits directly from Git
        clean_b = (branch or "").strip()
        if clean_b and clean_b.upper() not in ["ALL", "TODAS"]:
            iter_kwargs: Dict[str, Any] = {"rev": clean_b}
        else:
            iter_kwargs: Dict[str, Any] = {"all": True}
        start_date_tz = None
        if start_date is not None:
            start_date_tz = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date
            iter_kwargs["since"] = int(start_date_tz.timestamp())

        end_date_tz = None
        if end_date is not None:
            end_date_tz = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date
            iter_kwargs["until"] = int(end_date_tz.timestamp())

        if author:
            iter_kwargs["author"] = author.strip()

        matched_commits: List[Dict[str, Any]] = []
        has_more = False
        skipped = 0
        query_text = q.strip().lower() if q else ""

        try:
            commit_iter = repo.iter_commits(**iter_kwargs)
        except Exception as iter_err:
            logger.warning(f"Branch '{clean_b}' não pôde ser iterada diretamente ({iter_err}). Buscando com all=True.")
            iter_kwargs.pop("rev", None)
            iter_kwargs["all"] = True
            commit_iter = repo.iter_commits(**iter_kwargs)

        for commit in commit_iter:
            commit_dt = commit.committed_datetime
            if start_date_tz is not None and commit_dt < start_date_tz:
                continue
            if end_date_tz is not None and commit_dt > end_date_tz:
                continue

            msg = commit.message.strip()
            c_author_name = commit.author.name or ""
            c_author_email = commit.author.email or ""

            if query_text:
                if (
                    query_text not in commit.hexsha.lower()
                    and query_text not in msg.lower()
                    and query_text not in c_author_name.lower()
                    and query_text not in c_author_email.lower()
                ):
                    continue

            files_changed = cls.get_commit_files(repo, commit.hexsha)

            if only_xml and not any(f.get("is_xml") for f in files_changed):
                continue

            if skipped < skip:
                skipped += 1
                continue

            if len(matched_commits) >= limit:
                has_more = True
                break

            has_xml = any(f.get("is_xml") for f in files_changed)
            xml_analysis = cls.analyze_commit_xml_tags(repo, commit.hexsha) if has_xml else {
                "added": {},
                "removed": {},
                "total_added": 0,
                "total_removed": 0,
                "total_ics": 0,
                "flows": {},
            }
            author_display = f"{c_author_name} <{c_author_email}>" if c_author_email else c_author_name
            commit_branch = clean_b if (clean_b and clean_b.upper() not in ["ALL", "TODAS"]) else cls.get_commit_branch(path, commit.hexsha)

            matched_commits.append({
                "hash": commit.hexsha,
                "author": author_display,
                "author_name": c_author_name,
                "author_email": c_author_email,
                "commit_date": commit_dt,
                "message": msg,
                "files_changed": files_changed,
                "repo_name": cls.get_repo_name(path),
                "repo_path": str(path),
                "branch": commit_branch,
                "commit_url": cls.get_commit_url(path, commit.hexsha),
                "xml_tags_metrics": xml_analysis,
                "ic_count": xml_analysis["total_ics"],
            })

        return matched_commits, has_more

    @classmethod
    def save_commits(
        cls,
        db: Session,
        commits_data: List[Dict[str, Any]],
        execution_id: Optional[int] = None,
    ) -> List[Commit]:
        """Persist retrieved commits into the PostgreSQL database."""
        saved_records: List[Commit] = []
        try:
            for item in commits_data:
                # Check if commit hash already exists
                stmt = select(Commit).where(Commit.hash == item["hash"])
                existing = db.execute(stmt).scalar_one_or_none()

                if existing:
                    # Update fields and associate with execution if provided
                    existing.execution_id = execution_id or existing.execution_id
                    existing.author = item["author"]
                    existing.message = item["message"]
                    existing.commit_date = item["commit_date"]
                    existing.files_changed = item["files_changed"]
                    existing.repo_name = item.get("repo_name")
                    existing.repo_path = item.get("repo_path")
                    if item.get("branch"):
                        existing.branch = item["branch"]
                    if item.get("commit_url"):
                        existing.commit_url = item["commit_url"]
                    if item.get("xml_tags_metrics") is not None:
                        existing.xml_tags_metrics = item["xml_tags_metrics"]
                    if item.get("ic_count") is not None:
                        existing.ic_count = item["ic_count"]
                    saved_records.append(existing)
                else:
                    new_commit = Commit(
                        hash=item["hash"],
                        author=item["author"],
                        message=item["message"],
                        commit_date=item["commit_date"],
                        files_changed=item["files_changed"],
                        repo_name=item.get("repo_name"),
                        repo_path=item.get("repo_path"),
                        branch=item.get("branch"),
                        commit_url=item.get("commit_url"),
                        xml_tags_metrics=item.get("xml_tags_metrics"),
                        ic_count=item.get("ic_count", 0),
                        execution_id=execution_id,
                    )
                    db.add(new_commit)
                    saved_records.append(new_commit)

            db.commit()
            for rec in saved_records:
                db.refresh(rec)

            logger.info(f"{len(saved_records)} commits salvos/atualizados com sucesso no PostgreSQL.")
            return saved_records
        except Exception as exc:
            db.rollback()
            logger.error(f"Erro ao persistir commits no banco de dados: {exc}")
            raise

    @classmethod
    def execute_analysis(
        cls,
        db: Session,
        repo_path: str | Path,
        start_date: datetime,
        end_date: datetime,
        author: Optional[str] = None,
        branch: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Tuple[ExecutionHistory, List[Commit]]:
        """Run complete extraction pipeline: record history, fetch commits, and save to DB."""
        path = Path(repo_path).resolve()
        logger.info(f"Iniciando ciclo de execução de análise para o período {start_date} até {end_date} (branch: {branch or 'ALL'})")

        # 1. Create Execution History record
        history = ExecutionHistory(
            start_date=start_date,
            end_date=end_date,
            repo_path=str(path),
            total_commits=0,
            total_meetings=0,
            total_catalog_items=0,
            status="processando",
            notes=notes or (f"Branch: {branch}" if branch else "Todas as Branches"),
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        try:
            # 2. Fetch commits from Git
            commits_data = cls.get_commits(
                repo_path=path,
                start_date=start_date,
                end_date=end_date,
                author=author,
                branch=branch,
            )

            # 3. Save to database
            saved_commits = cls.save_commits(
                db=db,
                commits_data=commits_data,
                execution_id=history.id,
            )

            # 4. Update history totals
            history.total_commits = len(saved_commits)
            history.status = "concluido"
            db.commit()
            db.refresh(history)

            logger.info(
                f"Execução #{history.id} concluída com sucesso: {history.total_commits} commits registrados."
            )
            return history, saved_commits

        except Exception as exc:
            history.status = "erro"
            history.notes = f"Falha na execução: {str(exc)}"
            db.commit()
            logger.error(f"Execução #{history.id} finalizou com erro: {exc}")
            raise
