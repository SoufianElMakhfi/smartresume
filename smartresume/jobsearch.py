"""Stellensuche über die Jobbörse der Bundesagentur für Arbeit.

Die BA bietet keine offizielle API; die Jobbörse nutzt aber eine öffentliche Schnittstelle, die das
Projekt bundesAPI dokumentiert (https://github.com/bundesAPI/jobsuche-api). Kein Konto, kein Key nötig.
Kontaktdaten der Arbeitgeber gibt die Schnittstelle nicht heraus (Captcha) – die bleiben unangetastet.

Ablauf: search() → passende Stellen (mit verwandten Begriffen gesucht, selbst auf Relevanz geprüft),
details_text() → kompletter Anzeigentext für die Bewerbung.
"""
from __future__ import annotations

import base64
import re
from concurrent.futures import ThreadPoolExecutor

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-Key": "jobboerse-jobsuche", "User-Agent": "SmartResume (Open Source)"}
JOB_PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"

GERMANY = -1                                   # Umkreis „Deutschlandweit“ (die BA erlaubt höchstens 200 km)
RADII = [0, 10, 25, 50, 100, 200, GERMANY]
MAX_AGE = {"Heute": 0, "Letzte 7 Tage": 7, "Letzte 14 Tage": 14, "Letzte 30 Tage": 30, "Alle": 100}

# Arbeitsort. Die BA kennzeichnet Homeoffice nicht verlässlich (und unterscheidet nicht Homeoffice/Remote/hybrid),
# deshalb liest die App Titel und Anzeigentext selbst.
#   Egal        – kein Filter, schnellste Suche (nur Suchbegriff bzw. Titel zählen)
#   Homeoffice  – komplett von zu Hause aus (Arbeitgeber im gewählten Umkreis; ortsunabhängige Stellen zählen mit)
#   Remote      – egal wo, ortsunabhängig (deshalb immer deutschlandweit gesucht)
#   Hybrid      – beides: teils im Büro, teils zu Hause
#   Präsenz     – vor Ort, kein Homeoffice
ANY, HOMEOFFICE, REMOTE, HYBRID, ONSITE = WORK_MODES = ["Egal", "Homeoffice", "Remote", "Hybrid", "Präsenz"]
_MODE_KEY = {HOMEOFFICE: "homeoffice", REMOTE: "remote", HYBRID: "hybrid", ONSITE: "onsite"}
MAX_CHECK = 300                                # so viele Anzeigen werden höchstens auf den Arbeitsort geprüft

_REMOTE_WORD = (r"\bremote\b(?![\s-]?(?:support|desktop|zugriff|wartung|access|service|management|"
                r"administration|anbindung|steuer|überwach|monitor))")
_HOME_RE = re.compile(r"home[\s-]?office|mobile[ns]?\s+arbeiten|\bhybrid|telearbeit|von zu hause|work from home|"
                      + _REMOTE_WORD + r"|ortsunabh(?:ä|ae)ngig", re.I)
_NO_HOME_RE = re.compile(r"\bkein(?:e|en)?\s+(?:möglichkeit\s+(?:zum|für|auf)\s+)?(?:home[\s-]?office|remote|"
                         r"mobiles\s+arbeiten)|(?:home[\s-]?office|remote)[^.\n]{0,30}\bnicht\s+möglich|"
                         r"ausschließlich\s+vor\s+ort|100\s?%\s*vor\s+ort|präsenzpflicht|reine\s+präsenz", re.I)
_ALL = r"(?:100\s?%|zu\s+100\s?%|vollständig|vollstaendig|komplett|ausschließlich|ausschliesslich|fully|full|rein|voll)"
# egal wo: ortsunabhängig / von überall / ausdrücklich voll remote
_ANYWHERE_RE = re.compile(_ALL + r"[\s-]*(?:im\s+)?remote|remote[\s-]?(?:first|only)\b|\bfull[\s-]?remote\b|"
                          r"ortsunabh(?:ä|ae)ngig|work\s+from\s+anywhere|von\s+(?:überall|ueberall)|workation|"
                          r"(?:deutschlandweit|bundesweit|europaweit)\s+(?:remote|im\s+home[\s-]?office|von\s+zu\s+hause)|"
                          r"remote\s+(?:aus|in|von)\s+ganz\s+(?:deutschland|europa)|egal\s+wo|"
                          r"remote[\s\-–:/(]*(?:bundesweit|deutschlandweit|europaweit)|arbeitsort:?\s*remote|"
                          r"remote\s+oder\s+(?:vor\s+ort|(?:im|in\s+unserem)\s+büro)|"
                          r"(?:vor\s+ort|im\s+büro)\s+oder\s+remote|"
                          r"wo\s+(?:immer\s+)?du\s+(?:willst|möchtest|magst)", re.I)
