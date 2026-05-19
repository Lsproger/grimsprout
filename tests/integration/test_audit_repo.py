"""Integration tests for grimsprout.db.repositories.audit."""
from __future__ import annotations

import pytest

from grimsprout.db.models import AuditEntry
from grimsprout.db.repositories import audit as audit_repo

pytestmark = pytest.mark.mongo


async def test_log_inserts_entry(mongo_db) -> None:
    entry = AuditEntry(
        tg_id=42,
        action="water",
        payload={"plant_id": "areca_01"},
        file="trava/areca_01.md",
        commit_sha="deadbeef" * 5,
    )
    await audit_repo.log(mongo_db, entry)

    doc = await mongo_db.audit_log.find_one({"tg_id": 42})
    assert doc is not None
    assert doc["action"] == "water"
    assert doc["payload"] == {"plant_id": "areca_01"}
    assert doc["file"] == "trava/areca_01.md"


async def test_multiple_entries_for_same_user(mongo_db) -> None:
    for action in ("water", "fertilize", "repot"):
        await audit_repo.log(mongo_db, AuditEntry(tg_id=42, action=action))

    count = await mongo_db.audit_log.count_documents({"tg_id": 42})
    assert count == 3
