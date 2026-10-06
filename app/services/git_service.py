from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re
import time
import git
from git.exc import InvalidGitRepositoryError, NoSuchPathError
from app.core.logger import logger


class GitService:
    """Service to interact with local Git repositories using GitPython."""

    IC_NODE_TAGS = {
        # Nós e estados do fluxo
        "node",
        "task-node",
        "decision",
        "state",
        "fork",
        "join",
        "process-state",
        # Transições e regras
        "transition",
        "condition",
        # Elementos de fluxo, tarefas, raias e ações
        "action",
        "task",
        "variable",
        "swimlane",
    }
    EXCLUDED_XML_TAGS = {
        "end-state",
        "process-definition",
        "start-state",
        "assignment",
        "controller",
        "script",
        "event",
        "description",
        "field",
        "property",
        "exception-handler",
        "timer",
    }
    TAG_REGEX = re.compile(r"^[+-]\s*<([a-zA-Z_:][a-zA-Z0-9_.:-]*)(\s+[^>]*)?")
    DIFF_GIT_REGEX = re.compile(r'diff --git (?:\"a/|a/)(.*) (?:\"b/|b/)(.*)')
    NAME_ATTR_REGEX = re.compile(r'name=["\']([^"\']+)["\']')
    TO_ATTR_REGEX = re.compile(r'to=["\']([^"\']+)["\']')
    EXPR_ATTR_REGEX = re.compile(r'expression=["\']([^"\']*)["\']')

    @classmethod
    def analyze_commit_xml_tags(cls, repo: git.Repo, commit_hash: str) -> Dict[str, Any]:
        """Extract XML tag metrics (both added and removed) globally and per flow from commit diff with smart pairing."""
        flows: Dict[str, Dict[str, Any]] = {}
        current_flow: Optional[str] = None

        flow_del_items: List[Tuple[str, str, str, str, str]] = []
        flow_add_items: List[Tuple[str, str, str, str, str]] = []

        def finalize_flow():
            nonlocal current_flow, flow_del_items, flow_add_items
            if not current_flow:
                return

            unmatched_del: List[Tuple[str, str, str, str, str]] = []
            matched_items: List[Tuple[str, str]] = []

            # Pass 1: smart match by identifier (name, to, expression) within same tag
            for dt, dn, dto, dex, da in flow_del_items:
                matched = False
                for at, an, ato, aex, aa in list(flow_add_items):
                    if dt == at:
                        is_match = False
                        if dn and an and (dn == an or dn in an or an in dn):
                            is_match = True
                        elif dto and ato and dto == ato:
                            is_match = True
                        elif dex and aex and (dex == aex or dex in aex or aex in dex):
                            is_match = True

                        if is_match:
                            matched_items.append((dt, dn or dto or dex))
                            flow_add_items.remove((at, an, ato, aex, aa))
                            matched = True
                            break
                if not matched:
                    unmatched_del.append((dt, dn, dto, dex, da))

            # Pass 2: match remaining deletions and additions of the same tag as adjustments
            final_unmatched_del: List[Tuple[str, str, str, str, str]] = []
            for dt, dn, dto, dex, da in unmatched_del:
                matched = False
                for at, an, ato, aex, aa in list(flow_add_items):
                    if dt == at:
                        matched_items.append((dt, dn or dto or dex))
                        flow_add_items.remove((at, an, ato, aex, aa))
                        matched = True
                        break
                if not matched:
                    final_unmatched_del.append((dt, dn, dto, dex, da))

            f_added: Dict[str, int] = {}
            f_removed: Dict[str, int] = {}
            f_modified: Dict[str, int] = {}

            # Unmatched deletions -> removals
            for dt, _, _, _, _ in final_unmatched_del:
                f_removed[dt] = f_removed.get(dt, 0) + 1

            # Unmatched additions -> additions
            for at, _, _, _, _ in flow_add_items:
                f_added[at] = f_added.get(at, 0) + 1

            # Matched pairs -> modifications (adjustments: 1 addition + 1 deletion = 1 adjustment)
            for dt, _ in matched_items:
                f_modified[dt] = f_modified.get(dt, 0) + 1

            f_tot_add = sum(f_added.values())
            f_tot_rem = sum(f_removed.values())
            f_tot_mod = sum(f_modified.values())
            f_tot_ics = f_tot_add + f_tot_rem + f_tot_mod

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

            flow_del_items = []
            flow_add_items = []

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
                        continue

                    if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                        continue

                    sign = line[0] if line else ""
                    if sign not in ("+", "-"):
                        continue

                    m = cls.TAG_REGEX.match(line)
                    if not m:
                        continue

                    tag = m.group(1).lower()
                    attrs = m.group(2) or ""

                    if tag in cls.EXCLUDED_XML_TAGS:
                        continue

                    if tag not in cls.IC_NODE_TAGS:
                        continue

                    m_name = cls.NAME_ATTR_REGEX.search(attrs)
                    name_val = m_name.group(1) if m_name else ""
                    m_to = cls.TO_ATTR_REGEX.search(attrs)
                    to_val = m_to.group(1) if m_to else ""
                    m_expr = cls.EXPR_ATTR_REGEX.search(attrs)
                    expr_val = m_expr.group(1) if m_expr else ""

                    if sign == "-":
                        flow_del_items.append((tag, name_val, to_val, expr_val, attrs))
                    else:
                        flow_add_items.append((tag, name_val, to_val, expr_val, attrs))

            finalize_flow()
        except Exception as exc:
            logger.debug(f"Erro ao extrair diff de tags XML para o commit {commit_hash[:7]}: {exc}")
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
                is_sql = display_path.lower().endswith(".sql")

                files_changed.append({
                    "path": display_path,
                    "old_path": old_path,
                    "filename": filename,
                    "is_xml": is_xml,
                    "is_sql": is_sql,
                    "is_rename": is_rename,
                    "status": status[0] if status else "M",
                    "insertions": ins,
                    "deletions": dels,
                    "lines": ins + dels,
                })
        except Exception as exc:
            logger.debug(f"Erro ao extrair diff_tree para commit {commit_hash[:7]}: {exc}")
        return files_changed

    @classmethod
    def analisar_scripts_sql_commit(cls, repo: git.Repo, commit_hash: str) -> Dict[str, Any]:
        """Analisa os arquivos .sql alterados no commit e extrai os casos de uso de banco de dados."""
        from app.services.sql_analyzer_service import SqlAnalyzerService

        try:
            patch = repo.git.show(commit_hash, "-M", "--", "*.sql")
        except Exception as exc:
            logger.debug(f"Erro ao extrair diff SQL para o commit {commit_hash}: {exc}")
            patch = ""

        if not patch or not patch.strip():
            return {
                "arquivos": {},
                "casos_de_uso": [],
                "use_cases": [],
                "total_ics": 0,
                "operacoes": {"criar": 0, "alterar": 0, "excluir": 0, "consultar": 0},
                "tabelas": [],
            }

        file_diffs = re.split(r"(?=diff --git )", patch)
        arquivos_map: Dict[str, Any] = {}
        todos_casos: List[str] = []
        todas_tabelas: List[str] = []
        tot_operacoes: Dict[str, int] = {"criar": 0, "alterar": 0, "excluir": 0, "consultar": 0}

        for fd in file_diffs:
            if not fd.strip():
                continue
            first_line = fd.strip().splitlines()[0]
            m_path = re.search(r"diff --git [ab]/(.*?) [ab]/(.*)", first_line)
            file_path = m_path.group(2) if m_path else "script.sql"
            clean_file_path = cls.decode_git_path(file_path)

            analise_arq = SqlAnalyzerService.processar_diff_sql(fd)
            if analise_arq["total_ics"] > 0:
                arquivos_map[clean_file_path] = analise_arq
                for c in analise_arq["casos_de_uso"]:
                    if c not in todos_casos:
                        todos_casos.append(c)
                for t in analise_arq["tabelas"]:
                    if t not in todas_tabelas:
                        todas_tabelas.append(t)
                for op, cnt in analise_arq["operacoes"].items():
                    tot_operacoes[op] = tot_operacoes.get(op, 0) + cnt

        if not arquivos_map and patch.strip():
            analise_global = SqlAnalyzerService.processar_diff_sql(patch)
            if analise_global["total_ics"] > 0:
                arquivos_map["scripts.sql"] = analise_global
                todos_casos = analise_global["casos_de_uso"]
                todas_tabelas = analise_global["tabelas"]
                tot_operacoes = analise_global["operacoes"]

        return {
            "arquivos": arquivos_map,
            "casos_de_uso": todos_casos,
            "use_cases": todos_casos,
            "total_ics": len(todos_casos),
            "operacoes": tot_operacoes,
            "tabelas": todas_tabelas,
        }

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


    _BRANCHES_CACHE: Dict[str, Dict[str, Any]] = {}
    _BRANCHES_CACHE_TTL: int = 300  # 5 minutos

    @classmethod
    def clear_branches_cache(cls, repo_path: Optional[str | Path] = None) -> None:
        """Clear cached branches for a specific repository or all repositories."""
        if repo_path:
            cls._BRANCHES_CACHE.pop(str(Path(repo_path).resolve()), None)
        else:
            cls._BRANCHES_CACHE.clear()

    @classmethod
    def get_branches(cls, repo_path: str | Path, force_refresh: bool = False) -> Dict[str, Any]:
        """Return active branch, list of local branches, and list of remote branches with in-memory TTL caching."""
        path = Path(repo_path).resolve()
        cache_key = str(path)

        if not force_refresh and cache_key in cls._BRANCHES_CACHE:
            cached = cls._BRANCHES_CACHE[cache_key]
            if time.time() - cached.get("timestamp", 0) < cls._BRANCHES_CACHE_TTL:
                return cached.get("data", {"active": "", "local": [], "remote": []})

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

            result = {
                "active": active,
                "local": sorted(list(local_set), key=str.lower),
                "remote": sorted(list(remote_set), key=str.lower),
            }
            cls._BRANCHES_CACHE[cache_key] = {
                "timestamp": time.time(),
                "data": result,
            }
            return result
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
        analyze_xml: bool = True,
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

                # Check for XML changes and analyze tags using icf.sh rules (lazy-loaded if analyze_xml is False)
                has_xml = any(
                    f.get("is_xml") or cls.decode_git_path(str(f.get("path", ""))).lower().endswith(".xml")
                    for f in files_changed
                    if isinstance(f, dict)
                )
                has_sql = any(
                    f.get("is_sql") or cls.decode_git_path(str(f.get("path", ""))).lower().endswith(".sql")
                    for f in files_changed
                    if isinstance(f, dict)
                )
                xml_analysis = cls.analyze_commit_xml_tags(repo, commit.hexsha) if (has_xml and analyze_xml) else {
                    "added": {},
                    "removed": {},
                    "total_added": 0,
                    "total_removed": 0,
                    "total_ics": 0,
                    "flows": {},
                }
                sql_analysis = cls.analisar_scripts_sql_commit(repo, commit.hexsha) if has_sql else {
                    "arquivos": {},
                    "casos_de_uso": [],
                    "total_ics": 0,
                    "operacoes": {},
                }

                total_xml_ics = xml_analysis.get("total_ics", 0)
                if total_xml_ics == 0 and has_xml:
                    total_xml_ics = 1
                total_sql_ics = sql_analysis.get("total_ics", 0)
                if total_sql_ics == 0 and has_sql:
                    total_sql_ics = 1

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
                        "sql_scripts_metrics": sql_analysis,
                        "ic_count_xml": total_xml_ics,
                        "ic_count_sql": total_sql_ics,
                        "ic_count": total_xml_ics + total_sql_ics,
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
            has_sql = any(f.get("is_sql") for f in files_changed)
            xml_analysis = cls.analyze_commit_xml_tags(repo, c.hexsha) if has_xml else {
                "added": {},
                "removed": {},
                "total_added": 0,
                "total_removed": 0,
                "total_ics": 0,
                "flows": {},
            }
            sql_analysis = cls.analisar_scripts_sql_commit(repo, c.hexsha) if has_sql else {
                "arquivos": {},
                "casos_de_uso": [],
                "total_ics": 0,
                "operacoes": {},
            }
            total_xml_ics = xml_analysis.get("total_ics", 0)
            if total_xml_ics == 0 and has_xml:
                total_xml_ics = 1
            total_sql_ics = sql_analysis.get("total_ics", 0)
            if total_sql_ics == 0 and has_sql:
                total_sql_ics = 1
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
                "sql_scripts_metrics": sql_analysis,
                "ic_count_xml": total_xml_ics,
                "ic_count_sql": total_sql_ics,
                "ic_count": total_xml_ics + total_sql_ics,
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
        analyze_xml: bool = True,
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
            has_sql = any(f.get("is_sql") for f in files_changed)
            xml_analysis = cls.analyze_commit_xml_tags(repo, commit.hexsha) if (has_xml and analyze_xml) else {
                "added": {},
                "removed": {},
                "total_added": 0,
                "total_removed": 0,
                "total_ics": 0,
                "flows": {},
            }
            sql_analysis = cls.analisar_scripts_sql_commit(repo, commit.hexsha) if has_sql else {
                "arquivos": {},
                "casos_de_uso": [],
                "total_ics": 0,
                "operacoes": {},
            }
            total_xml_ics = xml_analysis.get("total_ics", 0)
            if total_xml_ics == 0 and has_xml:
                total_xml_ics = 1
            total_sql_ics = sql_analysis.get("total_ics", 0)
            if total_sql_ics == 0 and has_sql:
                total_sql_ics = 1
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
                "sql_scripts_metrics": sql_analysis,
                "ic_count_xml": total_xml_ics,
                "ic_count_sql": total_sql_ics,
                "ic_count": total_xml_ics + total_sql_ics,
            })

        return matched_commits, has_more

