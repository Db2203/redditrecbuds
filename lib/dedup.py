"""dedup mentions to per-user-per-product votes, with imprecise reference spread.

two stages:

1. precise mentions (brand + model both specified): collapse to one row per
   (author, brand, model) with the user's majority sentiment; weight = 1.0
2. imprecise mentions (brand specified, model not): spread the user's vote
   across the TOP 3 most-mentioned models of that brand, weighted by each
   model's overall mention count. weights sum to 1.0 per (author, brand) pair.
   capping at top 3 avoids smearing one "Bose" mention across 8 model variants
   and creating phantom ties in the rankings.

result: a `votes` table joining the two with a uniform schema.
"""

# how many top models per brand to spread imprecise mentions across
IMPRECISE_SPREAD_TOP_N = 3

DROP_VOTES = "DROP TABLE IF EXISTS votes"

BUILD_VOTES = """
CREATE TABLE votes AS

WITH precise_counts AS (
    SELECT c.author, m.brand, m.model, m.sentiment, COUNT(*) AS n
    FROM mentions m
    JOIN comments c ON c.id = m.comment_id
    WHERE m.brand IS NOT NULL
      AND m.model IS NOT NULL
      AND c.author NOT IN ('AutoModerator', '[deleted]')
    GROUP BY 1, 2, 3, 4
),
precise_winning AS (
    SELECT author, brand, model, sentiment
    FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY author, brand, model
            ORDER BY n DESC,
                     CASE sentiment
                         WHEN 'positive' THEN 0
                         WHEN 'negative' THEN 1
                         ELSE 2
                     END
        ) AS rk
        FROM precise_counts
    )
    WHERE rk = 1
),
brand_models_all AS (
    SELECT brand, model, COUNT(*) AS n,
           ROW_NUMBER() OVER (PARTITION BY brand ORDER BY COUNT(*) DESC) AS rk
    FROM mentions
    WHERE brand IS NOT NULL AND model IS NOT NULL
    GROUP BY 1, 2
),
brand_models AS (
    SELECT brand, model, n FROM brand_models_all WHERE rk <= {top_n}
),
brand_totals AS (
    SELECT brand, SUM(n) AS total
    FROM brand_models
    GROUP BY brand
),
imprecise_counts AS (
    SELECT c.author, m.brand, m.sentiment, COUNT(*) AS n
    FROM mentions m
    JOIN comments c ON c.id = m.comment_id
    WHERE m.brand IS NOT NULL
      AND m.model IS NULL
      AND c.author NOT IN ('AutoModerator', '[deleted]')
    GROUP BY 1, 2, 3
),
imprecise_winning AS (
    SELECT author, brand, sentiment
    FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY author, brand
            ORDER BY n DESC,
                     CASE sentiment
                         WHEN 'positive' THEN 0
                         WHEN 'negative' THEN 1
                         ELSE 2
                     END
        ) AS rk
        FROM imprecise_counts
    )
    WHERE rk = 1
)

SELECT author, brand, model, sentiment, 1.0 AS weight
FROM precise_winning

UNION ALL

SELECT iw.author, iw.brand, bm.model, iw.sentiment,
       bm.n * 1.0 / bt.total AS weight
FROM imprecise_winning iw
JOIN brand_models bm USING (brand)
JOIN brand_totals bt USING (brand)
"""


def _build_canonical_mentions(con):
    """create a temp table mirroring mentions but with (brand, model) canonicalized.
    we run dedup against THIS table so the merge happens upstream of all scoring math.
    """
    from lib.canonical import canonical
    con.execute("DROP TABLE IF EXISTS canonical_mentions")
    # copy schema only
    con.execute("CREATE TABLE canonical_mentions AS SELECT * FROM mentions WHERE 1=0")
    cols = [r[0] for r in con.execute("DESCRIBE mentions").fetchall()]
    placeholders = ",".join("?" * len(cols))
    rows = con.execute(f"SELECT {','.join(cols)} FROM mentions").fetchall()
    brand_idx = cols.index("brand")
    model_idx = cols.index("model")
    new_rows = []
    for r in rows:
        c_brand, c_model = canonical(r[brand_idx], r[model_idx])
        nr = list(r)
        nr[brand_idx] = c_brand
        nr[model_idx] = c_model
        new_rows.append(nr)
    con.executemany(
        f"INSERT INTO canonical_mentions VALUES ({placeholders})",
        new_rows,
    )


def rebuild_votes(con, top_n=IMPRECISE_SPREAD_TOP_N):
    """rebuild the votes table from current mentions, with canonical merge applied."""
    _build_canonical_mentions(con)
    con.execute(DROP_VOTES)
    # the canonical merge lives upstream in canonical_mentions; rest of the math unchanged.
    sql = BUILD_VOTES.format(top_n=top_n).replace("FROM mentions", "FROM canonical_mentions")
    con.execute(sql)
    return con.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
