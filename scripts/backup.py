"""Export every saved trip to backups/trips-<timestamp>.json (git-ignored: it's user data).

Run BEFORE any change to the prod database:
    .venv/bin/python scripts/backup.py            # uses SUPABASE_URL / SUPABASE_SECRET_KEY from .env (dev)
To back up prod, run it with prod's values in the environment for that one command (Ask me first: prod keys).
Restore: paste the rows back with the Supabase table editor, or POST them to /rest/v1/trips with the secret key.
"""
import json
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("SUPABASE_URL", "").rstrip("/")
key = os.getenv("SUPABASE_SECRET_KEY", "")
if not url or not key:
    sys.exit("Set SUPABASE_URL and SUPABASE_SECRET_KEY first.")

rows, page = [], 1000
while True:
    res = requests.get(f"{url}/rest/v1/trips", headers={"apikey": key, "Range": f"{len(rows)}-{len(rows) + page - 1}"},
                       params={"select": "*", "order": "created_at"}, timeout=30)
    res.raise_for_status()
    batch = res.json()
    rows += batch
    if len(batch) < page:
        break

os.makedirs("backups", exist_ok=True)
path = f"backups/trips-{datetime.now():%Y%m%d-%H%M%S}.json"
with open(path, "w") as f:
    json.dump(rows, f, indent=1)
print(f"Backed up {len(rows)} trips from {url.split('//')[-1].split('.')[0]} to {path}")
