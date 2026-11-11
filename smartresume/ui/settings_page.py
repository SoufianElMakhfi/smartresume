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
    how = ("dein Konto auf diesem PC – du bleibst angemeldet, bis du dich abmeldest" if auth.local_mode()
           else "Anmeldung per E-Mail-Code, kein Passwort nötig")
    st.write(f"Angemeldet als **{st.session_state.user['email']}** – {how}.")
    if st.button("Auf allen Geräten abmelden"):
        auth.end_all_sessions(uid())
        st.session_state.clear()
        st.session_state.clear_cookie = True
        st.rerun()


def _mail_section(settings: dict) -> None:
    st.subheader("E-Mail-Versand")
    acc = settings.get("mail") or {}
    ready = mailer.account_ready(acc)
    if ready:
        st.success(f"Eingerichtet: Bewerbungen werden von **{acc['address']}** gesendet.",
                   icon=":material/check_circle:")
    st.caption("Einmal verbunden, verschickst du Bewerbungen mit einem Klick direkt aus SmartResume – über dein "
               "eigenes Postfach, mit PDF im Anhang. Dauert etwa 2 Minuten. Ohne Verbindung geht es auch: Bei "
               "der fertigen Bewerbung gibt es einen **Entwurf mit Anhang** für Outlook, Thunderbird & Co. und "
               "einen Gmail-Entwurf.")
    with st.expander("E-Mail-Konto ändern" if ready else "E-Mail-Konto verbinden", expanded=not ready,
                     icon=":material/mail:"):
        address = st.text_input("Deine E-Mail-Adresse", value=acc.get("address") or st.session_state.user["email"],
                                key="mail_address", placeholder="vorname.nachname@gmail.com").strip()
        # Anbieter an der Adresse erkennen; gespeicherte Wahl gilt, solange die Adresse gleich bleibt
        names = list(mailer.PROVIDERS)
        detected = acc.get("provider") if acc.get("provider") in names and address == acc.get("address")             else mailer.detect_provider(address)
        prov = st.selectbox("Anbieter", names, index=names.index(detected), key=f"mail_provider_{detected}",
                            help="Wird an deiner Adresse erkannt – nur ändern, wenn das nicht stimmt.")
        info = mailer.PROVIDERS[prov]
        if info.get("unsupported"):
            st.info(info["how"], icon=":material/info:")
            return
        st.markdown("**So geht's**")
        st.markdown(info["how"])
        if info["help_url"]:
            st.link_button(info["help_label"], info["help_url"], icon=":material/open_in_new:")
        password = st.text_input(info["password_label"], type="password", key="mail_password",
                                 placeholder="gespeichert – zum Ändern neu eingeben" if acc.get("password") else "")
        host, port = info["host"], info["port"]
        if prov == "Andere":
            c1, c2 = st.columns([3, 1])
            host = c1.text_input("SMTP-Server", value=acc.get("host", ""), key="mail_host",
                                 placeholder="smtp.beispiel.de")
            port = int(c2.number_input("Port", value=int(acc.get("port") or 587), step=1, key="mail_port"))
        new = {"provider": prov, "host": host.strip(), "port": port, "address": address,
               "password": password.strip() or acc.get("password", "")}
        c1, c2, c3 = st.columns(3)
        if c1.button("Verbindung testen", use_container_width=True, disabled=not mailer.account_ready(new),
                     icon=":material/network_check:"):
            try:
                with st.spinner("Melde mich beim Mailserver an …"):
                    mailer.test_account(new)
                st.success("Verbindung klappt – es wurde nichts gesendet.", icon=":material/check_circle:")
            except mailer.MailError as e:
                st.error(str(e), icon=":material/error:")
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
        if acc and c3.button("Entfernen", use_container_width=True, icon=":material/link_off:"):
            settings.pop("mail", None)
            db.save_user_settings(uid(), settings)
            st.rerun()
        st.caption("Das Passwort wird nur lokal auf diesem Rechner gespeichert (data/smartresume.db) und nur zum "
                   "Versenden deiner Bewerbungen benutzt. Ein App-Passwort kannst du jederzeit beim Anbieter "
                   "widerrufen.")
