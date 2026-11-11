"""Einstellungen: Standardmodell, E-Mail-Versand, Konto."""
from __future__ import annotations

import streamlit as st

from .. import auth, db, mailer
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

    _mail_section(settings)

    st.subheader("Konto")
    st.write(f"Angemeldet als **{st.session_state.user['email']}** – Anmeldung per E-Mail-Code, kein Passwort nötig.")
    if st.button("Auf allen Geräten abmelden"):
        auth.end_all_sessions(uid())
        st.session_state.clear()
        st.session_state.clear_cookie = True
        st.rerun()


def _mail_section(settings: dict) -> None:
    st.subheader("E-Mail-Versand")
    acc = settings.get("mail") or {}
    if mailer.account_ready(acc):
        st.success(f"Eingerichtet: Bewerbungen werden von **{acc['address']}** gesendet.", icon=":material/check_circle:")
    st.caption("Damit verschickst du Bewerbungen direkt aus SmartResume – über dein eigenes Postfach, inklusive "
               "PDF im Anhang. Ohne Einrichtung kannst du stattdessen einen fertigen Gmail-Entwurf öffnen.")
    with st.expander("E-Mail-Konto einrichten" if not mailer.account_ready(acc) else "E-Mail-Konto ändern",
                     expanded=not mailer.account_ready(acc)):
        names = list(mailer.PROVIDERS)
        prov = st.selectbox("Anbieter", names, index=names.index(acc.get("provider", "Gmail"))
                            if acc.get("provider", "Gmail") in names else 0, key="mail_provider")
        info = mailer.PROVIDERS[prov]
        st.markdown(info["how"])
        if info["help_url"]:
            st.link_button("App-Passwort erstellen" if prov == "Gmail" else f"{prov} öffnen", info["help_url"],
                           icon=":material/open_in_new:")
        address = st.text_input("Deine E-Mail-Adresse", value=acc.get("address") or st.session_state.user["email"],
                                key="mail_address",
                                placeholder="vorname.nachname@gmail.com")
        password = st.text_input("App-Passwort" if prov == "Gmail" else "Passwort", type="password",
                                 key="mail_password",
                                 placeholder="gespeichert – zum Ändern neu eingeben" if acc.get("password") else "")
        host, port = info["host"], info["port"]
        if prov == "Andere":
            c1, c2 = st.columns([3, 1])
            host = c1.text_input("SMTP-Server", value=acc.get("host", ""), key="mail_host",
                                 placeholder="smtp.beispiel.de")
            port = int(c2.number_input("Port", value=int(acc.get("port") or 587), step=1, key="mail_port"))
        new = {"provider": prov, "host": host.strip(), "port": port, "address": address.strip(),
               "password": password.strip() or acc.get("password", "")}
        c1, c2, c3 = st.columns(3)
        if c1.button("Verbindung testen", use_container_width=True, disabled=not mailer.account_ready(new)):
            try:
                with st.spinner("Melde mich beim Mailserver an …"):
                    mailer.test_account(new)
                st.success("Verbindung klappt – es wurde nichts gesendet.")
            except mailer.MailError as e:
                st.error(str(e))
        if c2.button("Speichern", type="primary", use_container_width=True, icon=":material/save:",
                     disabled=not mailer.account_ready(new)):
            if not mailer.valid_email(new["address"]):
                st.error("Bitte eine gültige E-Mail-Adresse angeben.")
            else:
                settings["mail"] = new
                db.save_user_settings(uid(), settings)
                st.session_state.pop("mail_password", None)
                st.toast("E-Mail-Konto gespeichert.", icon=":material/check:")
                st.rerun()
        if acc and c3.button("Entfernen", use_container_width=True):
            settings.pop("mail", None)
            db.save_user_settings(uid(), settings)
            st.rerun()
        st.caption("Das Passwort wird nur lokal auf diesem Rechner gespeichert (data/smartresume.db) und nur zum "
                   "Versenden deiner Bewerbungen benutzt. Ein App-Passwort kannst du jederzeit beim Anbieter "
                   "widerrufen.")
