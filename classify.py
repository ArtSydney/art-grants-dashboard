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
    "terms and conditions", "terms & conditions",  # T&C pages, not opportunities
    "artist opportunities", "funding opportunities",  # generic landing pages
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
    # also handles "Entries close > 6pm 9th August 2026" (arrow + optional time)
    m = re.search(
        rf'(?:clos(?:es?|ing)|deadline|due|submit(?:ted)?\s+by|applications?\s+close|open\s+until|until)'
        rf'[:\s>]+(?:\d{{1,2}}(?:am|pm|:\d{{2}}(?:am|pm)?)?\s+)?'
        rf'(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})\s+(202\d)',
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
    """Return first dollar amount found, e.g. '$30,000'.

    Entry/application fees are blanked out first so the prize/grant figure is
    never confused with the cost to enter (a fee often sits above the prize on
    the page, and the old first-match rule would grab it).
    """
    text = _FEE_SPAN_RE.sub(" ", text)
    m = re.search(r'AUD\s*\$[\d,]+|\$[\d,]+(?:\s*(?:million|k))?\b', text, re.IGNORECASE)
    if not m:
        return ""
    val = m.group(0).strip()
    # normalise AUD $50,000 -> $50,000
    val = re.sub(r'^AUD\s*', '', val, flags=re.IGNORECASE)
    return val


# ---------------------------------------------------------------------------
# Entry fee: we only surface "Free". A paid or unknown fee is left blank, so
# the dashboard can tag and filter free-to-enter calls without ever guessing a
# dollar cost (which is unreliable and usually not on the page we fetch).
# ---------------------------------------------------------------------------

# Phrases that mean "free to enter". Anchored to entry/application context so a
# stray "free" (free workshop, free to visit) never trips it.
_FREE_ENTRY_SIGNALS = [
    "free to enter", "free entry", "no entry fee", "entry is free",
    "entry fee: free", "entry fee is free", "no cost to enter",
    "free to apply", "no application fee", "no submission fee",
    "free to submit", "no fee to enter", "entry: free",
]

# Fee figures in three shapes, used only to blank them out of the text before
# the prize amount is read. We do not report these as the entry fee.
_FEE_SPAN_RE = re.compile(
    r'\$\s?\d+(?:\.\d{2})?\s*per\s+(?:entry|work|artwork|image|piece|submission)'
    r'|\$\s?\d+(?:\.\d{2})?\s*(?:entry|application|submission|registration)\s+fee'
    r'|(?:entry fee|entry cost|application fee|submission fee|registration fee|'
    r'cost to enter|cost of entry|fee to enter)(?:\s+(?:is|of|:))?\s*\$\s?\d+(?:\.\d{2})?',
    re.IGNORECASE)


def _extract_entry_fee(text):
    """Return 'Free' when the text clearly says entry is free, else '' .
    Paid and unknown both map to '' so nothing but free is ever tagged."""
    low = text.lower()
    return "Free" if any(sig in low for sig in _FREE_ENTRY_SIGNALS) else ""


# ---------------------------------------------------------------------------
# Description sentence selection
# ---------------------------------------------------------------------------

# Boilerplate a page's meta/body sometimes leads with — never use as description.
_DESC_BOILERPLATE = (
    "acknowledge", "traditional custodians", "traditional owners",
    "always was and always will be", "pay respect", "pay our respect",
    "we recognise", "we pay our", "elders past and present",
)


def _good_sentence(s):
    """True if s reads like a real descriptive sentence — not boilerplate, not a
    navigation/year list, not a stray fragment. Guards against junk like an
    archive index ('Continue 2026 2025 2024 …') becoming the card description."""
    s = s.strip()
    if len(s) < 25:
        return False
    low = s.lower()
    if any(b in low for b in _DESC_BOILERPLATE):
        return False
    tokens = s.split()
    if len(tokens) < 5:
        return False
    # need enough real word-tokens (3+ alphabetic chars) vs numbers/short bits —
    # a year list or nav strip fails this because it's mostly numeric tokens
    wordish = sum(1 for t in tokens if sum(c.isalpha() for c in t) >= 3)
    if wordish < 4:
        return False
    if wordish / len(tokens) < 0.5:
        return False
    return True


def _first_good_sentence(text):
    """Return the first sentence in text that passes _good_sentence, or ''."""
    # collapse archive/nav year runs ("Continue 2026 2025 2024 … 1993 1") that
    # AGNSW-style pages embed with no punctuation — they glue onto the real
    # sentence after them and would otherwise swallow it. A lone 1-2 digit page
    # number sometimes trails the run, so sweep that too.
    text = re.sub(r'(?:\b(?:19|20)\d{2}\b[\s,]*){3,}(?:\b\d{1,2}\b\s*)?', ' ', text or "")
    text = re.sub(r'\bContinue\b\s*', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    for sent in re.split(r'(?<=[.!?])\s', text):
        s = sent.strip()
        if _good_sentence(s):
            return s[:180]
    return ""


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
        # explicitly closed calls — page still live but round has ended
        "entries are closed", "entries are now closed",
        "submissions are closed", "submissions are now closed",
        "applications are closed", "applications are now closed",
        "this prize is now closed", "prize is now closed",
        "competition is now closed", "competition is closed",
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

    # --- category fallback: title ends with a category word ---
    # Catches "Archibald Prize", "Wynne Prize", "Josephine Ulrick ... Award" etc
    # where the title alone is the signal but keyword matching on full text fails
    # because the page is thin or archive-heavy.
    if category == "Other":
        _TITLE_SUFFIX_MAP = [
            ("Prize",       ["prize", "award", "awards"]),
            ("Fellowship",  ["fellowship", "fellowships"]),
            ("Residency",   ["residency", "residencies"]),
            ("Scholarship", ["scholarship", "scholarships", "bursary"]),
            ("Grant",       ["grant", "grants", "fund", "funding"]),
            ("Commission",  ["commission"]),
        ]
        import re as _re
        title_stripped = _re.sub(r'\s+20\d\d$', '', title_low.rstrip(".")).rstrip()
        title_words = title_stripped.split()
        if title_words:
            last = title_words[-1]
            for cat, suffixes in _TITLE_SUFFIX_MAP:
                if last in suffixes:
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

    # If we found a deadline that's well in the past, the opportunity has closed
    # (or the page shows a stale prior-round date). Drop it entirely rather than
    # blanking the date — a blanked date would make a closed call look like an
    # open, undated one and it would linger on the dashboard forever. Genuinely
    # undated opportunities (no date found at all) are unaffected and still show.
    # The 30-day grace keeps very-recently-closed items visible briefly.
    if deadline:
        try:
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            dl_date = datetime.strptime(deadline, "%Y-%m-%d").date()
            today = datetime.now(ZoneInfo("Australia/Sydney")).date()
            if dl_date < today - timedelta(days=30):
                return _not_relevant("Deadline passed.")
        except ValueError:
            pass

    # --- entry fee (free-only; blank otherwise) ---
    entry_fee = _extract_entry_fee(summary + " " + title)

    # --- amount (prize / grant value) ---
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

    # --- one-line description ---
    # Prefer the page's own meta description (clean, human-written), but only if
    # it reads like a real sentence — some pages set it to just a site or gallery
    # name ("Brunswick Street Gallery"), or lead with an Acknowledgement of
    # Country, which is respectful but not a description of the opportunity.
    # Fall back to extracting the first real sentence from scraped text.
    description = ""
    meta_desc = (item.get("meta_desc") or "").strip()

    # Prefer the page's own meta description, taking its first genuinely
    # descriptive sentence (skips Acknowledgements of Country, year lists, etc).
    if meta_desc:
        description = _first_good_sentence(meta_desc)

    if not description:
        # strip Artsoz metadata prefix e.g. "Location: QLD. Medium: X. Type: Y. Tags: Z."
        # loop because there can be several segments back-to-back
        prev = None
        clean = summary
        while prev != clean:
            prev = clean
            clean = re.sub(r'^(?:Location|Medium|Type|Tags):[^.]+\.\s*', '', clean, flags=re.IGNORECASE).strip()
        # strip everything up to and including a nav marker (single-line safe)
        clean = re.sub(r'^.*?skip to (?:main )?content\s*', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'^(?:please note\s*:)\s*', '', clean, flags=re.IGNORECASE).strip()
        # strip common Creative Australia listing prefixes e.g. "Multi-art form Open"
        clean = re.sub(r'^(?:multi-art form|visual arts|literature|music|theatre|dance|first nations)\s+(?:open|closed)\s+', '', clean, flags=re.IGNORECASE).strip()
        # strip a leading email address
        clean = re.sub(r'^[\w.\-]+@[\w.\-]+\s*', '', clean).strip()
        # strip repeated page title from the start
        clean = re.sub(r'^' + re.escape(title[:50]) + r'[^\w]*', '', clean, flags=re.IGNORECASE).strip()
        # strip pipe-separated site name prefix e.g. "Creative Australia | Skip..."
        clean = re.sub(r'^[^|]{0,60}\|\s*', '', clean).strip()
        # take the first genuinely descriptive sentence (skips boilerplate,
        # nav strips, and year/archive lists that aren't real prose)
        description = _first_good_sentence(clean)

    return {
        "relevant":       True,
        "english":        True,
        "category":       category,
        "au_eligibility": au_eligibility,
        "location_scope": location_scope,
        "eligibility_note": "",
        "deadline":       deadline,
        "amount":         amount,
        "entry_fee":      entry_fee,
        "description":    description,
        "curator":        "",
        "judge":          "",
        "art_forms":      art_forms,
    }


def _not_relevant(reason=""):
    return {
        "relevant": False, "english": True,
        "category": "Other", "au_eligibility": "unclear",
        "location_scope": "Unknown", "eligibility_note": "",
        "deadline": "", "amount": "", "entry_fee": "", "summary": reason,
        "curator": "", "judge": "", "art_forms": [],
    }
