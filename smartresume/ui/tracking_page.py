"""Meine Bewerbungen – Status, Notizen, Download, Bearbeiten."""
from __future__ import annotations

import re

import streamlit as st

from .. import db, render
from . import generate_page
from .common import go, uid

STATUS_ICON = {"Erstellt": "📝", "Beworben": "🔵", "Interview": "🟡", "Angebot": "🟢", "Absage": "🔴", "Zurückgezogen": "⚪"}


def render() -> None:
    st.title("Meine Bewerbungen")
    apps = db.list_applications(uid())
    if not apps:
        st.info("Noch keine Bewerbungen gespeichert.")
        if st.button("➕ Erste Bewerbung erstellen", type="primary"):
            go("generate")
        return

    counts = {s: sum(1 for a in apps if a["status"] == s) for s in db.STATUS_OPTIONS}
    cols = st.columns(len(counts))
    for col, (s, n) in zip(cols, counts.items()):
        col.metric(f"{STATUS_ICON[s]} {s}", n)

    c1, c2 = st.columns([2, 1])
    q = c1.text_input("Suchen", placeholder="🔍 Firma oder Stelle …", label_visibility="collapsed")
    status_filter = c2.selectbox("Status", ["Alle"] + db.STATUS_OPTIONS, label_visibility="collapsed")
    shown = [a for a in apps
             if (not q or q.lower() in f"{a['company']} {a['job_title']}".lower())
             and (status_filter == "Alle" or a["status"] == status_filter)]
    if not shown:
        st.warning("Keine passende Bewerbung gefunden.")

    for a in shown:
        title = f"{STATUS_ICON.get(a['status'], '🔵')} {a['company'] or '?'} – {a['job_title'] or '?'}"
        meta = " · ".join(x for x in (a["employment_type"], a["applied_at"]) if x)
        with st.expander(f"{title}  ({meta})"):
            c1, c2 = st.columns([2, 1])
            new_status = c2.selectbox("Status", db.STATUS_OPTIONS,
                                      index=db.STATUS_OPTIONS.index(a["status"])
                                      if a["status"] in db.STATUS_OPTIONS else 0, key=f"st_{a['id']}")
            if new_status != a["status"]:
                db.update_application(uid(), a["id"], status=new_status)
                st.rerun()
            if a["job_url"]:
                c1.markdown(f"🔗 [Zur Stellenanzeige]({a['job_url']})")
            if a["status"] == "Erstellt":
                c1.caption("Unterlagen fertig, noch nicht als beworben markiert.")
                if c1.button("✅ Als beworben markieren", key=f"applied_{a['id']}"):
                    db.mark_applied(uid(), a["id"])
                    st.rerun()
            notes = st.text_area("Notizen (Ansprechpartner, Gesprächstermine …)", a["notes"] or "",
                                 key=f"notes_{a['id']}", height=80)
            if notes != (a["notes"] or ""):
                db.update_application(uid(), a["id"], notes=notes)
            detail = db.get_application(uid(), a["id"])
            if detail and detail["job_text"]:
                with st.popover("📄 Stellenanzeige"):
                    st.text(detail["job_text"][:6000])
            if detail and detail["pdf_bytes"]:
                base = re.sub(r"[^\w-]+", "_", f"{a['company']}_{a['job_title']}")[:70]
                d1, d2, d3 = st.columns(3)
                d1.download_button("⬇ Mappe (1 PDF)", detail["pdf_bytes"], file_name=f"Bewerbung_{base}.pdf",
                                   mime="application/pdf", key=f"dl_{a['id']}", use_container_width=True)
                try:
                    letter_pdf, cv_pdf = render.split_pdf(detail["pdf_bytes"])
                    d2.download_button("⬇ Anschreiben", letter_pdf, file_name=f"Anschreiben_{base}.pdf",
                                       mime="application/pdf", key=f"dla_{a['id']}", use_container_width=True)
                    d3.download_button("⬇ Lebenslauf", cv_pdf, file_name=f"Lebenslauf_{base}.pdf",
                                       mime="application/pdf", key=f"dll_{a['id']}", use_container_width=True)
                except Exception:  # noqa: BLE001 – ältere/abweichende PDFs: nur die Mappe
                    pass
            b2, b3 = st.columns(2)
            if b2.button("✏️ Bearbeiten", key=f"edit_{a['id']}", use_container_width=True,
                         disabled=not (detail and detail["structured"])):
                generate_page.load_application(detail)
                go("generate")
            if b3.button("🗑 Löschen", key=f"del_{a['id']}", use_container_width=True):
                st.session_state[f"confirm_del_{a['id']}"] = True
            if st.session_state.get(f"confirm_del_{a['id']}"):
                st.warning("Diese Bewerbung endgültig löschen?")
                if st.button("Ja, löschen", key=f"del_yes_{a['id']}", type="primary"):
                    db.delete_application(uid(), a["id"])
                    st.session_state.pop(f"confirm_del_{a['id']}", None)
                    st.rerun()
