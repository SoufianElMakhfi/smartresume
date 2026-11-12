import xml.etree.ElementTree as ET

import build_msix
from smartresume import paths


def test_store_version_has_zero_revision():
    assert build_msix.store_version("2.0.0") == "2.0.0.0"
    assert build_msix.store_version("v2.1") == "2.1.0.0"
    assert build_msix.store_version("3.4.5.6") == "3.4.5.0"


def test_manifest_uses_store_identity():
    root = ET.fromstring(build_msix.manifest("2.0.1.0"))
    ns = {"m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10"}
    ident = root.find("m:Identity", ns)
    assert ident.get("Name") == "Soubasa.smartresume" and ident.get("Version") == "2.0.1.0"
    assert ident.get("Publisher").startswith("CN=")
    assert root.find("m:Properties/m:PublisherDisplayName", ns).text == "Soubasa"


def test_source_checkout_is_not_packaged():
    assert not paths.packaged()


def test_third_party_licenses_cover_bundled_libraries():
    import build_licenses
    text = build_licenses.render()
    for pkg in ("streamlit", "pywebview", "typst", "pandas", "requests"):
        assert f"\n{pkg} " in text.split("Übersicht", 1)[1], pkg
    assert "Apache License" in text                         # Lizenz-/NOTICE-Texte sind mit drin
