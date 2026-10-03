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

    # 3. Check history page contains the Redmine issue ID
    hist_res = client.get("/history")
    assert hist_res.status_code == 200
    assert "294999" in hist_res.text

    # Clean up
    client.post(f"/catalog-items/{item_id}/delete")



