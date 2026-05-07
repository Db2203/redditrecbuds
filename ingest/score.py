"""rebuild the votes table from current mentions and show top 20."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db import connect
from lib.dedup import rebuild_votes


def main():
    con = connect()

    n_mentions = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
    print(f"{n_mentions:,} mentions in db")
    if n_mentions == 0:
        print("no mentions yet - run ingest/extract.py first")
        return

    n_votes = rebuild_votes(con)
    print(f"votes table rebuilt, {n_votes:,} rows")

    rows = con.execute(
        """
        SELECT brand, model,
            SUM(CASE WHEN sentiment = 'positive' THEN weight ELSE 0 END) AS pos,
            SUM(CASE WHEN sentiment = 'negative' THEN weight ELSE 0 END) AS neg,
            COUNT(DISTINCT author) AS users
        FROM votes
        GROUP BY brand, model
        ORDER BY pos DESC
        LIMIT 20
        """
    ).fetchall()
    print("\ntop 20 by positive votes:")
    for brand, model, pos, neg, users in rows:
        print(f"  {pos:>6.1f}+ / {neg:>4.1f}-  ({users:>3} users)  {brand} {model}")
    con.close()


if __name__ == "__main__":
    main()
