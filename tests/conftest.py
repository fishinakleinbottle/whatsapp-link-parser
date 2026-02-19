import os
from pathlib import Path

import pytest

from wa_link_parser import db
from wa_link_parser.exclusions import reset_exclusion_cache
from wa_link_parser.extractor import reset_link_type_cache


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


@pytest.fixture(autouse=True)
def _reset_caches():
    """Reset module-level caches between tests."""
    reset_exclusion_cache()
    reset_link_type_cache()
    yield
    reset_exclusion_cache()
    reset_link_type_cache()
