"""extract product mentions from comments using groq + llama 3.1."""
import argparse
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db import connect
from llm.groq_extract import make_client, load_prompt, extract

MIN_COMMENT_LEN = 80

MENTION_FIELDS = (
    "mention_id", "comment_id", "brand", "model",
    "form_factor", "connection", "price_mentioned", "use_case",
    "sound_signature", "sentiment", "one_line_reason", "extracted_at",
)


def _read_key():
    p = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
    return re.search(r'GROQ_API_KEY\s*=\s*"([^"]+)"', p.read_text()).group(1)


def _row_from_extraction(comment_id, item, now):
    return (
        f"{comment_id}_{uuid.uuid4().hex[:8]}",
        comment_id,
        item.get("brand"),
        item.get("model"),
        item.get("form_factor"),
        item.get("connection"),
        item.get("price_mentioned"),
        item.get("use_case"),
        item.get("sound_signature"),
        item.get("sentiment"),
        item.get("one_line_reason"),
        now,
    )


def get_pending(con, limit=None):
    """comments not yet extracted, with parent post title for context."""
    sql = """
        SELECT c.id, c.body, p.title
        FROM comments c
        JOIN posts p ON p.id = c.link_id
        WHERE LENGTH(c.body) >= ?
          AND c.author NOT IN ('AutoModerator', '[deleted]')
          AND c.body NOT IN ('[deleted]', '[removed]')
          AND NOT EXISTS (
              SELECT 1 FROM pull_checkpoints cp
              WHERE cp.source = 'extract:' || c.id AND cp.finished
          )
    """
    params = [MIN_COMMENT_LEN]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return con.execute(sql, params).fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    con = connect()
    client = make_client(_read_key())
    prompt = load_prompt()

    pending = get_pending(con, args.limit)
    print(f"{len(pending)} comments pending extraction")
    if args.dry_run or not pending:
        return

    placeholders = ",".join("?" * len(MENTION_FIELDS))
    insert_sql = f"INSERT INTO mentions ({','.join(MENTION_FIELDS)}) VALUES ({placeholders})"

    n_with_mentions = 0
    n_failed = 0
    start = time.time()
    for i, (cid, body, title) in enumerate(pending):
        try:
            mentions = extract(client, prompt, title, body)
        except Exception as e:
            print(f"  failed on {cid}: {e}")
            n_failed += 1
            continue
        now = int(time.time())
        rows = [_row_from_extraction(cid, m, now) for m in mentions]
        if rows:
            con.executemany(insert_sql, rows)
            n_with_mentions += 1
        # checkpoint regardless: marks the comment as processed
        con.execute(
            "INSERT INTO pull_checkpoints (source, finished) VALUES (?, TRUE) "
            "ON CONFLICT (source) DO UPDATE SET finished = TRUE",
            [f"extract:{cid}"],
        )
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed else 0
            eta = (len(pending) - (i + 1)) / rate / 60 if rate else 0
            print(f"  ...{i+1}/{len(pending)}  {n_with_mentions} with mentions  {rate:.1f}/s  eta {eta:.1f}m")

    elapsed = time.time() - start
    print(f"\ndone. {n_with_mentions}/{len(pending)} comments had mentions, {n_failed} failed")
    print(f"total mentions in db: {con.execute('SELECT COUNT(*) FROM mentions').fetchone()[0]}")
    print(f"elapsed: {elapsed / 60:.1f} min")
    con.close()


if __name__ == "__main__":
    main()
