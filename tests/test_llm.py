import pytest

from smartresume import llm


def test_parse_json_loose_variants():
    assert llm.parse_json_loose('{"a": 1}') == {"a": 1}
    assert llm.parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json_loose('Hier ist das JSON: {"a": [1, 2,], } Viel Erfolg!') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        llm.parse_json_loose("kein json")
    with pytest.raises(ValueError):
        llm.parse_json_loose("[1, 2]")


def test_resolve_key_prefers_user_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "server")
    cfg = {"key_env": "GEMINI_API_KEY", "provider": "gemini"}
    assert llm.resolve_key(cfg) == "server"
    assert llm.resolve_key(cfg, {"GEMINI_API_KEY": "nutzer"}) == "nutzer"
    assert llm.resolve_key(cfg, {"GEMINI_API_KEY": ""}) == "server"


def test_load_models_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SMARTRESUME_MODELS", str(tmp_path / "fehlt.json"))
    assert llm.load_models() == llm.DEFAULT_MODELS
    f = tmp_path / "models.json"
    f.write_text('[{"label": "X", "provider": "gemini", "model": "m", "key_env": "K"}]')
    monkeypatch.setenv("SMARTRESUME_MODELS", str(f))
    assert llm.load_models()[0]["label"] == "X"


CFG = {"label": "Fake", "provider": "fake", "model": "fake-1", "key_env": "K"}


def _install_fake(monkeypatch, answers):
    calls = []

    def fake(cfg, key, system, user, json_mode, max_tokens, temperature):
        calls.append(user)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return llm.LLMResult(a, 100, 50, cfg["model"])

    monkeypatch.setitem(llm.PROVIDERS, "fake", fake)
    return calls


def test_complete_json_retries_on_bad_json(monkeypatch):
    calls = _install_fake(monkeypatch, ["kaputt", '{"ok": true}'])
    res = llm.complete_json(CFG, "k", "sys", "user")
    assert res.data == {"ok": True}
    assert res.input_tokens == 200 and res.output_tokens == 100  # beide Versuche gezählt
    assert "FEHLERHAFT" in calls[1]


def test_complete_json_retries_on_validation(monkeypatch):
    _install_fake(monkeypatch, ['{"a": 1}', '{"a": 1, "b": 2}'])
    res = llm.complete_json(CFG, "k", "s", "u", validate=lambda d: [] if "b" in d else ["b fehlt"])
    assert res.data["b"] == 2


def test_complete_json_gives_up(monkeypatch):
    _install_fake(monkeypatch, ["x", "y"])
    with pytest.raises(llm.LLMError, match="kein brauchbares"):
        llm.complete_json(CFG, "k", "s", "u")


def test_friendly_errors(monkeypatch):
    _install_fake(monkeypatch, [RuntimeError("429 RESOURCE_EXHAUSTED quota")])
    with pytest.raises(llm.LLMError, match="Rate-Limit"):
        llm.complete(CFG, "k", "s", "u")
    with pytest.raises(llm.LLMError, match="Kein API-Key"):
        llm.complete(CFG, "", "s", "u")


def test_transient_classification(monkeypatch):
    for msg, transient in [("504 DEADLINE_EXCEEDED", True), ("503 UNAVAILABLE", True), ("429 quota", True),
                           ("Read timed out", True), ("401 Unauthorized", False), ("400 INVALID_ARGUMENT", False)]:
        assert llm._friendly(RuntimeError(msg), CFG).transient is transient, msg


def test_with_fallback_switches_on_transient_only():
    a, b, c = ({"label": "A"}, "ka", False), ({"label": "B"}, "kb", True), ({"label": "C"}, "kc", False)
    switches = []

    def fn(cfg, key):
        if cfg["label"] == "A":
            raise llm.LLMError("Timeout", transient=True)
        return f"ok-{key}"
    res, used = llm.with_fallback([a, b, c], fn, on_switch=lambda o, n, e: switches.append((o["label"], n["label"])))
    assert res == "ok-kb" and used is b and switches == [("A", "B")]

    def hard(cfg, key):
        raise llm.LLMError("Key ungültig")
    with pytest.raises(llm.LLMError, match="ungültig"):
        llm.with_fallback([a, b], hard)

    def always(cfg, key):
        raise llm.LLMError("überlastet", transient=True)
    with pytest.raises(llm.LLMError, match="überlastet"):
        llm.with_fallback([a, b], always)
