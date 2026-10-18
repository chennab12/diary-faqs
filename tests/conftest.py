import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own empty database and never calls the real API."""
    monkeypatch.setenv("DIARY_DB", str(tmp_path / "diary.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path
