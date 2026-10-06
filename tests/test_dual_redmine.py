import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from main import app
from app.core.database import get_db
from app.models.catalog_item import CatalogItem
from app.models.commit import Commit
from app.services.catalog_generator_service import CatalogGeneratorService

client = TestClient(app)


def test_proposta_apenas_xml():
    """Commit com apenas arquivos XML gera 1 Redmine de automação de fluxo."""
    commit_mock = {
        "hash": "abc1234567890abcdef1234567890abcdef1234",
        "message": "Ajuste na tarefa de automacao PJE",
        "author": "Desenvolvedor Teste",
        "commit_date": datetime.now(timezone.utc),
        "files_changed": [
            {"filename": "processo/fluxo.xml", "is_xml": True, "is_sql": False}
        ],
        "ic_count_xml": 2,
        "ic_count_sql": 0,
        "xml_tags_metrics": {
            "total_ics": 2,
            "flows": [{"flow_name": "FluxoPrincipal", "tags_added": 1, "tags_modified": 1}],
        },
        "sql_scripts_metrics": {},
    }

    propostas = CatalogGeneratorService.gerar_propostas_para_commit(commit_mock)
    assert len(propostas) == 1
    p = propostas[0]
    assert p["natureza"] == "fluxo"
    assert p["activity_type"] == "Desenvolvimento - Criar/Manter tarefa de automação"
    assert p["ic_count"] == 2
    assert p["commit_hash"] == commit_mock["hash"]
    assert "processo/fluxo.xml" in p["description"]


def test_proposta_apenas_sql():
    """Commit com apenas arquivos SQL gera 1 Redmine de scripts de banco de dados."""
    commit_mock = {
        "hash": "def9876543210fedcba9876543210fedcba9876",
        "message": "Script de migracao e carga",
        "author": "DBA Teste",
        "commit_date": datetime.now(timezone.utc),
        "files_changed": [
            {"filename": "scripts/01_update_pje.sql", "is_xml": False, "is_sql": True}
        ],
        "ic_count_xml": 0,
        "ic_count_sql": 3,
        "xml_tags_metrics": {},
        "sql_scripts_metrics": {
            "total_ics": 3,
            "inserts": 1,
            "updates": 2,
            "scripts": ["scripts/01_update_pje.sql"],
        },
    }

    propostas = CatalogGeneratorService.gerar_propostas_para_commit(commit_mock)
    assert len(propostas) == 1
    p = propostas[0]
    assert p["natureza"] == "sql"
    assert p["activity_type"] == "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados"
    assert p["ic_count"] == 3
    assert p["commit_hash"] == commit_mock["hash"]
    assert "01_update_pje.sql" in p["description"]


def test_proposta_ambos_xml_e_sql():
    """Commit com XML e SQL simultâneos gera 2 Redmines vinculados ao mesmo commit hash."""
    commit_mock = {
        "hash": "777888999aaabbbcccdddeeefff0001112223334",
        "message": "Feature completa: novo fluxo e carga de parametros",
        "author": "Fullstack Teste",
        "commit_date": datetime.now(timezone.utc),
        "files_changed": [
            {"filename": "automacao/tarefa.xml", "is_xml": True, "is_sql": False},
            {"filename": "scripts/carga_tb_parametro.sql", "is_xml": False, "is_sql": True},
        ],
        "ic_count_xml": 1,
        "ic_count_sql": 2,
        "xml_tags_metrics": {
            "total_ics": 1,
            "flows": [{"flow_name": "TarefaGeral", "tags_added": 1}],
        },
        "sql_scripts_metrics": {
            "total_ics": 2,
            "inserts": 2,
            "scripts": ["scripts/carga_tb_parametro.sql"],
        },
    }

    propostas = CatalogGeneratorService.gerar_propostas_para_commit(commit_mock)
    assert len(propostas) == 2

    # Proposta 1: Principal - Catálogo da funcionalidade (Fluxo XML)
    p_fluxo = propostas[0]
    assert p_fluxo["natureza"] == "fluxo"
    assert p_fluxo["activity_type"] == "Desenvolvimento - Criar/Manter tarefa de automação"
    assert p_fluxo["commit_hash"] == commit_mock["hash"]
    assert p_fluxo["ic_count"] == 1

    # Proposta 2: Secundária - Atividade de banco de dados (Scripts SQL)
    p_sql = propostas[1]
    assert p_sql["natureza"] == "sql"
    assert p_sql["activity_type"] == "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados"
    assert p_sql["commit_hash"] == commit_mock["hash"]
    assert p_sql["ic_count"] == 2


def test_commit_model_dual_redmine_properties():
    """Testa se o modelo Commit identifica corretamente ajustes em XML, SQL e necessidade de 2 Redmines."""
    commit = Commit(
        hash="11223344556677889900aabbccddeeff11223344",
        message="Ajuste misto de regras",
        author="Dev",
        branch="main",
        files_changed=[
            {"filename": "fluxo.xml", "is_xml": True, "is_sql": False},
            {"filename": "carga.sql", "is_xml": False, "is_sql": True},
        ],
        xml_tags_metrics={"total_ics": 1},
        sql_scripts_metrics={"total_ics": 1},
        ic_count_xml=1,
        ic_count_sql=1,
    )

    assert commit.has_xml_changes is True
    assert commit.has_sql_changes is True
    assert commit.tem_ambos_ajustes is True
    assert commit.precisa_dois_redmines is True
    assert commit.ic_fluxo_count == 1
    assert commit.ic_sql_count == 1

    d = commit.to_dict()
    assert d["has_xml_changes"] is True
    assert d["has_sql_changes"] is True
    assert d["tem_ambos_ajustes"] is True
    assert d["precisa_dois_redmines"] is True


