"""Lebenslauf-Import: Datei → Text → (einmalig per KI) strukturiertes Profil."""
from __future__ import annotations

import io
import json
import re

from . import llm
from .profile import normalize_profile

MAX_CV_CHARS = 15000


class CVImportError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:  # noqa: BLE001
            raise CVImportError(f"PDF konnte nicht gelesen werden: {e}")
    elif name.endswith(".docx"):
        import docx
        try:
            d = docx.Document(io.BytesIO(data))
        except Exception as e:  # noqa: BLE001
            raise CVImportError(f"DOCX konnte nicht gelesen werden: {e}")
        lines = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                cells = list(dict.fromkeys(c.text.strip() for c in row.cells if c.text.strip()))
                lines.append(" | ".join(cells))
        text = "\n".join(lines)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise CVImportError("Bitte PDF, DOCX oder TXT hochladen.")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) < 150:
        raise CVImportError("Im Dokument wurde kaum Text gefunden (gescanntes Bild-PDF?). "
                            "Bitte eine Text-PDF/DOCX hochladen oder die Daten manuell eingeben.")
    return text[:MAX_CV_CHARS]


def extract_photo_candidates(filename: str, data: bytes, max_n: int = 3) -> list[bytes]:
    """Sucht auf den ersten beiden PDF-Seiten nach Porträt-ähnlichen Bildern."""
    if not ((filename or "").lower().endswith(".pdf") or data[:4] == b"%PDF"):
        return []
    from PIL import Image
    from pypdf import PdfReader
    found = []
    try:
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages[:2]:
            for img in page.images:
                try:
                    im = Image.open(io.BytesIO(img.data))
                    w, h = im.size
                    if w >= 120 and h >= 120 and 0.6 <= w / h <= 1.25:
                        out = io.BytesIO()
                        im.convert("RGB").save(out, "JPEG", quality=90)
                        found.append((w * h, out.getvalue()))
                except Exception:  # noqa: BLE001 – defekte Einzelbilder ignorieren
                    continue
    except Exception:  # noqa: BLE001
        return []
    found.sort(key=lambda x: -x[0])
    return [b for _, b in found[:max_n]]


CV_SYSTEM = """Du extrahierst Daten aus einem Lebenslauf in ein festes JSON-Schema.
REGELN:
- Nur übernehmen, was im Dokument steht. NICHTS erfinden, nichts ergänzen, nicht aufwerten.
- Texte möglichst wörtlich übernehmen; Stichpunkte einer Station als kurze Einträge in "bullets" (je max. ~90 Zeichen, eine Aussage pro Eintrag, Nominalstil).
- Datumsformat "MM/JJJJ" (oder "JJJJ", wenn nur das Jahr bekannt ist), laufende Stationen: end = "Heute".
- Reihenfolge: neueste Station zuerst.
- skills: sinnvolle Kategorien (z.B. "Programmierung", "Tools", "Office", "Methoden"), Einträge kurz.
- Sprachen NICHT in skills, sondern in "languages".
- strengths: nur, wenn das Dokument eine Stärke mit konkretem Beleg nennt.
- Fehlende Angaben: leerer String bzw. leere Liste.
Antworte nur mit JSON in exakt diesem Schema (Listen enthalten beliebig viele Einträge dieser Form):
""" + json.dumps({
    "personal": {"first_name": "Vorname(n)", "last_name": "Nachname inkl. Zusätzen wie von/van/El",
                 "headline": "Berufsbezeichnung laut CV", "email": "", "phone": "",
                 "street": "", "zip_city": "PLZ Ort", "links": [{"label": "LinkedIn", "url": ""}]},
    "summary": "Profiltext laut CV oder leer",
    "experience": [{"company": "", "role": "Jobtitel/Position", "start": "MM/JJJJ", "end": "MM/JJJJ oder Heute",
                    "location": "", "bullets": ["…"]}],
    "education": [{"institution": "", "degree": "Abschluss/Ausbildung/Studiengang", "start": "", "end": "",
                   "location": "", "details": "Schwerpunkt/Note, falls genannt"}],
    "skills": [{"category": "", "items": ["…"]}],
    "languages": [{"language": "", "level": ""}],
    "projects": [{"name": "", "description": "", "stack": ["…"], "highlights": ["…"]}],
    "certificates": ["…"],
    "strengths": [{"skill": "", "evidence": ""}],
    "preferences": {"availability": "", "notice_period": "", "salary_expectation": "",
                    "hours_per_week": "", "student_status": "z.B. eingeschrieben, Studiengang, Semester"},
}, ensure_ascii=False)


def validate_cv(d: dict) -> list[str]:
    return [] if isinstance(d.get("personal"), dict) else ["Abschnitt 'personal' fehlt"]


def cv_prompts(cv_text: str) -> tuple[str, str]:
    """(System-Prompt, Nutzer-Prompt) – identisch für API und Abo-Modus."""
    return CV_SYSTEM, f"LEBENSLAUF:\n{cv_text}"


def parse_cv_with_ai(cv_text: str, model_cfg: dict, api_key: str) -> tuple[dict, int]:
    """Gibt (normalisiertes Profil, verbrauchte Tokens) zurück."""
    system, user = cv_prompts(cv_text)
    res = llm.complete_json(model_cfg, api_key, system, user, max_tokens=6000, temperature=0.1,
                            validate=validate_cv)
    return normalize_profile(res.data), res.total_tokens


def _key(*parts) -> str:
    return "|".join(re.sub(r"\W+", "", str(p or "").lower()) for p in parts)


def merge_profiles(base: dict, incoming: dict) -> dict:
    """Ergänzt `base` um Daten aus `incoming`, ohne Vorhandenes zu überschreiben."""
    base, incoming = normalize_profile(base), normalize_profile(incoming)
    out = json.loads(json.dumps(base))
    name_keys = ("first_name", "last_name", "name")
    if not (out["personal"]["first_name"] or out["personal"]["last_name"]):   # Name nur als Ganzes übernehmen
        out["personal"].update({k: incoming["personal"][k] for k in name_keys})
    for k, v in incoming["personal"].items():
        if k in name_keys:
            continue
        if k == "links":
            have = {l["url"].rstrip("/").lower() for l in out["personal"]["links"]}
            out["personal"]["links"] += [l for l in v if l["url"].rstrip("/").lower() not in have]
        elif not out["personal"][k]:
            out["personal"][k] = v
    if not out["summary"]:
        out["summary"] = incoming["summary"]

    def merge_list(section, keyfn):
        have = {keyfn(x) for x in out[section]}
        out[section] += [x for x in incoming[section] if keyfn(x) not in have]

    merge_list("experience", lambda x: _key(x["company"], x["role"]))
    merge_list("education", lambda x: _key(x["institution"], x["degree"]))
    merge_list("languages", lambda x: _key(x["language"]))
    merge_list("projects", lambda x: _key(x["name"]))
    merge_list("strengths", lambda x: _key(x["skill"]))
    have_certs = {_key(c) for c in out["certificates"]}
    out["certificates"] += [c for c in incoming["certificates"] if _key(c) not in have_certs]
    cats = {_key(s["category"]): s for s in out["skills"]}
    for s in incoming["skills"]:
        if _key(s["category"]) in cats:
            tgt = cats[_key(s["category"])]
            tgt["items"] += [i for i in s["items"] if _key(i) not in {_key(x) for x in tgt["items"]}]
        else:
            out["skills"].append(s)
    for k, v in incoming["preferences"].items():
        if not out["preferences"][k]:
            out["preferences"][k] = v
    return normalize_profile(out)
