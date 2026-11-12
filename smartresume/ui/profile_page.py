"""Profilseite: übersichtlich in 5 Bereichen, alles wird automatisch gespeichert.

Lebenslauf importieren · Persönlich (mit Foto) · Werdegang · Kenntnisse · Wünsche & Stil
"""
from __future__ import annotations

import json

import streamlit as st

from .. import auth, bridge, cv_import, db, llm
from ..profile import empty_profile, from_legacy_master, is_profile_usable, normalize_profile
from ..render import prepare_photo, prepare_signature
from .common import (branding, chat_bridge, fallback_chain, fmt_tokens, go, model_picker, notify_switch,
                     record_usage, uid)

LANG_LEVELS = ["Muttersprache", "Verhandlungssicher (C2)", "Fließend (C1)", "Sehr gut (B2)",
               "Gut (B1)", "Grundkenntnisse (A2)", "Anfänger (A1)"]
T_IMPORT, T_PERSONAL, T_CAREER, T_SKILLS, T_WISHES = TABS = [
    ":material/upload_file: Lebenslauf importieren", ":material/person: Persönlich", ":material/work: Werdegang",
    ":material/psychology: Kenntnisse", ":material/tune: Wünsche & Stil"]


def _tab_name(tab: str) -> str:
    """Reitername ohne Icon (für Fließtext)."""
    return tab.split(": ", 1)[-1]

TEMPLATES = {
    "experience": {"company": "", "role": "", "start": "", "end": "", "location": "", "bullets": []},
    "education": {"institution": "", "degree": "", "start": "", "end": "", "location": "", "details": ""},
    "skills": {"category": "", "items": []},
    "languages": {"language": "", "level": ""},
    "projects": {"name": "", "description": "", "stack": [], "highlights": []},
    "strengths": {"skill": "", "evidence": ""},
    "links": {"label": "", "url": ""},
}


# ---------------------------------------------------------------------------
# Entwurf: lebt in session_state; jede Änderung wird sofort gespeichert. `rev` erneuert die Widget-Keys,
# wenn der Entwurf von außen geändert wurde (Import, Hinzufügen, Entfernen, Verschieben).
# ---------------------------------------------------------------------------
def _load_draft(force: bool = False) -> None:
    if force or st.session_state.get("draft_uid") != uid():
        st.session_state.draft = db.get_profile(uid())["data"]
        st.session_state.draft_uid = uid()
        st.session_state.draft_rev = st.session_state.get("draft_rev", 0) + 1


def _bump() -> None:
    st.session_state.draft_rev += 1


def _k(name: str) -> str:
    return f"p{st.session_state.draft_rev}_{name}"


def _items(section: str) -> list:
    d = st.session_state.draft
    return d["personal"]["links"] if section == "links" else d[section]


def _list_action(section: str, action: str, i: int = 0) -> None:
    items = _items(section)
    if action == "del":
        items.pop(i)
    elif action == "up" and i > 0:
        items[i - 1], items[i] = items[i], items[i - 1]
    elif action == "down" and i < len(items) - 1:
        items[i + 1], items[i] = items[i], items[i + 1]
    elif action == "add":
        tpl = json.loads(json.dumps(TEMPLATES[section]))
        if section in ("experience", "education"):
            items.insert(0, tpl)          # neueste Station zuerst
        else:
            items.append(tpl)
    _bump()


def _lines(text: str) -> list[str]:
    return [x.strip(" •-\t") for x in (text or "").splitlines() if x.strip(" •-\t")]


def _row_tools(section: str, i: int, n: int, move: bool = True) -> None:
    """Kleine Werkzeugleiste: nach oben / nach unten / entfernen."""
    cols = st.columns([1, 1, 1, 5]) if move else st.columns([1, 7])
    if move:
        cols[0].button(":material/arrow_upward:", key=_k(f"{section}{i}_up"), on_click=_list_action, args=(section, "up", i),
                       disabled=i == 0, help="Nach oben")
        cols[1].button(":material/arrow_downward:", key=_k(f"{section}{i}_down"), on_click=_list_action, args=(section, "down", i),
                       disabled=i == n - 1, help="Nach unten")
    cols[2 if move else 0].button(":material/delete:", key=_k(f"{section}{i}_del"), on_click=_list_action,
                                  args=(section, "del", i), help="Entfernen")


