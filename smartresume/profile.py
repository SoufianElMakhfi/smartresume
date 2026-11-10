"""Generisches Bewerberprofil.

Ein Profil ist ein einfaches dict (JSON-serialisierbar), damit es 1:1 in der
Datenbank gespeichert, aus einem CV extrahiert oder manuell bearbeitet werden kann.
`normalize_profile` ist die einzige Stelle, die Struktur und Typen garantiert –
alles, was von außen kommt (KI, Upload, Formular), läuft dort durch.
"""
from __future__ import annotations

import copy
import re
from datetime import date

EMPLOYMENT_TYPES = [
    "Vollzeit",
    "Teilzeit",
    "Werkstudent",
    "Praktikum",
    "Ausbildung",
    "Minijob",
    "Freelance",
]


def empty_profile() -> dict:
    return {
        "personal": {
            "name": "",
            "headline": "",
            "email": "",
            "phone": "",
            "street": "",
            "zip_city": "",
            "links": [],  # [{"label": "Portfolio", "url": "https://..."}]
        },
        "summary": "",
        "experience": [],  # [{"company","role","start","end","location","bullets":[...]}]
        "education": [],   # [{"institution","degree","start","end","location","details"}]
        "skills": [],      # [{"category": "...", "items": ["...", "..."]}]
        "languages": [],   # [{"language": "Deutsch", "level": "Muttersprache"}]
        "projects": [],    # [{"name","description","stack":[...],"highlights":[...]}]
        "certificates": [],  # ["AWS Cloud Practitioner (2024)", ...]
        "strengths": [],   # [{"skill": "...", "evidence": "konkreter Beleg"}]
        "preferences": {
            "availability": "",
            "notice_period": "",
            "salary_expectation": "",
            "hours_per_week": "",
            "student_status": "",  # z.B. "Eingeschrieben, B.Sc. Informatik, 4. Semester"
        },
        "writing_style": {
            "tone": "",
            "own_words": [],
            "philosophy": "",
            "forbidden_phrases": [],
        },
        "design": {
            "accent_color": "",  # leer = Branding-Standard
        },
    }


# ---------------------------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------------------------
_CITE_RE = re.compile(r"\s*\[cite:[^\]]*\]")


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_s(x) for x in v if _s(x))
    return _CITE_RE.sub("", str(v)).strip()


def _str_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        parts = re.split(r"[\n;]|,(?![^()]*\))", v)
        return [p.strip(" •-\t") for p in parts if p.strip(" •-\t")]
    out = []
    for x in v:
        if isinstance(x, dict):
            x = x.get("text") or x.get("name") or ""
        x = _s(x)
        if x:
            out.append(x)
    return out


def _dict_list(v, fields: dict) -> list[dict]:
    """Normalisiert eine Liste von dicts. `fields` mappt Feldname → 'str' | 'list'."""
    out = []
    for item in v or []:
        if not isinstance(item, dict):
            continue
        norm = {}
        for f, kind in fields.items():
            norm[f] = _str_list(item.get(f)) if kind == "list" else _s(item.get(f))
        if any(norm.values()):
            out.append(norm)
    return out


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_profile(data: dict | None) -> dict:
    data = copy.deepcopy(data or {})
    p = empty_profile()

    pers = data.get("personal") or {}
    for k in ("name", "headline", "email", "phone", "street", "zip_city"):
        p["personal"][k] = _s(pers.get(k))
    links = []
    for link in pers.get("links") or []:
        if isinstance(link, dict) and _s(link.get("url")):
            url = _s(link["url"])
            if not re.match(r"^https?://", url):
                url = "https://" + url
            links.append({"label": _s(link.get("label")) or guess_link_label(url), "url": url})
    p["personal"]["links"] = links

    p["summary"] = _s(data.get("summary"))
    p["experience"] = _dict_list(data.get("experience"), {
        "company": "str", "role": "str", "start": "str", "end": "str",
        "location": "str", "bullets": "list"})
    p["education"] = _dict_list(data.get("education"), {
        "institution": "str", "degree": "str", "start": "str", "end": "str",
        "location": "str", "details": "str"})
    p["skills"] = [s for s in _dict_list(data.get("skills"), {"category": "str", "items": "list"})
                   if s["items"]]
    p["languages"] = _dict_list(data.get("languages"), {"language": "str", "level": "str"})
    p["projects"] = _dict_list(data.get("projects"), {
        "name": "str", "description": "str", "stack": "list", "highlights": "list"})
    p["certificates"] = _str_list(data.get("certificates"))
    p["strengths"] = _dict_list(data.get("strengths"), {"skill": "str", "evidence": "str"})

    for section in ("preferences", "writing_style", "design"):
        src = data.get(section) or {}
        for k, default in p[section].items():
            p[section][k] = _str_list(src.get(k)) if isinstance(default, list) else _s(src.get(k))
    if p["design"]["accent_color"] and not _HEX_RE.match(p["design"]["accent_color"]):
        p["design"]["accent_color"] = ""
    return p


