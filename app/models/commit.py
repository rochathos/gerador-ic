from datetime import datetime
from typing import Optional, List, Any, Dict
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


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


def normalize_xml_metrics(raw: Any, default_count: int = 0) -> Dict[str, Any]:
    """Normalize raw xml_tags_metrics into a standard dict containing added/removed/modified, flows, and counts."""
    if not isinstance(raw, dict):
        return {
            "added": {},
            "removed": {},
            "modified": {},
            "total_added": 0,
            "total_removed": 0,
            "total_modified": 0,
            "total_ics": default_count or 0,
            "flows": {},
        }
    if "added" in raw or "removed" in raw or "modified" in raw or "flows" in raw:
        added = raw.get("added") or {}
        removed = raw.get("removed") or {}
        modified = raw.get("modified") or {}
        total_added = raw.get("total_added", sum(added.values()))
        total_removed = raw.get("total_removed", sum(removed.values()))
        total_modified = raw.get("total_modified", sum(modified.values()))
        total_ics = raw.get("total_ics", total_added + total_removed + total_modified)
        flows = raw.get("flows") or {}
        if isinstance(flows, list):
            flows_dict = {}
            for idx, f in enumerate(flows):
                if isinstance(f, dict):
                    key = f.get("flow_name") or f.get("filename") or f.get("path") or f"flow_{idx}"
                    flows_dict[key] = f
            flows = flows_dict
        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "total_added": total_added,
            "total_removed": total_removed,
            "total_modified": total_modified,
            "total_ics": total_ics or default_count or 0,
            "flows": flows,
        }
    # Backward compatibility for flat dict {tag: count}
    total_added = sum(raw.values())
    return {
        "added": raw,
        "removed": {},
        "modified": {},
        "total_added": total_added,
        "total_removed": 0,
        "total_modified": 0,
        "total_ics": default_count or total_added,
        "flows": {},
    }


def format_ic_details(parsed_metrics: Dict[str, Any], ic_count: int = 0) -> List[str]:
    """Helper to generate detailed IC calculation lines showing additions, removals, and modifications per flow (XML file)."""
    total_ics = ic_count or parsed_metrics.get("total_ics", 0)
    if total_ics <= 0:
        return []

    lines: List[str] = [""]
    added_cnt = parsed_metrics.get("total_added", 0)
    removed_cnt = parsed_metrics.get("total_removed", 0)
    modified_cnt = parsed_metrics.get("total_modified", 0)

    parts: List[str] = []
    if added_cnt > 0:
        parts.append(f"+{added_cnt} adições")
    if removed_cnt > 0:
        parts.append(f"-{removed_cnt} remoções")
    if modified_cnt > 0:
        parts.append(f"~{modified_cnt} ajustes")
    summary_str = f" ({', '.join(parts)})" if parts else ""

    lines.append(f"Itens de Catálogo (IC) calculados: {total_ics} IC(s){summary_str}")

    flows = parsed_metrics.get("flows") or {}
    if flows:
        lines.append("")
        lines.append("Detalhamento por Fluxo (regras do PJE):")
        for path, flow_data in flows.items():
            f_added = flow_data.get("added", {})
            f_removed = flow_data.get("removed", {})
            f_modified = flow_data.get("modified", {})
            f_total_added = flow_data.get("total_added", sum(f_added.values()))
            f_total_removed = flow_data.get("total_removed", sum(f_removed.values()))
            f_total_modified = flow_data.get("total_modified", sum(f_modified.values()))
            f_total_ics = flow_data.get("total_ics", f_total_added + f_total_removed + f_total_modified)

            if f_total_ics == 0:
                continue

            lines.append("")
            lines.append(f"Fluxo: {path}")
            if f_added:
                lines.append(f"* Tags Adicionadas (+{f_total_added}):")
                for tag, count in sorted(f_added.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"** <{tag}>: {count}")
            if f_removed:
                lines.append(f"* Tags Removidas (-{f_total_removed}):")
                for tag, count in sorted(f_removed.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"** <{tag}>: {count}")
            if f_modified:
                lines.append(f"* Tags Modificadas / Ajustadas (~{f_total_modified}):")
                for tag, count in sorted(f_modified.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"** <{tag}>: {count}")
    else:
        added_tags = parsed_metrics.get("added", {})
        removed_tags = parsed_metrics.get("removed", {})
        modified_tags = parsed_metrics.get("modified", {})
        if added_tags or removed_tags or modified_tags:
            lines.append("Detalhamento das tags XML (regras do PJE):")
            if added_tags:
                lines.append(f"* Tags Adicionadas (+{added_cnt}):")
                for tag, count in sorted(added_tags.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"** <{tag}>: {count}")
            if removed_tags:
                lines.append(f"* Tags Removidas (-{removed_cnt}):")
                for tag, count in sorted(removed_tags.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"** <{tag}>: {count}")
            if modified_tags:
                lines.append(f"* Tags Modificadas / Ajustadas (~{modified_cnt}):")
                for tag, count in sorted(modified_tags.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"** <{tag}>: {count}")

    return lines


