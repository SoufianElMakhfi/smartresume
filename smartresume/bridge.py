"""Abo-Modus: KI-Aufträge per Kopieren & Einfügen über Gemini oder ChatGPT im Browser.

Rückfall, wenn keine KI-API eingerichtet ist oder die Kontingente aufgebraucht sind.
Funktioniert mit jedem normalen Konto (auch kostenlos) – der Nutzer schickt den Auftrag
selbst im Chat ab, es wird nichts automatisiert. Die Antwort durchläuft danach exakt
dieselben Prüfungen wie eine API-Antwort (Format, Ehrlichkeit, Qualität).
"""
from __future__ import annotations

from . import llm

CHAT_SITES = {
    "Gemini": "https://gemini.google.com/app",
    "ChatGPT": "https://chatgpt.com/",
}

_FORMAT_HINT = ("WICHTIG: Antworte ausschließlich mit dem JSON-Objekt in einem einzigen ```json-Codeblock – "
                "ohne Einleitung und ohne Erklärung danach.")


def chat_prompt(system: str, user: str) -> str:
    """Systemregeln + Auftrag als ein Text zum Einfügen in einen Chat."""
    return (f"Halte dich exakt an die folgenden Regeln.\n\n{system.strip()}\n\n"
            f"==========\n\n{user.strip()}\n\n==========\n{_FORMAT_HINT}")


def parse_answer(text: str, validate=None) -> dict:
    """Liest das JSON aus einer eingefügten Chat-Antwort (Codeblöcke/Vor- und Nachtext egal).
    Wirft ValueError mit verständlicher Meldung, wenn etwas fehlt."""
    if not (text or "").strip():
        raise ValueError("Es wurde noch keine Antwort eingefügt.")
    try:
        data = llm.parse_json_loose(text)
    except ValueError:
        raise ValueError("In der Antwort wurde kein vollständiges JSON gefunden – bitte die komplette Antwort "
                         "kopieren (am besten über den Kopieren-Knopf am Codeblock).") from None
    problems = validate(data) if validate else []
    if problems:
        raise ValueError("Die Antwort ist unvollständig: " + "; ".join(problems))
    return data


def correction_prompt(error: str) -> str:
    """Kurzer Nachsatz für denselben Chat, wenn die Antwort nicht verwertbar war."""
    return (f"Deine letzte Antwort war nicht verwertbar ({error}). Antworte bitte erneut – vollständig und "
            "ausschließlich mit dem JSON-Objekt in einem einzigen ```json-Codeblock.")
