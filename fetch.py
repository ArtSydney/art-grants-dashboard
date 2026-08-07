"""Pull raw items from every enabled source.

Two source types share one output shape, so the classifier downstream never has
to care where an item came from:
    {id, source, title, link, summary}
"""
import json
import hashlib
from urllib.parse import urljoin

import requests
import feedparser
from bs4 import BeautifulSoup

from config import SOURCES_FILE, USER_AGENT, REQUEST_TIMEOUT


def _item_id(link, title):
    """Stable id so the same listing is never processed twice, even across runs."""
    basis = (link or title or "").strip().lower()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def _meta_description(soup):
    """Pull a clean one-line description from a page's meta tags.

    Sites almost always carry a human-written og:description or meta description
    that reads far better than scraped body text (which is riddled with nav
    fragments). Returns '' if none found. Call this BEFORE decomposing tags.
    """
    for sel, attr in (
        ('meta[property="og:description"]', "content"),
        ('meta[name="description"]', "content"),
        ('meta[name="twitter:description"]', "content"),
    ):
        tag = soup.select_one(sel)
        if tag and tag.get(attr):
            text = " ".join(tag.get(attr).split()).strip()
            if len(text) > 20:
                return text[:300]
    return ""


def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources = json.load(f)
    return [s for s in sources if s.get("enabled")]


def fetch_rss(source):
    """Parse an RSS/Atom feed into normalised raw items."""
    ua = source.get("user_agent", USER_AGENT)
    feed = feedparser.parse(source["url"], request_headers={"User-Agent": ua})
    items = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        link = entry.get("link", "")
        summary_html = entry.get("summary", "") or entry.get("description", "")
        # feed summaries are usually HTML; strip tags so the model sees clean text
        summary = BeautifulSoup(summary_html, "html.parser").get_text(" ", strip=True)
        items.append({
            "id": _item_id(link, title),
            "source": source["name"],
            "title": title,
            "link": link,
            "summary": summary[:1500],
        })
    return items


