"""extract product mentions from comments using groq + llama 3.1.

uses a thread pool because groq calls are i/o bound. duckdb writes happen
on the main thread (the connection isn't thread-safe for concurrent writes).
"""
import argparse
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db import connect
from lib.secrets import get as get_secret
from llm.groq_extract import make_client, load_prompt, extract

MIN_COMMENT_LEN = 80

MENTION_FIELDS = (
    "mention_id", "comment_id", "brand", "model",
    "form_factor", "connection", "price_mentioned", "use_case",
    "sound_signature", "sentiment", "one_line_reason", "extracted_at",
)


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
        ORDER BY LENGTH(c.body) DESC
    """
    params = [MIN_COMMENT_LEN]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return con.execute(sql, params).fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    con = connect()
    client = make_client(get_secret("GROQ_API_KEY"))
    prompt = load_prompt()

    pending = get_pending(con, args.limit)
    print(f"{len(pending)} comments pending; using {args.workers} workers")
    if args.dry_run or not pending:
        return

    placeholders = ",".join("?" * len(MENTION_FIELDS))
    insert_sql = f"INSERT INTO mentions ({','.join(MENTION_FIELDS)}) VALUES ({placeholders})"
    cp_sql = (
        "INSERT INTO pull_checkpoints (source, finished) VALUES (?, TRUE) "
        "ON CONFLICT (source) DO UPDATE SET finished = TRUE"
    )

    def task(item):
        cid, body, title = item
        try:
            return cid, extract(client, prompt, title, body), None
        except Exception as e:
            return cid, [], str(e)

    n_with_mentions = 0
    n_failed = 0
    n_done = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(task, item) for item in pending]
        for fut in as_completed(futures):
            cid, mentions, err = fut.result()
            n_done += 1
            if err:
                n_failed += 1
            now = int(time.time())
            if mentions:
                rows = [_row_from_extraction(cid, m, now) for m in mentions]
                con.executemany(insert_sql, rows)
                n_with_mentions += 1
            con.execute(cp_sql, [f"extract:{cid}"])
            if n_done % 50 == 0:
                elapsed = time.time() - start
                rate = n_done / elapsed if elapsed else 0
                eta = (len(pending) - n_done) / rate / 60 if rate else 0
                print(f"  ...{n_done}/{len(pending)}  {n_with_mentions} with mentions  {rate:.1f}/s  eta {eta:.1f}m")

    elapsed = time.time() - start
    print(f"\ndone. {n_with_mentions}/{n_done} comments had mentions, {n_failed} failed")
    print(f"total mentions in db: {con.execute('SELECT COUNT(*) FROM mentions').fetchone()[0]}")
    print(f"elapsed: {elapsed / 60:.1f} min")
    con.close()


if __name__ == "__main__":
    main()
