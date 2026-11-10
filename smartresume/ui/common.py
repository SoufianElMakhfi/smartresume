"""Gemeinsame UI-Helfer: Nutzer, Modellwahl, Limits, Abo-Modus (Kopieren & Einfügen)."""
from __future__ import annotations

import hashlib
import json

import streamlit as st
import streamlit.components.v1 as components

from .. import bridge, db, llm
from ..branding import load_branding


def branding() -> dict:
    if "branding" not in st.session_state:
        st.session_state.branding = load_branding()
    return st.session_state.branding


def user() -> dict | None:
    return st.session_state.get("user")


def uid() -> int:
    return st.session_state.user["id"]


def go(page: str, **state) -> None:
    st.session_state.page = page
    for k, v in state.items():
        st.session_state[k] = v
    st.rerun()


def available_models() -> list[tuple[dict, str]]:
    """[(cfg, api_key)] – nur Modelle, für die auf dem Server ein Key hinterlegt ist (.env)."""
    out = []
    for cfg in llm.load_models():
        k = llm.resolve_key(cfg)
        if k:
            out.append((cfg, k))
    return out


def model_picker(key: str = "model_label", label: str = "KI-Modell", help_text: str = ""):
    """Selectbox mit verfügbaren Modellen. Gibt (cfg, api_key) zurück – oder None, wenn keine
    KI-API eingerichtet ist (dann greift der Abo-Modus per Kopieren & Einfügen)."""
    models = available_models()
    if not models:
        return None
    labels = [m[0]["label"] for m in models]
    settings = db.get_user_settings(uid())
    preferred = settings.get("default_model") or branding().get("default_model") or labels[0]
    if key not in st.session_state or st.session_state[key] not in labels:
        st.session_state[key] = preferred if preferred in labels else labels[0]

    def fmt(lbl):
        cfg = models[labels.index(lbl)][0]
        return f"{lbl} – {cfg['note']}" if cfg.get("note") else lbl

    choice = st.selectbox(label, labels, key=key, format_func=fmt, help=help_text or None)
    return models[labels.index(choice)]


def check_limit() -> str | None:
    limit = int(branding().get("daily_limit_per_user") or 0)
    if limit and db.generations_today(uid()) >= limit:
        return f"Das Tageslimit von {limit} KI-Bewerbungen ist erreicht."
    return None


def record_usage(kind: str, cfg: dict, tokens: int) -> None:
    db.log_usage(uid(), kind, cfg.get("model", ""), tokens)


def fmt_tokens(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def show_findings(findings: list[dict]) -> None:
    errors = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]
    if not findings:
        st.success("Qualitäts-Check: keine Auffälligkeiten – nicht übertrieben, nicht zu schwach.", icon="✅")
        return
    for f in errors:
        st.error(f["msg"], icon="⛔")
    for f in warns:
        st.warning(f["msg"], icon="⚠️")


def fallback_chain(picked) -> list[tuple[dict, str]]:
    """Gewähltes Modell zuerst, danach alle anderen verfügbaren als Ausweichmodelle."""
    others = [m for m in available_models() if m[0]["label"] != picked[0]["label"]]
    return [picked] + others


def notify_switch(old_cfg: dict, new_cfg: dict, err: Exception) -> None:
    st.info(f"{err} → weiche automatisch auf **{new_cfg['label']}** aus …", icon="🔄")


# ---------------------------------------------------------------------------
# Abo-Modus: Auftrag kopieren → in Gemini/ChatGPT einfügen → Antwort zurück einfügen
# ---------------------------------------------------------------------------
def _copy_buttons(prompt: str) -> None:
    """Buttons, die den Auftrag in die Zwischenablage kopieren und den Chat in einem neuen Tab öffnen.
    Die Buttons werden per Skript erzeugt (kein onclick-Attribut nötig)."""
    bid = "sr" + hashlib.sha1(prompt.encode()).hexdigest()[:10]
    cfg = json.dumps({"id": bid, "text": prompt, "accent": branding().get("accent_color") or "#0F5F6E",
                      "sites": bridge.CHAT_SITES}).replace("</", "<\\/")
    js = r"""
(function () {
  var c = %s;
  function copy(t) {
    var ok = false;
    try {
      var ta = document.createElement('textarea'); ta.value = t;
      ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta);
      ta.focus(); ta.select(); ok = document.execCommand('copy'); document.body.removeChild(ta);
    } catch (e) {}
    if (!ok && navigator.clipboard) { navigator.clipboard.writeText(t); ok = true; }
    if (!ok) { alert('Kopieren nicht möglich - bitte den Auftrag unter "Auftrag anzeigen" kopieren.'); }
  }
  function build(tries) {
    var box = document.getElementById(c.id);
    if (!box) { if (tries < 50) { setTimeout(function () { build(tries + 1); }, 100); } return; }
    if (box.dataset.ready) { return; }
    box.dataset.ready = '1';
    Object.keys(c.sites).forEach(function (name) {
      var b = document.createElement('button');
      b.textContent = '\uD83D\uDCCB Kopieren & ' + name + ' \u00F6ffnen';
      b.style.cssText = 'flex:1;min-width:180px;padding:.6rem 1rem;border:0;border-radius:.5rem;' +
                        'background:' + c.accent + ';color:#fff;font-size:.95rem;cursor:pointer';
      b.addEventListener('click', function () { copy(c.text); window.open(c.sites[name], '_blank'); });
      box.appendChild(b);
    });
  }
  build(0);
})();
""" % cfg
    body = (f'<div id="{bid}" style="display:flex;gap:.5rem;flex-wrap:wrap;margin:.25rem 0 .5rem"></div>'
            f"<script>{js}</script>")
    try:
        st.html(body, unsafe_allow_javascript=True)
    except TypeError:  # ältere Streamlit-Versionen: im iframe
        components.html(body, height=60)


def chat_bridge(prompt: str, key: str, validate=None) -> dict | None:
    """Zeigt den Abo-Modus für einen KI-Auftrag. Gibt das geprüfte JSON zurück, sobald eine
    verwertbare Antwort eingefügt wurde, sonst None."""
    st.markdown("**1.** Auftrag kopieren und im Chat einfügen · **2.** abschicken · "
                "**3.** komplette Antwort kopieren und unten einfügen")
    _copy_buttons(prompt)
    with st.expander("Auftrag anzeigen (zum manuellen Kopieren)"):
        st.code(prompt, language=None, wrap_lines=True)
    with st.form(f"bridge_{key}"):
        answer = st.text_area("Antwort von Gemini / ChatGPT hier einfügen", height=180, key=f"bridge_answer_{key}")
        submitted = st.form_submit_button("Weiter", type="primary", use_container_width=True)
    if not submitted:
        return None
    try:
        return bridge.parse_answer(answer, validate)
    except ValueError as e:
        st.error(str(e))
        st.markdown("Schreib das hier in **denselben Chat** und füge die neue Antwort ein:")
        st.code(bridge.correction_prompt(str(e)), language=None, wrap_lines=True)
        return None
