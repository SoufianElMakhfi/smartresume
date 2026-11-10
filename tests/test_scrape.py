import json

import pytest

from smartresume import scrape

LD = {
    "@context": "https://schema.org", "@type": "JobPosting", "title": "Sachbearbeiter (m/w/d)",
    "hiringOrganization": {"@type": "Organization", "name": "Muster GmbH"},
    "jobLocation": {"@type": "Place", "address": {"streetAddress": "Ring 1", "postalCode": "50667",
                                                  "addressLocality": "Köln"}},
    "employmentType": ["FULL_TIME"],
    "description": "&lt;p&gt;Wir suchen Verstärkung.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;SAP-Kenntnisse&lt;/li&gt;"
                   "&lt;li&gt;Teamgeist&lt;/li&gt;&lt;/ul&gt;" + " Mehr Text." * 30,
}


def test_jobposting_from_json_ld_graph():
    page = ('<html><head><script type="application/ld+json">' + json.dumps({"@graph": [{"@type": "WebPage"}, LD]})
            + '</script></head><body><nav>Menü</nav>Cookie-Banner</body></html>')
    text = scrape.extract_jobposting(page)
    assert "Stellentitel: Sachbearbeiter (m/w/d)" in text
    assert "Unternehmen: Muster GmbH" in text and "Ring 1 50667 Köln" in text
    assert "\n- SAP-Kenntnisse\n- Teamgeist" in text
    assert "Cookie" not in text


def test_fallback_main_text():
    page = "<html><body><nav>Menü</nav><main><h1>Koch</h1><p>Wir suchen einen Koch.</p></main>" \
           "<footer>Impressum</footer><script>var x=1</script></body></html>"
    assert scrape.extract_jobposting(page) is None
    text = scrape.extract_main_text(page)
    assert "Koch" in text and "Impressum" not in text and "var x" not in text


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.de", "http://127.0.0.1:8501", "http://localhost/",
                                 "http://192.168.0.1/admin", "notaurl"])
def test_rejects_internal_or_invalid_urls(url):
    with pytest.raises(scrape.ScrapeError):
        scrape.scrape_url(url)


def test_timeout_reads_as_blocked(monkeypatch):
    import requests
    monkeypatch.setattr(scrape, "_check_public_url", lambda url: None)

    def slow(*a, **k):
        raise requests.ReadTimeout("x")
    monkeypatch.setattr(requests, "get", slow)
    with pytest.raises(scrape.ScrapeError, match="stepstone.de lässt das automatische Auslesen nicht zu"):
        scrape.scrape_url("https://www.stepstone.de/stellenangebote--x.html")
