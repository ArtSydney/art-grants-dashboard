"""Discord notifications for art-openings-syd."""

import json
import os
import requests
from datetime import datetime, timezone

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

# Embed colors
COLOR_NEW = 0x6C5B7B       # Purple - new exhibition
COLOR_OPENING = 0xF67280   # Coral - opening tonight
COLOR_CLOSING = 0xE74C5E   # Red - closing soon
COLOR_DIGEST = 0x355C7D    # Navy - weekly digest

_webhook_warned = False


def send_embed(embed):
    """Send a single embed to Discord."""
    global _webhook_warned
    if not DISCORD_WEBHOOK_URL or not DISCORD_WEBHOOK_URL.startswith("https://"):
        if not _webhook_warned:
            print("[notify] No valid webhook URL, notifications disabled")
            _webhook_warned = True
        return
    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[notify] Error: {e}")


def notify_new_exhibition(record):
    """Send notification for a newly discovered exhibition."""
    title = record.get("title", "Untitled")
    venue = record.get("venue", "")
    suburb = record.get("suburb", "")
    start = record.get("start_date", "")
    end = record.get("end_date", "")
    opening = record.get("opening_date", "")
    opening_time = record.get("opening_time", "")
    website = record.get("website", "")
    artist = record.get("artist", "")
    desc = record.get("description", "")[:200]

    fields = []
    if venue:
        loc = venue
        if suburb:
            loc += f", {suburb}"
        fields.append({"name": "Venue", "value": loc, "inline": True})
    if artist:
        fields.append({"name": "Artist", "value": artist, "inline": True})
    if start:
        date_str = start
        if end:
            date_str += f" to {end}"
        fields.append({"name": "Dates", "value": date_str, "inline": True})
    if opening:
        op_str = opening
        if opening_time:
            op_str += f" at {opening_time}"
        fields.append({"name": "Opening", "value": op_str, "inline": True})

    embed = {
        "title": f"New: {title}",
        "description": desc if desc else None,
        "color": COLOR_NEW,
        "fields": fields,
        "url": website if website else None,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "footer": {"text": "Art Openings Sydney"},
    }
    embed = {k: v for k, v in embed.items() if v is not None}
    send_embed(embed)


def notify_opening_soon(record):
    """Send notification for exhibition opening tonight."""
    if record.get("opening_soon_sent"):
        return

    title = record.get("title", "Untitled")
    venue = record.get("venue", "")
    opening = record.get("opening_date", "")
    opening_time = record.get("opening_time", "")
    website = record.get("website", "")

    today = datetime.now(tz=timezone.utc).date()
    try:
        op_date = datetime.strptime(opening, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return

    if op_date != today:
        return

    desc = f"at {venue}" if venue else ""
    if opening_time:
        desc += f" | {opening_time}"

    embed = {
        "title": f"Opening TONIGHT: {title}",
        "description": desc,
        "color": COLOR_OPENING,
        "url": website if website else None,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "footer": {"text": "Art Openings Sydney"},
    }
    embed = {k: v for k, v in embed.items() if v is not None}
    send_embed(embed)
    record["opening_soon_sent"] = True


def notify_closing_soon(record):
    """Send notification for exhibition closing soon."""
    if record.get("closing_soon_sent"):
        return

    title = record.get("title", "Untitled")
    venue = record.get("venue", "")
    end = record.get("end_date", "")
    website = record.get("website", "")

    today = datetime.now(tz=timezone.utc).date()
    try:
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return

    days_left = (end_date - today).days
    if days_left < 0 or days_left > 3:
        return

    label = "LAST DAY" if days_left == 0 else f"Closing in {days_left} day(s)"

    embed = {
        "title": f"{label}: {title}",
        "description": f"at {venue}" if venue else "",
        "color": COLOR_CLOSING,
        "url": website if website else None,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "footer": {"text": "Art Openings Sydney"},
    }
    embed = {k: v for k, v in embed.items() if v is not None}
    send_embed(embed)
    record["closing_soon_sent"] = True


def check_alerts(state):
    """Run opening-tonight and closing-soon checks on all active records."""
    for key, rec in state.items():
        if key.startswith("__"):
            continue
        if rec.get("status") != "active":
            continue
        if rec.get("opening_date"):
            notify_opening_soon(rec)
        if rec.get("end_date"):
            notify_closing_soon(rec)