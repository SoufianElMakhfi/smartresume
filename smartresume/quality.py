"""Regelbasierter Qualitäts-Check (kostet keine Tokens).

Prüft, ob der Text übertreibt, unterverkauft oder gegen harte Regeln verstößt.
Ergebnis: Liste von {"level": "error"|"warn", "msg": str, "field": str}.
"""
from __future__ import annotations

import re

from .profile import total_experience_years

INFLATION = [
    "experte", "expertin", "langjährig", "umfassende", "umfassender", "umfangreiche", "tiefgreifend",
    "fundiert", "spezialist", "führend", "perfekt", "herausragend", "exzellent", "einzigartig",
    "weltklasse", "jahrelang", "profi ", "meisterhaft", "absolut sicher", "bestens",
]
WEAK = [
    "leider", "obwohl ich keine", "obwohl ich kein", "trotz fehlender", "ich hoffe", "ich würde mich sehr freuen",
    "ich traue mir zu", "ich glaube, dass ich", "vielleicht", "eventuell", "nicht viel erfahrung",
    "wenig erfahrung", "nur wenig", "bin mir nicht sicher", "auch wenn ich noch", " zwar ",
]
FLOSKELN = [
    "hiermit bewerbe ich mich", "mit großem interesse", "hochmotiviert", "leidenschaft", "ich brenne für",
    "dynamisches team", "spannende herausforderung", "teamplayer", "zielorientiert", "proaktiv",
    "innovative lösungen", "hands-on", "ich bin teamfähig", "kommunikationsstark",
]
SALARY_RE = re.compile(r"gehalt|brutto|netto|vergütung|\bk€|€\s*(?:pro|im)\s*(?:jahr|monat)", re.IGNORECASE)
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*jahre?n?\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"(?<![\w./])(\d+(?:[.,]\d+)?)(?:\s?(%|\+))?")
PLACEHOLDER_RE = re.compile(r"\[[^\]]{2,}\]|\{\{|XXX|<[^>]+>")


FORBIDDEN_INFLATION = {"experte", "expertin", "langjährig", "umfassende", "umfassender", "tiefgreifend", "fundiert",
                       "spezialist", "führend"}


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", text or "") if len(x.strip().split()) >= 4]


def _repeated_sentence(text: str) -> str | None:
    """Zwei Sätze, die fast dasselbe sagen (≥ 60 % gleiche Wörter) – wirkt unaufmerksam."""
    sents = _sentences(text)
    for i, a in enumerate(sents):
        wa = set(re.findall(r"\w{3,}", a.lower()))
        for b in sents[i + 1:]:
            wb = set(re.findall(r"\w{3,}", b.lower()))
            if wa and wb and len(wa & wb) / min(len(wa), len(wb)) >= 0.6:
                return b
    return None


def _norm_num(s: str) -> str:
    return s.replace(".", "").replace(",", "")


def _cover_text(cl: dict) -> str:
    return "\n".join(cl.get(k, "") for k in ("p1", "p2", "p3", "p4"))


