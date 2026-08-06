"""One run of the whole pipeline: fetch, classify new items, notify, rebuild data.

    export ANTHROPIC_API_KEY=sk-ant-...
    export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   # optional
    python main.py

The Discord webhook is optional. Without it, notifications are skipped so you
can test the pipeline quietly. Items already in seen.json are never re-processed,
so re-running is cheap and safe.
"""
import sys
from datetime import date

from config import CLOSING_SOON_DAYS
from fetch import fetch_all, load_sources
from classify import classify
from state import load_state, save_state
from notify import send_digest, send_closing_soon, days_left
from build_data import build
from prefilter import looks_like_opportunity


def run():
    print("1. Fetching sources")
    raw = fetch_all()

    # Sources flagged "prefilter": true get the no-API gate (the noisy news feed).
    noisy = {s["name"] for s in load_sources() if s.get("prefilter")}

    print("2. Classifying new items")
    state = load_state()
    new_records = []
    for item in raw:
        existing = state.get(item["id"])
        refresh = item.pop("refresh", False)   # page sources re-check every run
        if existing and not refresh:
            continue  # seen in a previous run, skip
        if item["source"] in noisy and not looks_like_opportunity(item):
            # record as seen-and-skipped so we never pay to look at it again
            item.pop("meta_desc", None)
            state[item["id"]] = {**item, "relevant": False, "prefiltered": True}
            continue
        result = classify(item)
        if result is None:
            continue
        item.pop("meta_desc", None)   # raw scratch field; description is derived from it
        record = {
            **item,
            **result,
            "first_seen": (existing or {}).get("first_seen", str(date.today())),
            "closing_soon_sent": (existing or {}).get("closing_soon_sent", False),
        }
        state[item["id"]] = record
        if not existing and result.get("relevant") and result.get("english"):
            new_records.append(record)
        print(f"  + {item['title'][:60]}  ->  "
              f"{result.get('category')} / {result.get('au_eligibility')}")

    print("3. Notifications")
    send_digest(new_records)
    for rec in state.values():
        if rec.get("closing_soon_sent"):
            continue
        if not (rec.get("relevant") and rec.get("english")):
            continue
        n = days_left(rec.get("deadline"))
        if n is not None and 0 <= n <= CLOSING_SOON_DAYS:
            send_closing_soon(rec)
            rec["closing_soon_sent"] = True

    print("4. Building dashboard data")
    build(state)

    save_state(state)
    print("Done.")


if __name__ == "__main__":
    run()
