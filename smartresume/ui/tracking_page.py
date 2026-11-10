"""Meine Bewerbungen – Status, Notizen, Download, Bearbeiten."""
from __future__ import annotations

import re

import streamlit as st

from .. import db
from . import generate_page
from .common import go, uid

STATUS_ICON = {"Beworben": "🔵", "Interview": "🟡", "Angebot": "🟢", "Absage": "🔴", "Zurückgezogen": "⚪"}


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
            notes = st.text_area("Notizen (Ansprechpartner, Gesprächstermine …)", a["notes"] or "",
                                 key=f"notes_{a['id']}", height=80)
            if notes != (a["notes"] or ""):
                db.update_application(uid(), a["id"], notes=notes)
            detail = db.get_application(uid(), a["id"])
            if detail and detail["job_text"]:
                with st.popover("📄 Stellenanzeige"):
                    st.text(detail["job_text"][:6000])
            b1, b2, b3 = st.columns(3)
            if detail and detail["pdf_bytes"]:
                fname = re.sub(r"[^\w-]+", "_", f"Bewerbung_{a['company']}_{a['job_title']}")[:80] + ".pdf"
                b1.download_button("⬇ PDF", detail["pdf_bytes"], file_name=fname, mime="application/pdf",
                                   key=f"dl_{a['id']}", use_container_width=True)
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
