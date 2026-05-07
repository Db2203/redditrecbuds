import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.db import connect
from lib.scoring import combined_score, normalize_log_volume, wilson_lower

st.set_page_config(page_title="rankings", layout="wide")
st.title("rankings")
st.caption("top wireless earbuds by combined wilson + log-volume score")

con = connect()


@st.cache_data
def load_scores(min_votes):
    sql = """
        SELECT brand, model,
            SUM(CASE WHEN sentiment = 'positive' THEN weight ELSE 0 END) AS pos,
            SUM(CASE WHEN sentiment = 'negative' THEN weight ELSE 0 END) AS neg,
            SUM(CASE WHEN sentiment = 'neutral'  THEN weight ELSE 0 END) AS neu,
            COUNT(DISTINCT author) AS users
        FROM votes
        GROUP BY brand, model
        HAVING (pos + neg) >= ?
    """
    df = con.execute(sql, [min_votes]).df()
    if df.empty:
        return df
    df["wilson"] = df.apply(lambda r: wilson_lower(r["pos"], r["neg"]), axis=1)
    df["log_vol"] = normalize_log_volume(df["pos"].tolist())
    df["combined"] = [
        combined_score(v, w) for v, w in zip(df["log_vol"], df["wilson"])
    ]
    return df.sort_values("combined", ascending=False).reset_index(drop=True)


@st.cache_data
def sample_comments(brand, model, sentiment, n=2):
    sql = """
        SELECT m.one_line_reason, c.body, c.score, c.link_id
        FROM mentions m
        JOIN comments c ON c.id = m.comment_id
        WHERE m.brand = ? AND m.model = ? AND m.sentiment = ?
          AND LENGTH(c.body) BETWEEN 80 AND 600
        ORDER BY c.score DESC
        LIMIT ?
    """
    return con.execute(sql, [brand, model, sentiment, n]).fetchall()


with st.sidebar:
    min_votes = st.slider("minimum votes (pos + neg)", 2, 50, 3)
    show = st.slider("how many to show", 10, 200, 30)

df = load_scores(min_votes)
if df.empty:
    st.info("no votes yet. run the ingest + extraction pipeline first.")
    st.stop()

st.metric("products in this view", f"{len(df):,}")
top = df.head(show)

for i, row in top.iterrows():
    with st.container(border=True):
        head, score = st.columns([3, 1])
        with head:
            st.markdown(f"### #{i + 1}  {row['brand']} {row['model']}")
            ratio = row["pos"] / max(row["pos"] + row["neg"], 1)
            st.caption(
                f"{row['pos']:.1f} positive · {row['neg']:.1f} negative · "
                f"{row['neu']:.1f} neutral · {ratio:.0%} positive · "
                f"{int(row['users'])} unique voters"
            )
        with score:
            st.metric("score", f"{row['combined']:.3f}")
            st.caption(f"wilson {row['wilson']:.2f} · vol {row['log_vol']:.2f}")

        pos_samples = sample_comments(row["brand"], row["model"], "positive")
        neg_samples = sample_comments(row["brand"], row["model"], "negative")
        if pos_samples or neg_samples:
            left, right = st.columns(2)
            with left:
                st.markdown("**what people like**")
                for reason, body, score, link_id in pos_samples:
                    snippet = (body or "")[:240]
                    st.markdown(f"> {snippet}{'…' if len(body or '') > 240 else ''}")
                    st.caption(
                        f"[{score} pts]"
                        f" · [thread](https://reddit.com/comments/{link_id})"
                    )
            with right:
                st.markdown("**what people don't**")
                for reason, body, score, link_id in neg_samples:
                    snippet = (body or "")[:240]
                    st.markdown(f"> {snippet}{'…' if len(body or '') > 240 else ''}")
                    st.caption(
                        f"[{score} pts]"
                        f" · [thread](https://reddit.com/comments/{link_id})"
                    )