def _add_button(section: str, label: str) -> None:
    st.button(label, key=_k(f"{section}_add"), on_click=_list_action, args=(section, "add"), icon=":material/add:")


# ---------------------------------------------------------------------------
# Vollständigkeit
# ---------------------------------------------------------------------------
def _checklist(d: dict, photo: bytes | None) -> list[tuple[str, bool, str]]:
    p = d["personal"]
    return [
        ("Vor- und Nachname", len(p["name"].split()) >= 2, T_PERSONAL),
        ("E-Mail und Telefon", bool(p["email"] and p["phone"]), T_PERSONAL),
        ("Adresse", bool(p["zip_city"]), T_PERSONAL),
        ("Bewerbungsfoto", bool(photo), T_PERSONAL),
        ("Berufserfahrung oder Ausbildung", bool(d["experience"] or d["education"]), T_CAREER),
        ("Skills", any(s["items"] for s in d["skills"]), T_SKILLS),
        ("Sprachen", bool(d["languages"]), T_SKILLS),
        ("Verfügbarkeit", bool(d["preferences"]["availability"]), T_WISHES),
    ]


def _jump(tab: str, label: str) -> None:
    st.session_state.profile_tab = tab
    st.session_state.profile_focus = label


def _focus_hint(tab: str) -> None:
    """Zeigt nach einem Klick in der Checkliste oben im Bereich, was hier fehlt."""
    focus = st.session_state.get("profile_focus")
    if focus and st.session_state.get("profile_tab") == tab:
        st.info(f"Hier ergänzen: **{focus}**", icon=":material/edit:")


def _progress(d: dict, photo: bytes | None) -> None:
    checks = _checklist(normalize_profile(d), photo)
    done = sum(ok for _, ok, _ in checks)
    missing = is_profile_usable(normalize_profile(d))
    if done == len(checks):
        st.success("Dein Profil ist vollständig – bereit für Bewerbungen.", icon=":material/check_circle:")
        return
    with st.container(border=True):
        st.progress(done / len(checks), text=f"**Profil zu {round(100 * done / len(checks))} % vollständig** "
                                             "– klicke auf einen offenen Punkt, um ihn zu ergänzen")
        if done:
            st.caption(":green[:material/check:] Erledigt: " + " · ".join(label for label, ok, _ in checks if ok))
        cols = st.columns(2)
        for i, (label, tab) in enumerate((label, tab) for label, ok, tab in checks if not ok):
            cols[i % 2].button(f"{label} · {_tab_name(tab)}", key=f"jump_{label}", on_click=_jump,
                               args=(tab, label), type="tertiary", icon=":material/radio_button_unchecked:")
        if missing:
            st.caption(":orange[:material/warning:] Pflicht für Bewerbungen: " + ", ".join(missing))


# ---------------------------------------------------------------------------
def render() -> None:
    _load_draft()
    d = st.session_state.draft
    stored = db.get_profile(uid())

    st.title("Mein Profil")
    st.caption(":material/cloud_done: Alles wird automatisch gespeichert – auch nach Abmelden oder Neustart.")
    empty = not (d["experience"] or d["education"] or d["personal"]["name"])
    # Platzhalter: Fortschritt wird erst NACH dem Auslesen aller Felder gezeichnet → aktualisiert sich live
    progress_slot = st.container()

    new = json.loads(json.dumps(d))
    # Nach dem Import: Ergebnis melden und direkt zu den übernommenen Daten springen
    if goto := st.session_state.pop("profile_goto", None):
        st.session_state.profile_tab = goto
    if flash := st.session_state.pop("profile_flash", None):
        st.success(flash, icon=":material/check_circle:")
    # Leeres Profil: mit dem Import beginnen; sonst bei den persönlichen Daten
    tabs = st.tabs(TABS, key="profile_tab", on_change="rerun", default=T_IMPORT if empty else T_PERSONAL)
    with tabs[0]:
        _cv_import(stored)
        if not st.session_state.get("cv_manual"):
            st.divider()
            _backup(stored)
    with tabs[1]:
        _focus_hint(T_PERSONAL)
        _personal(d, new, stored)
    with tabs[2]:
        _focus_hint(T_CAREER)
        _career(d, new)
    with tabs[3]:
        _focus_hint(T_SKILLS)
        _knowledge(d, new)
    with tabs[4]:
        _focus_hint(T_WISHES)
        _wishes(d, new, stored)

    with progress_slot:
        if not empty or normalize_profile(new) != normalize_profile(empty_profile()):
            _progress(new, db.get_profile(uid())["photo"])

    st.session_state.draft = new
    # Automatisch speichern: jede Änderung landet sofort in der Datenbank.
    if normalize_profile(new) != stored["data"]:
        db.save_profile(uid(), data=new)
        st.toast("Gespeichert", icon=":material/check:")


