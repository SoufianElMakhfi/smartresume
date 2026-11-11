"""Jobs finden: Stellensuche (Jobbörse der Bundesagentur für Arbeit) → Passung → Bewerbung per Klick."""
from __future__ import annotations

import streamlit as st

from .. import bridge, db, jobsearch, llm
from ..profile import EMPLOYMENT_TYPES, default_employment_type, profile_city
from .common import available_models, chat_bridge, fallback_chain, go, notify_switch, record_usage, uid

STATE = ("jobs", "jobs_total", "jobs_texts", "jobs_query", "jobs_shown", "jobs_ratings", "jobs_manual")
PAGE = 25          # so viele Stellen auf einmal anzeigen (deren Anzeigentexte werden dann geladen)
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


def _run_search(query: dict) -> None:
    jobs, total = jobsearch.search(**query)
    st.session_state.update(jobs=jobs, jobs_total=total, jobs_texts=jobsearch.details_many(jobs[:PAGE]),
                            jobs_query=query, jobs_shown=PAGE, jobs_ratings={}, jobs_manual=False)


def _load_texts(jobs: list[dict]) -> None:
    """Anzeigentexte der sichtbaren Stellen nachladen (für Profil-Treffer, KI-Passung und Bewerbung)."""
    missing = [j for j in jobs if j["ref"] not in st.session_state.jobs_texts]
    if missing:
        with st.spinner(f"Lade {len(missing)} Anzeigen …"):
            st.session_state.jobs_texts.update(jobsearch.details_many(missing))


def _rate(profile: dict, visible: list[dict]) -> None:
    """KI-Bewertung für die sichtbaren, noch unbewerteten Stellen (ein Aufruf)."""
    ratings = st.session_state.jobs_ratings
    todo = [j for j in visible if j["ref"] not in ratings][:PAGE]
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


def _manual(profile: dict, visible: list[dict]) -> None:
    todo = [j for j in visible if j["ref"] not in st.session_state.jobs_ratings][:PAGE]
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
                             placeholder="z. B. Software, Marketing, Controlling, Informationssicherheit")
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
            with st.spinner("Suche Stellen …"):
                _run_search(query)
        except jobsearch.JobSearchError as e:
            st.error(str(e))
            return

    jobs = st.session_state.get("jobs")
    if jobs is None:
        st.info("Ein allgemeiner Begriff reicht, z. B. „Software“, „Marketing“ oder „Controlling“. Verwandte "
                "Begriffe (bei „Software“ etwa Informatik, Developer, Fullstack) werden automatisch mitgesucht, "
                "unpassende Anzeigen aussortiert. „Was?“ leer lassen zeigt alle Stellen der gewählten Art im Umkreis.",
                icon=":material/lightbulb:")
        return
    query = st.session_state.jobs_query
    fields = jobsearch.plan(query["what"])["fields"]
    if not jobs:
        st.warning("Keine passenden Stellen gefunden. Versuche einen allgemeineren Suchbegriff, einen größeren "
                   "Umkreis oder einen längeren Zeitraum.")
        return

    ratings = st.session_state.jobs_ratings
    order = st.segmented_control("Sortieren nach", SORTS, default="Passung", key="jobs_sort") or "Passung"
    texts = st.session_state.jobs_texts
    keywords = jobsearch.profile_keywords(profile)

    def hits_of(j):
        return jobsearch.keyword_hits(texts.get(j["ref"], ""), keywords)
    if order == "Passung":   # KI-Bewertung > Relevanz zum Suchbegriff > Treffer mit dem Profil
        jobs = sorted(jobs, key=lambda j: (-(ratings.get(j["ref"], {}).get("score", -1)), -j.get("relevance", 0),
                                           -len(hits_of(j))))
    elif order == "Neueste":
        jobs = sorted(jobs, key=lambda j: j["published"] or "", reverse=True)
    else:
        jobs = sorted(jobs, key=lambda j: j["distance"] if j.get("distance") is not None else 9999)
    visible = jobs[:st.session_state.get("jobs_shown", PAGE)]
    _load_texts(visible)
    applications = db.list_applications(uid())

    c1, c2 = st.columns([3, 2])
    c1.markdown(f"**{st.session_state.jobs_total} Stellen gefunden**, {len(visible)} angezeigt")
    if fields:
        c1.caption("Fachgebiet erkannt: " + ", ".join(fields) + " – verwandte Begriffe wurden mitgesucht.")
    unrated = sum(1 for j in visible if j["ref"] not in ratings)
    if unrated and not st.session_state.get("jobs_manual"):
        if c2.button(f"KI-Passung prüfen ({min(unrated, PAGE)} Stellen)", use_container_width=True,
                     icon=":material/insights:",
                     help="Die KI vergleicht jede angezeigte Anzeige mit deinem Profil und vergibt 0–100 %. "
                          "Ein Aufruf für alle (ca. 5.000–12.000 Tokens)."):
            _rate(profile, visible)
            st.rerun()
    if st.session_state.get("jobs_manual"):
        _manual(profile, visible)

    for job in visible:
        _card(job, hits_of(job), ratings.get(job["ref"]), jobsearch.already_applied(job, applications))

    rest = len(jobs) - len(visible)
    if rest > 0:
        if st.button(f"Weitere {min(rest, PAGE)} Stellen anzeigen (noch {rest})", use_container_width=True,
                     icon=":material/expand_more:"):
            st.session_state.jobs_shown = len(visible) + PAGE
            st.rerun()