# komplett von zu Hause
_FULL_HOME_RE = re.compile(_ALL + r"[\s-]*(?:im\s+|von\s+|aus\s+dem\s+)?(?:home[\s-]?office|mobil\w*|zu\s+hause|"
                           r"daheim)|komplett\s+von\s+zu\s+hause|full[\s-]?home[\s-]?office", re.I)
# teils Büro, teils zu Hause
_HYBRID_RE = re.compile(r"\bhybrid|teilweise\s+(?:im\s+|von\s+)?(?:home|remote|mobil|zu\s+hause)|anteilig|"
                        r"\d\s*(?:(?:-|bis)\s*\d\s*)?(?:tag|tage|day|days)\w*\s+(?:pro\s+woche\s+|/\s*woche\s+|"
                        r"die\s+woche\s+)?(?:im\s+|von\s+)?(?:home|remote|mobil|zu\s+hause)|"
                        r"(?:home[\s-]?office|remote|mobil\w*)[\s-]?(?:anteil|quote|tage?)\b|wahlweise|"
                        r"flexibel(?:e|en)?\s+(?:zwischen|aufteilung|kombination)|"
                        r"büro\s+(?:und|oder|&|\+)\s+(?:home|zu\s+hause|remote|mobil)|"
                        r"(?:home[\s-]?office|zu\s+hause|remote)\s+(?:und|oder|&|\+)\s+(?:im\s+)?büro|"
                        r"bis\s+zu\s+(?:[1-9]\d?)\s?%\s*(?:im\s+)?(?:home|remote|mobil)", re.I)


def work_modes(title: str, text: str, flagged: bool = False) -> set[str]:
    """Welche Arbeitsorte die Anzeige zulässt: {'remote', 'homeoffice', 'hybrid', 'onsite'}.
    Remote (egal wo) schließt Homeoffice ein – wer überall arbeiten darf, darf es auch zu Hause.
    `flagged`: Homeoffice-Kennzeichen der BA – zählt nur, wenn der Text nichts anderes sagt."""
    t = f"{title}\n{text}"
    anywhere = _ANYWHERE_RE.search(t) or re.search(_REMOTE_WORD, title, re.I)    # „(Remote)“ im Titel
    full = _FULL_HOME_RE.search(t)
    if _NO_HOME_RE.search(t) and not (anywhere or full):
        return {"onsite"}
    modes = set()
    if anywhere:
        modes |= {"remote", "homeoffice"}
    if full:
        modes.add("homeoffice")
    if _HYBRID_RE.search(t) or (not modes and (_HOME_RE.search(t) or flagged)):
        modes.add("hybrid")
    return modes or {"onsite"}


def work_mode(title: str, text: str, flagged: bool = False) -> str:
    """Der freieste Arbeitsort der Anzeige: 'remote' > 'homeoffice' > 'hybrid' > 'onsite'."""
    modes = work_modes(title, text, flagged)
    return next(m for m in ("remote", "homeoffice", "hybrid", "onsite") if m in modes)


# Arbeitsort ausdrücklich im Suchbegriff („Java remote“) → gilt als Filter, wird aber nicht als Wort gesucht
_MODE_WORDS = [
    (REMOTE, _REMOTE_WORD + r"|\bortsunabh\w*"),
    (HOMEOFFICE, r"\bhome[\s-]?office\b|\bvon\s+zu\s+hause\b"),
    (HYBRID, r"\bhybrid\b"),
    (ONSITE, r"\bpräsenz\b|\bvor\s+ort\b|\bon[\s-]?site\b"),
]


def mode_from_query(what: str) -> str | None:
    """Arbeitsort aus dem Suchbegriff – oder None, wenn keiner genannt ist."""
    for mode, rx in _MODE_WORDS:
        if re.search(rx, what or "", re.I):
            return mode
    return None


def strip_mode_words(what: str) -> str:
    for _, rx in _MODE_WORDS:
        what = re.sub(rx, " ", what or "", flags=re.I)
    return re.sub(r"\s+", " ", what).strip()