# ── Persönlich ──────────────────────────────────────────────────────────────
def _personal(d: dict, new: dict, stored: dict) -> None:
    p = new["personal"]
    c_photo, c_form = st.columns([1, 2], gap="large")
    with c_photo:
        _photo(stored)
    with c_form:
        p["name"] = st.text_input("Vor- und Nachname *", d["personal"]["name"], key=_k("name"),
                                  placeholder="Max Mustermann")
        p["headline"] = st.text_input("Berufsbezeichnung", d["personal"]["headline"], key=_k("headline"),
                                      placeholder="z. B. Wirtschaftsinformatik-Student")
        c1, c2 = st.columns(2)
        p["email"] = c1.text_input("E-Mail *", d["personal"]["email"], key=_k("email"))
        p["phone"] = c2.text_input("Telefon", d["personal"]["phone"], key=_k("phone"))
        p["street"] = c1.text_input("Straße & Nr.", d["personal"]["street"], key=_k("street"))
        p["zip_city"] = c2.text_input("PLZ & Ort", d["personal"]["zip_city"], key=_k("zip"), placeholder="50667 Köln")

    st.markdown("##### Links")
    st.caption("Portfolio, LinkedIn, GitHub, XING … – erscheinen als Symbole auf dem Deckblatt.")
    links = []
    for i, link in enumerate(d["personal"]["links"]):
        c1, c2, c3 = st.columns([2, 5, 1])
        label = c1.text_input("Bezeichnung", link["label"], key=_k(f"link{i}_label"), placeholder="LinkedIn",
                              label_visibility="collapsed")
        url = c2.text_input("Adresse", link["url"], key=_k(f"link{i}_url"), placeholder="https://…",
                            label_visibility="collapsed")
        c3.button(":material/delete:", key=_k(f"links{i}_del"), on_click=_list_action, args=("links", "del", i), help="Entfernen")
        links.append({"label": label.strip(), "url": url.strip()})
    p["links"] = links
    _add_button("links", "Link hinzufügen")

    st.markdown("##### Kurzprofil (optional)")
    new["summary"] = st.text_area("Kurzprofil", d["summary"], height=100, key=_k("summary"),
                                  label_visibility="collapsed",
                                  help="Die KI schreibt für jede Stelle ein eigenes – das hier ist nur die Grundlage.",
                                  placeholder="2–3 Sätze über dich: was du machst, was du kannst, was du suchst.")


def _photo(stored: dict) -> None:
    st.markdown("**Bewerbungsfoto**")
    if stored["photo"]:
        st.image(stored["photo"], width=150)
    else:
        st.caption("Noch kein Foto. Ein freundliches, aktuelles Foto wirkt – ist aber freiwillig.")
    # Beim Import im Lebenslauf gefundene Fotos zur Übernahme anbieten
    for i, img in enumerate(st.session_state.get("photo_candidates") or []):
        st.image(img, width=110, caption="Im Lebenslauf gefunden")
        if st.button("Als Bewerbungsfoto übernehmen", key=f"use_photo_{i}", icon=":material/check:"):
            db.save_profile(uid(), photo=prepare_photo(img))
            st.session_state.photo_candidates = []
            st.toast("Foto übernommen.", icon=":material/photo_camera:")
            st.rerun()
    up = st.file_uploader("Foto hochladen", type=["jpg", "jpeg", "png", "webp"], key="photo_up", max_upload_size=10,
                          label_visibility="collapsed")
    # Sofort übernehmen (kein zweiter Klick); file_id verhindert erneutes Verarbeiten beim nächsten Durchlauf
    if up is not None and st.session_state.get("photo_done") != up.file_id:
        try:
            db.save_profile(uid(), photo=prepare_photo(up.getvalue()))
            st.session_state.photo_done = up.file_id
            st.toast("Foto gespeichert.", icon=":material/photo_camera:")
            st.rerun()
        except Exception as e:  # noqa: BLE001 – Pillow wirft diverse Formatfehler
            st.error(f"Bild konnte nicht verarbeitet werden: {e}")
    if stored["photo"] and st.button("Foto entfernen", key="photo_del"):
        db.save_profile(uid(), photo=None)
        st.rerun()
    st.caption("Wird automatisch quadratisch zugeschnitten.")


