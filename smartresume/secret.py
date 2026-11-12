"""Geheimnisse (API-Keys, Mail-Passwörter) verschlüsselt speichern – mit Windows-DPAPI.

DPAPI bindet die Verschlüsselung an das Windows-Konto: Nur dieselbe Person auf demselben PC kann die Werte
wieder lesen. Eine kopierte .env oder Datenbank ist woanders wertlos. Kein Schlüssel im Programm nötig.

Gespeichert wird "dpapi:<base64>". Alte Klartext-Werte werden weiter gelesen (und beim nächsten Speichern
verschlüsselt). Auf anderen Systemen (Linux-Server) bleibt der Wert unverändert – dort kommen Keys ohnehin
aus Umgebungsvariablen des Hosters.
"""
from __future__ import annotations

import base64
import sys

PREFIX = "dpapi:"
_ENTROPY = b"SmartResume/secret/v1"


def available() -> bool:
    return sys.platform == "win32"


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(data: bytes) -> _Blob:
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def _call(fn, data: bytes) -> bytes:
        src, ent, out = _blob(data), _blob(_ENTROPY), _Blob()
        CRYPTPROTECT_UI_FORBIDDEN = 0x1
        if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN,
                  ctypes.byref(out)):
            raise OSError(ctypes.GetLastError(), "DPAPI-Aufruf fehlgeschlagen")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    def _encrypt(data: bytes) -> bytes:
        return _call(ctypes.windll.crypt32.CryptProtectData, data)

    def _decrypt(data: bytes) -> bytes:
        return _call(ctypes.windll.crypt32.CryptUnprotectData, data)


def protect(value: str) -> str:
    """Klartext → "dpapi:…" (unter Windows). Leere oder schon verschlüsselte Werte bleiben, wie sie sind."""
    if not value or value.startswith(PREFIX) or not available():
        return value
    return PREFIX + base64.b64encode(_encrypt(value.encode("utf-8"))).decode("ascii")


def reveal(value: str) -> str:
    """"dpapi:…" → Klartext. Klartext bleibt Klartext. Nicht lesbar (anderer PC/anderes Konto) → ""."""
    if not value or not value.startswith(PREFIX):
        return value or ""
    if not available():
        return ""
    try:
        return _decrypt(base64.b64decode(value[len(PREFIX):])).decode("utf-8")
    except (OSError, ValueError):
        return ""


def is_secret_name(name: str) -> bool:
    """Welche .env-Einträge verschlüsselt werden: Keys, Tokens, Passwörter."""
    n = name.upper()
    return n.endswith(("_KEY", "_TOKEN", "_SECRET", "PASSWORD"))
