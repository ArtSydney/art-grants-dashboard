"""Deterministic classifier — zero API calls, zero cost.

Replaces the Claude Haiku classifier with rule-based extraction.
All fields are derived from the item title, source and summary text
using keyword matching and regex. No network calls, no latency, free.

The only thing lost vs the AI classifier is nuanced edge cases. In
practice the sources are well-structured enough that rules work well.
"""
import re

from config import ART_FORMS, WILDCARD_FORMS, DROP_IF_NO_ART_FORM

# ---------------------------------------------------------------------------
# Drop lists — items matching any of these are not relevant
# ---------------------------------------------------------------------------

_DROP_TITLES = [
    "workshop", "webinar", "info session", "information session",
    "knowledge series", "fundamentals of", "delivery partner",
    "how to apply", "making a grant application", "life drawing",
    "long pose", "drawing session", "painting session",
    "artist talk", "mask making", "weaving workshop",
    "vendor", "stallholder", "market stall",
    "job ", " jobs", "vacancy", "vacancies", "employment",
    "call for facilitators", "expression of interest for facilitators",
    "call for educators", "call for teachers",
]

_DROP_SOURCES = []  # currently none

# non-visual art forms — items exclusively about these are dropped
_NON_VISUAL = [
    "record label", "music australia", "contemporary music touring",
    "music residency", "sound art", "audio recording", "songwriting",
    "literary", "literature", "writing australia", "publishing",
    "writers festival", "poet laureate", "poetry award",
    "dance services", "dance residency", "theatre award", "opera",
    "screen australia", "film commission", "screenwriting",
    "games design", "for musicians", "for bands", "for composers",
    "music industry", "music export",
]

# ---------------------------------------------------------------------------
# Australian arts sources — always eligible for Australian artists
# ---------------------------------------------------------------------------

_AU_SOURCES = {
    "Creative Australia", "BNE Art: Opportunities",
    "Calendar for Artists", "Artsoz prize registry",
    "Google: Australian art prizes",
}

_AU_KEYWORDS = [
    "australia", "australian", "nsw", "victoria", "queensland",
    "south australia", "western australia", "tasmania",
    "northern territory", "act ", "canberra", "sydney", "melbourne",
    "brisbane", "perth", "adelaide", "hobart", "darwin",
    "create nsw", "arts queensland", "arts victoria",
]

# ---------------------------------------------------------------------------
# Category keywords
# ---------------------------------------------------------------------------

_CATEGORY_MAP = [
    ("Residency",   ["residency", "residencies", "artist in residence", "air program", "studio residency"]),
    ("Fellowship",  ["fellowship", "fellowships", "fellow "]),
    ("Scholarship", ["scholarship", "scholarships", "travelling scholarship", "bequest"]),
    ("Commission",  ["commission", "commissioning", "commissioned work", "public art commission", "eoi"]),
    ("Grant",       ["grant", "grants", "funding", "fund ", "micro grant", "matched funding"]),
    ("Prize",       ["prize", "prizes", "art prize", "award", "awards", "competition", "acquisitive"]),
    ("Award",       ["award", "awards", "lifetime achievement", "recognition award"]),
]

# ---------------------------------------------------------------------------
# Art form keyword mapping
# ---------------------------------------------------------------------------

_FORM_MAP = [
    ("Painting",         ["painting", "paintings", "paint ", "oils", "watercolour", "acrylic", "portrait paint"]),
    ("Drawing",          ["drawing", "drawings", "draw ", "printmaking", "prints and drawings", "works on paper", "paper prize"]),
    ("Sculpture",        ["sculpture", "sculptures", "sculptural", "3d work", "three-dimensional", "installation art", "public art"]),
    ("Photography",      ["photography", "photo", "photographic", "photograph", "lens-based", "portrait prize"]),
    ("Printmaking",      ["printmaking", "print award", "etching", "lithograph", "screenprint"]),
    ("Ceramics",         ["ceramic", "ceramics", "pottery", "clay"]),
    ("Textiles",         ["textile", "textiles", "fabric", "weaving", "fibre", "fiber"]),
    ("Illustration",     ["illustration", "illustrat"]),
    ("Digital/New Media",["digital art", "new media", "video art", "digital media", "digital work", "media art"]),
    ("Installation",     ["installation", "site-specific", "immersive"]),
    ("Mixed Media",      ["mixed media", "multi-media", "multimedia", "all media", "any medium", "any media"]),
]

