"""extract product mentions from comments using groq or gemini.

groq path: shared client + thread pool (groq sdk is thread-safe, single key).
gemini path: one worker thread pinned to one api key, paced at 4.5s/call to
respect the per-key 15 rpm cap. with N keys we get ~N/4 calls/sec total.
"""
import argparse
import queue
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db import connect
from lib.secrets import get as get_secret

MIN_COMMENT_LEN = 80
GEMINI_PER_KEY_INTERVAL = 4.5    # gemini: 15 rpm per key + buffer
CEREBRAS_PER_KEY_INTERVAL = 2.1  # cerebras: 30 rpm per key + buffer
GROQ_PACED_INTERVAL = 7.5        # groq: 6k tpm / ~800 tokens/call ≈ 8 calls/min

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


def _validate_keys(provider, keys):
    """ping each key with a tiny prompt; return only the ones that respond 200.
    retries network errors up to 3 times so transient timeouts don't drop good keys.
    only implemented for gemini (multi-key); cerebras + groq-paced are single-key."""
    import requests
    if provider != "gemini":
        return keys
    url_tpl = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": "OK"}]}], "generationConfig": {"maxOutputTokens": 5}}
    valid = []
    for k in keys:
        tail = k[-4:] if len(k) >= 4 else k
        last_err = None
        ok = False
        for attempt in range(3):
            try:
                r = requests.post(url_tpl.format(key=k), json=body, timeout=20)
                if r.status_code == 200:
                    ok = True
                    break
                # 4xx is a real key problem; don't retry
                if 400 <= r.status_code < 500:
                    last_err = f"{r.status_code}"
                    break
                last_err = f"{r.status_code}"
            except requests.RequestException as e:
                last_err = str(e)[:60]
                time.sleep(2)
        if ok:
            valid.append(k)
        else:
            print(f"  skipping bad key ...{tail} ({last_err})")
    return valid


def get_pending(con, limit=None, subreddit=None):
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
    if subreddit:
        sql += " AND c.subreddit = ?"
        params.append(subreddit)
    sql += " ORDER BY LENGTH(c.body) DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return con.execute(sql, params).fetchall()