# ── Werdegang ──────────────────────────────────────────────────────────────
def _career(d: dict, new: dict) -> None:
    st.markdown("##### Berufserfahrung")
    st.caption("Neueste Station zuerst. Pro Zeile eine Tätigkeit oder ein Erfolg – je mehr hier steht, desto "
               "besser wählt die KI pro Stelle das Passende aus.")
    _add_button("experience", "Station hinzufügen")
    n = len(d["experience"])
    for i, job in enumerate(d["experience"]):
        title = f"**{job['role'] or 'Neue Station'}** · {job['company'] or '…'}" + \
                (f" · {job['start']}–{job['end']}" if job["start"] else "")
        with st.expander(title, expanded=not job["company"]):
            e = new["experience"][i]
            c1, c2 = st.columns(2)
            e["role"] = c1.text_input("Position *", job["role"], key=_k(f"exp{i}_role"))
            e["company"] = c2.text_input("Firma *", job["company"], key=_k(f"exp{i}_company"))
            c3, c4, c5 = st.columns(3)
            e["start"] = c3.text_input("Von", job["start"], key=_k(f"exp{i}_start"), placeholder="MM/JJJJ")
            e["end"] = c4.text_input("Bis", job["end"], key=_k(f"exp{i}_end"), placeholder="MM/JJJJ oder Heute")
            e["location"] = c5.text_input("Ort", job["location"], key=_k(f"exp{i}_loc"))
            e["bullets"] = _lines(st.text_area("Tätigkeiten & Erfolge (eine pro Zeile)", "\n".join(job["bullets"]),
                                               height=120, key=_k(f"exp{i}_bullets")))
            _row_tools("experience", i, n)

    st.markdown("##### Ausbildung & Studium")
    _add_button("education", "Ausbildung hinzufügen")
    n = len(d["education"])
    for i, ed in enumerate(d["education"]):
        with st.expander(f"**{ed['degree'] or 'Neuer Eintrag'}** · {ed['institution'] or '…'}",
                         expanded=not ed["institution"]):
            e = new["education"][i]
            c1, c2 = st.columns(2)
            e["degree"] = c1.text_input("Abschluss / Studiengang *", ed["degree"], key=_k(f"edu{i}_deg"))
            e["institution"] = c2.text_input("Schule / Hochschule / Betrieb *", ed["institution"],
                                             key=_k(f"edu{i}_inst"))
            c3, c4, c5 = st.columns(3)
            e["start"] = c3.text_input("Von", ed["start"], key=_k(f"edu{i}_start"))
            e["end"] = c4.text_input("Bis", ed["end"], key=_k(f"edu{i}_end"))
            e["location"] = c5.text_input("Ort", ed["location"], key=_k(f"edu{i}_loc"))
            e["details"] = st.text_input("Details (Schwerpunkt, Note …)", ed["details"], key=_k(f"edu{i}_det"))
            _row_tools("education", i, n)


