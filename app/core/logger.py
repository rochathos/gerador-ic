import re
import sys
from loguru import logger
from app.core.config import settings


def _mascarar_segredos(record: dict) -> None:
    """Sanitiza mensagens de log para mascarar tokens e chaves sensíveis."""
    msg = str(record["message"])
    if "glpat-" in msg:
        msg = re.sub(r"glpat-[a-zA-Z0-9_\-]+", "glpat-***[MASKED]***", msg)
    if settings.GIT_ACCESS_TOKEN and settings.GIT_ACCESS_TOKEN in msg:
        msg = msg.replace(settings.GIT_ACCESS_TOKEN, "glpat-***[MASKED]***")
    if settings.REDMINE_API_KEY and settings.REDMINE_API_KEY in msg:
        msg = msg.replace(settings.REDMINE_API_KEY, "***[REDMINE_KEY_MASKED]***")
    record["message"] = msg


# Remove default handler
logger.remove()

# Console logger with rich colors
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.LOG_LEVEL,
)

# File logger with rotation and retention
logger.add(
    settings.LOG_FILE,
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level=settings.LOG_LEVEL,
    enqueue=True,
)

# Apply global masking patch
logger = logger.patch(_mascarar_segredos)

__all__ = ["logger"]
