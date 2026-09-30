"""Centralized selectors for Redmine automation via Selenium.

Centralizing all CSS and XPath selectors prevents duplication and makes updates
straightforward when UI changes occur.
"""
from selenium.webdriver.common.by import By


class RedmineSelectors:
    """Selectors for Redmine web interface."""

    # Authentication
    LOGIN_USERNAME_INPUT = (By.ID, "username")
    LOGIN_PASSWORD_INPUT = (By.ID, "password")
    LOGIN_SUBMIT_BUTTON = (By.NAME, "login")
    LOGGED_IN_USER_INDICATOR = (By.ID, "loggedas")
    LOGIN_ERROR_FLASH = (By.ID, "flash_error")

    # Navigation & Project
    PROJECT_MENU_LINK = (By.CSS_SELECTOR, "a.projects")
    NEW_ISSUE_TAB_LINK = (By.CSS_SELECTOR, "a.new-issue")
    ISSUES_LIST_LINK = (By.CSS_SELECTOR, "a.issues")

    # Issue / Catalog Item Creation Form
    TRACKER_SELECT = (By.ID, "issue_tracker_id")
    SUBJECT_INPUT = (By.ID, "issue_subject")
    DESCRIPTION_TEXTAREA = (By.ID, "issue_description")
    STATUS_SELECT = (By.ID, "issue_status_id")
    PRIORITY_SELECT = (By.ID, "issue_priority_id")
    ASSIGNED_TO_SELECT = (By.ID, "issue_assigned_to_id")
    CATEGORY_SELECT = (By.ID, "issue_category_id")
    SUBMIT_BUTTON = (By.CSS_SELECTOR, "input[name='commit']")
    CONTINUE_BUTTON = (By.CSS_SELECTOR, "input[name='continue']")

    # Success & Created Item Elements
    FLASH_NOTICE = (By.ID, "flash_notice")
    ISSUE_HEADING = (By.CSS_SELECTOR, "div.issue h2, h2.subject")
    ISSUE_ID_LINK = (By.CSS_SELECTOR, "div.issue a.issue, #content h2")
