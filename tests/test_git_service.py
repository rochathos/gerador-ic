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
    start_date = now - timedelta(days=1)
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


def test_execute_analysis_and_persistence(db_session):
    """Test the full analysis execution pipeline and DB persistence."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=1)
    end_date = now + timedelta(days=1)

    history, saved_commits = GitService.execute_analysis(
        db=db_session,
        repo_path=settings.BASE_DIR,
        start_date=start_date,
        end_date=end_date,
        author=None,
        notes="Teste automatizado via pytest",
    )

    assert history.id is not None
    assert history.status == "concluido"
    assert history.total_commits > 0
    assert len(saved_commits) == history.total_commits

    # Verify query directly in database
    db_history = db_session.get(ExecutionHistory, history.id)
    assert db_history is not None
    assert len(db_history.commits) == history.total_commits


def test_xml_files_metrics(db_session):
    """Test detection and counting of XML file edits and line modifications."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=1)
    end_date = now + timedelta(days=1)

    history, saved_commits = GitService.execute_analysis(
        db=db_session,
        repo_path=settings.BASE_DIR,
        start_date=start_date,
        end_date=end_date,
        author=settings.GIT_AUTHOR_NAME or None,
    )

    xml_commits = [c for c in saved_commits if c.has_xml_changes]
    assert len(xml_commits) >= 2

    # Check that XML metrics are properly extracted
    latest_xml = xml_commits[-1]
    assert latest_xml.xml_files_count >= 1
    assert latest_xml.xml_insertions > 0
    assert latest_xml.xml_total_edits > 0
    assert any("database-changelog.xml" in f["filename"] for f in latest_xml.xml_files)


def test_xml_tags_ic_counting():
    """Test XML tag counting rule matching icf.sh (filtering excluded tags)."""
    # Test exclusion set from icf.sh (with condition removed so it counts as IC)
    assert "process-definition" in GitService.EXCLUDED_XML_TAGS
    assert "start-state" in GitService.EXCLUDED_XML_TAGS
    assert "end-state" in GitService.EXCLUDED_XML_TAGS
    assert "condition" not in GitService.EXCLUDED_XML_TAGS
    assert "assignment" in GitService.EXCLUDED_XML_TAGS
    assert "controller" in GitService.EXCLUDED_XML_TAGS
    assert "task" in GitService.EXCLUDED_XML_TAGS
    assert "script" in GitService.EXCLUDED_XML_TAGS
    assert "event" in GitService.EXCLUDED_XML_TAGS

    # Test regex tag parsing for additions (+)
    line1 = '+   <transition to="fim" name="concluir"/>'
    m1 = GitService.TAG_REGEX.search(line1)
    assert m1 is not None
    tag1 = m1.group(1).lower()
    assert tag1 == "transition"
    assert tag1 not in GitService.EXCLUDED_XML_TAGS

    line2 = '+   <task name="tarefa_teste"/>'
    m2 = GitService.TAG_REGEX.search(line2)
    assert m2 is not None
    tag2 = m2.group(1).lower()
    assert tag2 in GitService.EXCLUDED_XML_TAGS

    # Test condition tag is counted when added or removed
    line_cond = '+   <condition expression="#{parametroUtil.getParametro(...)}"/>'
    m_cond = GitService.TAG_REGEX.search(line_cond)
    assert m_cond is not None
    assert m_cond.group(1).lower() == "condition"
    assert m_cond.group(1).lower() not in GitService.EXCLUDED_XML_TAGS

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
    assert "Itens de Catálogo (IC) calculados: 4 IC(s) (3 adicionadas, 1 removidas)" in text
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
    assert "Itens de Catálogo (IC) calculados: 6 IC(s) (5 adicionadas, 1 removidas)" in desc
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
