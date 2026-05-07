"""groq + llama 3.1 wrapper for extracting wireless-earbud mentions from comments."""
import json
import time
from pathlib import Path
from groq import Groq

MODEL = "llama-3.1-8b-instant"
PROMPT_PATH = Path(__file__).parent / "prompts" / "extract.txt"


def load_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def make_client(api_key):
    return Groq(api_key=api_key)


def extract(client, prompt_template, post_title, comment_body, max_retries=3):
    """run extraction on a single comment. returns list of product dicts."""
    prompt = (
        prompt_template
        .replace("{post_title}", post_title or "")
        .replace("{comment_body}", comment_body or "")
    )

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=1024,
            )
            content = resp.choices[0].message.content
            return json.loads(content).get("products", [])
        except json.JSONDecodeError:
            if attempt < max_retries - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            return []
        except Exception as e:
            msg = str(e).lower()
            if "rate" in msg or "429" in msg or "503" in msg:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    return []
