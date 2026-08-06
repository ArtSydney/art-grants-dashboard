"""Write docs/data.json: the current open opportunities the dashboard renders.

Everything the dashboard shows is decided here, so filtering logic lives in one
place. We keep relevant, English items whose deadline hasn't passed. Eligibility
is NOT filtered out: 'unclear' items stay in and are badged on the front end,
which is what you asked for.

All timestamps use Sydney time (Australia/Sydney) so the "last updated" line
on the dashboard is correct whether the pipeline runs locally or in GitHub Actions.
"""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from config import DATA_FILE, ART_FORMS, WILDCARD_FORMS, DROP_IF_NO_ART_FORM

SYDNEY = ZoneInfo("Australia/Sydney")


def _today():
    return datetime.now(SYDNEY).date()


def _active(rec):
    if not rec.get("relevant"):
        return False
    if not rec.get("english"):
        return False
    if DROP_IF_NO_ART_FORM and not rec.get("art_forms"):
        return False
    dl = rec.get("deadline")
    if dl:
        try:
            if datetime.strptime(dl, "%Y-%m-%d").date() < _today():
                return False
        except ValueError:
            pass
    return True


def _sort_key(rec):
    dl = rec.get("deadline")
    try:
        return (0, datetime.strptime(dl, "%Y-%m-%d").date())
    except (ValueError, TypeError):
        return (1, datetime(9999, 12, 31).date())


# ---------------------------------------------------------------------------
# De-duplication
#
# The same prize often arrives from several sources (an aggregator, a Google
# result, a registry), each as its own record with its own URL and id. We
# collapse those to one card so the dashboard doesn't show the same opportunity
# two or three times.
#
# Matching is deliberately CONSERVATIVE: two records are only treated as the
# same opportunity when their DISTINCTIVE title words match exactly (after
# stripping years, punctuation and generic art-world filler like "art"/"prize").
# We tested looser "subset" matching against real data and it wrongly merged
# different prizes that merely shared a word ("National Photography Prize" vs
# "Bowness Photography Prize", "Mosman Art Prize" vs "Mosman Youth Art Prize"),
# so subset matching is intentionally NOT used. Missing the odd real duplicate
# is a far smaller harm than merging two genuinely different prizes.
# ---------------------------------------------------------------------------

# Generic words carry no identifying signal — stripped before comparing titles.
_DEDUP_GENERIC = {
    "the", "art", "arts", "prize", "prizes", "award", "awards", "competition",
    "call", "callout", "open", "for", "of", "a", "an", "and", "entries",
    "emerging", "artist", "artists", "international", "national", "australian",
    "australia", "2d", "edition", "exhibition", "program", "programme",
    "annual", "contemporary", "fine",
}

# Source preference when two records tie — earlier = preferred. Aggregators with
# reliable structured detail pages rank above bare registry/search hits.
_SOURCE_RANK = {
    "BNE Art: Opportunities": 0,
    "Creative Australia": 1,
    "Calendar for Artists": 2,
    "Artsoz prize registry": 3,
    "Google: Australian art prizes": 4,
}


def _dedup_signature(title):
    """Frozenset of a title's distinctive words, or None if nothing distinctive
    remains (in which case the record is never merged — safer to keep it)."""
    t = (title or "").lower()
    t = re.sub(r"20\d\d", " ", t)            # strip 4-digit years
    t = re.sub(r"[^a-z0-9 ]", " ", t)        # strip punctuation
    words = frozenset(w for w in t.split() if w and w not in _DEDUP_GENERIC)
    return words or None


def _better_record(a, b):
    """Return whichever of two duplicate records should be kept.

    Preference order:
      1. has a deadline (a dated opportunity is more useful than an undated one)
      2. longer description (more informative card)
      3. lower source rank (more reliable source)
    """
    def score(r):
        has_dl = 1 if r.get("deadline") else 0
        desc_len = len(r.get("description") or "")
        src = _SOURCE_RANK.get(r.get("source"), 99)
        # higher tuple sorts as "better"; negate src so lower rank wins
        return (has_dl, desc_len, -src)
    return a if score(a) >= score(b) else b


def _dedup(records):
    """Collapse duplicate opportunities to one record each, preserving order."""
    best_by_sig = {}     # signature -> chosen record
    order = []           # signatures in first-seen order
    passthrough = []     # records with no distinctive signature (never merged)

    for rec in records:
        sig = _dedup_signature(rec.get("title"))
        if sig is None:
            passthrough.append(rec)
            continue
        if sig in best_by_sig:
            best_by_sig[sig] = _better_record(best_by_sig[sig], rec)
        else:
            best_by_sig[sig] = rec
            order.append(sig)

    deduped = [best_by_sig[sig] for sig in order] + passthrough
    dropped = len(records) - len(deduped)
    if dropped:
        print(f"  de-duplicated {dropped} record(s)")
    return deduped


def build(state):
    active = [r for r in state.values() if _active(r)]
    deduped = _dedup(active)
    records = sorted(deduped, key=_sort_key)
    disciplines = [f for f in ART_FORMS if f not in WILDCARD_FORMS]
    now_sydney = datetime.now(SYDNEY)
    payload = {
        "generated": now_sydney.isoformat(timespec="seconds"),
        "count": len(records),
        "disciplines": disciplines,
        "wildcards": WILDCARD_FORMS,
        "items": records,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  wrote {len(records)} active items to {DATA_FILE.name}")
