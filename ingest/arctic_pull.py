"""pull posts from a few audio subreddits via arctic shift into duckdb."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.arctic import make_session, paginate
from lib.db import connect

SUBS = ["HeadphoneAdvice", "Earbuds", "headphones", "budgetaudiophile"]

POST_FIELDS = (
    "id", "subreddit", "author", "title", "selftext", "url",
    "score", "num_comments", "created_utc", "retrieved_on",
    "link_flair_text", "source",
)


def _row_from_post(item, source):
    return (
        item.get("id"),
        item.get("subreddit"),
        item.get("author"),
        item.get("title"),
        item.get("selftext"),
        item.get("url"),
        item.get("score"),
        item.get("num_comments"),
        item.get("created_utc"),
        item.get("retrieved_on"),
        item.get("link_flair_text"),
        source,
    )


def pull_sub(con, session, sub, oldest_utc, batch_size=100):
    source = f"sub:{sub}"
    cp = con.execute(
        "SELECT last_after, finished FROM pull_checkpoints WHERE source = ?",
        [source],
    ).fetchone()
    before = cp[0] if cp and cp[0] else None

    n_seen = 0
    buf = []

    params = {"subreddit": sub}
    if before:
        params["before"] = before
        print(f"  resuming {sub} from before={before}")

    placeholders = ",".join("?" * len(POST_FIELDS))
    insert_sql = (
        f"INSERT INTO posts ({','.join(POST_FIELDS)}) VALUES ({placeholders}) "
        "ON CONFLICT (id) DO NOTHING"
    )

    last_ts = None
    for item in paginate(session, "/api/posts/search", params,
                         batch_size=batch_size, oldest_utc=oldest_utc):
        n_seen += 1
        buf.append(_row_from_post(item, source))
        last_ts = item.get("created_utc")
        if len(buf) >= 200:
            con.executemany(insert_sql, buf)
            buf.clear()
            if last_ts:
                con.execute(
                    "INSERT INTO pull_checkpoints (source, last_after) VALUES (?, ?) "
                    "ON CONFLICT (source) DO UPDATE SET last_after = excluded.last_after",
                    [source, last_ts],
                )
            print(f"  ...{n_seen} seen")

    if buf:
        con.executemany(insert_sql, buf)

    con.execute(
        "INSERT INTO pull_checkpoints (source, last_after, finished) VALUES (?, ?, TRUE) "
        "ON CONFLICT (source) DO UPDATE SET last_after = excluded.last_after, finished = TRUE",
        [source, last_ts],
    )
    print(f"  done {sub}: saw {n_seen}, total in db now: ", end="")
    print(con.execute("SELECT COUNT(*) FROM posts WHERE subreddit = ?", [sub]).fetchone()[0])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=12,
                        help="how many months back to pull")
    parser.add_argument("--subs", default=",".join(SUBS))
    parser.add_argument("--batch", type=int, default=50)
    args = parser.parse_args()

    oldest_utc = int(time.time()) - args.months * 30 * 86400
    subs = [s.strip() for s in args.subs.split(",") if s.strip()]
    print(f"pulling posts from {subs}, oldest_utc={oldest_utc} ({args.months} months back)")

    con = connect()
    session = make_session()

    for sub in subs:
        print(f"sub: r/{sub}")
        try:
            pull_sub(con, session, sub, oldest_utc, batch_size=args.batch)
        except Exception as e:
            print(f"  failed on {sub}: {e}")

    total = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    by_sub = con.execute(
        "SELECT subreddit, COUNT(*) FROM posts GROUP BY subreddit ORDER BY 2 DESC"
    ).fetchall()
    print(f"\ntotal posts: {total}")
    for row in by_sub:
        print(f"  r/{row[0]}: {row[1]}")
    con.close()


if __name__ == "__main__":
    main()
