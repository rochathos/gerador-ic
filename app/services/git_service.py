from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re
import time
from concurrent.futures import ThreadPoolExecutor
import git
from urllib.parse import quote_plus
import httpx
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from app.core.config import settings
from app.core.logger import logger


@dataclass
class _XmlTagItem:
    """Representa um elemento de tag XML extraído do diff com seus atributos identificadores."""
    tag: str
    name: str = ""
    to: str = ""
    expr: str = ""
    actor: str = ""
    attrs: str = ""

    def identifica_mesmo_item(self, outro: "_XmlTagItem") -> bool:
        """Verifica se dois itens de mesma tag correspondem à mesma entidade lógica para detecção de alteração/ajuste."""
        if self.tag != outro.tag:
            return False
        if self.name and outro.name and (self.name == outro.name or self.name in outro.name or outro.name in self.name):
            return True
        if self.to and outro.to and self.to == outro.to:
            return True
        if self.expr and outro.expr and (self.expr == outro.expr or self.expr in outro.expr or outro.expr in self.expr):
            return True
        if self.actor and outro.actor and (self.actor == outro.actor or self.actor in outro.actor or outro.actor in self.actor):
            return True
        return False


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
        "assignment",
    }
    EXCLUDED_XML_TAGS = {
        "end-state",
        "process-definition",
        "start-state",
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
    ACTOR_ATTR_REGEX = re.compile(r'(?:pooled-actors|actor-id|class)=["\']([^"\']*)["\']')

    # Caches em memória e controle de TTL
    _BRANCHES_CACHE: Dict[str, Dict[str, Any]] = {}
    _BRANCHES_CACHE_TTL: int = 300  # 5 minutos
    _COMMIT_BRANCH_CACHE: Dict[str, str] = {}


    @classmethod
    def _parsear_linha_tag_xml(cls, line: str) -> Optional[Tuple[str, _XmlTagItem]]:
        """Extrai sinal (+/-) e item de tag XML de uma linha de diff caso seja um nó de IC válido."""
        if not line:
            return None
        sign = line[0]
        if sign not in ("+", "-"):
            return None
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            return None

        m = cls.TAG_REGEX.match(line)
        if not m:
            return None

        tag = m.group(1).lower()
        if tag in cls.EXCLUDED_XML_TAGS or tag not in cls.IC_NODE_TAGS:
            return None

        attrs = m.group(2) or ""
        m_name = cls.NAME_ATTR_REGEX.search(attrs)
        m_to = cls.TO_ATTR_REGEX.search(attrs)
        m_expr = cls.EXPR_ATTR_REGEX.search(attrs)
        m_actor = cls.ACTOR_ATTR_REGEX.search(attrs)

        item = _XmlTagItem(
            tag=tag,
            name=m_name.group(1) if m_name else "",
            to=m_to.group(1) if m_to else "",
            expr=m_expr.group(1) if m_expr else "",
            actor=m_actor.group(1) if m_actor else "",
            attrs=attrs,
        )
        return sign, item

    @classmethod
    def _parear_tags_fluxo(
        cls,
        del_items: List[_XmlTagItem],
        add_items: List[_XmlTagItem],
    ) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
        """Realiza casamento em dois passos entre adições e remoções de tags para identificar ajustes."""
        remaining_add = list(add_items)
        unmatched_del: List[_XmlTagItem] = []
        f_modified: Dict[str, int] = {}
        f_added: Dict[str, int] = {}
        f_removed: Dict[str, int] = {}

        # Passo 1: Casamento inteligente por identificadores (name, to, expr, actor)
        for d_item in del_items:
            matched = False
            for a_item in remaining_add:
                if d_item.identifica_mesmo_item(a_item):
                    f_modified[d_item.tag] = f_modified.get(d_item.tag, 0) + 1
                    remaining_add.remove(a_item)
                    matched = True
                    break
            if not matched:
                unmatched_del.append(d_item)

        # Passo 2: Casamento por tipo de tag restante (ajuste/substituição dentro da mesma tag)
        final_del: List[_XmlTagItem] = []
        for d_item in unmatched_del:
            matched = False
            for a_item in remaining_add:
                if d_item.tag == a_item.tag:
                    f_modified[d_item.tag] = f_modified.get(d_item.tag, 0) + 1
                    remaining_add.remove(a_item)
                    matched = True
                    break
            if not matched:
                final_del.append(d_item)

        for d_item in final_del:
            f_removed[d_item.tag] = f_removed.get(d_item.tag, 0) + 1

        for a_item in remaining_add:
            f_added[a_item.tag] = f_added.get(a_item.tag, 0) + 1

        return f_added, f_removed, f_modified

    @staticmethod
    def _agregar_metricas_xml(flows: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Totaliza métricas de tags adicionadas, removidas e modificadas entre todos os fluxos."""
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

        total_added = sum(commit_added.values())
        total_removed = sum(commit_removed.values())
        total_modified = sum(commit_modified.values())

        return {
            "added": commit_added,
            "removed": commit_removed,
            "modified": commit_modified,
            "total_added": total_added,
            "total_removed": total_removed,
            "total_modified": total_modified,
            "total_ics": total_added + total_removed + total_modified,
            "flows": flows,
        }

    @classmethod
    def analyze_commit_xml_tags(cls, repo: git.Repo, commit_hash: str) -> Dict[str, Any]:
        """Extract XML tag metrics (both added and removed) globally and per flow from commit diff with smart pairing."""
        flows: Dict[str, Dict[str, Any]] = {}
        current_flow: Optional[str] = None
        del_items: List[_XmlTagItem] = []
        add_items: List[_XmlTagItem] = []

        def finalize_flow():
            nonlocal current_flow, del_items, add_items
            if not current_flow:
                return

            f_added, f_removed, f_modified = cls._parear_tags_fluxo(del_items, add_items)
            f_tot_add = sum(f_added.values())
            f_tot_rem = sum(f_removed.values())
            f_tot_mod = sum(f_modified.values())
            f_tot_ics = f_tot_add + f_tot_rem + f_tot_mod

            flows[current_flow] = {
                "flow_name": current_flow.replace("\\", "/").split("/")[-1],
                "path": current_flow,
                "added": f_added,
                "removed": f_removed,
                "modified": f_modified,
                "total_added": f_tot_add,
                "total_removed": f_tot_rem,
                "total_modified": f_tot_mod,
                "total_ics": f_tot_ics,
            }
            del_items = []
            add_items = []

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

                    parsed = cls._parsear_linha_tag_xml(line)
                    if parsed:
                        sign, item = parsed
                        if sign == "-":
                            del_items.append(item)
                        else:
                            add_items.append(item)

            finalize_flow()
        except Exception as exc:
            logger.debug(f"Erro ao extrair diff de tags XML para o commit {commit_hash[:7]}: {exc}")

        return cls._agregar_metricas_xml(flows)

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

    @classmethod
    def _deve_usar_gitlab_remoto(cls, repo_path: Optional[str | Path] = None) -> bool:
        """Determina se a consulta Git deve ser direcionada para a API do GitLab via Access Token."""
        if not settings.GIT_ACCESS_TOKEN:
            return False
        if not repo_path:
            return True
        p_clean = str(repo_path).strip().replace("\\", "/").lower()
        base_dir_clean = str(settings.BASE_DIR).strip().replace("\\", "/").lower()
        if p_clean == base_dir_clean:
            return False
        default_path_clean = str(settings.DEFAULT_GIT_REPO_PATH or "").strip().replace("\\", "/").lower()
        if p_clean in (default_path_clean, "pje", "sistemas/pje") or "pje" in p_clean:
            return True
        try:
            if Path(repo_path).resolve().exists():
                return False
        except Exception:
            pass
        return False

    @classmethod
    def validate_repository(cls, repo_path: Optional[str | Path] = None) -> Tuple[bool, str]:
        """Validate if the given path is a valid Git repository, or if GitLab Access Token is configured."""
        if cls._deve_usar_gitlab_remoto(repo_path):
            return True, f"GitLab Remoto ({settings.DEFAULT_REPO_NAME or 'PJE'})"

        if not repo_path:
            return False, "Caminho de repositório não informado."

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
    def clear_branches_cache(cls, repo_path: Optional[str | Path] = None) -> None:
        """Clear cached branches for a specific repository or all repositories."""
        if repo_path:
            cls._BRANCHES_CACHE.pop(str(Path(repo_path).resolve()), None)
        else:
            cls._BRANCHES_CACHE.clear()

    @classmethod
    def get_branches(cls, repo_path: str | Path, force_refresh: bool = False) -> Dict[str, Any]:
        """Return active branch, list of local branches, and list of remote branches with in-memory TTL caching."""
        if cls._deve_usar_gitlab_remoto(repo_path):
            cache_key = "gitlab_remote_branches"
            if not force_refresh and cache_key in cls._BRANCHES_CACHE:
                cached = cls._BRANCHES_CACHE[cache_key]
                if time.time() - cached.get("timestamp", 0) < cls._BRANCHES_CACHE_TTL:
                    return cached.get("data", {"active": "master", "local": [], "remote": []})

            remote_branches = cls.get_remote_branches_api()
            result = {
                "active": "master",
                "local": [],
                "remote": remote_branches,
            }
            cls._BRANCHES_CACHE[cache_key] = {
                "timestamp": time.time(),
                "data": result,
            }
            return result

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

    @classmethod
    def _obter_branches_contendo_commit(
        cls, repo: git.Repo, commit_hash: str
    ) -> Tuple[str, List[str], List[str]]:
        """Obtém o nome da branch ativa e as listas de branches locais e remotas que contêm o commit."""
        active = ""
        if not repo.head.is_detached:
            try:
                active = cls.decode_git_path(repo.active_branch.name)
            except Exception:
                pass

        raw_local: List[str] = []
        try:
            raw_local = [
                cls.decode_git_path(b.strip("* ").strip())
                for b in repo.git.branch("--contains", commit_hash).splitlines()
                if b.strip()
            ]
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

        return active, raw_local, raw_rem

    @classmethod
    def _resolver_branch_por_tarefa(
        cls, repo: git.Repo, commit_hash: str, candidate_branches: List[str]
    ) -> Optional[str]:
        """Tenta associar o commit a uma branch caso a mensagem mencione o número da tarefa/issue."""
        try:
            msg = repo.commit(commit_hash).message
            m_issue = re.search(r"#?(\d{5,7})", msg)
            if m_issue:
                issue_num = m_issue.group(1)
                for b in candidate_branches:
                    if issue_num in b:
                        return b
        except Exception:
            pass
        return None

    @classmethod
    def _resolver_branch_por_proximidade(
        cls,
        repo: git.Repo,
        commit_hash: str,
        active: str,
        raw_local: List[str],
        raw_rem: List[str],
    ) -> Optional[str]:
        """Resolve a branch por proximidade com a ativa ou pela menor distância topológica no grafo."""
        # 1. Proximidade com branch ativa (se for ancestral direta em até 10 commits)
        if active and active in raw_local:
            try:
                dist = int(repo.git.rev_list("--count", f"{commit_hash}..{active}"))
                if dist <= 10:
                    return active
            except Exception:
                pass

        # 2. Pool de candidatos priorizando branches locais e de releases/hotfix/feature
        candidate_pool = raw_local + [
            b for b in raw_rem if b.startswith("releases/") or b.startswith("hotfix/") or b.startswith("feature/")
        ]
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

        return best_branch or None

    @classmethod
    def get_commit_branch(cls, repo_path: str | Path, commit_hash: str) -> str:
        """Resolve a branch de origem principal contendo este commit (tarefa, proximidade ou distância topológica)."""
        if not commit_hash:
            return ""
        if commit_hash in cls._COMMIT_BRANCH_CACHE:
            return cls._COMMIT_BRANCH_CACHE[commit_hash]

        path = Path(repo_path).resolve()
        branch_escolhida = ""

        try:
            repo = git.Repo(path)
            active, raw_local, raw_rem = cls._obter_branches_contendo_commit(repo, commit_hash)

            # Heurística 1: Número de tarefa/issue na mensagem do commit
            branch_escolhida = (
                cls._resolver_branch_por_tarefa(repo, commit_hash, raw_local)
                or cls._resolver_branch_por_tarefa(repo, commit_hash, raw_rem)
                or ""
            )

            # Heurísticas 2 e 3: Proximidade com branch ativa ou menor distância topológica
            if not branch_escolhida:
                branch_escolhida = cls._resolver_branch_por_proximidade(
                    repo=repo,
                    commit_hash=commit_hash,
                    active=active,
                    raw_local=raw_local,
                    raw_rem=raw_rem,
                ) or ""

            # Fallback: primeira branch local ou remota que contém o commit
            if not branch_escolhida:
                branch_escolhida = raw_local[0] if raw_local else (raw_rem[0] if raw_rem else "")

        except Exception:
            pass

        cls._COMMIT_BRANCH_CACHE[commit_hash] = branch_escolhida
        return branch_escolhida

    @staticmethod
    def _normalizar_datetime_utc(dt: Optional[datetime]) -> Optional[datetime]:
        """Normaliza datetime ingênuo para fuso UTC consciente."""
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    @classmethod
    def _obter_iterador_commits(
        cls,
        repo: git.Repo,
        branch: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        author: Optional[str] = None,
    ) -> Any:
        """Cria e configura o iterador de commits do Git com resolução de branch e fallbacks."""
        clean_b = (branch or "").strip()
        if clean_b and clean_b.upper() not in ["ALL", "TODAS"]:
            iter_kwargs: Dict[str, Any] = {"rev": clean_b}
        else:
            iter_kwargs: Dict[str, Any] = {"all": True}

        if start_date is not None:
            iter_kwargs["since"] = int(start_date.timestamp())
        if end_date is not None:
            iter_kwargs["until"] = int(end_date.timestamp())
        if author:
            iter_kwargs["author"] = author.strip()

        try:
            return repo.iter_commits(**iter_kwargs)
        except Exception as iter_err:
            logger.warning(
                f"Branch '{clean_b}' não pôde ser iterada diretamente ({iter_err}). Buscando com all=True."
            )
            iter_kwargs.pop("rev", None)
            iter_kwargs["all"] = True
            return repo.iter_commits(**iter_kwargs)

    @classmethod
    def _montar_dados_commit(
        cls,
        repo: git.Repo,
        repo_path: Path,
        commit: git.Commit,
        files_changed: List[Dict[str, Any]],
        branch: Optional[str] = None,
        analyze_xml: bool = True,
    ) -> Dict[str, Any]:
        """Constrói e padroniza o dicionário de dados e métricas de IC de um commit."""
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

        author_name = commit.author.name or ""
        author_email = commit.author.email or ""
        author_display = f"{author_name} <{author_email}>" if author_email else author_name

        clean_b = (branch or "").strip()
        if clean_b and clean_b.upper() not in ["ALL", "TODAS"]:
            commit_branch = clean_b
        else:
            commit_branch = cls.get_commit_branch(repo_path, commit.hexsha)

        return {
            "hash": commit.hexsha,
            "author": author_display,
            "author_name": author_name,
            "author_email": author_email,
            "commit_date": commit.committed_datetime,
            "message": commit.message.strip(),
            "files_changed": files_changed,
            "repo_name": cls.get_repo_name(repo_path),
            "repo_path": str(repo_path),
            "branch": commit_branch,
            "commit_url": cls.get_commit_url(repo_path, commit.hexsha),
            "xml_tags_metrics": xml_analysis,
            "sql_scripts_metrics": sql_analysis,
            "ic_count_xml": total_xml_ics,
            "ic_count_sql": total_sql_ics,
            "ic_count": total_xml_ics + total_sql_ics,
        }

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
        if cls._deve_usar_gitlab_remoto(repo_path):
            clean_b = (branch or "").strip()
            commits, _ = cls.get_remote_commits_api(
                branch=clean_b if clean_b and clean_b.upper() not in ["ALL", "TODAS"] else None,
                author=author,
                since=start_date,
                until=end_date,
                limit=100,
            )
            return commits

        path = Path(repo_path).resolve()
        is_valid, msg = cls.validate_repository(path)
        if not is_valid:
            logger.error(f"Validação de repositório falhou: {msg}")
            raise ValueError(msg)

        logger.info(
            f"Buscando commits no repositório '{path}' entre {start_date} e {end_date} (autor: {author or 'TODOS'}, branch: {branch or 'ALL'})"
        )

        repo = git.Repo(path)

        start_date_tz = cls._normalizar_datetime_utc(start_date)
        end_date_tz = cls._normalizar_datetime_utc(end_date)
        clean_b = (branch or "").strip()
        commits_found: List[Dict[str, Any]] = []

        try:
            commit_iter = cls._obter_iterador_commits(
                repo=repo,
                branch=clean_b,
                start_date=start_date_tz,
                end_date=end_date_tz,
            )

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

                files_changed = cls.get_commit_files(repo, commit.hexsha)
                dados_commit = cls._montar_dados_commit(
                    repo=repo,
                    repo_path=path,
                    commit=commit,
                    files_changed=files_changed,
                    branch=clean_b,
                    analyze_xml=analyze_xml,
                )
                commits_found.append(dados_commit)

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
        if cls._deve_usar_gitlab_remoto(repo_path):
            return cls.get_remote_commit_by_hash_api(commit_hash)

        path = Path(repo_path).resolve()
        is_valid, _ = cls.validate_repository(path)
        if not is_valid:
            return None
        try:
            repo = git.Repo(path)
            c = repo.commit(commit_hash.strip())
            files_changed = cls.get_commit_files(repo, c.hexsha)
            return cls._montar_dados_commit(
                repo=repo,
                repo_path=path,
                commit=c,
                files_changed=files_changed,
                branch=None,
                analyze_xml=True,
            )
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
        if cls._deve_usar_gitlab_remoto(repo_path):
            clean_b = (branch or "").strip()
            page = (skip // limit) + 1 if limit > 0 else 1
            return cls.get_remote_commits_api(
                branch=clean_b if clean_b and clean_b.upper() not in ["ALL", "TODAS"] else None,
                author=author,
                since=start_date,
                until=end_date,
                limit=limit,
                page=page,
                query_filter=q,
                only_xml=only_xml,
            )
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
        start_date_tz = cls._normalizar_datetime_utc(start_date)
        end_date_tz = cls._normalizar_datetime_utc(end_date)

        matched_commits: List[Dict[str, Any]] = []
        has_more = False
        skipped = 0
        query_text = q.strip().lower() if q else ""

        commit_iter = cls._obter_iterador_commits(
            repo=repo,
            branch=clean_b,
            start_date=start_date_tz,
            end_date=end_date_tz,
            author=author,
        )

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

            dados_commit = cls._montar_dados_commit(
                repo=repo,
                repo_path=path,
                commit=commit,
                files_changed=files_changed,
                branch=clean_b,
                analyze_xml=analyze_xml,
            )
            matched_commits.append(dados_commit)


        return matched_commits, has_more

    # -------------------------------------------------------------------------
    # Métodos de Integração com a API do GitLab e Autenticação Remota
    # -------------------------------------------------------------------------

    @classmethod
    def _get_gitlab_headers(cls, token: Optional[str] = None) -> Dict[str, str]:
        """Retorna cabeçalhos HTTP autenticados para a API do GitLab."""
        tok = token or settings.GIT_ACCESS_TOKEN
        headers = {"Content-Type": "application/json"}
        if tok:
            headers["PRIVATE-TOKEN"] = tok
        return headers

    @classmethod
    def get_gitlab_project_path(cls, repo_path: Optional[str | Path] = None) -> str:
        """Extrai o namespace/projeto GitLab a partir da URL remota ou configurações."""
        if repo_path:
            path = Path(repo_path).resolve()
            if path.exists():
                try:
                    repo = git.Repo(path)
                    for remote in repo.remotes:
                        for raw_url in remote.urls:
                            clean = raw_url.strip()
                            if "git.tjce.jus.br" in clean or "gitlab" in clean:
                                match = re.search(r"[:/]([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+?)(?:\.git)?$", clean)
                                if match:
                                    return match.group(1).rstrip("/")
                except Exception:
                    pass
        return "sistemas/PJE"

    @classmethod
    def test_gitlab_connection(
        cls,
        token: Optional[str] = None,
        gitlab_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Testa conectividade e valida credenciais com a API do GitLab."""
        base_url = (gitlab_url or settings.GITLAB_URL).rstrip("/")
        tok = token or settings.GIT_ACCESS_TOKEN
        if not tok:
            return {
                "success": False,
                "message": "Nenhum Access Token do GitLab configurado.",
                "status_code": 400,
                "user": None,
            }

        headers = cls._get_gitlab_headers(tok)
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{base_url}/api/v4/user", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    user_info = {
                        "id": data.get("id"),
                        "username": data.get("username"),
                        "name": data.get("name"),
                        "email": data.get("email"),
                    }
                    return {
                        "success": True,
                        "message": f"Conexão com GitLab realizada com sucesso! Usuário: {user_info['name']} (@{user_info['username']})",
                        "status_code": 200,
                        "user": user_info,
                    }
                elif resp.status_code in (401, 403):
                    return {
                        "success": False,
                        "message": "Token do GitLab inválido, sem permissões ou expirado.",
                        "status_code": resp.status_code,
                        "user": None,
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Erro retornado pelo GitLab: HTTP {resp.status_code}",
                        "status_code": resp.status_code,
                        "user": None,
                    }
        except httpx.TimeoutException:
            logger.warning(f"Timeout ao conectar na API do GitLab ({base_url})")
            return {
                "success": False,
                "message": "Tempo limite esgotado ao conectar no GitLab. Verifique sua conexão ou VPN institucional.",
                "status_code": 504,
                "user": None,
            }
        except httpx.ConnectError:
            logger.warning(f"Erro de conexão ao acessar o GitLab ({base_url})")
            return {
                "success": False,
                "message": "Não foi possível conectar ao servidor do GitLab. Verifique se o endereço está acessível na rede.",
                "status_code": 503,
                "user": None,
            }
        except Exception as exc:
            err_msg = re.sub(r"glpat-[a-zA-Z0-9_\-]+", "glpat-***[MASKED]***", str(exc))
            logger.warning(f"Falha ao conectar na API do GitLab ({base_url}): {err_msg}")
            return {
                "success": False,
                "message": f"Falha de comunicação com o GitLab: {err_msg}",
                "status_code": 500,
                "user": None,
            }

    @classmethod
    def get_remote_branches_api(
        cls,
        project_path: Optional[str] = None,
        token: Optional[str] = None,
        gitlab_url: Optional[str] = None,
    ) -> List[str]:
        """Lista branches remotas diretamente da API do GitLab."""
        base_url = (gitlab_url or settings.GITLAB_URL).rstrip("/")
        proj = quote_plus(project_path or cls.get_gitlab_project_path())
        headers = cls._get_gitlab_headers(token)

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{base_url}/api/v4/projects/{proj}/repository/branches",
                    headers=headers,
                    params={"per_page": 100},
                )
                if resp.status_code == 200:
                    branches = [b.get("name") for b in resp.json() if b.get("name")]
                    return sorted(branches, key=str.lower)
                logger.warning(f"Erro ao listar branches da API do GitLab: HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning(f"Exceção ao listar branches remotas da API do GitLab: {exc}")
        return []

    @classmethod
    def _processar_diffs_remotos(cls, diff_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Processa a lista de diffs retornada pela API do GitLab e extrai arquivos, métricas XML e SQL."""
        from app.services.sql_analyzer_service import SqlAnalyzerService

        files_changed: List[Dict[str, Any]] = []
        flows: Dict[str, Dict[str, Any]] = {}
        sql_arquivos_map: Dict[str, Any] = {}
        sql_todos_casos: List[str] = []
        sql_todas_tabelas: List[str] = []
        sql_tot_operacoes: Dict[str, int] = {"criar": 0, "alterar": 0, "excluir": 0, "consultar": 0}

        for d in diff_items:
            new_path_raw = d.get("new_path") or ""
            old_path_raw = d.get("old_path") or ""
            is_rename = bool(d.get("renamed_file"))
            display_path = cls.decode_git_path(new_path_raw or old_path_raw)
            old_path = cls.decode_git_path(old_path_raw) if is_rename else ""
            filename = display_path.replace("\\", "/").split("/")[-1]
            is_xml = display_path.lower().endswith(".xml")
            is_sql = display_path.lower().endswith(".sql")

            if d.get("new_file"):
                status = "A"
            elif d.get("deleted_file"):
                status = "D"
            elif is_rename:
                status = "R"
            else:
                status = "M"

            diff_text = d.get("diff") or ""
            ins = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
            dels = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))

            files_changed.append({
                "path": display_path,
                "old_path": old_path,
                "filename": filename,
                "is_xml": is_xml,
                "is_sql": is_sql,
                "is_rename": is_rename,
                "status": status,
                "insertions": ins,
                "deletions": dels,
                "lines": ins + dels,
            })

            # Processamento de tags XML de fluxo
            if is_xml and diff_text:
                del_items: List[_XmlTagItem] = []
                add_items: List[_XmlTagItem] = []
                for line in diff_text.splitlines():
                    parsed = cls._parsear_linha_tag_xml(line)
                    if parsed:
                        sign, item = parsed
                        if sign == "-":
                            del_items.append(item)
                        else:
                            add_items.append(item)

                f_added, f_removed, f_modified = cls._parear_tags_fluxo(del_items, add_items)
                f_tot_add = sum(f_added.values())
                f_tot_rem = sum(f_removed.values())
                f_tot_mod = sum(f_modified.values())
                f_tot_ics = f_tot_add + f_tot_rem + f_tot_mod

                flows[display_path] = {
                    "flow_name": filename,
                    "path": display_path,
                    "added": f_added,
                    "removed": f_removed,
                    "modified": f_modified,
                    "total_added": f_tot_add,
                    "total_removed": f_tot_rem,
                    "total_modified": f_tot_mod,
                    "total_ics": f_tot_ics,
                }

            # Processamento de scripts SQL
            if is_sql and diff_text:
                analise_sql = SqlAnalyzerService.processar_diff_sql(diff_text)
                if analise_sql.get("total_ics", 0) > 0:
                    sql_arquivos_map[display_path] = analise_sql
                    for c in analise_sql.get("casos_de_uso", []):
                        if c not in sql_todos_casos:
                            sql_todos_casos.append(c)
                    for t in analise_sql.get("tabelas", []):
                        if t not in sql_todas_tabelas:
                            sql_todas_tabelas.append(t)
                    for op, cnt in analise_sql.get("operacoes", {}).items():
                        sql_tot_operacoes[op] = sql_tot_operacoes.get(op, 0) + cnt

        xml_metrics = cls._agregar_metricas_xml(flows)
        sql_metrics = {
            "arquivos": sql_arquivos_map,
            "casos_de_uso": sql_todos_casos,
            "use_cases": sql_todos_casos,
            "total_ics": len(sql_todos_casos),
            "operacoes": sql_tot_operacoes,
            "tabelas": sql_todas_tabelas,
        }

        has_xml = any(f["is_xml"] for f in files_changed)
        has_sql = any(f["is_sql"] for f in files_changed)

        total_xml_ics = xml_metrics.get("total_ics", 0)
        if total_xml_ics == 0 and has_xml:
            total_xml_ics = 1

        total_sql_ics = sql_metrics.get("total_ics", 0)
        if total_sql_ics == 0 and has_sql:
            total_sql_ics = 1

        total_ics = total_xml_ics + total_sql_ics
        if total_ics == 0:
            total_ics = 1

        return {
            "files_changed": files_changed,
            "xml_tags_metrics": xml_metrics,
            "sql_scripts_metrics": sql_metrics,
            "ic_count_xml": total_xml_ics,
            "ic_count_sql": total_sql_ics,
            "ic_count": total_ics,
        }

    @classmethod
    def get_remote_commit_by_hash_api(
        cls,
        commit_hash: str,
        project_path: Optional[str] = None,
        token: Optional[str] = None,
        gitlab_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Busca os detalhes e o diff de um commit específico diretamente via API do GitLab."""
        clean_hash = commit_hash.strip()
        if not clean_hash:
            return None

        base_url = (gitlab_url or settings.GITLAB_URL).rstrip("/")
        proj_name = project_path or cls.get_gitlab_project_path()
        proj_encoded = quote_plus(proj_name)
        headers = cls._get_gitlab_headers(token)

        try:
            with httpx.Client(timeout=15.0) as client:
                resp_commit = client.get(
                    f"{base_url}/api/v4/projects/{proj_encoded}/repository/commits/{clean_hash}",
                    headers=headers,
                )
                if resp_commit.status_code != 200:
                    logger.debug(f"Commit {clean_hash} não encontrado na API do GitLab: HTTP {resp_commit.status_code}")
                    return None

                rc = resp_commit.json()
                resp_diff = client.get(
                    f"{base_url}/api/v4/projects/{proj_encoded}/repository/commits/{clean_hash}/diff",
                    headers=headers,
                )
                diff_items = resp_diff.json() if resp_diff.status_code == 200 else []

                diff_metrics = cls._processar_diffs_remotos(diff_items)

                c_hash = rc.get("id") or clean_hash
                short_hash = rc.get("short_id") or c_hash[:7]
                msg = rc.get("message") or ""
                c_author = rc.get("author_name") or ""
                c_email = rc.get("author_email") or ""

                created_str = rc.get("created_at") or ""
                c_dt = None
                if created_str:
                    try:
                        c_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                web_url = rc.get("web_url") or f"{base_url}/{proj_name}/-/commit/{c_hash}"

                return {
                    "hash": c_hash,
                    "short_hash": short_hash,
                    "author": f"{c_author} <{c_email}>" if c_email else c_author,
                    "author_name": c_author,
                    "author_email": c_email,
                    "commit_date": c_dt or created_str,
                    "message": msg,
                    "files_changed": diff_metrics["files_changed"],
                    "repo_name": proj_name.split("/")[-1],
                    "repo_path": "",
                    "branch": "",
                    "commit_url": web_url,
                    "xml_tags_metrics": diff_metrics["xml_tags_metrics"],
                    "sql_scripts_metrics": diff_metrics["sql_scripts_metrics"],
                    "ic_count_xml": diff_metrics["ic_count_xml"],
                    "ic_count_sql": diff_metrics["ic_count_sql"],
                    "ic_count": diff_metrics["ic_count"],
                }
        except Exception as exc:
            logger.error(f"Erro ao buscar commit remoto {clean_hash} na API do GitLab: {exc}")
            return None

    @classmethod
    def get_remote_commits_api(
        cls,
        project_path: Optional[str] = None,
        branch: Optional[str] = None,
        author: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 20,
        page: int = 1,
        token: Optional[str] = None,
        gitlab_url: Optional[str] = None,
        query_filter: Optional[str] = None,
        only_xml: bool = False,
        analyze_diffs: bool = True,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Consulta commits diretamente pela API REST do GitLab v4."""
        # Se query_filter for um hash específico (>= 4 caracteres hexadecimais), tenta busca direta
        if query_filter and len(query_filter.strip()) >= 4:
            clean_q = query_filter.strip()
            single = cls.get_remote_commit_by_hash_api(clean_q, project_path=project_path, token=token, gitlab_url=gitlab_url)
            if single:
                if only_xml and not any(f.get("is_xml") for f in single.get("files_changed", [])):
                    return [], False
                return [single], False

        base_url = (gitlab_url or settings.GITLAB_URL).rstrip("/")
        proj_name = project_path or cls.get_gitlab_project_path()
        proj_encoded = quote_plus(proj_name)
        headers = cls._get_gitlab_headers(token)

        params: Dict[str, Any] = {
            "per_page": min(max(limit, 1), 100),
            "page": max(page, 1),
            "with_stats": "true",
        }
        clean_b = (branch or "").strip()
        if clean_b and clean_b.upper() not in ["ALL", "TODAS"]:
            params["ref_name"] = clean_b
        else:
            params["all"] = "true"

        if author and author.strip():
            params["author"] = author.strip()
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()
        if query_filter and query_filter.strip():
            params["search"] = query_filter.strip()

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{base_url}/api/v4/projects/{proj_encoded}/repository/commits",
                    headers=headers,
                    params=params,
                )
                if resp.status_code != 200:
                    logger.warning(f"GitLab API retornou status {resp.status_code} para commits: {resp.text[:200]}")
                    return [], False

                raw_commits = resp.json()
                x_next_page = resp.headers.get("x-next-page")
                total_pages_header = resp.headers.get("x-total-pages")

                if x_next_page and x_next_page.strip():
                    has_more = True
                elif total_pages_header:
                    try:
                        has_more = page < int(total_pages_header)
                    except Exception:
                        has_more = len(raw_commits) >= limit
                else:
                    has_more = len(raw_commits) >= limit

                if not raw_commits:
                    return [], False

                # Busca concorrente dos diffs para enriquecer métricas com alta performance
                diffs_map: Dict[str, List[Dict[str, Any]]] = {}
                if analyze_diffs:
                    def _fetch_diff(cid: str) -> Tuple[str, List[Dict[str, Any]]]:
                        try:
                            r_d = client.get(
                                f"{base_url}/api/v4/projects/{proj_encoded}/repository/commits/{cid}/diff",
                                headers=headers,
                            )
                            return cid, (r_d.json() if r_d.status_code == 200 else [])
                        except Exception:
                            return cid, []

                    commit_ids = [rc.get("id") for rc in raw_commits if rc.get("id")]
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        for cid, diff_items in executor.map(_fetch_diff, commit_ids):
                            diffs_map[cid] = diff_items

                commits: List[Dict[str, Any]] = []
                for rc in raw_commits:
                    c_hash = rc.get("id") or ""
                    short_hash = rc.get("short_id") or c_hash[:7]
                    msg = rc.get("message") or ""
                    c_author = rc.get("author_name") or ""
                    c_email = rc.get("author_email") or ""

                    created_str = rc.get("created_at") or ""
                    c_dt = None
                    if created_str:
                        try:
                            c_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    diff_items = diffs_map.get(c_hash, [])
                    diff_metrics = cls._processar_diffs_remotos(diff_items)

                    if query_filter and query_filter.strip():
                        q_lower = query_filter.strip().lower()
                        if (
                            q_lower not in c_hash.lower()
                            and q_lower not in msg.lower()
                            and q_lower not in c_author.lower()
                            and q_lower not in c_email.lower()
                        ):
                            continue

                    if only_xml and not any(f.get("is_xml") for f in diff_metrics["files_changed"]):
                        continue

                    web_url = rc.get("web_url") or f"{base_url}/{proj_name}/-/commit/{c_hash}"

                    commits.append({
                        "hash": c_hash,
                        "short_hash": short_hash,
                        "author": f"{c_author} <{c_email}>" if c_email else c_author,
                        "author_name": c_author,
                        "author_email": c_email,
                        "commit_date": c_dt or created_str,
                        "message": msg,
                        "files_changed": diff_metrics["files_changed"],
                        "repo_name": proj_name.split("/")[-1],
                        "repo_path": "",
                        "branch": clean_b,
                        "commit_url": web_url,
                        "xml_tags_metrics": diff_metrics["xml_tags_metrics"],
                        "sql_scripts_metrics": diff_metrics["sql_scripts_metrics"],
                        "ic_count_xml": diff_metrics["ic_count_xml"],
                        "ic_count_sql": diff_metrics["ic_count_sql"],
                        "ic_count": diff_metrics["ic_count"],
                    })

                # Ordena commits do mais recente para o mais antigo (ordem cronológica decrescente)
                def _parse_commit_dt(c: Dict[str, Any]) -> datetime:
                    dt = c.get("commit_date")
                    if isinstance(dt, datetime):
                        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                    if isinstance(dt, str) and dt:
                        try:
                            return datetime.fromisoformat(dt.replace("Z", "+00:00"))
                        except Exception:
                            pass
                    return datetime.min.replace(tzinfo=timezone.utc)

                commits.sort(key=_parse_commit_dt, reverse=True)

                return commits, has_more
        except Exception as exc:
            logger.error(f"Erro ao buscar commits remotos na API do GitLab: {exc}")
            return [], False

    @classmethod
    def fetch_remote_with_token(
        cls,
        repo_path: str | Path,
        remote_name: str = "origin",
    ) -> Tuple[bool, str]:
        """Executa git fetch no repositório local injetando o token de acesso de forma segura."""
        path = Path(repo_path).resolve()
        is_valid, msg = cls.validate_repository(path)
        if not is_valid:
            return False, msg

        token = settings.GIT_ACCESS_TOKEN
        try:
            repo = git.Repo(path)
            if token:
                # Injeta temporariamente o header HTTP sem gravar no .git/config
                repo.git.execute(["git", "-c", f"http.extraheader=PRIVATE-TOKEN: {token}", "fetch", remote_name])
            else:
                repo.git.fetch(remote_name)
            cls.clear_branches_cache(path)
            return True, "Repositório sincronizado com sucesso!"
        except Exception as exc:
            err_msg = re.sub(r"glpat-[a-zA-Z0-9_\-]+", "glpat-***[MASKED]***", str(exc))
            if token:
                err_msg = err_msg.replace(token, "glpat-***[MASKED]***")
            logger.warning(f"Erro ao executar git fetch em {path}: {err_msg}")
            return False, f"Falha ao sincronizar repositório: {err_msg}"


