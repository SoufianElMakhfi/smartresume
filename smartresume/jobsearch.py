"""Stellensuche über die Jobbörse der Bundesagentur für Arbeit.

Die BA bietet keine offizielle API; die Jobbörse nutzt aber eine öffentliche Schnittstelle, die das
Projekt bundesAPI dokumentiert (https://github.com/bundesAPI/jobsuche-api). Kein Konto, kein Key nötig.
Kontaktdaten der Arbeitgeber gibt die Schnittstelle nicht heraus (Captcha) – die bleiben unangetastet.

Ablauf: search() → Liste von Stellen, details_text() → kompletter Anzeigentext für die Bewerbung.
"""
from __future__ import annotations

import base64
import re
from concurrent.futures import ThreadPoolExecutor

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-Key": "jobboerse-jobsuche", "User-Agent": "SmartResume (Open Source)"}
JOB_PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"

RADII = [0, 10, 25, 50, 100, 200]
MAX_AGE = {"Heute": 0, "Letzte 7 Tage": 7, "Letzte 14 Tage": 14, "Letzte 30 Tage": 30, "Alle": 100}

# Beschäftigungsart der App → Filter der BA (angebotsart: 1 Arbeit, 2 Selbstständigkeit, 4 Ausbildung,
# 34 Praktikum/Trainee/Werkstudent; arbeitszeit: vz, tz, mj). Die BA verknüpft Suchwörter mit UND –
# „Werkstudent Informationssicherheit“ findet daher „Werkstudium Informationssicherheit“ nicht. Deshalb:
# Filter 34 + Suchwort, zusätzlich eine Suche „Werkstudent <Suchwort>“; passende Titel („prefer“) zuerst.
_FILTERS = {
    "Vollzeit": {"angebotsart": 1, "arbeitszeit": "vz"},
    "Teilzeit": {"angebotsart": 1, "arbeitszeit": "tz"},
    "Werkstudent": {"angebotsart": 34, "word": "Werkstudent", "prefer": ("werkstud",)},
    "Praktikum": {"angebotsart": 34, "word": "Praktikum", "prefer": ("prakti",)},
    "Ausbildung": {"angebotsart": 4},
    "Minijob": {"angebotsart": 1, "arbeitszeit": "mj"},
    "Freelance": {"angebotsart": 2},
}


class JobSearchError(RuntimeError):
    pass


def build_params(what: str, where: str, radius: int, employment_type: str, max_age: int,
                 page: int = 1, size: int = 25) -> dict:
    f = _FILTERS.get(employment_type, {})
    what = (what or "").strip() or f.get("word", "")
    params = {"was": what, "wo": (where or "").strip(), "page": page, "size": size,
              "veroeffentlichtseit": max_age, "pav": "false"}
    if params["wo"] and radius:
        params["umkreis"] = radius
    for k in ("angebotsart", "arbeitszeit"):
        if k in f:
            params[k] = f[k]
    return {k: v for k, v in params.items() if v not in ("", None)}