def test_api_salvar_dois_redmines_mesmo_commit():
    """Verifica que o endpoint /api/create-ic salva 2 itens de catálogo (fluxo e sql) para o mesmo hash sem colisão."""
    db = next(get_db())
    test_hash = "beefcafe12345678"

    # Limpar registros prévios do teste
    existing = db.execute(select(CatalogItem).where(CatalogItem.commit_hash == test_hash)).scalars().all()
    for item in existing:
        db.delete(item)
    db.commit()

    # 1. Salvar IC de Fluxo
    res_fluxo = client.post(
        "/api/create-ic",
        json={
            "title": "Fluxo XML - Commit Conjunto",
            "description": "Descricao do fluxo XML",
            "commit_hash": test_hash,
            "natureza": "fluxo",
            "activity_type": "Desenvolvimento - Criar/Manter tarefa de automação",
            "ic_count": 2,
            "status": "salvo",
        },
    )
    assert res_fluxo.status_code == 200
    data_fluxo = res_fluxo.json()
    assert data_fluxo["success"] is True
    assert data_fluxo["natureza"] == "fluxo"
    id_fluxo = data_fluxo["id"]

    # 2. Salvar IC de SQL para o MESMO commit
    res_sql = client.post(
        "/api/create-ic",
        json={
            "title": "Script SQL - Commit Conjunto",
            "description": "Descricao dos scripts SQL",
            "commit_hash": test_hash,
            "natureza": "sql",
            "activity_type": "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados",
            "ic_count": 3,
            "status": "salvo",
        },
    )
    assert res_sql.status_code == 200
    data_sql = res_sql.json()
    assert data_sql["success"] is True
    assert data_sql["natureza"] == "sql"
    id_sql = data_sql["id"]

    assert id_fluxo != id_sql

    # 3. Validar que ambos coexistem no banco de dados vinculados ao mesmo commit_hash
    itens = db.execute(select(CatalogItem).where(CatalogItem.commit_hash == test_hash)).scalars().all()
    assert len(itens) == 2

    naturezas = {it.natureza: it for it in itens}
    assert "fluxo" in naturezas
    assert "sql" in naturezas
    assert naturezas["fluxo"].ic_count == 2
    assert naturezas["sql"].ic_count == 3
    assert naturezas["fluxo"].activity_type == "Desenvolvimento - Criar/Manter tarefa de automação"
    assert naturezas["sql"].activity_type == "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados"

    # Cleanup
    for item in itens:
        db.delete(item)
    db.commit()


def test_api_redmine_simulacao_dois_redmines_mesmo_commit():
    """Verifica que a simulação (/api/redmine/create-ic com dry_run) gera Redmines distintos para cada natureza no mesmo commit."""
    db = next(get_db())
    test_hash = "cafebabe99887766"

    # Limpeza
    existing = db.execute(select(CatalogItem).where(CatalogItem.commit_hash == test_hash)).scalars().all()
    for item in existing:
        db.delete(item)
    db.commit()

    # 1. Simulação Fluxo
    res_fluxo = client.post(
        "/api/redmine/create-ic",
        json={
            "title": "Simulação Fluxo XML",
            "description": "Ajuste em fluxo",
            "commit_hash": test_hash,
            "natureza": "fluxo",
            "activity_type": "Desenvolvimento - Criar/Manter tarefa de automação",
            "ic_count": 1,
            "dry_run": True,
        },
    )
    assert res_fluxo.status_code == 200
    data_fluxo = res_fluxo.json()
    assert data_fluxo["success"] is True
    redmine_fluxo_id = str(data_fluxo["issue_id"])

    # 2. Simulação SQL
    res_sql = client.post(
        "/api/redmine/create-ic",
        json={
            "title": "Simulação Script SQL",
            "description": "Ajuste em script SQL",
            "commit_hash": test_hash,
            "natureza": "sql",
            "activity_type": "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados",
            "ic_count": 2,
            "dry_run": True,
        },
    )
    assert res_sql.status_code == 200
    data_sql = res_sql.json()
    assert data_sql["success"] is True
    redmine_sql_id = str(data_sql["issue_id"])

    # Validar persistência independente
    itens = db.execute(select(CatalogItem).where(CatalogItem.commit_hash == test_hash)).scalars().all()
    assert len(itens) == 2

    mapa = {it.natureza: it for it in itens}
    assert mapa["fluxo"].redmine_id == redmine_fluxo_id
    assert mapa["fluxo"].status == "criado"
    assert mapa["sql"].redmine_id == redmine_sql_id
    assert mapa["sql"].status == "criado"

    # Cleanup
    for item in itens:
        db.delete(item)
    db.commit()