def find_flow_metrics_for_file(path: str, flows: Any) -> Optional[Dict[str, Any]]:
    """Match a file path against the flows dictionary or list by exact path, normalized path, or basename."""
    if not flows or not path:
        return None
    norm_path = path.replace("\\", "/").strip().lower()
    base = norm_path.split("/")[-1]

    if isinstance(flows, dict):
        if path in flows:
            return flows[path]
        for f_path, f_data in flows.items():
            if str(f_path).replace("\\", "/").strip().lower() == norm_path:
                return f_data
        for f_path, f_data in flows.items():
            if str(f_path).replace("\\", "/").strip().lower().split("/")[-1] == base:
                return f_data
        return None
    elif isinstance(flows, list):
        for f in flows:
            if isinstance(f, dict):
                flow_name = str(f.get("flow_name") or f.get("filename") or f.get("path") or "").replace("\\", "/").strip().lower()
                if flow_name == norm_path or flow_name.split("/")[-1] == base:
                    return f
        return None
    return None


def format_flow_tags_lines(flow_data: Dict[str, Any]) -> List[str]:
    """Format tags touched for a specific flow with Redmine Textile nested list syntax."""
    lines: List[str] = []
    f_added = flow_data.get("added", {})
    f_removed = flow_data.get("removed", {})
    f_modified = flow_data.get("modified", {})
    f_total_added = flow_data.get("total_added", sum(f_added.values()))
    f_total_removed = flow_data.get("total_removed", sum(f_removed.values()))
    f_total_modified = flow_data.get("total_modified", sum(f_modified.values()))

    if f_added:
        lines.append(f"** Tags Adicionadas (+{f_total_added}):")
        for tag, count in sorted(f_added.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"*** <{tag}>: {count}")
    if f_removed:
        lines.append(f"** Tags Removidas (-{f_total_removed}):")
        for tag, count in sorted(f_removed.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"*** <{tag}>: {count}")
    if f_modified:
        lines.append(f"** Tags Modificadas / Ajustadas (~{f_total_modified}):")
        for tag, count in sorted(f_modified.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"*** <{tag}>: {count}")

    return lines


def build_ic_description(
    short_hash: str,
    commit_date: Any,
    author: str,
    message: str,
    commit_url: str = "",
    files_changed: Optional[List[Any]] = None,
    xml_tags_metrics: Optional[Dict[str, Any]] = None,
    ic_count: int = 0,
) -> str:
    """Build the clean, compact Redmine IC description.

    Tags touched are displayed directly below each altered XML file (fluxo) in 'Arquivos Alterados:',
    making the text shorter, more readable, and avoiding duplicate flow sections.
    """
    date_str = ""
    if commit_date:
        try:
            date_str = commit_date.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_str = str(commit_date)

    parsed_metrics = normalize_xml_metrics(xml_tags_metrics or {}, ic_count)
    total_ics = ic_count or parsed_metrics.get("total_ics", 0)
    flows = parsed_metrics.get("flows") or {}

    lines = [
        f"Commit: {short_hash}",
        f"Data: {date_str}",
        f"Autor: {author}",
    ]
    if commit_url:
        lines.append(f"Link: {commit_url}")

    lines.append("")
    lines.append("Descrição:")
    lines.append(message.strip() if message else "")

    added_cnt = parsed_metrics.get("total_added", 0)
    removed_cnt = parsed_metrics.get("total_removed", 0)
    modified_cnt = parsed_metrics.get("total_modified", 0)
    if total_ics > 0:
        parts: List[str] = []
        if added_cnt > 0:
            parts.append(f"+{added_cnt} adições")
        if removed_cnt > 0:
            parts.append(f"-{removed_cnt} remoções")
        if modified_cnt > 0:
            parts.append(f"~{modified_cnt} ajustes")
        summary_str = f" ({', '.join(parts)})" if parts else ""
        lines.append("")
        lines.append(f"Itens de Catálogo (IC) calculados: {total_ics} IC(s){summary_str}")

    clean_files = files_changed or []
    if clean_files:
        lines.append("")
        lines.append("Arquivos Alterados:")
        xml_count = 0
        matched_flow_paths = set()

        for f in clean_files:
            if isinstance(f, dict):
                raw_path = f.get("path") or f.get("filename") or ""
                path = decode_git_path(raw_path)
                ins = f.get("insertions", 0)
                dels = f.get("deletions", 0)
                diff_info = f" (+{ins} / -{dels})" if (ins or dels) else ""
                is_xml = f.get("is_xml") or path.lower().endswith(".xml")
            else:
                path = decode_git_path(str(f))
                diff_info = ""
                is_xml = path.lower().endswith(".xml")

            if is_xml:
                xml_count += 1
                lines.append(f"* [XML] {path}{diff_info}")
                flow_data = find_flow_metrics_for_file(path, flows)
                if flow_data:
                    matched_flow_paths.add(flow_data.get("path", path))
                    lines.extend(format_flow_tags_lines(flow_data))
            else:
                lines.append(f"* {path}{diff_info}")

        # In case some flows were not in files_changed (fallback)
        for f_path, f_data in flows.items():
            if f_data.get("total_ics", 0) > 0 and f_path not in matched_flow_paths:
                flow_check = find_flow_metrics_for_file(f_path, {p: {} for p in matched_flow_paths})
                if not flow_check:
                    xml_count += 1
                    lines.append(f"* [XML] {f_path}")
                    lines.extend(format_flow_tags_lines(f_data))

        if xml_count > 0:
            lines.append(f"(Total de arquivos XML alterados: {xml_count})")
    elif flows:
        lines.append("")
        lines.append("Arquivos Alterados:")
        xml_count = 0
        for f_path, f_data in flows.items():
            if f_data.get("total_ics", 0) > 0:
                xml_count += 1
                lines.append(f"* [XML] {f_path}")
                lines.extend(format_flow_tags_lines(f_data))
        if xml_count > 0:
            lines.append(f"(Total de arquivos XML alterados: {xml_count})")
    elif total_ics > 0 and (added_cnt > 0 or removed_cnt > 0):
        lines.append("")
        lines.append("Tags XML Alteradas:")
        added_tags = parsed_metrics.get("added", {})
        removed_tags = parsed_metrics.get("removed", {})
        if added_tags:
            lines.append(f"* Tags Adicionadas (+{added_cnt}):")
            for t, c in sorted(added_tags.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"** <{t}>: {c}")
        if removed_tags:
            lines.append(f"* Tags Removidas (-{removed_cnt}):")
            for t, c in sorted(removed_tags.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"** <{t}>: {c}")

    return "\n".join(lines)


