#!/usr/bin/env python3
"""
Index election poster PDFs into PROD Qdrant.

Thin wrapper: sets prod env vars, then exec's index_election_posters.py.

Usage:
    GOOGLE_APPLICATION_CREDENTIALS=~/Downloads/chat-vote-prod-firebase-adminsdk-fbsvc-*.json \
    python3 scripts/index_posters_prod.py [--commune CODE] [--dry-run] [--force]
"""
import os
import sys
from pathlib import Path

# Set prod env BEFORE exec
os.environ["API_NAME"] = "chatvote-api"
os.environ["ENV"] = "prod"
os.environ["QDRANT_URL"] = "https://chatvoteoan3waxf-qdrant-prod.functions.fnc.fr-par.scw.cloud"

# Keep GOOGLE_API_KEY from .env if not already set
from dotenv import dotenv_values
env_file = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
if "GOOGLE_API_KEY" not in os.environ and "GOOGLE_API_KEY" in env_file:
    os.environ["GOOGLE_API_KEY"] = env_file["GOOGLE_API_KEY"]

# Firebase prod credentials
cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if not cred_path:
    print("ERROR: GOOGLE_APPLICATION_CREDENTIALS not set")
    sys.exit(1)

# exec the main script in the same process (inherits env vars)
script = str(Path(__file__).resolve().parent / "index_election_posters.py")
sys.argv[0] = script
exec(open(script).read())
