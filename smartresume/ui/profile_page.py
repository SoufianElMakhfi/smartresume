"""Profilseite: CV importieren oder manuell eingeben, Foto, Skills, Stil."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from .. import bridge, cv_import, db, llm
from ..profile import empty_profile, from_legacy_master, is_profile_usable, normalize_profile
from ..render import prepare_photo, prepare_signature
from .common import (branding, chat_bridge, fallback_chain, fmt_tokens, model_picker, notify_switch,
                     record_usage, uid)

LANG_LEVELS = ["Muttersprache", "Verhandlungssicher (C2)", "Fließend (C1)", "Sehr gut (B2)",
               "Gut (B1)", "Grundkenntnisse (A2)", "Anfänger (A1)"]


# ---------------------------------------------------------------------------
# Entwurfs-Verwaltung: Der Entwurf lebt in session_state und wird erst mit
# "Speichern" in die DB geschrieben. `rev` erneuert die Widget-Keys, wenn der
# Entwurf von außen geändert wurde (Import, Entfernen, Verschieben).
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


def _list_action(section: str, action: str, i: int) -> None:
    items = st.session_state.draft[section]
    if action == "del":
        items.pop(i)
    elif action == "up" and i > 0:
        items[i - 1], items[i] = items[i], items[i - 1]
    elif action == "down" and i < len(items) - 1:
        items[i + 1], items[i] = items[i], items[i + 1]
    elif action == "add":
        tpl = {"experience": {"company": "", "role": "", "start": "", "end": "", "location": "", "bullets": []},
               "education": {"institution": "", "degree": "", "start": "", "end": "", "location": "",
                             "details": ""}}[section]
        items.insert(0, tpl)
    _bump()


def _table(rows: list[dict], columns: dict, key: str, column_config: dict | None = None) -> list[dict]:
    """Editierbare Tabelle. `columns` mappt Feldname → Spaltentitel."""
    df = pd.DataFrame([{title: r.get(field, "") for field, title in columns.items()} for r in rows],
                      columns=list(columns.values()))
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, use_container_width=True,
                            key=_k(key), column_config=column_config)
    out = []
    for rec in edited.fillna("").to_dict("records"):
        row = {field: str(rec.get(title, "")).strip() for field, title in columns.items()}
        if any(row.values()):
            out.append(row)
    return out


def _lines(text: str) -> list[str]:
    return [x.strip(" •-\t") for x in (text or "").splitlines() if x.strip(" •-\t")]


def _csv(text: str) -> list[str]:
    return [x.strip() for x in (text or "").split(",") if x.strip()]


# ---------------------------------------------------------------------------
def render() -> None:
    _load_draft()
    d = st.session_state.draft
    stored = db.get_profile(uid())

    st.title("Mein Profil")
    missing = is_profile_usable(normalize_profile(d))
    if missing:
        st.info("Noch nicht bereit für Bewerbungen. Es fehlt: **" + ", ".join(missing) + "**. "
                "Am schnellsten: Lebenslauf im Tab *Import* hochladen.", icon="ℹ️")

    tabs = st.tabs(["📥 Import", "👤 Persönliches", "💼 Erfahrung", "🎓 Ausbildung", "🛠 Skills",
                    "🚀 Projekte & Stärken", "⚙️ Rahmen & Stil", "🖼 Foto & Design"])
    new = json.loads(json.dumps(d))

    # ── Import ────────────────────────────────────────────────────────────
    with tabs[0]:
        _import_tab(stored)

    # ── Persönliches ──────────────────────────────────────────────────────
    with tabs[1]:
        p = new["personal"]
        c1, c2 = st.columns(2)
        p["name"] = c1.text_input("Vollständiger Name *", d["personal"]["name"], key=_k("name"))
        p["headline"] = c2.text_input("Berufsbezeichnung", d["personal"]["headline"], key=_k("headline"),
                                      placeholder="z.B. Kaufmann für Büromanagement")
        p["email"] = c1.text_input("E-Mail *", d["personal"]["email"], key=_k("email"))
        p["phone"] = c2.text_input("Telefon", d["personal"]["phone"], key=_k("phone"))
        p["street"] = c1.text_input("Straße & Nr.", d["personal"]["street"], key=_k("street"))
        p["zip_city"] = c2.text_input("PLZ & Ort", d["personal"]["zip_city"], key=_k("zip"),
                                      placeholder="50667 Köln")
        st.markdown("**Links** (Portfolio, LinkedIn, GitHub, XING …)")
        p["links"] = _table(d["personal"]["links"], {"label": "Bezeichnung", "url": "URL"}, "links")
        new["summary"] = st.text_area("Kurzprofil (optional – die KI schreibt pro Stelle ein eigenes)",
                                      d["summary"], height=100, key=_k("summary"))

    # ── Erfahrung ─────────────────────────────────────────────────────────
    with tabs[2]:
        st.caption("Neueste Station zuerst. Stichpunkte: eine Tätigkeit pro Zeile – je mehr Substanz hier steht, "
                   "desto besser kann die KI pro Stelle die passendsten auswählen.")
        st.button("＋ Station hinzufügen", on_click=_list_action, args=("experience", "add", 0), key=_k("exp_add"))
        for i, job in enumerate(d["experience"]):
            title = f"{job['role'] or 'Neue Station'} – {job['company'] or '…'}"
            with st.expander(title, expanded=not job["company"]):
                c1, c2 = st.columns(2)
                e = new["experience"][i]
                e["role"] = c1.text_input("Position *", job["role"], key=_k(f"exp{i}_role"))
                e["company"] = c2.text_input("Firma *", job["company"], key=_k(f"exp{i}_company"))
                c3, c4, c5 = st.columns(3)
                e["start"] = c3.text_input("Von (MM/JJJJ)", job["start"], key=_k(f"exp{i}_start"))
                e["end"] = c4.text_input("Bis (MM/JJJJ oder Heute)", job["end"], key=_k(f"exp{i}_end"))
                e["location"] = c5.text_input("Ort", job["location"], key=_k(f"exp{i}_loc"))
                e["bullets"] = _lines(st.text_area("Tätigkeiten & Erfolge (eine pro Zeile)",
                                                   "\n".join(job["bullets"]), height=120,
                                                   key=_k(f"exp{i}_bullets")))
                b1, b2, b3, _ = st.columns([1, 1, 1, 4])
                b1.button("↑", key=_k(f"exp{i}_up"), on_click=_list_action, args=("experience", "up", i))
                b2.button("↓", key=_k(f"exp{i}_down"), on_click=_list_action, args=("experience", "down", i))
                b3.button("🗑", key=_k(f"exp{i}_del"), on_click=_list_action, args=("experience", "del", i),
                          help="Station entfernen")

    # ── Ausbildung ────────────────────────────────────────────────────────
    with tabs[3]:
        st.button("＋ Ausbildung hinzufügen", on_click=_list_action, args=("education", "add", 0),
                  key=_k("edu_add"))
        for i, ed in enumerate(d["education"]):
            with st.expander(f"{ed['degree'] or 'Neuer Eintrag'} – {ed['institution'] or '…'}",
                             expanded=not ed["institution"]):
                c1, c2 = st.columns(2)
                e = new["education"][i]
                e["degree"] = c1.text_input("Abschluss / Studiengang *", ed["degree"], key=_k(f"edu{i}_deg"))
                e["institution"] = c2.text_input("Schule / Hochschule / Betrieb *", ed["institution"],
                                                 key=_k(f"edu{i}_inst"))
                c3, c4, c5 = st.columns(3)
                e["start"] = c3.text_input("Von", ed["start"], key=_k(f"edu{i}_start"))
                e["end"] = c4.text_input("Bis", ed["end"], key=_k(f"edu{i}_end"))
                e["location"] = c5.text_input("Ort", ed["location"], key=_k(f"edu{i}_loc"))
                e["details"] = st.text_input("Details (Schwerpunkt, Note …)", ed["details"], key=_k(f"edu{i}_det"))
                b1, b2, b3, _ = st.columns([1, 1, 1, 4])
                b1.button("↑", key=_k(f"edu{i}_up"), on_click=_list_action, args=("education", "up", i))
                b2.button("↓", key=_k(f"edu{i}_down"), on_click=_list_action, args=("education", "down", i))
                b3.button("🗑", key=_k(f"edu{i}_del"), on_click=_list_action, args=("education", "del", i))

    # ── Skills ────────────────────────────────────────────────────────────
    with tabs[4]:
        st.markdown("**Fähigkeiten** – Kategorie + Einträge mit Komma getrennt. Die KI wählt pro Stelle "
                    "nur aus diesen Einträgen aus und erfindet keine neuen.")
        rows = [{"category": s["category"], "items": ", ".join(s["items"])} for s in d["skills"]]
        new["skills"] = [{"category": r["category"] or "Weitere Kenntnisse", "items": _csv(r["items"])}
                         for r in _table(rows, {"category": "Kategorie", "items": "Einträge (kommagetrennt)"},
                                         "skills")]
        st.markdown("**Sprachen**")
        new["languages"] = _table(d["languages"], {"language": "Sprache", "level": "Niveau"}, "langs",
                                  column_config={"Niveau": st.column_config.SelectboxColumn(
                                      options=LANG_LEVELS + sorted({l["level"] for l in d["languages"]
                                                                    if l["level"] not in LANG_LEVELS}))})
        new["certificates"] = _lines(st.text_area("Zertifikate & Weiterbildungen (eine pro Zeile)",
                                                  "\n".join(d["certificates"]), height=90, key=_k("certs")))

    # ── Projekte & Stärken ───────────────────────────────────────────────
    with tabs[5]:
        st.markdown("**Projekte** (eigene, studentische oder berufliche)")
        rows = [{"name": p["name"], "description": p["description"], "stack": ", ".join(p["stack"]),
                 "highlights": "; ".join(p["highlights"])} for p in d["projects"]]
        new["projects"] = [{"name": r["name"], "description": r["description"], "stack": _csv(r["stack"]),
                            "highlights": [h.strip() for h in r["highlights"].split(";") if h.strip()]}
                           for r in _table(rows, {"name": "Name", "description": "Beschreibung",
                                                  "stack": "Technologien (Komma)", "highlights": "Ergebnisse (;)"},
                                           "projects")]
        st.markdown("**Stärken mit Beleg** – z.B. *Organisation* → *Events mit bis zu 2.000 Gästen geplant*. "
                    "Nur belegte Stärken landen im Anschreiben.")
        new["strengths"] = _table(d["strengths"], {"skill": "Stärke", "evidence": "Konkreter Beleg"}, "strengths")

    # ── Rahmen & Stil ─────────────────────────────────────────────────────
    with tabs[6]:
        st.markdown("**Rahmenbedingungen** – werden nur genannt, wenn die Stellenanzeige danach fragt.")
        pr = new["preferences"]
        c1, c2 = st.columns(2)
        pr["availability"] = c1.text_input("Verfügbar ab", d["preferences"]["availability"], key=_k("avail"),
                                           placeholder="sofort / 01.03.2027")
        pr["notice_period"] = c2.text_input("Kündigungsfrist", d["preferences"]["notice_period"],
                                            key=_k("notice"), placeholder="3 Monate zum Quartalsende")
        pr["salary_expectation"] = c1.text_input("Gehaltsvorstellung", d["preferences"]["salary_expectation"],
                                                 key=_k("salary"), placeholder="45.000 € brutto jährlich")
        pr["hours_per_week"] = c2.text_input("Wochenstunden (Teilzeit/Werkstudent)",
                                             d["preferences"]["hours_per_week"], key=_k("hours"),
                                             placeholder="20")
        pr["student_status"] = st.text_input("Studium (für Werkstudentenstellen)",
                                             d["preferences"]["student_status"], key=_k("student"),
                                             placeholder="Eingeschrieben, B.Sc. Wirtschaftsinformatik, 4. Semester")
        st.divider()
        st.markdown("**Schreibstil** (optional) – damit das Anschreiben nach dir klingt.")
        ws = new["writing_style"]
        ws["tone"] = st.text_input("Ton", d["writing_style"]["tone"], key=_k("tone"),
                                   placeholder="Direkt, bodenständig, kurze Sätze")
        ws["own_words"] = _lines(st.text_area("Typische Sätze von dir (einer pro Zeile)",
                                              "\n".join(d["writing_style"]["own_words"]), key=_k("own"),
                                              height=90))
        ws["philosophy"] = st.text_area("Arbeitsweise / Philosophie", d["writing_style"]["philosophy"],
                                        key=_k("philo"), height=80)
        ws["forbidden_phrases"] = _lines(st.text_area("Phrasen, die nie vorkommen sollen (eine pro Zeile)",
                                                      "\n".join(d["writing_style"]["forbidden_phrases"]),
                                                      key=_k("forbidden"), height=80))

    # ── Foto & Design ─────────────────────────────────────────────────────
    with tabs[7]:
        _photo_tab(stored, new)

    st.session_state.draft = new
    st.divider()
    dirty = normalize_profile(new) != stored["data"]
    c1, c2 = st.columns([1, 1])
    if c1.button("💾 Profil speichern", type="primary", use_container_width=True, disabled=not dirty):
        db.save_profile(uid(), data=new)
        _load_draft(force=True)
        st.toast("Profil gespeichert.", icon="✅")
        st.rerun()
    if c2.button("↩ Änderungen verwerfen", use_container_width=True, disabled=not dirty):
        _load_draft(force=True)
        st.rerun()
    if dirty:
        st.caption("⚠️ Ungespeicherte Änderungen.")


def _apply_cv(incoming: dict, mode: str, source: str) -> None:
    base = st.session_state.draft
    merged = incoming if mode.startswith("Ersetzen") else cv_import.merge_profiles(base, incoming)
    # Stil & Design bleiben beim Ersetzen erhalten
    merged["writing_style"] = normalize_profile(base)["writing_style"]
    merged["design"] = normalize_profile(base)["design"]
    db.save_profile(uid(), data=merged)
    _load_draft(force=True)
    st.success(f"Übernommen ({source}): {len(incoming['experience'])} Stationen, "
               f"{len(incoming['education'])} Ausbildungen, {len(incoming['skills'])} Skill-Kategorien. "
               "Bitte die Tabs kurz prüfen.")


def _import_tab(stored: dict) -> None:
    st.markdown("**Lebenslauf hochladen** (PDF, DOCX oder TXT). Die KI liest ihn **einmal** aus – danach "
                "nutzt jede Bewerbung nur noch dein kompaktes Profil. Das spart pro Bewerbung viele Tokens.")
    f = st.file_uploader("Lebenslauf", type=["pdf", "docx", "txt"], key="cv_upload",
                         label_visibility="collapsed")
    mode = st.radio("Bestehendes Profil", ["Ergänzen (Vorhandenes bleibt)", "Ersetzen"], horizontal=True,
                    key="cv_mode")
    picked = model_picker("cv_model", "Modell zum Auslesen",
                          "Schnelle Modelle (Flash-Lite, Groq) reichen für das Auslesen völlig.")
    c1, c2 = st.columns(2)
    run_upload = c1.button("🔍 Hochgeladenen CV auslesen", disabled=f is None,
                           use_container_width=True, type="primary")
    run_stored = c2.button("🔁 Gespeicherten CV erneut auslesen", disabled=not stored["cv_text"],
                           use_container_width=True)
    if run_upload or run_stored:
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
            else:
                with st.spinner("Lebenslauf wird ausgelesen …"):
                    (incoming, tokens), (cfg, key) = llm.with_fallback(
                        fallback_chain(picked), lambda c, k: cv_import.parse_cv_with_ai(text, c, k),
                        on_switch=notify_switch)
                record_usage("cv_import", cfg, tokens)
                _apply_cv(incoming, mode, f"{fmt_tokens(tokens)} Tokens")
        except cv_import.CVImportError as e:
            st.error(str(e))
        except llm.LLMError as e:
            st.session_state.cv_manual = {"text": text, "mode": mode,
                                          "reason": f"Die KI ist gerade nicht verfügbar ({e})."}

    m = st.session_state.get("cv_manual")
    if m:
        with st.container(border=True):
            st.markdown("**Lebenslauf mit Gemini oder ChatGPT auslesen** (kostenlos, mit deinem eigenen Konto)")
            if m["reason"]:
                st.caption(m["reason"])
            system, user = cv_import.cv_prompts(m["text"])
            answer = chat_bridge(bridge.chat_prompt(system, user), "cv", validate=cv_import.validate_cv)
            if answer is not None:
                st.session_state.cv_manual = None
                _apply_cv(normalize_profile(answer), m["mode"], "Gemini/ChatGPT")
            if st.button("Abbrechen", key="cv_manual_cancel"):
                st.session_state.cv_manual = None
                st.rerun()

    for i, img in enumerate(st.session_state.get("photo_candidates") or []):
        st.markdown("**Foto im Lebenslauf gefunden:**")
        c1, c2 = st.columns([1, 3])
        c1.image(img, width=110)
        if c2.button("Als Bewerbungsfoto übernehmen", key=f"use_photo_{i}"):
            db.save_profile(uid(), photo=prepare_photo(img))
            st.session_state.photo_candidates = []
            st.toast("Foto übernommen.", icon="🖼")
            st.rerun()

    if stored["cv_text"]:
        with st.expander(f"Gespeicherter Lebenslauf-Text ({stored['cv_filename']})"):
            st.text(stored["cv_text"][:5000])

    st.divider()
    st.markdown("**Profil sichern / übertragen**")
    c1, c2 = st.columns(2)
    c1.download_button("⬇ Profil als JSON exportieren", json.dumps(stored["data"], ensure_ascii=False, indent=2),
                       file_name="profil.json", mime="application/json", use_container_width=True)
    jf = c2.file_uploader("Profil-JSON importieren", type=["json"], key="json_upload")
    if jf is not None and c2.button("JSON übernehmen", use_container_width=True):
        try:
            raw = json.loads(jf.getvalue().decode("utf-8"))
            prof = from_legacy_master(raw) if "personal_info" in raw else normalize_profile(raw)
            db.save_profile(uid(), data=prof)
            _load_draft(force=True)
            st.success("Profil importiert.")
            st.rerun()
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
            st.error(f"Ungültige Datei: {e}")
    if st.button("🧹 Profil komplett leeren"):
        st.session_state.confirm_clear = True
    if st.session_state.get("confirm_clear"):
        st.warning("Wirklich alle Profildaten löschen? (Foto & Bewerbungen bleiben)")
        if st.button("Ja, leeren", type="primary"):
            db.save_profile(uid(), data=empty_profile(), cv_text="", cv_filename="")
            st.session_state.confirm_clear = False
            _load_draft(force=True)
            st.rerun()


def _photo_tab(stored: dict, new: dict) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Bewerbungsfoto**")
        if stored["photo"]:
            st.image(stored["photo"], width=160)
            if st.button("Foto entfernen"):
                db.save_profile(uid(), photo=None)
                st.rerun()
        up = st.file_uploader("Foto hochladen (JPG/PNG)", type=["jpg", "jpeg", "png", "webp"], key="photo_up")
        if up is not None and st.button("Foto übernehmen", type="primary"):
            try:
                db.save_profile(uid(), photo=prepare_photo(up.getvalue()))
                st.rerun()
            except Exception as e:  # noqa: BLE001 – Pillow wirft diverse Formatfehler
                st.error(f"Bild konnte nicht verarbeitet werden: {e}")
        st.caption("Wird automatisch quadratisch zugeschnitten und rund auf dem Deckblatt angezeigt.")
    with c2:
        st.markdown("**Unterschrift** (optional)")
        if stored["signature"]:
            st.image(stored["signature"], width=160)
            if st.button("Unterschrift entfernen"):
                db.save_profile(uid(), signature=None)
                st.rerun()
        up = st.file_uploader("Scan/Foto der Unterschrift", type=["png", "jpg", "jpeg"], key="sig_up")
        if up is not None and st.button("Unterschrift übernehmen", type="primary"):
            try:
                db.save_profile(uid(), signature=prepare_signature(up.getvalue()))
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Bild konnte nicht verarbeitet werden: {e}")
        st.caption("Weißer Hintergrund wird automatisch entfernt.")
    st.divider()
    st.markdown("**Akzentfarbe der Unterlagen**")
    presets = branding()["accent_presets"]
    current = new["design"]["accent_color"] or branding()["accent_color"]
    names = list(presets) + ["Eigene Farbe"]
    default = next((n for n, c in presets.items() if c.lower() == current.lower()), "Eigene Farbe")
    c1, c2 = st.columns([2, 1])
    choice = c1.selectbox("Farbe", names, index=names.index(default), key=_k("accent_preset"))
    color = presets.get(choice) or c2.color_picker("Eigene Farbe", current, key=_k("accent_custom"))
    if choice != "Eigene Farbe":
        c2.color_picker("Vorschau", color, disabled=True, key=_k(f"accent_prev_{choice}"))
    new["design"]["accent_color"] = color