# ── Kenntnisse ──────────────────────────────────────────────────────────────
def _knowledge(d: dict, new: dict) -> None:
    st.markdown("##### Skills")
    st.caption("Skill eintippen und **Enter** drücken. Die KI wählt pro Stelle nur aus diesen Einträgen aus und "
               "erfindet keine neuen. Jeder Skill zählt nur einmal.")
    skills, seen, dupes = [], {}, []
    for i, cat in enumerate(d["skills"]):
        with st.container(border=True):
            c1, c2 = st.columns([6, 1])
            name = c1.text_input("Kategorie", cat["category"], key=_k(f"sk{i}_cat"),
                                 placeholder="Kategorie, z. B. Programmierung", label_visibility="collapsed")
            c2.button(":material/delete:", key=_k(f"skills{i}_del"), on_click=_list_action, args=("skills", "del", i),
                      help="Kategorie entfernen")
            items = st.multiselect("Skills", options=cat["items"], default=cat["items"], accept_new_options=True,
                                   key=_k(f"sk{i}_items"), placeholder="Skill eintippen + Enter",
                                   label_visibility="collapsed")
        kept = []
        for it in items:
            it = it.strip()
            if not it:
                continue
            if it.lower() in seen:
                dupes.append(f"„{it}“ steht schon unter {seen[it.lower()] or 'einer anderen Kategorie'}")
                continue
            seen[it.lower()] = name.strip()
            kept.append(it)
        skills.append({"category": name.strip(), "items": kept})
    new["skills"] = skills
    if dupes:   # doppelte Skills sofort entfernen und Felder neu aufbauen
        st.session_state.draft = new
        st.session_state.skill_dupes = dupes
        _bump()
        st.rerun()
    for msg in st.session_state.pop("skill_dupes", []):
        st.info(msg + " – nicht doppelt übernommen.", icon=":material/info:")
    _add_button("skills", "Kategorie hinzufügen")

    st.markdown("##### Sprachen")
    langs = []
    for i, lang in enumerate(d["languages"]):
        c1, c2, c3 = st.columns([3, 3, 1])
        name = c1.text_input("Sprache", lang["language"], key=_k(f"lang{i}"), placeholder="z. B. Englisch",
                             label_visibility="collapsed")
        levels = LANG_LEVELS if lang["level"] in LANG_LEVELS or not lang["level"] else [lang["level"]] + LANG_LEVELS
        level = c2.selectbox("Niveau", levels, index=levels.index(lang["level"]) if lang["level"] in levels else 3,
                             key=_k(f"lang{i}_lvl"), label_visibility="collapsed")
        c3.button(":material/delete:", key=_k(f"languages{i}_del"), on_click=_list_action, args=("languages", "del", i),
                  help="Entfernen")
        langs.append({"language": name.strip(), "level": level})
    new["languages"] = langs
    _add_button("languages", "Sprache hinzufügen")

    st.markdown("##### Zertifikate & Weiterbildungen")
    new["certificates"] = _lines(st.text_area("Zertifikate", "\n".join(d["certificates"]), height=90,
                                              key=_k("certs"), label_visibility="collapsed",
                                              placeholder="Eine pro Zeile, z. B. „Scrum Master (PSM I), 2025“"))

    st.markdown("##### Projekte")
    st.caption("Eigene, studentische oder berufliche Projekte – gut für Berufseinsteiger.")
    n = len(d["projects"])
    for i, pr in enumerate(d["projects"]):
        with st.expander(f"**{pr['name'] or 'Neues Projekt'}**", expanded=not pr["name"]):
            e = new["projects"][i]
            e["name"] = st.text_input("Name", pr["name"], key=_k(f"prj{i}_name"))
            e["description"] = st.text_input("Worum geht es?", pr["description"], key=_k(f"prj{i}_desc"))
            e["stack"] = st.multiselect("Technologien / Werkzeuge", options=pr["stack"], default=pr["stack"],
                                        accept_new_options=True, key=_k(f"prj{i}_stack"),
                                        placeholder="eintippen + Enter")
            e["highlights"] = _lines(st.text_area("Ergebnisse (eines pro Zeile)", "\n".join(pr["highlights"]),
                                                  height=80, key=_k(f"prj{i}_hl")))
            _row_tools("projects", i, n, move=False)
    _add_button("projects", "Projekt hinzufügen")

    st.markdown("##### Stärken mit Beleg")
    st.caption("Nur belegte Stärken landen im Anschreiben – z. B. *Organisation* → *Events mit 2.000 Gästen geplant*.")
    strengths = []
    for i, s in enumerate(d["strengths"]):
        c1, c2, c3 = st.columns([2, 5, 1])
        skill = c1.text_input("Stärke", s["skill"], key=_k(f"str{i}"), placeholder="Stärke",
                              label_visibility="collapsed")
        ev = c2.text_input("Beleg", s["evidence"], key=_k(f"str{i}_ev"), placeholder="Konkreter Beleg",
                           label_visibility="collapsed")
        c3.button(":material/delete:", key=_k(f"strengths{i}_del"), on_click=_list_action, args=("strengths", "del", i),
                  help="Entfernen")
        strengths.append({"skill": skill.strip(), "evidence": ev.strip()})
    new["strengths"] = strengths
    _add_button("strengths", "Stärke hinzufügen")


