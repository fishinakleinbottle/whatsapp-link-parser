import os
from pathlib import Path

import pytest

import db


@pytest.fixture
def sample_chat_path():
    """Path to the sample chat file."""
    return str(Path(__file__).parent.parent / "sample_data" / "sample_chat.txt")


@pytest.fixture
def temp_db(tmp_path):
    """Set up a temporary database for testing."""
    db_path = str(tmp_path / "test_wa_links.db")
    os.environ["WA_LINKS_DB_PATH"] = db_path
    db.init_db()
    yield db_path
    os.environ.pop("WA_LINKS_DB_PATH", None)
