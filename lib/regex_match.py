"""regex pattern generation + simple sentiment for hybrid extraction.

we use the existing (brand, model) pairs from the mentions table as a dictionary,
generate variant patterns per product, and scan reddit comments for matches.
sentiment is keyword-based within +-80 chars of the match.

this is cheaper-but-rougher than the llm path; mentions tagged source='regex'
so the methodology page can be honest about the mix.
"""
import re

POS = {
    "love", "loved", "great", "amazing", "best", "awesome", "recommend",
    "recommended", "fantastic", "excellent", "perfect", "incredible",
    "solid", "killer", "top-tier", "favorite", "favourite", "stellar",
    "phenomenal", "outstanding", "happy", "impressed", "worth", "buy",
    "fan", "underrated", "winner",
}

NEG = {
    "avoid", "terrible", "awful", "hate", "hated", "disappointing",
    "disappointed", "returned", "returning", "sucks", "garbage", "junk",
    "regret", "mistake", "broken", "broke", "worst", "horrible", "failed",
    "failure", "skip", "overrated", "fell off", "uncomfortable", "buggy",
}


def split_alphanum(s):
    """split a string into alpha/digit chunks. WF-1000XM5 -> ['wf','1000','xm','5']"""
    return re.findall(r"[a-z]+|\d+", s.lower())


def patterns_for(brand, model):
    """generate a deduped list of regex strings for a (brand, model) pair.

    - always allows "<brand> <model-variant>" with the brand prefix
    - allows model-variant alone only if it's specific (alphanumeric mix, len>=5)
    - dashes and spaces in model are made optional
    """
    if not brand or not model:
        return []

    bp = re.escape(brand.lower()).replace(r"\ ", r"\s+")
    parts = split_alphanum(model)
    if not parts:
        return []

    out = set()
    # suffixes of the canonical model
    for n in range(1, len(parts) + 1):
        suffix = "".join(parts[-n:])
        if len(suffix) < 3:
            continue
        # always allow "<brand> <suffix>"
        out.add(rf"\b{bp}\s+{re.escape(suffix)}\b")
        # allow alone if specific (mix of letters+digits, len>=6 to avoid
        # ambiguous short codes like 'az100' matching across brands)
        if (len(suffix) >= 6
                and any(c.isdigit() for c in suffix)
                and any(c.isalpha() for c in suffix)):
            out.add(rf"\b{re.escape(suffix)}\b")

    # also "<brand> <full-model-with-flexible-separators>"
    flexible_model = "".join(
        f"{re.escape(p)}[\\s\\-]*" if i < len(parts) - 1 else re.escape(p)
        for i, p in enumerate(parts)
    )
    out.add(rf"\b{bp}\s+{flexible_model}\b")
    return sorted(out)


def build_product_patterns(products):
    """products: iterable of (brand, model) tuples.
    returns list of (brand, model, compiled_regex) ordered by specificity."""
    rows = []
    for brand, model in products:
        for pat in patterns_for(brand, model):
            try:
                rx = re.compile(pat, re.IGNORECASE)
                rows.append((brand, model, rx, pat))
            except re.error:
                continue
    # longer patterns first so "Sony WF-1000XM5" matches before "WF-1000XM5"
    rows.sort(key=lambda r: -len(r[3]))
    return rows


def find_products(text, patterns):
    """returns list of (brand, model, match_start, match_end).
    avoids duplicates per (brand, model) within the same comment."""
    if not text:
        return []
    seen = set()
    out = []
    for brand, model, rx, _ in patterns:
        key = (brand.lower(), model.lower())
        if key in seen:
            continue
        m = rx.search(text)
        if m:
            seen.add(key)
            out.append((brand, model, m.start(), m.end()))
    return out


def score_sentiment(text, match_start, match_end, window=80):
    """count pos/neg keywords within +-window chars of the match. returns
    'positive' | 'negative' | 'neutral'."""
    lo = max(0, match_start - window)
    hi = min(len(text), match_end + window)
    region = text[lo:hi].lower()
    tokens = set(re.findall(r"[a-z']+", region))
    pos = len(tokens & POS)
    neg = len(tokens & NEG)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"
