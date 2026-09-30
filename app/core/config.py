from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Productivity Assistant configuration settings loaded from environment/.env."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
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
    DEFAULT_GIT_REPO_PATH: str = "C:/ambiente/Git/PJE"
    DEFAULT_REPO_PATH: str = "C:/ambiente/Git/PJE"
    GIT_AUTHOR_NAME: Optional[str] = "athos.rocha"
    GIT_AUTHOR_EMAIL: Optional[str] = "athosrocha123@gmail.com"

    # Redmine Config (Corporate)
    REDMINE_URL: str = "https://redmine.corporativo.local"
    REDMINE_USERNAME: Optional[str] = None
    REDMINE_PASSWORD: Optional[str] = None

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
