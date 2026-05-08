import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.db import connect
from lib.scoring import combined_score, normalize_log_volume, wilson_lower
from lib.ui import apply_theme

st.set_page_config(page_title="redditrecbuds", layout="wide", initial_sidebar_state="collapsed")
apply_theme()

con = connect()


@st.cache_data
def stats():
    n_posts = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    n_comments = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    n_mentions = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
    n_users = con.execute("SELECT COUNT(DISTINCT author) FROM votes").fetchone()[0]
    n_products = con.execute(
        "SELECT COUNT(*) FROM (SELECT brand, model FROM votes GROUP BY brand, model HAVING SUM(weight) >= 2)"
    ).fetchone()[0]
    return n_posts, n_comments, n_mentions, n_users, n_products


@st.cache_data
def top_picks(n=3):
    df = con.execute(
        """SELECT brand, model,
              SUM(CASE WHEN sentiment = 'positive' THEN weight ELSE 0 END) AS pos,
              SUM(CASE WHEN sentiment = 'negative' THEN weight ELSE 0 END) AS neg,
              COUNT(DISTINCT author) AS users
           FROM votes GROUP BY brand, model HAVING (pos + neg) >= 2"""
    ).df()
    if df.empty:
        return df
    df["wilson"] = df.apply(lambda r: wilson_lower(r["pos"], r["neg"]), axis=1)
    df["log_vol"] = normalize_log_volume(df["pos"].tolist())
    df["combined"] = [combined_score(v, w) for v, w in zip(df["log_vol"], df["wilson"])]
    return df.sort_values("combined", ascending=False).head(n).reset_index(drop=True)


@st.cache_data
def quote_for(brand, model, sentiment="positive"):
    return con.execute(
        """SELECT c.body, c.score, c.link_id FROM mentions m
           JOIN comments c ON c.id = m.comment_id
           WHERE m.brand = ? AND m.model = ? AND m.sentiment = ?
             AND LENGTH(c.body) BETWEEN 60 AND 400
           ORDER BY c.score DESC LIMIT 1""",
        [brand, model, sentiment],
    ).fetchone()


@st.cache_data
def best_in(use_case):
    """top product score-wise that's been associated with a given use case."""
    row = con.execute(
        """WITH uc_authors AS (
              SELECT DISTINCT m.brand, m.model, c.author FROM mentions m
              JOIN comments c ON c.id = m.comment_id
              WHERE m.use_case = ? AND m.brand IS NOT NULL AND m.model IS NOT NULL
           ),
           agg AS (
              SELECT v.brand, v.model,
                  SUM(CASE WHEN v.sentiment='positive' THEN v.weight ELSE 0 END) AS pos,
                  SUM(CASE WHEN v.sentiment='negative' THEN v.weight ELSE 0 END) AS neg,
                  COUNT(DISTINCT v.author) AS users
              FROM votes v JOIN uc_authors u
                ON u.brand=v.brand AND u.model=v.model AND u.author=v.author
              GROUP BY v.brand, v.model HAVING (pos+neg) >= 2
           )
           SELECT brand, model, users FROM agg
           ORDER BY (pos / NULLIF(pos+neg,0)) * LN(pos+1) DESC LIMIT 1""",
        [use_case],
    ).fetchone()
    return row


n_posts, n_comments, n_mentions, n_users, n_products = stats()

# hero
st.markdown(
    "<div style='text-align:center; padding-top:24px;'>"
    "<div style='font-size:14px; color:#8c8c8c; letter-spacing:1.5px; text-transform:uppercase; font-weight:600;'>"
    "wireless earbud rankings, distilled from reddit"
    "</div>"
    "<div style='font-size:64px; font-weight:800; letter-spacing:-2px; line-height:1.05; margin:8px 0 12px 0;'>"
    "redditrecbuds"
    "</div>"
    "<div style='color:#8c8c8c; font-size:17px; max-width:560px; margin:0 auto 24px auto; line-height:1.5;'>"
    f"What r/Earbuds actually recommends, ranked by upvote-weighted Wilson scores. "
    f"<b>{n_users:,}</b> unique voters, <b>{n_products:,}</b> products, May 2025-May 2026."
    "</div></div>",
    unsafe_allow_html=True,
)

# CTA row
st.markdown(
    "<div style='text-align:center; margin-bottom:48px;'>"
    "<a href='/rankings' style='background:#ff7043; color:#fff; padding:13px 32px; border-radius:10px; "
    "text-decoration:none; font-weight:600; font-size:15px; margin-right:10px; display:inline-block;'>"
    "see the rankings &rarr;</a>"
    "<a href='/methodology' style='background:transparent; border:1px solid #2c3340; color:#cfcabd; "
    "padding:12px 28px; border-radius:10px; text-decoration:none; font-weight:500; font-size:15px; display:inline-block;'>"
    "how it works</a></div>",
    unsafe_allow_html=True,
)

