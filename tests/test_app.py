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
    """Test analyzing period via POST /analyze."""
    now = datetime.now()
    start_str = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    end_str = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")

    response = client.post(
        "/analyze",
        data={
            "start_date": start_str,
            "end_date": end_str,
            "repo_path": str(settings.BASE_DIR),
            "author": "athos",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "alert_type=success" in response.headers["location"]


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
