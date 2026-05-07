import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.db import connect
from lib.ui import apply_theme

st.set_page_config(page_title="methodology", layout="wide", initial_sidebar_state="collapsed")
apply_theme()
st.markdown(
    "<div style='font-size:36px; font-weight:800; letter-spacing:-1px;'>methodology</div>"
    "<div style='color:#8c8c8c; font-size:15px; margin-bottom:24px;'>"
    "how the rankings actually work, and what they don't tell you."
    "</div>",
    unsafe_allow_html=True,
)

con = connect()

n_posts = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
n_comments = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
try:
    n_mentions = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
    n_with_pos = con.execute(
        "SELECT COUNT(*) FROM mentions WHERE sentiment='positive'"
    ).fetchone()[0]
    n_users = con.execute("SELECT COUNT(DISTINCT author) FROM votes").fetchone()[0]
    n_votes = con.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
except Exception:
    n_mentions = n_with_pos = n_users = n_votes = 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("posts", f"{n_posts:,}")
c2.metric("comments", f"{n_comments:,}")
c3.metric("mentions", f"{n_mentions:,}")
c4.metric("unique users", f"{n_users:,}")

st.divider()

st.markdown(
    """
### what i did

1. **pulled** posts and comments from r/headphones, r/HeadphoneAdvice, r/Earbuds,
   and r/budgetaudiophile via the [arctic shift](https://arctic-shift.photon-reddit.com/)
   archive. originally i wanted PRAW + the official reddit api, but reddit closed
   self-service api access in late 2025 and personal-project applications get rejected,
   so i routed around it. arctic shift is an open archive that mirrors public reddit data.

2. **filtered** to comments long enough to actually contain a recommendation
   (≥ 80 chars), skipping AutoModerator and `[deleted]` / `[removed]` content.

3. **extracted** product mentions with llama 3.1 8b (via groq's free tier).
   the model returns, per comment, a json list of every wireless earbud mentioned -
   brand, specific model, sentiment (positive / neutral / negative), price if mentioned,
   use case, sound-signature words, and a one-line reason.
   the prompt has three few-shot examples and is strict about ignoring over-ear
   headphones, IEMs, and wired earbuds.

4. **deduped** votes per user. one user mentioning the same model 5 times in
   a thread shouldn't dominate that model's score, so per `(author, brand, model)`
   i keep the user's majority sentiment as a single vote.

5. **spread imprecise references**. when someone says "Galaxy Buds" with no version,
   i can't drop the data - but i shouldn't pin it on one specific buds model either.
   i spread that user's vote across all known galaxy buds models, weighted by each
   model's overall mention count (more popular = more likely the one being referred to).

6. **scored**. ranking is a weighted combination of two signals:

   - **wilson lower bound at 95% confidence** - the same statistic reddit's "best"
     comment sort uses. punishes products with a great ratio but a tiny sample.
     a product with 1 positive / 0 negative votes scores ~0.21, not 1.00.

   - **log-normalized positive volume** - sheer count of positive votes,
     log-transformed and normalized so the most-mentioned product is 1.0.

   final score = `0.75 * log_volume + 0.25 * wilson`. the 75:25 weighting reflects
   that sheer volume of approval is more telling than a few isolated rave reviews -
   a product mentioned positively 100 times by 80 different users carries more weight
   than one with a perfect ratio across 3 mentions.

### the wilson formula

```
n = pos + neg
p = pos / n
z = 1.96   # 95% confidence
wilson_lower = ( p + z^2/(2n) - z*sqrt(p(1-p)/n + z^2/(4n^2)) ) / (1 + z^2/n)
```

implemented in `lib/scoring.py`.

### what this dataset doesn't tell you

a few honest limitations to be aware of when reading the rankings:

- **reddit demographics skew western, english-speaking, and tech-leaning.**
  brands hot on r/HeadphoneAdvice may not reflect what's popular in (say) japan or india.
- **vocal users dominate.** even with per-user dedup, the people who post on r/headphones
  are not a representative sample of all earbud buyers.
- **recency bias.** newer products get more current attention; older models that
  were popular 18 months ago may show up less frequently. the time-window toggle
  (planned, not yet wired up) is meant to mitigate this.
- **model-name dedup is imperfect.** "Sony WF-1000XM5" and "Sony XM5" and "Sony 1000XM5"
  may sometimes get stored as separate rows. i did some manual cleanup but mistakes remain.
- **sentiment is llm-judged**, so it inherits whatever biases llama 3.1 has.
  occasional misreads are baked in.

### what's in here that's a bit different

- **wilson lower bound** for the ratio component (more rigorous than naive ratio for small-n products)
- the **per-product detail page** with extracted pros / cons, price distribution,
  mentions over time, and co-mentioned products
- the **side-by-side compare** view
- this transparency page itself

### what i'd add with more time

- per-month sentiment-over-time charts so you can see if a product's reputation
  is rising or falling
- price-tier and use-case filters on the rankings page
- embedding-based "earbuds like this one" recommendations
- generalize beyond wireless earbuds to over-ears and IEMs, with the same pipeline
"""
)
