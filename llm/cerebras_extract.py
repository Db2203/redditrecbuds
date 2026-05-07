"""cerebras wrapper. their api is openai-compatible so this is just
chat completions over https. free tier in 2026: 30 rpm, 14400 rpd, 1m tokens/day.
the 1M tpd is the binding constraint for us (~1500-2000 calls/day at our prompt size)."""
import json
import time
from pathlib import Path

import requests

MODEL = "llama-3.1-8b"
URL = "https://api.cerebras.ai/v1/chat/completions"
PROMPT_PATH = Path(__file__).parent / "prompts" / "extract.txt"


def load_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def make_session():
    return requests.Session()


def extract(session, api_key, prompt_template, post_title, comment_body, max_retries=3):
    prompt = (
        prompt_template
        .replace("{post_title}", post_title or "")
        .replace("{comment_body}", comment_body or "")
    )
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries):
        try:
            r = session.post(URL, json=body, headers=headers, timeout=60)
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise
        if r.status_code == 200:
            data = r.json()
            try:
                text = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                return []
            try:
                return json.loads(text).get("products", [])
            except json.JSONDecodeError:
                return []
        if r.status_code == 429:
            if attempt < max_retries - 1:
                time.sleep(30)
                continue
            raise RuntimeError("cerebras rate limited after retries")
        if r.status_code in (500, 502, 503, 504):
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
        r.raise_for_status()
    raise RuntimeError("cerebras: max retries exhausted")
