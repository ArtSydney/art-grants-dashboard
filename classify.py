"""Turn one raw item into structured fields with Claude Haiku.

Four targeted fixes based on live page curls:
1. 404/page-not-found pages are skipped before hitting the API.
2. Workshops, info sessions, delivery-partner tenders, and knowledge-series
   events are explicitly listed as not relevant in the prompt.
3. Music/record/publishing items must return art_forms [] — the prompt now
   gives concrete examples of non-visual keywords to watch for.
4. Australian location in metadata ("Location: NSW, Australia") is a strong
   signal: the prompt instructs the model to infer au_eligibility = "eligible"
   and location_scope = "Australia" from it.
"""
import json

from anthropic import Anthropic

from config import CLASSIFY_MODEL, MAX_TOKENS, ART_FORMS

client = Anthropic()

# Strings that indicate the page returned a 404 rather than real content.
_NOT_FOUND_SIGNALS = (
    "page not found",
    "could not be found",
    "404",
    "the requested page",
)

SYSTEM = """You classify arts funding listings for a dashboard used by \
visual artists based in Australia. You are given a listing's source, title \
and summary. Reply with ONE JSON object and nothing else: no prose, no \
markdown, no code fences.

Fields:
- relevant (boolean): true ONLY if this is a real opportunity a visual \
artist can apply for: grant, scholarship, prize, award, residency, \
fellowship, or commission. Set false for ALL of the following — news, \
reviews, interviews, opinion pieces, job vacancies, advertisements, \
workshops, info sessions, webinars, knowledge-series events, fundraising \
training sessions, delivery-partner tenders, "how to apply" guides, \
multi-year investment frameworks, and any opportunity exclusively for \
organisations (not individuals). If the title or summary contains words \
like "workshop", "webinar", "info session", "knowledge series", \
"fundamentals of", "delivery partner", "how to apply", or "register now \
for free", set relevant to false.
- category (string): one of "Grant", "Scholarship", "Prize", "Award", \
"Residency", "Fellowship", "Commission", "Other".
- english (boolean): true if the opportunity is run in English.
- au_eligibility (string): one of "eligible", "ineligible", or "unclear". \
IMPORTANT: if the summary contains "Location: " followed by an Australian \
state or city (e.g. "Location: NSW, Australia", "Location: VIC", \
"Location: Sydney"), set this to "eligible". If the listing is for an \
Australian government body (Creative Australia, Create NSW, Arts Queensland, \
etc.) set this to "eligible" unless it explicitly excludes individuals.
- location_scope (string): one of "Australia", "International", "Unknown". \
If the summary contains "Location: " followed by an Australian state or \
city, set this to "Australia". If the prize or grant is run by an \
Australian body but open worldwide, set to "International".
- eligibility_note (string): one short sentence on who can apply, or "".
- deadline (string): closing date as YYYY-MM-DD, or "". Never guess.
- amount (string): prize or funding value as written, or "".
- summary (string): one plain sentence describing the opportunity.
- curator (string): the named curator exactly as written, or "" if not stated.
- judge (string): the named judge or judges exactly as written, or "" if not \
stated. If multiple judges are listed, join them with ", ".
- art_forms (array of strings): visual-art disciplines only. Choose from: \
{ART_FORMS}. Rules: use specific media where named (e.g. ["Sculpture"]). \
Use "Visual Arts" when visual but no specific medium is named. Use \
"Multidisciplinary" ONLY when the listing is genuinely open to all art \
practices including visual arts. Return [] (empty array) when the \
opportunity is exclusively for a non-visual practice — this includes: \
music, record labels, bands, songwriting, audio, dance, theatre, drama, \
opera, literature, writing, publishing, books, literary journals, film, \
screen, games, or digital technology with no visual-art component. When in \
doubt between Multidisciplinary and [], ask: could a painter or sculptor \
meaningfully apply? If no, return [].

Output only the JSON object.""".replace("{ART_FORMS}", ", ".join(ART_FORMS))


def _is_404(summary):
    """Return True if the summary looks like a 404 page rather than real content."""
    low = summary.lower()
    return any(sig in low for sig in _NOT_FOUND_SIGNALS)


def _extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text[:4].lower() == "json":
            text = text[4:].strip()
    return json.loads(text)


def classify(item):
    """Return the classification dict for one raw item, or None on failure.

    Items whose page returned a 404 are skipped before hitting the API,
    marked as not relevant so they land in seen.json and are never retried.
    """
    summary = item.get("summary", "")

    if _is_404(summary):
        print(f"  ! 404 detected, skipping API call: {item['title'][:60]}")
        return {
            "relevant": False, "english": True,
            "category": "Other", "au_eligibility": "unclear",
            "location_scope": "Unknown", "eligibility_note": "",
            "deadline": "", "amount": "",
            "summary": "Page not found.", "art_forms": [],
        }

    user = (
        f"Source: {item['source']}\n"
        f"Title: {item['title']}\n"
        f"Summary: {summary}"
    )
    msg = client.messages.create(
        model=CLASSIFY_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    try:
        return _extract_json(text)
    except Exception as e:
        print(f"  ! parse failed for '{item['title'][:50]}': {e}")
        return None