def formatar_linhas_casos_de_uso_sql(dados_sql: Dict[str, Any]) -> List[str]:
    """Formata os casos de uso de um script .sql para a sintaxe Textile do Redmine."""
    lines: List[str] = []
    casos = dados_sql.get("casos_de_uso") or dados_sql.get("use_cases") or []
    total_ics = dados_sql.get("total_ics", len(casos))
    if casos:
        sufixo_ics = f" ({total_ics} ICs)" if total_ics > 1 else (" (1 IC)" if total_ics == 1 else "")
        lines.append(f"** Casos de Uso Identificados{sufixo_ics}:")
        for caso in casos:
            lines.append(f"*** {caso}")
    return lines


def construir_descricao_ic_fluxo(
    short_hash: str,
    commit_date: Any,
    author: str,
    message: str,
    commit_url: str = "",
    files_changed: Optional[List[Any]] = None,
    xml_tags_metrics: Optional[Dict[str, Any]] = None,
    ic_count: int = 0,
) -> str:
    """Gera a descrição exclusiva de IC de Fluxo de Automação (XML) para o Redmine em formato Textile."""
    date_str = ""
    if commit_date:
        try:
            date_str = commit_date.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_str = str(commit_date)

    parsed_metrics = normalize_xml_metrics(xml_tags_metrics or {}, 0)
    xml_ics = ic_count or parsed_metrics.get("total_ics", 0)
    flows = parsed_metrics.get("flows") or {}

    lines = [
        f"Commit: {short_hash}",
        f"Data: {date_str}",
        f"Autor: {author}",
    ]
    if commit_url:
        lines.append(f"Link: {commit_url}")

    lines.append("")
    lines.append("Descrição:")
    lines.append(message.strip() if message else "")

    added_cnt = parsed_metrics.get("total_added", 0)
    removed_cnt = parsed_metrics.get("total_removed", 0)
    modified_cnt = parsed_metrics.get("total_modified", 0)
    if xml_ics > 0:
        parts: List[str] = []
        if added_cnt > 0:
            parts.append(f"+{added_cnt} adições")
        if removed_cnt > 0:
            parts.append(f"-{removed_cnt} remoções")
        if modified_cnt > 0:
            parts.append(f"~{modified_cnt} ajustes")
        summary_str = f" ({', '.join(parts)})" if parts else ""
        lines.append("")
        lines.append(f"Itens de Catálogo (IC) calculados: {xml_ics} IC(s){summary_str}")

    clean_files = files_changed or []
    xml_files_found = []
    matched_flow_paths = set()

    for f in clean_files:
        if isinstance(f, dict):
            raw_path = f.get("path") or f.get("filename") or ""
            path = decode_git_path(raw_path)
            ins = f.get("insertions", 0)
            dels = f.get("deletions", 0)
            diff_info = f" (+{ins} / -{dels})" if (ins or dels) else ""
            is_xml = f.get("is_xml") or path.lower().endswith(".xml")
        else:
            path = decode_git_path(str(f))
            diff_info = ""
            is_xml = path.lower().endswith(".xml")

        if is_xml:
            xml_files_found.append((path, diff_info))

    if xml_files_found:
        lines.append("")
        lines.append("Arquivos Alterados (Fluxos XML):")
        for path, diff_info in xml_files_found:
            lines.append(f"* [XML] {path}{diff_info}")
            flow_data = find_flow_metrics_for_file(path, flows)
            if flow_data:
                matched_flow_paths.add(flow_data.get("path", path))
                lines.extend(format_flow_tags_lines(flow_data))

        # Fallback para fluxos com IC que não constam em clean_files
        for f_path, f_data in flows.items():
            if f_data.get("total_ics", 0) > 0 and f_path not in matched_flow_paths:
                flow_check = find_flow_metrics_for_file(f_path, {p: {} for p in matched_flow_paths})
                if not flow_check:
                    lines.append(f"* [XML] {f_path}")
                    lines.extend(format_flow_tags_lines(f_data))

        lines.append(f"(Total de arquivos XML alterados: {len(xml_files_found)})")
    elif flows:
        lines.append("")
        lines.append("Arquivos Alterados (Fluxos XML):")
        cnt = 0
        for f_path, f_data in flows.items():
            if f_data.get("total_ics", 0) > 0:
                cnt += 1
                lines.append(f"* [XML] {f_path}")
                lines.extend(format_flow_tags_lines(f_data))
        if cnt > 0:
            lines.append(f"(Total de arquivos XML alterados: {cnt})")
    elif xml_ics > 0 and (added_cnt > 0 or removed_cnt > 0):
        lines.append("")
        lines.append("Tags XML Alteradas:")
        added_tags = parsed_metrics.get("added", {})
        removed_tags = parsed_metrics.get("removed", {})
        if added_tags:
            lines.append(f"* Tags Adicionadas (+{added_cnt}):")
            for t, c in sorted(added_tags.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"** <{t}>: {c}")
        if removed_tags:
            lines.append(f"* Tags Removidas (-{removed_cnt}):")
            for t, c in sorted(removed_tags.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"** <{t}>: {c}")

    return "\n".join(lines)


