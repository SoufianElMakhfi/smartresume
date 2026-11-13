"""Neue Bewerbung: Stelle eingeben → generieren → prüfen/optimieren → PDF."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

import streamlit as st

from .. import attachments, ats, bridge, db, generate, llm, mailer, quality, render
from ..profile import EMPLOYMENT_TYPES, add_skills, default_employment_type, is_profile_usable
from ..scrape import ScrapeError, scrape_url
from .common import (branding, chat_bridge, check_limit, fallback_chain, fmt_tokens, go, model_picker,
                     notify_switch, record_usage, report_url, show_findings, status_strip, uid)

GEN_KEYS = ("gen_step", "gen", "gen_pdf", "gen_app_id", "gen_factcheck", "gen_manual", "repair_manual",
            "gen_sent", "gen_mail_to", "gen_mail_subject", "gen_mail_body", "gen_mail_copy", "gen_saved",
            "gen_format", "gen_attach")
MANUAL_LABEL = "Gemini/ChatGPT (Abo-Modus)"
SWITCH = "Kein Problem – weiter geht es kostenlos mit deinem Gemini- oder ChatGPT-Konto."


def reset() -> None:
    for k in GEN_KEYS:
        st.session_state.pop(k, None)


def load_application(app: dict) -> None:
    """Gespeicherte Bewerbung zum Bearbeiten öffnen (aus 'Meine Bewerbungen')."""
    reset()
    s = app["structured"] or {}
    s.setdefault("cover_letter", {})
    s.setdefault("gaps", [])
    st.session_state.gen = {
        "structured": s, "job_text": app.get("job_text") or "", "job_url": app.get("job_url") or "",
        "employment_type": app.get("employment_type") or s.get("employment_type") or "Vollzeit",
        "extra_info": "", "tokens": 0, "model": "", "show_photo": True, "show_links": True, "log": [],
    }
    st.session_state.gen_app_id = app["id"]
    st.session_state.gen_step = "review"


def render_page() -> None:
    step = st.session_state.get("gen_step", "input")
    {"input": _input, "review": _review, "manual": _manual}.get(step, _done)()


# ---------------------------------------------------------------------------
def _input() -> None:
    st.title("Neue Bewerbung")
    status_strip()
    prof = db.get_profile(uid())
    profile = prof["data"]
    missing = is_profile_usable(profile)
    if missing:
        st.warning("Dein Profil ist noch unvollständig (" + ", ".join(missing) + "). "
                   "Lade zuerst deinen Lebenslauf hoch oder trage deine Daten ein.")
        if st.button("Zum Profil", type="primary", icon=":material/arrow_forward:"):
            go("profile")
        return

    picked = model_picker()
    if picked is None:
        st.caption(":material/info: Ohne API-Key erstellst du die Bewerbung kostenlos über dein Gemini- oder "
                   "ChatGPT-Konto: Auftrag kopieren, dort einfügen, Antwort zurückkopieren – fertig ist das PDF.")
    prefs = db.get_user_settings(uid()).get("gen_prefs") or {}
    # Zuletzt gewählte Beschäftigungsart merken; ohne Vorgabe: Werkstudent, wenn ein Studium im Profil steht.
    # (Kann auch von „Jobs finden“ vorbelegt sein.)
    st.session_state.setdefault("gen_etype", default_employment_type(profile, prefs))
    etype = st.segmented_control("Beschäftigungsart", EMPLOYMENT_TYPES, key="gen_etype") or "Vollzeit"
    if etype == "Werkstudent" and not profile["preferences"]["student_status"]:
        st.caption(":material/lightbulb: Tipp: Trage im Profil unter *Wünsche & Stil* dein Studium ein – das ist bei "
                   "Werkstudentenstellen das wichtigste Argument.")
    if etype in ("Teilzeit", "Werkstudent", "Minijob") and not profile["preferences"]["hours_per_week"]:
        st.caption(":material/lightbulb: Tipp: Gewünschte Wochenstunden im Profil eintragen, dann können sie genannt werden.")

    job_url = st.text_input("Link zur Stellenanzeige", placeholder="https://www.stepstone.de/…", key="gen_url")
    job_text = st.text_area("… oder Anzeigentext einfügen", height=200, key="gen_text",
                            placeholder="Wird der Link nicht gelesen (z.B. Login nötig), hier den Text einfügen.")
    extra = st.text_area("Zusätzliche Skills / Infos für diese Bewerbung (optional)", height=70, key="gen_extra",
                         placeholder="z.B. Figma, Docker, Führerschein Klasse B – nur was wirklich stimmt")
    have = {i.lower() for s in profile["skills"] for i in s["items"]}
    known = [x for x in generate._parse_extra_skills(extra) if x.lower() in have]
    if known:
        st.caption("Schon in deinem Profil: " + ", ".join(known) + " – wird nicht doppelt aufgeführt.")
    keep_extra = st.checkbox("Neue Skills dauerhaft in mein Profil übernehmen", key="gen_keep_extra",
                             disabled=not extra.strip())
    focus = st.text_input("Schwerpunkt (optional)", key="gen_focus",
                          placeholder="z.B. 'Betone meine Erfahrung im Kundenservice'")
    with st.expander("Optionen"):
        c1, c2 = st.columns(2)
        show_photo = c1.toggle("Foto auf dem Deckblatt", value=bool(prof["photo"]), disabled=not prof["photo"],
                               key="gen_photo")
        show_links = c2.toggle("Links (Portfolio, LinkedIn …)", value=bool(profile["personal"]["links"]),
                               disabled=not profile["personal"]["links"], key="gen_links")
        st.session_state.setdefault("gen_bullets", prefs.get("bullets", 2))
        bullets = c1.radio("Stichpunkte pro Station", [2, 3], horizontal=True, key="gen_bullets")
        st.session_state.setdefault("gen_autofix", prefs.get("auto_fix", True))
        auto_fix = c2.toggle("Regelverstöße automatisch korrigieren", key="gen_autofix",
                             help="Bei harten Fehlern (erfundene Zahlen, Platzhalter …) überarbeitet die KI "
                                  "das Anschreiben einmal gezielt. Kostet nur dann zusätzliche Tokens.")

    if not st.button("Bewerbung erstellen", type="primary", use_container_width=True, icon=":material/edit_document:"):
        return
    settings = db.get_user_settings(uid())
    settings["gen_prefs"] = {"employment_type": etype, "bullets": bullets, "auto_fix": auto_fix}
    db.save_user_settings(uid(), settings)

    final_text = ""
    if job_url.strip() and not job_text.strip():   # eingefügter Text hat Vorrang – kein Abruf nötig
        with st.spinner("Stellenanzeige wird geladen …"):
            try:
                final_text = scrape_url(job_url.strip())
            except ScrapeError as e:
                st.error(f"{e}\n\n**So geht's:** Anzeige im Browser öffnen → **Strg+A** (alles markieren) → "
                         "**Strg+C** (kopieren) → oben ins Feld **„… oder Anzeigentext einfügen“** einfügen → "
                         "nochmal auf **„Bewerbung erstellen“**. Überflüssiger Text (Menü, Werbung) stört nicht.")
                return
    if job_text.strip():
        final_text = (final_text + "\n\n" + job_text.strip()).strip() if final_text else job_text.strip()
    if len(final_text) < 80:
        st.error("Bitte einen Link oder den Text der Stellenanzeige angeben.")
        return

    if keep_extra and extra.strip():
        added = add_skills(profile, generate._parse_extra_skills(extra))   # nur neue, keine Doppelten
        db.save_profile(uid(), data=profile)
        if added:
            st.toast("Ins Profil übernommen: " + ", ".join(added), icon=":material/check:")
        profile = db.get_profile(uid())["data"]
        st.session_state.pop("draft_uid", None)  # Profilentwurf neu laden

    job = {"job_text": final_text, "job_url": job_url.strip(), "employment_type": etype, "extra_info": extra,
           "focus": focus, "bullets": bullets, "show_photo": show_photo, "show_links": show_links}
    if picked is None:
        return _to_manual(job, "")
    limit_msg = check_limit()
    if limit_msg:
        return _to_manual(job, f"{limit_msg} {SWITCH}")

    cfg = picked[0]
    with st.spinner(f"{cfg['label']} schreibt deine Bewerbung …"):
        try:
            res, (cfg, key) = llm.with_fallback(
                fallback_chain(picked),
                lambda c, k: generate.generate_application(profile, final_text, etype, c, k, extra_info=extra,
                                                           focus=focus, bullets_per_job=bullets,
                                                           auto_repair=auto_fix),
                on_switch=notify_switch)
        except llm.LLMError as e:
            return _to_manual(job, f"Die KI ist gerade nicht verfügbar ({e}). {SWITCH}")
    record_usage("generate", cfg, res.input_tokens + res.output_tokens)
    reset()
    st.session_state.gen = {
        "structured": res.structured, "job_text": generate.clean_job_text(final_text), "job_url": job_url.strip(),
        "employment_type": etype, "extra_info": extra, "tokens": res.input_tokens + res.output_tokens,
        "model": cfg["label"], "repaired": res.repaired, "show_photo": show_photo, "show_links": show_links,
        "log": res.log,
    }
    st.session_state.gen_step = "review"
    st.rerun()


def _to_manual(job: dict, reason: str) -> None:
    """Wechselt in den Abo-Modus; alle Eingaben bleiben erhalten."""
    reset()
    st.session_state.gen_manual = {**job, "reason": reason}
    st.session_state.gen_step = "manual"
    st.rerun()


def _manual() -> None:
    m = st.session_state.gen_manual
    profile = db.get_profile(uid())["data"]
    st.title("Bewerbung mit Gemini oder ChatGPT schreiben")
    if m.get("reason"):
        st.info(m["reason"], icon=":material/sync:")
    st.caption("Gemini oder ChatGPT schreibt die Texte (Anschreiben, Kurzprofil, Stichpunkte für den Lebenslauf). "
               "SmartResume prüft sie genauso streng wie sonst, setzt Firmen, Zeiträume und Ausbildung aus deinem "
               "Profil ein und erstellt daraus das PDF. Funktioniert mit jedem Konto, auch kostenlos.")
    system, user = generate.build_prompts(profile, m["job_text"], m["employment_type"], m["extra_info"],
                                          m["focus"], m["bullets"])
    data = chat_bridge(bridge.chat_prompt(system, user), "gen", validate=generate.validate_ai,
                       submit="Antwort übernehmen und Entwurf prüfen")
    if data is not None:
        res = generate.finish(data, profile, m["job_text"], m["employment_type"], m["extra_info"], m["bullets"])
        reset()
        st.session_state.gen = {
            "structured": res.structured, "job_text": generate.clean_job_text(m["job_text"]),
            "job_url": m["job_url"], "employment_type": m["employment_type"], "extra_info": m["extra_info"],
            "tokens": 0, "model": MANUAL_LABEL, "repaired": False, "show_photo": m["show_photo"],
            "show_links": m["show_links"], "log": [],
        }
        st.session_state.gen_step = "review"
        st.rerun()
    if st.button("Abbrechen", use_container_width=True, icon=":material/close:"):
        reset()
        st.rerun()


# ---------------------------------------------------------------------------
def _refine_box(label: str, key: str, getter, setter, picked) -> None:
    c1, c2 = st.columns([4, 1])
    ins = c1.text_input(f"Anweisung für {label}", key=f"ins_{key}", label_visibility="collapsed",
                        placeholder="KI-Anweisung, z.B. 'kürzer', 'konkreter', 'selbstbewusster'")
    if c2.button("Optimieren", key=f"btn_{key}", use_container_width=True, disabled=not picked,
                  icon=":material/auto_awesome:"):
        if not ins.strip():
            st.toast("Bitte zuerst eine Anweisung eingeben.")
            return
        cfg, api_key = picked
        try:
            with st.spinner("Optimiere …"):
                text, tokens = generate.refine_text(getter(), ins, db.get_profile(uid())["data"], cfg, api_key)
            record_usage("refine", cfg, tokens)
            setter(generate.normalize_text(text))
            st.session_state.gen["tokens"] += tokens
            st.rerun()
        except llm.LLMError as e:
            st.error(str(e))


def _review() -> None:
    g = st.session_state.gen
    s = g["structured"]
    cl = s["cover_letter"]
    prof = db.get_profile(uid())
    profile = prof["data"]

    st.title("Entwurf prüfen")
    meta = [f"**{cl.get('job_title') or 'Stelle'}** bei **{cl.get('company') or '?'}**", g["employment_type"]]
    if g.get("tokens"):
        meta.append(f"{fmt_tokens(g['tokens'])} Tokens ({g['model']})")
    st.caption(" · ".join(meta))
    picked = model_picker("review_model", "Modell für Optimierungen")
    if picked is None:
        st.caption(":material/info: Ohne verbundene KI bearbeitest du die Texte direkt hier; Regelverstöße lassen sich unten "
                   "per Gemini/ChatGPT beheben.")
    rev = st.session_state.setdefault("review_rev", 0)

    def k(name):  # Widget-Keys erneuern, wenn die KI Texte ersetzt
        return f"r{rev}_{name}"

    # ── Anschreiben ───────────────────────────────────────────────────────
    st.subheader("Anschreiben")
    c1, c2 = st.columns(2)
    cl["company"] = c1.text_input("Unternehmen", cl.get("company", ""), key=k("company"))
    cl["contact_person"] = c2.text_input("Ansprechpartner", cl.get("contact_person", ""), key=k("contact"))
    cl["department"] = c1.text_input("Abteilung", cl.get("department", ""), key=k("dept"))
    cl["street"] = c2.text_input("Straße", cl.get("street", ""), key=k("street"))
    cl["city"] = c1.text_input("PLZ Ort", cl.get("city", ""), key=k("city"))
    cl["job_title"] = c2.text_input("Stellentitel (Deckblatt)", cl.get("job_title", ""), key=k("title"))
    cl["subject"] = st.text_input("Betreff", cl.get("subject") or f"Bewerbung als {cl.get('job_title', '')}",
                                  key=k("subject"))
    cl["salutation"] = st.text_input("Anrede", cl.get("salutation") or "Sehr geehrte Damen und Herren,",
                                     key=k("salutation"))
    for p_key, label, h in (("p1", "Einstieg", 90), ("p2", "Qualifikation", 140), ("p3", "Arbeitsweise", 100),
                            ("p4", "Abschluss", 90)):
        cl[p_key] = st.text_area(label, cl.get(p_key, ""), height=h, key=k(p_key))

        def _set(v, p=p_key):
            st.session_state.gen["structured"]["cover_letter"][p] = v
            st.session_state.review_rev += 1
        _refine_box(label, p_key, lambda p=p_key: cl[p], _set, picked)
    words = len(" ".join(cl.get(p, "") for p in ("p1", "p2", "p3", "p4")).split())
    st.caption(f"{words} Wörter (Ziel: 150–210 für eine Seite)")

    # ── Deckblatt-Text ────────────────────────────────────────────────────
    st.subheader("Über mich (Deckblatt)")
    s["summary"] = st.text_area("Kurzprofil", s.get("summary", ""), height=90, key=k("summary"),
                                label_visibility="collapsed")

    def _set_summary(v):
        st.session_state.gen["structured"]["summary"] = v
        st.session_state.review_rev += 1
    _refine_box("Kurzprofil", "summary", lambda: s["summary"], _set_summary, picked)

    # ── Lebenslauf ────────────────────────────────────────────────────────
    with st.expander("Lebenslauf: Stichpunkte bearbeiten"):
        for i, job in enumerate(s.get("experience", [])):
            st.markdown(f"**{job.get('role', '')}** – {job.get('company', '')}")
            txt = st.text_area("Stichpunkte", "\n".join(job.get("bullets", [])), height=80, key=k(f"b{i}"),
                               label_visibility="collapsed")
            job["bullets"] = [b.strip() for b in txt.splitlines() if b.strip()]
    with st.expander("Lebenslauf: Fähigkeiten bearbeiten"):
        for i, sk in enumerate(s.get("skills", [])):
            items = sk.get("items", "")
            sk["items"] = st.text_input(sk.get("category", ""), ", ".join(items) if isinstance(items, list)
                                        else items, key=k(f"s{i}"))

    # ── Qualitäts-Check ───────────────────────────────────────────────────
    st.subheader("Qualitäts-Check")
    findings = quality.check_application(s, profile, g["job_text"], g.get("extra_info", ""),
                                         generate.MAX_BULLET_CHARS)
    show_findings(findings)
    if g.get("repaired"):
        st.caption(":material/build: Das Anschreiben wurde nach der Erstellung einmal automatisch korrigiert.")
    for line in g.get("log", []):
        st.caption(line)
    _ats_panel(s)
    if s.get("gaps"):
        st.info("**Anforderungen, die dein Profil nicht belegt** – werden im Anschreiben nicht behauptet:\n\n"
                + "\n".join(f"- {x}" for x in s["gaps"]), icon=":material/rule:")
    fc = st.session_state.get("gen_factcheck")
    if fc is not None:
        if fc:
            st.warning("**KI-Faktencheck – nicht durch dein Profil belegt:**\n\n" +
                       "\n".join(f"- „{i['claim']}“ – {i.get('reason', '')}" for i in fc), icon=":material/fact_check:")
        else:
            st.success("KI-Faktencheck: alle Aussagen sind durch dein Profil gedeckt.", icon=":material/fact_check:")
    c1, c2 = st.columns(2)
    if c1.button("KI-Faktencheck", use_container_width=True, disabled=not picked, icon=":material/fact_check:",
                 help="Ein Modell vergleicht Anschreiben und Kurzprofil Satz für Satz mit deinem Profil "
                      "(ca. 2.000 Tokens)."):
        cfg, api_key = picked
        try:
            with st.spinner("Prüfe Aussagen gegen dein Profil …"):
                issues, tokens = generate.fact_check(s, profile, cfg, api_key, g.get("extra_info", ""))
            record_usage("factcheck", cfg, tokens)
            g["tokens"] += tokens
            st.session_state.gen_factcheck = issues
            st.rerun()
        except llm.LLMError as e:
            st.error(str(e))
    problems = quality.blocking_problems(findings) + [
        f"Nicht belegt: „{i['claim']}“ ({i.get('reason', '')}) – entfernen oder durch Belegtes ersetzen"
        for i in (fc or [])]
    if c2.button("Probleme automatisch beheben", use_container_width=True, icon=":material/auto_fix_high:",
                 disabled=not (picked and problems)):
        cfg, api_key = picked
        try:
            with st.spinner("Überarbeite Anschreiben …"):
                res = generate.repair_cover_letter(s, problems, profile, cfg, api_key)
            record_usage("repair", cfg, res.total_tokens)
            g["tokens"] += res.total_tokens
            generate.apply_repair(s, res.data)
            st.session_state.gen_factcheck = None
            st.session_state.review_rev += 1
            st.rerun()
        except llm.LLMError as e:
            st.error(f"{e} – du kannst die Probleme unten per Gemini/ChatGPT beheben.")
            st.session_state.repair_manual = True
    if problems and (picked is None or st.session_state.get("repair_manual")):
        with st.expander("Probleme mit Gemini/ChatGPT beheben", expanded=picked is None, icon=":material/auto_fix_high:"):
            system, user = generate.repair_prompts(s, problems, profile)
            data = chat_bridge(bridge.chat_prompt(system, user), "repair", validate=generate.validate_repair)
            if data is not None:
                generate.apply_repair(s, data)
                st.session_state.gen_factcheck = None
                st.session_state.repair_manual = False
                st.session_state.review_rev += 1
                st.rerun()

    # ── PDF ───────────────────────────────────────────────────────────────
    st.divider()
    c1, c2 = st.columns(2)
    g["show_photo"] = c1.toggle("Foto auf dem Deckblatt", value=g.get("show_photo", True) and bool(prof["photo"]),
                                disabled=not prof["photo"], key=k("photo"))
    g["show_links"] = c2.toggle("Links anzeigen", value=g.get("show_links", True),
                                disabled=not profile["personal"]["links"], key=k("links"))
    c1, c2 = st.columns(2)
    if c1.button("PDF erstellen", type="primary", use_container_width=True, icon=":material/picture_as_pdf:"):
        try:
            with st.spinner("PDF wird erstellt …"):
                st.session_state.gen_pdf = _render(s, prof, g)
            st.session_state.gen_step = "done"
            st.rerun()
        except render.RenderError as e:
            st.error(str(e))
    if c2.button("Verwerfen & neu starten", use_container_width=True, icon=":material/restart_alt:"):
        reset()
        st.rerun()


def _render(s: dict, prof: dict, g: dict) -> bytes:
    profile = prof["data"]
    return render.render_pdf(
        s, profile, photo=prof["photo"], signature=prof["signature"],
        accent=profile["design"]["accent_color"] or branding()["accent_color"], font=branding()["pdf_font"],
        show_photo=g.get("show_photo", True), show_links=g.get("show_links", True))


def _slug(x: str) -> str:
    return re.sub(r"[^\w-]+", "_", x or "").strip("_")[:40]


def _file_name(profile: dict, company: str, kind: str = "Bewerbung") -> str:
    """Bewerbung_Max_Mustermann_Firma.pdf · Anschreiben_Max_Mustermann_Firma.pdf · Lebenslauf_Max_Mustermann.pdf
    (Personaler und Bewerbersysteme ordnen Dateien so eindeutig zu)."""
    name = _slug(profile["personal"]["name"])
    if kind == "Lebenslauf":
        return f"Lebenslauf_{name}.pdf"
    return f"{kind}_{name}_{_slug(company) or 'Unternehmen'}.pdf"


FORMATS = ["Eine Bewerbungsmappe (1 PDF)", "Getrennt: Anschreiben + Lebenslauf"]


def _saved_format(value: str | None) -> str:
    """Gespeicherte Formatwahl – auch ältere Werte (mit Emoji davor) werden erkannt."""
    return FORMATS[1] if "Getrennt" in (value or "") else FORMATS[0]


def _autosave(g: dict, s: dict, pdf: bytes) -> int:
    """Jede erstellte Bewerbung landet sofort in „Meine Bewerbungen“ – mit Stellenanzeige und PDF, Status
    „Erstellt“. So geht nichts verloren, auch wenn man vergisst, sie als beworben zu markieren."""
    cl = s["cover_letter"]
    digest = hashlib.sha1(pdf).hexdigest()
    app_id = st.session_state.get("gen_app_id")
    if st.session_state.get("gen_saved") == digest and app_id:
        return app_id
    if app_id:
        db.update_application(uid(), app_id, pdf_bytes=pdf, company=cl.get("company"), job_title=cl.get("job_title"),
                              structured_data=json.dumps(s, ensure_ascii=False))
    else:
        app_id = db.save_application(uid(), cl.get("company", ""), cl.get("job_title", ""), g["employment_type"],
                                     g["job_text"], g["job_url"], pdf, s, status="Erstellt")
        st.session_state.gen_app_id = app_id
    st.session_state.gen_saved = digest
    return app_id


def _documents(prof: dict, cl: dict, pdf: bytes, separate: bool,
               extra: bytes | None = None) -> list[tuple[bytes, str]]:
    """[(pdf, dateiname)] im gewählten Format. `extra` = Anlagen (Zeugnisse …) als eine PDF: in der Mappe hinter
    dem Lebenslauf, bei getrennten Dateien als eigene Datei „Anlagen“ (Portale haben dafür ein eigenes Feld)."""
    if separate:
        try:
            letter_pdf, cv_pdf = render.split_pdf(pdf)
            docs = [(letter_pdf, _file_name(prof["data"], cl.get("company"), "Anschreiben")),
                    (cv_pdf, _file_name(prof["data"], cl.get("company"), "Lebenslauf"))]
            if extra:
                docs.append((extra, _file_name(prof["data"], cl.get("company"), "Anlagen")))
            return docs
        except Exception:  # noqa: BLE001 – Aufteilen fehlgeschlagen → komplette Mappe
            st.warning("Die Mappe ließ sich nicht aufteilen – es wird die komplette PDF verwendet.")
    if extra:
        pdf = attachments.merge([pdf, extra])
    return [(pdf, _file_name(prof["data"], cl.get("company")))]


def _attachments_pick() -> bytes | None:
    """Auswahl der Anlagen (Zeugnisse, Zertifikate) für diese Bewerbung → eine PDF oder None."""
    docs = db.list_documents(uid())
    if not docs:
        st.caption(":material/attach_file: Zeugnisse oder Zertifikate anhängen? Unter **Mein Profil → Kenntnisse** "
                   "hochladen – dann kannst du sie hier auswählen.")
        return None
    ids = [d["id"] for d in docs]
    titles = {d["id"]: d["title"] for d in docs}
    st.session_state.setdefault("gen_attach", ids)
    st.session_state.gen_attach = [i for i in st.session_state.gen_attach if i in ids]
    picked = st.multiselect("Anlagen (Zeugnisse, Zertifikate, Nachweise)", ids, key="gen_attach",
                            format_func=lambda i: titles[i], placeholder="Keine Anlagen",
                            help="Reihenfolge wie ausgewählt. Verwalten unter Mein Profil → Kenntnisse.")
    if not picked:
        return None
    return attachments.merge([d["pdf_bytes"] for d in db.get_documents(uid(), picked)])


def _done() -> None:
    g = st.session_state.gen
    s = g["structured"]
    cl = s["cover_letter"]
    prof = db.get_profile(uid())
    pdf = st.session_state.gen_pdf
    app_id = _autosave(g, s, pdf)
    app = next((a for a in db.list_applications(uid()) if a["id"] == app_id), {})

    company = cl.get("company") or "das Unternehmen"
    st.title(f"Bewerbung an {company} ist fertig")
    # Status auf einen Blick: was ist erledigt, was fehlt noch?
    sent = app.get("status") not in (None, "", "Erstellt")
    c1, c2, c3 = st.columns(3)
    c1.markdown(":green[:material/check_circle:] **Erstellt**")
    c2.markdown(":green[:material/check_circle:] **Gespeichert** in „Meine Bewerbungen“")
    c3.markdown(f":green[:material/check_circle:] **{app.get('status')}** · {app.get('applied_at', '')}" if sent
                else ":orange[:material/radio_button_unchecked:] **Noch nicht versendet**")
    pages = render.count_pages(pdf)
    if pages != 3:
        st.warning(f"Das PDF hat {pages} statt 3 Seiten – vermutlich ist das Anschreiben oder der Lebenslauf "
                   "zu lang. Unten auf „Bearbeiten“ klicken und kürzen.")

    # Unterlagen-Format + Anlagen bestimmen, was versendet bzw. heruntergeladen wird – Auswahl kompakt vorab
    settings = db.get_user_settings(uid())
    st.session_state.setdefault("gen_format", _saved_format(settings.get("pdf_format")))
    with st.container(border=True):
        st.markdown("**Unterlagen**")
        fmt = st.segmented_control("Format", FORMATS, key="gen_format", label_visibility="collapsed") or FORMATS[0]
        if fmt != settings.get("pdf_format"):
            settings["pdf_format"] = fmt
            db.save_user_settings(uid(), settings)
        separate = fmt == FORMATS[1]
        st.caption("Anschreiben und Lebenslauf als zwei Dateien (ohne Deckblatt) – für Portale mit einzelnen "
                   "Upload-Feldern." if separate else
                   "Deckblatt, Anschreiben und Lebenslauf in einer Datei – Standard für Bewerbungen per E-Mail.")
        extra = _attachments_pick()
        docs = _documents(prof, cl, pdf, separate, extra)

    # 1) Versenden – die Hauptaktion, deshalb ganz oben und hervorgehoben
    _send_section(g, s, prof, docs)

    # 2) Herunterladen (z. B. für ein Bewerbungsportal)
    st.markdown("##### Herunterladen")
    cols = st.columns(len(docs))
    for col, (data, name) in zip(cols, docs):
        label = next((k for k in ("Anschreiben", "Lebenslauf", "Anlagen") if name.startswith(k)),
                     "Bewerbungsmappe (PDF)")
        col.download_button(label, data, file_name=name, mime="application/pdf", use_container_width=True,
                            key=f"dl_{name}", icon=":material/download:")

    # 3) Nebenaktionen klein am Ende
    st.divider()
    c1, c2, c3 = st.columns(3)
    if c1.button("Bearbeiten", use_container_width=True, icon=":material/edit:"):
        st.session_state.gen_step = "review"
        st.rerun()
    if c2.button("Neue Bewerbung", use_container_width=True, icon=":material/add:"):
        reset()
        st.rerun()
    if not sent and c3.button("Als beworben markieren", use_container_width=True, icon=":material/task_alt:",
                              help="Z. B. nach dem Hochladen in ein Bewerbungsportal. Gespeichert ist schon alles."):
        db.mark_applied(uid(), app_id)
        st.rerun()
    _report_ai_content(g, s)


def _report_ai_content(g: dict, s: dict) -> None:
    """KI-Hinweis + Meldeweg für unpassende Inhalte (Microsoft-Store-Richtlinie 11.16)."""
    st.caption("Die Texte wurden von einer KI erstellt (Fakten wie Firmen, Zeiträume und Abschlüsse stammen "
               "unverändert aus deinem Profil). Bitte lies sie vor dem Versand.")
    job = s.get("cover_letter") or {}
    url = report_url("KI-Inhalt melden", "Was ist an dem erzeugten Text unpassend oder falsch?\n\n"
                     f"Stelle: {job.get('job_title', '')} – {job.get('company', '')}\nModell: {g.get('model', '')}\n"
                     "(Bitte keine Bewerbungsunterlagen anhängen, wenn es nicht nötig ist.)")
    if url:
        st.link_button("Unpassenden KI-Inhalt melden", url, icon=":material/flag:")


def _send_section(g: dict, s: dict, prof: dict, docs: list[tuple[bytes, str]]) -> None:
    """Bewerbung versenden: Empfänger aus der Anzeige, dann direkt per SMTP oder als Gmail-Entwurf."""
    sent_to = st.session_state.get("gen_sent")
    if sent_to:
        st.success(f"**Gesendet an {sent_to}** – steht in „Meine Bewerbungen“ als beworben.",
                   icon=":material/mark_email_read:")
        return
    box = st.container(border=True)
    with box:
        _send_form(g, s, prof, docs)


def _send_form(g: dict, s: dict, prof: dict, docs: list[tuple[bytes, str]]) -> None:
    st.markdown("### :material/send: Per E-Mail bewerben")
    found = mailer.find_emails(g.get("job_text", ""))
    if found:
        st.caption("Empfänger aus der Anzeige übernommen" +
                   (f" (weitere: {', '.join(found[1:3])})" if len(found) > 1 else "") + " – bitte kurz prüfen.")
    else:
        st.info("In der Anzeige steht **keine E-Mail-Adresse** – dann meist über das Bewerbungsformular der Firma "
                "(Anzeige öffnen → „Jetzt bewerben“ → PDF hochladen). Kennst du doch eine Adresse, trag sie ein.",
                icon=":material/info:")
        if g.get("job_url"):
            st.link_button("Anzeige / Bewerbungsportal öffnen", g["job_url"], icon=":material/open_in_new:")
    st.session_state.setdefault("gen_mail_to", found[0] if found else "")
    st.session_state.setdefault("gen_mail_subject", mailer.default_subject(s))
    st.session_state.setdefault("gen_mail_body", mailer.default_body(s, prof["data"]))
    c1, c2 = st.columns([2, 3])
    to = c1.text_input("An", key="gen_mail_to", placeholder="z. B. bewerbung@firma.de")
    subject = c2.text_input("Betreff", key="gen_mail_subject")
    with st.expander("E-Mail-Text ansehen / anpassen", icon=":material/edit_note:"):
        body = st.text_area("Text der E-Mail", key="gen_mail_body", height=220, label_visibility="collapsed",
                            help="Kurz halten – das eigentliche Anschreiben steckt im PDF.")
    st.caption(":material/attach_file: Anhang: " + ", ".join(name for _, name in docs))
    acc = db.get_user_settings(uid()).get("mail") or {}
    ok_to = mailer.valid_email(to)

    if mailer.account_ready(acc):
        copy = st.checkbox("Kopie an mich", value=not mailer.PROVIDERS.get(acc.get("provider"), {}).get("saves_sent"),
                           key="gen_mail_copy", help="Gmail legt gesendete Mails ohnehin unter „Gesendet“ ab.")
        if st.button(f"Jetzt senden (von {acc['address']})", type="primary", use_container_width=True,
                     icon=":material/send:", disabled=not ok_to):
            try:
                msg = mailer.build_message(acc, prof["data"]["personal"].get("name", ""), to, subject, body, docs,
                                           copy_to_self=copy)
                with st.spinner("Sende …"):
                    mailer.send(acc, msg)
            except mailer.MailError as e:
                st.error(str(e))
                return
            note = f"Per E-Mail an {to.strip()} gesendet am {date.today():%d.%m.%Y}."
            app_id = st.session_state.gen_app_id                # durch _autosave immer vorhanden
            db.mark_applied(uid(), app_id)
            db.update_application(uid(), app_id, notes=note)
            st.session_state.gen_sent = to.strip()
            st.rerun()
    else:
        st.markdown("**Direkt aus SmartResume senden** – mit Anhang, ein Klick. Dafür einmalig dein E-Mail-Konto "
                    "verbinden (Gmail, Outlook, GMX, Web.de …, ca. 2 Minuten).")
        if st.button("E-Mail-Konto verbinden", type="primary", use_container_width=True, icon=":material/link:"):
            go("settings")
        personal = prof["data"]["personal"]
        draft = mailer.build_draft(personal.get("name", ""), personal.get("email") or st.session_state.user["email"],
                                   to, subject, body, docs)
        company = re.sub(r"[^\w-]+", "_", s["cover_letter"].get("company") or "Bewerbung").strip("_")[:40]
        with st.expander("Ohne Konto: als Entwurf in deinem Mailprogramm öffnen", icon=":material/drafts:"):
            c1, c2 = st.columns(2)
            c1.download_button("Entwurf mit Anhang (.eml)", draft, file_name=f"Bewerbung_{company}.eml",
                               mime="message/rfc822", use_container_width=True, icon=":material/attach_email:",
                               key="gen_mail_draft")
            c1.caption("Outlook, Thunderbird, Apple Mail: Datei öffnen – Empfänger, Text und PDF sind drin, nur "
                       "noch senden. (Thunderbird: „Als neu bearbeiten“.)")
            c2.link_button("Gmail-Entwurf öffnen", mailer.gmail_compose_url(to, subject, body),
                           use_container_width=True, disabled=not ok_to, icon=":material/drafts:")
            c2.caption("Gmail im Browser: Text ist vorausgefüllt, die PDF" + ("s" if len(docs) > 1 else "") +
                       " unten herunterladen und anhängen.")


def _ats_fix(action: str, term: str, profile_word: str = "") -> None:
    s = st.session_state.gen["structured"]
    if action == "add":
        ats.add_to_skills(s, term)
    else:
        ats.use_ad_wording(s, term, profile_word)
    st.session_state.review_rev += 1          # Eingabefelder (Fähigkeiten) neu aufbauen


def _ats_panel(s: dict) -> None:
    """Schlüsselbegriffe der Anzeige vs. Unterlagen – so, wie Bewerbermanagement-Software (ATS) filtert."""
    rep = ats.report(s)
    if not rep:
        return
    score, best = ats.score(rep), ats.best_possible(rep)
    color = "green" if score >= 75 else "orange" if score >= 50 else "red"
    fixable = [r for r in rep if r["status"] in ("addable", "wording")]
    with st.expander(f"ATS-Check: :{color}[**{score} %**] der Schlüsselbegriffe der Anzeige abgedeckt"
                     + (f" – ehrlich möglich: {best} %" if best > score else ""), expanded=bool(fixable),
                     icon=":material/manage_search:"):
        st.caption("Viele Firmen lassen Bewerbungen zuerst von Software (z. B. Personio, SAP SuccessFactors, "
                   "Workday) nach den Begriffen der Anzeige durchsuchen – oft wörtlich. Hier siehst du, welche "
                   "davon in deinen Unterlagen stehen. Ergänzt wird nur, was laut deinem Profil stimmt.")
        for i, r in enumerate(rep):
            t, p = r["term"], r["profile"]
            if r["status"] == "ok":
                st.markdown(f":green[:material/check_circle:] **{t}**")
            elif r["status"] == "bridge":
                st.markdown(f":blue[:material/info:] **{t}** – im Anschreiben ehrlich als Lücke angesprochen (die Software findet den "
                            "Begriff trotzdem).")
            elif r["status"] == "wording":
                c1, c2 = st.columns([3, 2])
                c1.markdown(f":orange[:material/spellcheck:] **{t}** – steht als „{p}“ drin. Die Software sucht evtl. genau „{t}“.")
                c2.button(f"„{t}“ verwenden", key=f"ats_w{i}", on_click=_ats_fix, args=("wording", t, p),
                          use_container_width=True)
            elif r["status"] == "addable":
                c1, c2 = st.columns([3, 2])
                c1.markdown(f":orange[:material/add_circle:] **{t}** – hast du laut Profil" + (f" („{p}“)" if p.lower() != t.lower() else "")
                            + ", steht aber nicht in den Unterlagen.")
                c2.button("In Kenntnisse aufnehmen", key=f"ats_a{i}", on_click=_ats_fix, args=("add", t),
                          use_container_width=True)
            else:
                st.markdown(f":gray[:material/radio_button_unchecked:] **{t}** – nicht in deinem Profil. Kannst du es doch? Dann im Profil ergänzen "
                            "und die Bewerbung neu erstellen.")
