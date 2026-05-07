"""gemini wrapper for extracting wireless-earbud mentions.

mirrors llm/groq_extract.py's interface so extract.py can swap providers.
gemini's free tier has way more generous tpm than groq's, but a tighter
daily request cap (1500 rpd at the time of writing).
"""
import json
import time
from pathlib import Path

import google.generativeai as genai

MODEL = "gemini-2.5-flash-lite"
PROMPT_PATH = Path(__file__).parent / "prompts" / "extract.txt"


def load_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def make_client(api_key):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL)


def extract(client, prompt_template, post_title, comment_body, max_retries=2):
    prompt = (
        prompt_template
        .replace("{post_title}", post_title or "")
        .replace("{comment_body}", comment_body or "")
    )

    for attempt in range(max_retries):
        try:
            resp = client.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1,
                    "max_output_tokens": 512,
                },
            )
            return json.loads(resp.text).get("products", [])
        except json.JSONDecodeError:
            return []
        except Exception as e:
            msg = str(e).lower()
            if any(s in msg for s in ("rate", "429", "quota", "resource_exhausted")) and attempt < max_retries - 1:
                time.sleep(15)
                continue
            return []
    return []