# ── Wünsche & Stil ──────────────────────────────────────────────────────────
def _wishes(d: dict, new: dict, stored: dict) -> None:
    st.markdown("##### Rahmenbedingungen")
    st.caption("Werden nur genannt, wenn die Stellenanzeige danach fragt.")
    pr = new["preferences"]
    c1, c2 = st.columns(2)
    pr["availability"] = c1.text_input("Verfügbar ab", d["preferences"]["availability"], key=_k("avail"),
                                       placeholder="sofort / 01.03.2027")
    pr["notice_period"] = c2.text_input("Kündigungsfrist", d["preferences"]["notice_period"], key=_k("notice"),
                                        placeholder="3 Monate zum Quartalsende")
    pr["salary_expectation"] = c1.text_input("Gehaltsvorstellung", d["preferences"]["salary_expectation"],
                                             key=_k("salary"), placeholder="45.000 € brutto jährlich")
    pr["hours_per_week"] = c2.text_input("Wochenstunden (Teilzeit/Werkstudent)", d["preferences"]["hours_per_week"],
                                         key=_k("hours"), placeholder="20")
    pr["student_status"] = st.text_input("Studium (wichtig für Werkstudentenstellen)",
                                         d["preferences"]["student_status"], key=_k("student"),
                                         placeholder="Eingeschrieben, B.Sc. Wirtschaftsinformatik, 4. Semester")

    st.markdown("##### Schreibstil (optional)")
    with st.expander("Damit das Anschreiben nach dir klingt"):
        ws = new["writing_style"]
        ws["tone"] = st.text_input("Ton", d["writing_style"]["tone"], key=_k("tone"),
                                   placeholder="Direkt, bodenständig, kurze Sätze")
        ws["own_words"] = _lines(st.text_area("Typische Sätze von dir (einer pro Zeile)",
                                              "\n".join(d["writing_style"]["own_words"]), key=_k("own"), height=90))
        ws["philosophy"] = st.text_area("Arbeitsweise / Philosophie", d["writing_style"]["philosophy"],
                                        key=_k("philo"), height=80)
        ws["forbidden_phrases"] = _lines(st.text_area("Phrasen, die nie vorkommen sollen (eine pro Zeile)",
                                                      "\n".join(d["writing_style"]["forbidden_phrases"]),
                                                      key=_k("forbidden"), height=80))

    st.markdown("##### Design der Unterlagen")
    presets = branding()["accent_presets"]
    current = new["design"]["accent_color"] or branding()["accent_color"]
    names = list(presets) + ["Eigene Farbe"]
    default = next((n for n, c in presets.items() if c.lower() == current.lower()), "Eigene Farbe")
    c1, c2 = st.columns([3, 1])
    choice = c1.selectbox("Akzentfarbe", names, index=names.index(default), key=_k("accent_preset"))
    color = presets.get(choice) or c2.color_picker("Eigene Farbe", current, key=_k("accent_custom"))
    if choice != "Eigene Farbe":
        c2.color_picker("Vorschau", color, disabled=True, key=_k(f"accent_prev_{choice}"))
    new["design"]["accent_color"] = color

    st.markdown("**Unterschrift** (optional, unter dem Anschreiben)")
    c1, c2 = st.columns([1, 2])
    with c1:
        if stored["signature"]:
            st.image(stored["signature"], width=150)
            if st.button("Unterschrift entfernen", key="sig_del"):
                db.save_profile(uid(), signature=None)
                st.rerun()
        else:
            st.caption("Noch keine Unterschrift.")
    with c2:
        up = st.file_uploader("Scan/Foto der Unterschrift", type=["png", "jpg", "jpeg"], key="sig_up", max_upload_size=10,
                              label_visibility="collapsed")
        if up is not None and st.session_state.get("sig_done") != up.file_id:
            try:
                db.save_profile(uid(), signature=prepare_signature(up.getvalue()))
                st.session_state.sig_done = up.file_id
                st.toast("Unterschrift gespeichert.", icon=":material/check:")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Bild konnte nicht verarbeitet werden: {e}")
        st.caption("Auf weißem Papier unterschreiben, abfotografieren – der Hintergrund wird automatisch entfernt.")