def guess_link_label(url: str) -> str:
    u = url.lower()
    if "linkedin." in u:
        return "LinkedIn"
    if "github." in u:
        return "GitHub"
    if "xing." in u:
        return "XING"
    if "behance." in u or "dribbble." in u:
        return "Portfolio"
    return "Website"


def link_icon(label: str, url: str) -> str:
    """Name des Icons in icons/ (ohne .svg)."""
    s = f"{label} {url}".lower()
    if "linkedin" in s:
        return "linkedin"
    if "github" in s:
        return "github"
    return "globe"


def profile_city(profile: dict) -> str:
    """Stadt für 'Ort, den Datum' aus PLZ/Ort (z.B. '51069 Köln' → 'Köln')."""
    zc = profile.get("personal", {}).get("zip_city", "")
    return re.sub(r"^\s*\d{4,5}\s*", "", zc).strip()


def default_employment_type(profile: dict, prefs: dict | None = None) -> str:
    """Zuletzt gewählte Beschäftigungsart; sonst Werkstudent, wenn ein Studium im Profil steht."""
    last = (prefs or {}).get("employment_type")
    if last in EMPLOYMENT_TYPES:
        return last
    return "Werkstudent" if (profile.get("preferences") or {}).get("student_status") else "Vollzeit"


def is_profile_usable(profile: dict) -> list[str]:
    """Gibt fehlende Pflichtangaben zurück (leere Liste = ok)."""
    missing = []
    pers = profile.get("personal", {})
    if not pers.get("name"):
        missing.append("Name")
    elif len(pers["name"].split()) < 2:
        missing.append("Nachname (unter *Persönliches* den vollen Namen eintragen)")
    if not pers.get("email"):
        missing.append("E-Mail")
    if not profile.get("experience") and not profile.get("education"):
        missing.append("mindestens eine Berufserfahrung oder Ausbildung")
    return missing


# ---------------------------------------------------------------------------
# Berufserfahrung in Jahren (für Plausibilitätsprüfung "X Jahre Erfahrung")
# ---------------------------------------------------------------------------
_DATE_RE = re.compile(r"(?:(\d{1,2})[./])?(\d{4})")


def _parse_date(s: str, end: bool = False) -> date | None:
    s = (s or "").strip().lower()
    if not s:
        return None
    if s in ("heute", "aktuell", "jetzt", "present", "today", "laufend", "now"):
        return date.today()
    m = _DATE_RE.search(s)
    if not m:
        return None
    month = int(m.group(1)) if m.group(1) else (12 if end else 1)
    month = min(max(month, 1), 12)
    return date(int(m.group(2)), month, 1)


def total_experience_years(profile: dict) -> float:
    """Summe der Berufserfahrung in Jahren (überlappende Zeiträume zusammengeführt)."""
    ranges = []
    for job in profile.get("experience", []):
        a = _parse_date(job.get("start", ""))
        b = _parse_date(job.get("end", ""), end=True) or date.today()
        if a and b and b >= a:
            ranges.append((a, b))
    ranges.sort()
    merged: list[list[date]] = []
    for a, b in ranges:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    days = sum((b - a).days for a, b in merged)
    return round(days / 365.25, 1)