_VISUAL_KEYWORDS = [
    "visual art", "visual arts", "fine art", "contemporary art",
    "painter", "sculptor", "artist", "artwork", "artworks",
    "painting", "drawing", "sculpture", "photography",
    "printmaking", "ceramics", "textile", "illustration",
    "gallery", "exhibition", "acquisitive",
]

_MULTI_KEYWORDS = [
    "all art forms", "all arts", "all disciplines", "any discipline",
    "any medium", "any media", "all mediums", "all practices",
    "multi-art", "multidisciplinary", "cross-disciplinary",
    "open to all artists",
]

# ---------------------------------------------------------------------------
# Deadline extraction
# ---------------------------------------------------------------------------

_MONTHS = (
    "January|February|March|April|May|June|"
    "July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)
_MONTH_NUM = {
    "january":"01","february":"02","march":"03","april":"04",
    "may":"05","june":"06","july":"07","august":"08",
    "september":"09","october":"10","november":"11","december":"12",
    "jan":"01","feb":"02","mar":"03","apr":"04",
    "jun":"06","jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
}


def _extract_deadline(text):
    """Return YYYY-MM-DD or '' from free text.
    Prioritises dates that appear near closing/deadline keywords.
    """
    # YYYYMMDD numeric (BNE Art widget format)
    m = re.search(r'\b(202\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b', text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # Look for closing-keyword + date patterns first (highest confidence)
    # "closes: 5 October 2026", "close 5 Oct 2026", "deadline: 5 October"
    m = re.search(
        rf'(?:clos(?:es?|ing)|deadline|due|submit(?:ted)?\s+by|applications?\s+close)[:\s]+(\d{{1,2}})\s+({_MONTHS})\s+(202\d)',
        text, re.IGNORECASE
    )
    if m:
        d = m.group(1).zfill(2)
        mo = _MONTH_NUM.get(m.group(2).lower()[:3], "")
        y = m.group(3)
        if mo:
            return f"{y}-{mo}-{d}"

    # "until 5 October 2026" / "open until 5 Oct 2026"
    m = re.search(
        rf'until\s+(\d{{1,2}})\s+({_MONTHS})\s+(202\d)',
        text, re.IGNORECASE
    )
    if m:
        d = m.group(1).zfill(2)
        mo = _MONTH_NUM.get(m.group(2).lower()[:3], "")
        y = m.group(3)
        if mo:
            return f"{y}-{mo}-{d}"

    # "5 October 2026" anywhere — only if it's a future year
    m = re.search(
        rf'\b(\d{{1,2}})\s+({_MONTHS})\s+(202[6-9]|203\d)\b',
        text, re.IGNORECASE
    )
    if m:
        d = m.group(1).zfill(2)
        mo = _MONTH_NUM.get(m.group(2).lower()[:3], "")
        y = m.group(3)
        if mo:
            return f"{y}-{mo}-{d}"

    # "October 5, 2026" or "October 5 2026"
    m = re.search(
        rf'\b({_MONTHS})\s+(\d{{1,2}})[,\s]+(202[6-9]|203\d)\b',
        text, re.IGNORECASE
    )
    if m:
        mo = _MONTH_NUM.get(m.group(1).lower()[:3], "")
        d = m.group(2).zfill(2)
        y = m.group(3)
        if mo:
            return f"{y}-{mo}-{d}"

    # "14 August" with no year — assume current or next year
    m = re.search(
        rf'(?:clos(?:es?|ing)|deadline|until)[:\s]+(\d{{1,2}})\s+({_MONTHS})\b',
        text, re.IGNORECASE
    )
    if m:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Australia/Sydney"))
        d = m.group(1).zfill(2)
        mo = _MONTH_NUM.get(m.group(2).lower()[:3], "")
        if mo:
            y = now.year
            try:
                candidate = datetime(y, int(mo), int(d))
                if candidate.date() < now.date():
                    y += 1
            except ValueError:
                pass
            return f"{y}-{mo}-{d}"

    return ""


def _extract_amount(text):
    """Return first dollar amount found, e.g. '$30,000'."""
    m = re.search(r'AUD\s*\$[\d,]+|\$[\d,]+(?:\s*(?:million|k))?\b', text, re.IGNORECASE)
    if not m:
        return ""
    val = m.group(0).strip()
    # normalise AUD $50,000 -> $50,000
    val = re.sub(r'^AUD\s*', '', val, flags=re.IGNORECASE)
    return val


# ---------------------------------------------------------------------------
# Main classify function
# ---------------------------------------------------------------------------

def classify(item):
    """Return classification dict using deterministic rules. No API calls."""
    title   = (item.get("title") or "").strip()
    source  = (item.get("source") or "").strip()
    summary = (item.get("summary") or "").strip()
    text    = f"{title} {summary}".lower()

    # --- 404 / empty page guard ---
    if any(s in text for s in ("page not found", "could not be found", "just a moment")):
        return _not_relevant("Page not found.")

    # --- drop non-opportunity content by title keywords ---
    title_low = title.lower()
    if any(kw in title_low for kw in _DROP_TITLES):
        return _not_relevant(f"Dropped: title matches noise keyword.")

    # --- drop exclusively non-visual art forms ---
    # check title separately since summary may not repeat the art form
    title_low = title.lower()
    non_visual_hit = any(kw in text for kw in _NON_VISUAL) or any(kw in title_low for kw in _NON_VISUAL)
    visual_hit = any(kw in text for kw in _VISUAL_KEYWORDS[:8])
    if non_visual_hit and not visual_hit:
        return _not_relevant("Dropped: exclusively non-visual art form.")

    # --- relevance: must look like an opportunity ---
    opportunity_signals = [
        "entries open", "entries now open", "entries close", "open for entries",
        "apply now", "applications open", "applications now open", "applications close",
        "call for entries", "call for artists", "call for applications",
        "submissions open", "submissions close", "submissions now open",
        "prize", "grant", "award", "residency", "fellowship", "scholarship",
        "commission", "acquisitive", "funding", "open call",
        "expression of interest", "eoi open",
    ]
    relevant = any(sig in text for sig in opportunity_signals)
    if not relevant:
        return _not_relevant("No opportunity signal found.")

    # --- category ---
    category = "Other"
    for cat, keywords in _CATEGORY_MAP:
        if any(kw in text for kw in keywords):
            category = cat
            break

    # --- au_eligibility ---
    if source in _AU_SOURCES or any(kw in text for kw in _AU_KEYWORDS):
        au_eligibility = "eligible"
        location_scope = "Australia"
    elif any(kw in text for kw in ["international", "worldwide", "global", "any country", "all countries"]):
        au_eligibility = "unclear"
        location_scope = "International"
    else:
        au_eligibility = "unclear"
        location_scope = "Unknown"

    # items explicitly restricted to non-AU applicants
    if any(kw in text for kw in ["uk only", "us only", "usa only", "united states only",
                                   "european ", "eu only", "not open to australian"]):
        au_eligibility = "ineligible"

    # --- deadline ---
    deadline = _extract_deadline(summary + " " + title)

    # --- amount ---
    amount = _extract_amount(summary + " " + title)

    # --- art_forms ---
    art_forms = []
    for form, keywords in _FORM_MAP:
        if any(kw in text for kw in keywords):
            art_forms.append(form)

    if not art_forms:
        if any(kw in text for kw in _MULTI_KEYWORDS):
            art_forms = ["Multidisciplinary"]
        elif any(kw in text for kw in _VISUAL_KEYWORDS):
            art_forms = ["Visual Arts"]

    # deduplicate while preserving order
    seen_forms = set()
    art_forms = [f for f in art_forms if not (f in seen_forms or seen_forms.add(f))]

    if DROP_IF_NO_ART_FORM and not art_forms:
        return _not_relevant("No visual art form detected.")

    # --- one-line summary from first sentence of summary ---
    first_sent = re.split(r'(?<=[.!?])\s', summary)
    brief = first_sent[0][:200] if first_sent else title

    return {
        "relevant":       True,
        "english":        True,
        "category":       category,
        "au_eligibility": au_eligibility,
        "location_scope": location_scope,
        "eligibility_note": "",
        "deadline":       deadline,
        "amount":         amount,
        "summary":        brief,
        "curator":        "",
        "judge":          "",
        "art_forms":      art_forms,
    }


def _not_relevant(reason=""):
    return {
        "relevant": False, "english": True,
        "category": "Other", "au_eligibility": "unclear",
        "location_scope": "Unknown", "eligibility_note": "",
        "deadline": "", "amount": "", "summary": reason,
        "curator": "", "judge": "", "art_forms": [],
    }
