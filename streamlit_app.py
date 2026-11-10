"""Einstieg für Streamlit Community Cloud (erwartet streamlit_app.py)."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
