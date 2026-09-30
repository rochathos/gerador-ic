from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings
from app.core.logger import logger

# Create SQLAlchemy engine with pool pre-ping to handle disconnected sockets
engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and handles rollback/close."""
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        logger.error(f"Falha de banco de dados na sessão ativa: {exc}")
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables."""
    try:
        logger.info("Verificando e inicializando tabelas do banco de dados PostgreSQL...")
        # Import all models to ensure they are registered with Base.metadata
        import app.models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Tabelas do PostgreSQL verificadas/criadas com sucesso.")
    except Exception as exc:
        logger.error(f"Erro ao inicializar tabelas no PostgreSQL: {exc}")
        raise
