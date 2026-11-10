"""Verwaltung (nur Admins): Nutzer, Verbrauch, Branding-Übersicht."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from .. import auth, db
from .common import branding, uid


def render() -> None:
    st.title("Verwaltung")
    tab_users, tab_usage, tab_brand = st.tabs(["👥 Nutzer", "📊 Verbrauch", "🎨 Branding"])

    with tab_users:
        users = db.list_users()
        st.dataframe(pd.DataFrame(users).rename(columns={
            "id": "ID", "email": "E-Mail", "is_admin": "Admin", "created_at": "Erstellt", "apps": "Bewerbungen"}),
            hide_index=True, use_container_width=True)
        st.markdown("**Nutzer anlegen**")
        st.caption("Neue Nutzer melden sich einfach mit ihrer E-Mail an und bekommen einen Code – "
                   "anlegen ist nur nötig, wenn die Selbstregistrierung ausgeschaltet ist.")
        with st.form("new_user", clear_on_submit=True):
            c1, c2 = st.columns([4, 1])
            email = c1.text_input("E-Mail")
            admin = c2.checkbox("Admin")
            if st.form_submit_button("Anlegen"):
                try:
                    db.create_user(email, is_admin=admin)
                    st.success(f"**{email}** angelegt – Anmeldung per Code an diese Adresse.")
                except db.UserError as e:
                    st.error(str(e))
        st.markdown("**Nutzer verwalten**")
        others = [u for u in users if u["id"] != uid()]
        if others:
            sel = st.selectbox("Nutzer", others, format_func=lambda u: u["email"])
            c1, c2 = st.columns([3, 1])
            new_mail = c1.text_input("E-Mail ändern", value=sel["email"],
                                     key=f"mail_{sel['id']}")
            c2.markdown("<br>", unsafe_allow_html=True)
            if c2.button("Speichern", use_container_width=True):
                try:
                    db.set_email(sel["id"], new_mail)
                    auth.end_all_sessions(sel["id"])
                    st.rerun()
                except db.UserError as e:
                    st.error(str(e))
            if st.button("🗑 Nutzer löschen (inkl. aller Daten)", use_container_width=True):
                st.session_state.confirm_user_del = sel["id"]
            if st.session_state.get("confirm_user_del") == sel["id"]:
                st.warning(f"{sel['email']} und alle Profile/Bewerbungen endgültig löschen?")
                if st.button("Ja, endgültig löschen", type="primary"):
                    db.delete_user(sel["id"])
                    st.session_state.confirm_user_del = None
                    st.rerun()

    with tab_usage:
        st.caption("Tokens aller KI-Aufrufe über die Server-Keys. Bewerbungen im Abo-Modus kosten nichts.")
        df = pd.DataFrame(db.usage_summary()).rename(columns={
            "email": "E-Mail", "calls": "Aufrufe", "tokens": "Tokens", "last_use": "Zuletzt"})
        st.dataframe(df, hide_index=True, use_container_width=True)

    with tab_brand:
        st.markdown("Das Branding wird über **`branding.json`** im Projektordner gesteuert "
                    "(Vorlage: `branding.example.json`). Aktuelle Werte:")
        st.code(json.dumps(branding(), ensure_ascii=False, indent=2), language="json")
