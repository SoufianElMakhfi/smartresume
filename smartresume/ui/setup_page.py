"""KI einrichten (nur Admins): kostenlose API-Keys eintragen, testen, speichern.

Die Keys landen verschlüsselt (Windows-DPAPI, secret.py) in der lokalen .env und gelten
für alle Nutzer dieser Installation. Ohne Key funktioniert die App weiter über den Abo-Modus.
"""
from __future__ import annotations

import streamlit as st

from .. import config, llm


def _test(env: str, key: str) -> tuple[bool, str]:
    cfg = next((m for m in llm.load_models() if m.get("key_env") == env), None)
    if not cfg:
        return False, "Für diesen Anbieter ist kein Modell in der Modellliste eingetragen."
    try:
        llm.complete(cfg, key, "Antworte nur mit dem Wort OK.", "Test", max_tokens=50, temperature=0)
        return True, f"Funktioniert ({cfg['label']})."
    except llm.LLMError as e:
        return False, str(e)


def _provider(p: dict) -> str | None:
    """Zeigt einen Anbieter. Eingefügter Key wird sofort geprüft und gespeichert – kein extra „Speichern“."""
    env = p["env"]
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        status = ":green[:material/check_circle: eingerichtet und aktiv]" if config.is_set(env) \
            else ":gray[noch kein Key]"
        c1.markdown(f"**{p['name']}** {'· kostenlos' if p['free'] else ''}  \n{status}")
        c2.link_button("Key holen", p["url"], use_container_width=True, icon=":material/open_in_new:")
        st.caption(p["how"])
        if config.set_externally(env):
            st.caption("Dieser Key ist auf dem Server fest hinterlegt und kann hier nicht geändert werden.")
            return None
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        c1.text_input("API-Key", type="password", key=f"setup_{env}", on_change=_save_key, args=(env,),
                      placeholder="Key hier einfügen – wird sofort geprüft und gespeichert" if not config.is_set(env)
                      else "gespeichert – zum Ändern neuen Key einfügen", label_visibility="collapsed")
        c2.button("Prüfen & speichern", key=f"save_{env}", type="primary", use_container_width=True,
                  on_click=_save_key, args=(env,), icon=":material/check:")
        if config.is_set(env) and st.button("Gespeicherten Key testen", key=f"test_{env}", type="tertiary",
                                            icon=":material/network_check:"):
            ok, msg = _test(env, llm.resolve_key({"key_env": env}))
            st.session_state[f"setup_msg_{env}"] = (ok, msg if ok else f"Test fehlgeschlagen: {msg}")
        ok, msg = st.session_state.get(f"setup_msg_{env}") or (None, "")
        if ok is True:
            st.success(msg, icon=":material/check_circle:")
        elif ok is False:
            st.error(msg, icon=":material/error:")
            if st.session_state.get(f"setup_pending_{env}") and st.button("Trotzdem speichern", key=f"force_{env}",
                         help="Z. B. wenn nur das Tageskontingent gerade aufgebraucht ist."):
                config.save_values({env: st.session_state.pop(f"setup_pending_{env}", "")})
                st.session_state[f"setup_msg_{env}"] = (True, "Gespeichert.")
                st.rerun()
        return None


def _save_key(env: str) -> None:
    """Callback beim Einfügen (Enter/Verlassen des Felds): testen und bei Erfolg sofort speichern."""
    key = (st.session_state.get(f"setup_{env}") or "").strip()
    st.session_state[f"setup_{env}"] = ""                     # Key nicht im Feld stehen lassen
    if not key:
        return
    ok, msg = _test(env, key)
    if ok:
        config.save_values({env: key})
        st.session_state[f"setup_msg_{env}"] = (True, f"{msg} Gespeichert – die KI arbeitet ab jetzt automatisch.")
    else:
        st.session_state[f"setup_pending_{env}"] = key
        st.session_state[f"setup_msg_{env}"] = (False, f"Key nicht gespeichert: {msg}")


# Einfügen genügt: Nach Strg+V in ein Key-Feld verlässt das Skript das Feld kurz – dann übernimmt Streamlit den
# Wert sofort (sonst erst bei Enter oder Klick woanders), und der Key wird geprüft und gespeichert.
_PASTE_COMMITS = """<script>
(function () {
  var doc = document;
  try { if (window.parent && window.parent.document) doc = window.parent.document; } catch (e) {}
  if (doc.__srPasteCommit) return;
  doc.__srPasteCommit = true;
  doc.addEventListener('paste', function (e) {
    var t = e.target;
    if (t && t.tagName === 'INPUT' && t.type === 'password') setTimeout(function () { t.blur(); }, 80);
  }, true);
})();
</script>"""


def _paste_commits() -> None:
    try:
        st.html(_PASTE_COMMITS, unsafe_allow_javascript=True)
    except TypeError:          # ältere Streamlit-Versionen: Enter bzw. Knopf genügen
        pass


def render() -> None:
    st.title("KI einrichten")
    _paste_commits()
    st.write("Mit einem **kostenlosen** API-Key schreibt die KI deine Bewerbungen automatisch. "
             "Ein Key reicht – mit zwei oder drei springt die App automatisch um, wenn ein Kontingent leer ist.")
    st.caption("Ohne Key funktioniert SmartResume trotzdem: dann über dein Gemini- oder ChatGPT-Konto per "
               "Kopieren & Einfügen. Die Keys bleiben auf diesem PC – verschlüsselt und nur mit deinem Windows-Konto lesbar.")

    for p in [p for p in config.PROVIDERS if p["free"]]:
        _provider(p)
    with st.expander("Weitere Anbieter (kostenpflichtig, optional)"):
        for p in [p for p in config.PROVIDERS if not p["free"]]:
            _provider(p)

    removable = [p for p in config.PROVIDERS if config.is_set(p["env"]) and not config.set_externally(p["env"])]
    if removable:
        with st.popover("Key entfernen", icon=":material/delete:"):
            for p in removable:
                if st.button(p["name"], key=f"rm_{p['env']}", use_container_width=True):
                    config.save_values({p["env"]: ""})
                    st.rerun()
    st.caption("Hinweis: Bei kostenlosen Angeboten können Anbieter Eingaben zum Training nutzen – die Aufträge "
               "enthalten Lebenslaufdaten.")