def fetch_html(source):
    """Scrape a listing page using CSS selectors declared in the source config.

    Each scrape-only source needs its own selectors because every site's DOM is
    different. That's why they live in sources.json, not in code.
    """
    item_sel = source.get("item_selector")
    if not item_sel or item_sel == "REPLACE_ME":
        raise ValueError("item_selector not configured")

    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(source["url"], headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for node in soup.select(item_sel):
        title_el = node.select_one(source["title_selector"]) if source.get("title_selector") else None
        link_el = node.select_one(source.get("link_selector") or "a")
        summary_el = node.select_one(source["summary_selector"]) if source.get("summary_selector") else None

        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue
        href = link_el.get("href") if link_el else ""
        link = urljoin(source["url"], href) if href else source["url"]
        summary = summary_el.get_text(" ", strip=True) if summary_el else ""

        items.append({
            "id": _item_id(link, title),
            "source": source["name"],
            "title": title,
            "link": link,
            "summary": summary[:1500],
        })
    return items


def fetch_creative_australia(source, max_pages=12):
    """Custom parser for creative.gov.au (Drupal, paginated, not Cloudflare-blocked).

    Two-pass approach:
    1. Walk the listing pages to discover all opportunity URLs and card text.
    2. Fetch each detail page to get the full Key dates section (deadline, amount,
       notification date). This is what the classifier needs to extract a deadline.

    The listing card text alone is too thin — it carries only a one-line description,
    which is why items came through with no deadline. The detail page reliably contains
    "Applications close: [date]" in the Key dates section.
    """
    base = "https://creative.gov.au/investments-opportunities"
    NAV = {
        "application-process", "assessment", "manage-your-grant", "awarded-grants",
        "multi-year-investment", "international-engagement", "arts-disability",
        "digital-culture", "peer-feedback", "leadership-capability",
        "private-investment-capability", "training-professional-development",
    }
    # slug fragments that indicate non-opportunity content
    SLUG_DROP = (
        # workshops and events
        "knowledge-series", "artist-fundraiser", "fundraiser-workshop",
        "art-science-fundraising", "fundraising",
        "how-a-zoom", "shifting-lines", "new-vision",
        "navigating-a-digital", "zoom-super-choir",
        # non-visual art forms
        "music-australia", "music-export", "music-residency",
        "music-touring", "music-core", "contemporary-music",
        "record-label", "publishing-and-promotion", "publishers-program",
        "writers-festival", "translation-fund", "international-rights-fund",
        "dal-stivens", "poet-laureate", "prime-ministers-literary",
        "ballet-scholarship", "operatic-scholarship",
        "dance-services", "playing-australia",
        "victorian-circus", "circus-and-physical",
        "international-travel-fund",  # primarily for screen/music
        # delivery partners and services
        "delivery-partner",
        # org-only / not individual artists
        "company-director", "capacity-building", "four-year-investment",
        "multi-year-investment", "national-performing-arts-partnership",
        "matched-funding-for-organisations",
        # digital/tech programs
        "createch", "digital-enterprise", "beyond-bubble", "nft",
        "uplift-digital", "digital-skills",
        "download-online", "download-digital",
        # resources and info pages
        "making-a-grant-application", "visual-arts-and-craft-strategy",
        "international-arts-strategy",
        "marten-bequest-scholarships-terms",  # terms page, not the scholarship itself
        "fellowships$",  # bare nav page
        # other specific non-relevant
        "gifts-in-wills", "pick-up-the-phone",
        "tri-nations-exchange", "kathleen-mitchell-award",
        "visiting-international-publishers",
        "oceania-pacific", "first-nations-writing-services",
        "storytelling-and-recording", "flourish-first-nations-fashion",
        "legacy-first-nations", "elevate-first-nations",
        "young-people-first-nations", "space-to-create",
        "download-digital-indigenous",
    )
    headers = {"User-Agent": USER_AGENT}
    items, seen = [], set()

    # Pass 1: discover URLs from listing pages
    for page in range(max_pages):
        resp = requests.get(f"{base}?page={page}", headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = {}
        for a in soup.select('a[href*="/investments-opportunities/"]'):
            full = urljoin(base, a.get("href", "")).split("?")[0]
            slug = full.split("/investments-opportunities/")[-1].strip("/")
            if not slug or "/" in slug or slug in NAV:
                continue
            if any(s in slug for s in SLUG_DROP):
                continue
            entry = cards.setdefault(full, {"title": "", "text": ""})
            title_attr = (a.get("title") or "").strip()
            if title_attr and not entry["title"]:
                entry["title"] = title_attr
            text = a.get_text(" ", strip=True)
            if len(text) > len(entry["text"]):
                entry["text"] = text

        if not cards:
            break

        for full, entry in cards.items():
            if full in seen:
                continue
            seen.add(full)
            title = entry["title"] or entry["text"][:80]

            # Pass 2: fetch the detail page for key dates and amount
            detail_text = entry["text"]
            meta_desc = ""
            try:
                dr = requests.get(full, headers=headers, timeout=REQUEST_TIMEOUT)
                dr.raise_for_status()
                dsoup = BeautifulSoup(dr.text, "html.parser")
                meta_desc = _meta_description(dsoup)  # grab before decomposing
                for t in dsoup(["script", "style", "nav", "footer", "header", "noscript"]):
                    t.decompose()
                detail_text = " ".join(dsoup.get_text(" ", strip=True).split())[:4000]
            except Exception as e:
                print(f"  ! Creative Australia detail fetch failed ({e}): {title[:50]}")

            items.append({
                "id": _item_id(full, title),
                "source": source["name"],
                "title": title,
                "link": full,
                "summary": detail_text,
                "meta_desc": meta_desc,
            })
    return items



def fetch_calendarforartists(source, max_pages=6):
    """calendarforartists.com runs WordPress + The Events Calendar plugin.

    Prefer the plugin's REST API (one clean JSON call with title, description,
    cost and closing date). If that's unavailable, fall back to scraping the
    category page for event links. Covers the independent/regional Australian
    prize tier (Kangaroo Valley, Basil Sellers, etc.) our other sources miss.
    """
    headers = {"User-Agent": USER_AGENT}
    items = []

    # --- primary: The Events Calendar REST API ---
    api = "https://calendarforartists.com/wp-json/tribe/events/v1/events"
    try:
        page = 1
        while page <= max_pages:
            r = requests.get(api, headers=headers, timeout=REQUEST_TIMEOUT,
                             params={"per_page": 50, "page": page, "start_date": "2020-01-01"})
            if r.status_code != 200:
                break
            data = r.json()
            events = data.get("events", [])
            if not events:
                break
            for ev in events:
                title = (ev.get("title") or "").strip()
                url = ev.get("url") or ""
                if not title or not url:
                    continue
                desc = BeautifulSoup(ev.get("description") or "", "html.parser").get_text(" ", strip=True)
                cost = ev.get("cost") or ""
                start = (ev.get("start_date") or "").split(" ")[0]  # 'YYYY-MM-DD'
                cats = ", ".join(c.get("name", "") for c in (ev.get("categories") or []))
                closing = f"Closing date: {start}" if start else ""
                summary = " | ".join(x for x in [desc, cost, cats, closing] if x)
                items.append({
                    "id": _item_id(url, title),
                    "source": source["name"],
                    "title": title,
                    "link": url,
                    "summary": summary[:1500],
                })
            if page >= int(data.get("total_pages") or 1):
                break
            page += 1
        if items:
            return items
    except Exception as e:
        print(f"  ! {source['name']} REST API failed, falling back to HTML: {e}")

    # --- fallback: scrape the category page for event links ---
    r = requests.get(source["url"], headers=headers, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    seen = set()
    for a in soup.select('a[href*="/events/"]'):
        full = urljoin(source["url"], a.get("href", "")).split("?")[0]
        slug = full.split("/events/")[-1].strip("/")
        if not slug or "/" in slug or slug in seen:
            continue  # skip category links and duplicates
        seen.add(slug)
        title = a.get_text(strip=True)
        if not title:
            continue
        items.append({
            "id": _item_id(full, title),
            "source": source["name"],
            "title": title,
            "link": full,
            "summary": title,
        })
    return items


def fetch_page(source):
    """Fetch a single standalone opportunity page — a prize site with no feed.

    One page becomes one item: the source's name is the title, and the page's
    readable text is handed to the classifier to mine for deadline, amount,
    eligibility and discipline. Marked refresh=True so it is re-checked every run,
    which keeps annual prizes current when their page rolls to a new round.
    """
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(source["url"], headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    meta_desc = _meta_description(soup)  # grab before decomposing
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "img", "svg"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    title = source["name"]
    return [{
        "id": _item_id(source["url"], title),
        "source": source["name"],
        "title": title,
        "link": source["url"],
        "summary": text[:6000],   # generous, since dates often sit low on the page
        "meta_desc": meta_desc,
        "refresh": True,
    }]


def fetch_bneart(source, max_pages=4):
    """Scrape BNE Art's opportunities listing. WordPress site, server-rendered,
    no Cloudflare. Each card carries a clean title, description, and a deadline
    in YYYYMMDD format embedded as text. Links follow /slug/ pattern.
    80 pages exist; we read the first few since they are sorted newest-first.
    """
    headers = {"User-Agent": USER_AGENT}
    base = "https://bneart.com"
    seen, items = set(), []

    for page_num in range(1, max_pages + 1):
        if page_num == 1:
            url = source["url"]
        else:
            url = f"{source['url']}?sf_paged={page_num}"
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ! BNE Art page {page_num}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        new_on_page = 0

        # each article block has an <h4> with the link and a deadline text node
        for article in soup.select("article, .post, h4"):
            a = article.find("a", href=True) if article.name != "a" else article
            if not a:
                continue
            href = a.get("href", "")
            if not href.startswith("https://bneart.com/") or "/category/" in href:
                continue
            if href in seen:
                continue
            seen.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # extract deadline — BNE Art uses two formats:
            # numeric: 20260802  OR  human: "2 August" / "14 August 2026"
            deadline_raw = ""
            parent = a.find_parent(["article", "div", "section"])
            if parent:
                block_text = parent.get_text(" ", strip=True)
                import re
                # try numeric YYYYMMDD first
                m = re.search(r'\b(202\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b', block_text)
                if m:
                    y, mo, d = m.group(1), m.group(2), m.group(3)
                    deadline_raw = f"Deadline: {y}-{mo}-{d}."
                else:
                    # try human-readable: "2 August", "14 August 2026", "August 14"
                    months = "January|February|March|April|May|June|July|August|September|October|November|December"
                    m2 = re.search(
                        rf'\b(\d{{1,2}})\s+({months})(?:\s+(202\d))?\b'
                        rf'|\b({months})\s+(\d{{1,2}})(?:\s+(202\d))?\b',
                        block_text, re.IGNORECASE
                    )
                    if m2:
                        deadline_raw = f"Deadline: {m2.group(0).strip()}."
                summary = f"{deadline_raw} {block_text[:1000]}".strip()
            else:
                summary = title

            # card text is truncated ("Presented by the…") so fetch the
            # detail page for the full description including the deadline
            detail_text = summary
            meta_desc = ""
            try:
                dr = requests.get(href, headers=headers, timeout=REQUEST_TIMEOUT)
                dr.raise_for_status()
                dsoup = BeautifulSoup(dr.text, "html.parser")
                meta_desc = _meta_description(dsoup)  # grab before decomposing
                for t in dsoup(["script", "style", "nav", "footer", "header", "noscript", "img", "svg"]):
                    t.decompose()
                page_text = " ".join(dsoup.get_text(" ", strip=True).split())
                # strip Related Posts section before truncating — it contains
                # other items' deadlines which corrupt extraction
                for marker in ("Related Posts", "You may also like"):
                    idx = page_text.find(marker)
                    if idx != -1:
                        page_text = page_text[:idx]
                page_text = page_text[:3000]
                m = re.search(r'\b(202\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b', page_text)
                if m:
                    y, mo, d = m.group(1), m.group(2), m.group(3)
                    deadline_raw = f"Deadline: {y}-{mo}-{d}."
                else:
                    months = "January|February|March|April|May|June|July|August|September|October|November|December"
                    m2 = re.search(
                        rf'\b(\d{{1,2}})\s+({months})(?:\s+(202\d))?\b'
                        rf'|\b({months})\s+(\d{{1,2}})(?:\s+(202\d))?\b',
                        page_text, re.IGNORECASE
                    )
                    if m2:
                        deadline_raw = f"Deadline: {m2.group(0).strip()}."
                detail_text = f"{deadline_raw} {page_text[:3000]}".strip()
            except Exception as e:
                print(f"  ! BNE Art detail failed ({e}): {title[:50]}")

            items.append({
                "id": _item_id(href, title),
                "source": source["name"],
                "title": title,
                "link": href,
                "summary": detail_text[:4000],
                "meta_desc": meta_desc,
            })
            new_on_page += 1

        if new_on_page == 0:
            break

    return items



def fetch_google_search(source):
    """Run one or more Serper API queries and return each unique result URL as
    a fetchable item.

    This is the discovery mechanism for prize pages that have no feed and are
    not in any aggregator. Each daily run fires the queries, finds URLs we have
    not seen before, fetches each page, and hands the text to the classifier.
    Cloudflare-blocked pages are skipped gracefully. Already-seen URLs are
    deduped by the main pipeline so we never re-classify the same page.

    Queries live in sources.json under "queries": [...]. The Serper key is read
    from SERPER_API_KEY in the environment. If the key is absent the source
    is silently skipped, so the pipeline still runs without it.
    """
    from config import SERPER_API_KEY
    if not SERPER_API_KEY:
        print(f"  ! {source['name']}: SERPER_API_KEY not set, skipping")
        return []

    queries = source.get("queries", [])
    if not queries:
        return []

    headers_serper = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    headers_fetch = {"User-Agent": USER_AGENT}

    # collect unique URLs across all queries
    seen_urls, raw_results = set(), []
    for query in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers=headers_serper,
                json={"q": query, "gl": "au", "hl": "en", "num": 10},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            for r in resp.json().get("organic", []):
                url = (r.get("link") or "").strip()
                title = (r.get("title") or "").strip()
                snippet = (r.get("snippet") or "").strip()
                if not url or url in seen_urls:
                    continue
                # skip aggregator and news domains
                skip_domains = (
                    "artshub.com.au", "artsoz.com.au", "calendarforartists.com",
                    "artshow.com", "creative.gov.au", "neonmarketplace.nsw.gov.au",
                    "bneart.com",
                    # news and PR sites
                    "newshub.medianet.com.au", "miragenews.com", "medianet.com.au",
                    "newcastleherald.com.au", "newcastleweekly.com.au",
                    "insidelocalgovernment.com.au", "ausleisure.com.au",
                    "artcollector.net.au", "artgallery.nsw.gov.au",
                )
                if any(d in url for d in skip_domains):
                    continue
                # skip URLs that look like news, FAQs, info booklets, or directories
                skip_url_patterns = (
                    "/news/", "/news-", "congratulations", "winner-of",
                    "faq", "info-booklet", "information-booklet",
                    "artprizelistings", "art-prize-listings",
                    "/blog/", "/press-release/", "/media-release/",
                    "instagram.com", "facebook.com", "twitter.com",
                    "/artist-opportunities/", "/funding/other-grants/", 
                    "/sector/funding/", "/terms-and-conditions/",
                )
                if any(p in url.lower() for p in skip_url_patterns):
                    continue
                # skip titles that are obviously news/announcements
                title_low = title.lower()
                if any(p in title_low for p in (
                    "congratulations", "winner of", "announces winner",
                    "finalists announced", "faq", "info booklet",
                    "art prizes planner", "prize listings",
                )):
                    continue
                seen_urls.add(url)
                raw_results.append({"url": url, "title": title, "snippet": snippet})
        except Exception as e:
            print(f"  ! Serper query failed ({e}): {query[:60]}")

    # fetch each new URL for the classifier
    items = []
    for r in raw_results:
        url, title, snippet = r["url"], r["title"], r["snippet"]
        page_text = snippet  # fallback if page fetch fails
        meta_desc = ""
        try:
            pr = requests.get(url, headers=headers_fetch, timeout=REQUEST_TIMEOUT)
            pr.raise_for_status()
            if "just a moment" in pr.text.lower() or "challenge-platform" in pr.text:
                continue  # Cloudflare block, skip silently
            soup = BeautifulSoup(pr.text, "html.parser")
            meta_desc = _meta_description(soup)  # grab before decomposing
            for t in soup(["script", "style", "nav", "footer", "header", "noscript", "img", "svg"]):
                t.decompose()
            page_text = " ".join(soup.get_text(" ", strip=True).split())[:4000]
        except Exception:
            pass  # use snippet as summary, classifier will handle thin text

        items.append({
            "id": _item_id(url, title),
            "source": source["name"],
            "title": title,
            "link": url,
            "summary": page_text,
            "meta_desc": meta_desc,
        })

    return items


def fetch_neon_marketplace(source, max_pages=8):
    """Scrape Neon Marketplace (neonmarketplace.nsw.gov.au), the NSW Government's
    creative sector marketplace. Server-rendered, no Cloudflare. Opportunity links
    follow the stable /opportunity/nd/<slug> pattern. Each detail page carries
    title, description, deadline and poster organisation.

    The listing is paginated via ?p=N. We harvest all slugs, then fetch each
    detail page to build a rich summary for the classifier.
    """
    headers = {"User-Agent": USER_AGENT}
    base = "https://www.neonmarketplace.nsw.gov.au"
    listing = source["url"].rstrip("/")
    seen, items = set(), []

    for page_num in range(1, max_pages + 1):
        url = listing if page_num == 1 else f"{listing}?p={page_num}"
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ! Neon Marketplace page {page_num}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        new_on_page = 0

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/opportunity/nd/" not in href:
                continue
            full = urljoin(base, href).split("?")[0]
            if full in seen:
                continue
            seen.add(full)
            new_on_page += 1

            # fetch the detail page for structured data
            title, summary = a.get_text(strip=True), ""
            try:
                dr = requests.get(full, headers=headers, timeout=REQUEST_TIMEOUT)
                dr.raise_for_status()
                dsoup = BeautifulSoup(dr.text, "html.parser")
                for t in dsoup(["script", "style", "nav", "footer", "header", "noscript", "img", "svg"]):
                    t.decompose()
                page_text = " ".join(dsoup.get_text(" ", strip=True).split())
                # title from the page is cleaner than the link text
                if dsoup.title and dsoup.title.string:
                    page_title = dsoup.title.string.replace("| Neon Marketplace", "").strip()
                    if page_title:
                        title = page_title
                summary = page_text[:2000]
            except Exception as e:
                print(f"  ! Neon detail fetch failed ({e}): {full}")

            if not title:
                continue
            items.append({
                "id": _item_id(full, title),
                "source": source["name"],
                "title": title,
                "link": full,
                "summary": summary,
            })

        if new_on_page == 0:
            break

    return items


def fetch_artsoz_prizes(source, max_prizes=40):
    """Artsoz publishes a structured list of major Australian prizes with their
    official URLs and metadata (state, medium, type) at art-prizes.json.

    We use it as a registry: read the list, then visit each prize's OWN site to
    pull the live deadline and terms, handing the classifier Artsoz's state and
    medium metadata alongside the page text. That metadata is what lets the
    classifier tag location and discipline confidently. Grows automatically as
    Artsoz adds prizes. Heaviest source (one fetch per prize), refreshed each run.
    """
    headers = {"User-Agent": USER_AGENT}
    r = requests.get("https://artsoz.com.au/art-prizes.json", headers=headers, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    prizes = r.json()

    # URL overrides: when Artsoz has the wrong URL for a prize, fix it here
    # in sources.json under "url_overrides": {"Prize Name": "https://correct-url"}
    # rather than touching code. Keys must match the prize's "name" field exactly.
    overrides = source.get("url_overrides", {})

    items = []
    for p in prizes[:max_prizes]:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        # apply override if one exists for this prize name
        url = overrides.get(name) or (p.get("official_url") or "").strip()
        if not url:
            continue
        meta = []
        if p.get("state"):
            meta.append(f"Location: {p['state']}, Australia")
        if p.get("medium"):
            meta.append(f"Medium: {p['medium']}")
        if p.get("type"):
            meta.append(f"Type: {p['type']}")
        if p.get("tags"):
            meta.append("Tags: " + ", ".join(p["tags"]))
        meta_text = ". ".join(meta)

        page_text = ""
        meta_desc = ""
        try:
            pr = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            pr.raise_for_status()
            soup = BeautifulSoup(pr.text, "html.parser")
            meta_desc = _meta_description(soup)  # grab before decomposing
            for t in soup(["script", "style", "nav", "footer", "header", "noscript", "img", "svg"]):
                t.decompose()
            page_text = " ".join(soup.get_text(" ", strip=True).split())[:5000]
        except Exception as e:
            print(f"  ! {name}: official page fetch failed ({e}); using directory metadata only")

        items.append({
            "id": _item_id(url, name),
            "source": source["name"],
            "title": name,
            "link": url,
            "summary": f"{meta_text}. {page_text}".strip()[:6000],
            "meta_desc": meta_desc,
            "refresh": True,
        })
    return items


def fetch_artshub_opportunities(source, max_pages=5):
    """Scrape the ArtsHub opportunity listing page, which is server-rendered
    (unlike the search/filter pages which are JS-rendered and return empty).

    The listing page exposes opportunity cards as <h3> or <h2> anchor tags with
    a stable /opportunity/<slug>-<id>/ URL pattern. Each card also carries
    artform, closing date and classification text inline, which we pass to the
    classifier as the summary rather than fetching each detail page, keeping
    the run lightweight. The opportunity section is paginated via ?page=N.
    """
    headers = {"User-Agent": USER_AGENT}
    base = source["url"].rstrip("/")
    seen, items = set(), []

    for page_num in range(1, max_pages + 1):
        url = base if page_num == 1 else f"{base}?page={page_num}"
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ! ArtsHub page {page_num}: {e}")
            break

        # Cloudflare challenge page: bail out gracefully
        if "just a moment" in resp.text.lower() or "challenge-platform" in resp.text:
            print(f"  ! ArtsHub: Cloudflare challenge on page {page_num}, stopping")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        new_on_page = 0

        # Opportunity links follow the pattern /opportunity/<slug>-<digits>/
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/opportunity/" not in href:
                continue
            full = urljoin(base, href).split("?")[0]
            # must end with a numeric ID segment (real opportunity, not category page)
            slug = full.rstrip("/").split("/opportunity/")[-1].strip("/")
            if not slug or not slug.split("-")[-1].isdigit():
                continue
            if full in seen:
                continue
            seen.add(full)

            # collect the closest block of descriptive text around this link
            parent = a.find_parent(["article", "li", "div", "section"])
            if parent:
                block_text = parent.get_text(" ", strip=True)
            else:
                block_text = a.get_text(strip=True)

            title = a.get_text(strip=True) or slug
            if not title or len(title) < 5:
                continue

            items.append({
                "id": _item_id(full, title),
                "source": source["name"],
                "title": title,
                "link": full,
                "summary": block_text[:1500],
            })
            new_on_page += 1

        if new_on_page == 0:
            break   # no new items: past the last real page

    return items


# Sources with "parser": "<name>" in the config route here instead of the
# generic rss/html fetchers. Add an entry when a site needs bespoke handling.
CUSTOM_PARSERS = {
    "creative_australia": fetch_creative_australia,
    "calendarforartists": fetch_calendarforartists,
    "neon_marketplace": fetch_neon_marketplace,
    "artsoz_prizes": fetch_artsoz_prizes,
    "artshub_opportunities": fetch_artshub_opportunities,
    "google_search": fetch_google_search,
    "bneart": fetch_bneart,
}


def fetch_all():
    """Fetch every enabled source. One source failing never sinks the run."""
    raw = []
    for source in load_sources():
        try:
            parser = source.get("parser")
            if parser:
                fn = CUSTOM_PARSERS.get(parser)
                if fn is None:
                    print(f"  ! {source['name']}: no parser named '{parser}'")
                    continue
                got = fn(source)
            elif source["type"] == "rss":
                got = fetch_rss(source)
            elif source["type"] == "html":
                got = fetch_html(source)
            elif source["type"] == "page":
                got = fetch_page(source)
            else:
                print(f"  ! {source['name']}: unknown type '{source['type']}'")
                continue
            print(f"  {source['name']}: {len(got)} items")
            raw.extend(got)
        except Exception as e:
            print(f"  ! {source['name']} failed: {e}")
    return raw
