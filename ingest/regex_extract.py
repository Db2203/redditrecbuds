"""regex-based extraction. uses the existing (brand, model) dictionary from
the mentions table, scans every r/Earbuds comment for matches, attaches a
keyword-based sentiment to each match.

mentions inserted by this script are tagged source='regex' so the methodology
page can be transparent about the mix.
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db import connect
from lib.regex_match import build_product_patterns, find_products, score_sentiment

MIN_COMMENT_LEN = 60
MIN_PRODUCT_MENTIONS = 2  # don't generate patterns for products with 1 mention


def ensure_source_column(con):
    """add a `source` column to mentions if missing, default existing rows to llm."""
    cols = [r[0] for r in con.execute("DESCRIBE mentions").fetchall()]
    if "source" not in cols:
        print("adding source column to mentions...")
        con.execute("ALTER TABLE mentions ADD COLUMN source TEXT DEFAULT 'llm'")
        con.execute("UPDATE mentions SET source = 'llm' WHERE source IS NULL")


def load_product_dictionary(con, min_mentions=MIN_PRODUCT_MENTIONS):
    """Returns a deduped dictionary of (brand, model) — one row per unique
    NORMALIZED model (lowercased, non-alphanumeric stripped). Takes the
    brand with most LLM mentions.

    Drops LLM hallucinations like 'Sony AZ100' / 'Anker AZ100' (real is
    Technics AZ100) and collapses 'Earfun Air Pro 4' vs 'Earfun Air Pro 4+'
    which have identical regex patterns.
    """
    import re as _re
    raw = con.execute(
        """SELECT brand, model, COUNT(*) AS n
           FROM mentions
           WHERE brand IS NOT NULL AND model IS NOT NULL
           GROUP BY brand, model""",
    ).fetchall()
    # group by normalized model
    by_norm = {}
    for brand, model, n in raw:
        norm = _re.sub(r"[^a-z0-9]", "", model.lower())
        if not norm or len(norm) < 2:
            continue
        if norm not in by_norm or by_norm[norm][2] < n:
            by_norm[norm] = (brand, model, n)
    out = [(b, m) for (b, m, n) in by_norm.values() if n >= min_mentions]
    return out


def get_pending_comments(con, subreddit="Earbuds", limit=None):
    sql = """
        SELECT c.id, c.body
        FROM comments c
        WHERE c.subreddit = ?
          AND LENGTH(c.body) >= ?
          AND c.author NOT IN ('AutoModerator', '[deleted]')
          AND c.body NOT IN ('[deleted]', '[removed]')
          AND NOT EXISTS (
              SELECT 1 FROM pull_checkpoints cp
              WHERE cp.source = 'regex:' || c.id AND cp.finished
          )
    """
    params = [subreddit, MIN_COMMENT_LEN]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return con.execute(sql, params).fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subreddit", default="Earbuds")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-product-mentions", type=int, default=MIN_PRODUCT_MENTIONS)
    args = parser.parse_args()

    con = connect()
    ensure_source_column(con)

    products = load_product_dictionary(con, args.min_product_mentions)
    print(f"loaded {len(products)} (brand, model) products from existing mentions")

    patterns = build_product_patterns(products)
    print(f"generated {len(patterns)} regex patterns")

    pending = get_pending_comments(con, args.subreddit, args.limit)
    print(f"{len(pending)} r/{args.subreddit} comments to scan")
    if not pending:
        return

    insert_sql = (
        "INSERT INTO mentions (mention_id, comment_id, brand, model, sentiment, "
        "extracted_at, source) VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    cp_sql = (
        "INSERT INTO pull_checkpoints (source, finished) VALUES (?, TRUE) "
        "ON CONFLICT (source) DO UPDATE SET finished = TRUE"
    )

    n_with = 0
    n_mentions = 0
    start = time.time()
    for i, (cid, body) in enumerate(pending):
        matches = find_products(body, patterns)
        now = int(time.time())
        if matches:
            n_with += 1
            for brand, model, ms, me in matches:
                sentiment = score_sentiment(body, ms, me)
                mention_id = f"{cid}_rgx_{uuid.uuid4().hex[:8]}"
                con.execute(
                    insert_sql,
                    [mention_id, cid, brand, model, sentiment, now, "regex"],
                )
                n_mentions += 1
        con.execute(cp_sql, [f"regex:{cid}"])
        if (i + 1) % 500 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed else 0
            print(f"  ...{i+1}/{len(pending)}  {n_with} with matches  {n_mentions} mentions  {rate:.0f}/s")

    elapsed = time.time() - start
    print(f"\ndone. {n_with}/{len(pending)} comments matched, {n_mentions} mentions added")
    print(f"elapsed: {elapsed:.1f}s")
    print(f"total mentions in db: {con.execute('SELECT COUNT(*) FROM mentions').fetchone()[0]}")
    print(f"  by source: {dict(con.execute('SELECT source, COUNT(*) FROM mentions GROUP BY source').fetchall())}")
    con.close()


if __name__ == "__main__":
    main()
