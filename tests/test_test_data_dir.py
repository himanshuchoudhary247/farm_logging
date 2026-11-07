"""Tests run on a copy of data/ (tests/conftest.py), never the repo's own
tracked files, and the weather/feed cache follows FARMER_CHAT_DATA_DIR."""
from __future__ import annotations

import os
from pathlib import Path

REPO_DATA = Path(__file__).resolve().parent.parent / "data"


def test_the_test_run_never_uses_the_repo_data_folder():
    from storage import get_data_dir

    assert Path(os.environ["FARMER_CHAT_DATA_DIR"]).resolve() != REPO_DATA.resolve()
    assert get_data_dir().resolve() != REPO_DATA.resolve()


def test_the_cache_lives_under_the_data_folder():
    from services.cache_refresh import service
    from storage import get_data_dir

    assert service.CACHE_ROOT == get_data_dir() / "cache"
