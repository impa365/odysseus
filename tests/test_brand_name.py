"""ODYSSEUS_BRAND_NAME renames the display name without touching identifiers."""

import src.constants as constants
from src import app_helpers
from src.chat_handler import _with_brand_identity

PAGE = "<html><head><title>Odysseus Chat</title></head><body data-x='odysseus-theme'>Odysseus</body></html>"


def test_default_brand_only_adds_meta(monkeypatch):
    monkeypatch.setattr(constants, "BRAND_NAME", "Odysseus")
    out = app_helpers.apply_brand(PAGE)
    assert '<meta name="app-brand" content="Odysseus">' in out
    assert "<title>Odysseus Chat</title>" in out


def test_custom_brand_replaces_display_name_only(monkeypatch):
    monkeypatch.setattr(constants, "BRAND_NAME", "KaiserChat")
    out = app_helpers.apply_brand(PAGE)
    assert "<title>KaiserChat</title>" in out
    assert ">KaiserChat</body>" in out
    assert "odysseus-theme" in out
    assert '<meta name="app-brand" content="KaiserChat">' in out


def test_assistant_named_after_brand_unless_persona(monkeypatch):
    monkeypatch.setattr(constants, "BRAND_NAME", "KaiserChat")
    assert _with_brand_identity(None, "") == "Your name is KaiserChat."
    assert _with_brand_identity("Be concise.", "") == "Your name is KaiserChat. Be concise."
    assert _with_brand_identity("Your name is Lara. Be nice.", "Lara") == "Your name is Lara. Be nice."
    monkeypatch.setattr(constants, "BRAND_NAME", "Odysseus")
    assert _with_brand_identity("Be concise.", "") == "Be concise."
