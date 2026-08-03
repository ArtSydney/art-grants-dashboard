# Open Calls

A dashboard of arts grants, prizes, scholarships, residencies, fellowships and
commissions for artists based in Australia. It pulls from RSS feeds and scraped
pages, uses Claude to sort the real opportunities from the noise, shows them on a
static dashboard sorted by what closes next, and posts to Discord.

## How it works

```
sources.json ──▶ fetch.py ──▶ classify.py ──▶ seen.json ──▶ build_data.py ──▶ docs/data.json ──▶ dashboard
                 (rss+html)   (Claude Haiku)   (dedup +      (filter open      (what the page
                                                record store) opportunities)    reads)
                                                     │
                                                     └──▶ notify.py (Discord: daily digest + closing-soon)
```

- **fetch.py** reads every enabled entry in `sources.json`. `rss` sources are
  parsed with feedparser; `html` sources are scraped with selectors you declare
  in the config. Both produce the same item shape.
- **classify.py** sends each new item to Claude Haiku and gets back structured
  fields: category, English yes/no, Australian eligibility, deadline, amount, and
  a one-line summary.
- **seen.json** records everything processed so nothing is classified or notified
  twice. It is also the store the dashboard is built from.
- **build_data.py** writes `docs/data.json`: relevant, English, still-open items,
  sorted by soonest deadline. Eligibility is kept and badged, not filtered out.
- **notify.py** posts a daily digest of new items, and an instant ping when a
  deadline is 7 days out.

English is a hard gate. News, reviews and job ads are dropped as not relevant.

## Run it locally (Kali/Linux)

```bash
pip install -r requirements.txt
cp .env.example .env          # then edit .env and add your API key
chmod +x run_local.sh
./run_local.sh
```

`run_local.sh` loads `.env`, runs the pipeline once, then serves the dashboard at
http://localhost:8000. The Discord webhook is optional: leave it blank in `.env`
and notifications are skipped so you can test quietly.

To run just the pipeline without serving:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 main.py
```

Note: open the dashboard over http (the server above), not by double-clicking
`index.html`, because browsers block `fetch` of a local file over `file://`.

## Adding a source

Edit `sources.json`. For a feed:

```json
{ "name": "Some Feed", "type": "rss", "url": "https://example.com/feed/", "enabled": true }
```

For a page with no feed, inspect its HTML and fill the selectors:

```json
{
  "name": "Some Body",
  "type": "html",
  "url": "https://example.com/opportunities",
  "item_selector": ".opportunity-card",
  "title_selector": "h3",
  "link_selector": "a",
  "summary_selector": ".excerpt",
  "enabled": true
}
```

`item_selector` matches each listing block; the others pick fields out of it.
Creative Australia is pre-filled as a disabled template to copy.

## Source notes from research

- **ArtsHub** (`artshub.com.au/feed`) is the strongest Australian source and has a
  confirmed feed. It carries the whole site, so news and jobs come through too;
  the classifier drops them. Enabled by default.
- **Colossal** and **e-flux** are good international sources for prizes and
  residencies that are often open worldwide. Confirm their feed URLs load, then
  enable.
- **Creative Australia** (the big national funder) publishes pages, not a clean
  feed, so it needs the `html` scraper. High value, worth configuring first.

## Host it publicly (later)

1. Push the repo to GitHub.
2. Settings > Pages: serve from the `main` branch, `/docs` folder.
3. Settings > Secrets and variables > Actions: add `ANTHROPIC_API_KEY` and
   `DISCORD_WEBHOOK_URL`.
4. The workflow in `.github/workflows/update.yml` runs daily, refreshes
   `docs/data.json`, and commits it so Pages updates itself.

Same code, whether it runs on your machine or in Actions. The only difference is
where the schedule and the secrets live.

## Config

Everything tweakable is in `config.py`: the model string, the closing-soon
threshold (default 7 days), and file paths.
