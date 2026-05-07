import duckdb
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data.duckdb"

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    subreddit TEXT,
    author TEXT,
    title TEXT,
    selftext TEXT,
    url TEXT,
    score INTEGER,
    num_comments INTEGER,
    created_utc BIGINT,
    retrieved_on BIGINT,
    link_flair_text TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    link_id TEXT,
    parent_id TEXT,
    subreddit TEXT,
    author TEXT,
    body TEXT,
    score INTEGER,
    created_utc BIGINT,
    retrieved_on BIGINT
);

CREATE TABLE IF NOT EXISTS pull_checkpoints (
    source TEXT PRIMARY KEY,
    last_after BIGINT,
    finished BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mentions (
    mention_id TEXT PRIMARY KEY,
    comment_id TEXT,
    brand TEXT,
    model TEXT,
    form_factor TEXT,
    connection TEXT,
    price_mentioned INTEGER,
    use_case TEXT,
    sound_signature TEXT,
    sentiment TEXT,
    one_line_reason TEXT,
    extracted_at BIGINT
);
"""


def connect(path=DB_PATH):
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con
