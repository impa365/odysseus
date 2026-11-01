"""Import "save all" persists every suggestion in one store write."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import routes.memory_routes as memory_routes
from src.memory import MemoryManager


class _Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _bulk_endpoint(manager, monkeypatch, user="alice", vector=None):
    monkeypatch.setattr(memory_routes, "get_current_user", lambda request: user)
    import src.auth_helpers as auth_helpers
    monkeypatch.setattr(auth_helpers, "require_privilege", lambda request, priv: None)
    router = memory_routes.setup_memory_routes(manager, MagicMock(), memory_vector=vector)
    return next(r.endpoint for r in router.routes if r.path == "/api/memory/add-bulk")


def test_bulk_add_saves_all_and_skips_duplicates(monkeypatch, tmp_path):
    manager = MemoryManager(str(tmp_path))
    existing = manager.add_entry("Mora em São Paulo", owner="alice")
    other_owner = manager.add_entry("Usa Docker Swarm", owner="bob")
    manager.save([existing, other_owner])
    vector = MagicMock(healthy=True)
    add_bulk = _bulk_endpoint(manager, monkeypatch, vector=vector)

    items = [{"text": f"Fato número {i}", "category": "fact"} for i in range(300)]
    items += [
        {"text": "mora em são paulo", "category": "fact"},   # already stored
        {"text": "Fato número 1", "category": "fact"},       # repeated in batch
        {"text": "Usa Docker Swarm", "category": "project"}, # only bob has it
        {"text": "   ", "category": "fact"},
        "not-a-dict",
    ]
    result = asyncio.run(add_bulk(_Req({"items": items})))

    assert result["added"] == 301
    assert result["skipped"] == 4
    alice = manager.load(owner="alice")
    assert len(alice) == 302
    assert {m["text"] for m in alice} >= {"Fato número 0", "Fato número 299", "Usa Docker Swarm"}
    vector.add_many.assert_called_once()
    assert len(vector.add_many.call_args[0][0]) == 301


def test_bulk_add_rejects_oversized_and_malformed(monkeypatch, tmp_path):
    manager = MemoryManager(str(tmp_path))
    manager.save([])
    add_bulk = _bulk_endpoint(manager, monkeypatch)
    with pytest.raises(HTTPException) as too_many:
        asyncio.run(add_bulk(_Req({"items": [{"text": "x"}] * 501})))
    assert too_many.value.status_code == 413
    with pytest.raises(HTTPException) as bad:
        asyncio.run(add_bulk(_Req({"items": "nope"})))
    assert bad.value.status_code == 400
    assert manager.load_all() == []


def test_embedded_json_array_is_recovered():
    raw = 'Here are the facts:\n[{"text": "Prefere respostas curtas", "category": "preference"}]\nDone.'
    assert memory_routes._loads_embedded_json_array(raw) == [
        {"text": "Prefere respostas curtas", "category": "preference"}
    ]
    with pytest.raises(json.JSONDecodeError):
        memory_routes._loads_embedded_json_array("We need to analyze the conversation first.")
