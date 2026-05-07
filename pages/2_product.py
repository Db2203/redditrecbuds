import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.db import connect
from lib.scoring import combined_score, normalize_log_volume, wilson_lower

st.set_page_config(page_title="product", layout="wide")
st.title("product detail")

con = connect()


@st.cache_data
def list_products(min_votes):
    return con.execute(
        """
        SELECT brand, model,
            SUM(CASE WHEN sentiment = 'positive' THEN weight ELSE 0 END) AS pos,
            SUM(CASE WHEN sentiment = 'negative' THEN weight ELSE 0 END) AS neg
        FROM votes
        GROUP BY brand, model
        HAVING (pos + neg) >= ?
        ORDER BY pos DESC
        """,
        [min_votes],
    ).df()


@st.cache_data
def product_summary(brand, model):
    return con.execute(
        """
        SELECT
            SUM(CASE WHEN sentiment = 'positive' THEN weight ELSE 0 END) AS pos,
            SUM(CASE WHEN sentiment = 'negative' THEN weight ELSE 0 END) AS neg,
            SUM(CASE WHEN sentiment = 'neutral'  THEN weight ELSE 0 END) AS neu,
            COUNT(DISTINCT author) AS users
        FROM votes WHERE brand = ? AND model = ?
        """,
        [brand, model],
    ).fetchone()


@st.cache_data
def mentions_over_time(brand, model):
    return con.execute(
        """
        SELECT DATE_TRUNC('month', TO_TIMESTAMP(c.created_utc)) AS month,
               m.sentiment,
               COUNT(*) AS n
        FROM mentions m
        JOIN comments c ON c.id = m.comment_id
        WHERE m.brand = ? AND m.model = ?
        GROUP BY 1, 2
        ORDER BY 1
        """,
        [brand, model],
    ).df()


@st.cache_data
def price_distribution(brand, model):
    return con.execute(
        """
        SELECT price_mentioned
        FROM mentions
        WHERE brand = ? AND model = ? AND price_mentioned IS NOT NULL
          AND price_mentioned BETWEEN 10 AND 1000
        """,
        [brand, model],
    ).df()


@st.cache_data
def top_quotes(brand, model, sentiment, n=5):
    return con.execute(
        """
        SELECT c.body, c.score, c.link_id, m.one_line_reason
        FROM mentions m
        JOIN comments c ON c.id = m.comment_id
        WHERE m.brand = ? AND m.model = ? AND m.sentiment = ?
          AND LENGTH(c.body) BETWEEN 80 AND 800
        ORDER BY c.score DESC
        LIMIT ?
        """,
        [brand, model, sentiment, n],
    ).fetchall()


@st.cache_data
def co_mentioned(brand, model, n=8):
    return con.execute(
        """
        WITH this_users AS (
            SELECT DISTINCT author FROM votes WHERE brand = ? AND model = ?
        )
        SELECT v.brand, v.model, COUNT(DISTINCT v.author) AS n
        FROM votes v
        JOIN this_users tu ON tu.author = v.author
        WHERE NOT (v.brand = ? AND v.model = ?)
        GROUP BY 1, 2
        ORDER BY n DESC
        LIMIT ?
        """,
        [brand, model, brand, model, n],
    ).df()


with st.sidebar:
    min_votes = st.slider("min votes for product list", 2, 30, 3)

products = list_products(min_votes)
if products.empty:
    st.info("no products yet. run the pipeline first.")
    st.stop()

labels = [f"{r['brand']} {r['model']}" for _, r in products.iterrows()]
choice = st.selectbox("pick a product", labels)
chosen = products.iloc[labels.index(choice)]
brand, model = chosen["brand"], chosen["model"]

pos, neg, neu, users = product_summary(brand, model)
ratio = pos / max(pos + neg, 1)
score = combined_score(
    normalize_log_volume([pos] + products["pos"].tolist())[0],
    wilson_lower(pos, neg),
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("positive", f"{pos:.1f}")
c2.metric("negative", f"{neg:.1f}")
c3.metric("positive ratio", f"{ratio:.0%}")
c4.metric("unique voters", f"{int(users)}")

st.divider()

st.subheader("mentions over time")
ts = mentions_over_time(brand, model)
if not ts.empty:
    fig = px.bar(ts, x="month", y="n", color="sentiment",
                 color_discrete_map={
                     "positive": "#5cb85c",
                     "negative": "#d9534f",
                     "neutral": "#8c8c8c",
                 })
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("no mentions over time data")

prices = price_distribution(brand, model)
if not prices.empty:
    st.subheader("prices people mentioned")
    fig = px.histogram(prices, x="price_mentioned", nbins=20)
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

left, right = st.columns(2)
with left:
    st.subheader("what people like")
    for body, comment_score, link_id, reason in top_quotes(brand, model, "positive"):
        snippet = (body or "")[:400]
        st.markdown(f"> {snippet}{'…' if len(body or '') > 400 else ''}")
        st.caption(f"[{comment_score} pts] · [thread](https://reddit.com/comments/{link_id})")
        st.markdown("---")

with right:
    st.subheader("what people don't")
    neg_quotes = top_quotes(brand, model, "negative")
    if not neg_quotes:
        st.caption("no negative mentions in the dataset for this product")
    for body, comment_score, link_id, reason in neg_quotes:
        snippet = (body or "")[:400]
        st.markdown(f"> {snippet}{'…' if len(body or '') > 400 else ''}")
        st.caption(f"[{comment_score} pts] · [thread](https://reddit.com/comments/{link_id})")
        st.markdown("---")

st.divider()
st.subheader("what else people who mentioned this also mentioned")
co = co_mentioned(brand, model)
if not co.empty:
    co["product"] = co["brand"] + " " + co["model"]
    fig = px.bar(co.iloc[::-1], x="n", y="product", orientation="h")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis_title="overlapping users", yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("not enough overlap data yet")
