"""Shared de-duplication logic used by both main.py (at state-write time)
and build_data.py (at render time as a safety net).

The same prize often arrives from several sources (an aggregator, a Google
result, a registry), each as its own record with its own URL and id. We
collapse those to one canonical record so the dashboard never shows the same
opportunity twice, and so closing-soon notifications fire exactly once.

Matching is deliberately CONSERVATIVE: two records are only treated as the
same opportunity when their DISTINCTIVE title words match exactly (after
stripping years, punctuation and generic art-world filler like "art"/"prize").
Subset matching is intentionally NOT used -- it wrongly merged different prizes
that shared a word ("Mosman Art Prize" vs "Mosman Youth Art Prize").
Missing a real duplicate is a far smaller harm than merging two different prizes.
"""
import re

# Generic words carry no identifying signal -- stripped before comparing titles.
DEDUP_GENERIC = {
    "the", "art", "arts", "prize", "prizes", "award", "awards", "competition",
    "call", "callout", "open", "for", "of", "a", "an", "and", "entries",
    "emerging", "artist", "artists", "international", "national", "australian",
    "australia", "2d", "edition", "exhibition", "program", "programme",
    "annual", "contemporary", "fine",
}

# Source preference when two records tie -- earlier = preferred.
# Aggregators with reliable structured detail pages rank above bare registry/search hits.
SOURCE_RANK = {
    "BNE Art: Opportunities": 0,
    "Creative Australia": 1,
    "Calendar for Artists": 2,
    "Artsoz prize registry": 3,
    "Google: Australian art prizes": 4,
}


def signature(title):
    """Frozenset of a title's distinctive words, or None if nothing distinctive
    remains (record is never merged in that case -- safer to keep it)."""
    t = (title or "").lower()
    t = re.sub(r"20\d\d", " ", t)        # strip 4-digit years
    t = re.sub(r"[^a-z0-9 ]", " ", t)   # strip punctuation
    words = frozenset(w for w in t.split() if w and w not in DEDUP_GENERIC)
    return words if words else None


def better_record(a, b):
    """Return whichever of two duplicate records should be kept, carrying
    forward sticky fields (closing_soon_sent, first_seen) from the loser
    so they are never accidentally dropped when a better record wins.

    Preference order:
      1. has a deadline (a dated record is more useful than an undated one)
      2. longer description (more informative card)
      3. lower source rank (more reliable source)
    """
    def score(r):
        has_dl = 1 if r.get("deadline") else 0
        desc_len = len(r.get("description") or "")
        src = SOURCE_RANK.get(r.get("source"), 99)
        return (has_dl, desc_len, -src)

    winner, loser = (a, b) if score(a) >= score(b) else (b, a)

    # carry forward sticky fields from the loser so they are never lost
    merged = dict(winner)
    if loser.get("closing_soon_sent"):
        merged["closing_soon_sent"] = True
    # keep the earliest first_seen across both records
    fs_winner = winner.get("first_seen") or ""
    fs_loser  = loser.get("first_seen") or ""
    if fs_loser and (not fs_winner or fs_loser < fs_winner):
        merged["first_seen"] = fs_loser

    return merged


def dedup(records):
    """Collapse duplicate opportunities to one record each, preserving
    first-seen order. Returns (deduped_list, dropped_count)."""
    best_by_sig = {}   # signature -> chosen record
    order = []         # signatures in first-seen order
    passthrough = []   # records with no distinctive signature (never merged)

    for rec in records:
        sig = signature(rec.get("title"))
        if sig is None:
            passthrough.append(rec)
            continue
        if sig in best_by_sig:
            best_by_sig[sig] = better_record(best_by_sig[sig], rec)
        else:
            best_by_sig[sig] = rec
            order.append(sig)

    deduped = [best_by_sig[sig] for sig in order] + passthrough
    dropped = len(records) - len(deduped)
    return deduped, dropped
