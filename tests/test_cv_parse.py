"""Lebenslauf ohne KI auslesen – nur erfundene Lebensläufe."""
import json
from pathlib import Path

from smartresume import cv_parse, render
from smartresume.profile import normalize_profile, split_name

# „Zeitraum  Titel, Firma“ in einer Zeile
DATE_FIRST = """Max Mustermann
max@example.de | +49 170 1234567 | Musterweg 1, 50667 Köln
BERUFSERFAHRUNG
05/2021 – heute  Sachbearbeiter, Muster GmbH, Köln
- Bearbeitung von Kundenanfragen per Telefon und E-Mail
- Pflege der Stammdaten in SAP
03/2019 - 04/2021 Werkstudent bei Beispiel AG
- Unterstützung im Controlling
AUSBILDUNG
2018 – 2021 Kaufmann für Büromanagement, IHK Köln
2010 – 2018 Abitur, Gymnasium Musterstadt
KENNTNISSE
MS Office, SAP, DATEV
Deutsch (Muttersprache), Englisch (B2)
HOBBYS
Fußball, Lesen
"""

# „Titel / Zeitraum / Firma · Zusatz“ untereinander, Symbolschrift-Aufzählungszeichen (\x7f), umbrochene Zeilen
TITLE_FIRST = """Lina Ben Salah
Studentin der Informatik
Ahornweg 7, 50667 Köln · +49 160 1112233 · lina@example.com
KURZPROFIL
Studentin der Informatik im 3. Semester mit Erfahrung in der Werkstudenten-
tätigkeit und Freude an sauberem Code.
AUSBILDUNG
Bachelor of Science Informatik
 seit 10/2023
Hochschule Musterstadt · 3. Semester
\x7f Relevante Module: Programmierung (Java, Python), Datenbanken,
Algorithmen und Datenstrukturen
Allgemeine Hochschulreife
 06/2023
Beispiel-Gymnasium Köln
BERUFSERFAHRUNG
Werkstudentin IT-Support
 seit 11/2023
Muster Software GmbH, Köln
\x7f Betreuung von 200 Arbeitsplätzen
\x7f Dokumentation von Lösungen im Wiki und
Schulung neuer Kolleginnen und Kollegen
Aushilfe Einzelhandel
 03/2021 – 09/2023
Beispiel Markt KG, Köln
\x7f Kassieren und Warenverräumung
KENNTNISSE
\x7f Programmierung: Java, Python, SQL
\x7f Software: MS Office (Word, Excel) · sehr gute Kenntnisse
\x7f Sprachen: Deutsch (Muttersprache), Englisch (C1), Arabisch (B2)
\x7f Arbeitsweise: strukturiert, selbstständig und
teamorientiert
"""

# Block „Persönliche Daten“ mit Beschriftungen, Monatsnamen
LABELED = """LEBENSLAUF
PERSÖNLICHE DATEN
Name: Maria von der Heide
Anschrift: Lindenstraße 4a, 80331 München
Telefon: 0151 23456789
E-Mail: maria.heide@example.com
Geburtsdatum: 01.02.1999
www.linkedin.com/in/maria-heide
BERUFLICHER WERDEGANG
Okt. 2022 – bis heute
Projektmanagerin
Beispiel Software GmbH, München
• Leitung von drei Kundenprojekten mit bis zu 8 Personen
Juli 2020 – Sep. 2022
Junior Consultant
Muster Consulting AG
• Analyse von Geschäftsprozessen
STUDIUM
10/2016 – 06/2020
B.Sc. Betriebswirtschaftslehre
Universität zu Köln
SPRACHEN
Deutsch – Muttersprache
Englisch – fließend (C1)
ZERTIFIKATE
Professional Scrum Master I (2021)
"""


def test_split_name_keeps_name_particles_in_last_name():
    assert split_name("Max Mustermann") == ("Max", "Mustermann")
    assert split_name("Anna Maria Schmidt") == ("Anna Maria", "Schmidt")
    assert split_name("Lina Ben Salah") == ("Lina", "Ben Salah")
    assert split_name("Maria von der Heide") == ("Maria", "von der Heide")
    assert split_name("Mustermann, Max") == ("Max", "Mustermann")
    assert split_name("Max") == ("Max", "")


def test_profile_builds_full_name_and_reads_old_profiles():
    p = normalize_profile({"personal": {"first_name": "Lina", "last_name": "Ben Salah"}})
    assert p["personal"]["name"] == "Lina Ben Salah"
    old = normalize_profile({"personal": {"name": "Maria von der Heide"}})      # Profil von vor der Trennung
    assert (old["personal"]["first_name"], old["personal"]["last_name"]) == ("Maria", "von der Heide")


