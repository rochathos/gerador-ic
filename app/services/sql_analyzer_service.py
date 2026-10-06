import re
from typing import List, Dict, Any, Optional, Tuple
from app.core.logger import logger


class SqlAnalyzerService:
    """Service to parse SQL script diffs and extract use cases (ICs) for database changes.
    
    Ported and adapted from the Java DiffProcessor rules:
    - Identifies INSERT (criar), UPDATE (alterar), DELETE (excluir), SELECT (consultar).
    - Special rule for 'tb_parametro' extracting the specific parameter name.
    - Deduplicates use cases so each unique operation on an entity/parameter counts as 1 IC.
    """

    INSERT_PATTERN = re.compile(r"insert\s+into\s+([a-zA-Z0-9_.]+)", re.IGNORECASE)
    UPDATE_PATTERN = re.compile(r"update\s+([a-zA-Z0-9_.]+)", re.IGNORECASE)
    DELETE_PATTERN = re.compile(r"delete\s+from\s+([a-zA-Z0-9_.]+)", re.IGNORECASE)
    SELECT_PATTERN = re.compile(r"select\s+(?:.*?\s+from\s+)?([a-zA-Z0-9_.]+)", re.IGNORECASE | re.DOTALL)

    TB_PARAMETRO_NM_PATTERN = re.compile(
        r"\b(?:nm_parametro|cd_parametro|cd_chave|nm_variavel)\s*=\s*'([^']*)'",
        re.IGNORECASE,
    )
    WHERE_PARAM_PATTERN = re.compile(r"\bwhere\s+.*?'([A-Za-z0-9_]+)'", re.IGNORECASE)
    FALLBACK_PARAM_PATTERN = re.compile(r"'([A-Za-z0-9_]+)'")
    STRING_LITERAL_PATTERN = re.compile(r"'([^']+)'")

    @classmethod
    def remover_comentarios_sql(cls, sql_text: str) -> str:
        """Remove comentários de linha única do SQL (-- ...) preservando o restante."""
        cleaned_lines = []
        for line in sql_text.splitlines():
            comment_idx = line.find("--")
            if comment_idx != -1:
                prefix = line[:comment_idx]
                if prefix.count("'") % 2 == 0:
                    line = prefix
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    # Alias em inglês
    strip_sql_comments = remover_comentarios_sql

    @classmethod
    def gerar_caso_de_uso(cls, table: str, operation: str, stmt: str) -> str:
        """Gera o texto descritivo do caso de uso para a operação na tabela.
        
        Se a tabela for 'tb_parametro', tenta extrair o nome do parâmetro:
          '<operacao> o parâmetro \'<parametro>\''
        Caso contrário:
          '<operacao> a entidade <table>'
        """
        table_clean = table.strip().lower()
        table_name = table_clean.split(".")[-1]

        if table_name == "tb_parametro":
            parametro: Optional[str] = None
            m_nm = cls.TB_PARAMETRO_NM_PATTERN.search(stmt)
            if m_nm:
                parametro = m_nm.group(1).strip()
            else:
                m_where = cls.WHERE_PARAM_PATTERN.search(stmt)
                if m_where:
                    parametro = m_where.group(1).strip()
                else:
                    m_fallback = cls.FALLBACK_PARAM_PATTERN.search(stmt)
                    if m_fallback:
                        parametro = m_fallback.group(1).strip()
                    else:
                        m_str = cls.STRING_LITERAL_PATTERN.search(stmt)
                        if m_str:
                            parametro = m_str.group(1).strip()

            if parametro:
                return f"{operation} o parâmetro '{parametro}'"
            return f"{operation} a entidade tb_parametro"

        return f"{operation} a entidade {table_clean}"

    # Alias em inglês
    generate_use_case = gerar_caso_de_uso

    @classmethod
    def processar_diff_sql(cls, diff_text: str) -> Dict[str, Any]:
        """Analisa o texto de diff de arquivos .sql e extrai casos de uso únicos (ICs).
        
        Retorna dicionário com:
            - casos_de_uso (e use_cases): Lista de casos de uso sem duplicidades
            - total_ics: Quantidade total de ICs calculados
            - operacoes (e operations_count): Contagem por tipo de operação
            - tabelas (e tables): Tabelas identificadas no diff
        """
        if not diff_text or not diff_text.strip():
            return {
                "casos_de_uso": [],
                "use_cases": [],
                "total_ics": 0,
                "operacoes": {"criar": 0, "alterar": 0, "excluir": 0, "consultar": 0},
                "operations_count": {"criar": 0, "alterar": 0, "excluir": 0, "consultar": 0},
                "tabelas": [],
                "tables": [],
            }

        lines = diff_text.splitlines()
        sql_parts: List[str] = []

        for line in lines:
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                continue
            if line.startswith("+") or line.startswith(" "):
                sql_parts.append(line[1:])

        sql_full_text = "\n".join(sql_parts)
        sql_clean = cls.remover_comentarios_sql(sql_full_text)

        statements = [s.strip() for s in sql_clean.split(";") if s.strip()]

        casos_de_uso: List[str] = []
        seen: Set[str] = set()
        operations_count: Dict[str, int] = {"criar": 0, "alterar": 0, "excluir": 0, "consultar": 0}
        tables_touched: List[str] = []

        for stmt in statements:
            m_insert = cls.INSERT_PATTERN.search(stmt)
            m_update = cls.UPDATE_PATTERN.search(stmt)
            m_delete = cls.DELETE_PATTERN.search(stmt)
            m_select = cls.SELECT_PATTERN.search(stmt)

            table: Optional[str] = None
            operation: Optional[str] = None

            if m_insert:
                table = m_insert.group(1)
                operation = "criar"
            elif m_update:
                table = m_update.group(1)
                operation = "alterar"
            elif m_delete:
                table = m_delete.group(1)
                operation = "excluir"
            elif m_select:
                table = m_select.group(1)
                operation = "consultar"

            if table and operation:
                table_clean = table.strip().lower()
                if table_clean not in tables_touched:
                    tables_touched.append(table_clean)

                caso = cls.gerar_caso_de_uso(table=table_clean, operation=operation, stmt=stmt)
                if caso not in seen:
                    seen.add(caso)
                    casos_de_uso.append(caso)
                    operations_count[operation] = operations_count.get(operation, 0) + 1

        logger.debug(f"[SqlAnalyzerService] Encontrados {len(casos_de_uso)} casos de uso SQL únicos.")

        return {
            "casos_de_uso": casos_de_uso,
            "use_cases": casos_de_uso,
            "total_ics": len(casos_de_uso),
            "operacoes": operations_count,
            "operations_count": operations_count,
            "tabelas": tables_touched,
            "tables": tables_touched,
        }

    # Alias em inglês
    parse_sql_diff = processar_diff_sql

    @classmethod
    def formatar_resumo_casos_de_uso(cls, use_cases: List[str]) -> str:
        """Formata a lista de casos de uso em texto amigável para exibição."""
        if not use_cases:
            return "  (Nenhum caso de uso SQL mapeado)"
        lines = ["  Casos de Uso Identificados:"]
        for uc in use_cases:
            lines.append(f"    - {uc}")
        return "\n".join(lines)

    # Alias em inglês
    format_use_cases_summary = formatar_resumo_casos_de_uso

