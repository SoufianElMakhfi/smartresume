"""Lebenslauf ohne KI auslesen: feste Regeln statt Sprachmodell – sofort, kostenlos, offline.

Erkennt Kontaktdaten, Abschnitte (Berufserfahrung, Ausbildung, Kenntnisse …), Zeiträume und Aufzählungen
in den üblichen Layouts („Zeitraum  Titel, Firma“ oder „Titel / Zeitraum / Firma“ untereinander).
Ergebnis ist eine Grundlage zum Durchsehen – bei ungewöhnlichen Layouts (z. B. mehrspaltig, Tabellen
mit vermischtem Text) liest die KI genauer.
"""
from __future__ import annotations

import re
from pathlib import Path

from .profile import normalize_profile, split_name

# ── Abschnitte ──────────────────────────────────────────────────────────────
SECTIONS = {
    "summary": {"kurzprofil", "profil", "über mich", "ueber mich", "zusammenfassung", "persönliches profil",
                "berufliches profil", "profil und ziele", "karriereziel", "motivation", "summary", "profile",
                "about me", "professional summary", "objective"},
    "experience": {"berufserfahrung", "berufserfahrungen", "berufliche erfahrung", "berufliche erfahrungen",
                   "berufspraxis", "praxiserfahrung", "praktische erfahrung", "praktische erfahrungen",
                   "berufliche stationen", "beruflicher werdegang", "werdegang", "arbeitserfahrung", "erfahrung",
                   "praktika", "praktikum", "nebentätigkeiten", "nebenjobs", "tätigkeiten", "berufstätigkeit",
                   "berufserfahrung und praktika", "praktika und berufserfahrung", "beruflicher hintergrund",
                   "ehrenamt", "ehrenamtliches engagement", "engagement", "work experience", "experience",
                   "professional experience", "employment", "employment history", "work history", "volunteering"},
    "education": {"ausbildung", "bildung", "bildungsweg", "bildungsgang", "schulbildung", "schulische ausbildung",
                  "studium", "hochschulbildung", "akademischer werdegang", "schulischer werdegang",
                  "ausbildung und studium", "studium und ausbildung", "schul und berufsausbildung",
                  "schulische und berufliche ausbildung", "education", "academic background"},
    "skills": {"kenntnisse", "fähigkeiten", "skills", "kompetenzen", "fachkompetenzen", "it kenntnisse",
               "edv kenntnisse", "fachkenntnisse", "technische kenntnisse", "besondere kenntnisse",
               "kenntnisse und fähigkeiten", "fähigkeiten und kenntnisse", "sonstige kenntnisse", "qualifikationen",
               "computerkenntnisse", "kenntnisse und kompetenzen", "technical skills", "hard skills",
               "soft skills", "it skills", "skills und kompetenzen"},
    "languages": {"sprachen", "sprachkenntnisse", "fremdsprachen", "languages"},
    "projects": {"projekte", "projekterfahrung", "ausgewählte projekte", "studienprojekte", "eigene projekte",
                 "projects"},
    "certificates": {"zertifikate", "zertifizierungen", "weiterbildung", "weiterbildungen", "fortbildung",
                     "fortbildungen", "fort und weiterbildungen", "kurse", "lehrgänge", "auszeichnungen",
                     "certificates", "certifications", "awards"},
    "personal": {"persönliche daten", "persönliches", "kontakt", "kontaktdaten", "personal details",
                 "personal information", "contact"},
    "other": {"interessen", "hobbys", "hobbies", "freizeit", "sonstiges", "referenzen", "interests"},
}

# ── Muster ──────────────────────────────────────────────────────────────────
# Aufzählungszeichen – \x7f und der Private-Use-Bereich sind Symbolschriften, die pypdf nicht übersetzt
BULLET_RE = re.compile(r"^\s*(?:[\x7f•‣⁃∙▪▫●○◦■□►"
                       r"▸➢✓✔·*>]|[-–—](?=\s)|[-])\s*")
