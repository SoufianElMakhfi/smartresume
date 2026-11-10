"""Neue Bewerbung: Stelle eingeben → generieren → prüfen/optimieren → PDF."""
from __future__ import annotations

import json
import re

import streamlit as st

from .. import bridge, db, generate, llm, quality, render
from ..profile import EMPLOYMENT_TYPES, is_profile_usable
from ..scrape import ScrapeError, scrape_url
from .common import (branding, chat_bridge, check_limit, fallback_chain, fmt_tokens, go, model_picker,
                     notify_switch, record_usage, show_findings, uid)

GEN_KEYS = ("gen_step", "gen", "gen_pdf", "gen_app_id", "gen_factcheck", "gen_manual", "repair_manual")
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
    prof = db.get_profile(uid())
    profile = prof["data"]
    missing = is_profile_usable(profile)
    if missing:
        st.warning("Dein Profil ist noch unvollständig (" + ", ".join(missing) + "). "
                   "Lade zuerst deinen Lebenslauf hoch oder trage deine Daten ein.")
        if st.button("Zum Profil →", type="primary"):
            go("profile")
        return

    picked = model_picker()
    if picked is None:
        st.info("Keine KI-API eingerichtet – kein Problem: Du erstellst die Bewerbung kostenlos mit deinem "
                "eigenen **Gemini**- oder **ChatGPT**-Konto (Kopieren & Einfügen, dauert ca. 30 Sekunden länger).",
                icon="💬")
        if st.session_state.user.get("is_admin") and st.button("🔑 Kostenlosen KI-Key einrichten (2 Minuten)"):
            go("setup")
    etype = st.segmented_control("Beschäftigungsart", EMPLOYMENT_TYPES, default="Vollzeit", key="gen_etype") \
        or "Vollzeit"
    if etype == "Werkstudent" and not profile["preferences"]["student_status"]:
        st.caption("💡 Tipp: Trage im Profil unter *Rahmen & Stil* dein Studium ein – das ist bei "
                   "Werkstudentenstellen das wichtigste Argument.")
    if etype in ("Teilzeit", "Werkstudent", "Minijob") and not profile["preferences"]["hours_per_week"]:
        st.caption("💡 Tipp: Gewünschte Wochenstunden im Profil eintragen, dann können sie genannt werden.")

    job_url = st.text_input("Link zur Stellenanzeige", placeholder="https://www.stepstone.de/…", key="gen_url")
    job_text = st.text_area("… oder Anzeigentext einfügen", height=200, key="gen_text",
                            placeholder="Wird der Link nicht gelesen (z.B. Login nötig), hier den Text einfügen.")
    extra = st.text_area("Zusätzliche Skills / Infos für diese Bewerbung (optional)", height=70, key="gen_extra",
                         placeholder="z.B. Figma, Docker, Führerschein Klasse B – nur was wirklich stimmt")
    keep_extra = st.checkbox("Diese Skills dauerhaft in mein Profil übernehmen", key="gen_keep_extra",
                             disabled=not extra.strip())
    focus = st.text_input("Schwerpunkt (optional)", key="gen_focus",
                          placeholder="z.B. 'Betone meine Erfahrung im Kundenservice'")
    with st.expander("Optionen"):
        c1, c2 = st.columns(2)
        show_photo = c1.toggle("Foto auf dem Deckblatt", value=bool(prof["photo"]), disabled=not prof["photo"],
                               key="gen_photo")
        show_links = c2.toggle("Links (Portfolio, LinkedIn …)", value=bool(profile["personal"]["links"]),
                               disabled=not profile["personal"]["links"], key="gen_links")
        bullets = c1.radio("Stichpunkte pro Station", [2, 3], horizontal=True, key="gen_bullets")
        auto_fix = c2.toggle("Regelverstöße automatisch korrigieren", value=True, key="gen_autofix",
                             help="Bei harten Fehlern (erfundene Zahlen, Platzhalter …) überarbeitet die KI "
                                  "das Anschreiben einmal gezielt. Kostet nur dann zusätzliche Tokens.")

    if not st.button("✨ Bewerbung erstellen", type="primary", use_container_width=True):
        return

    final_text = ""
    if job_url.strip():
        with st.spinner("Stellenanzeige wird geladen …"):
            try:
                final_text = scrape_url(job_url.strip())
            except ScrapeError as e:
                if not job_text.strip():
                    st.error(f"{e} Bitte den Anzeigentext unten einfügen.")
                    return
                st.info(f"{e} Nutze den eingefügten Text.")
    if job_text.strip():
        final_text = (final_text + "\n\n" + job_text.strip()).strip() if final_text else job_text.strip()
    if len(final_text) < 80:
        st.error("Bitte einen Link oder den Text der Stellenanzeige angeben.")
        return

    if keep_extra and extra.strip():
        profile["skills"].append({"category": "Weitere Kenntnisse", "items": generate._parse_extra_skills(extra)})
        db.save_profile(uid(), data=profile)
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
    st.title("Mit Gemini oder ChatGPT erstellen")
    if m.get("reason"):
        st.info(m["reason"], icon="🔄")
    st.caption("Funktioniert mit jedem Gemini- oder ChatGPT-Konto, auch kostenlos. Der Auftrag enthält alle Regeln; "
               "die Antwort prüft die App danach genauso streng wie sonst.")
    system, user = generate.build_prompts(profile, m["job_text"], m["employment_type"], m["extra_info"],
                                          m["focus"], m["bullets"])
    data = chat_bridge(bridge.chat_prompt(system, user), "gen", validate=generate.validate_ai)
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
    if st.button("✖ Abbrechen", use_container_width=True):
        reset()
        st.rerun()


