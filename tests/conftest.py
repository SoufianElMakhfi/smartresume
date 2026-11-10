from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"   # erfundenes Beispielprofil (Max Mustermann)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Jeder Test bekommt eine frische, isolierte Datenbank."""
    path = tmp_path / "test.db"
    monkeypatch.setenv("SMARTRESUME_DB", str(path))
    from smartresume import db
    db.init_db()
    return path


@pytest.fixture(autouse=True)
def _apptest_ignores_stale_widgets(monkeypatch):
    """Nach st.rerun() mitten im Lauf lässt AppTest Elemente des ersten Durchgangs im
    Baum stehen (der Browser entfernt sie). Deren Widget-State ist bereits gelöscht –
    beim nächsten Klick würde AppTest daran mit KeyError scheitern. Wir ignorieren sie,
    so wie der Browser es tut."""
    from streamlit.testing.v1 import element_tree

    orig = element_tree.get_widget_state

    def tolerant(node):
        try:
            return orig(node)
        except KeyError:
            return None
    monkeypatch.setattr(element_tree, "get_widget_state", tolerant)