_MONTHS = {"jan": 1, "feb": 2, "mär": 3, "mae": 3, "mar": 3, "apr": 4, "mai": 5, "may": 5, "jun": 6, "jul": 7,
           "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12}
_MONTH_NAME = (r"(?:jan(?:uar|uary)?|feb(?:ruar|ruary)?|märz|maerz|mär|mar(?:ch)?|apr(?:il)?|mai|may|"
               r"jun[ie]?|jul[iy]?|aug(?:ust)?|sep(?:t|tember)?|okt(?:ober)?|oct(?:ober)?|nov(?:ember)?|"
               r"dez(?:ember)?|dec(?:ember)?)")
_YEAR = r"(?:19|20)\d{2}"
_ONE_DATE = (rf"(?:(?:\d{{1,2}}\.\s?)?\d{{1,2}}\s?[./]\s?{_YEAR}(?!\d)|\b{_MONTH_NAME}\b\.?\s+{_YEAR}(?!\d)"
             rf"|(?<![\d./]){_YEAR}(?![\d.,]\d))")
_NOW = r"(?:bis\s+)?(?:heute|dato|aktuell|jetzt|derzeit|laufend|present|today|now|current)\b"
RANGE_RE = re.compile(rf"(?P<since>\b(?:seit|ab|since|from)\s+)?(?P<a>{_ONE_DATE})"
                      rf"(?:\s*(?:[-–—]|\bbis\b|\bto\b|\buntil\b)\s*(?P<b>{_ONE_DATE}|{_NOW}))?", re.I)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+|00)\d{1,3}[\s/().-]*\d[\d\s/().-]{5,}\d|(?<![\d/.])0\d{2,5}[\s/().-]*\d[\d\s/().-]{4,}\d")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s|·•,]+|\b(?:linkedin\.com|github\.com|xing\.com|gitlab\.com)/[^\s|·•,]+",
                    re.I)
ZIP_RE = re.compile(r"(?<![\d+])(?:(?:D|A|CH)-)?\d{4,5}\s+(?=[A-ZÄÖÜ])")
STREET_WORDS = (r"(?:str\.|straße|strasse|weg|allee|platz|gasse|ring|damm|ufer|pfad|chaussee|markt|hof|berg|feld|"
                r"steig|kamp|stieg|wall|graben|garten|park|tor|bogen|winkel|siedlung|höhe|chaussee|street|road|"
                r"avenue)")
STREET_RE = re.compile(rf"[A-ZÄÖÜ][\wäöüß.\- ]*?{STREET_WORDS}\.?\s*\d{{1,4}}\s?[a-zA-Z]?\b", re.I)
SEP_RE = re.compile(r"\s+[|·•]\s+|\s{2,}")   # starke Trenner zwischen Feldern einer Zeile
ORG_RE = re.compile(r"\b(?:GmbH|AG|KG|SE|OHG|UG|KGaA|e\.\s?V\.|mbH|Inc|Ltd|LLC|Corp|Co\.|Gruppe|Group|Holding|"
                    r"Universität|University|Hochschule|Fachhochschule|TH|FH|TU|Uni|Schule|Gymnasium|Realschule|"
                    r"Gesamtschule|Hauptschule|Berufskolleg|Berufsschule|Kolleg|Akademie|Academy|College|Institut|"
                    r"Institute|IHK|HWK|Verlag|Bank|Sparkasse|Klinik|Klinikum|Krankenhaus|Agentur|Verein|"
                    r"Stiftung|Werke|Campus)\b|(?:schule|gymnasium|universität|akademie|kolleg|zentrum|werk)\b",
                    re.I)
DEGREE_RE = re.compile(r"\b(?:Bachelor|Master|B\.\s?(?:Sc|A|Eng)|M\.\s?(?:Sc|A|Eng)|Diplom|Abitur|Hochschulreife|"
                       r"Fachhochschulreife|Fachabitur|Realschulabschluss|Mittlere Reife|Hauptschulabschluss|"
                       r"Fachoberschulreife|Ausbildung|Promotion|Staatsexamen|Studium|Abschluss|MBA|Ph\.?\s?D)",
                       re.I)
LANGUAGES = ("Deutsch|Englisch|Französisch|Spanisch|Italienisch|Portugiesisch|Niederländisch|Türkisch|Arabisch|"
             "Russisch|Polnisch|Ukrainisch|Rumänisch|Bulgarisch|Griechisch|Kroatisch|Serbisch|Bosnisch|"
             "Albanisch|Kurdisch|Persisch|Farsi|Dari|Paschtu|Hindi|Urdu|Bengali|Tamil|Chinesisch|Mandarin|"
             "Kantonesisch|Japanisch|Koreanisch|Vietnamesisch|Thailändisch|Indonesisch|Tagalog|Schwedisch|"
             "Dänisch|Norwegisch|Finnisch|Ungarisch|Tschechisch|Slowakisch|Slowenisch|Litauisch|Lettisch|"
             "Estnisch|Hebräisch|Amharisch|Tigrinya|Somali|Swahili|Berberisch|Latein|Altgriechisch|"
             "Gebärdensprache|DGS|German|English|French|Spanish|Italian|Portuguese|Dutch|Turkish|Arabic|"
             "Russian|Polish|Chinese|Japanese|Korean")
