from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.core.logger import logger
from app.dashboard.routes import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown lifecycle events."""
    logger.info("==================================================================")
    logger.info(f"Iniciando {settings.APP_NAME} (v1.0.0)")
    logger.info(f"Ambiente: {settings.APP_ENV} | Debug: {settings.APP_DEBUG}")
    logger.info(f"Acesse localmente em: http://{settings.APP_HOST}:{settings.APP_PORT}")
    logger.info("==================================================================")

    # Initialize PostgreSQL tables
    init_db()

    yield

    logger.info(f"Encerrando {settings.APP_NAME}...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Sistema automatizado de levantamento de atividades e geração de Itens de Catálogo (IC) no Redmine.",
    version="1.0.0",
    docs_url="/docs" if settings.APP_DEBUG else None,
    redoc_url="/redoc" if settings.APP_DEBUG else None,
    lifespan=lifespan,
)

# Enable CORS for Microsoft Teams Web and local integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_private_network_access_headers(request, call_next):
    """Handle Chrome Private Network Access (PNA) preflight and response headers."""
    from starlette.responses import Response

    if request.method == "OPTIONS":
        response = Response(status_code=204)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

import sys
import threading
import webbrowser


def obter_diretorio_estaticos() -> Path:
    """Retorna o diretório de arquivos estáticos tanto em ambiente de desenvolvimento quanto compilado."""
    if hasattr(sys, "_MEIPASS"):
        candidato_meipass = Path(sys._MEIPASS) / "app" / "dashboard" / "static"
        if candidato_meipass.exists():
            return candidato_meipass
    caminho_local = Path(__file__).resolve().parent / "app" / "dashboard" / "static"
    if caminho_local.exists():
        return caminho_local
    caminho_base = settings.BASE_DIR / "app" / "dashboard" / "static"
    if caminho_base.exists():
        return caminho_base
    return caminho_local


# Mount static files
static_dir = obter_diretorio_estaticos()
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include dashboard and API routes
app.include_router(dashboard_router)


def abrir_navegador_ao_iniciar(url: str, atraso_segundos: float = 1.5) -> None:
    """Abre o navegador padrão automaticamente após a inicialização do servidor."""
    def _abrir():
        try:
            webbrowser.open(url)
        except Exception as erro:
            logger.warning(f"Não foi possível abrir o navegador automaticamente: {erro}")

    temporizador = threading.Timer(atraso_segundos, _abrir)
    temporizador.daemon = True
    temporizador.start()


if __name__ == "__main__":
    eh_compilado = hasattr(sys, "frozen") or hasattr(sys, "__compiled__") or "__compiled__" in globals()
    url_aplicacao = f"http://{settings.APP_HOST}:{settings.APP_PORT}"

    # Dispara abertura automática do navegador
    abrir_navegador_ao_iniciar(url_aplicacao)

    if eh_compilado:
        # Em modo executável compilado, passa a instância do app diretamente e desativa reload
        uvicorn.run(
            app,
            host=settings.APP_HOST,
            port=settings.APP_PORT,
            reload=False,
            log_level="info",
        )
    else:
        uvicorn.run(
            "main:app",
            host=settings.APP_HOST,
            port=settings.APP_PORT,
            reload=settings.APP_DEBUG,
        )
