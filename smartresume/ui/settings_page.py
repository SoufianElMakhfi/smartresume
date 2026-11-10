"""Einstellungen: Standardmodell, Konto."""
from __future__ import annotations

import streamlit as st

from .. import auth, db
from .common import available_models, branding, fmt_tokens, uid


def render() -> None:
    st.title("Einstellungen")
    settings = db.get_user_settings(uid())

    st.subheader("KI-Modell")
    labels = [cfg["label"] for cfg, _ in available_models()]
    if labels:
        current = settings.get("default_model") or branding().get("default_model") or labels[0]
        choice = st.selectbox("Standardmodell", labels, index=labels.index(current) if current in labels else 0)
        if choice != settings.get("default_model"):
            settings["default_model"] = choice
            db.save_user_settings(uid(), settings)
            st.toast("Standardmodell gespeichert.")
        st.caption("Sind die Kontingente aufgebraucht, wechselt die App automatisch zum nächsten Modell und "
                   "zuletzt zu Gemini/ChatGPT per Kopieren & Einfügen.")
    else:
        st.caption("Auf diesem Server ist keine KI-API eingerichtet. Bewerbungen entstehen über dein eigenes "
                   "Gemini- oder ChatGPT-Konto (Kopieren & Einfügen) – kostenlos.")
    st.caption(f"Bisher verbraucht: {fmt_tokens(db.user_token_total(uid()))} Tokens")

    st.subheader("Konto")
    st.write(f"Angemeldet als **{st.session_state.user['email']}** – Anmeldung per E-Mail-Code, kein Passwort nötig.")
    if st.button("Auf allen Geräten abmelden"):
        auth.end_all_sessions(uid())
        st.session_state.clear()
        st.session_state.clear_cookie = True
        st.rerun()
