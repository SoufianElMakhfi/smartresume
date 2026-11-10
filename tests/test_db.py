import sqlite3

import pytest

from smartresume import db
from smartresume.profile import empty_profile


def test_user_lifecycle(tmp_db):
    assert db.needs_setup()
    uid = db.create_user(" Anna@Example.com ", is_admin=True)
    assert not db.needs_setup()
    u = db.get_user_by_email("ANNA@example.com")  # case-insensitiv
    assert u["id"] == uid and u["email"] == "anna@example.com" and u["is_admin"]
    assert db.get_user_by_email("niemand@example.com") is None
    assert db.get_user_by_email("kaputt") is None
    with pytest.raises(db.UserError):
        db.create_user("anna@EXAMPLE.com")
    with pytest.raises(db.UserError):
        db.create_user("keine-mail")
    db.set_email(uid, "anna.neu@example.com")
    assert db.get_user(uid)["email"] == "anna.neu@example.com"
    other = db.create_user("bo@example.com")
    with pytest.raises(db.UserError):
        db.set_email(other, "anna.neu@example.com")
    assert db.count_users() == 2


def test_profile_save_partial(tmp_db):
    uid = db.create_user("anna@example.com")
    assert db.get_profile(uid)["data"] == empty_profile()
    p = empty_profile()
    p["personal"]["name"] = "Anna"
    db.save_profile(uid, data=p, photo=b"IMG")
    db.save_profile(uid, cv_text="Lebenslauf", cv_filename="cv.pdf")  # Foto bleibt
    got = db.get_profile(uid)
    assert got["data"]["personal"]["name"] == "Anna"
    assert got["photo"] == b"IMG" and got["cv_text"] == "Lebenslauf"
    db.save_profile(uid, photo=None)
    assert db.get_profile(uid)["photo"] is None


def test_applications_are_isolated_per_user(tmp_db):
    a = db.create_user("anna@example.com")
    b = db.create_user("bernd@example.com")
    app_id = db.save_application(a, "ACME", "Dev", "Vollzeit", "text", "", b"%PDF", {"x": 1})
    assert len(db.list_applications(a)) == 1
    assert db.list_applications(b) == []
    assert db.get_application(b, app_id) is None
    db.update_application(b, app_id, status="Absage")      # fremder Nutzer: keine Wirkung
    db.delete_application(b, app_id)
    got = db.get_application(a, app_id)
    assert got["status"] == "Beworben" and got["structured"] == {"x": 1}
    db.update_application(a, app_id, status="Interview", notes="Call", hacker="x")
    assert db.get_application(a, app_id)["status"] == "Interview"
    db.delete_user(a)
    assert db.get_application(a, app_id) is None  # Cascade


def test_usage_log(tmp_db):
    a = db.create_user("anna@example.com")
    db.log_usage(a, "generate", "m", 4000)
    db.log_usage(a, "generate", "m", 3000)
    db.log_usage(a, "cv_import", "m", 2000)
    assert db.generations_today(a) == 2
    assert db.user_token_total(a) == 9000
    s = {r["email"]: r for r in db.usage_summary()}
    assert s["anna@example.com"]["tokens"] == 9000 and s["anna@example.com"]["calls"] == 3
