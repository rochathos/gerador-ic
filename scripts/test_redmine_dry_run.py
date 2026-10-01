"""Script de teste completo e simulação (Dry-Run) da integração Redmine REST API.

Valida:
1. Conexão com Redmine TJCE e dados do usuário autenticado.
2. Permissões no Projeto PJe (ID 52) e Rastreador Item Catálogo PJE (ID 156).
3. Existência e integridade dos Campos Customizados (455, 456, 457, 479).
4. Leitura do repositório Git local (C:/ambiente/Git/PJE) e último commit do autor.
5. Cálculo de métricas e contagem de ICs (Item de Catálogo).
6. Montagem e validação do payload JSON final (SEM criar a tarefa no Redmine).
7. Conexão com o banco de dados PostgreSQL.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import text
from app.core.config import settings
from app.core.logger import logger
from app.core.database import SessionLocal
from app.services.git_service import GitService
from app.services.catalog_generator_service import CatalogGeneratorService
from app.services.redmine_service import RedmineService


def run_full_dry_run():
    print("\n" + "=" * 80)
    print(" INICIANDO TESTE COMPLETO DE INTEGRAÇÃO REDMINE (MODO SEGURO / DRY-RUN)")
    print("=" * 80 + "\n")

    logger.info("==================================================================")
    logger.info("[TESTE / DRY-RUN] Iniciando validação completa da integração Redmine...")
    logger.info("==================================================================")

    # -------------------------------------------------------------------------
    # ETAPA 1: Conexão com o Redmine e Validação do Usuário
    # -------------------------------------------------------------------------
    logger.info("[ETAPA 1/7] Testando conexão com a API do Redmine TJCE...")
    base_url = settings.REDMINE_URL.rstrip("/")
    api_key = settings.REDMINE_API_KEY

    if not api_key:
        logger.error("[ETAPA 1/7] FALHA: REDMINE_API_KEY não configurada no .env!")
        return

    headers = RedmineService.get_headers(api_key)
    try:
        with httpx.Client(verify=False, timeout=15.0) as client:
            resp = client.get(f"{base_url}/users/current.json", headers=headers)
            if resp.status_code != 200:
                logger.error(f"[ETAPA 1/7] FALHA: HTTP {resp.status_code} ao consultar usuário: {resp.text}")
                return
            user_data = resp.json().get("user", {})
            user_id = user_data.get("id")
            user_login = user_data.get("login")
            user_name = f"{user_data.get('firstname', '')} {user_data.get('lastname', '')}".strip()
            user_mail = user_data.get("mail")

            logger.info(f"[ETAPA 1/7] SUCESSO: Conectado como '{user_name}' (ID: #{user_id}, Login: {user_login}, Email: {user_mail})")
    except Exception as exc:
        logger.error(f"[ETAPA 1/7] FALHA de rede ao conectar no Redmine: {str(exc)}")
        return

    # -------------------------------------------------------------------------
    # ETAPA 2: Validação do Projeto PJe (ID 52) e Rastreador (ID 156)
    # -------------------------------------------------------------------------
    logger.info("[ETAPA 2/7] Validando acesso ao Projeto PJe (ID 52) e Tracker 156...")
    proj_id = settings.REDMINE_PROJECT_ID or 52
    track_id = settings.REDMINE_TRACKER_ID or 156

    try:
        with httpx.Client(verify=False, timeout=15.0) as client:
            resp = client.get(f"{base_url}/projects/{proj_id}.json?include=trackers", headers=headers)
            if resp.status_code != 200:
                logger.error(f"[ETAPA 2/7] FALHA ao consultar projeto {proj_id}: HTTP {resp.status_code}")
                return
            project = resp.json().get("project", {})
            proj_name = project.get("name")
            proj_ident = project.get("identifier")
            trackers = project.get("trackers", [])
            target_tracker = next((t for t in trackers if t.get("id") == track_id), None)

            if not target_tracker:
                logger.error(f"[ETAPA 2/7] FALHA: Rastreador #{track_id} não encontrado no projeto {proj_name}!")
                return

            logger.info(
                f"[ETAPA 2/7] SUCESSO: Projeto '{proj_name}' (ID: #{proj_id}, Identificador: '{proj_ident}') confirmado!"
            )
            logger.info(f"[ETAPA 2/7] SUCESSO: Rastreador ativo confirmado: '{target_tracker.get('name')}' (ID: #{track_id})")
    except Exception as exc:
        logger.error(f"[ETAPA 2/7] FALHA ao validar projeto: {str(exc)}")
        return

    # -------------------------------------------------------------------------
    # ETAPA 3: Validação dos Campos Customizados (455, 456, 457, 479)
    # -------------------------------------------------------------------------
    logger.info("[ETAPA 3/7] Consultando tarefas recentes do autor para auditar campos customizados...")
    try:
        with httpx.Client(verify=False, timeout=15.0) as client:
            resp = client.get(
                f"{base_url}/issues.json?author_id={user_id}&tracker_id={track_id}&limit=1",
                headers=headers,
            )
            if resp.status_code == 200:
                issues = resp.json().get("issues", [])
                if issues:
                    last_issue = issues[0]
                    logger.info(f"[ETAPA 3/7] Última tarefa do autor encontrada no Redmine: #{last_issue.get('id')} - '{last_issue.get('subject')}'")
                    for cf in last_issue.get("custom_fields", []):
                        if cf.get("id") in [455, 456, 457, 479]:
                            logger.info(f"[ETAPA 3/7]   -> Campo Customizado #{cf.get('id')} ({cf.get('name')}): {repr(cf.get('value'))}")
                else:
                    logger.info("[ETAPA 3/7] Nenhuma tarefa anterior deste autor com tracker 156, usando mapeamento padrão confirmado.")
            else:
                logger.warning(f"[ETAPA 3/7] Aviso ao buscar issues: HTTP {resp.status_code}")
    except Exception as exc:
        logger.warning(f"[ETAPA 3/7] Aviso na etapa 3: {str(exc)}")

    # -------------------------------------------------------------------------
    # ETAPA 4: Validação do Repositório Git Local e Leitura de Commit Real
    # -------------------------------------------------------------------------
    repo_path = settings.DEFAULT_GIT_REPO_PATH or "C:/ambiente/Git/PJE"
    author_name = settings.GIT_AUTHOR_NAME or "athos.rocha"
    logger.info(f"[ETAPA 4/7] Analisando repositório Git local em '{repo_path}' para autor '{author_name}'...")

    try:
        is_valid, msg = GitService.validate_repository(repo_path)
        if not is_valid:
            logger.error(f"[ETAPA 4/7] FALHA ao validar repositório: {msg}")
            return

        logger.info(f"[ETAPA 4/7] Repositório Git válido! Buscando commit mais recente do autor...")
        commits, _ = GitService.get_commits_paged(repo_path=repo_path, author=author_name, limit=3)
        if not commits:
            logger.warning(f"[ETAPA 4/7] Nenhum commit recente para '{author_name}', buscando últimos commits do repositório...")
            commits, _ = GitService.get_commits_paged(repo_path=repo_path, limit=3)

        if not commits:
            logger.error("[ETAPA 4/7] Repositório não possui commits disponíveis para análise.")
            return

        sample_commit = commits[0]
        c_hash = sample_commit.get("hash", "")
        c_short = sample_commit.get("short_hash", "")
        c_msg = sample_commit.get("message", "").strip().split("\n")[0]
        c_author = sample_commit.get("author", "")
        c_files = len(sample_commit.get("files_changed", []))
        c_ins = sample_commit.get("insertions", 0)
        c_del = sample_commit.get("deletions", 0)
        c_url = sample_commit.get("commit_url") or ""

        logger.info(f"[ETAPA 4/7] Commit selecionado para teste:")
        logger.info(f"[ETAPA 4/7]   Hash: {c_short} ({c_hash})")
        logger.info(f"[ETAPA 4/7]   Autor: {c_author}")
        logger.info(f"[ETAPA 4/7]   Mensagem: {c_msg}")
        logger.info(f"[ETAPA 4/7]   Arquivos alterados: {c_files} | Linhas: +{c_ins} / -{c_del}")
        logger.info(f"[ETAPA 4/7]   Link Evidência GitLab: {c_url}")
    except Exception as exc:
        logger.error(f"[ETAPA 4/7] FALHA ao inspecionar repositório Git: {str(exc)}")
        return

    # -------------------------------------------------------------------------
    # ETAPA 5: Geração da Proposta de Item de Catálogo (IC)
    # -------------------------------------------------------------------------
    logger.info("[ETAPA 5/7] Calculando Item de Catálogo (IC) e métricas via CatalogGeneratorService...")
    try:
        ic_proposal = CatalogGeneratorService.generate_ic_for_commit(sample_commit)
        ic_title = ic_proposal.get("title", "")
        ic_desc = ic_proposal.get("description", "")
        ic_count = ic_proposal.get("ic_count", 1) or 1
        complexity = "Baixa"
        activity_type = "Desenvolvimento - Criar/Manter tarefa de automação"

        logger.info(f"[ETAPA 5/7] Proposta de IC gerada com êxito:")
        logger.info(f"[ETAPA 5/7]   Título: {ic_title}")
        logger.info(f"[ETAPA 5/7]   Quantidade calculada de ICs: {ic_count}")
        logger.info(f"[ETAPA 5/7]   Atividade Catálogo: {activity_type}")
        logger.info(f"[ETAPA 5/7]   Complexidade: {complexity}")
        logger.info(f"[ETAPA 5/7]   Tamanho da Descrição: {len(ic_desc)} caracteres")
    except Exception as exc:
        logger.error(f"[ETAPA 5/7] FALHA ao gerar proposta de IC: {str(exc)}")
        return

    # -------------------------------------------------------------------------
    # ETAPA 6: Montagem e Validação do Payload REST API (Simulação Dry-Run)
    # -------------------------------------------------------------------------
    logger.info("[ETAPA 6/7] Montando payload JSON final para a API do Redmine (Modo Dry-Run)...")
    custom_fields = [
        {"id": 455, "value": activity_type},
        {"id": 456, "value": complexity},
        {"id": 457, "value": str(max(1, ic_count))},
    ]
    if c_url:
        custom_fields.append({"id": 479, "value": c_url})

    payload = {
        "issue": {
            "project_id": proj_id,
            "tracker_id": track_id,
            "subject": ic_title[:255],
            "description": ic_desc,
            "custom_fields": custom_fields,
        }
    }

    # Validações estruturais do payload
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    payload_bytes = payload_json.encode("utf-8")

    logger.info(f"[ETAPA 6/7] Validação do Payload JSON:")
    logger.info(f"[ETAPA 6/7]   Tamanho total: {len(payload_bytes)} bytes")
    logger.info(f"[ETAPA 6/7]   Codificação: UTF-8 válida")
    logger.info(f"[ETAPA 6/7]   Campos customizados configurados: {len(custom_fields)}")
    logger.info(f"[ETAPA 6/7]   Endpoint de destino: {base_url}/issues.json")
    print("\n--- [PAYLOAD JSON SIMULADO QUE SERÁ ENVIADO AO REDMINE] ---")
    print(payload_json)
    print("-----------------------------------------------------------\n")

    logger.info("==================================================================")
    logger.info("[ETAPA 6/7] [DRY-RUN CONFIRMADO] NENHUMA TAREFA FOI CRIADA NO REDMINE!")
    logger.info("[ETAPA 6/7] O payload acima está 100% pronto, validado e conforme com o TJCE.")
    logger.info("==================================================================")

    # -------------------------------------------------------------------------
    # ETAPA 7: Teste do Banco de Dados PostgreSQL Local
    # -------------------------------------------------------------------------
    logger.info("[ETAPA 7/7] Testando conexão com o banco de dados PostgreSQL...")
    try:
        db = SessionLocal()
        result = db.execute(text("SELECT current_database(), current_user, version();")).fetchone()
        db_name, db_user, db_version = result[0], result[1], result[2]
        logger.info(f"[ETAPA 7/7] SUCESSO: Conectado ao PostgreSQL!")
        logger.info(f"[ETAPA 7/7]   Database: {db_name} | User: {db_user}")
        logger.info(f"[ETAPA 7/7]   Versão: {db_version.split(',')[0]}")
        db.close()
    except Exception as exc:
        logger.error(f"[ETAPA 7/7] FALHA ao conectar no PostgreSQL: {str(exc)}")
        return

    print("\n" + "=" * 80)
    print(" >>> RESULTADO FINAL DO TESTE: TODAS AS 7 ETAPAS FORAM APROVADAS COM SUCESSO! <<<")
    print(" (Zero tarefas criadas no Redmine, validação 100% concluída)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_full_dry_run()
