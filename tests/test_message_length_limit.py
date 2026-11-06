"""The chat message length cap is configurable and its error is readable."""

import pytest
from fastapi import HTTPException

import src.constants as constants
from src.chat_helpers import validate_message


def test_default_limit_is_50k(monkeypatch):
    monkeypatch.delenv("ODYSSEUS_MAX_MESSAGE_CHARS", raising=False)
    assert constants._positive_int_env("ODYSSEUS_MAX_MESSAGE_CHARS", 50000) == 50000
    monkeypatch.setenv("ODYSSEUS_MAX_MESSAGE_CHARS", "200000")
    assert constants._positive_int_env("ODYSSEUS_MAX_MESSAGE_CHARS", 50000) == 200000
    monkeypatch.setenv("ODYSSEUS_MAX_MESSAGE_CHARS", "-3")
    assert constants._positive_int_env("ODYSSEUS_MAX_MESSAGE_CHARS", 50000) == 50000


def test_validate_message_uses_configured_limit(monkeypatch):
    monkeypatch.setattr(constants, "MAX_MESSAGE_CHARS", 120)
    assert validate_message("  oi  ") == "oi"
    assert validate_message("x" * 120) == "x" * 120
    with pytest.raises(HTTPException) as err:
        validate_message("x" * 121)
    assert err.value.status_code == 400
    assert "121 characters" in err.value.detail and "limit is 120" in err.value.detail
    assert "tool" not in err.value.detail and "auto" not in err.value.detail
