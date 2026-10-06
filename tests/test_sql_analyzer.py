import pytest
from app.services.sql_analyzer_service import SqlAnalyzerService


def test_insert_into_table():
    diff = """
diff --git a/scripts/update.sql b/scripts/update.sql
--- a/scripts/update.sql
+++ b/scripts/update.sql
@@ -1,3 +1,5 @@
+INSERT INTO tb_processo_documento (id, cd_tipo) VALUES (1, 'PETICAO');
+INSERT INTO tb_processo_documento (id, cd_tipo) VALUES (2, 'CERTIDAO');
"""
    result = SqlAnalyzerService.parse_sql_diff(diff)
    assert result["total_ics"] == 1
    assert result["use_cases"] == ["criar a entidade tb_processo_documento"]
    assert result["operations_count"]["criar"] == 1
    assert "tb_processo_documento" in result["tables"]


def test_update_tb_parametro_with_nm_parametro():
    diff = """
@@ -10,3 +10,4 @@
+UPDATE tb_parametro SET vl_parametro = 'TRUE' WHERE nm_parametro = 'PJE_HABILITA_REQUISICAO';
"""
    result = SqlAnalyzerService.parse_sql_diff(diff)
    assert result["total_ics"] == 1
    assert result["use_cases"] == ["alterar o parâmetro 'PJE_HABILITA_REQUISICAO'"]
    assert result["operations_count"]["alterar"] == 1


def test_update_tb_parametro_fallback_token():
    diff = """
+UPDATE tb_parametro SET vl_parametro = '100' WHERE cd_chave = 'MAX_FILE_SIZE_MB';
"""
    result = SqlAnalyzerService.parse_sql_diff(diff)
    assert result["total_ics"] == 1
    assert result["use_cases"] == ["alterar o parâmetro 'MAX_FILE_SIZE_MB'"]


def test_insert_tb_parametro():
    diff = """
+INSERT INTO tb_parametro (nm_parametro, vl_parametro) VALUES ('PJE_NOVO_PARAM', 'VAL');
"""
    result = SqlAnalyzerService.parse_sql_diff(diff)
    assert result["total_ics"] == 1
    assert result["use_cases"] == ["criar o parâmetro 'PJE_NOVO_PARAM'"]
    assert result["operations_count"]["criar"] == 1


def test_delete_and_select_operations():
    diff = """
+DELETE FROM tb_sessao_julgamento WHERE id = 99;
+SELECT id, ds_nome FROM tb_usuario WHERE fl_ativo = 1;
"""
    result = SqlAnalyzerService.parse_sql_diff(diff)
    assert result["total_ics"] == 2
    assert "excluir a entidade tb_sessao_julgamento" in result["use_cases"]
    assert "consultar a entidade tb_usuario" in result["use_cases"]
    assert result["operations_count"]["excluir"] == 1
    assert result["operations_count"]["consultar"] == 1


def test_schema_qualified_table_name():
    diff = """
+INSERT INTO pje.tb_parametro (id, vl_parametro) VALUES (1, 'TESTE') WHERE nm_parametro = 'PJE_MODO_ESTRITO';
+UPDATE public.tb_configuracao SET fl_ativo = 1;
"""
    result = SqlAnalyzerService.parse_sql_diff(diff)
    assert result["total_ics"] == 2
    assert "criar o parâmetro 'PJE_MODO_ESTRITO'" in result["use_cases"]
    assert "alterar a entidade public.tb_configuracao" in result["use_cases"]


def test_sql_comments_are_ignored():
    diff = """
+-- INSERT INTO tb_fake_table (id) VALUES (1);
+/* comentário multilinha */
+INSERT INTO tb_auditoria (data_hora) VALUES (NOW());
"""
    result = SqlAnalyzerService.parse_sql_diff(diff)
    assert result["total_ics"] == 1
    assert result["use_cases"] == ["criar a entidade tb_auditoria"]


def test_empty_or_whitespace_diff():
    result = SqlAnalyzerService.parse_sql_diff("")
    assert result["total_ics"] == 0
    assert result["use_cases"] == []

    result_none = SqlAnalyzerService.parse_sql_diff("   \n\n  ")
    assert result_none["total_ics"] == 0
    assert result_none["use_cases"] == []


def test_format_use_cases_summary():
    use_cases = [
        "alterar o parâmetro 'PJE_HABILITA_REQUISICAO'",
        "criar a entidade tb_processo",
    ]
    formatted = SqlAnalyzerService.format_use_cases_summary(use_cases)
    assert "Casos de Uso Identificados:" in formatted
    assert "- alterar o parâmetro 'PJE_HABILITA_REQUISICAO'" in formatted
    assert "- criar a entidade tb_processo" in formatted

    empty_formatted = SqlAnalyzerService.format_use_cases_summary([])
    assert "Nenhum caso de uso SQL mapeado" in empty_formatted
