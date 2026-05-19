"""manual canonical-name merges for the most common product-name duplicates.

each entry collapses one variant onto the canonical (brand, model) pair.
key is (lowercase brand, alphanum-only lowercase model) so the same value
folds in case + dash + space + abbreviation differences.

deliberately kept short and obvious - automatic similarity matching risks
collapsing genuinely different products (Liberty 4 vs Liberty 4 Pro etc).
"""
import re

CANONICAL_MERGES = {
    # Sony WF-1000XM* shorthand
    ("sony", "xm3"): ("Sony", "WF-1000XM3"),
    ("sony", "xm4"): ("Sony", "WF-1000XM4"),
    ("sony", "xm5"): ("Sony", "WF-1000XM5"),
    ("sony", "xm6"): ("Sony", "WF-1000XM6"),
    ("sony", "1000xm3"): ("Sony", "WF-1000XM3"),
    ("sony", "1000xm4"): ("Sony", "WF-1000XM4"),
    ("sony", "1000xm5"): ("Sony", "WF-1000XM5"),
    ("sony", "1000xm6"): ("Sony", "WF-1000XM6"),

    # Technics official vs casual name
    ("technics", "eahaz100"): ("Technics", "AZ100"),
    ("technics", "eahaz80"): ("Technics", "AZ80"),
    ("technics", "eahaz60"): ("Technics", "AZ60"),

    # Bose QuietComfort family (abbreviation + case variants)
    ("bose", "qc"): ("Bose", "QuietComfort"),
    ("bose", "quietcomfort"): ("Bose", "QuietComfort"),
    ("bose", "qcultra"): ("Bose", "QuietComfort Ultra"),
    ("bose", "quietcomfortultra"): ("Bose", "QuietComfort Ultra"),
    ("bose", "qcii"): ("Bose", "QuietComfort II"),
    ("bose", "quietcomfortii"): ("Bose", "QuietComfort II"),

    # Sennheiser Momentum True Wireless 4 has 3 common forms
    ("sennheiser", "mtw4"): ("Sennheiser", "Momentum True Wireless 4"),
    ("sennheiser", "momentum4"): ("Sennheiser", "Momentum True Wireless 4"),
    ("sennheiser", "momentumtruewireless4"): ("Sennheiser", "Momentum True Wireless 4"),
    ("sennheiser", "mtw3"): ("Sennheiser", "Momentum True Wireless 3"),
    ("sennheiser", "momentum3"): ("Sennheiser", "Momentum True Wireless 3"),

    # Samsung Galaxy Buds family — "Galaxy" prefix often dropped
    ("samsung", "buds3pro"): ("Samsung", "Galaxy Buds 3 Pro"),
    ("samsung", "galaxybuds3pro"): ("Samsung", "Galaxy Buds 3 Pro"),
    ("samsung", "buds2pro"): ("Samsung", "Galaxy Buds 2 Pro"),
    ("samsung", "galaxybuds2pro"): ("Samsung", "Galaxy Buds 2 Pro"),
    ("samsung", "budsfe"): ("Samsung", "Galaxy Buds FE"),
    ("samsung", "galaxybudsfe"): ("Samsung", "Galaxy Buds FE"),

    # JBL Tour Pro 3
    ("jbl", "tp3"): ("JBL", "Tour Pro 3"),
    ("jbl", "tourpro3"): ("JBL", "Tour Pro 3"),

    # Denon Perl Pro — case-only fix
    ("denon", "perlpro"): ("Denon", "Perl Pro"),

    # Earfun Air Pro 4 — sometimes called "Pro 4"
    ("earfun", "pro4"): ("Earfun", "Air Pro 4"),
    ("earfun", "airpro4"): ("Earfun", "Air Pro 4"),

    # Google Pixel Buds Pro
    ("google", "pixelbudspro"): ("Google", "Pixel Buds Pro"),
    ("google", "pixelbudspro2"): ("Google", "Pixel Buds Pro 2"),

    # B&W Pi8 (sometimes written with ampersand variations)
    ("bowers&wilkins", "pi8"): ("Bowers & Wilkins", "Pi8"),
    ("bw", "pi8"): ("Bowers & Wilkins", "Pi8"),
}


def canonical(brand, model):
    """returns canonical (brand, model) for known dup variants, original otherwise."""
    if not brand or not model:
        return brand, model
    key = (
        brand.lower().strip(),
        re.sub(r"[^a-z0-9]", "", model.lower()),
    )
    return CANONICAL_MERGES.get(key, (brand, model))
