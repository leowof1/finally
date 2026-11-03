"""Tests for the snapshot background task."""

import asyncio

from app import db
from app.market import PriceCache
from app.portfolio import run_snapshot_loop


async def test_snapshot_loop_records_periodically(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    task = asyncio.create_task(run_snapshot_loop(PriceCache(), interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    snapshots = db.get_snapshots()
    assert len(snapshots) >= 2
    assert snapshots[0]["total_value"] == 10000.0
