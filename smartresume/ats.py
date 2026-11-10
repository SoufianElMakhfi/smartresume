"""ATS-Check: Wie gut decken die Unterlagen die Schlüsselbegriffe der Stellenanzeige ab?

Bewerbermanagement-Systeme (Personio, SAP SuccessFactors, Workday, softgarden, d.vinci …) lesen den Text aus dem
PDF und vergleichen ihn mit den Begriffen der Anzeige – oft wörtlich. Dieses Modul prüft das deterministisch:

- ok:       Begriff steht (so wie in der Anzeige) in den Unterlagen
- wording:  Fähigkeit steht drin, aber anders geschrieben als in der Anzeige („Excel“ statt „MS Excel“)
- addable:  laut Profil vorhanden, aber nicht in den Unterlagen erwähnt
- missing:  nicht im Profil – wird NIE eingefügt (ehrliche Lücke)

Die Zuordnung Begriff → Profileintrag liefert die KI; sie wird hier gegen den echten Profiltext geprüft,
damit nichts behauptet wird, was nicht im Profil steht.
"""
from __future__ import annotations

import re

from .profile import compact_profile_text

OTHER = "Weitere Kenntnisse"


def contains(text: str, term: str) -> bool:
    term = (term or "").strip()
    if not term:
        return False
    # Bindestrich zählt als Wortgrenze („Shopify-System“, „SAP-Kenntnisse“) – so zerlegen auch ATS die Wörter
    return bool(re.search(r"(?<![\w.+#])" + re.escape(term) + r"(?![\w+#])", text or "", re.IGNORECASE))


def clean_keywords(raw, profile: dict, extra_info: str = "") -> list[dict]:
    """KI-Ausgabe normalisieren. Ein Profileintrag zählt nur, wenn er wirklich im Profil/den Zusatzangaben steht."""
    source = compact_profile_text(profile) + "\n" + (extra_info or "")
    out, seen = [], set()
    for k in raw if isinstance(raw, list) else []:
        if isinstance(k, str):
            k = {"term": k, "profile": ""}
        if not isinstance(k, dict):
            continue
        term = str(k.get("term") or "").strip()[:60]
        prof = str(k.get("profile") or "").strip()[:60]
        if not term or term.lower() in seen:
            continue
        seen.add(term.lower())
        if prof and not contains(source, prof):
            prof = ""
        if not prof and contains(source, term):
            prof = term
        out.append({"term": term, "profile": prof})
    return out[:15]


def application_text(structured: dict) -> str:
    """Der Text, den ein ATS aus den Unterlagen liest (Anschreiben + Lebenslauf)."""
    parts = [structured.get("summary", "")]
    for j in structured.get("experience", []):
        parts += [j.get("role", ""), j.get("company", "")] + list(j.get("bullets", []))
    for e in structured.get("education", []):
        parts += [e.get("degree", ""), e.get("institution", ""), e.get("detail", "")]
    for s in structured.get("skills", []):
        items = s.get("items", "")
        parts += [s.get("category", ""), ", ".join(items) if isinstance(items, list) else str(items)]
    cl = structured.get("cover_letter", {})
    parts += [cl.get("subject", "")] + [cl.get(p, "") for p in ("p1", "p2", "p3", "p4")]
    return "\n".join(str(p) for p in parts if p)


def report(structured: dict) -> list[dict]:
    text = application_text(structured)
    out = []
    terms = [k["term"].lower() for k in structured.get("keywords") or []]
    for k in structured.get("keywords") or []:
        term, prof = k["term"], k.get("profile", "")
        if contains(text, term) and not prof:
            status = "bridge"     # nur als Lücke angesprochen („… habe ich noch nicht gearbeitet“)
        elif contains(text, term):
            status = "ok"
        elif prof and contains(text, prof):
            status = "wording"
        elif prof:
            status = "addable"
        else:
            status = "missing"
        out.append({"term": term, "profile": prof, "status": status})
    # Lücken (Anforderungen, die das Profil nicht belegt) zählen mit – sonst wäre der Wert geschönt
    if out:
        for gap in structured.get("gaps") or []:
            if not any(t in gap.lower() for t in terms):
                out.append({"term": gap, "profile": "", "status": "missing"})
    return out


def score(rep: list[dict]) -> int:
    """Anteil der Schlüsselbegriffe, die ein ATS findet (andere Schreibweise zählt halb)."""
    if not rep:
        return 0
    pts = sum(1 if r["status"] in ("ok", "bridge") else 0.5 if r["status"] == "wording" else 0 for r in rep)
    return round(100 * pts / len(rep))


def best_possible(rep: list[dict]) -> int:
    """Erreichbar, ohne zu lügen: alles außer echten Lücken."""
    if not rep:
        return 0
    return max(score(rep), round(100 * sum(r["status"] not in ("missing", "bridge") for r in rep) / len(rep)))


def _items(s: dict) -> list[str]:
    items = s.get("items", "")
    return list(items) if isinstance(items, list) else [x.strip() for x in str(items).split(",") if x.strip()]


def add_to_skills(structured: dict, term: str) -> None:
    """Begriff (laut Profil vorhanden) in die Kenntnisse des Lebenslaufs aufnehmen."""
    if contains(application_text({"skills": structured.get("skills", [])}), term):
        return
    skills = structured.setdefault("skills", [])
    target = next((s for s in skills if s.get("category", "").lower() == OTHER.lower()), None)
    if target is None:
        idx = next((i for i, s in enumerate(skills) if s.get("category") == "Sprachen"), len(skills))
        skills.insert(idx, {"category": OTHER, "items": term})
    else:
        target["items"] = ", ".join(_items(target) + [term])


def use_ad_wording(structured: dict, term: str, profile_word: str) -> None:
    """Schreibweise der Anzeige in den Kenntnissen verwenden („Excel“ → „MS Excel“) – gleiche Fähigkeit."""
    pat = re.compile(r"(?<![\w.+#-])" + re.escape(profile_word) + r"(?![\w+#-])", re.IGNORECASE)
    changed = False
    for s in structured.get("skills", []):
        items = _items(s)
        new = [term if pat.fullmatch(i.strip()) else i for i in items]
        if new != items:
            s["items"] = ", ".join(new)
            changed = True
    if not changed:
        add_to_skills(structured, term)
