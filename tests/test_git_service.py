from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.models.commit import Commit
from app.models.execution_history import ExecutionHistory
from app.services.git_service import GitService


@pytest.fixture(scope="module")
def setup_database():
    """Ensure database tables exist."""
    init_db()
    yield


@pytest.fixture
def db_session(setup_database):
    """Provide a clean session per test."""
    session = SessionLocal()
    yield session
    session.close()


def test_validate_repository_valid():
    """Test validation of an existing valid git repository."""
    is_valid, msg = GitService.validate_repository(settings.BASE_DIR)
    assert is_valid is True
    assert "Repositório válido" in msg


def test_validate_repository_invalid():
    """Test validation of an invalid path."""
    is_valid, msg = GitService.validate_repository("D:/caminho/inexistente/123")
    assert is_valid is False


def test_get_commits_period():
    """Test extracting commits within a specific period."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=1)
    end_date = now + timedelta(days=1)

    commits = GitService.get_commits(
        repo_path=settings.BASE_DIR,
        start_date=start_date,
        end_date=end_date,
        author="athos",
    )

    assert len(commits) > 0
    first = commits[0]
    assert "hash" in first
    assert "author" in first
    assert "commit_date" in first
    assert "message" in first
    assert "files_changed" in first
    assert len(first["hash"]) == 40


def test_execute_analysis_and_persistence(db_session):
    """Test the full analysis execution pipeline and DB persistence."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=1)
    end_date = now + timedelta(days=1)

    history, saved_commits = GitService.execute_analysis(
        db=db_session,
        repo_path=settings.BASE_DIR,
        start_date=start_date,
        end_date=end_date,
        author=None,
        notes="Teste automatizado via pytest",
    )

    assert history.id is not None
    assert history.status == "concluido"
    assert history.total_commits > 0
    assert len(saved_commits) == history.total_commits

    # Verify query directly in database
    db_history = db_session.get(ExecutionHistory, history.id)
    assert db_history is not None
    assert len(db_history.commits) == history.total_commits
