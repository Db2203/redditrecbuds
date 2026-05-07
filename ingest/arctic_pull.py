"""pull posts and comments from a few audio subreddits via arctic shift into duckdb."""
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

COMMENT_FIELDS = (
    "id", "link_id", "parent_id", "subreddit", "author",
    "body", "score", "created_utc", "retrieved_on",
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


def _row_from_comment(item):
    link_id = item.get("link_id") or ""
    # arctic shift returns link_id with the t3_ prefix; strip to match posts.id
    if link_id.startswith("t3_"):
        link_id = link_id[3:]
    return (
        item.get("id"),
        link_id,
        item.get("parent_id"),
        item.get("subreddit"),
        item.get("author"),
        item.get("body"),
        item.get("score"),
        item.get("created_utc"),
        item.get("retrieved_on"),
    )


def pull_sub_posts(con, session, sub, oldest_utc, batch_size=50):
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


def pull_post_comments(con, session, post_id, batch_size=50):
    source = f"post_comments:{post_id}"
    placeholders = ",".join("?" * len(COMMENT_FIELDS))
    insert_sql = (
        f"INSERT INTO comments ({','.join(COMMENT_FIELDS)}) VALUES ({placeholders}) "
        "ON CONFLICT (id) DO NOTHING"
    )

    n_seen = 0
    buf = []
    for item in paginate(session, "/api/comments/search", {"link_id": post_id},
                         batch_size=batch_size):
        n_seen += 1
        buf.append(_row_from_comment(item))
        if len(buf) >= 200:
            con.executemany(insert_sql, buf)
            buf.clear()

    if buf:
        con.executemany(insert_sql, buf)

    con.execute(
        "INSERT INTO pull_checkpoints (source, last_after, finished) VALUES (?, NULL, TRUE) "
        "ON CONFLICT (source) DO UPDATE SET finished = TRUE",
        [source],
    )
    return n_seen


def pull_comments_for_relevant(con, session, min_score=2, min_num_comments=3):
    posts = con.execute(
        """
        SELECT p.id, p.title, p.num_comments
        FROM posts p
        WHERE p.score >= ?
          AND p.num_comments >= ?
          AND NOT EXISTS (
            SELECT 1 FROM pull_checkpoints cp
            WHERE cp.source = 'post_comments:' || p.id AND cp.finished
          )
        ORDER BY p.num_comments DESC
        """,
        [min_score, min_num_comments],
    ).fetchall()

    print(f"  {len(posts)} posts to fetch comments for")
    total = 0
    for i, (post_id, title, ncomm) in enumerate(posts):
        try:
            n = pull_post_comments(con, session, post_id)
            total += n
        except Exception as e:
            print(f"  failed on {post_id}: {e}")
            continue
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(posts)} posts done, {total} comments so far")

    print(f"  done. {total} comments fetched.")
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["posts", "comments", "all"], default="all")
    parser.add_argument("--months", type=int, default=12,
                        help="how many months back to pull (posts mode)")
    parser.add_argument("--subs", default=",".join(SUBS))
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--min-score", type=int, default=2)
    parser.add_argument("--min-num-comments", type=int, default=3)
    args = parser.parse_args()

    con = connect()
    session = make_session()

    if args.mode in ("posts", "all"):
        oldest_utc = int(time.time()) - args.months * 30 * 86400
        subs = [s.strip() for s in args.subs.split(",") if s.strip()]
        print(f"pulling posts from {subs}, {args.months} months back")
        for sub in subs:
            print(f"sub: r/{sub}")
            try:
                pull_sub_posts(con, session, sub, oldest_utc, batch_size=args.batch)
            except Exception as e:
                print(f"  failed on {sub}: {e}")

    if args.mode in ("comments", "all"):
        print("\npulling comments for relevant posts")
        pull_comments_for_relevant(
            con, session,
            min_score=args.min_score,
            min_num_comments=args.min_num_comments,
        )

    print()
    print(f"posts in db:    {con.execute('SELECT COUNT(*) FROM posts').fetchone()[0]}")
    print(f"comments in db: {con.execute('SELECT COUNT(*) FROM comments').fetchone()[0]}")
    con.close()


if __name__ == "__main__":
    main()