# Beschäftigungsart der App → Filter der BA (angebotsart: 1 Arbeit, 2 Selbstständigkeit, 4 Ausbildung,
# 34 Praktikum/Trainee/Werkstudent; arbeitszeit: vz, tz, mj). „title“: woran man die Art im Stellentitel erkennt
# (Filter 34 enthält Werkstudent, Praktikum und Trainee gemischt).
_FILTERS = {
    "Vollzeit": {"angebotsart": 1, "arbeitszeit": "vz"},
    "Teilzeit": {"angebotsart": 1, "arbeitszeit": "tz"},
    "Werkstudent": {"angebotsart": 34, "word": "Werkstudent",
                    "title": r"werkstud|student|studierend|studi-?job|hilfskraft",
                    # Abschlussarbeiten und reine Praktika sind keine Werkstudentenjobs (außer „… / Werkstudent“)
                    "not_title": r"abschlussarbeit|masterand|bachelorand|thesis|masterarbeit|bachelorarbeit|"
                                 r"prakti"},
    "Praktikum": {"angebotsart": 34, "word": "Praktikum", "title": r"prakti|intern\b|internship|praxissemester"},
    "Ausbildung": {"angebotsart": 4},
    "Minijob": {"angebotsart": 1, "arbeitszeit": "mj"},
    "Freelance": {"angebotsart": 2},
}

# Ausdrücklich genannte Stellenart im Suchbegriff („Werkstudent Wirtschaftsinformatik“) hat Vorrang vor der Auswahl,
# sonst sucht man mit „Vollzeit“ und bekommt Vollzeitstellen. NICHT „Student“: das beschreibt die Person, nicht die
# gesuchte Stelle (fertige Studenten suchen Vollzeit). Reihenfolge = Vorrang.
_TYPE_WORDS = [
    ("Werkstudent", r"\bwerkstud\w*|\bstudentische\w*\s+(?:hilfskraft|aushilfe|mitarbeit)\w*"),
    ("Praktikum", r"\bprakti\w*|\bpraxissemester\b|\binternship\b"),
    ("Ausbildung", r"\bausbildung\w*|\bazubi\w*"),
    ("Minijob", r"\bminijob\w*|\bgeringfügig\w*"),
    ("Teilzeit", r"\bteilzeit\b"),
    ("Vollzeit", r"\bvollzeit\b"),
    ("Freelance", r"\bfreelanc\w*|\bfreiberuf\w*"),
]


def type_from_query(what: str) -> str | None:
    """Beschäftigungsart aus dem Suchbegriff – oder None, wenn keine genannt ist."""
    for etype, rx in _TYPE_WORDS:
        if re.search(rx, what or "", re.I):
            return etype
    return None