# ── Import ──────────────────────────────────────────────────────────────────
MODES = ["Ergänzen – Vorhandenes bleibt", "Ersetzen – Profil neu aus dem Lebenslauf"]


def _apply_cv(incoming: dict, mode: str, source: str) -> None:
    """Übernimmt den ausgelesenen Lebenslauf ins Profil und springt zu den persönlichen Daten."""
    base = st.session_state.draft
    merged = incoming if mode.startswith("Ersetzen") else cv_import.merge_profiles(base, incoming)
    # Stil & Design bleiben beim Ersetzen erhalten
    merged["writing_style"] = normalize_profile(base)["writing_style"]
    merged["design"] = normalize_profile(base)["design"]
    db.save_profile(uid(), data=merged)
    _load_draft(force=True)
    st.session_state.cv_manual = None
    photo = " Im Lebenslauf wurde ein Foto gefunden – du kannst es links übernehmen." \
        if st.session_state.get("photo_candidates") else ""
    st.session_state.profile_flash = (
        f"**Lebenslauf übernommen** ({source}): {len(incoming['experience'])} Stationen, "
        f"{len(incoming['education'])} Ausbildungen, {len(incoming['skills'])} Skill-Kategorien. "
        f"Bitte die Bereiche kurz durchsehen und Fehlendes ergänzen.{photo}")
    st.session_state.profile_goto = T_PERSONAL
    st.rerun()


def _cv_import(stored: dict) -> None:
    if st.session_state.get("cv_manual"):
        _cv_manual(st.session_state.cv_manual)
        return

    st.markdown("#### Profil aus deinem Lebenslauf füllen")
    st.caption("Lade deinen vorhandenen Lebenslauf hoch. SmartResume liest ihn aus und trägt Kontaktdaten, "
               "Werdegang, Ausbildung, Skills und Sprachen in die Bereiche dieses Profils ein – du prüfst danach nur "
               "noch und ergänzt, was fehlt. Kein Lebenslauf zur Hand? Dann die Bereiche einfach selbst ausfüllen.")
    f = st.file_uploader("Lebenslauf (PDF, DOCX oder TXT)", type=["pdf", "docx", "txt"], key="cv_upload", max_upload_size=10)
    has_data = bool(st.session_state.draft["experience"] or st.session_state.draft["education"])
    mode = st.radio("Dein Profil enthält schon Daten. Was soll mit ihnen passieren?", MODES, key="cv_mode") \
        if has_data else MODES[1]
    picked = model_picker("cv_model", "Modell zum Auslesen",
                          "Schnelle Modelle (Flash-Lite, Groq) reichen für das Auslesen völlig.")
    if picked is None:
        _no_ai_hint()

    run_upload = st.button("Lebenslauf auslesen und Profil füllen", disabled=f is None, type="primary",
                           use_container_width=True, icon=":material/document_scanner:")
    run_stored = False
    if stored["cv_text"]:
        run_stored = st.button(f"Gespeicherten Lebenslauf erneut auslesen ({stored['cv_filename']})",
                               use_container_width=True, icon=":material/refresh:")
    if run_upload or run_stored:
        text = ""
        try:
            if run_upload:
                data = f.getvalue()
                text = cv_import.extract_text(f.name, data)
                st.session_state.photo_candidates = cv_import.extract_photo_candidates(f.name, data)
                db.save_profile(uid(), cv_text=text, cv_filename=f.name)
            else:
                text = stored["cv_text"]
            if picked is None:
                st.session_state.cv_manual = {"text": text, "mode": mode, "reason": ""}
                st.rerun()
            with st.spinner("Lebenslauf wird ausgelesen …"):
                (incoming, tokens), (cfg, key) = llm.with_fallback(
                    fallback_chain(picked), lambda c, k: cv_import.parse_cv_with_ai(text, c, k),
                    on_switch=notify_switch)
            record_usage("cv_import", cfg, tokens)
            _apply_cv(incoming, mode, f"{cfg['label']}, {fmt_tokens(tokens)} Tokens")
        except cv_import.CVImportError as e:
            st.error(str(e), icon=":material/error:")
        except llm.LLMError as e:
            st.session_state.cv_manual = {"text": text, "mode": mode,
                                          "reason": f"Die verbundene KI ist gerade nicht erreichbar ({e})."}
            st.rerun()

    if stored["cv_text"]:
        with st.expander("Text des gespeicherten Lebenslaufs ansehen", icon=":material/description:"):
            st.text(stored["cv_text"][:5000])


