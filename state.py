"""Persist everything we've processed, keyed by item id.

seen.json is both the dedup ledger (so each listing is classified and notified
once) and the full record store the dashboard is built from. Commit it to the
repo so runs on different machines share the same memory.
"""
import json

from config import STATE_FILE


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