# ---------------------------------------------------------------------------
# Fachgebiete. Die Jobbörse sucht wortgenau und verknüpft Wörter mit UND: „Software“ findet weder
# „Softwareentwicklung“ noch „Informatiker“ oder „Developer“. Erkennt die App im Suchbegriff ein Fachgebiet
# („trigger“, je Wort geprüft), sucht sie zusätzlich nach dessen Begriffen („queries“) und prüft danach selbst,
# ob Titel („title“) bzw. Berufsangabe der BA („beruf“) wirklich zum Gebiet passen – sonst fliegt die Stelle raus.
# ---------------------------------------------------------------------------
FIELDS = [
    {"name": "IT & Software",
     "trigger": r"software|informati|^entwickler|^developer|programmier|full.?stack|front.?end|back.?end|devops|"
                r"coding|^it$|^web|^apps?$|java|python|script|cloud|^sap$|^dev",
     "queries": ["Software", "Softwareentwicklung", "Softwareentwickler", "Developer", "Informatik", "Informatiker",
                 "Wirtschaftsinformatik", "IT", "Fullstack", "Frontend", "Backend", "Webentwicklung", "Programmierer",
                 "DevOps", "Java", "Python", "SAP", "Cloud"],
     "title": r"software|informati|programmier|full.?stack|front.?end|back.?end|devops|web.?(?:entwickl|develop)|"
              r"anwendungsentwickl|\bjava\b|python|javascript|typescript|\breact\b|angular|(?<!\w)\.net\b|\bc#|"
              r"c\+\+|\bsap\b|\bit\b|\bentwickler|developer|(?:app|software|web).?development|\bcloud|\bki\b|"
              r"\bai\b|künstliche intelligenz|machine learning|data engineer|test.?automat|\bqa\b|"
              r"requirements.?engineer|\bcod(?:ing|er)\b|datenbank|database|linux|system.?administr|helpdesk|"
              r"\berp\b|\bcrm\b",
     "beruf": r"informati|software|programmier|anwendungsentwick|system.?administr|datenbank|data.?scien|"
              r"web.?(?:entwick|design)|\bit-(?:system|administr|anwend|support|sicherheit)|\(it\)"},
    {"name": "IT-Sicherheit & Datenschutz",
     "trigger": r"informationssicherheit|it-?sicherheit|security|cyber|pentest|^isms$|datenschutz",
     "queries": ["Informationssicherheit", "IT-Sicherheit", "IT Security", "Cyber Security", "Security",
                 "Datenschutz", "ISMS", "Pentest"],
     "title": r"informationssicherheit|it-?sicherheit|security|cyber|pentest|penetration|\bisms\b|datenschutz|"
              r"\bsoc\b|forensi|\biam\b",
     "beruf": r"\(it\)|informati|datenschutz"},
    {"name": "Data & KI",
     "trigger": r"^data|^daten(?!schutz)|analy|statisti|^bi$|intelligence|power.?bi|tableau|^machine|^ki$|^ai$|"
                r"science",
     "queries": ["Data", "Data Science", "Data Analyst", "Datenanalyse", "Business Intelligence", "Analytics",
                 "Machine Learning", "KI", "Statistik", "Power BI", "Reporting"],
     "title": r"\bdata\b|daten(?!schutz)|analy|statisti|intelligence|\bbi\b|power.?bi|tableau|machine learning|"
              r"\bki\b|\bai\b|künstliche|reporting|data.?scien",
     "beruf": r"data|statisti|mathemati|informati|analyst"},
    {"name": "Marketing & Kommunikation",
     "trigger": r"marketing|social|^seo$|^sea$|content|kommunikation|^pr$|brand|commerce|redakt|media",
     "queries": ["Marketing", "Online Marketing", "Social Media", "Content", "Kommunikation", "PR",
                 "E-Commerce", "Brand", "Redaktion", "SEO"],
     "title": r"marketing|social.?media|\bseo\b|\bsea\b|content|kommunikation|\bpr\b|public relations|brand|"
              r"commerce|redakt|influencer|kampagne|campaign|\bmedia\b",
     "beruf": r"marketing|kommunikation|\bwerbe|\bpr\b|redakt|online"},
    {"name": "Vertrieb & Kundenbetreuung",
     "trigger": r"vertrieb|sales|verkauf|^account|^business$|key.?account|kunden|customer",
     "queries": ["Vertrieb", "Sales", "Verkauf", "Business Development", "Key Account", "Account Management",
                 "Kundenbetreuung", "Customer Success", "Innendienst"],
     "title": r"vertrieb|sales|verkauf|account|business.?develop|kundenbetreu|kundenservice|customer|innendienst|"
              r"außendienst",
     "beruf": r"vertrieb|verkauf|sales|kundenberat|kundenbetreu"},
    {"name": "Finanzen & Controlling",
     "trigger": r"finanz|finance|controll|buchhalt|accounting|rechnungswesen|steuer|^tax$|audit|prüfung|bank|"
                r"treasury|payroll|^lohn",
     "queries": ["Finanzen", "Finance", "Controlling", "Buchhaltung", "Accounting", "Rechnungswesen", "Steuern",
                 "Tax", "Audit", "Wirtschaftsprüfung", "Treasury"],
     "title": r"finanz|finance|controll|buchhalt|accounting|rechnungswesen|steuer|\btax\b|audit|prüfung|"
              r"treasury|payroll|lohn|bilanz|kreditor|debitor|\bbank",
     "beruf": r"finanz|buchhalt|controll|steuer|bank|bilanz|wirtschaftsprüf"},
    {"name": "Personal & HR",
     "trigger": r"personal|^hr$|human|recruit|^people$|talent",
     "queries": ["Personal", "HR", "Human Resources", "Recruiting", "Personalwesen", "Personalentwicklung",
                 "Talent Acquisition"],
     "title": r"personal|\bhr\b|human.?resource|recruit|talent|\bpeople\b",
     "beruf": r"personal"},
    {"name": "Design & Medien",
     "trigger": r"design|^ux$|^ui$|grafik|gestalt|illustr|video|^foto|^film",
     "queries": ["Design", "UX", "UI Design", "Grafikdesign", "Mediengestaltung", "Produktdesign", "Video"],
     "title": r"design|\bux\b|\bui\b|grafik|gestalt|illustr|video|\bfoto|motion|\b3d\b|\bfilm",
     "beruf": r"design|gestalt|grafik|foto|medien"},
    {"name": "Elektrotechnik & Energie",
     "trigger": r"elektro|electric|energie|energy|automatisier|embedded|hardware|mechatron",
     "queries": ["Elektrotechnik", "Electrical Engineering", "Energietechnik", "Automatisierung", "Embedded",
                 "Hardware", "Mechatronik"],
     "title": r"elektro|electric|energie|energy|automatisier|embedded|hardware|mechatron|\bsps\b|\bplc\b|"
              r"schaltung|hochfrequenz",
     "beruf": r"elektro|energie|mechatron|automatisier"},
    {"name": "Maschinenbau & Produktion",
     "trigger": r"maschinenbau|mechanical|konstruk|^cad$|produktion|fertigung|verfahrenstechn|fahrzeug|automotive|"
                r"luftfahrt|raumfahrt|qualität|quality",
     "queries": ["Maschinenbau", "Konstruktion", "Mechanical Engineering", "Produktion", "Fertigung",
                 "Verfahrenstechnik", "Fahrzeugtechnik", "Qualitätsmanagement", "CAD"],
     "title": r"maschinenbau|mechanical|konstruk|\bcad\b|produktion|fertigung|verfahrenstechn|fahrzeug|automotive|"
              r"luftfahrt|raumfahrt|qualität|quality|werkstoff",
     "beruf": r"maschinenbau|konstrukt|ingenieur|produktion|fertigung|verfahrenstechn|qualität"},
    {"name": "Logistik & Einkauf",
     "trigger": r"logistik|logistic|supply|einkauf|procurement|beschaffung|^lager|transport|spedition",
     "queries": ["Logistik", "Supply Chain", "Einkauf", "Procurement", "Beschaffung", "Disposition"],
     "title": r"logisti|supply|einkauf|procurement|beschaffung|\blager|transport|spedition|disposition",
     "beruf": r"logisti|lager|einkauf|beschaffung|spedition|supply"},
    {"name": "Recht & Compliance",
     "trigger": r"recht|^jura$|jurist|legal|compliance|anwalt|kanzlei",
     "queries": ["Recht", "Jura", "Legal", "Compliance", "Rechtsabteilung", "Kanzlei"],
     "title": r"recht|\bjura\b|jurist|legal|compliance|anwalt|kanzlei|patent",
     "beruf": r"jurist|recht|anwalt|notar"},
    {"name": "Beratung & Projektmanagement",
     "trigger": r"consult|beratung|berater|strateg|projektmanag|^projekt|^bwl$|betriebswirt|^business$",
     "queries": ["Consulting", "Beratung", "Strategie", "Projektmanagement", "Business", "BWL",
                 "Unternehmensentwicklung"],
     "title": r"consult|berat|strateg|projekt|project|business|\bbwl\b|betriebswirt|prozessmanag|operations|"
              r"unternehmensentwicklung",
     "beruf": r"berater|betriebswirt|projektmanag|business|wirtschaftswissen"},
]

