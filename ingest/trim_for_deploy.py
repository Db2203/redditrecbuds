"""make a slimmed copy of data.duckdb for deploying to streamlit cloud.

drops the post selftext (largest field, never read by the app),
deletes/removed comments, and the resumability checkpoints.
output goes to data.duckdb (overwrites). source is preserved as data.full.duckdb.
"""
import shutil
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data.duckdb"
FULL = ROOT / "data.full.duckdb"
TMP = ROOT / "data.trimmed.duckdb"


def main():
    if not SRC.exists():
        print(f"no source db at {SRC}")
        sys.exit(1)

    # back up the full db so we don't lose detail
    if not FULL.exists():
        print(f"backing up {SRC} -> {FULL}")
        shutil.copy(SRC, FULL)

    if TMP.exists():
        TMP.unlink()

    con = duckdb.connect(str(TMP))
    con.execute(f"ATTACH '{FULL}' AS src (READ_ONLY)")

    print("copying posts (without selftext)...")
    con.execute(
        """
        CREATE TABLE posts AS
        SELECT id, subreddit, author, title, url, score, num_comments,
               created_utc, link_flair_text
        FROM src.posts
        """
    )

    print("copying useful comments...")
    con.execute(
        """
        CREATE TABLE comments AS
        SELECT id, link_id, parent_id, subreddit, author, body, score, created_utc
        FROM src.comments
        WHERE LENGTH(body) >= 40
          AND author NOT IN ('AutoModerator', '[deleted]')
          AND body NOT IN ('[deleted]', '[removed]')
        """
    )

    for tbl in ("mentions", "votes"):
        try:
            con.execute(f"CREATE TABLE {tbl} AS SELECT * FROM src.{tbl}")
            print(f"copied {tbl}")
        except Exception as e:
            print(f"skipping {tbl}: {e}")

    con.execute("DETACH src")
    con.close()

    # replace data.duckdb with the trimmed version
    SRC.unlink()
    TMP.rename(SRC)

    size_mb = SRC.stat().st_size / 1024 / 1024
    print(f"\ndone. data.duckdb now {size_mb:.1f} MB")
    print(f"full backup preserved at {FULL.name}")


if __name__ == "__main__":
    main()
