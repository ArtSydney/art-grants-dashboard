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
    for chunk in _chunks(content, 1900):  # Discord caps content at 2000 chars
        requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk}, timeout=20)


def _chunks(text, size):
    buf = ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > size and buf:
            yield buf
            buf = ""
        buf += line + "\n"
    if buf.strip():
        yield buf


def _fmt(rec):
    lines = [f"**{rec['title']}**  ({rec.get('category', '?')} · {rec['source']})"]
    meta = []
    if rec.get("amount"):
        meta.append(rec["amount"])
    if rec.get("deadline"):
        meta.append(f"closes {rec['deadline']}")
    if rec.get("au_eligibility") == "unclear":
        meta.append("eligibility unclear")
    if meta:
        lines.append("  " + " · ".join(meta))
    if rec.get("link"):
        lines.append(f"  {rec['link']}")
    return "\n".join(lines)


def send_digest(new_records):
    """One message summarising everything new this run."""
    if not new_records:
        print("  no new items for the digest")
        return
    header = f"__**New arts opportunities — {date.today():%d %b %Y}**__ ({len(new_records)} new)\n"
    body = "\n\n".join(_fmt(r) for r in new_records)
    _post(header + "\n" + body)
    print(f"  digest sent ({len(new_records)} items)")


def send_closing_soon(rec):
    """An urgent, per-item ping when a deadline is nearly here."""
    n = days_left(rec.get("deadline"))
    if n is None:
        return
    when = "today" if n == 0 else f"in {n} day{'s' if n != 1 else ''}"
    msg = (
        f"\u23f0 **Closing {when}:** {rec['title']} ({rec.get('category', '?')})\n"
        f"  {rec.get('amount', '')}  {rec.get('link', '')}"
    )
    _post(msg)
    print(f"  closing-soon ping: {rec['title'][:50]}")