# Wörter, die nur die Beschäftigungsart beschreiben (die steht schon im Filter) oder nichts aussagen
_SKIP = re.compile(r"^(?:werkstud\w*|studentisch\w*|student\w*|studierend\w*|praktik\w*|praxissemester|vollzeit|"
                   r"teilzeit|minijob|ausbildung|azubi|freelance\w*|freiberuf\w*|jobs?|stellen?|m|w|d|und|oder|im|in|"
                   r"der|die|das|den|dem|für|bereich|als|mit|bei|von|zur|zum|am|an)$")
QUERY_PAGES = 2     # je Suchwort höchstens 200 Stellen (die BA liefert max. 100 pro Seite)
POOL_PAGES = 20     # Werkstudent/Praktikum: bis zu 2.000 Stellen der Art im Umkreis, dann selbst filtern
PAGE_SIZE = 100


def _stem(word: str) -> str:
    """Grober Wortstamm, damit „Buchhaltung“ auch „Buchhalter“ findet."""
    for suffix in ("ungen", "ung", "erinnen", "erin", "innen", "er", "en", "in", "e", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 5:
            return word[: -len(suffix)]
    return word


def plan(what: str) -> dict:
    """Zerlegt den Suchbegriff: eigene Wörter, erkannte Fachgebiete, Suchwörter für die BA und Prüfmuster."""
    raw = [w.strip("-.") for w in re.findall(r"[\wäöüß.+#-]+", strip_mode_words(what or ""))]
    raw = [w for w in raw if len(w) >= 2 and not _SKIP.match(w.lower())]
    words = [w.lower() for w in raw]
    fields = [f for f in FIELDS if any(re.search(f["trigger"], w) for w in words)]
    others = [f for f in FIELDS if f not in fields]
    own = [re.escape(_stem(w)) if len(w) >= 4 else rf"\b{re.escape(w)}\b" for w in words]
    queries, seen = [], set()
    for q in ([" ".join(raw)] if len(raw) > 1 else []) + raw + [q for f in fields for q in f["queries"]]:
        if q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)

    def rx(parts: list[str]):
        return re.compile("|".join(parts), re.I) if parts else None
    return {
        "words": words,
        "fields": [f["name"] for f in fields],
        "queries": queries[:24],
        "own": rx(own),
        "title": rx([f["title"] for f in fields]),
        "beruf": rx([f["beruf"] for f in fields] + own),
        "other": rx([f["title"] for f in others]),
    }