LANG_RE = re.compile(rf"^({LANGUAGES})\b\s*(?:\((.*?)\)|[:–—-]\s*(.+)|\s+(.+))?$", re.I)
LEVEL_ONLY_RE = re.compile(r"^(?:sehr\s+)?(?:gute|grundlegende|fortgeschrittene|erweiterte|solide|fundierte|"
                           r"vertiefte|umfassende)\s+kenntnisse$|^(?:grundkenntnisse|anfänger|fortgeschritten|"
                           r"experte|expert|basic|advanced|fluent|verhandlungssicher)$", re.I)
_HANGING = re.compile(r"(?:[,;:/(\-–—&+]|\b(?:und|oder|sowie|mit|von|der|die|das|des|für|in|im|zur|zum|bei|"
                      r"auf|and|or|with|of|for|the|to))$", re.I)
_SKIP_TITLE = re.compile(r"^(?:lebenslauf|curriculum vitae|cv|resume|résumé|bewerbung|tabellarischer lebenslauf)"
                         r"\b\s*[-–—:|]?\s*", re.I)


# ── Hilfen ──────────────────────────────────────────────────────────────────
def _section_of(line: str) -> str | None:
    t = line.strip().strip(":").strip()
    if not t or len(t) > 45 or re.search(r"\d", t):
        return None
    if re.fullmatch(r"(?:\w\s)+\w", t):                       # „B E R U F S E R F A H R U N G“
        t = t.replace(" ", "")
    key = t.lower().replace("&", " und ").replace("-", " ").replace("/", " und ")
    key = re.sub(r"\s+", " ", re.sub(r"[^a-zäöüß ]", "", key)).strip()
    for section, names in SECTIONS.items():
        if key in names:
            return section
    return None


def _join(a: str, b: str) -> str:
    """Zeilenumbruch rückgängig machen (inkl. Silbentrennung „Werkstudenten-“ + „tätigkeit“)."""
    if re.search(r"[a-zäöüß]-$", a) and b[:1].islower():
        return a[:-1] + b
    return f"{a} {b}"


def _norm_date(s: str) -> str:
    s = s.strip()
    if re.fullmatch(_NOW, s, re.I):
        return "Heute"
    m = re.search(rf"(\d{{1,2}})\s?[./]\s?({_YEAR})$", s)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    m = re.match(rf"({_MONTH_NAME})\.?\s+({_YEAR})", s, re.I)
    if m:
        return f"{_MONTHS.get(m.group(1).lower()[:3], 1):02d}/{m.group(2)}"
    return s


def find_range(line: str):
    """Zeitraum am Anfang oder Ende der Zeile → (start, end, Rest der Zeile, einzeln?) oder None."""
    t = line.strip()
    for m in RANGE_RE.finditer(t):
        at_start = not t[:m.start()].strip(" |·•,:–—-(")
        at_end = not t[m.end():].strip(" |·•,:–—-).")
        if not (at_start or at_end):
            continue
        a = _norm_date(m.group("a"))
        rest = (t[:m.start()] + "  " + t[m.end():]).strip(" |·•,:–—-()\t")
        if m.group("b"):
            return a, _norm_date(m.group("b")), rest, False
        if m.group("since"):
            return a, "Heute", rest, False
        return a, "", rest, True
    return None


def _bullet(line: str) -> str | None:
    m = BULLET_RE.match(line)
    if not m:
        return None
    rest = line[m.end():].strip()
    return rest or None


def _is_place(s: str) -> bool:
    s = s.strip()
    return (0 < len(s) <= 30 and len(s.split()) <= 3 and s[:1].isupper() and not ORG_RE.search(s)
            and not DEGREE_RE.search(s) and not re.search(r"\d", re.sub(r"^\d{4,5}\s", "", s)))


def _split_org(text: str) -> tuple[str, str]:
    """„Muster GmbH, Köln“ → (Muster GmbH, Köln)."""
    chunks = [c.strip() for c in re.split(r",\s+", text) if c.strip()]
    if len(chunks) > 1 and _is_place(chunks[-1]):
        return ", ".join(chunks[:-1]), chunks[-1]
    return text.strip(), ""


