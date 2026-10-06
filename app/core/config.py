import sys
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


def obter_diretorio_base() -> Path:
    """Retorna o diretório base da aplicação considerando execução em código-fonte ou executável compilado."""
    if hasattr(sys, "frozen") or "__compiled__" in globals() or hasattr(sys, "__compiled__"):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = obter_diretorio_base()


def obter_caminho_arquivo_env() -> str:
    """Localiza o arquivo .env no diretório de execução atual ou no diretório base."""
    candidato_local = Path.cwd() / ".env"
    if candidato_local.exists():
        return str(candidato_local)
    candidato_base = BASE_DIR / ".env"
    if candidato_base.exists():
        return str(candidato_base)
    return str(candidato_base)


class Settings(BaseSettings):
    """Productivity Assistant configuration settings loaded from environment/.env."""

    model_config = SettingsConfigDict(
        env_file=obter_caminho_arquivo_env(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General App Config
    APP_NAME: str = "Productivity Assistant"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000

    # PostgreSQL Database Config
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "12345"
    DB_NAME: str = "productivity_assistant"
    DATABASE_URL: Optional[str] = None

    # Git Config
    DEFAULT_GIT_REPO_PATH: str = str(BASE_DIR)
    DEFAULT_REPO_PATH: Optional[str] = None
    DEFAULT_REPO_NAME: Optional[str] = "PJE"
    GIT_AUTHOR_NAME: Optional[str] = "athos.rocha"
    GIT_AUTHOR_EMAIL: Optional[str] = "athosrocha123@gmail.com"

    # Redmine Config (Corporate)
    REDMINE_URL: str = "https://redmine.corporativo.local"
    REDMINE_API_KEY: Optional[str] = None
    REDMINE_PROJECT_ID: Optional[int] = 52
    REDMINE_TRACKER_ID: Optional[int] = 156
    REDMINE_USERNAME: Optional[str] = None
    REDMINE_PASSWORD: Optional[str] = None

    def model_post_init(self, __context: object) -> None:
        if not self.DEFAULT_REPO_PATH:
            self.DEFAULT_REPO_PATH = self.DEFAULT_GIT_REPO_PATH

    # Chrome / Selenium Config
    CHROME_PROFILE_PATH: Optional[str] = None
    CHROME_HEADLESS: bool = False

    # Directories
    BASE_DIR: Path = BASE_DIR
    SCREENSHOTS_DIR: Path = BASE_DIR / "screenshots"
    REPORTS_DIR: Path = BASE_DIR / "reports"
    LOGS_DIR: Path = BASE_DIR / "logs"
    LOG_FILE: Path = BASE_DIR / "logs" / "app.log"
    LOG_LEVEL: str = "INFO"

    @property
    def sync_database_url(self) -> str:
        """Construct the SQLAlchemy synchronous database URL."""
        if self.DATABASE_URL:
            # Ensure correct dialect prefix
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()

# Ensure directories exist
settings.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