# ---------------------------------------------------------------------------
def _refine_box(label: str, key: str, getter, setter, picked) -> None:
    c1, c2 = st.columns([4, 1])
    ins = c1.text_input(f"Anweisung für {label}", key=f"ins_{key}", label_visibility="collapsed",
                        placeholder="KI-Anweisung, z.B. 'kürzer', 'konkreter', 'selbstbewusster'")
    if c2.button("✨ Optimieren", key=f"btn_{key}", use_container_width=True, disabled=not picked):
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
        st.caption("💡 Ohne KI-API bearbeitest du die Texte direkt hier; Regelverstöße lassen sich unten "
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
        st.caption("🛠 Das Anschreiben wurde nach der Erstellung einmal automatisch korrigiert.")
    for line in g.get("log", []):
        st.caption(line)
    if s.get("gaps"):
        st.info("**Anforderungen, die dein Profil nicht belegt** – werden im Anschreiben nicht behauptet:\n\n"
                + "\n".join(f"- {x}" for x in s["gaps"]), icon="🧭")
    fc = st.session_state.get("gen_factcheck")
    if fc is not None:
        if fc:
            st.warning("**KI-Faktencheck – nicht durch dein Profil belegt:**\n\n" +
                       "\n".join(f"- „{i['claim']}“ – {i.get('reason', '')}" for i in fc), icon="🔎")
        else:
            st.success("KI-Faktencheck: alle Aussagen sind durch dein Profil gedeckt.", icon="🔎")
    c1, c2 = st.columns(2)
    if c1.button("🔎 KI-Faktencheck", use_container_width=True, disabled=not picked,
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
    if c2.button("🛠 Probleme automatisch beheben", use_container_width=True,
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
        with st.expander("🛠 Probleme mit Gemini/ChatGPT beheben", expanded=picked is None):
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
    if c1.button("📄 PDF erstellen", type="primary", use_container_width=True):
        try:
            with st.spinner("PDF wird erstellt …"):
                st.session_state.gen_pdf = _render(s, prof, g)
            st.session_state.gen_step = "done"
            st.rerun()
        except render.RenderError as e:
            st.error(str(e))
    if c2.button("✖ Verwerfen & neu starten", use_container_width=True):
        reset()
        st.rerun()


def _render(s: dict, prof: dict, g: dict) -> bytes:
    profile = prof["data"]
    return render.render_pdf(
        s, profile, photo=prof["photo"], signature=prof["signature"],
        accent=profile["design"]["accent_color"] or branding()["accent_color"], font=branding()["pdf_font"],
        show_photo=g.get("show_photo", True), show_links=g.get("show_links", True))


def _file_name(profile: dict, company: str) -> str:
    def slug(x):
        return re.sub(r"[^\w-]+", "_", x or "").strip("_")[:40]
    return f"Bewerbung_{slug(profile['personal']['name'])}_{slug(company) or 'Unternehmen'}.pdf"


def _done() -> None:
    g = st.session_state.gen
    s = g["structured"]
    cl = s["cover_letter"]
    prof = db.get_profile(uid())
    pdf = st.session_state.gen_pdf
    st.title("Fertig! 🎉")
    pages = render.count_pages(pdf)
    if pages != 3:
        st.warning(f"Das PDF hat {pages} statt 3 Seiten – vermutlich ist das Anschreiben oder der Lebenslauf "
                   "zu lang. Unter 'Bearbeiten' kürzen.")
    st.download_button("⬇ PDF herunterladen (Deckblatt, Anschreiben, Lebenslauf)", pdf,
                       file_name=_file_name(prof["data"], cl.get("company")), mime="application/pdf",
                       type="primary", use_container_width=True)
    c1, c2 = st.columns(2)
    if c1.button("✏️ Bearbeiten", use_container_width=True):
        st.session_state.gen_step = "review"
        st.rerun()
    if c2.button("➕ Neue Bewerbung", use_container_width=True):
        reset()
        st.rerun()
    st.divider()
    app_id = st.session_state.get("gen_app_id")
    if app_id:
        if st.button("💾 Änderungen in 'Meine Bewerbungen' speichern", use_container_width=True):
            db.update_application(uid(), app_id, pdf_bytes=pdf, company=cl.get("company"),
                                  job_title=cl.get("job_title"),
                                  structured_data=json.dumps(s, ensure_ascii=False))
            st.success("Gespeichert.")
    elif st.button("✅ Als beworben speichern", use_container_width=True):
        st.session_state.gen_app_id = db.save_application(
            uid(), cl.get("company", ""), cl.get("job_title", ""), g["employment_type"], g["job_text"],
            g["job_url"], pdf, s)
        st.success("Gespeichert – du findest sie unter 'Meine Bewerbungen'.")
