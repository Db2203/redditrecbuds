import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.db import connect
from lib.scoring import combined_score, normalize_log_volume, wilson_lower
from lib.ui import apply_theme

st.set_page_config(page_title="rankings", layout="wide", initial_sidebar_state="expanded")
apply_theme()

st.markdown(
    "<div style='font-size:36px; font-weight:800; letter-spacing:-1px;'>rankings</div>"
    "<div style='color:#8c8c8c; font-size:15px; margin-bottom:16px;'>"
    "top wireless earbuds, ranked by combined wilson lower bound + log-normalized volume."
    "</div>",
    unsafe_allow_html=True,
)

con = connect()

USE_CASES = ["all", "general", "workout", "calls", "anc", "commute", "podcasts", "gaming", "audiophile"]


@st.cache_data
def load_scores(min_votes, use_case):
    if use_case and use_case != "all":
        sql = """
        WITH uc_authors AS (
            SELECT DISTINCT m.brand, m.model, c.author
            FROM mentions m JOIN comments c ON c.id = m.comment_id
            WHERE m.use_case = ? AND m.brand IS NOT NULL AND m.model IS NOT NULL
        )
        SELECT v.brand, v.model,
            SUM(CASE WHEN v.sentiment = 'positive' THEN v.weight ELSE 0 END) AS pos,
            SUM(CASE WHEN v.sentiment = 'negative' THEN v.weight ELSE 0 END) AS neg,
            SUM(CASE WHEN v.sentiment = 'neutral'  THEN v.weight ELSE 0 END) AS neu,
            COUNT(DISTINCT v.author) AS users
        FROM votes v
        JOIN uc_authors u ON u.brand = v.brand AND u.model = v.model AND u.author = v.author
        GROUP BY v.brand, v.model
        HAVING (pos + neg) >= ?
        """
        df = con.execute(sql, [use_case, min_votes]).df()
    else:
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
def product_meta(brand, model):
    """price stats + top use case + sound signatures for a single product."""
    row = con.execute(
        """SELECT
              CAST(MEDIAN(price_mentioned) AS INTEGER) AS price_med,
              MIN(price_mentioned) AS price_lo,
              MAX(price_mentioned) AS price_hi
           FROM mentions
           WHERE brand = ? AND model = ? AND price_mentioned BETWEEN 10 AND 1000""",
        [brand, model],
    ).fetchone()
    use_row = con.execute(
        """SELECT use_case FROM mentions
           WHERE brand = ? AND model = ? AND use_case IS NOT NULL AND use_case != 'general'
           GROUP BY use_case ORDER BY COUNT(*) DESC LIMIT 1""",
        [brand, model],
    ).fetchone()
    sig_rows = con.execute(
        """SELECT sound_signature FROM mentions
           WHERE brand = ? AND model = ? AND sound_signature IS NOT NULL""",
        [brand, model],
    ).fetchall()
    sigs = set()
    for (s,) in sig_rows:
        for tag in (s or "").split(","):
            tag = tag.strip().lower()
            if tag and len(tag) < 20:
                sigs.add(tag)
    return {
        "price_med": row[0] if row else None,
        "price_lo": row[1] if row else None,
        "price_hi": row[2] if row else None,
        "top_use_case": use_row[0] if use_row else None,
        "sigs": list(sigs)[:3],
    }


@st.cache_data
def sample_quote(brand, model, sentiment):
    row = con.execute(
        """SELECT c.body, c.score, c.link_id
           FROM mentions m JOIN comments c ON c.id = m.comment_id
           WHERE m.brand = ? AND m.model = ? AND m.sentiment = ?
             AND LENGTH(c.body) BETWEEN 60 AND 500
           ORDER BY c.score DESC LIMIT 1""",
        [brand, model, sentiment],
    ).fetchone()
    return row


def render_tag(text, color="#252b36"):
    return (
        f'<span style="background:{color}; color:#cfcabd; padding:3px 10px; '
        f'border-radius:999px; font-size:12px; margin-right:6px; '
        f'display:inline-block; font-weight:500;">{text}</span>'
    )


with st.sidebar:
    st.markdown("### filters")
    use_case = st.selectbox("use case", USE_CASES, index=0)
    min_votes = st.slider("min votes (pos + neg)", 2, 30, 2)
    show = st.slider("how many to show", 5, 100, 25)

