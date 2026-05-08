"""groq via direct http with the same (session, api_key, ...) signature as
gemini/cerebras so it can drop into run_paced_pool. lets us proactively pace
groq calls (the existing groq sdk path with threadpool can't pace per-call)."""
import json
import time

import requests

MODEL = "llama-3.1-8b-instant"
URL = "https://api.groq.com/openai/v1/chat/completions"


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
            raise RuntimeError("groq-paced rate limited after retries")
        if r.status_code in (500, 502, 503, 504):
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
        r.raise_for_status()
    raise RuntimeError("groq-paced: max retries exhausted")
