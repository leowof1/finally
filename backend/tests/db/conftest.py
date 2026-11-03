"""Fixtures for database tests."""

import pytest

from app.db import init_db


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    """Point DB_PATH at a fresh temp database and initialize it."""
    path = tmp_path / "sub" / "test.db"
    monkeypatch.setenv("DB_PATH", str(path))
    init_db()
    return path
