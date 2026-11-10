"""Stellenanzeigen von einer URL laden.

1. schema.org/JobPosting (JSON-LD) – sauber, kurz, auf den meisten Jobbörsen vorhanden
2. Fallback: sichtbarer Haupttext der Seite ohne Navigation/Footer
"""
from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse


class ScrapeError(RuntimeError):
    pass


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.6",
}


def _check_public_url(url: str) -> None:
    """Schutz vor SSRF im Mehrbenutzerbetrieb: nur öffentliche http(s)-Adressen."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ScrapeError("Ungültiger Link – bitte mit https:// angeben.")
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except socket.gaierror:
        raise ScrapeError("Die Adresse konnte nicht aufgelöst werden.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ScrapeError("Interne Adressen sind nicht erlaubt.")


def _html_to_text(fragment: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(fragment or "", "html.parser")
    for li in soup.find_all("li"):
        li.replace_with(soup.new_string("- " + li.get_text(" ", strip=True)))
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))


def _iter_ld(obj):
    if isinstance(obj, list):
        for x in obj:
            yield from _iter_ld(x)
    elif isinstance(obj, dict):
        yield obj
        if "@graph" in obj:
            yield from _iter_ld(obj["@graph"])


def extract_jobposting(page_html: str) -> str | None:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _iter_ld(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "JobPosting" not in types:
                continue
            parts = [f"Stellentitel: {node.get('title', '')}"]
            org = node.get("hiringOrganization") or {}
            if isinstance(org, dict) and org.get("name"):
                parts.append(f"Unternehmen: {org['name']}")
            locs = node.get("jobLocation") or []
            for loc in (locs if isinstance(locs, list) else [locs]):
                addr = (loc or {}).get("address") or {}
                if isinstance(addr, dict):
                    a = " ".join(str(addr.get(k, "")) for k in ("streetAddress", "postalCode", "addressLocality"))
                    if a.strip():
                        parts.append(f"Ort: {a.strip()}")
            if node.get("employmentType"):
                et = node["employmentType"]
                parts.append("Anstellungsart: " + (", ".join(et) if isinstance(et, list) else str(et)))
            for field in ("description", "responsibilities", "qualifications", "skills", "jobBenefits"):
                if node.get(field):
                    parts.append(_html_to_text(html.unescape(str(node[field]))))
            text = "\n".join(p for p in parts if p.strip())
            if len(text) > 200:
                return text
    return None


def extract_main_text(page_html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return main.get_text("\n", strip=True)


def scrape_url(url: str, timeout: int = 15) -> str:
    import requests
    _check_public_url(url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        raise ScrapeError(f"Seite nicht erreichbar ({e.__class__.__name__}).")
    if resp.status_code in (401, 403, 429):
        raise ScrapeError(f"Die Seite blockiert automatische Abrufe (HTTP {resp.status_code}).")
    if resp.status_code >= 400:
        raise ScrapeError(f"Seite nicht ladbar (HTTP {resp.status_code}).")
    resp.encoding = resp.encoding or resp.apparent_encoding
    page = resp.text
    text = extract_jobposting(page) or extract_main_text(page)
    if len(text) < 200:
        raise ScrapeError("Auf der Seite wurde kaum Text gefunden (evtl. per JavaScript geladen).")
    return text
