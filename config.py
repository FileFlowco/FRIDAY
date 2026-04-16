"""
FRIDAY — Central config
All paths go through here so moving to cloud = one env var change.

Set DATA_DIR in .env to override default:
  DATA_DIR=/app/data          # cloud / VPS
  DATA_DIR=~/Documents/FRIDAY # local (default)
"""

import os

# ── Base directory ────────────────────────────────────────────────────────────
# Cloud: set DATA_DIR=/app/data (or wherever your volume is mounted)
# Local: defaults to ~/Documents/FRIDAY
_raw = os.getenv("DATA_DIR", "~/Documents/FRIDAY")
DATA_DIR = os.path.expanduser(_raw)

# ── Sub-directories ────────────────────────────────────────────────────────────
LEADS_DIR    = os.path.join(DATA_DIR, "leads")
OUTPUT_DIR   = os.path.join(DATA_DIR, "output")
IMAGES_DIR   = os.path.join(DATA_DIR, "output", "images")
INVOICES_DIR = os.path.join(DATA_DIR, "output", "invoices")
LOGS_DIR     = os.path.join(DATA_DIR, "logs")
STATE_FILE   = os.path.join(DATA_DIR, "logs", "state.json")
USAGE_FILE   = os.path.join(DATA_DIR, "logs", "usage.json")
PROJECTS_FILE= os.path.join(DATA_DIR, "logs", "projects.json")

# ── Ensure dirs exist on import ───────────────────────────────────────────────
for _d in [LEADS_DIR, OUTPUT_DIR, IMAGES_DIR, INVOICES_DIR, LOGS_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── App config ─────────────────────────────────────────────────────────────────
PORT     = int(os.getenv("PORT", 7771))
HOST     = os.getenv("HOST", "0.0.0.0")

# ── Company ───────────────────────────────────────────────────────────────────
COMPANY_NAME  = os.getenv("COMPANY_NAME",  "FileFlow Inc")
COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "")
REPLY_TO      = os.getenv("REPLY_TO_EMAIL", COMPANY_EMAIL)
