import json
import random
from typing import Optional, Tuple, Dict, Any, List
import httpx
import urllib3

from app.core.config import settings
from app.core.logger import logger
from app.models.catalog_item import CatalogItem

# Suppress SSL warnings if self-signed or internal TJCE certs are encountered
urllib3.disable_warnings()


class RedmineService:
    """Automates Redmine Catalog Item creation via official REST API and Selenium."""

    @classmethod
    def get_headers(cls, api_key: Optional[str] = None) -> Dict[str, str]:
        """Construct standard HTTP headers with Redmine API Key."""
        key = api_key or settings.REDMINE_API_KEY
        return {
            "X-Redmine-API-Key": key or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @classmethod
    def test_connection(cls, api_key: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Validate connection and API Key with Redmine.
        
        Returns:
            Tuple of (success, message, user_data_dict)
        """
        base_url = settings.REDMINE_URL.rstrip("/")
        key = api_key or settings.REDMINE_API_KEY

        logger.info("[REDMINE API] [PASSO 1/2] Testando conexão com a API do Redmine...")
        if not key:
            msg = "Chave de API do Redmine não configurada (REDMINE_API_KEY ausente)."
            logger.error(f"[REDMINE API] {msg}")
            return False, msg, None

        logger.info(f"[REDMINE API] [PASSO 2/2] Consultando usuário atual em {base_url}/users/current.json")
        try:
            with httpx.Client(verify=False, timeout=10.0) as client:
                resp = client.get(f"{base_url}/users/current.json", headers=cls.get_headers(key))
                if resp.status_code == 200:
                    data = resp.json().get("user", {})
                    user_name = f"{data.get('firstname', '')} {data.get('lastname', '')}".strip()
                    user_id = data.get("id")
                    logger.info(
                        f"[REDMINE API] Autenticação bem-sucedida! Usuário: '{user_name}' (ID: #{user_id}, Login: {data.get('login')})"
                    )
                    return True, f"Autenticado com sucesso como '{user_name}' (#{user_id})", data
                else:
                    msg = f"Falha na autenticação da API (HTTP {resp.status_code}): {resp.text}"
                    logger.error(f"[REDMINE API] {msg}")
                    return False, msg, None
        except Exception as exc:
            msg = f"Erro de rede ao conectar no Redmine: {str(exc)}"
            logger.error(f"[REDMINE API] {msg}")
            return False, msg, None

    @classmethod
    def format_description_for_redmine(cls, text: str) -> str:
        """Format description to ensure line breaks and lists are rendered cleanly in Redmine Textile/Markdown."""
        if not text:
            return ""
        raw_lines = text.replace("\r\n", "\n").split("\n")
        processed_lines: List[str] = []
        for line in raw_lines:
            stripped_left = line.lstrip()
            # Convert legacy indented tag bullets into Redmine Textile nested bullets
            if stripped_left.startswith("* <") or stripped_left.startswith("* &lt;"):
                processed_lines.append(f"*** {stripped_left[2:]}")
            elif stripped_left.startswith("* Tags ") or stripped_left.startswith("* Tags:"):
                processed_lines.append(f"** {stripped_left[2:]}")
            elif stripped_left.startswith("* Casos de Uso"):
                processed_lines.append(f"** {stripped_left[2:]}")
            elif line.startswith("- [XML]") or line.startswith("* [XML]"):
                processed_lines.append(f"* [XML]{line[7:]}")
            elif line.startswith("- [SQL]") or line.startswith("* [SQL]"):
                processed_lines.append(f"* [SQL]{line[7:]}")
            elif line.startswith("- ") and not line.startswith("- -"):
                processed_lines.append(f"* {line[2:]}")
            else:
                processed_lines.append(line)
        return "\n".join(processed_lines)

    @classmethod
    def create_catalog_item_api(
        cls,
        title: str,
        description: str,
        commit_hash: Optional[str] = None,
        commit_url: Optional[str] = None,
        ic_count: int = 1,
        activity_type: str = "Desenvolvimento - Criar/Manter tarefa de automação",
        complexity: str = "Baixa",
        project_id: Optional[int] = None,
        tracker_id: Optional[int] = None,
        api_key: Optional[str] = None,
        dry_run: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[int], List[str]]:
        """Create a new Catalog Item (IC) in Redmine via REST API with granular step-by-step logging.

        Args:
            dry_run: If True, executes all validations, project checks, and payload construction
                     WITHOUT sending the final issue creation HTTP request.

        Returns:
            Tuple of (success: bool, web_url: Optional[str], issue_id: Optional[int], logs: List[str])
        """
        step_logs: List[str] = []

        def log_step(msg: str, is_error: bool = False):
            formatted = f"[REDMINE API] {msg}"
            step_logs.append(msg)
            if is_error:
                logger.error(formatted)
            else:
                logger.info(formatted)

        base_url = settings.REDMINE_URL.rstrip("/")
        key = api_key or getattr(settings, "REDMINE_API_KEY", None)
        proj_id = project_id or getattr(settings, "REDMINE_PROJECT_ID", 52) or 52
        track_id = tracker_id or getattr(settings, "REDMINE_TRACKER_ID", 156) or 156

        # PASSO 1
        mode_label = "SIMULAÇÃO (DRY-RUN)" if dry_run else "CRIAÇÃO OFICIAL"
        log_step(f"[PASSO 1/6] Iniciando processo de {mode_label} de IC no Redmine ({base_url})")
        if not key:
            log_step("[PASSO 1/6] FALHA: REDMINE_API_KEY não informada no sistema.", is_error=True)
            return False, None, None, step_logs

        # PASSO 2
        log_step("[PASSO 2/6] Validando autenticidade da chave e consultando perfil do usuário...")
        try:
            with httpx.Client(verify=False, timeout=12.0) as client:
                r_user = client.get(f"{base_url}/users/current.json", headers=cls.get_headers(key))
                if r_user.status_code != 200:
                    if dry_run:
                        log_step(f"[PASSO 2/6] [SIMULAÇÃO] Servidor Redmine respondeu HTTP {r_user.status_code}. Prosseguindo com validação local da simulação...")
                    else:
                        log_step(f"[PASSO 2/6] FALHA: Chave de API inválida ou rejeitada pelo servidor (HTTP {r_user.status_code}).", is_error=True)
                        return False, None, None, step_logs
                else:
                    user_info = r_user.json().get("user", {})
                    author_name = f"{user_info.get('firstname', '')} {user_info.get('lastname', '')}".strip()
                    log_step(f"[PASSO 2/6] Autenticado com sucesso como autor: {author_name} (ID: #{user_info.get('id')})")
        except Exception as exc:
            if dry_run:
                log_step(f"[PASSO 2/6] [SIMULAÇÃO] Servidor Redmine TJCE indisponível sem VPN ({str(exc)[:50]}). Prosseguindo com validação local da simulação...")
            else:
                log_step(f"[PASSO 2/6] FALHA: Erro de conexão ao validar usuário: {str(exc)}", is_error=True)
                return False, None, None, step_logs

        # PASSO 3
        log_step(f"[PASSO 3/6] Validando destino no Redmine: Projeto ID={proj_id} (PJe) e Tracker ID={track_id} (Item Catálogo PJE)...")
        try:
            with httpx.Client(verify=False, timeout=12.0) as client:
                r_proj = client.get(f"{base_url}/projects/{proj_id}.json?include=trackers", headers=cls.get_headers(key))
                if r_proj.status_code == 200:
                    p_data = r_proj.json().get("project", {})
                    p_name = p_data.get("name", "PJe")
                    trackers = p_data.get("trackers", [])
                    t_target = next((t for t in trackers if t.get("id") == track_id), None)
                    t_name = t_target.get("name") if t_target else "Item Catálogo PJE"
                    log_step(f"[PASSO 3/6] Destino validado: Projeto '{p_name}' (#{proj_id}) | Rastreador ativo: '{t_name}' (#{track_id})")
                else:
                    log_step(f"[PASSO 3/6] Projeto #{proj_id} respondeu HTTP {r_proj.status_code}, mantendo configuração padrão.")
        except Exception as exc:
            log_step(f"[PASSO 3/6] Aviso na checagem do projeto: {str(exc)}")

        # PASSO 4
        log_step("[PASSO 4/6] Montando payload da tarefa e configurando campos customizados do PJe TJCE:")
        log_step(f"[PASSO 4/6]   -> Atividade (455): '{activity_type}'")
        log_step(f"[PASSO 4/6]   -> Complexidade (456): '{complexity}'")
        log_step(f"[PASSO 4/6]   -> Quantidade ICs (457): '{ic_count}'")

        custom_fields: List[Dict[str, Any]] = [
            # [DEVPJE] - Atividade Catálogo (id=455)
            {"id": 455, "value": activity_type},
            # [DEVPJE] Complexidade (id=456)
            {"id": 456, "value": complexity},
            # [DEVPJE] - Quantidade (id=457)
            {"id": 457, "value": str(max(1, ic_count))},
        ]

        if commit_url:
            custom_fields.append({"id": 479, "value": commit_url})
            log_step(f"[PASSO 4/6]   -> Link Nota Evidência (479): '{commit_url}'")

        formatted_desc = cls.format_description_for_redmine(description)
        payload = {
            "issue": {
                "project_id": proj_id,
                "tracker_id": track_id,
                "subject": title[:255] if title else "Item de Catálogo",
                "description": formatted_desc,
                "custom_fields": custom_fields,
            }
        }
        log_step(f"[PASSO 4/6] Payload estruturado com sucesso: Título='{title[:60]}...'")

        # PASSO 5 & 6
        if dry_run:
            log_step("[PASSO 5/6] [MODO SIMULAÇÃO ATIVO] Validando estrutura, codificação UTF-8 e tamanho do JSON...")
            payload_json = json.dumps(payload, ensure_ascii=False)
            payload_bytes = payload_json.encode("utf-8")
            log_step(f"[PASSO 5/6] Payload JSON validado com sucesso! Tamanho: {len(payload_bytes)} bytes.")
            fake_issue_id = str(random.randint(990000, 999999))
            fake_issue_url = f"{base_url}/issues/{fake_issue_id}"
            log_step(f"[PASSO 6/6] [SIMULAÇÃO BEM-SUCEDIDA] Número simulado do Redmine gerado: #{fake_issue_id}")
            log_step(f"[PASSO 6/6] Nenhuma tarefa real foi criada no Redmine. IC pronto para persistência no banco!")
            return True, fake_issue_url, fake_issue_id, step_logs

        endpoint_url = f"{base_url}/issues.json"
        log_step(f"[PASSO 5/6] Enviando requisição HTTP POST para {endpoint_url}...")
        try:
            with httpx.Client(verify=False, timeout=20.0) as client:
                resp = client.post(
                    endpoint_url,
                    headers=cls.get_headers(key),
                    content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                )

                # PASSO 6
                log_step(f"[PASSO 6/6] Resposta recebida do servidor Redmine: HTTP {resp.status_code}")
                if resp.status_code in (200, 201):
                    created_issue = resp.json().get("issue", {})
                    issue_id = created_issue.get("id")
                    issue_url = f"{base_url}/issues/{issue_id}"
                    log_step(f"[PASSO 6/6] SUCESSO ABSOLUTO! Tarefa #{issue_id} criada com êxito!")
                    log_step(f"[PASSO 6/6] Link direto da tarefa: {issue_url}")
                    return True, issue_url, issue_id, step_logs
                else:
                    error_text = resp.text
                    try:
                        err_json = resp.json()
                        if "errors" in err_json:
                            error_text = ", ".join(err_json["errors"])
                    except Exception:
                        pass
                    log_step(f"[PASSO 6/6] FALHA ao criar tarefa no Redmine (HTTP {resp.status_code}): {error_text}", is_error=True)
                    return False, None, None, step_logs
        except Exception as exc:
            log_step(f"[PASSO 5/6] FALHA: Exceção durante requisição HTTP para o Redmine: {str(exc)}", is_error=True)
            return False, None, None, step_logs
