"""One run of the whole pipeline: fetch, classify new items, notify, rebuild data.

    export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   # optional
    python main.py

The Discord webhook is optional. Without it, notifications are skipped so you
can test the pipeline quietly.

State architecture
------------------
seen.json is keyed by item ID (SHA1 of URL). Each record carries a "status" field:

  active        -- relevant, open, shows on the dashboard
  needs_review  -- relevant but no deadline and from Google search; hidden until
                   a future run picks up a date from the page
  closed        -- deadline passed or explicitly closed; hidden, never re-fetched
  suppressed    -- dropped by classifier (not relevant, 404, etc); kept so we
                   never re-fetch

Deduplication happens at state-write time (not render time), so closing-soon
notifications and digest counts are always based on the canonical deduplicated
set. The canonical record for each prize is tracked in a separate signature ->
id index within state under the special key "__dedup_index__".
"""
from datetime import date

from config import CLOSING_SOON_DAYS
from fetch import fetch_all, load_sources
from classify import classify
from state import load_state, save_state
from notify import send_digest, send_closing_soon, days_left
from build_data import build
from prefilter import looks_like_opportunity
import dedup as _dedup


def _assign_status(record):
    """Derive the status field from classifier output and source.

    active        -- relevant, English, and either has a deadline or is from a
                     trusted source (non-Google), so we trust it is open
    needs_review  -- relevant, English, no deadline, from Google search only;
                     hide until a future run can confirm it is open
    closed        -- not relevant (classifier dropped it)
    suppressed    -- not English or some other hard exclude
    """
    if not record.get("relevant"):
        return "suppressed"
    if not record.get("english"):
        return "suppressed"
    # Google-sourced items with no deadline are unconfirmed -- park them
    if (not record.get("deadline")
            and record.get("source") == "Google: Australian art prizes"):
        return "needs_review"
    return "active"


def run():
    print("1. Fetching sources")
    raw = fetch_all()

    noisy = {s["name"] for s in load_sources() if s.get("prefilter")}

    print("2. Classifying new items")
    state = load_state()

    # The dedup index maps dedup signature (as a sorted tuple of words) to the
    # canonical record ID currently held in state for that prize.
    # Stored in state under the reserved key "__dedup_index__".
    dedup_index = state.pop("__dedup_index__", {})  # sig_key -> canonical_id

    new_records = []  # new active items for the digest (post-dedup)

    for item in raw:
        existing = state.get(item["id"])
        refresh = item.pop("refresh", False)

        if existing and not refresh:
            # Already processed. If it came back as a refresh source, re-classify
            # below; otherwise skip entirely.
            continue

        if item["source"] in noisy and not looks_like_opportunity(item):
            item.pop("meta_desc", None)
            state[item["id"]] = {
                **item,
                "relevant": False,
                "status": "suppressed",
                "prefiltered": True,
            }
            continue

        result = classify(item)
        if result is None:
            continue

        item.pop("meta_desc", None)
        record = {
            **item,
            **result,
            "first_seen": (existing or {}).get("first_seen", str(date.today())),
            "closing_soon_sent": (existing or {}).get("closing_soon_sent", False),
        }
        record["status"] = _assign_status(record)

        # --- dedup at write time ---
        sig = _dedup.signature(record.get("title"))
        sig_key = "|".join(sorted(sig)) if sig else None

        if sig_key and sig_key in dedup_index:
            canonical_id = dedup_index[sig_key]
            canonical = state.get(canonical_id)
            if canonical and canonical_id != item["id"]:
                # merge: pick the better record, carry sticky fields
                merged = _dedup.better_record(canonical, record)
                if merged["id"] == record["id"]:
                    # new record won -- replace canonical, retire old id
                    state[item["id"]] = merged
                    # mark the old canonical as superseded (keep in state so
                    # we never re-fetch it, but suppress from dashboard)
                    state[canonical_id] = {
                        **canonical,
                        "status": "suppressed",
                        "superseded_by": item["id"],
                    }
                    dedup_index[sig_key] = item["id"]
                    print(f"  ~ {item['title'][:55]}  ->  merged (new record won)")
                else:
                    # existing canonical won -- update it with any improvements
                    # (sticky fields already merged in better_record)
                    state[canonical_id] = merged
                    # record the new id as suppressed so we skip it next run
                    state[item["id"]] = {
                        **record,
                        "status": "suppressed",
                        "superseded_by": canonical_id,
                    }
                    print(f"  ~ {item['title'][:55]}  ->  merged (existing won)")
                continue  # do not add to new_records; canonical handles it
        else:
            # first time we see this prize -- register it as canonical
            if sig_key:
                dedup_index[sig_key] = item["id"]

        state[item["id"]] = record

        is_new = not existing
        if is_new and record["status"] == "active":
            new_records.append(record)

        status_label = record["status"]
        print(f"  + {item['title'][:55]}  ->  "
              f"{result.get('category')} / {result.get('au_eligibility')} / {status_label}")

    print("3. Notifications")
    send_digest(new_records)

    # closing-soon: iterate canonical active records only (dedup already done)
    canonical_ids = set(dedup_index.values())
    for rec_id, rec in state.items():
        if rec_id not in canonical_ids:
            continue
        if rec.get("closing_soon_sent"):
            continue
        if rec.get("status") != "active":
            continue
        n = days_left(rec.get("deadline"))
        if n is not None and 0 <= n <= CLOSING_SOON_DAYS:
            send_closing_soon(rec)
            rec["closing_soon_sent"] = True

    print("4. Building dashboard data")
    build(state)

    # put dedup index back before saving
    state["__dedup_index__"] = dedup_index
    save_state(state)
    print("Done.")


if __name__ == "__main__":
    run()
