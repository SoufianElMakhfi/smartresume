"""Jobs finden: Stellensuche (Jobbörse der Bundesagentur für Arbeit) → Passung → Bewerbung per Klick."""
from __future__ import annotations

import streamlit as st

from .. import bridge, db, jobsearch, llm
from ..profile import EMPLOYMENT_TYPES, default_employment_type, profile_city
from .common import available_models, chat_bridge, fallback_chain, go, notify_switch, record_usage, uid

STATE = ("jobs", "jobs_total", "jobs_texts", "jobs_query", "jobs_page", "jobs_ratings", "jobs_manual")
SORTS = ["Passung", "Neueste", "Entfernung"]


def _default_what(profile: dict) -> str:
    head = profile["personal"].get("headline", "")
    if head:
        return head
    exp = profile.get("experience") or []
    return exp[0].get("role", "") if exp else ""


def _chain():
    models = available_models()
    if not models:
        return None
    pref = db.get_user_settings(uid()).get("default_model")
    first = next((m for m in models if m[0]["label"] == pref), models[0])
    return fallback_chain(first)


def _run_search(query: dict, page: int) -> None:
    jobs, total = jobsearch.search(page=page, **query)
    texts = jobsearch.details_many(jobs)
    if page == 1:
        st.session_state.update(jobs=jobs, jobs_total=total, jobs_texts=texts, jobs_query=query, jobs_page=1,
                                jobs_ratings={}, jobs_manual=False)
    else:
        seen = {j["ref"] for j in st.session_state.jobs}
        st.session_state.jobs += [j for j in jobs if j["ref"] not in seen]
        st.session_state.jobs_texts.update(texts)
        st.session_state.jobs_page = page


def _rate(profile: dict) -> None:
    """KI-Bewertung für alle noch unbewerteten Stellen (ein Aufruf)."""
    ratings = st.session_state.jobs_ratings
    todo = [j for j in st.session_state.jobs if j["ref"] not in ratings][:25]
    if not todo:
        return
    system, user = jobsearch.rating_prompts(profile, todo, st.session_state.jobs_texts)
    chain = _chain()
    if chain:
        try:
            with st.spinner(f"KI bewertet {len(todo)} Stellen …"):
                res, (cfg, _) = llm.with_fallback(
                    chain, lambda c, k: llm.complete_json(c, k, system, user, max_tokens=4000, temperature=0.2,
                                                          validate=jobsearch.validate_ratings(len(todo))),
                    on_switch=notify_switch)
            ratings.update(jobsearch.apply_ratings(res.data, todo))
            record_usage("job_rating", cfg, res.input_tokens + res.output_tokens)
            return
        except llm.LLMError as e:
            st.warning(f"{e} Weiter geht es kostenlos mit deinem Gemini- oder ChatGPT-Konto.")
    st.session_state.jobs_manual = True


def _manual(profile: dict) -> None:
    todo = [j for j in st.session_state.jobs if j["ref"] not in st.session_state.jobs_ratings][:25]
    if not todo:
        st.session_state.jobs_manual = False
        return
    with st.container(border=True):
        st.markdown(f"#### Passung mit Gemini oder ChatGPT prüfen ({len(todo)} Stellen)")
        st.caption("Gemini oder ChatGPT vergleicht jede Anzeige mit deinem Profil und vergibt 0–100 %. "
                   "SmartResume zeigt die Bewertung danach an den Stellen an.")
        system, user = jobsearch.rating_prompts(profile, todo, st.session_state.jobs_texts)
        data = chat_bridge(bridge.chat_prompt(system, user), "jobs", validate=jobsearch.validate_ratings(len(todo)),
                           submit="Antwort übernehmen und Stellen bewerten")
        if data:
            st.session_state.jobs_ratings.update(jobsearch.apply_ratings(data, todo))
            st.session_state.jobs_manual = False
            st.rerun()
        if st.button("Abbrechen", key="jobs_manual_cancel", icon=":material/close:"):
            st.session_state.jobs_manual = False
            st.rerun()


def _apply(job: dict) -> None:
    text = st.session_state.jobs_texts.get(job["ref"])
    if not text:
        try:
            text = jobsearch.details_text(job)
        except jobsearch.JobSearchError as e:
            st.error(str(e))
            return
    from . import generate_page
    generate_page.reset()
    # Text statt Link übergeben: kein erneuter Abruf; der Link wird mit der Bewerbung gespeichert
    go("generate", gen_text=text, gen_url=job["url"], gen_etype=st.session_state.jobs_query["employment_type"])
    st.rerun()


def _card(job: dict, hits: list[str], rating: dict | None, applied: bool) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        where = job["location"] + (f" · {job['distance']} km" if job.get("distance") is not None else "")
        c1.markdown(f"**{job['title']}**  \n{job['company']} · {where}")
        facts = []
        if job["salary"]:
            facts.append(f":material/payments: {job['salary']}")
        if job["homeoffice"]:
            facts.append(":material/home_work: Homeoffice möglich")
        if job["published"]:
            d = job["published"][:10].split("-")
            facts.append(f":material/calendar_today: seit {d[2]}.{d[1]}." if len(d) == 3
                         else f":material/calendar_today: {job['published']}")
        if applied:
            facts.append(":green[:material/task_alt:] schon beworben")
        if facts:
            c1.caption(" · ".join(facts))
        if rating:
            color = "green" if rating["score"] >= 75 else "orange" if rating["score"] >= 50 else "red"
            c2.markdown(f"### :{color}[{rating['score']} %]")
            c1.markdown(f":material/insights: {rating['reason']}")
            if rating["missing"]:
                c1.caption("Fehlt: " + ", ".join(rating["missing"]))
        elif hits:
            c2.markdown(f"**{len(hits)}** Treffer")
        if hits:
            c1.caption("Passt zu deinem Profil: " + ", ".join(hits[:8]))
        b1, b2 = st.columns(2)
        if b1.button("Bewerbung erstellen", key=f"apply_{job['ref']}", type="primary", use_container_width=True,
                     icon=":material/edit_document:"):
            _apply(job)
        b2.link_button("Anzeige öffnen", job["url"], use_container_width=True, icon=":material/open_in_new:")
        text = st.session_state.jobs_texts.get(job["ref"])
        if text:
            with st.expander("Anzeigentext lesen"):
                st.text(text)


