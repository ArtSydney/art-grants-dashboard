"""Write docs/data.json: the current open opportunities the dashboard renders.

Everything the dashboard shows is decided here, so filtering logic lives in one
place. We keep relevant, English items whose deadline hasn't passed. Eligibility
is NOT filtered out: 'unclear' items stay in and are badged on the front end,
which is what you asked for.

All timestamps use Sydney time (Australia/Sydney) so the "last updated" line
on the dashboard is correct whether the pipeline runs locally or in GitHub Actions.
"""
import json
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


def build(state):
    records = sorted((r for r in state.values() if _active(r)), key=_sort_key)
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
