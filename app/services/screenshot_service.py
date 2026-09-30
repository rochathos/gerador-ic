from datetime import datetime
from pathlib import Path
from typing import Optional
from selenium.webdriver.remote.webdriver import WebDriver
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logger import logger
from app.models.evidence import Evidence


class ScreenshotService:
    """Captures and stores visual evidence of Catalog Item creation."""

    @classmethod
    def capture_screenshot(
        cls,
        driver: WebDriver,
        step_name: str,
        catalog_item_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> Optional[Evidence]:
        """Capture screenshot from Selenium WebDriver and save to disk + database."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_step = step_name.lower().replace(" ", "_")
        filename = f"ic_{catalog_item_id or 'general'}_{clean_step}_{timestamp}.png"
        filepath = settings.SCREENSHOTS_DIR / filename

        try:
            settings.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            driver.save_screenshot(str(filepath))
            logger.info(f"Evidência capturada e salva em: {filepath}")

            if db:
                evidence = Evidence(
                    filename=filename,
                    filepath=str(filepath),
                    catalog_item_id=catalog_item_id,
                )
                db.add(evidence)
                db.commit()
                db.refresh(evidence)
                return evidence
            return None
        except Exception as exc:
            logger.error(f"Erro ao capturar screenshot '{filename}': {exc}")
            return None
