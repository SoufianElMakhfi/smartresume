"""Einheitliche KI-Schnittstelle für mehrere Anbieter.

- Gemini (google-genai SDK)
- OpenAI-kompatibel: OpenRouter, Groq, OpenAI, Mistral, lokales Ollama … (per HTTP)
- Claude (anthropic SDK)

Modelle sind in models.json konfigurierbar (Whitelabel), API-Keys kommen aus der
Umgebung (.env des Betreibers). Ohne Key oder bei leerem Kontingent greift der
Abo-Modus (bridge.py): Kopieren & Einfügen über Gemini/ChatGPT im Browser.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths


# Gemini-Aliase (*-latest, nur unter API „v1beta“) verhindern, dass die App bricht, wenn Google alte
# Versionen abschaltet; fehlt ein Modell trotzdem, sucht _call_gemini ein passendes verfügbares. Reihenfolge = Fallback-Reihenfolge:
# Flash-Lite war im Test 3–6 s schnell bei guter Qualität, Flash lag bei 55–200 s bzw. Timeout.
DEFAULT_MODELS = [
    {"label": "Gemini Flash-Lite", "provider": "gemini", "model": "gemini-flash-lite-latest",
     "key_env": "GEMINI_API_KEY", "note": "Kostenlos, schnell – empfohlen"},
    {"label": "Gemini Flash", "provider": "gemini", "model": "gemini-flash-latest",
     "key_env": "GEMINI_API_KEY", "note": "Kostenlos, gründlicher, oft langsam", "thinking_budget": 1024},
    {"label": "DeepSeek V4 Flash (OpenRouter)", "provider": "openai_compat", "model": "deepseek/deepseek-v4-flash",
     "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY", "note": "Sehr günstig"},
    {"label": "GPT-OSS 120B (Groq)", "provider": "openai_compat", "model": "openai/gpt-oss-120b",
     "base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY", "note": "Kostenlos, sehr schnell"},
    {"label": "Mistral Small", "provider": "openai_compat", "model": "mistral-small-latest",
     "base_url": "https://api.mistral.ai/v1", "key_env": "MISTRAL_API_KEY", "note": "Kostenloser Experiment-Plan, europäisch"},
    {"label": "Claude Haiku 5.5", "provider": "claude", "model": "claude-haiku-5-5",
     "key_env": "ANTHROPIC_API_KEY", "note": "Günstig, sehr zuverlässig"},
    {"label": "Claude Sonnet 5.5", "provider": "claude", "model": "claude-sonnet-5-5",
     "key_env": "ANTHROPIC_API_KEY", "note": "Beste Textqualität, kostenpflichtig"},
]


class LLMError(RuntimeError):
    """Fehler mit nutzerfreundlicher Meldung. `transient` = anderes Modell/erneuter
    Versuch kann helfen (Timeout, Überlastung, Rate-Limit)."""

    def __init__(self, msg: str, transient: bool = False):
        super().__init__(msg)
        self.transient = transient


def with_fallback(candidates: list, fn, on_switch=None):
    """Ruft fn(cfg, key) mit dem ersten Kandidaten auf; bei vorübergehenden Fehlern
    wird der nächste Kandidat versucht. candidates: [(cfg, key), …].
    Gibt (Ergebnis, (cfg, key)) zurück."""
    last = None
    for i, cand in enumerate(candidates):
        cfg, key = cand[0], cand[1]
        try:
            return fn(cfg, key), cand
        except LLMError as e:
            last = e
            if not e.transient or i == len(candidates) - 1:
                raise
            if on_switch:
                on_switch(cfg, candidates[i + 1][0], e)
    raise last or LLMError("Kein KI-Modell verfügbar.")


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    data: dict | None = field(default=None)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def load_models() -> list[dict]:
    path = Path(os.environ.get("SMARTRESUME_MODELS", paths.home_dir() / "models.json"))
    if path.exists():
        try:
            models = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(models, list) and models:
                return models
        except json.JSONDecodeError:
            pass
    return DEFAULT_MODELS


def resolve_key(cfg: dict, user_keys: dict | None = None) -> str:
    """Nutzer-Key (BYOK) hat Vorrang vor dem Betreiber-Key aus der Umgebung."""
    env = cfg.get("key_env", "")
    if user_keys and user_keys.get(env):
        return user_keys[env]
    if cfg.get("provider") == "openai_compat" and "localhost" in cfg.get("base_url", ""):
        return os.environ.get(env, "") or "local"
    return os.environ.get(env, "")


# ---------------------------------------------------------------------------
# JSON robust parsen
# ---------------------------------------------------------------------------
def parse_json_loose(text: str) -> dict:
    """Parst JSON auch wenn das Modell Codefences, Vor-/Nachtext oder
    trailing commas liefert."""
    if text is None:
        raise ValueError("Leere Antwort")
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE)
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Kein JSON-Objekt in der Antwort gefunden")
        chunk = t[start:end + 1]
        chunk = re.sub(r",\s*([}\]])", r"\1", chunk)  # trailing commas
        obj = json.loads(chunk)
    if not isinstance(obj, dict):
        raise ValueError("JSON ist kein Objekt")
    return obj


# ---------------------------------------------------------------------------
# Provider-Aufrufe
# ---------------------------------------------------------------------------
# Gefundene Ersatzmodelle, falls Google ein konfiguriertes Modell abschaltet: {(gewünscht): echt}
_GEMINI_RESOLVED: dict[str, str] = {}


def _gemini_family(model: str) -> str:
    m = model.lower()
    return "flash-lite" if "flash-lite" in m else "flash" if "flash" in m else "pro" if "pro" in m else ""


def _gemini_version(name: str) -> tuple:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return (float(m.group(1)) if m else 0.0,)


def pick_gemini_model(wanted: str, available: list[str]) -> str | None:
    """Wählt aus den verfügbaren Modellen (Namen ohne „models/“) das passendste zur gewünschten
    Familie (flash-lite / flash / pro): stabile vor Vorschau-Versionen, neueste Version zuerst."""
    fam = _gemini_family(wanted)
    if not fam:
        return None

    def fits(n: str) -> bool:
        n = n.lower()
        if not n.startswith("gemini-") or any(x in n for x in ("tts", "image", "audio", "live", "embedding", "robotics")):
            return False
        return _gemini_family(n) == fam

    cands = [n for n in available if fits(n)]
    if not cands:
        return None
    # -latest-Aliase sind ideal; sonst stabil > preview/exp, dann neueste Version
    cands.sort(key=lambda n: (n.endswith("-latest"), not any(x in n for x in ("preview", "exp")),
                              _gemini_version(n)), reverse=True)
    return cands[0]


def _gemini_generate(client, types, model, user, kwargs):
    return client.models.generate_content(model=model, contents=user, config=types.GenerateContentConfig(**kwargs))


def _call_gemini(cfg, key, system, user, json_mode, max_tokens, temperature) -> LLMResult:
    from google import genai
    from google.genai import types

    timeout_ms = int(cfg.get("timeout", 120)) * 1000
    # google-genai >= 3 spricht standardmäßig „v1“ an – dort fehlen die *-latest-Aliase.
    client = genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=timeout_ms, api_version=cfg.get("api_version", "v1beta")))
    kwargs = dict(system_instruction=system, temperature=temperature, max_output_tokens=max_tokens)
    if json_mode:
        kwargs["response_mime_type"] = "application/json"
    if "thinking_budget" in cfg:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=int(cfg["thinking_budget"]))
    model = _GEMINI_RESOLVED.get(cfg["model"], cfg["model"])
    try:
        resp = _gemini_generate(client, types, model, user, kwargs)
    except Exception as e:  # noqa: BLE001
        if "not_found" not in str(e).lower() and "404" not in str(e):
            raise
        # Modell gibt es (nicht mehr): passendes verfügbares Modell suchen und merken
        try:
            names = [m.name.split("/")[-1] for m in client.models.list()
                     if "generateContent" in (getattr(m, "supported_actions", None) or ["generateContent"])]
        except Exception:  # noqa: BLE001
            raise e from None
        alt = pick_gemini_model(cfg["model"], names)
        if not alt or alt == model:
            raise LLMError(f"Das Modell „{cfg['model']}“ gibt es bei Google nicht (mehr). "
                           "In models.json ein aktuelles Gemini-Modell eintragen.") from e
        resp = _gemini_generate(client, types, alt, user, kwargs)
        _GEMINI_RESOLVED[cfg["model"]] = model = alt
    text = resp.text
    if not text:
        reason = "unbekannt"
        if getattr(resp, "candidates", None):
            reason = str(resp.candidates[0].finish_reason)
        raise LLMError(f"Gemini hat keine Antwort geliefert ({reason}).")
    um = getattr(resp, "usage_metadata", None)
    return LLMResult(text,
                     getattr(um, "prompt_token_count", 0) or 0,
                     (getattr(um, "candidates_token_count", 0) or 0) + (getattr(um, "thoughts_token_count", 0) or 0),
                     model)


def _call_openai_compat(cfg, key, system, user, json_mode, max_tokens, temperature) -> LLMResult:
    import requests

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if "openrouter.ai" in cfg.get("base_url", ""):
        headers["X-Title"] = os.environ.get("SMARTRESUME_APP_NAME", "SmartResume")
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    resp = requests.post(cfg["base_url"].rstrip("/") + "/chat/completions",
                         headers=headers, json=payload, timeout=int(cfg.get("timeout", 120)))
    if resp.status_code >= 400:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    text = body["choices"][0]["message"]["content"]
    usage = body.get("usage") or {}
    return LLMResult(text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), cfg["model"])


def _call_claude(cfg, key, system, user, json_mode, max_tokens, temperature) -> LLMResult:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=cfg["model"], max_tokens=max_tokens, temperature=temperature,
        system=system, messages=[{"role": "user", "content": user}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return LLMResult(text, resp.usage.input_tokens, resp.usage.output_tokens, cfg["model"])


PROVIDERS = {"gemini": _call_gemini, "openai_compat": _call_openai_compat, "claude": _call_claude}


def _friendly(e: Exception, cfg: dict) -> LLMError:
    msg = str(e)
    low = msg.lower()
    if any(k in low for k in ("api key", "api_key", "unauthorized", "401", "permission", "authentication")):
        return LLMError(f"API-Key für {cfg['label']} ungültig oder fehlt.")
    if any(k in low for k in ("quota", "resource_exhausted", "rate limit", "rate_limit", "429")):
        return LLMError(f"Kontingent/Rate-Limit bei {cfg['label']} erreicht – kurz warten oder anderes Modell wählen.",
                        transient=True)
    if any(k in low for k in ("timeout", "timed out", "deadline", "504")):
        return LLMError(f"Zeitüberschreitung bei {cfg['label']} – bitte erneut versuchen.", transient=True)
    if any(k in low for k in ("500", "502", "503", "unavailable", "overloaded", "529", "internal")):
        return LLMError(f"{cfg['label']} ist gerade überlastet – bitte erneut versuchen.", transient=True)
    return LLMError(f"KI-Fehler ({cfg['label']}): {msg[:400]}")


def complete(cfg: dict, key: str, system: str, user: str, *, json_mode: bool = False,
             max_tokens: int = 4096, temperature: float = 0.4) -> LLMResult:
    if not key:
        raise LLMError(f"Kein API-Key für {cfg['label']} hinterlegt ({cfg.get('key_env')}).")
    fn = PROVIDERS.get(cfg.get("provider"))
    if not fn:
        raise LLMError(f"Unbekannter Anbieter: {cfg.get('provider')}")
    try:
        return fn(cfg, key, system, user, json_mode, max_tokens, temperature)
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001 – Provider-SDKs werfen unterschiedlichste Fehler
        raise _friendly(e, cfg) from e


def complete_json(cfg: dict, key: str, system: str, user: str, *, max_tokens: int = 4096,
                  temperature: float = 0.4, retries: int = 1, validate=None) -> LLMResult:
    """Wie `complete`, aber garantiert ein geparstes dict in `result.data`.
    Bei kaputtem JSON oder fehlgeschlagener Validierung wird einmal mit
    Fehlerhinweis nachgefragt. `validate(data)` gibt eine Fehlerliste zurück."""
    total_in = total_out = 0
    prompt = user
    last_err = ""
    for attempt in range(retries + 1):
        res = complete(cfg, key, system, prompt, json_mode=True, max_tokens=max_tokens,
                       temperature=temperature)
        total_in += res.input_tokens
        total_out += res.output_tokens
        try:
            data = parse_json_loose(res.text)
            problems = validate(data) if validate else []
            if not problems:
                res.data, res.input_tokens, res.output_tokens = data, total_in, total_out
                return res
            last_err = "; ".join(problems)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = f"Ungültiges JSON: {e}"
        prompt = (f"{user}\n\nDEINE LETZTE ANTWORT WAR FEHLERHAFT: {last_err}\n"
                  "Antworte erneut, ausschließlich mit vollständigem, validem JSON.")
        if attempt < retries:
            time.sleep(0.5)
    raise LLMError(f"Die KI hat kein brauchbares Ergebnis geliefert ({last_err}). "
                   "Bitte erneut versuchen oder ein anderes Modell wählen.", transient=True)
