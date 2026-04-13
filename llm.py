"""
Cliente LLM unificado. Roteia entre Google Gemini direto e OpenRouter (OpenAI-compatible).

Config via env:
- LLM_PROVIDER: 'google' (default) | 'openrouter'
- LLM_MODEL: id do modelo no provider (ex: 'gemini-2.5-flash' ou 'google/gemini-2.5-flash')
- GEMINI_API_KEY / OPENROUTER_API_KEY
"""
import os
import json
import urllib.request
import urllib.error


def provider() -> str:
    return os.environ.get("LLM_PROVIDER", "google").lower()


def model() -> str:
    return os.environ.get("LLM_MODEL") or (
        "google/gemini-2.5-flash" if provider() == "openrouter" else "gemini-2.5-flash"
    )


def is_configured() -> bool:
    if provider() == "openrouter":
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    return bool(os.environ.get("GEMINI_API_KEY"))


def generate(prompt: str, system: str | None = None, temperature: float = 0.1,
             max_tokens: int = 8192) -> str:
    """Gera texto. Retorna string. Levanta RuntimeError em erro."""
    if provider() == "openrouter":
        return _openrouter(prompt, system, temperature, max_tokens)
    return _google(prompt, system, temperature, max_tokens)


def _google(prompt: str, system: str | None, temperature: float, max_tokens: int) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("google-generativeai não instalado.")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY não configurada.")
    genai.configure(api_key=key)
    gen_cfg = {"temperature": temperature, "max_output_tokens": max_tokens}
    try:
        m = genai.GenerativeModel(model_name=model(), system_instruction=system,
                                   generation_config=gen_cfg)
    except TypeError:
        m = genai.GenerativeModel(model())
    resp = m.generate_content(prompt)
    return resp.text


def _openrouter(prompt: str, system: str | None, temperature: float, max_tokens: int) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada.")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Auto Video Editor",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenRouter {e.code}: {body[:500]}") from e
    return data["choices"][0]["message"]["content"]
