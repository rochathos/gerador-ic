from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.models.commit import Commit
from app.models.execution_history import ExecutionHistory
from app.services.git_service import GitService


@pytest.fixture(scope="module")
def setup_database():
    """Ensure database tables exist."""
    init_db()
    yield


@pytest.fixture
def db_session(setup_database):
    """Provide a clean session per test."""
    session = SessionLocal()
    yield session
    session.close()


def test_validate_repository_valid():
    """Test validation of an existing valid git repository."""
    is_valid, msg = GitService.validate_repository(settings.BASE_DIR)
    assert is_valid is True
    assert "Repositório válido" in msg


def test_validate_repository_invalid():
    """Test validation of an invalid path."""
    is_valid, msg = GitService.validate_repository("D:/caminho/inexistente/123")
    assert is_valid is False


def test_get_commits_period():
    """Test extracting commits within a specific period."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=7)
    end_date = now + timedelta(days=1)

    commits = GitService.get_commits(
        repo_path=settings.BASE_DIR,
        start_date=start_date,
        end_date=end_date,
        author=settings.GIT_AUTHOR_NAME or None,
    )

    assert len(commits) > 0
    first = commits[0]
    assert "hash" in first
    assert "author" in first
    assert "commit_date" in first
    assert "message" in first
    assert "files_changed" in first
    assert len(first["hash"]) == 40


def test_xml_files_metrics():
    """Test detection and counting of XML file edits and line modifications via get_commits."""
    from app.models.commit import CommitItem

    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=7)
    end_date = now + timedelta(days=1)

    raw_commits = GitService.get_commits(
        repo_path=settings.BASE_DIR,
        start_date=start_date,
        end_date=end_date,
        author=settings.GIT_AUTHOR_NAME or None,
        analyze_xml=True,
    )

    commits = [CommitItem(c) for c in raw_commits]
    xml_commits = [c for c in commits if c.has_xml_changes]
    assert len(xml_commits) >= 2

    # Check that XML metrics are properly extracted
    latest_xml = xml_commits[-1]
    assert latest_xml.xml_files_count >= 1
    assert latest_xml.xml_insertions > 0
    assert latest_xml.xml_total_edits > 0
    assert any("database-changelog.xml" in f["filename"] for f in latest_xml.xml_files)


def test_xml_tags_ic_counting():
    """Test XML tag counting rules: IC tags include nodes, transitions, condition, task, action, swimlane, variable."""
    assert "process-definition" in GitService.EXCLUDED_XML_TAGS
    assert "start-state" in GitService.EXCLUDED_XML_TAGS
    assert "end-state" in GitService.EXCLUDED_XML_TAGS
    assert "assignment" in GitService.EXCLUDED_XML_TAGS
    assert "controller" in GitService.EXCLUDED_XML_TAGS
    assert "script" in GitService.EXCLUDED_XML_TAGS
    assert "event" in GitService.EXCLUDED_XML_TAGS

    # Must NOT be in excluded: transition, condition, task, action, swimlane, variable
    for tag in ("transition", "condition", "task", "action", "swimlane", "variable"):
        assert tag not in GitService.EXCLUDED_XML_TAGS
        assert tag in GitService.IC_NODE_TAGS

    # Test regex tag parsing for additions (+)
    line1 = '+   <transition to="fim" name="concluir"/>'
    m1 = GitService.TAG_REGEX.search(line1)
    assert m1 is not None
    tag1 = m1.group(1).lower()
    assert tag1 == "transition"
    assert tag1 in GitService.IC_NODE_TAGS

    line2 = '+   <task name="tarefa_teste"/>'
    m2 = GitService.TAG_REGEX.search(line2)
    assert m2 is not None
    tag2 = m2.group(1).lower()
    assert tag2 in GitService.IC_NODE_TAGS

    line_cond = '+   <condition expression="#{parametroUtil.getParametro(...)}"/>'
    m_cond = GitService.TAG_REGEX.search(line_cond)
    assert m_cond is not None
    assert m_cond.group(1).lower() == "condition"
    assert m_cond.group(1).lower() in GitService.IC_NODE_TAGS


    # Test regex tag parsing for removals (-)
    line3 = '-   <decision name="Decisao Antiga">'
    m3 = GitService.TAG_REGEX.search(line3)
    assert m3 is not None
    tag3 = m3.group(1).lower()
    assert tag3 == "decision"
    assert tag3 not in GitService.EXCLUDED_XML_TAGS

    line4 = '-   <event type="node-enter"/>'
    m4 = GitService.TAG_REGEX.search(line4)
    assert m4 is not None
    tag4 = m4.group(1).lower()
    assert tag4 in GitService.EXCLUDED_XML_TAGS

    # Test normalize_xml_metrics and formatting
    from app.models.commit import normalize_xml_metrics, format_ic_details

    metrics = {
        "added": {"transition": 2, "decision": 1},
        "removed": {"decision": 1},
        "total_added": 3,
        "total_removed": 1,
        "total_ics": 4,
    }
    normalized = normalize_xml_metrics(metrics)
    assert normalized["total_added"] == 3
    assert normalized["total_removed"] == 1
    assert normalized["total_ics"] == 4

    lines = format_ic_details(normalized, 4)
    text = "\n".join(lines)
    assert "Itens de Catálogo (IC) calculados: 4 IC(s) (+3 adições, -1 remoções)" in text
    assert "Tags Adicionadas (+3)" in text
    assert "<transition>: 2" in text
    assert "Tags Removidas (-1)" in text
    assert "<decision>: 1" in text

    # Test removals-only scenario (e.g. only removing decisions/transitions)
    removals_only = {
        "added": {},
        "removed": {"decision": 2},
        "total_added": 0,
        "total_removed": 2,
        "total_ics": 2,
    }
    rem_lines = format_ic_details(normalize_xml_metrics(removals_only), 2)
    rem_text = "\n".join(rem_lines)
    assert "Itens de Catálogo (IC) calculados: 2 IC(s) (-2 remoções)" in rem_text
    assert "Tags Removidas (-2)" in rem_text
    assert "<decision>: 2" in rem_text
    assert "Tags Adicionadas" not in rem_text

    # Test per-flow detailing scenario
    flow_metrics = {
        "added": {"transition": 3, "decision": 1},
        "removed": {"transition": 1},
        "total_added": 4,
        "total_removed": 1,
        "total_ics": 5,
        "flows": {
            "Fluxos/1o Grau/Plantao/Transferencia.xml": {
                "flow_name": "Transferencia.xml",
                "path": "Fluxos/1o Grau/Plantao/Transferencia.xml",
                "added": {"transition": 3},
                "removed": {"transition": 1},
                "total_added": 3,
                "total_removed": 1,
                "total_ics": 4,
            },
            "Fluxos/1o Grau/Plantao/Analise.xml": {
                "flow_name": "Analise.xml",
                "path": "Fluxos/1o Grau/Plantao/Analise.xml",
                "added": {"decision": 1},
                "removed": {},
                "total_added": 1,
                "total_removed": 0,
                "total_ics": 1,
            }
        }
    }
    norm_flows = normalize_xml_metrics(flow_metrics)
    assert len(norm_flows["flows"]) == 2
    f_lines = format_ic_details(norm_flows, 5)
    f_text = "\n".join(f_lines)
    assert "Detalhamento por Fluxo (regras do PJE):" in f_text
    assert "Fluxo: Fluxos/1o Grau/Plantao/Transferencia.xml" in f_text
    assert "Fluxo: Fluxos/1o Grau/Plantao/Analise.xml" in f_text
    assert "Tags Adicionadas (+3):" in f_text
    assert "Tags Removidas (-1):" in f_text
    assert "Tags Adicionadas (+1):" in f_text


def test_decode_git_path():
    """Test decoding of Git octal escape sequences for paths with accents and special characters."""
    from app.models.commit import decode_git_path

    # Path with í (\303\255) and ç (\303\247)
    raw1 = r"Fluxos/1o Grau/Fam\303\255lia/Juntada de Pe\303\247as.xml"
    assert decode_git_path(raw1) == "Fluxos/1o Grau/Família/Juntada de Peças.xml"

    # Quoted path with ã (\303\243) and ê (\303\252)
    raw2 = r'"Fluxos/1o Grau/Plant\303\243o/Transfer\303\252ncia de Plant\303\243o.xml"'
    assert decode_git_path(raw2) == "Fluxos/1o Grau/Plantão/Transferência de Plantão.xml"

    # Normal path
    raw3 = "app/models/commit.py"
    assert decode_git_path(raw3) == "app/models/commit.py"

    # None and empty
    assert decode_git_path("") == ""
    assert decode_git_path(None) == ""


def test_build_ic_description_compact_format():
    """Test build_ic_description generates compact description with tags placed directly under each XML file."""
    from app.models.commit import build_ic_description

    files_changed = [
        {
            "path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - Crimes Tráfico de Drogas.xml",
            "insertions": 15,
            "deletions": 2,
            "is_xml": True,
        },
        {
            "path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - VDOC.xml",
            "insertions": 1,
            "deletions": 1,
            "is_xml": True,
        },
        {
            "path": "src/main/resources/application.properties",
            "insertions": 2,
            "deletions": 0,
            "is_xml": False,
        }
    ]

    xml_tags_metrics = {
        "added": {"transition": 4, "condition": 1},
        "removed": {"condition": 1},
        "total_added": 5,
        "total_removed": 1,
        "total_ics": 6,
        "flows": {
            "Fluxos/1o Grau/Criminal/Análise de Secretaria - Crimes Tráfico de Drogas.xml": {
                "flow_name": "Crimes Tráfico de Drogas.xml",
                "path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - Crimes Tráfico de Drogas.xml",
                "added": {"transition": 4},
                "removed": {},
                "total_added": 4,
                "total_removed": 0,
                "total_ics": 4,
            },
            "Fluxos/1o Grau/Criminal/Análise de Secretaria - VDOC.xml": {
                "flow_name": "VDOC.xml",
                "path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - VDOC.xml",
                "added": {"condition": 1},
                "removed": {"condition": 1},
                "total_added": 1,
                "total_removed": 1,
                "total_ics": 2,
            }
        }
    }

    desc = build_ic_description(
        short_hash="5de7896",
        commit_date=None,
        author="desenvolvedor",
        message="#291317\nAdição das outras transições faltantes",
        commit_url="https://git.tjce.jus.br/sistemas/PJE/-/commit/5de7896",
        files_changed=files_changed,
        xml_tags_metrics=xml_tags_metrics,
        ic_count=6,
    )

    assert "Commit: 5de7896" in desc
    assert "Itens de Catálogo (IC) calculados: 6 IC(s) (+5 adições, -1 remoções)" in desc
    assert "Arquivos Alterados:" in desc
    # Checks that tags are placed under the XML file with a line break per tag
    assert "- [XML] Fluxos/1o Grau/Criminal/Análise de Secretaria - Crimes Tráfico de Drogas.xml (+15 / -2)" in desc
    assert "  * Tags Adicionadas (+4):" in desc
    assert "    * <transition>: 4" in desc
    assert "- [XML] Fluxos/1o Grau/Criminal/Análise de Secretaria - VDOC.xml (+1 / -1)" in desc
    assert "  * Tags Adicionadas (+1):" in desc
    assert "    * <condition>: 1" in desc
    assert "  * Tags Removidas (-1):" in desc
    assert "    * <condition>: 1" in desc
    assert "- src/main/resources/application.properties (+2 / -0)" in desc
    assert "(Total de arquivos XML alterados: 2)" in desc
    # Ensure redundant section was removed
    assert "Detalhamento por Fluxo" not in desc


def test_build_ic_description_with_modified_tags():
    """Test build_ic_description with modified tags (paired additions and deletions = adjustments)."""
    from app.models.commit import build_ic_description

    files_changed = [
        {
            "path": "Fluxos/2o Grau/Plantão/Análise de Secretaria - Plantão Criminal 2º Grau.xml",
            "insertions": 7,
            "deletions": 17,
            "is_xml": True,
        }
    ]

    xml_tags_metrics = {
        "added": {},
        "removed": {"node": 1, "transition": 1},
        "modified": {"decision": 1, "task-node": 1, "transition": 1},
        "total_added": 0,
        "total_removed": 2,
        "total_modified": 3,
        "total_ics": 5,
        "flows": {
            "Fluxos/2o Grau/Plantão/Análise de Secretaria - Plantão Criminal 2º Grau.xml": {
                "flow_name": "Análise de Secretaria - Plantão Criminal 2º Grau.xml",
                "path": "Fluxos/2o Grau/Plantão/Análise de Secretaria - Plantão Criminal 2º Grau.xml",
                "added": {},
                "removed": {"node": 1, "transition": 1},
                "modified": {"decision": 1, "task-node": 1, "transition": 1},
                "total_added": 0,
                "total_removed": 2,
                "total_modified": 3,
                "total_ics": 5,
            }
        },
    }

    desc = build_ic_description(
        short_hash="a716bd9",
        commit_date=None,
        author="athos.rocha",
        message="#287725 - Atualização de fluxos",
        commit_url="https://git.tjce.jus.br/sistemas/PJE/-/commit/a716bd9",
        files_changed=files_changed,
        xml_tags_metrics=xml_tags_metrics,
        ic_count=5,
    )

    assert "Commit: a716bd9" in desc
    assert "Itens de Catálogo (IC) calculados: 5 IC(s) (-2 remoções, ~3 ajustes)" in desc
    assert "  * Tags Removidas (-2):" in desc
    assert "    * <node>: 1" in desc
    assert "    * <transition>: 1" in desc
    assert "  * Tags Modificadas / Ajustadas (~3):" in desc
    assert "    * <decision>: 1" in desc
    assert "    * <task-node>: 1" in desc
    assert "    * <transition>: 1" in desc


def test_build_ic_description_multi_flow_with_condition():
    """Test IC description generation with multiple XML flows and condition adjustment (Soluções 1 e 2)."""
    from app.models.commit import build_ic_description

    files_changed = [
        {"path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - Crimes Tráfico de Drogas.xml", "insertions": 15, "deletions": 2, "is_xml": True},
        {"path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - Júri Organizações Criminosas.xml", "insertions": 20, "deletions": 7, "is_xml": True},
        {"path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - VDOC.xml", "insertions": 1, "deletions": 1, "is_xml": True},
    ]

    xml_tags_metrics = {
        "added": {"node": 2, "transition": 2},
        "removed": {},
        "modified": {"transition": 9, "condition": 1},
        "total_added": 4,
        "total_removed": 0,
        "total_modified": 10,
        "total_ics": 14,
        "flows": {
            "Fluxos/1o Grau/Criminal/Análise de Secretaria - Crimes Tráfico de Drogas.xml": {
                "flow_name": "Análise de Secretaria - Crimes Tráfico de Drogas.xml",
                "path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - Crimes Tráfico de Drogas.xml",
                "added": {"node": 1, "transition": 1},
                "removed": {},
                "modified": {"transition": 2},
                "total_added": 2,
                "total_removed": 0,
                "total_modified": 2,
                "total_ics": 4,
            },
            "Fluxos/1o Grau/Criminal/Análise de Secretaria - Júri Organizações Criminosas.xml": {
                "flow_name": "Análise de Secretaria - Júri Organizações Criminosas.xml",
                "path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - Júri Organizações Criminosas.xml",
                "added": {"node": 1, "transition": 1},
                "removed": {},
                "modified": {"transition": 7},
                "total_added": 2,
                "total_removed": 0,
                "total_modified": 7,
                "total_ics": 9,
            },
            "Fluxos/1o Grau/Criminal/Análise de Secretaria - VDOC.xml": {
                "flow_name": "Análise de Secretaria - VDOC.xml",
                "path": "Fluxos/1o Grau/Criminal/Análise de Secretaria - VDOC.xml",
                "added": {},
                "removed": {},
                "modified": {"condition": 1},
                "total_added": 0,
                "total_removed": 0,
                "total_modified": 1,
                "total_ics": 1,
            },
        },
    }

    desc = build_ic_description(
        short_hash="5de7896",
        commit_date=None,
        author="athos.rocha",
        message="#291317 - Adição das outras transições faltantes",
        commit_url="https://git.tjce.jus.br/sistemas/PJE/-/commit/5de7896",
        files_changed=files_changed,
        xml_tags_metrics=xml_tags_metrics,
        ic_count=14,
    )

    assert "Commit: 5de7896" in desc
    assert "Itens de Catálogo (IC) calculados: 14 IC(s) (+4 adições, ~10 ajustes)" in desc
    assert "- [XML] Fluxos/1o Grau/Criminal/Análise de Secretaria - Crimes Tráfico de Drogas.xml (+15 / -2)" in desc
    assert "- [XML] Fluxos/1o Grau/Criminal/Análise de Secretaria - Júri Organizações Criminosas.xml (+20 / -7)" in desc
    assert "- [XML] Fluxos/1o Grau/Criminal/Análise de Secretaria - VDOC.xml (+1 / -1)" in desc
    assert "<condition>: 1" in desc
    assert "(Total de arquivos XML alterados: 3)" in desc


def test_analyze_commit_xml_tags_new_rules():
    """Test that IC_NODE_TAGS treats transition, condition, variable, swimlane, action, and task as ICs and adjustments."""
    from unittest.mock import MagicMock

    fake_patch = """diff --git "a/Fluxos/fluxo1.xml" "b/Fluxos/fluxo1.xml"