# ── Einträge (Berufserfahrung, Ausbildung, Projekte) ───────────────────────
def _entries(lines: list[str]) -> list[dict]:
    rows = []
    for line in lines:
        b = _bullet(line)
        if b is not None:
            rows.append((True, b))
        elif line.strip():
            rows.append((False, line.strip()))
    first_line = next((t for is_b, t in rows if not is_b), "")
    date_first = bool(find_range(first_line))

    def has_date(i: int) -> bool:
        return 0 <= i < len(rows) and not rows[i][0] and bool(find_range(rows[i][1]))

    entries: list[dict] = []
    cur = None
    for i, (is_b, t) in enumerate(rows):
        if is_b:
            if cur is None:
                cur = {"head": [], "date": None, "bullets": []}
                entries.append(cur)
            cur["bullets"].append(t)
            continue
        rng = find_range(t)
        if cur is not None and not rng and cur["bullets"]:
            hanging = bool(_HANGING.search(cur["bullets"][-1])) or t[:1].islower()
            new = not date_first and (has_date(i + 1) or (not hanging and not rows[i + 1][0] and has_date(i + 2))
                                      if i + 1 < len(rows) else False)
            if not new:
                cur["bullets"][-1] = _join(cur["bullets"][-1], t)
                continue
        start_new = cur is None or (rng and (cur["date"] or cur["bullets"])) or \
            (not rng and not date_first and (cur["date"] or cur["bullets"]) and has_date(i + 1))
        if start_new:
            cur = {"head": [], "date": None, "bullets": []}
            entries.append(cur)
        if rng and not cur["date"]:
            cur["date"] = rng[:2] + (rng[3],)
            if rng[2]:
                cur["head"].append(rng[2])
        else:
            cur["head"].append(t)
    return entries


def _fields(head: list[str]) -> tuple[str, str, str, list[str]]:
    """Kopfzeilen eines Eintrags → (Titel, Organisation, Ort, Rest)."""
    pieces: list[str] = []
    for line in head:
        pieces += [p.strip() for p in SEP_RE.split(line) if p.strip()]
    if not pieces:
        return "", "", "", []
    if len(head) == 1 and len(pieces) == 1:          # „Sachbearbeiter, Muster GmbH, Köln“ / „… bei Muster GmbH“
        m = re.match(r"(.+?)\s+(?:bei|at|@)\s+(.+)", pieces[0])
        if m:
            pieces = [m.group(1), m.group(2)]
        else:
            chunks = [c.strip() for c in re.split(r",\s+", pieces[0]) if c.strip()]
            if len(chunks) >= 2:
                pieces = [chunks[0], ", ".join(chunks[1:])]
    title, org, rest = pieces[0], (pieces[1] if len(pieces) > 1 else ""), pieces[2:]
    if org and ORG_RE.search(title) and not ORG_RE.search(org):
        title, org = org, title
    org, place = _split_org(org) if org else ("", "")
    if not place and rest and _is_place(rest[0]):
        place, rest = rest[0], rest[1:]
    return title, org, place, rest


def _experience(lines: list[str]) -> list[dict]:
    out = []
    for e in _entries(lines):
        role, company, place, rest = _fields(e["head"])
        start, end, single = e["date"] or ("", "", False)
        out.append({"role": role, "company": company, "location": place, "start": start, "end": end,
                    "bullets": rest + e["bullets"]})
    return out


def _education(lines: list[str]) -> list[dict]:
    out = []
    for e in _entries(lines):
        degree, inst, place, rest = _fields(e["head"])
        if inst and DEGREE_RE.search(inst) and not DEGREE_RE.search(degree):
            degree, inst = inst, degree
        start, end, single = e["date"] or ("", "", False)
        if single:                                       # nur ein Datum = Abschluss
            start, end = "", start
        out.append({"degree": degree, "institution": inst, "location": place, "start": start, "end": end,
                    "details": " · ".join(rest + e["bullets"])})
    return out


def _projects(lines: list[str]) -> list[dict]:
    out = []
    for e in _entries(lines):
        if not e["head"] and not e["bullets"]:
            continue
        name = e["head"][0] if e["head"] else e["bullets"].pop(0)
        stack, highlights = [], []
        for b in e["bullets"]:
            m = re.match(r"(?:technologien|stack|tools|tech|eingesetzt)\s*:\s*(.+)", b, re.I)
            if m:
                stack += _items(m.group(1))
            else:
                highlights.append(b)
        out.append({"name": name, "description": " ".join(e["head"][1:]), "stack": stack,
                    "highlights": highlights})
    return out


