from typing import Optional
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from app.core.config import settings
from app.core.logger import logger


class SeleniumService:
    """Manages ChromeDriver lifecycle and browser automation settings.

    Prepared for Phase 3 Redmine automation.
    """

    def __init__(self, profile_path: Optional[str] = None, headless: bool = False):
        self.profile_path = profile_path or settings.CHROME_PROFILE_PATH
        self.headless = headless or settings.CHROME_HEADLESS
        self.driver: Optional[webdriver.Chrome] = None

    def start_driver(self) -> webdriver.Chrome:
        """Initialize and configure Chrome WebDriver."""
        logger.info("Inicializando ChromeDriver para automação...")
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--start-maximized")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        if self.profile_path:
            profile_dir = Path(self.profile_path).resolve()
            if profile_dir.exists():
                logger.info(f"Utilizando perfil do usuário do Chrome: {profile_dir}")
                options.add_argument(f"--user-data-dir={profile_dir}")

        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            logger.info("ChromeDriver inicializado com sucesso.")
            return self.driver
        except Exception as exc:
            logger.error(f"Falha ao iniciar ChromeDriver: {exc}")
            raise

    def stop_driver(self) -> None:
        """Safely close and quit WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("ChromeDriver encerrado com sucesso.")
            except Exception as exc:
                logger.warning(f"Erro ao encerrar ChromeDriver: {exc}")
            finally:
                self.driver = None
