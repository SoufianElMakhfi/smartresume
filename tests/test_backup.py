import io
import json
import zipfile

import pytest

from smartresume import backup, db
from smartresume.profile import normalize_profile

SAMPLE = json.loads(open("tests/fixtures/sample_profile.json", encoding="utf-8").read())


def _fill(uid):
    db.save_profile(uid, data=normalize_profile(SAMPLE), photo=b"\xff\xd8JPEG", signature=b"\x89PNGsig",
                    cv_text="Lebenslauf-Text", cv_filename="cv.pdf")
    db.save_user_settings(uid, {"default_model": "Fake", "mail": {"address": "lena@example.com", "password": "pw"}})
    a = db.save_application(uid, "Lumora GmbH", "Frontend Developer", "Vollzeit", "Anzeige", "https://x.de/1",
                            b"%PDF-1", {"summary": "Hallo"}, status="Erstellt")
    db.update_application(uid, a, notes="Rückruf Freitag")
    db.save_application(uid, "Nordwind", "Dev", "Teilzeit", "", "", b"%PDF-2", {})


def test_export_contains_everything_but_secrets(tmp_db):
    uid = db.create_user("lena@example.com")
    _fill(uid)
    z = zipfile.ZipFile(io.BytesIO(backup.export_user(uid)))
    names = z.namelist()
    assert {"smartresume.json", "profil.json", "einstellungen.json", "foto.jpg", "unterschrift.png",
            "bewerbungen.json"} <= set(names)
    assert sum(n.startswith("Bewerbungen/") and n.endswith(".pdf") for n in names) == 2
    assert "pw" not in z.read("einstellungen.json").decode()            # kein Passwort in der Sicherung
    assert backup.read_backup(backup.export_user(uid))["applications"] == 2


def test_restore_on_new_pc_roundtrip(tmp_db):
    uid = db.create_user("lena@example.com")
    _fill(uid)
    data = backup.export_user(uid)
    other = db.create_user("neu@example.com")                          # „neuer PC“: leeres Konto
    db.save_application(other, "Alt", "Alt", "Vollzeit", "", "", b"", {})
    info = backup.import_user(other, data)
    assert info["applications"] == 2
    prof = db.get_profile(other)
    assert prof["data"]["personal"]["name"] == db.get_profile(uid)["data"]["personal"]["name"]
    assert prof["photo"] == b"\xff\xd8JPEG" and prof["signature"] == b"\x89PNGsig" and prof["cv_text"] == "Lebenslauf-Text"
    apps = db.list_applications(other)
    assert [a["company"] for a in apps] == ["Nordwind", "Lumora GmbH"]   # „Alt“ ersetzt
    lumora = db.get_application(other, apps[1]["id"])
    assert lumora["notes"] == "Rückruf Freitag" and lumora["status"] == "Erstellt"
    assert bytes(lumora["pdf_bytes"]) == b"%PDF-1"
    assert db.get_user_settings(other)["default_model"] == "Fake"


@pytest.mark.parametrize("data", [b"kein zip", b""])
def test_rejects_foreign_files(tmp_db, data):
    with pytest.raises(backup.BackupError):
        backup.read_backup(data)
