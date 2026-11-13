"""Einstellungen: Standardmodell, E-Mail-Versand, Daten & Sicherung, Konto."""
from __future__ import annotations

import os
import sys

import streamlit as st

from .. import auth, backup, db, mailer, paths
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
        where = ("Noch keine KI verbunden (unter „KI einrichten“ geht das kostenlos in 2 Minuten)."
                 if auth.local_mode() else "Auf diesem Server ist keine KI-API eingerichtet.")
        st.caption(f"{where} Bewerbungen entstehen bis dahin über dein eigenes Gemini- oder ChatGPT-Konto "
                   "(Kopieren & Einfügen) – kostenlos.")
    st.caption(f"Bisher verbraucht: {fmt_tokens(db.user_token_total(uid()))} Tokens")

    _mail_section(settings)
    _data_section()

    st.subheader("Konto")
    how = ("dein Konto auf diesem PC – du bleibst angemeldet, bis du dich abmeldest" if auth.local_mode()
           else "Anmeldung per E-Mail-Code, kein Passwort nötig")
    st.write(f"Angemeldet als **{st.session_state.user['email']}** – {how}.")
    if not auth.local_mode() and st.button("Auf allen Geräten abmelden"):
        auth.end_all_sessions(uid())
        st.session_state.clear()
        st.session_state.clear_cookie = True
        st.rerun()


def _test_mail(acc: dict, key: str) -> None:
    """Empfänger + „Testmail senden“: prüft, ob Mails über das Konto wirklich ankommen."""
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    to = c1.text_input("Testmail an", value=acc.get("address", ""), key=f"test_to_{key}",
                       help="Am besten auch einmal an eine andere Adresse (z. B. ein zweites Postfach) – "
                            "dann siehst du, ob Mails auch außerhalb deines Postfachs ankommen.").strip()
    if c2.button("Testmail senden", key=f"test_send_{key}", use_container_width=True, icon=":material/send:",
                 disabled=not mailer.account_ready(acc)):
        try:
            with st.spinner("Sende Testmail …"):
                name = (db.get_profile(uid())["data"].get("personal") or {}).get("name", "")
                mailer.send(acc, mailer.build_test_message(acc, name, to))
            st.success(f"Testmail an **{to}** gesendet – schau in dein Postfach (auch in den Spam-Ordner). "
                       "Kommt sie an, kommen auch deine Bewerbungen an.", icon=":material/mark_email_read:")
        except mailer.MailError as e:
            st.error(str(e), icon=":material/error:")


def _mail_section(settings: dict) -> None:
    st.subheader("E-Mail-Versand")
    acc = settings.get("mail") or {}
    ready = mailer.account_ready(acc)
    if ready:
        st.success(f"Eingerichtet: Bewerbungen werden von **{acc['address']}** gesendet.",
                   icon=":material/check_circle:")
        _test_mail(acc, "saved")
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
        if not ready:                      # vor dem Speichern ausprobieren (danach steht es oben)
            _test_mail(new, "new")
        st.caption("Das Passwort bleibt auf diesem PC – verschlüsselt und nur mit deinem Windows-Konto lesbar – und wird nur zum "
                   "Versenden deiner Bewerbungen benutzt. Ein App-Passwort kannst du jederzeit beim Anbieter "
                   "widerrufen.")


def _data_section() -> None:
    st.subheader("Daten & Sicherung")
    if auth.local_mode():
        folder = paths.real_home_dir()
        st.write("Alles, was du in SmartResume anlegst, bleibt auf diesem PC – in diesem Ordner:")
        st.code(str(folder), language=None, wrap_lines=True)
        if sys.platform == "win32" and st.button("Ordner öffnen", icon=":material/folder_open:"):
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)  # noqa: S606 – fester Pfad, kein Nutzereingabe
        if paths.packaged():
            st.warning("**Wichtig:** Beim Deinstallieren von SmartResume löscht Windows diesen Ordner. Lade vorher "
                       "eine Sicherung herunter – damit kommt alles zurück, auch auf einem neuen PC.",
                       icon=":material/warning:")
    st.caption("Die Sicherung enthält dein Profil (mit Foto und Unterschrift), deine Einstellungen und alle "
               "Bewerbungen samt PDF. Nicht enthalten sind Passwörter und KI-Keys.")
    c1, c2 = st.columns(2)
    if c1.button("Sicherung erstellen", use_container_width=True, icon=":material/inventory_2:"):
        st.session_state.backup_zip = backup.export_user(uid())
    if st.session_state.get("backup_zip"):
        c2.download_button("Sicherung herunterladen", st.session_state.backup_zip, file_name=backup.filename(),
                           mime="application/zip", use_container_width=True, type="primary",
                           icon=":material/download:", on_click="ignore")

    with st.expander("Sicherung wiederherstellen", icon=":material/restore:"):
        up = st.file_uploader("Sicherungsdatei (ZIP)", type=["zip"], key="backup_up",
                              max_upload_size=backup.MAX_BYTES // (1024 * 1024))
        if up is None:
            return
        data = up.getvalue()
        try:
            info = backup.read_backup(data)
        except backup.BackupError as e:
            st.error(str(e), icon=":material/error:")
            return
        when = info["created"].replace("T", " ")[:16]
        st.write(f"Sicherung vom **{when}**" + (f" · Profil **{info['name']}**" if info["name"] else "")
                 + f" · **{info['applications']}** Bewerbung(en)")
        st.warning("Ersetzt dein aktuelles Profil, deine Einstellungen und alle Bewerbungen in diesem Konto.",
                   icon=":material/warning:")
        if st.button("Jetzt wiederherstellen", type="primary", icon=":material/restore:"):
            backup.import_user(uid(), data)
            st.session_state.draft_uid = None          # Profilseite lädt neu
            st.session_state.pop("backup_zip", None)
            st.toast("Sicherung wiederhergestellt.", icon=":material/check:")
            st.rerun()
