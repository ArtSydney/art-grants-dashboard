"""A no-API gate for noisy sources.

Only sources flagged "prefilter": true in sources.json run through this (the
ArtsHub main feed, which is mostly news). Curated opportunity sources skip it and
go straight to the classifier. The gate is a permissive whitelist: if a title or
summary contains any hint word, it reaches Claude; otherwise it's dropped without
costing a token. Keep the list generous and add words when you spot a miss.
"""

OPPORTUNITY_HINTS = (
    "grant", "prize", "award", "scholarship", "residency", "fellowship",
    "commission", "competition", "contest", "stipend", "juried",
    "open call", "call for", "call-out", "callout", "eoi",
    "expression of interest", "applications open", "applications are open",
    "apply now", "now open", "submissions", "funding", "bursary",
)


def looks_like_opportunity(item):
    text = f"{item['title']} {item.get('summary', '')}".lower()
    return any(hint in text for hint in OPPORTUNITY_HINTS)
