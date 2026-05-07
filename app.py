import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.db import connect
from lib.ui import apply_theme, hero, metric_row

st.set_page_config(page_title="redditrecbuds", layout="wide", initial_sidebar_state="collapsed")
apply_theme()

con = connect()
n_posts = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
n_comments = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
try:
    n_mentions = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
except Exception:
    n_mentions = 0
try:
    n_users = con.execute("SELECT COUNT(DISTINCT author) FROM votes").fetchone()[0]
    n_products = con.execute(
        "SELECT COUNT(*) FROM (SELECT brand, model FROM votes GROUP BY brand, model HAVING SUM(weight) >= 2)"
    ).fetchone()[0]
except Exception:
    n_users = 0
    n_products = 0

hero(
    "redditrecbuds",
    "wireless earbud rankings distilled from r/Earbuds discussions, "
    "weighted by what real users actually recommend (not what brands advertise).",
)

metric_row([
    ("Posts ingested", f"{n_posts:,}"),
    ("Comments analyzed", f"{n_comments:,}"),
    ("Product mentions", f"{n_mentions:,}"),
    ("Unique voters", f"{n_users:,}"),
    ("Earbuds ranked", f"{n_products:,}"),
])

st.markdown(
    "<div style='text-align:center; margin: 16px 0 32px 0;'>"
    "<a href='/rankings' style='background:#ff7043; color:#fff; padding:12px 28px; "
    "border-radius:10px; text-decoration:none; font-weight:600; display:inline-block;'>"
    "see the rankings &rarr;</a></div>",
    unsafe_allow_html=True,
)

st.markdown(
    "<div style='max-width:720px; margin: 24px auto; color:#a8a39a; line-height:1.7;'>"
    "<p>Comments are pulled from r/Earbuds via the Arctic Shift archive, then an LLM extracts product mentions "
    "and sentiment. Each user's mentions of a model are deduped to a single vote (so prolific posters can't dominate), "
    "imprecise references like \"Galaxy Buds\" are spread across known models weighted by popularity, and the final score "
    "combines the Wilson lower bound on positive ratio with log-normalized volume at 75:25.</p>"
    "<p style='color:#6a7280; font-size:14px;'>The methodology page in the app has the full breakdown and known limitations. "
    "Source on <a href='https://github.com/Db2203/redditrecbuds' style='color:#ff7043'>GitHub</a>.</p>"
    "</div>",
    unsafe_allow_html=True,
)
