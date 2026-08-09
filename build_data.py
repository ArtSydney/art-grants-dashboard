"""Write docs/data.json: the current open opportunities the dashboard renders.

Everything the dashboard shows is decided here. We keep active items only --
status field is the single source of truth set by main.py at classify time.
Eligibility is NOT filtered: 'unclear' items stay in and are badged on the
front end.

All timestamps use Sydney time (Australia/Sydney) so the "last updated" line
on the dashboard is correct whether the pipeline runs locally or in GitHub Actions.

A second-pass dedup runs here as a safety net for records that were already in
state before the new dedup-at-write-time logic was introduced, and for refresh
sources that can produce multiple versions of the same record in one run.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from config import DATA_FILE, ART_FORMS, WILDCARD_FORMS, DROP_IF_NO_ART_FORM
import dedup as _dedup

SYDNEY = ZoneInfo("Australia/Sydney")


def _today():
    return datetime.now(SYDNEY).date()


def _sort_key(rec):
    dl = rec.get("deadline")
    try:
        return (0, datetime.strptime(dl, "%Y-%m-%d").date())
    except (ValueError, TypeError):
        return (1, datetime(9999, 12, 31).date())


def build(state):
    # active records only -- status is the single source of truth
    active = [
        r for r in state.values()
        if isinstance(r, dict)           # guard against __dedup_index__ sentinel
        and r.get("status") == "active"
        and r.get("relevant")
        and r.get("english")
        and not (DROP_IF_NO_ART_FORM and not r.get("art_forms"))
    ]

    # safety-net dedup for any pre-migration records or same-run refresh dupes
    deduped, dropped = _dedup.dedup(active)
    if dropped:
        print(f"  de-duplicated {dropped} record(s) at render time")

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
