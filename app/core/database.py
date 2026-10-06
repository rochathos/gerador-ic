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


def assegurar_banco_de_dados_existe() -> None:
    """Verifica se o banco de dados configurado existe no servidor PostgreSQL.
    Caso não exista, conecta ao banco padrão 'postgres' e executa o CREATE DATABASE automaticamente.
    """
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    from urllib.parse import urlparse

    db_name = settings.DB_NAME
    host = settings.DB_HOST
    port = settings.DB_PORT
    user = settings.DB_USER
    password = settings.DB_PASSWORD

    if settings.DATABASE_URL:
        try:
            url = urlparse(settings.DATABASE_URL)
            db_name = url.path.lstrip("/") or db_name
            host = url.hostname or host
            port = url.port or port
            user = url.username or user
            password = url.password or password
        except Exception as parse_err:
            logger.debug(f"Falha ao extrair parâmetros de DATABASE_URL: {parse_err}")

    if not db_name:
        return

    conn = None
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname="postgres",
            connect_timeout=5,
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
            if not cur.fetchone():
                logger.info(f"Banco de dados '{db_name}' não encontrado no PostgreSQL. Criando automaticamente...")
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
                logger.info(f"Banco de dados '{db_name}' criado com sucesso no PostgreSQL!")
            else:
                logger.debug(f"Banco de dados '{db_name}' já existe no PostgreSQL.")
    except Exception as exc:
        logger.warning(
            f"Não foi possível verificar/criar o banco de dados '{db_name}' automaticamente via banco 'postgres': {exc}. "
            "Tentando conectar diretamente ao banco alvo..."
        )
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def init_db() -> None:
    """Initialize database and tables."""
    try:
        # Garante a existência do banco de dados antes de criar tabelas
        assegurar_banco_de_dados_existe()

        logger.info("Verificando e inicializando tabelas do banco de dados PostgreSQL...")
        # Import all models to ensure they are registered with Base.metadata
        import app.models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE commits ADD COLUMN IF NOT EXISTS branch VARCHAR(255);"))
                conn.execute(text("ALTER TABLE commits ADD COLUMN IF NOT EXISTS sql_scripts_metrics JSON;"))
                conn.execute(text("ALTER TABLE commits ADD COLUMN IF NOT EXISTS ic_count_xml INTEGER DEFAULT 0;"))
                conn.execute(text("ALTER TABLE commits ADD COLUMN IF NOT EXISTS ic_count_sql INTEGER DEFAULT 0;"))
                conn.execute(text("ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS natureza VARCHAR(50);"))
                conn.execute(text("ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS activity_type VARCHAR(255);"))
                conn.execute(text("ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS ic_count INTEGER DEFAULT 1;"))
                conn.commit()
        except Exception as col_err:
            logger.debug(f"Verificação de colunas de banco: {col_err}")
        logger.info("Tabelas do PostgreSQL verificadas/criadas com sucesso.")
    except Exception as exc:
        logger.error(f"Erro ao inicializar tabelas no PostgreSQL: {exc}")
        raise

