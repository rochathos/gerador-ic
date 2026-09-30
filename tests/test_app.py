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

    # 1. Live query without save_to_db (default)
    response_live = client.post(
        "/analyze",
        data={
            "start_date": start_str,
            "end_date": end_str,
            "repo_path": str(settings.BASE_DIR),
            "author": "athos",
        },
        follow_redirects=False,
    )
    assert response_live.status_code == 303
    assert "start_date=" in response_live.headers["location"]

    # 2. Query with save_to_db = true
    response_save = client.post(
        "/analyze",
        data={
            "start_date": start_str,
            "end_date": end_str,
            "repo_path": str(settings.BASE_DIR),
            "author": "athos",
            "save_to_db": "true",
        },
        follow_redirects=False,
    )
    assert response_save.status_code == 303
    assert "alert_type=success" in response_save.headers["location"]


def test_create_single_ic_endpoint():
    """Test creating an individual IC via POST /api/create-ic."""
    response = client.post(
        "/api/create-ic",
        json={
            "title": "Ajuste de teste individual",
            "description": "Commit: 1234567\nData: 30/09/2026\nAutor: athos.rocha",
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