# top 3 picks
picks = top_picks(3)
if not picks.empty:
    st.markdown(
        "<div style='font-size:13px; font-weight:600; color:#8c8c8c; text-transform:uppercase; "
        "letter-spacing:1px; margin-bottom:12px;'>top picks right now</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(min(3, len(picks)))
    medals = ["1st", "2nd", "3rd"]
    for i, (_, row) in enumerate(picks.iterrows()):
        with cols[i]:
            brand = row["brand"]
            model = row["model"]
            users = int(row["users"])
            ratio = row["pos"] / max(row["pos"] + row["neg"], 1)
            q = quote_for(brand, model, "positive")
            quote_html = ""
            if q:
                body, sc, link_id = q
                snippet = (body or "")[:160]
                if len(body or "") > 160:
                    snippet += "..."
                quote_html = (
                    f'<div style="font-size:13px; color:#a8a39a; line-height:1.5; '
                    f'margin-top:12px; font-style:italic;">"{snippet}"</div>'
                    f'<div style="font-size:11px; color:#6a7280; margin-top:4px;">'
                    f'<a href="https://reddit.com/comments/{link_id}" target="_blank" '
                    f'style="color:#6a7280;">{sc} pts &rarr; thread</a></div>'
                )
            st.markdown(
                f'<div style="background:#151a22; border:1px solid #232a36; border-radius:14px; '
                f'padding:24px; height:100%; min-height:240px;">'
                f'<div style="font-size:11px; color:#ff7043; font-weight:700; '
                f'letter-spacing:1px; text-transform:uppercase;">{medals[i]} place</div>'
                f'<div style="font-size:20px; font-weight:700; color:#f1e5d1; margin-top:6px;">'
                f'{brand} {model}</div>'
                f'<div style="font-size:13px; color:#8c8c8c; margin-top:4px;">'
                f'{users} voters &middot; {ratio:.0%} positive</div>'
                f'{quote_html}</div>',
                unsafe_allow_html=True,
            )

# best-for-X quick links
st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)
st.markdown(
    "<div style='font-size:13px; font-weight:600; color:#8c8c8c; text-transform:uppercase; "
    "letter-spacing:1px; margin-bottom:12px;'>best for...</div>",
    unsafe_allow_html=True,
)

use_cases_to_show = ["workout", "calls", "anc", "commute", "podcasts", "audiophile"]
chip_html_parts = ['<div style="display:flex; flex-wrap:wrap; gap:10px;">']
for uc in use_cases_to_show:
    pick = best_in(uc)
    if pick:
        b, m, u = pick
        chip_html_parts.append(
            f'<a href="/rankings?use_case={uc}" style="background:#1a1f2b; '
            f'border:1px solid #2c3340; border-radius:10px; padding:12px 16px; '
            f'text-decoration:none; min-width:200px; flex:1; display:block;">'
            f'<div style="font-size:11px; color:#ff7043; text-transform:uppercase; '
            f'letter-spacing:0.8px; font-weight:600;">{uc}</div>'
            f'<div style="font-size:15px; color:#f1e5d1; font-weight:600; margin-top:4px;">'
            f'{b} {m}</div>'
            f'<div style="font-size:11px; color:#6a7280; margin-top:2px;">{u} voters</div></a>'
        )
chip_html_parts.append('</div>')
st.markdown("".join(chip_html_parts), unsafe_allow_html=True)

# stats row at bottom
st.markdown("<div style='height:64px;'></div>", unsafe_allow_html=True)
st.markdown(
    "<div style='border-top:1px solid #1f2530; padding-top:24px; "
    "display:flex; gap:32px; flex-wrap:wrap; color:#8c8c8c; font-size:13px;'>"
    f"<div><b style='color:#cfcabd;'>{n_posts:,}</b> posts ingested</div>"
    f"<div><b style='color:#cfcabd;'>{n_comments:,}</b> comments analyzed</div>"
    f"<div><b style='color:#cfcabd;'>{n_mentions:,}</b> mentions extracted</div>"
    f"<div style='margin-left:auto;'>"
    f"<a href='https://github.com/Db2203/redditrecbuds' style='color:#8c8c8c;'>github &rarr;</a>"
    f"</div></div>",
    unsafe_allow_html=True,
)
