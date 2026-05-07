import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.db import connect

st.set_page_config(page_title="redditrecbuds", layout="wide")

st.title("redditrecbuds")
st.write(
    "wireless earbud recommendations distilled from a few audio subreddits. "
    "i pulled posts and comments via the [arctic shift](https://arctic-shift.photon-reddit.com/) "
    "archive (since reddit closed self-service api access in late 2025), used llama 3.1 to extract "
    "product mentions and sentiment, then ranked them with a wilson + log-volume score."
)

con = connect()

n_posts = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
n_comments = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
try:
    n_mentions = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
except Exception:
    n_mentions = 0
try:
    n_votes = con.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    n_users = con.execute("SELECT COUNT(DISTINCT author) FROM votes").fetchone()[0]
except Exception:
    n_votes = 0
    n_users = 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("posts ingested", f"{n_posts:,}")
c2.metric("comments analyzed", f"{n_comments:,}")
c3.metric("product mentions", f"{n_mentions:,}")
c4.metric("unique voters", f"{n_users:,}")

st.divider()

st.subheader("pages")
st.markdown(
    "- **rankings** - top earbuds, ranked\n"
    "- **product** - drill into one product\n"
    "- **compare** - head-to-head between two\n"
    "- **methodology** - how the ranking actually works (and what it doesn't tell you)"
)

st.divider()
st.caption(
    "inspired by redditrecs.com. my version uses a wilson lower-bound for the ratio "
    "term and supports time-windowed rankings. "
    "[source on github](https://github.com/Db2203/redditrecbuds)"
)
