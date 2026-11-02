"""Large memory stores: AI tidy prompts stay bounded and fuzzy dedupe is fast."""

import json
import re
import time

import pytest

from tests.test_builtin_memory_consolidation import _import_consolidate_action, _write_memories


@pytest.mark.asyncio
async def test_large_store_tidy_uses_bounded_batches(monkeypatch, tmp_path):
    from src import constants, llm_core, task_endpoint
    import src.builtin_actions as ba
    action = _import_consolidate_action()

    memories = [
        {"id": f"m{i}", "owner": "alice", "category": "fact", "timestamp": i,
         "text": f"Fato distinto numero {i} sobre o projeto {i * 7919 % 104729} na VPS {i % 13}"}
        for i in range(1200)
    ]
    data_dir = _write_memories(tmp_path, memories)
    monkeypatch.setattr(constants, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(task_endpoint, "resolve_task_candidates", lambda *a, **k: [("http://llm", "model", {})])
    monkeypatch.setattr(ba, "wait_for_interactive_quiet", lambda *a, **k: _noop())

    batch_sizes = []

    async def fake_llm(_candidates, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        batch_sizes.append(len(re.findall(r'"id": "m\d+"', prompt)))
        return json.dumps({"keep": [], "drop": []})

    monkeypatch.setattr(llm_core, "llm_call_async_with_fallback", fake_llm)

    started = time.monotonic()
    await action("alice")
    elapsed = time.monotonic() - started

    assert batch_sizes and max(batch_sizes) <= ba._AI_TIDY_BATCH
    assert len(batch_sizes) <= ba._AI_TIDY_MAX_BATCHES
    assert elapsed < 60


async def _noop():
    return None
