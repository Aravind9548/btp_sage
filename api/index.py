"""Vercel serverless entrypoint.

Vercel auto-detects files under /api as serverless functions and looks for a
WSGI callable named `app` (or `handler`). vercel.json rewrites every incoming
path here, so this one function serves the whole site.

The repo root is pushed onto sys.path because `web_app` and `saga_bench` live
one level up from this file.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app import app  # noqa: E402

handler = app
