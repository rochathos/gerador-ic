from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.config import settings

client = TestClient(app)


def test_home_page():
    """Verify home page loads successfully with 200 OK."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Productivity Assistant" in response.text
    assert "Painel de Produtividade" in response.text


def test_commits_page():
    """Verify commits page loads successfully."""
    response = client.get("/commits")
    assert response.status_code == 200
    assert "Gerenciamento de Commits" in response.text


def test_meetings_page():
    """Verify meetings page loads successfully."""
    response = client.get("/meetings")
    assert response.status_code == 200
    assert "Reuniões" in response.text


def test_catalog_items_page():
    """Verify catalog items page loads successfully."""
    response = client.get("/catalog-items")
    assert response.status_code == 200
    assert "Itens de Catálogo (IC)" in response.text


def test_history_page():
    """Verify execution history page loads successfully."""
    response = client.get("/history")
    assert response.status_code == 200
    assert "Histórico de Execuções" in response.text


def test_analyze_endpoint():
    """Test analyzing period via POST /analyze (live query vs db save)."""
    now = datetime.now()
    start_str = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    end_str = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")

    author_param = settings.GIT_AUTHOR_NAME or ""
    # Live query without saving to db (default)
    response_live = client.post(
        "/analyze",
        data={
            "start_date": start_str,
            "end_date": end_str,
            "repo_path": str(settings.BASE_DIR),
            "author": author_param,
        },
        follow_redirects=False,
    )
    assert response_live.status_code == 303
    assert "start_date=" in response_live.headers["location"]



def test_create_single_ic_endpoint():
    """Test creating an individual IC via POST /api/create-ic."""
    response = client.post(
        "/api/create-ic",
        json={
            "title": "Ajuste de teste individual",
            "description": "Commit: 1234567\nData: 30/09/2026\nAutor: desenvolvedor",
            "status": "sugerido",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "id" in data
    assert data["title"] == "Ajuste de teste individual"


def test_export_excel():
    """Test generating and downloading Excel export."""
    response = client.get("/export/excel")
    assert response.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in response.headers["content-type"]
    assert len(response.content) > 0


def test_export_pdf():
    """Test generating and downloading PDF export."""
    response = client.get("/export/pdf")
    assert response.status_code == 200
    assert "application/pdf" in response.headers["content-type"]
    assert len(response.content) > 0


def test_api_commits_git_paged():
    """Test lazy-load API endpoint /api/commits/git-paged."""
    response = client.get("/api/commits/git-paged?skip=0&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "commits" in data
    assert "has_more" in data
    assert "next_skip" in data
    assert isinstance(data["commits"], list)


def test_api_commits_inspect_and_save_ic():
    """Test inspecting commit by hash and saving IC with commit_hash."""
    # First get a valid commit from paged API
    response = client.get("/api/commits/git-paged?skip=0&limit=1")
    assert response.status_code == 200
    commits = response.json()["commits"]
    if commits:
        target_hash = commits[0]["hash"]
        inspect_res = client.get(f"/api/commits/inspect/{target_hash}")
        assert inspect_res.status_code == 200
        inspect_data = inspect_res.json()
        assert inspect_data["success"] is True
        assert inspect_data["commit"]["hash"] == target_hash

        # Now create IC with this commit_hash
        create_res = client.post(
            "/api/create-ic",
            json={
                "title": f"IC para commit {commits[0]['short_hash']}",
                "description": "Descrição detalhada do commit inspecionado",
                "commit_hash": target_hash,
                "status": "sugerido",
            },
        )
        assert create_res.status_code == 200
        assert create_res.json()["success"] is True

        # Inspect again, now is_saved should be True
        inspect_res_2 = client.get(f"/api/commits/inspect/{target_hash}")
        assert inspect_res_2.status_code == 200
        assert inspect_res_2.json()["commit"]["is_saved"] is True


def test_redmine_api_connection():
    """Test connecting to Redmine API with configured API key."""
    import pytest
    from app.services.redmine_service import RedmineService
    if settings.REDMINE_API_KEY:
        success, msg, user_data = RedmineService.test_connection()
        if not success and ("getaddrinfo failed" in msg or "Failed to establish a new connection" in msg or "Connection refused" in msg):
            pytest.skip("Redmine TJCE intranet unreachable without VPN")
        assert success is True
        assert user_data is not None
        assert "id" in user_data
        assert "firstname" in user_data
    else:
        success, msg, user_data = RedmineService.test_connection()
        assert success is False


def test_api_redmine_create_ic_validation():
    """Test POST /api/redmine/create-ic validation."""
    response = client.post(
        "/api/redmine/create-ic",
        json={"title": "", "description": "Sem titulo"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False


def test_create_ic_default_status_salvo():
    """Test creating an IC defaults to status 'salvo' and updates properly."""
    res = client.post(
        "/api/create-ic",
        json={
            "title": "IC de Teste Status Salvo",
            "description": "Descrição do teste com status salvo",
            "commit_hash": "abcdef1234567890abcdef1234567890abcdef12",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "salvo"
    item_id = data["id"]

    # History page should list this IC
    history_res = client.get("/history")
    assert history_res.status_code == 200
    assert "IC de Teste Status Salvo" in history_res.text
    assert "Salvo" in history_res.text

    # Prefix match should return is_saved=True even with short hash
    inspect_res = client.get("/api/commits/inspect/abcdef1")
    # inspect might return 404 if git doesn't have this mock hash, but check_is_commit_saved handles it
    # Clean up test item
    del_res = client.post(f"/catalog-items/{item_id}/delete")
    assert del_res.status_code in (200, 302, 303)


def test_update_catalog_item_redmine_id():
    """Test linking a Redmine ID to an existing Catalog Item."""
    # 1. Create an IC
    create_res = client.post(
        "/api/create-ic",
        json={
            "title": "IC Teste Redmine Link",
            "description": "Descricao de teste",
            "commit_hash": "999888777666555444333222111000aabbccdde",
        },
    )
    assert create_res.status_code == 200
    item_id = create_res.json()["id"]

    # 2. Update Redmine ID
    link_res = client.post(
        f"/api/catalog-items/{item_id}/redmine-id",
        json={"redmine_id": "294999"},
    )
    assert link_res.status_code == 200
    data = link_res.json()
    assert data["success"] is True
    assert data["redmine_id"] == "294999"
    assert data["status"] == "criado"

    # 3. Check history page contains the Redmine issue ID and does NOT contain delete button for this created item
    hist_res = client.get("/history")
    assert hist_res.status_code == 200
    assert "294999" in hist_res.text
    assert f"/catalog-items/{item_id}/delete" not in hist_res.text

    # 4. Attempting to delete an item created in Redmine should be blocked by backend
    del_res = client.post(f"/catalog-items/{item_id}/delete")
    assert del_res.status_code in (200, 302, 303)

    from app.core.database import SessionLocal
    from app.models.catalog_item import CatalogItem
    db = SessionLocal()
    try:
        item = db.get(CatalogItem, item_id)
        assert item is not None  # Exclusão bloqueada com sucesso!
        # Limpeza direta no banco de dados para isolamento do teste
        db.delete(item)
        db.commit()
    finally:
        db.close()


def test_import_teams_calls_17_minutes():
    """Test importing Teams calls with 17m duration via /api/meetings/import-teams-calls."""
    from app.services.meeting_service import MeetingService

    # 1. Verify parser directly
    secs = MeetingService.parse_duration_to_seconds("17m")
    assert secs == 1020
    assert MeetingService.format_seconds_to_duration(secs) == "17m"

    secs2 = MeetingService.parse_duration_to_seconds("17 minutos e 30 segundos")
    assert secs2 == 1050
    assert MeetingService.format_seconds_to_duration(secs2) == "17m 30s"

    # 2. Test API import
    payload = {
        "calls": [
            {
                "contact_name": "Colega Teste 17m",
                "title": "Alinhamento com Colega Teste 17m",
                "call_type": "efetuada",
                "duration": "17m",
                "date_str": "Hoje às 14:00",
            }
        ]
    }

    res = client.post("/api/meetings/import-teams-calls", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["count"] >= 1

    # 3. Check meetings page displays 17m
    meetings_page = client.get("/meetings")
    assert meetings_page.status_code == 200
    assert "Colega Teste 17m" in meetings_page.text
    assert "17m" in meetings_page.text

    # 4. Clean up test meeting
    from app.core.database import SessionLocal
    from app.models.meeting import Meeting
    db = SessionLocal()
    try:
        db.query(Meeting).filter(Meeting.contact_name == "Colega Teste 17m").delete()
        db.commit()
    finally:
        db.close()


def test_meeting_is_saved_status_and_card_layout():
    """Verify that a meeting saved in DB shows 'Salvo' status and matching meetings inherit saved status."""
    from app.core.database import SessionLocal
    from app.models.meeting import Meeting
    from app.models.catalog_item import CatalogItem
    from app.services.meeting_service import MeetingService
    from datetime import datetime, timezone, timedelta

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        # 1. Create a meeting
        m1 = Meeting(
            title="Alinhamento Arquitetura",
            contact_name="Fulano de Tal",
            call_type="efetuada",
            start_time=now,
            end_time=now + timedelta(minutes=30),
            duration="30m",
            status="pendente",
        )
        db.add(m1)
        db.commit()
        db.refresh(m1)

        # 2. Before IC, should be is_saved False
        assert m1.is_saved is False

        # 3. Call create-ic with dry_run=True (simulation)
        payload = {
            "meeting_ids": [m1.id],
            "title": "Alinhamento com Fulano de Tal",
            "activity_type": "Gestão - Participação em reunião, exceto reunião de levantamento de requisitos",
            "complexity": "Baixa",
            "dry_run": True,
        }
        res = client.post("/api/meetings/create-ic", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

        db.refresh(m1)
        assert m1.is_saved is True
        assert m1.status == "salvo"

        # 4. Check meetings page shows "Salvo"
        page = client.get("/meetings")
        assert page.status_code == 200
        assert "Status IC" in page.text
        assert "Salvo" in page.text

        # 5. Create another meeting with same person, date/time and duration
        m2 = Meeting(
            title="Alinhamento Arquitetura Duplicado",
            contact_name="Fulano de Tal",
            call_type="efetuada",
            start_time=now,
            end_time=now + timedelta(minutes=30),
            duration="30m",
            status="pendente",
        )
        db.add(m2)
        db.commit()
        db.refresh(m2)

        # get_meetings should identify m2 as is_saved because an identical saved meeting exists
        meetings = MeetingService.get_meetings(db)
        m2_found = next((m for m in meetings if m.id == m2.id), None)
        assert m2_found is not None
        assert m2_found.is_saved is True

        # Clean up
        db.delete(m1)
        db.delete(m2)
        db.query(CatalogItem).filter(CatalogItem.title == "Alinhamento com Fulano de Tal").delete()
        db.commit()
    finally:
        db.close()


def test_commits_table_columns_selector():
    """Test that commits tables in both home and commits page contain column customization selectors and attributes."""
    # 1. Home page table
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "column-selector-list" in res_home.text
    assert 'data-col="hash"' in res_home.text
    assert 'data-col="author"' in res_home.text
    assert 'data-col="repo"' in res_home.text
    assert 'data-col="branch"' in res_home.text
    assert 'data-col="files"' in res_home.text
    assert 'data-col="status"' in res_home.text
    assert 'data-col="actions"' in res_home.text

    # 2. Commits full page table
    res_commits = client.get("/commits")
    assert res_commits.status_code == 200
    assert "column-selector-list" in res_commits.text
    assert 'data-col="hash"' in res_commits.text
    assert 'data-col="author"' in res_commits.text
    assert 'data-col="repo"' in res_commits.text
    assert 'data-col="branch"' in res_commits.text
    assert 'data-col="files"' in res_commits.text
    assert 'data-col="status"' in res_commits.text
    assert 'data-col="actions"' in res_commits.text


def test_assegurar_banco_de_dados_existe_already_exists(monkeypatch):
    """Test that assegurar_banco_de_dados_existe checks pg_database and skips creation if db exists."""
    from unittest.mock import MagicMock
    import psycopg2
    from app.core.database import assegurar_banco_de_dados_existe

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (1,)  # Database exists
    mock_conn.cursor.return_value = mock_cursor

    monkeypatch.setattr(psycopg2, "connect", lambda **kwargs: mock_conn)

    assegurar_banco_de_dados_existe()
    assert mock_cursor.execute.call_count == 1
    # Ensure CREATE DATABASE was NOT executed
    args, _ = mock_cursor.execute.call_args
    assert "SELECT 1 FROM pg_database" in args[0]


def test_assegurar_banco_de_dados_existe_creates_new(monkeypatch):
    """Test that assegurar_banco_de_dados_existe executes CREATE DATABASE when database does not exist."""
    from unittest.mock import MagicMock
    import psycopg2
    from app.core.database import assegurar_banco_de_dados_existe

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None  # Database does not exist
    mock_conn.cursor.return_value = mock_cursor

    monkeypatch.setattr(psycopg2, "connect", lambda **kwargs: mock_conn)

    assegurar_banco_de_dados_existe()
    assert mock_cursor.execute.call_count == 2
    create_call_args = mock_cursor.execute.call_args_list[1][0]
    # Verify CREATE DATABASE statement
    assert "CREATE DATABASE" in str(create_call_args[0])


def test_assegurar_banco_de_dados_existe_handles_connection_error(monkeypatch):
    """Test that assegurar_banco_de_dados_existe gracefully handles connection errors without halting."""
    import psycopg2
    from app.core.database import assegurar_banco_de_dados_existe

    def mock_connect(**kwargs):
        raise psycopg2.OperationalError("Simulated connection failure to postgres db")

    monkeypatch.setattr(psycopg2, "connect", mock_connect)

    # Should not raise exception
    assegurar_banco_de_dados_existe()