def test_date_first_layout():
    p, skipped = cv_parse.parse_cv(DATE_FIRST)
    pers = p["personal"]
    assert (pers["first_name"], pers["last_name"]) == ("Max", "Mustermann")
    assert (pers["email"], pers["phone"]) == ("max@example.de", "+49 170 1234567")
    assert (pers["street"], pers["zip_city"]) == ("Musterweg 1", "50667 Köln")
    job, student = p["experience"]
    assert (job["role"], job["company"], job["location"], job["start"], job["end"]) == \
        ("Sachbearbeiter", "Muster GmbH", "Köln", "05/2021", "Heute")
    assert job["bullets"] == ["Bearbeitung von Kundenanfragen per Telefon und E-Mail", "Pflege der Stammdaten in SAP"]
    assert (student["role"], student["company"]) == ("Werkstudent", "Beispiel AG")
    assert [(e["degree"], e["institution"]) for e in p["education"]] == \
        [("Kaufmann für Büromanagement", "IHK Köln"), ("Abitur", "Gymnasium Musterstadt")]
    assert p["skills"] == [{"category": "Kenntnisse", "items": ["MS Office", "SAP", "DATEV"]}]
    assert p["languages"] == [{"language": "Deutsch", "level": "Muttersprache"},
                              {"language": "Englisch", "level": "B2"}]
    assert skipped == ["Hobbys"]


def test_title_first_layout_with_wrapped_lines():
    p, _ = cv_parse.parse_cv(TITLE_FIRST)
    pers = p["personal"]
    assert (pers["first_name"], pers["last_name"], pers["headline"]) == \
        ("Lina", "Ben Salah", "Studentin der Informatik")
    assert (pers["street"], pers["zip_city"], pers["phone"]) == ("Ahornweg 7", "50667 Köln", "+49 160 1112233")
    assert "Werkstudententätigkeit und Freude" in p["summary"]                 # Silbentrennung aufgelöst
    bsc, abi = p["education"]
    assert (bsc["degree"], bsc["institution"], bsc["start"], bsc["end"]) == \
        ("Bachelor of Science Informatik", "Hochschule Musterstadt", "10/2023", "Heute")
    assert "Datenbanken, Algorithmen und Datenstrukturen" in bsc["details"]
    assert (abi["degree"], abi["start"], abi["end"]) == ("Allgemeine Hochschulreife", "", "06/2023")
    ws, shop = p["experience"]
    assert (ws["role"], ws["company"], ws["location"]) == ("Werkstudentin IT-Support", "Muster Software GmbH", "Köln")
    assert ws["bullets"][1] == "Dokumentation von Lösungen im Wiki und Schulung neuer Kolleginnen und Kollegen"
    assert (shop["role"], shop["start"], shop["end"]) == ("Aushilfe Einzelhandel", "03/2021", "09/2023")
    skills = {s["category"]: s["items"] for s in p["skills"]}
    assert skills["Software"] == ["MS Office (Word, Excel) – sehr gute Kenntnisse"]
    assert skills["Arbeitsweise"] == ["strukturiert", "selbstständig und teamorientiert"]
    assert [l["language"] for l in p["languages"]] == ["Deutsch", "Englisch", "Arabisch"]


def test_labeled_personal_block_and_month_names():
    p, _ = cv_parse.parse_cv(LABELED)
    pers = p["personal"]
    assert (pers["first_name"], pers["last_name"]) == ("Maria", "von der Heide")
    assert (pers["street"], pers["zip_city"], pers["phone"]) == ("Lindenstraße 4a", "80331 München", "0151 23456789")
    assert pers["links"] == [{"label": "LinkedIn", "url": "https://www.linkedin.com/in/maria-heide"}]
    pm, jc = p["experience"]
    assert (pm["role"], pm["company"], pm["location"], pm["start"], pm["end"]) == \
        ("Projektmanagerin", "Beispiel Software GmbH", "München", "10/2022", "Heute")
    assert (jc["start"], jc["end"]) == ("07/2020", "09/2022")
    assert p["education"][0]["institution"] == "Universität zu Köln"
    assert p["languages"][1] == {"language": "Englisch", "level": "fließend (C1)"}
    assert p["certificates"] == ["Professional Scrum Master I (2021)"]


def test_name_from_filename_when_text_has_none():
    p, _ = cv_parse.parse_cv("BERUFSERFAHRUNG\n2020 – 2024 Verkäuferin, Muster AG\n",
                             "Lebenslauf_Lina_Ben_Salah (1).pdf")
    assert (p["personal"]["first_name"], p["personal"]["last_name"]) == ("Lina", "Ben Salah")


def test_years_in_bullets_are_not_dates():
    p, _ = cv_parse.parse_cv("Max Mustermann\nBERUFSERFAHRUNG\n2020 – 2024 Admin, Muster AG\n"
                             "- Migration auf Windows Server 2019\n- Einführung von Office 2021\n")
    assert len(p["experience"]) == 1 and len(p["experience"][0]["bullets"]) == 2


def test_reads_own_pdf_export():
    """Kontaktdaten aus einem mit SmartResume erzeugten PDF (Zeiträume liefert pypdf dort nicht)."""
    from smartresume import cv_import, generate
    profile = normalize_profile(json.loads((Path(__file__).parent / "fixtures" / "sample_profile.json")
                                           .read_text(encoding="utf-8")))
    s = generate.assemble({"summary": "Kurzprofil.", "cover_letter": {"p1": "Text " * 40}}, profile, "Vollzeit")
    text = cv_import.extract_text("x.pdf", render.render_pdf(s, profile))
    p, _ = cv_parse.parse_cv(text)
    assert p["personal"]["name"] == profile["personal"]["name"]
    assert p["personal"]["email"] == profile["personal"]["email"]
