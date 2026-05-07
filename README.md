# redditrecbuds

a wireless-earbud recommender built from r/Earbuds comments. wilson-lower-bound ranking, sentiment extraction, per-product detail views.

**[live →](https://redditrecbuds.streamlit.app/)**

## how it works

1. pull posts and comments from a few audio subs via [arctic shift](https://arctic-shift.photon-reddit.com/) (reddit closed self-service api access in late 2025)
2. extract product mentions and sentiment with llama 3.1 / gemini 2.5 flash
3. dedup at user level, spread imprecise references across known models
4. rank with `0.75 * normalized_log_volume + 0.25 * wilson_lower_bound`

full breakdown in the methodology page of the app.

## stack

python, duckdb, streamlit, plotly, groq, gemini, arctic-shift. hosted on streamlit community cloud.

## running it locally

```bash
git clone https://github.com/Db2203/redditrecbuds
cd redditrecbuds
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# add your free groq key, and a gemini_api_key.txt with one key per line for parallel extraction

python ingest/arctic_pull.py --mode posts --months 12
python ingest/arctic_pull.py --mode comments --comments-subreddit Earbuds --min-score 2 --min-num-comments 5 --max-posts 1500
python ingest/extract.py --provider gemini --subreddit Earbuds --limit 5000
python ingest/score.py
streamlit run app.py
```

extraction is checkpointed per-comment so you can ctrl-c and resume.

## credits

- [arctic shift](https://arctic-shift.photon-reddit.com/) for the data
- [groq](https://groq.com), [google ai studio](https://aistudio.google.com), and [cerebras](https://cerebras.ai) for free-tier llm api access
