import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.db import connect
from lib.scoring import combined_score, normalize_log_volume, wilson_lower
from lib.ui import apply_theme, quote, rank_card, section

st.set_page_config(page_title="rankings", layout="wide", initial_sidebar_state="collapsed")
apply_theme()

st.markdown(
    "<div style='font-size:36px; font-weight:800; letter-spacing:-1px;'>rankings</div>"
    "<div style='color:#8c8c8c; font-size:15px; margin-bottom:24px;'>"
    "top wireless earbuds, ranked by combined wilson lower bound + log-normalized volume score."
    "</div>",
    unsafe_allow_html=True,
)

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
    df["combined"] = [combined_score(v, w) for v, w in zip(df["log_vol"], df["wilson"])]
    return df.sort_values("combined", ascending=False).reset_index(drop=True)


@st.cache_data
def sample_comments(brand, model, sentiment, n=2):
    return con.execute(
        """SELECT m.one_line_reason, c.body, c.score, c.link_id
           FROM mentions m JOIN comments c ON c.id = m.comment_id
           WHERE m.brand = ? AND m.model = ? AND m.sentiment = ?
             AND LENGTH(c.body) BETWEEN 80 AND 600
           ORDER BY c.score DESC LIMIT ?""",
        [brand, model, sentiment, n],
    ).fetchall()


with st.sidebar:
    st.markdown("### filters")
    min_votes = st.slider("min votes (pos + neg)", 2, 30, 2)
    show = st.slider("how many to show", 5, 100, 25)

df = load_scores(min_votes)

if df.empty:
    st.info("no votes yet. run the ingest + extraction pipeline first.")
    st.stop()

top = df.head(show)
for i, row in top.iterrows():
    rank_card(
        rank=i + 1,
        brand=row["brand"],
        model=row["model"],
        pos=row["pos"],
        neg=row["neg"],
        neu=row["neu"],
        users=row["users"],
        score=row["combined"],
    )

    pos_q = sample_comments(row["brand"], row["model"], "positive", n=1)
    neg_q = sample_comments(row["brand"], row["model"], "negative", n=1)
    if pos_q or neg_q:
        cols = st.columns(2)
        with cols[0]:
            section("what people like")
            for _, body, score, link_id in pos_q:
                quote(body, score, link_id, "positive")
            if not pos_q:
                st.caption("no positive quotes on file")
        with cols[1]:
            section("what people don't")
            for _, body, score, link_id in neg_q:
                quote(body, score, link_id, "negative")
            if not neg_q:
                st.caption("no negative quotes on file")
