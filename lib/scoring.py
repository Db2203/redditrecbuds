"""scoring functions for ranking products by reddit reception.

wilson lower bound is the same statistic reddit's 'best' comment sort uses.
it gives a confidence-aware floor on the true positive ratio: products
with great ratios but tiny sample sizes get heavily penalized, which
solves the '1 positive, 0 negative ranks #1' problem.

final ranking combines wilson with a volume signal at 75:25.
rationale: a product with 200 positive votes and 5 negative is more
clearly the popular pick than one with 5 positive and 0 negative, even
if the second has a better naive ratio.
"""
import math

WILSON_Z = 1.96  # 95% confidence


def wilson_lower(pos, neg, z=WILSON_Z):
    """lower bound of the wilson score interval. 0..1."""
    n = pos + neg
    if n == 0:
        return 0.0
    p = pos / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def normalize_log_volume(values):
    """map a list of positive counts to log-normalized 0..1 scores.

    log1p(v) / log1p(max), so the most-mentioned product is 1.0 and
    a product with 0 positive votes is 0.0.
    """
    if not values:
        return []
    logs = [math.log1p(v) for v in values]
    cap = max(logs)
    if cap <= 0:
        return [0.0] * len(values)
    return [v / cap for v in logs]


def combined_score(volume_norm, wilson, w_volume=0.75):
    """75:25 weighted blend of volume signal and wilson lower bound."""
    return w_volume * volume_norm + (1 - w_volume) * wilson