def check_application(structured: dict, profile: dict, job_text: str = "", extra_info: str = "",
                      max_bullet_chars: int = 80) -> list[dict]:
    findings: list[dict] = []

    def add(level, msg, field="cover_letter"):
        findings.append({"level": level, "msg": msg, "field": field})

    cl = structured.get("cover_letter", {})
    letter = _cover_text(cl)
    summary = structured.get("summary", "")
    full = f"{summary}\n{letter}"
    low = full.lower()

    # 1) Übertreibung
    for w in INFLATION:
        if w in low:
            if w.strip() in FORBIDDEN_INFLATION:   # im Prompt ausdrücklich verboten → automatische Korrektur
                add("error", f"Übertreibung: „{w.strip()}“ – klingt nach mehr Erfahrung, als das Profil belegt.")
            else:
                add("warn", f"Mögliche Übertreibung: „{w.strip()}“ – nur verwenden, wenn das Profil es klar belegt.")
    years_have = total_experience_years(profile)
    for m in YEARS_RE.finditer(full):
        claimed = int(m.group(1))
        if claimed > max(years_have + 0.5, 1):
            add("error", f"Behauptet {claimed} Jahre Erfahrung, Profil belegt ca. {years_have:g} Jahre insgesamt.")

    # 2) Unterverkaufen
    for w in WEAK:
        if w in low:
            add("warn", f"Schwächt den Bewerber: „{w}“ – selbstbewusster formulieren.")

    rep = _repeated_sentence(letter)
    if rep:
        add("error", f"Wiederholung: „{rep[:70]}…“ sagt fast dasselbe wie ein Satz davor.")

    # 3) Floskeln (global + eigene verbotene Phrasen)
    own = [p.lower() for p in profile.get("writing_style", {}).get("forbidden_phrases", [])]
    for w in FLOSKELN + own:
        if w and w in low:
            add("warn", f"Floskel/verbotene Phrase: „{w}“.")

    # 4) Harte Regeln
    if PLACEHOLDER_RE.search(full):
        add("error", "Platzhalter oder Klammern im Text gefunden.")
    if re.search(r"https?://|www\.", full):
        add("warn", "URL im Fließtext – Links stehen bereits auf dem Deckblatt.")
    job_low = (job_text or "").lower()
    asks_salary = any(k in job_low for k in ("gehaltsvorstellung", "gehaltswunsch", "gehaltsvorstellungen"))
    if SALARY_RE.search(letter) and not asks_salary:
        add("error", "Gehalt erwähnt, obwohl die Anzeige nicht danach fragt.")

    # 5) Zahlen-Faktencheck: jede Zahl muss als eigenständige Zahl im Profil, den
    #    Zusatzangaben oder der Anzeige vorkommen ("20" in "2020" zählt NICHT).
    import json
    src_text = json.dumps(profile, ensure_ascii=False) + " " + (extra_info or "") + " " + (job_text or "")
    known = {_norm_num(x) for x in re.findall(r"\d+(?:[.,]\d+)*", src_text)}
    known |= {str(int(round(total_experience_years(profile))))}
    seen = set()
    for m in NUMBER_RE.finditer(full):
        num = m.group(1)
        if len(_norm_num(num)) < 2 or num in seen:  # Einzelziffern ("2 Projekte") sind meist harmlos
            continue
        seen.add(num)
        if _norm_num(num) not in known:
            add("error", f"Zahl „{num}“ steht weder im Profil noch in der Anzeige – vermutlich erfunden.")

    # 6) Widerspruch: fehlende Kenntnis benannt, aber im selben Satz als erlernt dargestellt
    for sent in re.split(r"(?<=[.!?])\s+", letter):
        s = sent.lower()
        if re.search(r"noch nicht|keine erfahrung|bisher nicht", s) and \
                re.search(r"erschlossen|erlernt|gelernt|eingearbeitet|angeeignet|beherrsche", s):
            add("error", f"Widerspruch – fehlende Kenntnis wird als bereits erlernt dargestellt: „{sent[:90]}…“")
    if low.count("gehaltsvorstellung") > 1:
        add("warn", "Gehaltsvorstellung wird doppelt genannt.")

    # 6b) Du/Sie-Mix
    salutation = cl.get("salutation", "")
    du_words = re.findall(r"\b(du|dich|dir|dein\w*|euch|euer\w*|eure\w*|ihr)\b", letter)  # bewusst case-sensitiv
    sie_words = re.findall(r"\b(Sie|Ihnen|Ihr\w*)\b", letter)
    if du_words and (sie_words or salutation.startswith("Sehr geehrte")):
        add("error", f"Du/Sie gemischt („{du_words[0]}“) – Anrede einheitlich halten.")

    # 7) Länge
    words = len(letter.split())
    if words > 240:
        add("warn", f"Anschreiben hat {words} Wörter – passt evtl. nicht auf eine Seite (Ziel ≤ 210).")
    elif words < 90 and letter.strip():
        add("warn", f"Anschreiben hat nur {words} Wörter – wirkt eventuell zu knapp.")
    for job in structured.get("experience", []):
        for b in job.get("bullets", []):
            if len(b) > max_bullet_chars:
                add("warn", f"Bullet zu lang ({len(b)} Zeichen): „{b[:40]}…“", "experience")
    return findings


def blocking_problems(findings: list[dict]) -> list[str]:
    return [f["msg"] for f in findings if f["level"] == "error" and f["field"] == "cover_letter"]
