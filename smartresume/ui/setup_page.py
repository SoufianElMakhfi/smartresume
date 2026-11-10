"""KI einrichten (nur Admins): kostenlose API-Keys eintragen, testen, speichern.

Die Keys landen in der Datei .env neben dem Programm (lokal auf der Festplatte) und gelten
für alle Nutzer dieser Installation. Ohne Key funktioniert die App weiter über den Abo-Modus.
"""
from __future__ import annotations

import os

import streamlit as st

from .. import config, llm


def _test(env: str, key: str) -> tuple[bool, str]:
    cfg = next((m for m in llm.load_models() if m.get("key_env") == env), None)
    if not cfg:
        return False, "Für diesen Anbieter ist kein Modell in der Modellliste eingetragen."
    try:
        llm.complete(cfg, key, "Antworte nur mit dem Wort OK.", "Test", max_tokens=50, temperature=0)
        return True, f"Funktioniert ({cfg['label']})."
    except llm.LLMError as e:
        return False, str(e)


def _provider(p: dict) -> str | None:
    """Zeigt einen Anbieter. Gibt den eingegebenen Key zurück (oder None, wenn extern gesetzt)."""
    env = p["env"]
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        status = "✅ eingerichtet" if config.is_set(env) else "– noch kein Key"
        c1.markdown(f"**{p['name']}** {'· kostenlos' if p['free'] else ''}  \n:gray[{status}]")
        c2.link_button("Key holen ↗", p["url"], use_container_width=True)
        st.caption(p["how"])
        if config.set_externally(env):
            st.caption("Dieser Key ist auf dem Server fest hinterlegt und kann hier nicht geändert werden.")
            return None
        value = st.text_input("API-Key", type="password", key=f"setup_{env}", placeholder="hier einfügen" if not config.is_set(env)
                              else "gespeichert – zum Ändern neuen Key einfügen", label_visibility="collapsed")
        if st.button("Testen", key=f"test_{env}", disabled=not (value.strip() or config.is_set(env))):
            ok, msg = _test(env, value.strip() or os.environ.get(env, ""))
            (st.success if ok else st.error)(msg)
        return value.strip()


def render() -> None:
    st.title("KI einrichten")
    st.write("Mit einem **kostenlosen** API-Key schreibt die KI deine Bewerbungen automatisch. "
             "Ein Key reicht – mit zwei oder drei springt die App automatisch um, wenn ein Kontingent leer ist.")
    st.caption("Ohne Key funktioniert SmartResume trotzdem: dann über dein Gemini- oder ChatGPT-Konto per "
               "Kopieren & Einfügen. Die Keys werden nur lokal in der Datei `.env` neben dem Programm gespeichert.")

    entered: dict[str, str] = {}
    for p in [p for p in config.PROVIDERS if p["free"]]:
        v = _provider(p)
        if v:
            entered[p["env"]] = v
    with st.expander("Weitere Anbieter (kostenpflichtig, optional)"):
        for p in [p for p in config.PROVIDERS if not p["free"]]:
            v = _provider(p)
            if v:
                entered[p["env"]] = v

    c1, c2 = st.columns(2)
    if c1.button("💾 Speichern", type="primary", use_container_width=True, disabled=not entered):
        config.save_values(entered)
        for env in entered:
            st.session_state.pop(f"setup_{env}", None)
        st.toast("Gespeichert – die KI ist sofort einsatzbereit.", icon="✅")
        st.rerun()
    removable = [p for p in config.PROVIDERS if config.is_set(p["env"]) and not config.set_externally(p["env"])]
    if removable:
        with c2.popover("🗑 Key entfernen", use_container_width=True):
            for p in removable:
                if st.button(p["name"], key=f"rm_{p['env']}", use_container_width=True):
                    config.save_values({p["env"]: ""})
                    st.rerun()
    st.caption("Hinweis: Bei kostenlosen Angeboten können Anbieter Eingaben zum Training nutzen – die Aufträge "
               "enthalten Lebenslaufdaten.")
