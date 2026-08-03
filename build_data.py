"""Write docs/data.json: the current open opportunities the dashboard renders.

Everything the dashboard shows is decided here, so filtering logic lives in one
place. We keep relevant, English items whose deadline hasn't passed. Eligibility
is NOT filtered out: 'unclear' items stay in and are badged on the front end,
which is what you asked for.
"""
import json
from datetime import date, datetime

from config import DATA_FILE, ART_FORMS, WILDCARD_FORMS, DROP_IF_NO_ART_FORM


def _active(rec):
    if not rec.get("relevant"):
        return False
    if not rec.get("english"):
        return False
    if DROP_IF_NO_ART_FORM and not rec.get("art_forms"):
        return False  # exclusively non-visual (or unclassified), drop it
    dl = rec.get("deadline")
    if dl:
        try:
            if datetime.strptime(dl, "%Y-%m-%d").date() < date.today():
                return False  # deadline already passed
        except ValueError:
            pass  # unparseable date, keep it rather than lose it
    return True


def _sort_key(rec):
    # dated items first, soonest deadline first; undated items last
    dl = rec.get("deadline")
    try:
        return (0, datetime.strptime(dl, "%Y-%m-%d").date())
    except (ValueError, TypeError):
        return (1, date.max)


def build(state):
    records = sorted((r for r in state.values() if _active(r)), key=_sort_key)
    # discipline chips the dashboard should offer: the specific media only, in
    # config order. Wildcards aren't chips; they match every chip instead.
    disciplines = [f for f in ART_FORMS if f not in WILDCARD_FORMS]
    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "count": len(records),
        "disciplines": disciplines,
        "wildcards": WILDCARD_FORMS,
        "items": records,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  wrote {len(records)} active items to {DATA_FILE.name}")
