"""Bewerbung erzeugen: Prompt → KI → Zusammenbau mit Profildaten → Qualitäts-Check.

Die KI liefert nur Referenzen + zugeschnittene Texte. Firmen, Zeiträume, Orte und
Ausbildung kommen immer aus dem Profil – dadurch sind sie fälschungssicher und die
Antwort der KI ist deutlich kürzer (weniger Output-Tokens).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import llm, prompts, quality
from .profile import EMPLOYMENT_TYPES

MAX_BULLET_CHARS = 80
MAX_JOB_CHARS = 7000

_JUNK_LINE = re.compile(
    r"^(cookie|datenschutz|impressum|agb|anmelden|login|registrieren|teilen|share|merken|"
    r"jetzt bewerben|zurück|weiter|menü|suche|newsletter|alle rechte|©)", re.IGNORECASE)


def clean_job_text(text: str, limit: int = MAX_JOB_CHARS) -> str:
    """Entfernt Navigation/Cookie-Müll und Duplikate aus gescrapten Anzeigen und
    kürzt auf `limit` Zeichen – spart oft 50–80 % der Input-Tokens."""
    out, seen = [], set()
    for line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 3 or _JUNK_LINE.match(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    cleaned = "\n".join(out)
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rsplit("\n", 1)[0] + "\n[…gekürzt]"
    return cleaned


# ---------------------------------------------------------------------------
# Bullet-Kürzung (Sicherheitsnetz, falls die KI das Limit ignoriert)
# ---------------------------------------------------------------------------
def shorten_bullet(text: str, limit: int = MAX_BULLET_CHARS) -> str:
    text = re.sub(r"\s+", " ", text or "").strip().rstrip(".")
    if len(text) <= limit:
        return text
    for pattern in (r"\s+inkl\.\s+[^,]+", r"\s+sowie\s+[^,]+", r"\s+im Rahmen (?:von|des|der)[^,]*",
                    r"\s+zur\s+[^,]+", r"\s+um\s+[^,]+zu\s+\w+", r"\s*\([^)]*\)"):
        cand = re.sub(pattern, "", text).strip()
        if cand and len(cand) <= limit:
            return cand
        if len(cand) < len(text):
            text = cand
    for sep in (", ", " und "):
        idx = text.rfind(sep, 0, limit + 1)
        if idx > 20:
            return text[:idx].strip()
    cut = text[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > 20 else cut).rstrip(" ,;–-")


# ---------------------------------------------------------------------------
# Zusammenbau
# ---------------------------------------------------------------------------
def _dates(a: str, b: str) -> str:
    return " – ".join(x for x in (a, b) if x)


def _ref_index(ref, prefix: str) -> int | None:
    m = re.match(rf"^\s*{prefix}?(\d+)", str(ref or ""), re.IGNORECASE)
    return int(m.group(1)) - 1 if m else None


def _parse_extra_skills(extra_info: str) -> list[str]:
    items = re.split(r"[,;\n]", extra_info or "")
    return [i.strip(" •-") for i in items if 1 < len(i.strip(" •-")) <= 40]


_GENDER_RE = re.compile(r"\s*\(\s*(?:[mwdfxi]|div|all)(?:\s*[/|,]\s*(?:[mwdfxi]|div|all))+\s*\)|\s*\*\s*$",
                        re.IGNORECASE)


def clean_job_title(title: str) -> str:
    """'Frontend Developer (m/w/d)' → 'Frontend Developer' (für Betreff & Deckblatt)."""
    return re.sub(r"\s{2,}", " ", _GENDER_RE.sub("", title or "")).strip(" -–")


_ASKS_SALARY = re.compile(r"gehaltsvorstellung|gehaltswunsch|gehaltsvorstellungen|gehaltsangabe", re.IGNORECASE)
_ASKS_START = re.compile(r"eintrittstermin|frühestmöglich|verfügbarkeit|startdatum|kündigungsfrist|"
                         r"eintrittsdatum|ab wann", re.IGNORECASE)


def closing_facts(ai_job: dict, job_text: str, profile: dict) -> str:
    """Gehalt/Eintritt deterministisch aus dem Profil – die KI darf das nicht selbst formulieren."""
    prefs = profile["preferences"]
    asks_salary = bool(ai_job.get("asks_salary")) or bool(_ASKS_SALARY.search(job_text or ""))
    asks_start = bool(ai_job.get("asks_start_date")) or bool(_ASKS_START.search(job_text or ""))
    parts = []
    if asks_salary and prefs["salary_expectation"]:
        parts.append(f"Meine Gehaltsvorstellung liegt bei {prefs['salary_expectation']}.")
    if asks_start:
        avail = prefs["availability"]
        if avail:
            if not re.match(r"^(ab|zum|nach|sofort|innerhalb|mit)\b", avail, re.IGNORECASE):
                avail = f"ab {avail}"
            parts.append(f"Ein Eintritt ist {avail} möglich.")
        if prefs["notice_period"]:
            parts.append(f"Meine Kündigungsfrist beträgt {prefs['notice_period']}.")
    return " ".join(parts)


def _match_category(name: str, items: list, profile: dict) -> str:
    """Ordnet eine von der KI benannte Kategorie einer echten Profilkategorie zu."""
    cats = [s["category"] for s in profile["skills"]]
    for c in cats:
        if c.lower() == (name or "").strip().lower():
            return c
    wanted = {str(i).strip().lower() for i in items}
    best, score = "", 0
    for s in profile["skills"]:
        hit = len(wanted & {i.lower() for i in s["items"]})
        if hit > score:
            best, score = s["category"], hit
    return best or "Weitere Kenntnisse"


def assemble(ai: dict, profile: dict, employment_type: str, extra_info: str = "",
             bullets_per_job: int = 2, max_bullet_chars: int = MAX_BULLET_CHARS, job_text: str = "") -> dict:
    """Baut aus KI-Antwort + Profil die vollständige, renderbare Struktur."""
    ai = normalize_text(ai)
    job = ai.get("job") or {}

    # Erfahrung: alle Stationen aus dem Profil, Bullets von der KI (Fallback: Profil)
    ai_bullets: dict[int, list[str]] = {}
    for e in ai.get("experience") or []:
        idx = _ref_index(e.get("ref"), "E")
        if idx is not None and isinstance(e.get("bullets"), list):
            ai_bullets[idx] = [str(b) for b in e["bullets"] if str(b).strip()]
    experience = []
    for i, src in enumerate(profile["experience"]):
        bullets = ai_bullets.get(i) or src["bullets"]
        bullets = [shorten_bullet(b, max_bullet_chars) for b in bullets][:bullets_per_job]
        experience.append({"company": src["company"], "role": src["role"],
                           "dates": _dates(src["start"], src["end"]), "location": src["location"],
                           "bullets": bullets})

    education = [{"institution": e["institution"], "degree": e["degree"],
                  "dates": _dates(e["start"], e["end"]), "location": e["location"],
                  "detail": e["details"]} for e in profile["education"]]

    # Skills: nur Einträge, die wirklich im Profil/den Zusatzangaben stehen
    extra = _parse_extra_skills(extra_info)
    allowed_all = {i.lower(): i for s in profile["skills"] for i in s["items"]}
    allowed_all.update({x.lower(): x for x in extra})
    skills, used_cats = [], set()
    for s in ai.get("skills") or []:
        idx = _ref_index(s.get("ref"), "S")
        if idx is not None and 0 <= idx < len(profile["skills"]):
            cat = profile["skills"][idx]["category"]
            pool = {i.lower(): i for i in profile["skills"][idx]["items"]}
            pool.update({x.lower(): x for x in extra})
        else:
            cat = _match_category(str(s.get("category") or ""), s.get("items") or [], profile)
            pool = allowed_all
        if cat in used_cats:
            continue
        items = []
        for it in s.get("items") or []:
            key = str(it).strip().lower()
            if key in pool and pool[key] not in items:
                items.append(pool[key])
        if items:
            skills.append({"category": cat, "items": ", ".join(items[:6])})
            used_cats.add(cat)
        if len(skills) >= 5:
            break
    if not skills:  # Fallback: die ersten Kategorien des Profils
        skills = [{"category": s["category"], "items": ", ".join(s["items"][:6])} for s in profile["skills"][:4]]
    if extra and not any(x in s["items"] for s in skills for x in extra):
        skills.append({"category": "Weitere Kenntnisse", "items": ", ".join(extra[:6])})
    if profile["languages"]:
        skills.append({"category": "Sprachen", "items": ", ".join(
            f"{l['language']} ({l['level']})" if l["level"] else l["language"] for l in profile["languages"])})

    cl = ai.get("cover_letter") or {}
    job_title = clean_job_title(str(job.get("job_title") or ""))
    subject = f"Bewerbung als {job_title}" if job_title else "Bewerbung"
    if employment_type in ("Werkstudent", "Teilzeit", "Praktikum", "Minijob", "Ausbildung") \
            and employment_type.lower() not in job_title.lower() \
            and not (employment_type == "Werkstudent" and "werkstudent" in job_title.lower()):
        subject += f" ({employment_type})"
    salutation = str(cl.get("salutation") or "").strip()
    if not re.match(r"^(Sehr geehrte|Hallo|Liebe|Guten Tag)", salutation):
        salutation = "Sehr geehrte Damen und Herren,"
    if not salutation.endswith(","):
        salutation += ","
    paragraphs = {p: str(cl.get(p) or "").strip() for p in ("p1", "p2", "p3", "p4")}
    facts = closing_facts(job, job_text, profile)
    if facts:
        paragraphs["p4"] = f"{paragraphs['p4']} {facts}".strip()

    return {
        "version": 2,
        "employment_type": employment_type,
        "summary": str(ai.get("summary") or profile.get("summary") or "").strip(),
        "experience": experience,
        "education": education,
        "skills": skills,
        "gaps": [str(g) for g in ai.get("gaps") or []][:6],
        "cover_letter": {
            "company": str(job.get("company") or "").strip(),
            "contact_person": str(job.get("contact_person") or "").strip(),
            "department": str(job.get("department") or "").strip(),
            "street": str(job.get("street") or "").strip(),
            "city": str(job.get("zip_city") or "").strip(),
            "job_title": job_title,
            "subject": subject,
            "salutation": salutation,
            **paragraphs,
        },
    }


_CHAR_FIX = str.maketrans({"‑": "-", "‐": "-", "‒": "–", "­": "", "​": "",
                           " ": " ", " ": " "})


def normalize_text(obj):
    """Exotische Bindestriche/Leerzeichen einiger Modelle → Standardzeichen (Schrift hat sonst Lücken)."""
    if isinstance(obj, str):
        return obj.translate(_CHAR_FIX)
    if isinstance(obj, list):
        return [normalize_text(x) for x in obj]
    if isinstance(obj, dict):
        return {k: normalize_text(v) for k, v in obj.items()}
    return obj


def validate_ai(ai: dict) -> list[str]:
    problems = []
    cl = ai.get("cover_letter")
    if not isinstance(cl, dict) or not all(str(cl.get(p, "")).strip() for p in ("p1", "p2", "p3", "p4")):
        problems.append("cover_letter mit p1–p4 fehlt oder ist leer")
    if not isinstance(ai.get("experience"), list):
        problems.append("experience fehlt")
    if not str(ai.get("summary", "")).strip():
        problems.append("summary fehlt")
    return problems


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------
@dataclass
class GenerationResult:
    structured: dict
    findings: list[dict]
    input_tokens: int = 0
    output_tokens: int = 0
    repaired: bool = False
    log: list[str] = field(default_factory=list)


def build_prompts(profile: dict, job_text: str, employment_type: str, extra_info: str = "", focus: str = "",
                  bullets_per_job: int = 2) -> tuple[str, str]:
    """(System-Prompt, Nutzer-Prompt) – identisch für API und Abo-Modus."""
    if employment_type not in EMPLOYMENT_TYPES:
        employment_type = "Vollzeit"
    has_portfolio = any(l["label"].lower() in ("portfolio", "website") for l in profile["personal"]["links"])
    system = prompts.build_system_prompt(bullets_per_job, MAX_BULLET_CHARS, has_portfolio)
    user = prompts.build_user_prompt(profile, clean_job_text(job_text), employment_type, extra_info, focus)
    return system, user


def finish(ai: dict, profile: dict, job_text: str, employment_type: str, extra_info: str = "",
           bullets_per_job: int = 2) -> GenerationResult:
    """KI-Antwort (egal ob API oder Abo-Modus) → fertige Struktur + Qualitäts-Check."""
    if employment_type not in EMPLOYMENT_TYPES:
        employment_type = "Vollzeit"
    job_text = clean_job_text(job_text)
    structured = assemble(ai, profile, employment_type, extra_info, bullets_per_job, job_text=job_text)
    findings = quality.check_application(structured, profile, job_text, extra_info, MAX_BULLET_CHARS)
    return GenerationResult(structured, findings)


def apply_repair(structured: dict, data: dict) -> None:
    """Übernimmt die korrigierten Absätze einer Reparatur-Antwort ins Anschreiben."""
    for k, v in normalize_text(data or {}).items():
        if k in REPAIR_KEYS and str(v).strip():
            structured["cover_letter"][k] = str(v).strip()


REPAIR_KEYS = ("salutation", "p1", "p2", "p3", "p4")


def validate_repair(data: dict) -> list[str]:
    return [] if any(str(data.get(k, "")).strip() for k in REPAIR_KEYS) else ["keine Absätze (p1–p4) enthalten"]


def repair_prompts(structured: dict, problems: list[str], profile: dict) -> tuple[str, str]:
    cl = {k: structured["cover_letter"].get(k, "") for k in REPAIR_KEYS}
    return prompts.REPAIR_SYSTEM, prompts.build_repair_prompt(cl, problems, profile)


def generate_application(profile: dict, job_text: str, employment_type: str, model_cfg: dict, api_key: str,
                         extra_info: str = "", focus: str = "", bullets_per_job: int = 2,
                         auto_repair: bool = True) -> GenerationResult:
    system, user = build_prompts(profile, job_text, employment_type, extra_info, focus, bullets_per_job)
    res = llm.complete_json(model_cfg, api_key, system, user, max_tokens=4096, temperature=0.4,
                            validate=validate_ai)
    result = finish(res.data, profile, job_text, employment_type, extra_info, bullets_per_job)
    result.input_tokens, result.output_tokens = res.input_tokens, res.output_tokens
    structured, findings = result.structured, result.findings
    job_text = clean_job_text(job_text)

    problems = quality.blocking_problems(findings)
    if auto_repair and problems:
        try:
            fixed = repair_cover_letter(structured, problems, profile, model_cfg, api_key)
            result.input_tokens += fixed.input_tokens
            result.output_tokens += fixed.output_tokens
            apply_repair(structured, fixed.data)
            result.findings = quality.check_application(structured, profile, job_text, extra_info, MAX_BULLET_CHARS)
            result.repaired = True
        except llm.LLMError as e:
            result.log.append(f"Automatische Korrektur fehlgeschlagen: {e}")
    return result


def repair_cover_letter(structured: dict, problems: list[str], profile: dict, model_cfg: dict, api_key: str):
    system, user = repair_prompts(structured, problems, profile)
    return llm.complete_json(model_cfg, api_key, system, user, max_tokens=2048, temperature=0.2,
                             validate=validate_repair)


def fact_check(structured: dict, profile: dict, model_cfg: dict, api_key: str,
               extra_info: str = "") -> tuple[list[dict], int]:
    """KI-Faktencheck: findet Aussagen im Anschreiben/Summary, die das Profil nicht belegt.
    Gibt ([{"claim", "reason"}], Tokens) zurück."""
    cl = structured.get("cover_letter", {})
    text = "\n".join([structured.get("summary", "")] + [cl.get(p, "") for p in ("p1", "p2", "p3", "p4")])
    from .profile import compact_profile_text
    user = (f"PROFIL:\n{compact_profile_text(profile)}\n"
            + (f"\nZUSATZANGABEN:\n{extra_info}\n" if extra_info.strip() else "")
            + f"\nTEXT:\n{text}")
    res = llm.complete_json(model_cfg, api_key, prompts.FACTCHECK_SYSTEM, user, max_tokens=2048, temperature=0.0)
    issues = [i for i in res.data.get("unsupported", []) if isinstance(i, dict) and i.get("claim")]
    return issues, res.total_tokens


def refine_text(text: str, instruction: str, profile: dict, model_cfg: dict, api_key: str) -> tuple[str, int]:
    """Überarbeitet einen einzelnen Absatz. Gibt (neuer Text, Tokens) zurück."""
    from .profile import compact_profile_text
    user = (f"ANWEISUNG: {instruction}\n\nTEXT:\n{text}\n\n"
            f"PROFIL (einzige Faktenquelle):\n{compact_profile_text(profile)}")
    res = llm.complete(model_cfg, api_key, prompts.REFINE_SYSTEM, user, max_tokens=1024, temperature=0.4)
    return res.text.strip().strip('"„“'), res.total_tokens
