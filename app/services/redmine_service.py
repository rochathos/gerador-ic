from typing import Optional, Tuple
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.core.selectors import RedmineSelectors
from app.core.logger import logger
from app.models.catalog_item import CatalogItem


class RedmineService:
    """Automates Redmine Catalog Item creation via Selenium.

    Prepared for Phase 3 automation.
    """

    def __init__(self, driver: WebDriver, base_url: str):
        self.driver = driver
        self.base_url = base_url.rstrip("/")
        self.wait = WebDriverWait(driver, 15)

    def login(self, username: str, password: str) -> bool:
        """Authenticate into Redmine."""
        logger.info(f"Realizando login no Redmine: {self.base_url}/login")
        self.driver.get(f"{self.base_url}/login")

        try:
            user_field = self.wait.until(EC.visibility_of_element_located(RedmineSelectors.LOGIN_USERNAME_INPUT))
            pass_field = self.driver.find_element(*RedmineSelectors.LOGIN_PASSWORD_INPUT)
            submit_btn = self.driver.find_element(*RedmineSelectors.LOGIN_SUBMIT_BUTTON)

            user_field.clear()
            user_field.send_keys(username)
            pass_field.clear()
            pass_field.send_keys(password)
            submit_btn.click()

            self.wait.until(EC.presence_of_element_located(RedmineSelectors.LOGGED_IN_USER_INDICATOR))
            logger.info("Login no Redmine realizado com sucesso.")
            return True
        except Exception as exc:
            logger.error(f"Falha na autenticação do Redmine: {exc}")
            return False

    def create_catalog_item(self, item: CatalogItem, project_id: str = "default") -> Tuple[bool, Optional[str]]:
        """Fill and submit a Catalog Item form in Redmine."""
        logger.info(f"Criando Item de Catálogo: '{item.title}'")
        url = f"{self.base_url}/projects/{project_id}/issues/new"
        self.driver.get(url)

        try:
            subject_input = self.wait.until(EC.visibility_of_element_located(RedmineSelectors.SUBJECT_INPUT))
            subject_input.clear()
            subject_input.send_keys(item.title)

            desc_textarea = self.driver.find_element(*RedmineSelectors.DESCRIPTION_TEXTAREA)
            desc_textarea.clear()
            desc_textarea.send_keys(item.description)

            submit_btn = self.driver.find_element(*RedmineSelectors.SUBMIT_BUTTON)
            submit_btn.click()

            self.wait.until(EC.presence_of_element_located(RedmineSelectors.FLASH_NOTICE))
            logger.info(f"Item de Catálogo criado com sucesso: {item.title}")
            return True, "ID_PLACEHOLDER"
        except Exception as exc:
            logger.error(f"Falha ao criar Item de Catálogo no Redmine: {exc}")
            return False, None
