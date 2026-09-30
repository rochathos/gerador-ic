import sys
from loguru import logger
from app.core.config import settings

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

__all__ = ["logger"]