def construir_descricao_ic_sql(
    short_hash: str,
    commit_date: Any,
    author: str,
    message: str,
    commit_url: str = "",
    files_changed: Optional[List[Any]] = None,
    sql_scripts_metrics: Optional[Dict[str, Any]] = None,
    ic_count: int = 0,
) -> str:
    """Gera a descrição exclusiva de IC de Banco de Dados (SQL) para o Redmine em formato Textile."""
    date_str = ""
    if commit_date:
        try:
            date_str = commit_date.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_str = str(commit_date)

    sql_metrics = sql_scripts_metrics or {}
    sql_ics = ic_count or sql_metrics.get("total_ics", 0)
    arquivos_sql = sql_metrics.get("arquivos") or {}

    lines = [
        f"Commit: {short_hash}",
        f"Data: {date_str}",
        f"Autor: {author}",
    ]
    if commit_url:
        lines.append(f"Link: {commit_url}")

    lines.append("")
    lines.append("Descrição:")
    lines.append(message.strip() if message else "")

    if sql_ics > 0:
        lines.append("")
        lines.append(f"Itens de Catálogo (IC) calculados: {sql_ics} IC(s) em scripts SQL")

    clean_files = files_changed or []
    sql_files_found = []
    matched_sql_paths = set()

    for f in clean_files:
        if isinstance(f, dict):
            raw_path = f.get("path") or f.get("filename") or ""
            path = decode_git_path(raw_path)
            ins = f.get("insertions", 0)
            dels = f.get("deletions", 0)
            diff_info = f" (+{ins} / -{dels})" if (ins or dels) else ""
            is_sql = f.get("is_sql") or path.lower().endswith(".sql")
        else:
            path = decode_git_path(str(f))
            diff_info = ""
            is_sql = path.lower().endswith(".sql")

        if is_sql:
            sql_files_found.append((path, diff_info))

    if sql_files_found:
        lines.append("")
        lines.append("Arquivos Alterados (Scripts SQL):")
        for path, diff_info in sql_files_found:
            lines.append(f"* [SQL] {path}{diff_info}")
            norm = path.replace("\\", "/").lower()
            file_sql_data = None
            for k, v in arquivos_sql.items():
                k_norm = k.replace("\\", "/").lower()
                if k_norm == norm or k_norm.split("/")[-1] == norm.split("/")[-1]:
                    file_sql_data = v
                    matched_sql_paths.add(k)
                    break
            if file_sql_data:
                lines.extend(formatar_linhas_casos_de_uso_sql(file_sql_data))

        # Fallback para arquivos SQL com casos de uso não listados
        for a_path, a_data in arquivos_sql.items():
            if a_path not in matched_sql_paths and a_data.get("total_ics", 0) > 0:
                lines.append(f"* [SQL] {a_path}")
                lines.extend(formatar_linhas_casos_de_uso_sql(a_data))

        lines.append(f"(Total de scripts SQL alterados: {len(sql_files_found)})")
    elif arquivos_sql:
        lines.append("")
        lines.append("Arquivos Alterados (Scripts SQL):")
        for a_path, a_data in arquivos_sql.items():
            if a_data.get("total_ics", 0) > 0:
                lines.append(f"* [SQL] {a_path}")
                lines.extend(formatar_linhas_casos_de_uso_sql(a_data))
        lines.append(f"(Total de scripts SQL alterados: {len(arquivos_sql)})")
    elif sql_metrics.get("casos_de_uso"):
        lines.append("")
        lines.append("Casos de Uso Identificados:")
        for caso in sql_metrics["casos_de_uso"]:
            lines.append(f"* {caso}")

    return "\n".join(lines)