df = load_scores(min_votes, use_case)
if df.empty:
    st.info("no products match this filter. try lowering min votes or switching to 'all'.")
    st.stop()

n_with_filter = "" if use_case == "all" else f" for **{use_case}**"
st.markdown(
    f"<div style='color:#8c8c8c; margin-bottom:24px;'>"
    f"<b>{len(df)}</b> products{n_with_filter}, ranked &middot; showing top <b>{min(show, len(df))}</b>"
    f"</div>",
    unsafe_allow_html=True,
)

top = df.head(show)
for i, row in top.iterrows():
    brand = row["brand"]
    model = row["model"]
    pos = float(row["pos"])
    neg = float(row["neg"])
    neu = float(row["neu"])
    users = int(row["users"])
    score = row["combined"]
    ratio = pos / max(pos + neg, 1)

    meta = product_meta(brand, model)
    pos_q = sample_quote(brand, model, "positive")
    neg_q = sample_quote(brand, model, "negative")

    # build tags row
    tags_html = ""
    if meta["top_use_case"]:
        tags_html += render_tag(f"best for {meta['top_use_case']}", "#2a3346")
    if meta["price_med"]:
        tags_html += render_tag(f"~${int(meta['price_med'])}", "#2d2618")
    for sig in meta["sigs"]:
        tags_html += render_tag(sig)

    # card top: rank | name + meta + tags | score
    st.markdown(
        f'''<div class="rb-card" style="padding:18px 22px;">
        <div style="display:flex; align-items:center; gap:18px;">
            <div style="font-size:36px; font-weight:800; color:#ff7043; min-width:54px; line-height:1; font-variant-numeric:tabular-nums;">{i + 1}</div>
            <div style="flex:1;">
                <div style="font-size:19px; font-weight:700; color:#f1e5d1;">{brand} {model}</div>
                <div style="font-size:13px; color:#8c8c8c; margin-top:2px;">
                    {pos:.1f} positive &middot; {neg:.1f} negative &middot; {ratio:.0%} positive &middot; {users} unique voters
                </div>
                <div style="margin-top:8px;">{tags_html}</div>
            </div>
            <div style="text-align:right; min-width:80px;">
                <div style="font-size:22px; font-weight:700; color:#f1e5d1; font-variant-numeric:tabular-nums;">{score:.3f}</div>
                <div style="font-size:11px; color:#8c8c8c; text-transform:uppercase; letter-spacing:0.5px;">score</div>
            </div>
        </div>''',
        unsafe_allow_html=True,
    )

    # quotes row
    if pos_q or neg_q:
        cols = st.columns(2)
        with cols[0]:
            if pos_q:
                body, sc, link_id = pos_q
                snippet = (body or "")[:240]
                if len(body or "") > 240:
                    snippet += "..."
                st.markdown(
                    f'<div style="background:#0e1117; border-left:3px solid #5cb85c; '
                    f'padding:10px 14px; margin-top:8px; border-radius:0 6px 6px 0; '
                    f'color:#c9c4ba; font-size:13px; line-height:1.55;">{snippet}'
                    f'<div style="font-size:11px; color:#6a7280; margin-top:4px;">'
                    f'{sc} pts &middot; <a href="https://reddit.com/comments/{link_id}" '
                    f'target="_blank" style="color:#6a7280;">view thread</a></div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("no positive quote on file")
        with cols[1]:
            if neg_q:
                body, sc, link_id = neg_q
                snippet = (body or "")[:240]
                if len(body or "") > 240:
                    snippet += "..."
                st.markdown(
                    f'<div style="background:#0e1117; border-left:3px solid #d9534f; '
                    f'padding:10px 14px; margin-top:8px; border-radius:0 6px 6px 0; '
                    f'color:#c9c4ba; font-size:13px; line-height:1.55;">{snippet}'
                    f'<div style="font-size:11px; color:#6a7280; margin-top:4px;">'
                    f'{sc} pts &middot; <a href="https://reddit.com/comments/{link_id}" '
                    f'target="_blank" style="color:#6a7280;">view thread</a></div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("no negative quote on file")

    # close the card
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