# ── Listen (Kenntnisse, Sprachen, Zertifikate) ─────────────────────────────
def _rows(lines: list[str]) -> list[str]:
    """Zeilen ohne Aufzählungszeichen, umgebrochene Zeilen wieder zusammengefügt."""
    out: list[str] = []
    for line in lines:
        b = _bullet(line)
        t = (b if b is not None else line).strip()
        if not t:
            continue
        cont = out and b is None and (t[:1].islower() or bool(_HANGING.search(out[-1]))) and \
            not (":" in t[:40] and ":" in out[-1][:40] and not t[:1].islower())
        if cont:
            out[-1] = _join(out[-1], t)
        else:
            out.append(t)
    return out


def _items(text: str) -> list[str]:
    parts = [p.strip(" .") for p in re.split(r",(?![^()]*\))|;|\s+[|•]\s+", text) if p.strip(" .")]
    out: list[str] = []
    for p in parts:
        sub = [s.strip() for s in re.split(r"\s+·\s+", p) if s.strip()]
        for s in sub:
            if out and LEVEL_ONLY_RE.match(s):
                out[-1] = f"{out[-1]} – {s}"
            else:
                out.append(s)
    return out


def _languages(text: str) -> list[dict] | None:
    """„Deutsch (Muttersprache), Englisch (C1)“ → Liste – None, wenn kein Eintrag eine Sprache ist."""
    found = []
    for item in _items(text):
        m = LANG_RE.match(item)
        if not m:
            return None
        level = next((g for g in m.groups()[1:] if g), "").strip()
        found.append({"language": m.group(1).capitalize() if m.group(1).isupper() and len(m.group(1)) > 3
                      else m.group(1), "level": level})
    return found or None


def _skills(lines: list[str]) -> tuple[list[dict], list[dict]]:
    skills, languages = [], []
    for row in _rows(lines):
        m = re.match(r"([^:]{2,40}):\s*(.+)", row)
        cat, rest = (m.group(1).strip(), m.group(2)) if m else ("Kenntnisse", row)
        if re.search(r"sprach|languages", cat, re.I) or not m:
            langs = _languages(rest)
            if langs:
                languages += langs
                continue
        skills.append({"category": cat, "items": _items(rest)})
    return skills, languages


def _language_section(lines: list[str]) -> list[dict]:
    out = []
    for row in _rows(lines):
        langs = _languages(row)
        if langs:
            out += langs
            continue
        m = re.match(r"(.+?)\s*(?:\((.+)\)|[:–—-]\s*(.+))$", row)
        if m:
            out.append({"language": m.group(1), "level": m.group(2) or m.group(3)})
        else:
            out.append({"language": row, "level": ""})
    return out


# ── Kopf / persönliche Daten ────────────────────────────────────────────────
def _looks_like_name(line: str) -> bool:
    t = line.strip()
    words = t.split()
    if not (2 <= len(words) <= 6) or len(t) > 50 or re.search(r"[\d@/:|·•,]", t) or _section_of(t):
        return False
    return all(w[:1].isupper() or w.lower().strip(".'") in _PARTICLES for w in words) and \
        all(re.fullmatch(r"[\w'’.\-]+", w) for w in words)


_PARTICLES = {"von", "van", "vom", "zu", "der", "den", "de", "del", "di", "da", "du", "la", "le", "el", "al", "ben",
              "bin", "ibn", "abu", "ter", "ten"}


def _nice_name(name: str) -> str:
    if name.isupper():
        return " ".join(w if w.lower() in _PARTICLES else w.capitalize() for w in name.split())
    return name


def _name_from_filename(filename: str) -> str:
    stem = Path(filename or "").stem
    stem = re.sub(r"\(\d+\)|\d+", " ", stem)
    words = [w for w in re.split(r"[\s_\-.]+", stem) if w and not re.fullmatch(
        r"(?i)lebenslauf|cv|resume|résumé|curriculum|vitae|bewerbung|final|neu|new|aktuell|de|en|deutsch|english",
        w)]
    cand = " ".join(w if w.lower() in _PARTICLES else w[:1].upper() + w[1:] for w in words)
    return cand if _looks_like_name(cand) else ""