class Commit(Base):
    """Stores Git commit information retrieved by Productivity Assistant."""

    __tablename__ = "commits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    commit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    files_changed: Mapped[Any] = mapped_column(JSON, nullable=True)  # List of changed file names/stats
    repo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    repo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    commit_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    xml_tags_metrics: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # Dict of {tag: count}
    sql_scripts_metrics: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # Dict of {arquivos, casos_de_uso, total_ics}
    ic_count_xml: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    ic_count_sql: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    ic_count: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    execution_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("execution_history.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    execution: Mapped[Optional["ExecutionHistory"]] = relationship("ExecutionHistory", back_populates="commits")

    def __repr__(self) -> str:
        return f"<Commit {self.hash[:7]} by {self.author} on {self.commit_date}>"

    @property
    def short_hash(self) -> str:
        return self.hash[:7] if self.hash else ""

    @property
    def web_commit_url(self) -> Optional[str]:
        """Return the web link for the commit (GitHub, GitLab, etc.)."""
        if self.commit_url:
            return self.commit_url
        if self.repo_path:
            try:
                from app.services.git_service import GitService
                derived = GitService.get_commit_url(self.repo_path, self.hash)
                if derived:
                    return derived
            except Exception:
                pass
        return None

    @property
    def files_count(self) -> int:
        if isinstance(self.files_changed, list):
            return len(self.files_changed)
        if isinstance(self.files_changed, dict):
            return len(self.files_changed.keys())
        return 0

    @property
    def files_changed_clean(self) -> List[Dict[str, Any]]:
        """Return files_changed with octal escapes decoded into proper UTF-8 accents."""
        cleaned = []
        if isinstance(self.files_changed, list):
            for f in self.files_changed:
                if isinstance(f, dict):
                    f_copy = dict(f)
                    raw_path = f.get("path") or f.get("filename") or ""
                    clean_path = decode_git_path(raw_path)
                    f_copy["path"] = clean_path
                    f_copy["filename"] = clean_path.split("/")[-1].split("\\")[-1]
                    f_copy["is_xml"] = f.get("is_xml") or clean_path.lower().endswith(".xml")
                    f_copy["is_sql"] = f.get("is_sql") or clean_path.lower().endswith(".sql")
                    cleaned.append(f_copy)
                else:
                    clean_path = decode_git_path(str(f))
                    cleaned.append({
                        "path": clean_path,
                        "filename": clean_path.split("/")[-1].split("\\")[-1],
                        "is_xml": clean_path.lower().endswith(".xml"),
                        "is_sql": clean_path.lower().endswith(".sql"),
                        "insertions": 0,
                        "deletions": 0,
                        "lines": 0,
                    })
        return cleaned

    @property
    def xml_files(self) -> List[Any]:
        """Return list of modified XML files with their diff metrics."""
        return [f for f in self.files_changed_clean if f.get("is_xml")]

    @property
    def xml_files_count(self) -> int:
        return len(self.xml_files)

    @property
    def xml_insertions(self) -> int:
        return sum(f.get("insertions", 0) for f in self.xml_files)

    @property
    def xml_deletions(self) -> int:
        return sum(f.get("deletions", 0) for f in self.xml_files)

    @property
    def xml_total_edits(self) -> int:
        return self.xml_insertions + self.xml_deletions

    @property
    def sql_files(self) -> List[Any]:
        """Return list of modified SQL files with their diff metrics."""
        return [f for f in self.files_changed_clean if f.get("is_sql")]

    @property
    def sql_files_count(self) -> int:
        return len(self.sql_files)

    @property
    def has_sql_changes(self) -> bool:
        return self.sql_files_count > 0 or (getattr(self, "ic_count_sql", 0) or 0) > 0

    @property
    def has_xml_changes(self) -> bool:
        return self.xml_files_count > 0 or (getattr(self, "ic_count_xml", 0) or 0) > 0

    @property
    def tem_ambos_ajustes(self) -> bool:
        """Indicates whether this commit touches both XML flows and SQL scripts."""
        return self.has_xml_changes and self.has_sql_changes

    @property
    def precisa_dois_redmines(self) -> bool:
        """Business rule: commit with both XML and SQL adjustments requires two separate Redmine issues."""
        return self.tem_ambos_ajustes

    @property
    def ic_metrics_parsed(self) -> Dict[str, Any]:
        return normalize_xml_metrics(getattr(self, "xml_tags_metrics", None), getattr(self, "ic_count_xml", 0) or getattr(self, "ic_count", 0) or 0)

    @property
    def ic_fluxo_count(self) -> int:
        if getattr(self, "ic_count_xml", 0):
            return self.ic_count_xml
        if self.ic_metrics_parsed.get("total_ics", 0) > 0:
            return self.ic_metrics_parsed["total_ics"]
        return 1 if self.xml_files_count > 0 else 0

    @property
    def ic_sql_count(self) -> int:
        if getattr(self, "ic_count_sql", 0):
            return self.ic_count_sql
        if (getattr(self, "sql_scripts_metrics", None) or {}).get("total_ics", 0) > 0:
            return (getattr(self, "sql_scripts_metrics", None) or {}).get("total_ics", 0)
        return 1 if self.sql_files_count > 0 else 0

    @property
    def ic_added_count(self) -> int:
        return self.ic_metrics_parsed["total_added"]

    @property
    def ic_removed_count(self) -> int:
        return self.ic_metrics_parsed["total_removed"]

    @property
    def ic_title(self) -> str:
        first_line = (self.message or "").strip().split("\n")[0].strip() if self.message else "Atividade de Desenvolvimento"
        return first_line[:180]

    @property
    def ic_description(self) -> str:
        return build_ic_description(
            short_hash=self.short_hash,
            commit_date=self.commit_date,
            author=self.author,
            message=self.message,
            commit_url=self.web_commit_url or self.commit_url or "",
            files_changed=self.files_changed_clean,
            xml_tags_metrics=self.xml_tags_metrics,
            ic_count=getattr(self, "ic_count", 0) or 0,
        )

    @property
    def ic_description_fluxo(self) -> str:
        return construir_descricao_ic_fluxo(
            short_hash=self.short_hash,
            commit_date=self.commit_date,
            author=self.author,
            message=self.message,
            commit_url=self.web_commit_url or self.commit_url or "",
            files_changed=self.files_changed_clean,
            xml_tags_metrics=self.xml_tags_metrics,
            ic_count=self.ic_fluxo_count,
        )

    @property
    def ic_description_sql(self) -> str:
        return construir_descricao_ic_sql(
            short_hash=self.short_hash,
            commit_date=self.commit_date,
            author=self.author,
            message=self.message,
            commit_url=self.web_commit_url or self.commit_url or "",
            files_changed=self.files_changed_clean,
            sql_scripts_metrics=self.sql_scripts_metrics,
            ic_count=self.ic_sql_count,
        )

    def to_dict(self) -> Dict[str, Any]:
        parsed_metrics = self.ic_metrics_parsed
        return {
            "id": self.id,
            "hash": self.hash,
            "short_hash": self.short_hash,
            "author": self.author,
            "commit_date": self.commit_date.strftime("%d/%m/%Y %H:%M") if self.commit_date else "",
            "message": self.message,
            "repo_name": self.repo_name or "",
            "branch": getattr(self, "branch", "") or "",
            "repo_path": self.repo_path or "",
            "commit_url": self.web_commit_url or self.commit_url or "",
            "files_changed": self.files_changed_clean,
            "files_count": self.files_count,
            "xml_files_count": self.xml_files_count,
            "xml_insertions": self.xml_insertions,
            "xml_deletions": self.xml_deletions,
            "sql_files_count": self.sql_files_count,
            "has_xml_changes": self.has_xml_changes,
            "has_sql_changes": self.has_sql_changes,
            "tem_ambos_ajustes": self.tem_ambos_ajustes,
            "precisa_dois_redmines": self.precisa_dois_redmines,
            "xml_tags_metrics": parsed_metrics,
            "sql_scripts_metrics": getattr(self, "sql_scripts_metrics", {}) or {},
            "ic_count": getattr(self, "ic_count", 0) or (self.ic_fluxo_count + self.ic_sql_count),
            "ic_count_xml": self.ic_fluxo_count,
            "ic_count_sql": self.ic_sql_count,
            "ic_added_count": self.ic_added_count,
            "ic_removed_count": self.ic_removed_count,
            "ic_title": self.ic_title,
            "ic_description": self.ic_description,
            "ic_description_fluxo": self.ic_description_fluxo,
            "is_saved": getattr(self, "is_saved", False),
            "is_saved_fluxo": getattr(self, "is_saved_fluxo", False),
            "is_saved_sql": getattr(self, "is_saved_sql", False),
            "redmine_id": getattr(self, "redmine_id", None),
            "redmine_id_fluxo": getattr(self, "redmine_id_fluxo", None),
            "redmine_id_sql": getattr(self, "redmine_id_sql", None),
        }


class CommitItem:
    """In-memory representation of a git commit with XML and web url helpers."""

    def __init__(self, data: Dict[str, Any]):
        self.id = None
        self.hash = data.get("hash", "")
        self.author = data.get("author", "")
        self.author_name = data.get("author_name", "")
        self.author_email = data.get("author_email", "")
        self.commit_date = data.get("commit_date")
        self.message = data.get("message", "")
        self.files_changed = data.get("files_changed", [])
        self.repo_name = data.get("repo_name", "")
        self.branch = data.get("branch", "")
        self.repo_path = data.get("repo_path", "")
        self.commit_url = data.get("commit_url", "")
        self.xml_tags_metrics = data.get("xml_tags_metrics") or {}
        self.sql_scripts_metrics = data.get("sql_scripts_metrics") or {}

        # Contadores individuais separados por natureza de IC
        xml_total = self.xml_tags_metrics.get("total_ics", 0) if isinstance(self.xml_tags_metrics, dict) else 0
        sql_total = self.sql_scripts_metrics.get("total_ics", 0) if isinstance(self.sql_scripts_metrics, dict) else 0
        self.ic_count_xml = data.get("ic_count_xml") if (data.get("ic_count_xml") is not None and data.get("ic_count_xml") > 0) else xml_total
        self.ic_count_sql = data.get("ic_count_sql") if (data.get("ic_count_sql") is not None and data.get("ic_count_sql") > 0) else sql_total
        if self.ic_count_xml == 0 and self.xml_files_count > 0:
            self.ic_count_xml = 1
        if self.ic_count_sql == 0 and self.sql_files_count > 0:
            self.ic_count_sql = 1
        self.ic_count = data.get("ic_count") or (self.ic_count_xml + self.ic_count_sql)
        self.is_saved = data.get("is_saved", False)

    @property
    def short_hash(self) -> str:
        return self.hash[:7] if self.hash else ""

    @property
    def web_commit_url(self) -> Optional[str]:
        return self.commit_url or None

    @property
    def files_count(self) -> int:
        return len(self.files_changed) if isinstance(self.files_changed, list) else 0

    @property
    def files_changed_clean(self) -> List[Dict[str, Any]]:
        """Return files_changed with octal escapes decoded into proper UTF-8 accents."""
        cleaned = []
        if isinstance(self.files_changed, list):
            for f in self.files_changed:
                if isinstance(f, dict):
                    f_copy = dict(f)
                    raw_path = f.get("path") or f.get("filename") or ""
                    clean_path = decode_git_path(raw_path)
                    f_copy["path"] = clean_path
                    f_copy["filename"] = clean_path.split("/")[-1].split("\\")[-1]
                    f_copy["is_xml"] = f.get("is_xml") or clean_path.lower().endswith(".xml")
                    f_copy["is_sql"] = f.get("is_sql") or clean_path.lower().endswith(".sql")
                    cleaned.append(f_copy)
                else:
                    clean_path = decode_git_path(str(f))
                    cleaned.append({
                        "path": clean_path,
                        "filename": clean_path.split("/")[-1].split("\\")[-1],
                        "is_xml": clean_path.lower().endswith(".xml"),
                        "is_sql": clean_path.lower().endswith(".sql"),
                        "insertions": 0,
                        "deletions": 0,
                        "lines": 0,
                    })
        return cleaned

    @property
    def xml_files(self) -> List[Any]:
        """Return list of modified XML files with their diff metrics."""
        return [f for f in self.files_changed_clean if f.get("is_xml")]

    @property
    def xml_files_count(self) -> int:
        return len(self.xml_files)

    @property
    def xml_insertions(self) -> int:
        return sum(f.get("insertions", 0) for f in self.xml_files)

    @property
    def xml_deletions(self) -> int:
        return sum(f.get("deletions", 0) for f in self.xml_files)

    @property
    def xml_total_edits(self) -> int:
        return self.xml_insertions + self.xml_deletions

    @property
    def sql_files(self) -> List[Any]:
        """Return list of modified SQL files with their diff metrics."""
        return [f for f in self.files_changed_clean if f.get("is_sql")]

    @property
    def sql_files_count(self) -> int:
        return len(self.sql_files)

    @property
    def has_sql_changes(self) -> bool:
        return self.sql_files_count > 0 or (getattr(self, "ic_count_sql", 0) or 0) > 0

    @property
    def has_xml_changes(self) -> bool:
        return self.xml_files_count > 0 or (getattr(self, "ic_count_xml", 0) or 0) > 0

    @property
    def tem_ambos_ajustes(self) -> bool:
        """Indicates whether this commit touches both XML flows and SQL scripts."""
        return self.has_xml_changes and self.has_sql_changes

    @property
    def precisa_dois_redmines(self) -> bool:
        """Business rule: commit with both XML and SQL adjustments requires two separate Redmine issues."""
        return self.tem_ambos_ajustes

    @property
    def ic_metrics_parsed(self) -> Dict[str, Any]:
        return normalize_xml_metrics(self.xml_tags_metrics, self.ic_count_xml or 0)

    @property
    def ic_fluxo_count(self) -> int:
        if self.ic_count_xml is not None and self.ic_count_xml > 0:
            return self.ic_count_xml
        if self.ic_metrics_parsed.get("total_ics", 0) > 0:
            return self.ic_metrics_parsed["total_ics"]
        return 1 if self.xml_files_count > 0 else 0

    @property
    def ic_sql_count(self) -> int:
        if self.ic_count_sql is not None and self.ic_count_sql > 0:
            return self.ic_count_sql
        if (self.sql_scripts_metrics or {}).get("total_ics", 0) > 0:
            return (self.sql_scripts_metrics or {}).get("total_ics", 0)
        return 1 if self.sql_files_count > 0 else 0

    @property
    def ic_added_count(self) -> int:
        return self.ic_metrics_parsed["total_added"]

    @property
    def ic_removed_count(self) -> int:
        return self.ic_metrics_parsed["total_removed"]

    @property
    def ic_title(self) -> str:
        first_line = (self.message or "").strip().split("\n")[0].strip() if self.message else "Atividade de Desenvolvimento"
        return first_line[:180]

    @property
    def ic_description(self) -> str:
        return build_ic_description(
            short_hash=self.short_hash,
            commit_date=self.commit_date,
            author=self.author,
            message=self.message,
            commit_url=self.web_commit_url or self.commit_url or "",
            files_changed=self.files_changed_clean,
            xml_tags_metrics=self.xml_tags_metrics,
            ic_count=self.ic_count or 0,
        )

    @property
    def ic_description_fluxo(self) -> str:
        return construir_descricao_ic_fluxo(
            short_hash=self.short_hash,
            commit_date=self.commit_date,
            author=self.author,
            message=self.message,
            commit_url=self.web_commit_url or self.commit_url or "",
            files_changed=self.files_changed_clean,
            xml_tags_metrics=self.xml_tags_metrics,
            ic_count=self.ic_fluxo_count,
        )

    @property
    def ic_description_sql(self) -> str:
        return construir_descricao_ic_sql(
            short_hash=self.short_hash,
            commit_date=self.commit_date,
            author=self.author,
            message=self.message,
            commit_url=self.web_commit_url or self.commit_url or "",
            files_changed=self.files_changed_clean,
            sql_scripts_metrics=self.sql_scripts_metrics,
            ic_count=self.ic_sql_count,
        )

    def to_dict(self) -> Dict[str, Any]:
        date_str = ""
        if self.commit_date:
            try:
                date_str = self.commit_date.strftime("%d/%m/%Y %H:%M")
            except Exception:
                date_str = str(self.commit_date)
        parsed_metrics = self.ic_metrics_parsed
        return {
            "id": self.id,
            "hash": self.hash,
            "short_hash": self.short_hash,
            "author": self.author,
            "commit_date": date_str,
            "message": self.message,
            "repo_name": self.repo_name or "",
            "branch": getattr(self, "branch", "") or "",
            "repo_path": self.repo_path or "",
            "commit_url": self.web_commit_url or self.commit_url or "",
            "files_changed": self.files_changed_clean,
            "files_count": self.files_count,
            "xml_files_count": self.xml_files_count,
            "xml_insertions": self.xml_insertions,
            "xml_deletions": self.xml_deletions,
            "sql_files_count": self.sql_files_count,
            "has_xml_changes": self.has_xml_changes,
            "has_sql_changes": self.has_sql_changes,
            "tem_ambos_ajustes": self.tem_ambos_ajustes,
            "precisa_dois_redmines": self.precisa_dois_redmines,
            "xml_tags_metrics": parsed_metrics,
            "sql_scripts_metrics": self.sql_scripts_metrics,
            "ic_count": self.ic_count or (self.ic_fluxo_count + self.ic_sql_count),
            "ic_count_xml": self.ic_fluxo_count,
            "ic_count_sql": self.ic_sql_count,
            "ic_added_count": self.ic_added_count,
            "ic_removed_count": self.ic_removed_count,
            "ic_title": self.ic_title,
            "ic_description": self.ic_description,
            "ic_description_fluxo": self.ic_description_fluxo,
            "ic_description_sql": self.ic_description_sql,
            "is_saved": getattr(self, "is_saved", False),
            "is_saved_fluxo": getattr(self, "is_saved_fluxo", False),
            "is_saved_sql": getattr(self, "is_saved_sql", False),
            "redmine_id": getattr(self, "redmine_id", None),
            "redmine_id_fluxo": getattr(self, "redmine_id_fluxo", None),
            "redmine_id_sql": getattr(self, "redmine_id_sql", None),
        }