def _no_ai_hint() -> None:
    """Ohne verbundene KI: vorab erklären, wie das Auslesen trotzdem funktioniert."""
    st.info("**Es ist noch keine KI verbunden.** Das Auslesen funktioniert trotzdem – über dein eigenes, kostenloses "
            "Gemini- oder ChatGPT-Konto: SmartResume erstellt einen fertigen Auftrag, du fügst ihn dort ein und "
            "kopierst die Antwort zurück. Das dauert etwa eine Minute.", icon=":material/info:")
    if auth.can_configure_ai(st.session_state.user) and st.button(
            "Stattdessen KI verbinden – dann läuft das Auslesen automatisch", icon=":material/key:"):
        go("setup")


def _cv_manual(m: dict) -> None:
    """Lebenslauf über Gemini/ChatGPT auslesen (Abo-Modus)."""
    st.markdown("#### Lebenslauf mit Gemini oder ChatGPT auslesen")
    if m["reason"]:
        st.warning(m["reason"], icon=":material/cloud_off:")
    st.caption("Gemini oder ChatGPT liest deinen Lebenslauf und gibt die Daten in einem festen Format zurück. "
               "SmartResume prüft die Antwort und trägt alles in dein Profil ein. Kostenlos mit deinem eigenen "
               "Konto – es wird nichts automatisch verschickt.")
    with st.container(border=True):
        system, user = cv_import.cv_prompts(m["text"])
        answer = chat_bridge(bridge.chat_prompt(system, user), "cv", validate=cv_import.validate_cv,
                             submit="Antwort übernehmen und Profil füllen")
    if answer is not None:
        _apply_cv(normalize_profile(answer), m["mode"], "Gemini/ChatGPT")
    if st.button("Abbrechen", key="cv_manual_cancel", icon=":material/close:"):
        st.session_state.cv_manual = None
        st.rerun()


def _backup(stored: dict) -> None:
    st.markdown("##### Profil sichern & übertragen")
    st.caption("Sichert dein Profil als Datei – z. B. für einen anderen Rechner. Eine komplette Sicherung mit Foto, "
               "Unterschrift und allen Bewerbungen gibt es unter **Einstellungen → Daten & Sicherung**.")
    c1, c2 = st.columns(2)
    c1.download_button("Profil als Datei sichern", json.dumps(stored["data"], ensure_ascii=False, indent=2),
                       file_name="profil.json", mime="application/json", use_container_width=True,
                       icon=":material/download:")
    jf = c2.file_uploader("Gesicherte Profil-Datei laden", type=["json"], key="json_upload", max_upload_size=10)
    if jf is not None and c2.button("Profil-Datei übernehmen", use_container_width=True, icon=":material/upload:"):
        try:
            raw = json.loads(jf.getvalue().decode("utf-8"))
            prof = from_legacy_master(raw) if "personal_info" in raw else normalize_profile(raw)
            db.save_profile(uid(), data=prof)
            _load_draft(force=True)
            st.session_state.profile_flash = "Profil-Datei übernommen."
            st.rerun()
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
            st.error(f"Ungültige Datei: {e}")
    with st.expander("Profil komplett leeren", icon=":material/delete_forever:"):
        st.warning("Löscht alle Profildaten (Foto, Unterschrift und Bewerbungen bleiben).")
        if st.button("Ja, Profil leeren", type="primary"):
            db.save_profile(uid(), data=empty_profile(), cv_text="", cv_filename="")
            _load_draft(force=True)
            st.rerun()
