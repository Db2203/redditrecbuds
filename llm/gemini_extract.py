"""gemini wrapper using direct http calls.

we go direct (vs google-generativeai's sdk) because that sdk uses module-level
configure(api_key=...) which precludes multiple keys in the same process.
direct http lets us pin a key per worker for parallel multi-key throughput.
"""
import json
import time

import requests

MODEL = "gemini-2.5-flash-lite"
URL_TPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

from pathlib import Path
PROMPT_PATH = Path(__file__).parent / "prompts" / "extract.txt"


def load_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def make_session():
    return requests.Session()


def extract(session, api_key, prompt_template, post_title, comment_body, max_retries=3):
    """returns list of mention dicts on success.
    raises on rate limit / api failure so caller can skip checkpointing.
    a bad-shaped response from the model returns [] (treated as 'no products')."""
    prompt = (
        prompt_template
        .replace("{post_title}", post_title or "")
        .replace("{comment_body}", comment_body or "")
    )
    url = URL_TPL.format(model=MODEL, key=api_key)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
            "maxOutputTokens": 512,
        },
    }
    for attempt in range(max_retries):
        try:
            r = session.post(url, json=body, timeout=60)
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise
        if r.status_code == 200:
            data = r.json()
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
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
            raise RuntimeError("gemini rate limited after retries")
        if r.status_code in (500, 502, 503, 504):
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
        r.raise_for_status()
    raise RuntimeError("gemini extract: max retries exhausted")