def _personal(head: list[str], extra: list[str], filename: str) -> tuple[dict, list[str]]:
    lines = [_SKIP_TITLE.sub("", l).strip() for l in head + extra]
    lines = [l for l in lines if l]
    text = "\n".join(lines)
    pers = {"first_name": "", "last_name": "", "headline": "", "email": "", "phone": "", "street": "",
            "zip_city": "", "links": []}
    labeled = {}
    for l in lines:
        m = re.match(r"(name|vorname|nachname|anschrift|adresse|wohnort|e-?mail|telefon|tel\.?|mobil|handy)\s*:\s*(.+)",
                     l, re.I)
        if m:
            labeled[m.group(1).lower().rstrip(".")] = m.group(2).strip()

    if m := EMAIL_RE.search(text):
        pers["email"] = m.group(0)
    phone_src = " ".join(labeled.get(k, "") for k in ("telefon", "tel", "mobil", "handy")).strip() or text
    if m := PHONE_RE.search(phone_src):
        pers["phone"] = re.sub(r"\s+", " ", m.group(0)).strip()
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;)")
        if "@" not in url:
            pers["links"].append({"label": "", "url": url})

    addr_src = labeled.get("anschrift") or labeled.get("adresse") or labeled.get("wohnort") or text
    for line in addr_src.splitlines():
        if m := ZIP_RE.search(line):
            city = re.split(r"\s*[,|·•]\s*|\s{2,}|\s(?=\+)", line[m.end():])[0].strip()
            pers["zip_city"] = (m.group(0) + " ".join(city.split()[:3])).strip()
            before = re.split(r"[|·•]", line[:m.start()])[-1].strip(" ,")
            if re.search(r"\d", before) and len(before) <= 50:
                pers["street"] = before
            break
    if not pers["street"] and (m := STREET_RE.search(addr_src)):
        pers["street"] = m.group(0).strip()

    name = labeled.get("name") or " ".join(x for x in (labeled.get("vorname"), labeled.get("nachname")) if x)
    name_idx = -1
    if not name:
        for i, l in enumerate(lines[:6]):
            if _looks_like_name(l):
                name, name_idx = l, i
                break
    if not name:
        name = _name_from_filename(filename)
    if labeled.get("vorname") or labeled.get("nachname"):
        pers["first_name"], pers["last_name"] = labeled.get("vorname", ""), labeled.get("nachname", "")
    else:
        pers["first_name"], pers["last_name"] = split_name(_nice_name(name))

    # Berufsbezeichnung: erste „normale“ Zeile direkt unter dem Namen
    leftovers = []
    for i, l in enumerate(lines):
        if i == name_idx or re.match(r"\w[\w-]*\s*:", l):
            continue
        contact = EMAIL_RE.search(l) or PHONE_RE.search(l) or URL_RE.search(l) or ZIP_RE.search(l) \
            or (pers["street"] and pers["street"] in l)
        if contact:
            continue
        if not pers["headline"] and i <= name_idx + 2 and 3 <= len(l) <= 80 and i > name_idx:
            pers["headline"] = l
        else:
            leftovers.append(l)
    return pers, leftovers


# ── Einstieg ────────────────────────────────────────────────────────────────
def parse_cv(text: str, filename: str = "") -> tuple[dict, list[str]]:
    """Lebenslauf-Text → (normalisiertes Profil, Überschriften der Abschnitte, die nicht übernommen wurden)."""
    blocks: dict[str, list[str]] = {}
    head: list[str] = []
    skipped: list[str] = []
    current = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        sec = _section_of(line) if _bullet(raw) is None else None
        if sec:
            current = sec
            blocks.setdefault(sec, [])
            if sec == "other":
                skipped.append(line.strip(":").strip().title() if line.isupper() else line.strip(":").strip())
            continue
        (blocks[current] if current else head).append(raw)

    pers, leftovers = _personal(head, blocks.get("personal", []), filename)
    summary = " ".join(_rows(blocks.get("summary", [])))
    if not summary:                                       # Profiltext direkt unter dem Kopf ohne Überschrift
        prose = [l for l in leftovers if len(l) > 60]
        summary = " ".join(prose) if len(prose) >= 2 else ""
    skills, langs = _skills(blocks.get("skills", []))
    profile = {
        "personal": pers,
        "summary": summary,
        "experience": _experience(blocks.get("experience", [])),
        "education": _education(blocks.get("education", [])),
        "skills": skills,
        "languages": langs + _language_section(blocks.get("languages", [])),
        "projects": _projects(blocks.get("projects", [])),
        "certificates": _rows(blocks.get("certificates", [])),
    }
    return normalize_profile(profile), skipped
