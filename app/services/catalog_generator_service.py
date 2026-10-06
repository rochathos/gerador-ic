from typing import List, Dict, Any, Optional
from app.core.logger import logger
from app.models.commit import (
    normalize_xml_metrics,
    format_ic_details,
    decode_git_path,
    build_ic_description,
    construir_descricao_ic_fluxo,
    construir_descricao_ic_sql,
)


class CatalogGeneratorService:
    """Gera propostas de Itens de Catálogo (ICs) para envio ao Redmine.
    
    Regra de negócio:
    - Alterações apenas em .xml: 1 Redmine de catálogo de funcionalidade ("Desenvolvimento - Criar/Manter tarefa de automação")
    - Alterações apenas em .sql: 1 Redmine de banco de dados ("Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados")
    - Alterações em .xml E .sql: 2 Redmines independentes vinculados ao mesmo commit analisado:
      1. Principal: Catálogo de funcionalidade (Fluxo XML)
      2. Segundo: Banco de dados (Scripts SQL)
    """

    ATIVIDADE_FLUXO_XML = "Desenvolvimento - Criar/Manter tarefa de automação"
    ATIVIDADE_BANCO_SQL = "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados"

    @classmethod
    def gerar_proposta_ic_fluxo(cls, commit: Any) -> Dict[str, Any]:
        """Gera a proposta de IC específica para ajustes em Fluxo de Automação (XML)."""
        if isinstance(commit, dict):
            msg = commit.get("message", "").strip()
            commit_hash = commit.get("hash", "")
            short_hash = commit_hash[:7] if commit_hash else ""
            author = commit.get("author", "")
            commit_date = commit.get("commit_date")
            commit_url = commit.get("commit_url") or ""
            files_changed = commit.get("files_changed") or []
            raw_xml_tags = commit.get("xml_tags_metrics") or {}
            ic_count_xml = commit.get("ic_count_xml", 0) or 0
        else:
            msg = commit.message.strip()
            commit_hash = commit.hash
            short_hash = commit.short_hash
            author = commit.author
            commit_date = commit.commit_date
            commit_url = commit.web_commit_url or commit.commit_url or ""
            files_changed = commit.files_changed or []
            raw_xml_tags = getattr(commit, "xml_tags_metrics", {}) or {}
            ic_count_xml = getattr(commit, "ic_count_xml", 0) or getattr(commit, "ic_fluxo_count", 0) or 0

        parsed_metrics = normalize_xml_metrics(raw_xml_tags, ic_count_xml)
        total_ics = ic_count_xml or parsed_metrics.get("total_ics", 0)
        first_line = msg.split("\n")[0].strip() if msg else "Atividade de Desenvolvimento"
        title = first_line[:180]

        description = construir_descricao_ic_fluxo(
            short_hash=short_hash,
            commit_date=commit_date,
            author=author,
            message=msg,
            commit_url=commit_url,
            files_changed=files_changed,
            xml_tags_metrics=raw_xml_tags,
            ic_count=total_ics,
        )

        return {
            "title": title,
            "description": description,
            "natureza": "fluxo",
            "activity_type": cls.ATIVIDADE_FLUXO_XML,
            "status": "sugerido",
            "commit_hash": commit_hash,
            "commit_url": commit_url,
            "ic_count": total_ics or 1,
            "xml_tags_metrics": parsed_metrics,
        }

    @classmethod
    def gerar_proposta_ic_sql(cls, commit: Any) -> Dict[str, Any]:
        """Gera a proposta de IC específica para ajustes em Banco de Dados / Scripts SQL."""
        if isinstance(commit, dict):
            msg = commit.get("message", "").strip()
            commit_hash = commit.get("hash", "")
            short_hash = commit_hash[:7] if commit_hash else ""
            author = commit.get("author", "")
            commit_date = commit.get("commit_date")
            commit_url = commit.get("commit_url") or ""
            files_changed = commit.get("files_changed") or []
            raw_sql_tags = commit.get("sql_scripts_metrics") or {}
            ic_count_sql = commit.get("ic_count_sql", 0) or 0
        else:
            msg = commit.message.strip()
            commit_hash = commit.hash
            short_hash = commit.short_hash
            author = commit.author
            commit_date = commit.commit_date
            commit_url = commit.web_commit_url or commit.commit_url or ""
            files_changed = commit.files_changed or []
            raw_sql_tags = getattr(commit, "sql_scripts_metrics", {}) or {}
            ic_count_sql = getattr(commit, "ic_count_sql", 0) or getattr(commit, "ic_sql_count", 0) or 0

        total_ics = ic_count_sql or raw_sql_tags.get("total_ics", 0)
        first_line = msg.split("\n")[0].strip() if msg else "Atividade de Desenvolvimento"
        title = first_line[:180]

        description = construir_descricao_ic_sql(
            short_hash=short_hash,
            commit_date=commit_date,
            author=author,
            message=msg,
            commit_url=commit_url,
            files_changed=files_changed,
            sql_scripts_metrics=raw_sql_tags,
            ic_count=total_ics,
        )

        return {
            "title": title,
            "description": description,
            "natureza": "sql",
            "activity_type": cls.ATIVIDADE_BANCO_SQL,
            "status": "sugerido",
            "commit_hash": commit_hash,
            "commit_url": commit_url,
            "ic_count": total_ics or 1,
            "sql_scripts_metrics": raw_sql_tags,
        }

    @classmethod
    def gerar_propostas_para_commit(cls, commit: Any) -> List[Dict[str, Any]]:
        """Gera as propostas de IC para um commit aplicando a regra de negócio completa:
        - Apenas XML -> 1 proposta (Fluxo)
        - Apenas SQL -> 1 proposta (Banco)
        - Ambos XML e SQL -> 2 propostas (Principal: Fluxo, Segunda: Banco)
        """
        if isinstance(commit, dict):
            files_changed = commit.get("files_changed") or []
            xml_ics = commit.get("ic_count_xml", 0) or 0
            sql_ics = commit.get("ic_count_sql", 0) or 0
            has_xml = xml_ics > 0 or any(f.get("is_xml") for f in files_changed if isinstance(f, dict))
            has_sql = sql_ics > 0 or any(f.get("is_sql") for f in files_changed if isinstance(f, dict))
        else:
            has_xml = getattr(commit, "has_xml_changes", False) or (getattr(commit, "ic_fluxo_count", 0) > 0)
            has_sql = getattr(commit, "has_sql_changes", False) or (getattr(commit, "ic_sql_count", 0) > 0)

        propostas: List[Dict[str, Any]] = []

        if has_xml and has_sql:
            # Commit misto: gera o principal (Fluxo) e o segundo (Banco)
            propostas.append(cls.gerar_proposta_ic_fluxo(commit))
            propostas.append(cls.gerar_proposta_ic_sql(commit))
        elif has_sql and not has_xml:
            propostas.append(cls.gerar_proposta_ic_sql(commit))
        else:
            # Padrão ou apenas XML
            propostas.append(cls.gerar_proposta_ic_fluxo(commit))

        return propostas

    @classmethod
    def generate_ic_for_commit(cls, commit: Any, tipo: str = "auto") -> Dict[str, Any]:
        """Gera proposta de IC com base na natureza desejada ('auto', 'fluxo'/'xml', 'sql'/'banco')."""
        if tipo in ("fluxo", "xml"):
            return cls.gerar_proposta_ic_fluxo(commit)
        if tipo in ("sql", "banco"):
            return cls.gerar_proposta_ic_sql(commit)

        propostas = cls.gerar_propostas_para_commit(commit)
        return propostas[0] if propostas else cls.gerar_proposta_ic_fluxo(commit)