def run_paced_pool(extract_fn, per_key_interval, pool, prompt, pending,
                   write_result, log_progress):
    work_q = queue.Queue()
    for item in pending:
        work_q.put(item)
    sentinel = object()
    for _ in pool:
        work_q.put(sentinel)

    result_q = queue.Queue()

    def worker(key, sess):
        last = 0.0
        while True:
            item = work_q.get()
            if item is sentinel:
                return
            cid, body, title = item
            wait = (last + per_key_interval) - time.time()
            if wait > 0:
                time.sleep(wait)
            try:
                mentions = extract_fn(sess, key, prompt, title, body)
                result_q.put((cid, mentions, None))
            except Exception as e:
                result_q.put((cid, None, str(e)))
            last = time.time()

    threads = [threading.Thread(target=worker, args=(k, s), daemon=True)
               for k, s in pool]
    for t in threads:
        t.start()

    n_done = n_with = n_failed = 0
    start = time.time()
    total = len(pending)
    while n_done < total:
        cid, mentions, err = result_q.get()
        n_done += 1
        if err:
            n_failed += 1
            continue
        if mentions:
            write_result(cid, mentions)
            n_with += 1
        else:
            write_result(cid, [])
        if n_done % 50 == 0:
            log_progress(n_done, total, n_with, n_failed, start)

    for t in threads:
        t.join(timeout=1)

    return n_done, n_with, n_failed, time.time() - start


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--subreddit", default=None)
    parser.add_argument("--provider", choices=["groq", "groq-paced", "gemini", "cerebras"], default="groq")
    parser.add_argument("--keys-file", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    con = connect()
    pending = get_pending(con, args.limit, subreddit=args.subreddit)

    placeholders = ",".join("?" * len(MENTION_FIELDS))
    insert_sql = f"INSERT INTO mentions ({','.join(MENTION_FIELDS)}) VALUES ({placeholders})"
    cp_sql = (
        "INSERT INTO pull_checkpoints (source, finished) VALUES (?, TRUE) "
        "ON CONFLICT (source) DO UPDATE SET finished = TRUE"
    )

    def write_result(cid, mentions):
        if mentions:
            now = int(time.time())
            rows = [_row_from_extraction(cid, m, now) for m in mentions]
            con.executemany(insert_sql, rows)
        con.execute(cp_sql, [f"extract:{cid}"])

    def log_progress(n_done, total, n_with, n_failed, start):
        elapsed = time.time() - start
        rate = n_done / elapsed if elapsed else 0
        eta = (total - n_done) / rate / 60 if rate else 0
        print(f"  ...{n_done}/{total}  {n_with} with mentions  {n_failed} failed  {rate:.1f}/s  eta {eta:.1f}m")

    if args.provider in ("gemini", "cerebras", "groq-paced"):
        if args.provider == "gemini":
            from llm.gemini_extract import make_session, load_prompt, extract as ext_fn
            default_keys_file = "gemini_api_key.txt"
            interval = GEMINI_PER_KEY_INTERVAL
            from_file = True
        elif args.provider == "cerebras":
            from llm.cerebras_extract import make_session, load_prompt, extract as ext_fn
            default_keys_file = "cerebras_api_key.txt"
            interval = CEREBRAS_PER_KEY_INTERVAL
            from_file = True
        else:  # groq-paced
            from llm.gemini_extract import make_session  # generic requests.Session
            from llm.groq_extract import load_prompt
            from llm.groq_paced_extract import extract as ext_fn
            default_keys_file = None
            interval = GROQ_PACED_INTERVAL
            from_file = False

        if from_file:
            keys_path = args.keys_file or str(
                Path(__file__).resolve().parents[1] / default_keys_file
            )
            all_keys = [l.strip() for l in open(keys_path) if l.strip()]
            # validate every key with a tiny test call; drop any that fail.
            print(f"validating {len(all_keys)} {args.provider} keys...")
            valid = _validate_keys(args.provider, all_keys)
            if not valid:
                print(f"no working {args.provider} keys; bailing")
                return
            print(f"  {len(valid)}/{len(all_keys)} keys valid")
            pool = [(k, make_session()) for k in valid]
        else:
            # single-key path (groq-paced)
            single_key = get_secret("GROQ_API_KEY")
            pool = [(single_key, make_session())]

        prompt = load_prompt()
        print(f"{args.provider}: {len(pool)} key(s), paced at {interval}s/call/key")
        print(f"{len(pending)} comments pending")
        if args.dry_run or not pending:
            return
        n_done, n_with, n_failed, elapsed = run_paced_pool(
            ext_fn, interval, pool, prompt, pending, write_result, log_progress
        )
        print(f"\ndone. {n_with}/{n_done} with mentions, {n_failed} failed, {elapsed/60:.1f} min")
        print(f"total mentions in db: {con.execute('SELECT COUNT(*) FROM mentions').fetchone()[0]}")
        con.close()
        return

    # groq single-key path
    from llm.groq_extract import make_client, load_prompt, extract as groq_extract
    client = make_client(get_secret("GROQ_API_KEY"))
    prompt = load_prompt()
    print(f"groq: {len(pending)} comments pending; using {args.workers} workers")
    if args.dry_run or not pending:
        return

    def task(item):
        cid, body, title = item
        try:
            return cid, groq_extract(client, prompt, title, body), None
        except Exception as e:
            return cid, None, str(e)

    n_with = n_failed = n_done = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed([ex.submit(task, it) for it in pending]):
            cid, mentions, err = fut.result()
            n_done += 1
            if err:
                n_failed += 1
                continue
            if mentions:
                write_result(cid, mentions)
                n_with += 1
            else:
                write_result(cid, [])
            if n_done % 50 == 0:
                log_progress(n_done, len(pending), n_with, n_failed, start)

    print(f"\ndone. {n_with}/{n_done} with mentions, {n_failed} failed, {(time.time()-start)/60:.1f} min")
    print(f"total mentions in db: {con.execute('SELECT COUNT(*) FROM mentions').fetchone()[0]}")
    con.close()


if __name__ == "__main__":
    main()
