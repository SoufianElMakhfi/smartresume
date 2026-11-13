import io

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from smartresume import attachments, backup, db


def _pdf(pages: int = 1, password: str = "") -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=595, height=842)
    if password:
        w.encrypt(password)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (3000, 2000), (200, 30, 30)).save(out, "PNG")      # größer als A4 → wird verkleinert
    return out.getvalue()


def test_image_becomes_a4_pdf_and_pdf_stays():
    pdf = attachments.to_pdf("zeugnis.png", _png())
    page = PdfReader(io.BytesIO(pdf)).pages[0]
    assert round(float(page.mediabox.width)) == 595 and round(float(page.mediabox.height)) == 842   # A4
    original = _pdf(2)
    assert attachments.to_pdf("zertifikat.pdf", original) == original


def test_rejects_protected_broken_and_huge_files():
    with pytest.raises(attachments.AttachmentError, match="passwortgeschützt"):
        attachments.to_pdf("geheim.pdf", _pdf(password="x"))
    with pytest.raises(attachments.AttachmentError, match="weder PDF"):
        attachments.to_pdf("foto.jpg", b"kein bild")
    with pytest.raises(attachments.AttachmentError, match="größer"):
        attachments.to_pdf("riesig.pdf", b"%PDF" + b"0" * (attachments.MAX_MB * 1024 * 1024))


def test_merge_keeps_order_and_pages():
    merged = attachments.merge([_pdf(3), _pdf(1), attachments.to_pdf("a.png", _png())])
    assert attachments.page_count(merged) == 5


def test_documents_in_db_and_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("SMARTRESUME_DB", str(tmp_path / "a.db"))
    db.init_db()
    uid = db.create_user("anna@example.com")
    a = db.add_document(uid, "Arbeitszeugnis Muster AG", "zeugnis.pdf", _pdf(2))
    db.add_document(uid, "Abiturzeugnis", "abi.png", attachments.to_pdf("abi.png", _png()))
    db.rename_document(uid, a, "Zeugnis Muster AG")
    docs = db.list_documents(uid)
    assert [d["title"] for d in docs] == ["Zeugnis Muster AG", "Abiturzeugnis"] and docs[0]["size"] > 0
    picked = db.get_documents(uid, [docs[1]["id"], docs[0]["id"]])   # Reihenfolge wie ausgewählt
    assert [d["title"] for d in picked] == ["Abiturzeugnis", "Zeugnis Muster AG"]

    zip_bytes = backup.export_user(uid)
    db.delete_document(uid, a)
    assert len(db.list_documents(uid)) == 1
    backup.import_user(uid, zip_bytes)
    assert [d["title"] for d in db.list_documents(uid)] == ["Zeugnis Muster AG", "Abiturzeugnis"]