def relevance(job: dict, p: dict) -> int:
    """0 = passt nicht zum Suchbegriff. Eigenes Wort im Titel (4) > Fachgebiet im Titel (2) > nur Berufsangabe (1).
    Die Berufsangabe der BA ist oft ungenau („Steuerberatung“ → IT-Berater/in) – sie zählt allein nur, wenn der
    Titel nicht eindeutig zu einem anderen Fachgebiet gehört."""
    if not p["words"]:
        return 1
    title, beruf = job["title"], job.get("profession") or ""
    score = 0
    if p["own"] and p["own"].search(title):
        score += 4
    if p["title"] and p["title"].search(title):
        score += 2
    if p["beruf"] and p["beruf"].search(beruf) and (score or not (p["other"] and p["other"].search(title))):
        score += 1
    return score


class JobSearchError(RuntimeError):
    pass


def build_params(what: str, where: str, radius: int, employment_type: str, max_age: int,
                 page: int = 1, size: int = 25) -> dict:
    f = _FILTERS.get(employment_type, {})
    what = (what or "").strip() or f.get("word", "")
    if radius == GERMANY:                      # deutschlandweit: ohne Ort suchen
        where, radius = "", 0
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
        "professions": [b for b in j.get("alleBerufe") or [] if isinstance(b, str)],
    }


