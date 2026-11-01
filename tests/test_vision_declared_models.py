"""Models listed in Settings → Vision are treated as image-capable, and the
Vision fallback chain is used even when no primary Vision model is set."""

import src.settings as settings_mod
import src.chat_helpers as ch
import src.document_processor as dp


def _settings(monkeypatch, values):
    monkeypatch.setattr(settings_mod, "get_user_setting",
                        lambda key, owner="", default=None: values.get(key, default))


def test_fallback_listed_model_counts_as_vision(monkeypatch):
    _settings(monkeypatch, {"vision_model": "",
                            "vision_model_fallbacks": [{"endpoint_id": "e1", "model": "combo-deepseek-v4.1-flash"}]})
    assert ch.is_declared_vision_model("combo-deepseek-v4.1-flash")
    assert ch.is_declared_vision_model("COMBO-DeepSeek-v4.1-Flash", owner="admin")
    assert not ch.is_declared_vision_model("ocz/deepseek-v4-pro")
    assert ch.model_supports_vision("combo-deepseek-v4.1-flash")


def test_primary_vision_model_counts_as_vision(monkeypatch):
    _settings(monkeypatch, {"vision_model": "my-router-alias", "vision_model_fallbacks": []})
    assert ch.is_declared_vision_model("my-router-alias")
    assert not ch.is_declared_vision_model("")


def test_analyze_uses_fallbacks_without_primary(monkeypatch, tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(dp, "_load_vl_settings", lambda: {"vision_enabled": True, "vision_model": ""})

    def _no_primary(configured, owner=None):
        raise ValueError("No vision model available")

    monkeypatch.setattr(dp, "_resolve_vl_model", _no_primary)
    import src.endpoint_resolver as er
    monkeypatch.setattr(er, "resolve_vision_fallback_candidates",
                        lambda owner=None: [("http://router/v1", "combo-deepseek-v4.1-flash", None)])
    calls = []
    monkeypatch.setattr(dp, "llm_call", lambda url, model, msgs, **kw: calls.append(model) or "a red square")

    result = dp.analyze_image_with_vl_result(str(img))
    assert result == {"text": "a red square", "model": "combo-deepseek-v4.1-flash"}
    assert calls == ["combo-deepseek-v4.1-flash"]


def test_analyze_reports_missing_when_nothing_configured(monkeypatch, tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(dp, "_load_vl_settings", lambda: {"vision_enabled": True, "vision_model": ""})
    monkeypatch.setattr(dp, "_resolve_vl_model", lambda configured, owner=None: (_ for _ in ()).throw(ValueError()))
    import src.endpoint_resolver as er
    monkeypatch.setattr(er, "resolve_vision_fallback_candidates", lambda owner=None: [])

    result = dp.analyze_image_with_vl_result(str(img))
    assert result["text"].startswith("[No vision model configured")
