import json
import re

from smartresume.ui import common

_HTMLISH = re.compile(r"<[/\w!]")    # dieselbe Prüfung, mit der DOMPurify verdächtige Elemente entfernt


def test_copy_button_script_survives_sanitizer():
    """Streamlit bereinigt st.html mit DOMPurify: Steht im Skripttext etwas wie „<span>“, wird das ganze <script>
    entfernt – die Knöpfe „Kopieren und Gemini/ChatGPT öffnen“ fehlen dann ohne Fehlermeldung."""
    prompt = "Stelle: Entwickler <m/w/d> bei <b>Firma</b> </script><img src=x onerror=alert(1)>"
    body = common._copy_buttons_html(prompt)
    script = body.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    assert not _HTMLISH.search(script), _HTMLISH.search(script).group(0)
    data = json.loads(re.search(r"var c = (\{.*?\});\n", script, re.S).group(1))   # < ist gültiges JSON
    assert data["text"] == prompt and data["copy"].startswith("<svg")
