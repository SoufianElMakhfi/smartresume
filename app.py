"""SmartResume – Streamlit-Einstieg.

Start:  streamlit run app.py
Konfiguration: .env (KI-Keys – auch in der App unter „KI einrichten“), branding.json, models.json
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smartresume import auth, config, db, paths  # noqa: E402

config.load_env()  # KI-Keys usw. aus .env neben dem Programm
from smartresume.branding import load_branding  # noqa: E402

BR = load_branding()
st.set_page_config(page_title=BR["app_name"], page_icon=BR["page_icon"] or None, layout="centered")
st.markdown("""<style>
  [data-testid="stDecoration"], footer, #MainMenu { display: none !important; }
  h1 a, h2 a, h3 a { display: none !important; }
  .block-container { padding-top: 2.2rem; }
  /* Upload-Feld auf Deutsch (Streamlit kennt nur Englisch); Dateitypen stehen in der Beschriftung */
  [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p { font-size: 0; }
  [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {
    content: "Datei auswählen"; font-size: 0.875rem; }
  [data-testid="stFileUploaderDropzoneInstructions"] span { font-size: 0; }
  [data-testid="stFileUploaderDropzoneInstructions"] span::after { content: "oder hierher ziehen"; font-size: 0.875rem; }
  /* Hinweistexte gut lesbar: dunkelgrau statt Streamlit-Hellgrau */
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
  [data-testid="stWidgetLabel"] p, .stTooltipIcon { color: #39444D !important; }
  [data-testid="stWidgetLabel"] p { font-weight: 500; }
  /* Platzhalter = nur Beispiel: kursiv, aber lesbar; verschwindet beim Hineinklicken */
  input::placeholder, textarea::placeholder { font-style: italic; color: #6B7680 !important; opacity: 1; }
  input:focus::placeholder, textarea:focus::placeholder { color: transparent !important; opacity: 0; }
</style>""", unsafe_allow_html=True)

db.init_db()
st.session_state.branding = BR


def _logo() -> None:
    logo = next((d / BR["logo"] for d in (paths.home_dir(), paths.app_dir()) if BR["logo"] and (d / BR["logo"]).exists()),
                None)
    if logo:
        st.image(str(logo), width=180)
    else:
        st.markdown(f"## {BR['page_icon']} {BR['app_name']}")


# ---------------------------------------------------------------------------
# Login: E-Mail → Code → fertig. Neue E-Mails bekommen automatisch ein Konto,
# die allererste wird Admin (Ersteinrichtung).
# ---------------------------------------------------------------------------
COOKIE = "smartresume_session"
_LOGIN_KEYS = ("login_email", "login_sent", "login_dev_code")


def _header(name: str) -> str:
    try:
        val = st.context.headers.get(name, "")
        return val if isinstance(val, str) else ""
    except Exception:
        return ""


def _is_local() -> bool:
    host = _header("Host").rsplit(":", 1)[0].strip("[]")
    return host in ("localhost", "127.0.0.1", "::1")


def _base_url() -> str:
    if os.environ.get("SMARTRESUME_URL"):
        return os.environ["SMARTRESUME_URL"]
    host = _header("Host")
    return f"{_header('X-Forwarded-Proto') or 'http'}://{host}" if host else ""


def _write_cookie(token: str) -> None:
    """Setzt (oder löscht bei leerem Token) das Sitzungs-Cookie im Browser."""
    age = auth.session_ttl() if token else 0
    js = f"document.cookie = '{COOKIE}={token}; path=/; max-age={age}; SameSite=Lax';"
    try:
        st.html(f"<script>{js}</script>", unsafe_allow_javascript=True)   # Streamlit ≥ 1.5x, ohne iframe
    except TypeError:
        components.html(f"<script>window.parent.{js}</script>", height=0)


def _restore_session() -> None:
    if st.session_state.get("user"):
        return
    try:
        token = st.context.cookies.get(COOKIE, "")
    except Exception:
        token = ""
    if not isinstance(token, str):
        token = ""
    user = auth.user_from_session(token)
    if user:
        st.session_state.user = user
        st.session_state.session_token = token


def _handle_login_link() -> None:
    """Klick auf den Link in der Mail: ?email=…&code=… → direkt anmelden."""
    qp = st.query_params
    if "code" not in qp or "email" not in qp:
        return
    email, code = qp.get("email", ""), qp.get("code", "")
    st.query_params.clear()
    if st.session_state.get("user"):
        return
    try:
        ok = auth.verify_code(email, code)
    except auth.AuthError as e:
        st.session_state.login_error = str(e)
        return
    if ok:
        _complete_login(email)
    st.session_state.login_error = "Der Login-Link ist ungültig oder wurde schon benutzt."


def _send_code(email: str) -> None:
    code = auth.request_code(email)
    try:
        sent = auth.send_code(email, code, BR["app_name"], auth.login_link(_base_url(), email, code))
    except auth.AuthError:
        auth.discard_code(email)
        raise
    st.session_state.login_email = email
    st.session_state.login_sent = sent
    st.session_state.login_dev_code = code if (not sent and _is_local()) else None


def _any_ai_key() -> bool:
    from smartresume import llm
    return any(llm.resolve_key(m) for m in llm.load_models())


def _complete_login(email: str) -> None:
    user = db.get_user_by_email(email)
    page = "generate"
    if not user:
        first = db.needs_setup()
        db.create_user(email, is_admin=first)                # erstes Konto = Admin
        user = db.get_user_by_email(email)
        prof = db.get_profile(user["id"])["data"]                # Login-Adresse als Kontakt-E-Mail vorschlagen
        if not prof["personal"]["email"]:
            prof["personal"]["email"] = email
            db.save_profile(user["id"], data=prof)
        page = "profile"                                     # neue Nutzer starten beim Profil
        if (first or auth.local_mode()) and not _any_ai_key():
            page = "setup"                                   # Ersteinrichtung: zuerst kostenlose KI verbinden
    for k in _LOGIN_KEYS:
        st.session_state.pop(k, None)
    st.session_state.user = user
    st.session_state.session_token = auth.create_session(user["id"])
    st.session_state.page = page
    st.rerun()


def _local_step() -> None:
    """Lokal (nur dieser PC): E-Mail-Adresse eingeben, fertig – kein Code, kein Passwort."""
    with st.form("form_local"):
        email = st.text_input("Deine E-Mail-Adresse", placeholder="du@beispiel.de", autocomplete="email")
        st.caption("Sie ist dein Konto auf diesem PC – Profil und Bewerbungen werden darunter gespeichert. "
                   "Kein Passwort, kein Code. Du bleibst angemeldet, bis du dich abmeldest.")
        if not st.form_submit_button("Weiter", type="primary", use_container_width=True,
                                     icon=":material/arrow_forward:"):
            return
    try:
        email = db.normalize_email(email)
    except db.UserError as e:
        st.error(str(e))
        return
    if not db.needs_setup() and not db.get_user_by_email(email) and not BR["allow_registration"]:
        st.error("Für diese E-Mail gibt es kein Konto. Bitte wende dich an den Administrator.")
        return
    _complete_login(email)


def _email_step(setup: bool) -> None:
    ask_invite = not setup and BR["allow_registration"] and bool(BR["invite_code"])
    with st.form("form_email"):
        email = st.text_input("E-Mail-Adresse", placeholder="du@beispiel.de", autocomplete="email")
        invite = st.text_input("Einladungscode (nur für neue Konten)", type="password") if ask_invite else ""
        if not st.form_submit_button("Code senden", type="primary", use_container_width=True):
            return
    try:
        email = db.normalize_email(email)
    except db.UserError as e:
        st.error(str(e))
        return
    if not setup and not db.get_user_by_email(email):
        if not BR["allow_registration"]:
            st.error("Für diese E-Mail gibt es kein Konto. Bitte wende dich an den Administrator.")
            return
        if BR["invite_code"] and (invite or "").strip() != BR["invite_code"]:
            st.error("Einladungscode ungültig.")
            return
    try:
        _send_code(email)
    except auth.AuthError as e:
        st.error(str(e))
        return
    st.rerun()


def _code_step(email: str) -> None:
    if st.session_state.get("login_sent"):
        st.success(f"Wir haben dir einen 6-stelligen Code an **{email}** geschickt. "
                   "Gib ihn hier ein oder klicke auf den Link in der Mail.", icon=":material/mark_email_read:")
    elif st.session_state.get("login_dev_code"):
        st.info(f"Lokaler Modus (kein E-Mail-Versand eingerichtet) – dein Code für **{email}**: "
                f"`{st.session_state.login_dev_code}`", icon=":material/key:")
    else:
        st.warning("E-Mail-Versand ist nicht eingerichtet – der Code steht in der Server-Konsole.")
    with st.form("form_code"):
        code = st.text_input("Code", placeholder="123456", autocomplete="one-time-code")
        submitted = st.form_submit_button("Anmelden", type="primary", use_container_width=True)
    if submitted:
        try:
            if auth.verify_code(email, code):
                _complete_login(email)
            st.error("Der Code stimmt nicht – bitte nochmal prüfen.")
        except auth.AuthError as e:
            st.error(str(e))
    c1, c2 = st.columns(2)
    if c1.button("Neuen Code senden", use_container_width=True):
        try:
            _send_code(email)
            st.toast("Neuer Code ist unterwegs.", icon=":material/mark_email_read:")
        except auth.AuthError as e:
            st.error(str(e))
    if c2.button("Andere E-Mail", use_container_width=True):
        for k in _LOGIN_KEYS:
            st.session_state.pop(k, None)
        st.rerun()


def _login() -> None:
    if st.session_state.pop("clear_cookie", False):
        _write_cookie("")
    _logo()
    setup = db.needs_setup()
    if setup and auth.local_mode():
        st.subheader("Willkommen bei SmartResume")
        st.write("Schön, dass du da bist. Gib deine E-Mail-Adresse ein – dann geht's los.")
    elif setup:
        st.subheader("Ersteinrichtung")
        st.write("Melde dich mit deiner E-Mail an – dieses erste Konto erhält Administratorrechte.")
    elif BR["tagline"]:
        st.caption(BR["tagline"])
    if err := st.session_state.pop("login_error", None):
        st.error(err)
    if auth.local_mode() and not auth.local_access_ok(st.query_params.get("k", "")):
        st.info("Bitte öffne SmartResume über das Startmenü bzw. die SmartResume-Verknüpfung.",
                icon=":material/lock:")
    elif auth.local_mode():
        _local_step()
    elif st.session_state.get("login_email"):
        _code_step(st.session_state.login_email)
    else:
        _email_step(setup)
    if BR["support_email"]:
        st.caption(f"Hilfe: {BR['support_email']}")


# ---------------------------------------------------------------------------
# Hauptnavigation
# ---------------------------------------------------------------------------
def _main() -> None:
    from smartresume.ui import (admin_page, generate_page, info_page, jobs_page, profile_page, settings_page,
                                setup_page, tracking_page)

    user = st.session_state.user
    pages = {"generate": ("Neue Bewerbung", ":material/edit_document:"),
             "jobs": ("Jobs finden", ":material/travel_explore:"),
             "profile": ("Mein Profil", ":material/person:"),
             "tracking": ("Meine Bewerbungen", ":material/folder_open:"),
             "settings": ("Einstellungen", ":material/settings:")}
    if auth.can_configure_ai(user):
        pages["setup"] = ("KI einrichten", ":material/key:")
    if user["is_admin"] and not auth.local_mode():          # Nutzerverwaltung nur beim Betrieb als Server
        pages["admin"] = ("Verwaltung", ":material/admin_panel_settings:")
    pages["info"] = ("Hilfe & Info", ":material/help:")
    st.session_state.setdefault("page", "generate")
    if st.session_state.page not in pages:
        st.session_state.page = "generate"

    with st.sidebar:
        _logo()
        st.caption(f"Angemeldet als **{user['email']}**")
        # Wie arbeitet die KI gerade? Auf einen Blick – damit klar ist, ob der Key aktiv ist
        from smartresume.ui.common import available_models
        models = available_models()
        if models:
            st.caption(f":green[:material/bolt:] KI automatisch: **{models[0][0]['label']}**"
                       + (f" (+{len(models) - 1} Ersatz)" if len(models) > 1 else ""))
        else:
            st.caption(":orange[:material/content_paste:] KI per Kopieren & Einfügen (kein API-Key)"
                       + (" – unter **KI einrichten** einen kostenlosen Key eintragen, dann geht alles automatisch."
                          if auth.can_configure_ai(user) else ""))
        for key, (label, icon) in pages.items():
            if st.button(label, key=f"nav_{key}", use_container_width=True, icon=icon,
                         type="primary" if st.session_state.page == key else "secondary"):
                st.session_state.page = key
                st.rerun()
        st.divider()
        if st.button("Abmelden", use_container_width=True, icon=":material/logout:"):
            auth.end_session(st.session_state.get("session_token", ""))
            st.session_state.clear()
            st.session_state.clear_cookie = True
            st.rerun()
        if BR["footer"]:
            st.caption(BR["footer"])

    {"generate": generate_page.render_page, "jobs": jobs_page.render, "profile": profile_page.render, "tracking": tracking_page.render,
     "settings": settings_page.render, "setup": setup_page.render,
     "admin": admin_page.render, "info": info_page.render}[st.session_state.page]()
    _write_cookie(st.session_state.get("session_token", ""))  # angemeldet bleiben (30 Tage)


_restore_session()
_handle_login_link()
if not st.session_state.get("user"):
    _login()
else:
    _main()
