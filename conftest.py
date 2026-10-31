"""Pytest bootstrap: ensure the repository root is importable as a package root.

Running ``python -m pytest`` from the repo root already puts the root on
``sys.path``; this conftest makes the ``src`` package importable regardless of
how pytest is invoked (e.g. ``pytest tests/``).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
