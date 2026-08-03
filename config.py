"""Central settings. Anything you'd want to tweak lives here, not scattered
through the code."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
DATA_FILE = DOCS / "data.json"        # what the dashboard reads
STATE_FILE = ROOT / "seen.json"       # dedup + record store (what we've processed)
SOURCES_FILE = ROOT / "sources.json"  # the source list you grow over time

# Classification model. Change this string to swap models.
CLASSIFY_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 600

# Notifications
CLOSING_SOON_DAYS = 7                  # instant alert fires at this many days out
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

# Secrets (read from the environment, never hard-coded)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
SERPER_API_KEY    = os.environ.get("SERPER_API_KEY", "").strip()

# Fetch behaviour
USER_AGENT = "art-grants-dashboard/1.0"
REQUEST_TIMEOUT = 20

# --- Discipline tags -------------------------------------------------------
# The classifier tags each opportunity with one or more of these. Edit this
# list to change the scope. To widen back out (e.g. add writing or music), add
# the terms here and set DROP_IF_NO_ART_FORM = False.
#
# Two of these are "wildcards" that match every discipline filter on the
# dashboard, because a specialist can apply to them:
#   "Visual Arts"      - visual, but no specific medium named
#   "Multidisciplinary"- open to all art practices
ART_FORMS = [
    "Painting", "Drawing", "Sculpture", "Photography", "Printmaking",
    "Ceramics", "Textiles", "Illustration", "Digital/New Media",
    "Installation", "Mixed Media", "Visual Arts", "Multidisciplinary",
]
WILDCARD_FORMS = ["Visual Arts", "Multidisciplinary"]

# When True, opportunities the classifier tags with no art form (i.e. that are
# exclusively non-visual, like a music or writing grant) are dropped from the
# dashboard. Set False to keep everything and just tag what's visual.
DROP_IF_NO_ART_FORM = True
