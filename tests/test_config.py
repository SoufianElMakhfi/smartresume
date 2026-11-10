import os

import pytest

from smartresume import config, paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SMARTRESUME_HOME", str(tmp_path))
    monkeypatch.setattr(config, "_from_file", set())
    for env in ("GEMINI_API_KEY", "MISTRAL_API_KEY", "SMTP_HOST"):
        monkeypatch.setenv(env, "x")      # merken, damit pytest den Ursprungszustand wiederherstellt
        monkeypatch.delenv(env)
    return tmp_path


def test_paths_follow_home(home):
    assert paths.env_file() == home / ".env"
    assert paths.data_dir() == home / "data"
    assert (paths.app_dir() / "template.typ").exists()


def test_save_values_keeps_other_lines_and_applies_immediately(home):
    (home / ".env").write_text("# Kommentar\nSMTP_HOST=smtp.example.com\nGEMINI_API_KEY=alt\n", encoding="utf-8")
    config.load_env()
    assert os.environ["GEMINI_API_KEY"] == "alt" and not config.set_externally("GEMINI_API_KEY")
    config.save_values({"GEMINI_API_KEY": "neu", "MISTRAL_API_KEY": " m-123 "})
    text = (home / ".env").read_text(encoding="utf-8")
    assert "# Kommentar" in text and "SMTP_HOST=smtp.example.com" in text
    assert "GEMINI_API_KEY=neu" in text and "MISTRAL_API_KEY=m-123" in text and "alt" not in text
    assert os.environ["GEMINI_API_KEY"] == "neu" and os.environ["MISTRAL_API_KEY"] == "m-123"
    config.save_values({"GEMINI_API_KEY": ""})                 # leer = entfernen
    assert "GEMINI_API_KEY" not in (home / ".env").read_text(encoding="utf-8")
    assert "GEMINI_API_KEY" not in os.environ


def test_external_env_wins(home, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "vom-hoster")
    (home / ".env").write_text("GEMINI_API_KEY=aus-datei\n", encoding="utf-8")
    config.load_env()
    assert os.environ["GEMINI_API_KEY"] == "vom-hoster" and config.set_externally("GEMINI_API_KEY")