--- a/Fluxos/fluxo1.xml
+++ b/Fluxos/fluxo1.xml
@@ -10,6 +10,8 @@
-    <swimlane name="Atendente Antigo"/>
+    <swimlane name="Atendente Novo"/>
-    <task name="Analisar Autos Antigo"/>
+    <task name="Analisar Autos Novo"/>
-    <transition to="Destino A" name="Enviar"/>
+    <transition to="Destino A" name="Enviar Ajustado"/>
+    <transition to="Destino B" name="Nova Transicao"/>
-    <condition expression="#{antigo}"/>
+    <condition expression="#{novo}"/>
-    <action expression="#{oldAction()}"/>
+    <action expression="#{newAction()}"/>
-    <variable name="varOld"/>
+    <variable name="varNew"/>
"""
    repo = MagicMock()
    repo.git.show.return_value = fake_patch

    result = GitService.analyze_commit_xml_tags(repo, "abc1234567890")
    assert result["total_added"] == 1  # Nova Transicao
    assert result["total_removed"] == 0
    assert result["total_modified"] == 6  # swimlane, task, transition, condition, action, variable
    assert result["total_ics"] == 7
    assert result["modified"]["swimlane"] == 1
    assert result["modified"]["task"] == 1
    assert result["modified"]["transition"] == 1
    assert result["modified"]["condition"] == 1
    assert result["modified"]["action"] == 1
    assert result["modified"]["variable"] == 1
    assert result["added"]["transition"] == 1


def test_get_branches_caching():
    """Test that get_branches caches results in memory and honors force_refresh and clear_branches_cache."""
    GitService.clear_branches_cache()
    repo_path = Path(settings.BASE_DIR).resolve()
    cache_key = str(repo_path)

    assert cache_key not in GitService._BRANCHES_CACHE

    # First call fills the cache
    res1 = GitService.get_branches(repo_path)
    assert isinstance(res1, dict)
    assert "active" in res1
    assert "local" in res1
    assert "remote" in res1
    assert cache_key in GitService._BRANCHES_CACHE
    initial_timestamp = GitService._BRANCHES_CACHE[cache_key]["timestamp"]

    # Second call uses the cached result (same timestamp)
    res2 = GitService.get_branches(repo_path)
    assert res2 == res1
    assert GitService._BRANCHES_CACHE[cache_key]["timestamp"] == initial_timestamp

    # Force refresh updates the timestamp
    import time
    time.sleep(0.01)
    res3 = GitService.get_branches(repo_path, force_refresh=True)
    assert res3 == res1
    assert GitService._BRANCHES_CACHE[cache_key]["timestamp"] >= initial_timestamp

    # Clear cache removes it
    GitService.clear_branches_cache(repo_path)
    assert cache_key not in GitService._BRANCHES_CACHE




