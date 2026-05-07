"""tiny helper to read api keys from .streamlit/secrets.toml or env.

streamlit's st.secrets only works inside a streamlit run, so cli scripts
need their own way to read the same toml file. this is that.
"""
import os
import re
from pathlib import Path

SECRETS_PATH = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"


def get(name):
    env = os.environ.get(name)
    if env:
        return env
    if SECRETS_PATH.exists():
        text = SECRETS_PATH.read_text(encoding="utf-8")
        m = re.search(rf'^\s*{re.escape(name)}\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            return m.group(1)
    raise RuntimeError(f"{name} not found in env or {SECRETS_PATH}")