# ---------------------------------------------------------------------------
# Kompakte Textdarstellung für Prompts (spart Tokens ggü. JSON mit indent)
# ---------------------------------------------------------------------------
def compact_profile_text(profile: dict) -> str:
    """Kompakte, nummerierte Darstellung. Die Nummern (E1, B1.2, S1 …) werden
    von der KI als Referenzen genutzt – so muss sie keine Fakten zurückschreiben."""
    lines = []
    pers = profile["personal"]
    lines.append(f"NAME: {pers['name']}" + (f" | {pers['headline']}" if pers["headline"] else ""))
    if profile.get("summary"):
        lines.append(f"PROFIL: {profile['summary']}")
    if profile["experience"]:
        lines.append("ERFAHRUNG:")
        for i, job in enumerate(profile["experience"], 1):
            lines.append(f"E{i}: {job['role']} @ {job['company']} ({job['start']}–{job['end']})")
            for j, b in enumerate(job["bullets"], 1):
                lines.append(f"  E{i}.{j} {b}")
    if profile["education"]:
        lines.append("AUSBILDUNG:")
        for i, ed in enumerate(profile["education"], 1):
            det = f" – {ed['details']}" if ed["details"] else ""
            lines.append(f"A{i}: {ed['degree']}, {ed['institution']} ({ed['start']}–{ed['end']}){det}")
    if profile["skills"]:
        lines.append("SKILLS:")
        for i, s in enumerate(profile["skills"], 1):
            lines.append(f"S{i} {s['category']}: {', '.join(s['items'])}")
    if profile["languages"]:
        lines.append("SPRACHEN: " + ", ".join(
            f"{l['language']} ({l['level']})" if l["level"] else l["language"] for l in profile["languages"]))
    if profile["certificates"]:
        lines.append("ZERTIFIKATE: " + "; ".join(profile["certificates"]))
    if profile["projects"]:
        lines.append("PROJEKTE:")
        for p in profile["projects"]:
            parts = [p["name"]]
            if p["description"]:
                parts.append(p["description"])
            if p["stack"]:
                parts.append("Stack: " + ", ".join(p["stack"]))
            if p["highlights"]:
                parts.append("Highlights: " + " / ".join(p["highlights"]))
            lines.append("- " + " | ".join(parts))
    if profile["strengths"]:
        lines.append("STÄRKEN (mit Beleg):")
        for s in profile["strengths"]:
            lines.append(f"- {s['skill']}: {s['evidence']}")
    prefs = {k: v for k, v in profile["preferences"].items() if v}
    if prefs:
        names = {"availability": "Verfügbar", "notice_period": "Kündigungsfrist",
                 "salary_expectation": "Gehaltswunsch", "hours_per_week": "Std/Woche",
                 "student_status": "Studium"}
        lines.append("RAHMEN: " + "; ".join(f"{names[k]}: {v}" for k, v in prefs.items()))
    lines.append(f"BERUFSERFAHRUNG GESAMT: ca. {total_experience_years(profile)} Jahre")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Migration des alten master_profile.json (v1, Einzelnutzer)
# ---------------------------------------------------------------------------
def from_legacy_master(d: dict) -> dict:
    info = d.get("personal_info", {})
    loc = _s(info.get("location"))
    street, zip_city = "", loc
    if "," in loc:
        street, zip_city = [x.strip() for x in loc.split(",", 1)]
    links = []
    for key, label in (("portfolio", "Portfolio"), ("github", "GitHub"), ("linkedin", "LinkedIn")):
        if info.get(key):
            links.append({"label": label, "url": info[key]})

    experience = []
    for e in d.get("experience", []):
        bullets = [x["text"] if isinstance(x, dict) else x for x in e.get("responsibilities_pool", [])]
        experience.append({
            "company": e.get("company"), "role": e.get("role"),
            "start": e.get("start_date"), "end": e.get("end_date"),
            "location": e.get("location"), "bullets": bullets,
        })
    education = [{
        "institution": e.get("institution"), "degree": e.get("degree"),
        "start": e.get("start_date"), "end": e.get("end_date"),
        "location": e.get("location"), "details": e.get("details", ""),
    } for e in d.get("education", [])]

    skills, languages = [], []
    for cat, val in (d.get("skills") or {}).items():
        items = val.get("items", []) if isinstance(val, dict) else val
        if cat.lower() in ("sprachen", "languages"):
            for it in items:
                m = re.match(r"(.+?)\s*\((.+)\)", it)
                languages.append({"language": m.group(1), "level": m.group(2)} if m else {"language": it})
        else:
            skills.append({"category": cat, "items": items})

    projects = [{
        "name": p.get("name"),
        "description": " – ".join(x for x in (p.get("type"), p.get("tagline")) if x),
        "stack": p.get("stack", []), "highlights": p.get("highlights", []),
    } for p in d.get("projects", [])]
    strengths = [{"skill": t.get("skill"), "evidence": t.get("context")}
                 for t in d.get("transferable_skills", [])]
    voice = d.get("personal_voice", {})

    return normalize_profile({
        "personal": {"name": info.get("name"), "email": info.get("email"), "phone": info.get("phone"),
                     "street": street, "zip_city": zip_city, "links": links},
        "summary": d.get("professional_summary"),
        "experience": experience,
        "education": education,
        "skills": skills,
        "languages": languages,
        "projects": projects,
        "strengths": strengths,
        "preferences": {"availability": d.get("availability"),
                        "salary_expectation": d.get("salary_expectation")},
        "writing_style": {"tone": voice.get("tone"), "own_words": voice.get("own_words"),
                          "philosophy": voice.get("philosophy"),
                          "forbidden_phrases": voice.get("forbidden_phrases")},
    })
