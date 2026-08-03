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
    "how to apply", "making a grant application",
    "life drawing", "long pose", "drawing session", "painting session",
    "drawing & painting", "drawing and painting",
    "artist talk", "mask making", "weaving workshop", "weaving yourself",
    "vendor", "stallholder", "market stall",
    "job ", " jobs", "vacancy", "vacancies", "employment",
    "call for facilitators", "expression of interest for facilitators",
    "call for educators", "call for teachers",
    "networking", "meet by ", "events june", "events july", "events august",
    "drawing festival", "art & wellbeing", "art and wellbeing",
    "navigating a digital", "new writers' program", "new writers program",
    "paste up festival", "art fair ",
    "how a zoom", "super choir", "wellbeing workshop",
    "facilitation 2026",  # Workshop Facilitation 2026
    "working with the grain",  # specific workshop
]

_DROP_SOURCES = []  # currently none

# non-visual art forms — items exclusively about these are dropped
_NON_VISUAL = [
    "record label", "music australia", "contemporary music touring",
    "music touring", "music residency", "sound art", "audio recording",
    "songwriting", "for musicians", "for bands", "for composers",
    "music industry", "music export", "music program",
    "literary", "literature award", "writing australia", "publishing fund",
    "publishing and promotion", "writers festival", "poet laureate",
    "poetry award", "book prize", "literary prize",
    "dance services", "dance residency", "theatre award", "opera grant",
    "screen australia", "film commission", "screenwriting",
    "games design", "australian publishing",
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
    ("Prize",       ["art prize", "art award", "acquisitive prize", "acquisitive award",
                     "prize pool", "prize money", "prize for", "award for", "award celebrating",
                     "competition", "art competition", "portrait prize", "landscape prize",
                     "sculpture prize", "photography prize", "drawing prize",
                     "painting prize", "open prize", "non-acquisitive prize"]),
    ("Residency",   [" residency", "residency.", "residency program", "artist in residence",
                     "air program", "studio residency", "residencies"]),
    ("Fellowship",  ["fellowship", "fellowships", "creative fellow"]),
    ("Scholarship", ["scholarship", "scholarships", "travelling scholarship", "bursary"]),
    ("Commission",  ["commission", "commissioning", "commissioned work", "public art commission"]),
    ("Grant",       ["grant program", "grant funding", "micro grant", "matched funding",
                     "funding program", "funding opportunity", "apply for funding",
                     "project fund", "development fund"]),
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
    Strips Related Posts sections (BNE Art includes other items' deadlines there).
    Prioritises dates near closing keywords over bare dates.
    """
    # strip "Related Posts" section — everything after it contains other items' dates
    for marker in ("Related Posts", "related posts", "You may also like", "See also"):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]

    # YYYYMMDD numeric — only valid if in the main article, not related posts
    m = re.search(r'\b(202\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b', text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # closing keyword + day month year: "closes 5 October 2026"
    m = re.search(
        rf'(?:clos(?:es?|ing)|deadline|due|submit(?:ted)?\s+by|applications?\s+close|open\s+until|until)[:\s]+(\d{{1,2}})\s+({_MONTHS})\s+(202\d)',
        text, re.IGNORECASE
    )
    if m:
        d = m.group(1).zfill(2)
        mo = _MONTH_NUM.get(m.group(2).lower()[:3], "")
        y = m.group(3)
        if mo:
            return f"{y}-{mo}-{d}"

    # closing keyword + month day year: "until October 5 2026"
    m = re.search(
        rf'(?:clos(?:es?|ing)|deadline|until|open\s+until)[:\s]+({_MONTHS})\s+(\d{{1,2}})(?:[,\s]+(202\d))?',
        text, re.IGNORECASE
    )
    if m:
        mo = _MONTH_NUM.get(m.group(1).lower()[:3], "")
        d = m.group(2).zfill(2)
        y = m.group(3) if m.group(3) else None
        if mo:
            if not y:
                from datetime import datetime
                from zoneinfo import ZoneInfo
                now = datetime.now(ZoneInfo("Australia/Sydney"))
                y = str(now.year)
                try:
                    from datetime import datetime as dt
                    if dt(int(y), int(mo), int(d)).date() < now.date():
                        y = str(int(y) + 1)
                except ValueError:
                    pass
            return f"{y}-{mo}-{d}"

    # bare "5 October 2026" anywhere (future years only)
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

    # bare "October 5, 2026"
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

    # closing keyword + no-year: "closes 2 August" / "Deadline: October 5"
    m = re.search(
        rf'(?:clos(?:es?|ing)|deadline|until)[:\s]+(?:(\d{{1,2}})\s+({_MONTHS})|({_MONTHS})\s+(\d{{1,2}}))',
        text, re.IGNORECASE
    )
    if m:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Australia/Sydney"))
        if m.group(1):  # day month
            d, mo_str = m.group(1).zfill(2), m.group(2)
        else:           # month day
            d, mo_str = m.group(4).zfill(2), m.group(3)
        mo = _MONTH_NUM.get(mo_str.lower()[:3], "")
        if mo:
            y = now.year
            try:
                from datetime import datetime as dt
                if dt(y, int(mo), int(d)).date() < now.date():
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
        return _not_relevant("Dropped: title matches noise keyword.")

    # also check summary for workshop/event signals when title is clean
    _DROP_SUMMARY = [
        "register now for free", "register to attend", "book your spot",
        "life drawing session", "weekly session", "weekly drawing",
        "drop-in session", "attend this workshop",
    ]
    summary_low = summary.lower()
    if any(kw in summary_low for kw in _DROP_SUMMARY):
        return _not_relevant("Dropped: summary matches event keyword.")

    # --- filter Artshow items to Australia-relevant only ---
    # Artshow feeds include many US/EU competitions with no Australian eligibility
    if source in ("Artshow.com Competitions", "Artshow.com International"):
        us_eu_signals = [
            ", tx", ", ny", ", ca", ", oh", ", sc", ", pa", ", mi",
            ", wa,", "greenville, sc", "wayne, pa", "muskegon", "sugar land",
            "miami university", "oxford, oh", "troy, oh",
            "los angeles, c", "lacda", "nyc4pa",
        ]
        if any(sig in text for sig in us_eu_signals):
            return _not_relevant("Dropped: US/EU-only competition.")
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
    # title-based overrides for common patterns that confuse keyword matching
    title_low = title.lower()
    category = "Other"
    if any(x in title_low for x in ["art prize", "art award", "photography prize",
                                      "sculpture prize", "painting prize", "drawing prize",
                                      "portrait prize", "landscape prize"]):
        category = "Prize"
    elif "fellowship" in title_low or "fellowships" == title_low.strip():
        category = "Fellowship"
    elif "residency" in title_low or "artist in residence" in title_low:
        category = "Residency"
    elif "scholarship" in title_low:
        category = "Scholarship"
    elif any(x in title_low for x in ["arts projects", "grant program", "micro grant",
                                        "development fund", "project fund", "matched funding"]):
        category = "Grant"
    else:
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

    # sanity check: if the extracted deadline is more than 30 days in the past,
    # it's likely an old round date from a page that hasn't updated yet — drop it
    if deadline:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            dl_date = datetime.strptime(deadline, "%Y-%m-%d").date()
            today = datetime.now(ZoneInfo("Australia/Sydney")).date()
            from datetime import timedelta
            if dl_date < today - timedelta(days=30):
                deadline = ""
        except ValueError:
            pass

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