def _get(path: str, params: dict | None = None, timeout: int = 20) -> dict:
    import requests
    try:
        r = requests.get(BASE + path, headers=HEADERS, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise JobSearchError(f"Die Jobbörse der Arbeitsagentur ist gerade nicht erreichbar ({e.__class__.__name__}).")
    if r.status_code == 404:
        raise JobSearchError("Diese Stelle gibt es nicht mehr.")
    if r.status_code >= 400:
        raise JobSearchError(f"Die Jobbörse der Arbeitsagentur hat die Anfrage abgelehnt (HTTP {r.status_code}). "
                             "Evtl. hat sich die Schnittstelle geändert – bitte später erneut versuchen.")
    try:
        return r.json()
    except ValueError:
        raise JobSearchError("Unerwartete Antwort der Jobbörse.")


def _salary(j: dict) -> str:
    unit = {"JAHRESGEHALT": "/Jahr", "MONATSGEHALT": "/Monat", "STUNDENLOHN": "/Std."}.get(
        j.get("verguetungsangabe", ""), "")

    def eur(x) -> str:
        return f"{x:,.0f} €".replace(",", ".") if x >= 100 else f"{x:.2f} €".replace(".", ",")
    if j.get("gehaltsspanneVon") and j.get("gehaltsspanneBis"):
        return f"{eur(j['gehaltsspanneVon'])}–{eur(j['gehaltsspanneBis'])}{unit}".replace(" €–", "–")
    if j.get("festgehalt"):
        return f"{eur(j['festgehalt'])}{unit}"
    return ""


def _location(j: dict) -> str:
    for loc in j.get("stellenlokationen") or []:
        a = (loc or {}).get("adresse") or {}
        s = " ".join(x for x in (a.get("plz", ""), a.get("ort", "")) if x)
        if s:
            return s
    return ""


def normalize(j: dict) -> dict:
    ref = j.get("referenznummer") or j.get("refnr") or ""
    return {
        "ref": ref,
        "title": re.sub(r"\s+", " ", j.get("stellenangebotsTitel") or j.get("titel") or "").strip(),
        "company": (j.get("firma") or j.get("arbeitgeber") or "").strip(),
        "location": _location(j),
        "distance": j.get("entfernung"),
        "published": j.get("datumErsteVeroeffentlichung") or (j.get("veroeffentlichungszeitraum") or {}).get("von", ""),
        "start": (j.get("eintrittszeitraum") or {}).get("von", ""),
        "salary": _salary(j),
        "homeoffice": bool(j.get("homeofficemoeglich")),
        "url": j.get("externeURL") or JOB_PAGE.format(ref=ref),
        "external": bool(j.get("externeURL")),
        "profession": j.get("hauptberuf", ""),
    }


def search(what: str, where: str, radius: int = 25, employment_type: str = "Vollzeit", max_age: int = 30,
           page: int = 1, size: int = 25) -> tuple[list[dict], int]:
    """Gibt (Stellen, Gesamtzahl) zurück."""
    if not (what or "").strip() and not (where or "").strip():
        raise JobSearchError("Bitte einen Suchbegriff oder Ort angeben.")
    params = build_params(what, where, radius, employment_type, max_age, page, size)
    data = _get("/pc/v6/jobs", params)
    jobs = [normalize(j) for j in data.get("ergebnisliste") or data.get("stellenangebote") or []]
    total = int(data.get("maxErgebnisse") or len(jobs))
    f = _FILTERS.get(employment_type, {})
    word = f.get("word", "")
    if word and page == 1 and word.lower() not in params["was"].lower():
        extra_params = {k: v for k, v in params.items() if k != "angebotsart"}
        extra_params["was"] = f"{word} {params['was']}"
        extra = _get("/pc/v6/jobs", extra_params)
        seen = {j["ref"] for j in jobs}
        new = [n for n in (normalize(j) for j in extra.get("ergebnisliste") or []) if n["ref"] not in seen]
        jobs += new
        total += len(new)
    prefer = f.get("prefer")
    if prefer:   # stabile Sortierung: passende Titel zuerst, sonst Reihenfolge der BA
        jobs.sort(key=lambda j: not any(w in j["title"].lower() for w in prefer))
    return [j for j in jobs if j["ref"]], total


def details(ref: str) -> dict:
    code = base64.b64encode(ref.encode()).decode()
    return _get(f"/pc/v4/jobdetails/{code}")


def details_text(job: dict, raw: dict | None = None) -> str:
    """Kompletter Anzeigentext im selben Format wie ein eingefügter Text (für die Bewerbung)."""
    raw = raw if raw is not None else details(job["ref"])
    parts = [f"Stellentitel: {job['title']}", f"Unternehmen: {job['company']}"]
    if job.get("location"):
        parts.append(f"Ort: {job['location']}")
    if job.get("salary"):
        parts.append(f"Vergütung laut Anzeige: {job['salary']}")
    if job.get("start"):
        parts.append(f"Eintritt ab: {job['start']}")
    if raw.get("vertragsdauer") == "BEFRISTET" and raw.get("befristungInMonaten"):
        parts.append(f"Befristet: {raw['befristungInMonaten']} Monate")
    desc = (raw.get("stellenangebotsBeschreibung") or "").strip()
    return "\n".join(parts) + ("\n\n" + desc if desc else "")


def details_many(jobs: list[dict], workers: int = 6) -> dict[str, str]:
    """Anzeigentexte für mehrere Stellen parallel laden: {ref: text}. Fehlende Stellen werden ausgelassen."""
    def one(job):
        try:
            return job["ref"], details_text(job)
        except JobSearchError:
            return job["ref"], ""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return {ref: text for ref, text in ex.map(one, jobs) if text}


# ---------------------------------------------------------------------------
# Passung
# ---------------------------------------------------------------------------
def profile_keywords(profile: dict) -> list[str]:
    """Skills und Begriffe aus dem Profil, nach denen in Anzeigen gesucht wird."""
    words: list[str] = []
    for group in profile.get("skills") or []:
        items = group.get("items") or [] if isinstance(group, dict) else [group]
        for item in items:
            words += [w.strip() for w in re.split(r"\s*/\s*|,\s*", str(item)) if w.strip()]
    for p in profile.get("projects") or []:
        if isinstance(p, dict):
            words += [str(s) for s in p.get("stack") or [] if s]
    for lang in profile.get("languages") or []:
        if isinstance(lang, dict) and lang.get("language"):
            words.append(lang["language"])
    seen, out = set(), []
    for w in words:
        if 1 < len(w) <= 40 and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits = []
    for k in keywords:
        if re.search(r"(?<![\w.+#-])" + re.escape(k) + r"(?![\w+#-])", text, re.IGNORECASE):
            hits.append(k)
    return hits


def already_applied(job: dict, applications: list[dict]) -> bool:
    def norm(s):
        return re.sub(r"\W+", " ", (s or "").lower()).strip()
    c, t = norm(job["company"]), norm(job["title"])
    for a in applications:
        ac, at = norm(a.get("company")), norm(a.get("job_title"))
        if ac and c and (ac in c or c in ac) and at and t and (at[:25] in t or t[:25] in at):
            return True
    return False


RATING_SYSTEM = """Du bist eine erfahrene Recruiterin. Bewerte, wie gut ein Bewerberprofil zu Stellenanzeigen passt.
Regeln:
- score 0–100: 80+ = klar passend, 60–79 = gut möglich, 40–59 = mit Lücken, <40 = passt kaum.
- Bewerte nur anhand der Fakten im Profil, nichts dazuerfinden. Pflichtanforderungen wiegen schwerer als Wünsche.
- Beachte Beschäftigungsart, Abschluss/Studium und Sprachanforderungen.
- reason: ein kurzer deutscher Satz (max. 20 Wörter), warum.
- missing: höchstens 3 wichtige Anforderungen, die im Profil fehlen (kurz).
Antworte ausschließlich mit JSON: {"ratings": [{"id": "J1", "score": 0, "reason": "", "missing": []}]}"""


def _profile_brief(profile: dict) -> str:
    p = profile.get("personal", {})
    lines = [f"Titel: {p.get('headline', '')}"]
    if profile.get("summary"):
        lines.append(f"Kurzprofil: {profile['summary'][:400]}")
    for e in (profile.get("experience") or [])[:6]:
        lines.append(f"Station: {e.get('role', '')} bei {e.get('company', '')} ({e.get('start', '')}–{e.get('end', '')})")
    for e in (profile.get("education") or [])[:4]:
        lines.append(f"Ausbildung: {e.get('degree', '')}, {e.get('institution', '')} ({e.get('end', '')})")
    lines.append("Skills: " + ", ".join(profile_keywords(profile)[:60]))
    status = (profile.get("preferences") or {}).get("student_status")
    if status:
        lines.append(f"Studium: {status}")
    return "\n".join(lines)


def rating_prompts(profile: dict, jobs: list[dict], texts: dict[str, str], chars: int = 1800) -> tuple[str, str]:
    blocks = []
    for i, job in enumerate(jobs, 1):
        text = texts.get(job["ref"]) or f"Stellentitel: {job['title']}\nUnternehmen: {job['company']}"
        blocks.append(f"### J{i}\n{text[:chars]}")
    user = f"PROFIL\n{_profile_brief(profile)}\n\nSTELLEN\n" + "\n\n".join(blocks)
    return RATING_SYSTEM, user


def validate_ratings(n: int):
    def check(data: dict) -> list[str]:
        r = data.get("ratings")
        if not isinstance(r, list) or not r:
            return ["'ratings' fehlt oder ist leer"]
        ids = {str(x.get("id")) for x in r if isinstance(x, dict)}
        missing = [f"J{i}" for i in range(1, n + 1) if f"J{i}" not in ids]
        if len(missing) > n // 3:
            return [f"Bewertungen fehlen für {', '.join(missing[:5])}"]
        return []
    return check


def apply_ratings(data: dict, jobs: list[dict]) -> dict[str, dict]:
    """{ref: {"score", "reason", "missing"}} aus der KI-Antwort."""
    out = {}
    for r in data.get("ratings") or []:
        m = re.fullmatch(r"J(\d+)", str(r.get("id", "")).strip())
        if not m or not 1 <= int(m.group(1)) <= len(jobs):
            continue
        try:
            score = max(0, min(100, int(float(r.get("score", 0)))))
        except (TypeError, ValueError):
            continue
        missing = r.get("missing") or []
        out[jobs[int(m.group(1)) - 1]["ref"]] = {
            "score": score, "reason": str(r.get("reason") or "").strip(),
            "missing": [str(x) for x in missing][:3] if isinstance(missing, list) else []}
    return out
