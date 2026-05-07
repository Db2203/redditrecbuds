"""shared theme + small ui helpers.

most of the look comes from one block of css injected per page (apply_theme()).
covers the streamlit chrome that screams 'default streamlit', the font swap,
and a few shared classes used across pages (rank cards, hero, soft cards).
"""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* hide streamlit chrome */
header[data-testid="stHeader"] { display: none; }
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
.stDeployButton { display: none; }
[data-testid="stToolbar"] { display: none; }

/* font */
html, body, [class*="css"], .stApp, .stMarkdown, .stText, .stCaption, h1, h2, h3, h4, h5, h6, p, div, span {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
code, pre, .stCodeBlock, .stCode {
    font-family: 'JetBrains Mono', 'Courier New', monospace !important;
}

/* tighter top padding */
.main .block-container, [data-testid="stMainBlockContainer"] {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 1100px;
}

/* hero */
.rb-hero-title {
    font-size: 52px;
    font-weight: 800;
    text-align: center;
    letter-spacing: -1.5px;
    margin: 8px 0 4px 0;
    line-height: 1.05;
}
.rb-hero-sub {
    text-align: center;
    color: #8c8c8c;
    font-size: 17px;
    max-width: 640px;
    margin: 0 auto 36px auto;
    line-height: 1.5;
}

/* metric pill row */
.rb-metric-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: center;
    margin: 0 0 32px 0;
}
.rb-metric {
    background: #151a22;
    border: 1px solid #232a36;
    border-radius: 12px;
    padding: 16px 20px;
    flex: 1 1 180px;
    min-width: 160px;
}
.rb-metric-num {
    font-size: 28px;
    font-weight: 700;
    color: #f1e5d1;
    line-height: 1.1;
}
.rb-metric-label {
    font-size: 12px;
    color: #8c8c8c;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 4px;
}

/* ranking card */
.rb-card {
    background: #151a22;
    border: 1px solid #232a36;
    border-radius: 14px;
    padding: 20px 24px;
    margin: 10px 0;
    transition: border-color 0.15s ease, transform 0.15s ease;
}
.rb-card:hover {
    border-color: #ff7043;
}
.rb-rank-row {
    display: flex;
    align-items: center;
    gap: 20px;
}
.rb-rank-num {
    font-size: 40px;
    font-weight: 800;
    color: #ff7043;
    min-width: 60px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}
.rb-product {
    font-size: 20px;
    font-weight: 700;
    color: #f1e5d1;
    margin-bottom: 2px;
}
.rb-meta {
    font-size: 13px;
    color: #8c8c8c;
}
.rb-score {
    margin-left: auto;
    text-align: right;
}
.rb-score-num {
    font-size: 22px;
    font-weight: 700;
    color: #f1e5d1;
    font-variant-numeric: tabular-nums;
}
.rb-score-label {
    font-size: 11px;
    color: #8c8c8c;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* quote block */
.rb-quote {
    background: #0e1117;
    border-left: 3px solid #ff7043;
    padding: 12px 16px;
    margin: 8px 0;
    border-radius: 0 8px 8px 0;
    color: #c9c4ba;
    font-size: 14px;
    line-height: 1.5;
}
.rb-quote.neg {
    border-left-color: #d9534f;
}
.rb-quote-meta {
    font-size: 12px;
    color: #6a7280;
    margin-top: 4px;
}
.rb-quote-meta a {
    color: #6a7280;
    text-decoration: none;
}
.rb-quote-meta a:hover {
    color: #ff7043;
}

/* soft section header */
.rb-section {
    font-size: 13px;
    font-weight: 600;
    color: #8c8c8c;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 24px 0 8px 0;
}
</style>
"""


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title, subtitle):
    st.markdown(
        f'<div class="rb-hero-title">{title}</div>'
        f'<div class="rb-hero-sub">{subtitle}</div>',
        unsafe_allow_html=True,
    )


def metric_row(metrics):
    """metrics: list of (label, value) tuples."""
    parts = ['<div class="rb-metric-row">']
    for label, value in metrics:
        parts.append(
            f'<div class="rb-metric"><div class="rb-metric-num">{value}</div>'
            f'<div class="rb-metric-label">{label}</div></div>'
        )
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def rank_card(rank, brand, model, pos, neg, neu, users, score):
    ratio = pos / max(pos + neg, 1)
    st.markdown(
        f'''<div class="rb-card"><div class="rb-rank-row">
        <div class="rb-rank-num">{rank}</div>
        <div>
            <div class="rb-product">{brand} {model}</div>
            <div class="rb-meta">{pos:.1f} positive · {neg:.1f} negative · {ratio:.0%} positive · {int(users)} unique voters</div>
        </div>
        <div class="rb-score">
            <div class="rb-score-num">{score:.3f}</div>
            <div class="rb-score-label">score</div>
        </div></div></div>''',
        unsafe_allow_html=True,
    )


def quote(body, score, link_id, sentiment="positive"):
    cls = "rb-quote neg" if sentiment == "negative" else "rb-quote"
    snippet = (body or "")[:300]
    if len(body or "") > 300:
        snippet += "..."
    st.markdown(
        f'<div class="{cls}">{snippet}'
        f'<div class="rb-quote-meta">{score} pts · '
        f'<a href="https://reddit.com/comments/{link_id}" target="_blank">view thread</a></div></div>',
        unsafe_allow_html=True,
    )


def section(label):
    st.markdown(f'<div class="rb-section">{label}</div>', unsafe_allow_html=True)
