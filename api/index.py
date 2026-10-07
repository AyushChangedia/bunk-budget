"""
Vercel's entrypoint.

Vercel's Python runtime looks for handlers under `api/`, imports the module,
and serves whatever ASGI application it finds exported as `app`. There is no
render.yaml, no Dockerfile, no uvicorn and no port here: the platform owns the
server, and this file only points it at the application that already exists.

The repository root goes on sys.path because main.py imports `budget` and
`extract` as top-level modules and they sit beside it, while the handler runs
from api/. Getting that wrong is the failure that is hardest to read from a
browser — every route 500s identically, with nothing saying which import died.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402

__all__ = ["app"]
