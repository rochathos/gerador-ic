import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from main import app
from app.core.database import get_db
from app.models.catalog_item import CatalogItem

client = TestClient(app)

def test_simulation_generates_fake_id_and_saves_to_db():
    db = next(get_db())
    test_hash = "aabb11223344"
    
    # Ensure clean state for test commit hash
    existing = db.execute(select(CatalogItem).where(CatalogItem.commit_hash == test_hash)).scalars().all()
    for item in existing:
        db.delete(item)
    db.commit()

    payload = {
        "title": "Teste Automatizado de Simulação IC",
        "description": "Descrição de teste para simulação do Redmine",
        "commit_hash": test_hash,
        "commit_url": "https://git.tjce.jus.br/sistemas/PJE/-/commit/aabb11223344",
        "ic_count": 2,
        "activity_type": "Desenvolvimento - Criar/Manter tarefa de automação",
        "complexity": "Baixa",
        "dry_run": True,
    }

    response = client.post("/api/redmine/create-ic", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["dry_run"] is True
    assert "issue_id" in data
    fake_id = str(data["issue_id"])
    assert fake_id.startswith("99")
    assert f"/issues/{fake_id}" in data["issue_url"]

    # Verify database persistence
    saved_item = db.execute(select(CatalogItem).where(CatalogItem.commit_hash == test_hash)).scalars().first()
    assert saved_item is not None
    assert saved_item.status == "criado"
    assert saved_item.redmine_id == fake_id
    assert saved_item.title == payload["title"]

    # Cleanup
    db.delete(saved_item)
    db.commit()
