import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.db import connect
from lib.scoring import combined_score, normalize_log_volume, wilson_lower

st.set_page_config(page_title="compare", layout="wide")
st.title("compare two earbuds")

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
def summary(brand, model):
    row = con.execute(
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
    return {
        "pos": row[0] or 0, "neg": row[1] or 0, "neu": row[2] or 0,
        "users": row[3] or 0,
    }


@st.cache_data
def quotes(brand, model, sentiment, n=3):
    return con.execute(
        """
        SELECT c.body, c.score, c.link_id
        FROM mentions m
        JOIN comments c ON c.id = m.comment_id
        WHERE m.brand = ? AND m.model = ? AND m.sentiment = ?
          AND LENGTH(c.body) BETWEEN 80 AND 600
        ORDER BY c.score DESC
        LIMIT ?
        """,
        [brand, model, sentiment, n],
    ).fetchall()


products = list_products(2)
if products.empty:
    st.info("no products yet.")
    st.stop()

labels = [f"{r['brand']} {r['model']}" for _, r in products.iterrows()]

c1, c2 = st.columns(2)
with c1:
    a = st.selectbox("first", labels, index=0, key="a")
with c2:
    b = st.selectbox("second", labels, index=min(1, len(labels) - 1), key="b")

if a == b:
    st.warning("pick two different products")
    st.stop()

a_brand, a_model = products.iloc[labels.index(a)][["brand", "model"]]
b_brand, b_model = products.iloc[labels.index(b)][["brand", "model"]]

a_sum = summary(a_brand, a_model)
b_sum = summary(b_brand, b_model)

max_pos = max(a_sum["pos"], b_sum["pos"], 1)
a_score = combined_score(
    normalize_log_volume([a_sum["pos"], max_pos])[0],
    wilson_lower(a_sum["pos"], a_sum["neg"]),
)
b_score = combined_score(
    normalize_log_volume([b_sum["pos"], max_pos])[0],
    wilson_lower(b_sum["pos"], b_sum["neg"]),
)

left, right = st.columns(2)


def panel(col, brand, model, summary_, score):
    with col:
        st.subheader(f"{brand} {model}")
        st.metric("score", f"{score:.3f}")
        st.caption(
            f"{summary_['pos']:.1f} positive | {summary_['neg']:.1f} negative | "
            f"{summary_['neu']:.1f} neutral | {int(summary_['users'])} users"
        )

        st.markdown("**likes**")
        for body, sc, link_id in quotes(brand, model, "positive"):
            st.markdown(f"> {(body or '')[:280]}{'…' if len(body or '') > 280 else ''}")
            st.caption(f"[{sc} pts] | [thread](https://reddit.com/comments/{link_id})")

        st.markdown("**gripes**")
        nq = quotes(brand, model, "negative")
        if not nq:
            st.caption("none on file")
        for body, sc, link_id in nq:
            st.markdown(f"> {(body or '')[:280]}{'…' if len(body or '') > 280 else ''}")
            st.caption(f"[{sc} pts] | [thread](https://reddit.com/comments/{link_id})")


panel(left, a_brand, a_model, a_sum, a_score)
panel(right, b_brand, b_model, b_sum, b_score)

st.divider()

# little side-by-side bar chart
metrics = ["pos", "neg", "neu", "users"]
df = pd.DataFrame({
    "metric": metrics * 2,
    "product": [f"{a_brand} {a_model}"] * 4 + [f"{b_brand} {b_model}"] * 4,
    "value": [a_sum[m] for m in metrics] + [b_sum[m] for m in metrics],
})
fig = go.Figure()
for prod in df["product"].unique():
    sub = df[df["product"] == prod]
    fig.add_trace(go.Bar(name=prod, x=sub["metric"], y=sub["value"]))
fig.update_layout(barmode="group", height=320, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig, use_container_width=True)
