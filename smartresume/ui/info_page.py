"""Hilfe & Info: Kontakt, Problem/KI-Inhalt melden, Datenschutzerklärung, Lizenzen."""
from __future__ import annotations

import streamlit as st

from .. import __version__, paths
from .common import branding, report_url

SOURCE_URL = "https://github.com/SoufianElMakhfi/smartresume"
PRIVACY_URL = SOURCE_URL + "/blob/main/PRIVACY.md"


def _read(name: str) -> str:
    p = paths.app_dir() / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def render() -> None:
    br = branding()
    st.title("Hilfe & Info")
    st.caption(f"{br['app_name']} · Version {__version__}")

    st.subheader("Hilfe & Kontakt")
    st.write("Etwas funktioniert nicht, eine Idee oder eine Frage? Schreib uns – wir antworten so schnell wie möglich.")
    problem = report_url("Problem / Feedback", "Was ist passiert bzw. was wünschst du dir?\n\n")
    content = report_url("KI-Inhalt melden", "Welcher erzeugte Text war unpassend, beleidigend oder falsch?\n\n")
    if problem:
        c1, c2 = st.columns(2)
        c1.link_button("Problem melden / Feedback", problem, use_container_width=True, icon=":material/mail:")
        c2.link_button("Unpassenden KI-Inhalt melden", content, use_container_width=True, icon=":material/flag:")
        st.caption(f"E-Mail: {br['support_email']}")
    log = paths.real_home_dir() / "logs" / "smartresume.log"
    if log.exists():
        st.caption(f"Bei technischen Fehlern hilft uns die Protokolldatei (enthält keine Profildaten): `{log}`")

    st.subheader("Über die KI")
    st.write("SmartResume lässt Anschreiben und Lebenslauf-Texte von einer KI schreiben – über den Anbieter, den du "
             "unter „KI einrichten“ verbindest, oder per Kopieren & Einfügen über dein eigenes Gemini- oder "
             "ChatGPT-Konto. Firmen, Zeiträume, Abschlüsse und Kontaktdaten übernimmt SmartResume unverändert aus "
             "deinem Profil, und automatische Prüfungen sortieren Übertreibungen aus. KI kann trotzdem Fehler machen: "
             "Lies die Texte bitte vor dem Versand.")

    st.subheader("Datenschutz")
    st.write("Deine Daten bleiben auf deinem PC. Sie gehen nur an den KI-Anbieter, die Jobbörse oder deinen "
             "Mailanbieter, wenn du die jeweilige Funktion nutzt. Es gibt kein Tracking und keine Werbung.")
    privacy = _read("PRIVACY.md")
    with st.expander("Datenschutzerklärung lesen", icon=":material/privacy_tip:"):
        st.markdown(privacy or f"[Datenschutzerklärung online]({PRIVACY_URL})")

    st.subheader("Lizenzen")
    st.write(f"SmartResume ist Open Source unter der **GNU Affero General Public License v3.0** – den Quellcode "
             f"gibt es auf [GitHub]({SOURCE_URL}). Schriften: Lexend, Montserrat und Poppins (SIL Open Font "
             "License). Symbole: Material Symbols (Apache 2.0).")
    third = _read("THIRD_PARTY_LICENSES.txt")
    if third:
        with st.expander("Lizenzen der verwendeten Bibliotheken", icon=":material/gavel:"):
            st.code(third, language=None, wrap_lines=True)
    with st.expander("Lizenztext von SmartResume (AGPL-3.0)", icon=":material/description:"):
        st.code(_read("LICENSE"), language=None, wrap_lines=True)