def render() -> None:
    st.title("Jobs finden")
    st.caption("Quelle: Jobbörse der Bundesagentur für Arbeit – die größte Stellendatenbank Deutschlands; viele "
               "Anzeigen von StepStone, Indeed & Co. stehen dort ebenfalls. Kein Konto nötig.")
    profile = db.get_profile(uid())["data"]
    settings = db.get_user_settings(uid())
    saved = settings.get("job_search") or {}

    with st.form("job_search"):
        c1, c2 = st.columns([3, 2])
        what = c1.text_input("Was?", value=saved.get("what", _default_what(profile)),
                             placeholder="z. B. Frontend Entwickler, Informationssicherheit, Buchhaltung")
        where = c2.text_input("Wo?", value=saved.get("where", profile_city(profile)), placeholder="Stadt oder PLZ")
        c3, c4, c5 = st.columns(3)
        etype = saved.get("employment_type") or default_employment_type(profile, settings.get("gen_prefs"))
        etype = c3.selectbox("Beschäftigungsart", EMPLOYMENT_TYPES,
                             index=EMPLOYMENT_TYPES.index(etype) if etype in EMPLOYMENT_TYPES else 0)
        radius = saved.get("radius", 25)
        radius = c4.selectbox("Umkreis", jobsearch.RADII, index=jobsearch.RADII.index(radius)
                              if radius in jobsearch.RADII else 2,
                              format_func=lambda r: "nur dieser Ort" if r == 0 else f"{r} km")
        ages = list(jobsearch.MAX_AGE)
        age = saved.get("age", "Letzte 30 Tage")
        age = c5.selectbox("Veröffentlicht", ages, index=ages.index(age) if age in ages else 3)
        submitted = st.form_submit_button("Suchen", type="primary", use_container_width=True, icon=":material/search:")

    if submitted:
        settings["job_search"] = {"what": what, "where": where, "employment_type": etype, "radius": radius, "age": age}
        db.save_user_settings(uid(), settings)
        query = {"what": what, "where": where, "radius": radius, "employment_type": etype,
                 "max_age": jobsearch.MAX_AGE[age]}
        try:
            with st.spinner("Suche Stellen und lade die Anzeigen …"):
                _run_search(query, 1)
        except jobsearch.JobSearchError as e:
            st.error(str(e))
            return

    jobs = st.session_state.get("jobs")
    if jobs is None:
        st.info("Tipp: Suchbegriff kurz halten (z. B. „Informationssicherheit“ statt eines ganzen Stellentitels) – "
                "die Jobbörse sucht nach allen Wörtern gleichzeitig.", icon=":material/lightbulb:")
        return
    if not jobs:
        st.warning("Keine Stellen gefunden. Versuche einen kürzeren oder allgemeineren Suchbegriff, einen größeren "
                   "Umkreis oder einen längeren Zeitraum.")
        return

    ratings = st.session_state.jobs_ratings
    keywords = jobsearch.profile_keywords(profile)
    hits = {j["ref"]: jobsearch.keyword_hits(st.session_state.jobs_texts.get(j["ref"], ""), keywords) for j in jobs}
    applications = db.list_applications(uid())

    c1, c2 = st.columns([3, 2])
    c1.markdown(f"**{st.session_state.jobs_total} Stellen gefunden**, {len(jobs)} geladen")
    unrated = sum(1 for j in jobs if j["ref"] not in ratings)
    if unrated and not st.session_state.get("jobs_manual"):
        if c2.button(f"KI-Passung prüfen ({min(unrated, 25)} Stellen)", use_container_width=True,
                     icon=":material/insights:",
                     help="Die KI vergleicht jede Anzeige mit deinem Profil und vergibt 0–100 %. "
                          "Ein Aufruf für alle Stellen (ca. 5.000–12.000 Tokens)."):
            _rate(profile)
            st.rerun()
    if st.session_state.get("jobs_manual"):
        _manual(profile)

    order = st.segmented_control("Sortieren nach", SORTS, default="Passung", key="jobs_sort") or "Passung"
    if order == "Passung":
        jobs = sorted(jobs, key=lambda j: (-(ratings.get(j["ref"], {}).get("score", -1)), -len(hits[j["ref"]])))
    elif order == "Neueste":
        jobs = sorted(jobs, key=lambda j: j["published"] or "", reverse=True)
    else:
        jobs = sorted(jobs, key=lambda j: j["distance"] if j.get("distance") is not None else 9999)

    for job in jobs:
        _card(job, hits[job["ref"]], ratings.get(job["ref"]), jobsearch.already_applied(job, applications))

    if len(st.session_state.jobs) < st.session_state.jobs_total:
        if st.button("Weitere Stellen laden", use_container_width=True):
            try:
                with st.spinner("Lade weitere Stellen …"):
                    _run_search(st.session_state.jobs_query, st.session_state.jobs_page + 1)
            except jobsearch.JobSearchError as e:
                st.error(str(e))
                return
            st.rerun()
