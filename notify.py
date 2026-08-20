"""Discord notifications: a daily digest of new items, plus a closing-soon ping.

If DISCORD_WEBHOOK_URL isn't set, everything here quietly no-ops, so local test
runs don't spam a channel.
"""
from datetime import date, datetime

import requests

from config import DISCORD_WEBHOOK_URL


def days_left(deadline):
    """Whole days from today until the deadline, or None if there's no valid date."""
    if not deadline:
        return None
    try:
        d = datetime.strptime(deadline, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - date.today()).days


def _post(content):
    if not DISCORD_WEBHOOK_URL:
        print("  (no DISCORD_WEBHOOK_URL, skipping Discord)")
        return
    for chunk in _chunks(content, 1900):
        requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk}, timeout=20)


def _post_embeds(content, embeds):
    if not DISCORD_WEBHOOK_URL:
        print("  (no DISCORD_WEBHOOK_URL, skipping Discord)")
        return
    payload = {}
    if content:
        payload["content"] = content
    for i in range(0, len(embeds), 10):
        chunk_payload = dict(payload)
        chunk_payload["embeds"] = embeds[i:i + 10]
        if i > 0:
            chunk_payload.pop("content", None)
        requests.post(DISCORD_WEBHOOK_URL, json=chunk_payload, timeout=20)


def _chunks(text, size):
    buf = ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > size and buf:
            yield buf
            buf = ""
        buf += line + "\n"
    if buf.strip():
        yield buf


def _embed_color(deadline):
    n = days_left(deadline)
    if n is None:
        return 0x5865F2
    if n < 14:
        return 0xED4245
    if n < 30:
        return 0xFAA61A
    return 0x3BA55D


def _embed(rec):
    n = days_left(rec.get("deadline"))
    fields = []
    if rec.get("amount"):
        fields.append({"name": "Prize", "value": rec["amount"], "inline": True})
    entry = "Free" if str(rec.get("entry_fee") or "").lower() == "free" else "Open"
    if rec.get("deadline"):
        if n is None:
            days_str = ""
        elif n < 0:
            days_str = " · closed"
        elif n == 0:
            days_str = " · closes today"
        else:
            warning = " ⚠️" if n < 14 else ""
            days_str = f" · {n} days left{warning}"
        fields.append({"name": "Closes", "value": rec["deadline"] + days_str, "inline": True})
    fields.append({"name": "Entry", "value": entry, "inline": True})
    if rec.get("au_eligibility") == "unclear":
        fields.append({"name": "Eligibility", "value": "Unclear", "inline": True})

    _SOURCE_NAMES = {
        "Google: Australian art prizes": "via Google search",
        "BNE Art: Opportunities": "BNE Art",
        "Calendar for Artists": "Calendar for Artists",
        "Artsoz prize registry": "Artsoz",
        "Creative Australia": "Creative Australia",
        "Neon Marketplace": "Neon Marketplace",
        "ArtsHub": "ArtsHub",
    }
    source_label = _SOURCE_NAMES.get(rec["source"], rec["source"])
    embed = {
        "title": rec["title"],
        "color": _embed_color(rec.get("deadline")),
        "fields": fields,
        "footer": {"text": f"{rec.get('category', '?')} · Source: {source_label}"},
    }
    if rec.get("link"):
        embed["url"] = rec["link"]
    if rec.get("description"):
        embed["description"] = rec["description"]
    return embed


def send_digest(new_records):
    """One message summarising everything new this run."""
    if not new_records:
        print("  no new items for the digest")
        return
    header = f"__**New arts opportunities — {date.today():%d %b %Y}**__ ({len(new_records)} new)"
    embeds = [_embed(r) for r in new_records]
    _post_embeds(header, embeds)
    print(f"  digest sent ({len(new_records)} items)")


def send_closing_soon(rec):
    """An urgent, per-item ping when a deadline is nearly here."""
    n = days_left(rec.get("deadline"))
    if n is None:
        return
    when = "today" if n == 0 else f"in {n} day{'s' if n != 1 else ''}"
    days_str = "closes today" if n == 0 else f"{n} day{'s' if n != 1 else ''} left \u26a0\ufe0f"

    fields = []
    if rec.get("amount"):
        fields.append({"name": "Prize", "value": rec["amount"], "inline": True})
    if rec.get("deadline"):
        fields.append({"name": "Closes", "value": f"{rec['deadline']} \u00b7 {days_str}", "inline": True})
    entry = "Free" if str(rec.get("entry_fee") or "").lower() == "free" else "Open"
    fields.append({"name": "Entry", "value": entry, "inline": True})

    _SOURCE_NAMES = {
        "Google: Australian art prizes": "via Google search",
        "BNE Art: Opportunities": "BNE Art",
        "Calendar for Artists": "Calendar for Artists",
        "Artsoz prize registry": "Artsoz",
        "Creative Australia": "Creative Australia",
        "Neon Marketplace": "Neon Marketplace",
        "ArtsHub": "ArtsHub",
    }
    source_label = _SOURCE_NAMES.get(rec["source"], rec["source"])

    embed = {
        "title": f"\u23f0 Closing {when}",
        "description": rec["title"],
        "color": 0xED4245,
        "fields": fields,
        "footer": {"text": f"{rec.get('category', '?')} \u00b7 Source: {source_label}"},
    }
    if rec.get("link"):
        embed["url"] = rec["link"]

    _post_embeds(None, [embed])
    print(f"  closing-soon ping: {rec['title'][:50]}")