def _fetch(specs: list[tuple[dict, int]], workers: int = 8) -> list[dict]:
    """Mehrere Abfragen parallel, jeweils mit Folgeseiten. Schlägt alles fehl, kommt der erste Fehler."""
    results: list[dict] = []
    errors: list[JobSearchError] = []

    def one(params: dict):
        try:
            return params, _get("/pc/v6/jobs", params)
        except JobSearchError as e:
            errors.append(e)
            return params, None

    def items(data: dict) -> list[dict]:
        return data.get("ergebnisliste") or data.get("stellenangebote") or []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        first = list(ex.map(one, [{**p, "page": 1} for p, _ in specs]))
        more = []
        for (params, data), (_, pages) in zip(first, specs):
            if data is None:
                continue
            results += items(data)
            total = int(data.get("maxErgebnisse") or 0)
            last = min(pages, -(-total // PAGE_SIZE))
            more += [{**params, "page": n} for n in range(2, last + 1)]
        for _, data in ex.map(one, more):
            if data is not None:
                results += items(data)
    if errors and not results:
        raise errors[0]
    return results


def search(what: str, where: str, radius: int = 25, employment_type: str = "Vollzeit",
           max_age: int = 30, work_mode: str = ANY, texts: dict | None = None,
           stats: dict | None = None) -> tuple[list[dict], int]:
    """Gibt (Stellen, Anzahl) zurück – nach Relevanz sortiert, Unpassendes bereits entfernt.

    Sucht nach dem Begriff und verwandten Begriffen des erkannten Fachgebiets; bei Werkstudent/Praktikum
    zusätzlich nach allen Stellen dieser Art im Umkreis. Danach prüft die App selbst, ob Titel bzw. Berufsangabe
    passen – die Volltextsuche der Jobbörse liefert sonst z. B. Logistik-Jobs, deren Text „Software“ erwähnt.

    work_mode: „Egal“ prüft nichts (schnellste Suche). Sonst werden die Anzeigentexte der relevantesten Stellen
    geladen (landen in `texts`) und auf den Arbeitsort geprüft. „Remote“ (egal wo) sucht deutschlandweit – der
    Wohnort spielt dann keine Rolle; Homeoffice, Hybrid und Präsenz suchen im gewählten Umkreis."""
    remote = work_mode == REMOTE
    if remote:
        where, radius = "", GERMANY
    if not (what or "").strip() and not (where or "").strip() and not remote:
        raise JobSearchError("Bitte einen Suchbegriff oder Ort angeben.")
    p = plan(what)
    f = _FILTERS.get(employment_type, {})
    base = {k: v for k, v in build_params("", where, radius, employment_type, max_age, size=PAGE_SIZE).items()
            if k not in ("was", "page")}
    if remote:   # deutschlandweit nur Anzeigen, die Remote/Homeoffice überhaupt erwähnen (Volltextsuche der BA)
        words = p["queries"][:8] or [f.get("word", "")]
        specs = [({**base, "was": f"{q} {h}".strip()}, QUERY_PAGES) for q in words for h in ("remote", "homeoffice")]
        # Die BA verknüpft mit UND und findet „Informatik remote“ viel seltener als „remote“ allein → zusätzlich alle
        # Anzeigen mit diesen Wörtern holen; Titel/Fachgebiet prüft danach relevance()
        if p["words"]:
            specs += [({**base, "was": h}, POOL_PAGES) for h in ("remote", "homeoffice", "ortsunabhängig")]
    else:
        specs = [({**base, "was": q}, QUERY_PAGES) for q in p["queries"]]
    if f.get("word") and not remote:
        without_type = {k: v for k, v in base.items() if k != "angebotsart"}
        # Viele Anzeigen findet die BA nicht unter „Werkstudent“ („Werkstudierende“, „Studentische Hilfskraft“) –
        # deshalb zusätzlich alle Stellen der Kategorie ohne Suchwort; der Titel-Filter sortiert danach aus.
        specs += [(base, POOL_PAGES), ({**base, "was": f["word"]}, POOL_PAGES),
                  ({**without_type, "was": f["word"]}, POOL_PAGES)]
    elif not p["queries"]:
        specs.append((base, POOL_PAGES))

    jobs: dict[str, dict] = {}
    for raw in _fetch(specs):
        j = normalize(raw)
        if j["ref"] and j["ref"] not in jobs:
            jobs[j["ref"]] = j
    out = []
    for j in jobs.values():
        if f.get("title") and not re.search(f["title"], j["title"], re.I):
            continue                                   # z. B. Trainee-Stelle bei der Suche nach Werkstudent
        if f.get("not_title") and re.search(f["not_title"], j["title"], re.I)                 and not re.search(r"werkstud", j["title"], re.I):
            continue
        j["relevance"] = relevance(j, p)
        if j["relevance"]:
            out.append(j)
    out.sort(key=lambda j: j["published"] or "", reverse=True)
    out.sort(key=lambda j: -j["relevance"])            # stabil: innerhalb gleicher Relevanz neueste zuerst
    wanted = _MODE_KEY.get(work_mode)
    if wanted:
        texts = texts if texts is not None else {}
        # Bei vielen Kandidaten zuerst die, die laut BA (k)ein Homeoffice haben – Reihenfolge bleibt die Relevanz
        check = sorted(out, key=lambda j: j["homeoffice"] == (wanted == "onsite"))[:MAX_CHECK]
        texts.update(details_many([j for j in check if j["ref"] not in texts], workers=10))
        keep = set()
        for j in check:
            if wanted in work_modes(j["title"], texts.get(j["ref"], ""), j["homeoffice"]):
                j["work_mode"] = wanted                # so steht es dann auch auf der Karte
                keep.add(j["ref"])
        if stats is not None:
            stats.update(candidates=len(out), checked=len(check))
        out = [j for j in out if j["ref"] in keep]     # Reihenfolge (Relevanz) bleibt
    return out, len(out)


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
