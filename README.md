# redditrecbuds

a wireless-earbud recommender built from reddit comments. the goal: a "what should i actually buy" tool, backed by what real people on r/headphones, r/HeadphoneAdvice, r/Earbuds, and r/budgetaudiophile have said over the last year. inspired by [redditrecs.com](https://redditrecs.com) with a more rigorous ranking method and a few extra views.

**[live](#)** | **[methodology](pages/4_methodology.py)**

## what's inside

- **rankings** - top wireless earbuds, ranked by `0.75 * log_volume + 0.25 * wilson_lower_bound`. wilson is the same statistic reddit's "best" comment sort uses; it punishes products with great ratios but tiny samples.
- **product detail** - pick a product: mentions over time, sentiment breakdown, top quoted reasons people like and don't, prices people mentioned, related products via co-mention.
- **compare** - head-to-head between two earbuds.
- **methodology** - full write-up of how rankings work and what the data doesn't tell you.

## how it works

```
arctic shift archive  ->  duckdb  ->  llama 3.1 (groq)  ->  per-user dedup  ->  wilson + log-volume score
```

1. pull posts and comments via [arctic shift](https://arctic-shift.photon-reddit.com/). originally i wanted PRAW + the official reddit api, but reddit closed self-service api access in late 2025 and most personal-project applications get rejected. arctic shift is an open archive that mirrors public reddit and is the simplest way to do this kind of work in 2026.
2. filter posts to ones that look like buying advice (score and comment-count thresholds).
3. extract product mentions, sentiment, price, and use-case from each comment using llama 3.1 8b on groq's free tier. the prompt is strict about only counting wireless earbuds, not over-ears or IEMs.
4. dedup at user level (one user mentioning a model 5 times = one vote, not five).
5. spread imprecise references ("Galaxy Buds" with no version) across known models of that brand, weighted by overall mention count.
6. score with `0.75 * normalized_log_volume + 0.25 * wilson_lower_bound` and rank.

## the numbers

| | |
|---|---|
| posts ingested | _filled in after first full run_ |
| comments analyzed | _filled in after first full run_ |
| product mentions extracted | _filled in after first full run_ |
| unique users contributing votes | _filled in after first full run_ |
| wireless earbud models ranked | _filled in after first full run_ |

## stack

- **arctic shift** - public reddit archive (no auth)
- **duckdb** - embedded analytical sql, single-file db
- **groq + llama 3.1 8b** - extraction and sentiment, free tier
- **streamlit + plotly** - the dashboard
- **streamlit community cloud** - hosting

everything is free with no credit card.

## running it locally

```bash
git clone https://github.com/Db2203/redditrecbuds
cd redditrecbuds
python -m venv .venv && .venv/Scripts/activate    # or source .venv/bin/activate on mac/linux
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# put your free groq api key in .streamlit/secrets.toml

python ingest/arctic_pull.py --mode posts --months 12
python ingest/arctic_pull.py --mode comments --min-score 5 --min-num-comments 15
python ingest/extract.py
python ingest/score.py

streamlit run app.py
```

ingest takes ~45-90 min depending on how loaded arctic shift is that day. checkpoints mean you can ctrl-c and resume.

## what this doesn't tell you

a few honest limitations:

- **reddit demographics skew western, english-speaking, and tech-leaning.** what's hot on r/HeadphoneAdvice is not what's popular globally.
- **vocal users dominate** even after per-user dedup.
- **recency bias** - newer products attract more attention; older models that were big 18 months ago show up less.
- **model-name dedup is imperfect** - "Sony WF-1000XM5" / "Sony XM5" / "Sony 1000XM5" sometimes end up as separate rows. some manual cleanup, but mistakes remain. there's a `# TODO` for this.
- **sentiment is llm-judged**, so it inherits whatever biases llama 3.1 has.

the methodology page in the app says all of this too, prominently.

## what i'd build next

- per-month sentiment trends per product (catches "this used to be great, now people complain about firmware")
- price-tier and use-case filters on the rankings page
- embedding-based "earbuds like this one"
- generalize the same pipeline to over-ear headphones and IEMs

## a couple of things i learned the hard way

- arctic shift's backend returns 422 with "Timeout. Maybe slow down a bit" - that's a *backend query timeout*, not a rate-limit. backing off harder than you'd expect actually works. `sort=asc` on a wide time range trips it; `before=` walking backward is reliable.
- llama 3.1 8b's structured-output mode (`response_format={"type": "json_object"}`) is solid for this kind of extraction with a few-shot prompt. it does occasionally classify a wired iem as a wireless earbud - the methodology page is honest about this.

## credits

- [redditrecs.com](https://redditrecs.com) for the methodology and the inspiration
- [arctic shift](https://arctic-shift.photon-reddit.com/) for keeping reddit data accessible
- [groq](https://groq.com) for the genuinely-usable free-tier llm api
