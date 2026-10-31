"""Dependency-free ``.env`` loader for the VulneraSafe AI pipeline.

Python does not read a project ``.env`` file automatically, and this project
deliberately avoids adding ``python-dotenv`` as a dependency. :func:`load_dotenv`
parses a simple ``KEY=VALUE`` file and populates :data:`os.environ` for keys
that are **not already set**, so a real environment variable always wins over a
file value.

Security note (Req 4): this loader never logs, prints, or returns the parsed
values. It returns only the *names* of the keys it set, so callers can confirm a
key is present without ever surfacing a secret.

Supported syntax
----------------
* ``KEY=VALUE`` one per line.
* Blank lines and lines whose first non-space character is ``#`` are ignored.
* An optional leading ``export `` prefix is stripped.
* Surrounding single or double quotes around the value are stripped.
* Inline whitespace around the key and value is trimmed.
* A line with no ``=`` is skipped.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union


def _strip_quotes(value: str) -> str:
    """Strip one matching pair of surrounding single or double quotes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_dotenv(path: Union[str, Path] = ".env", *, override: bool = False) -> list[str]:
    """Load ``KEY=VALUE`` pairs from ``path`` into :data:`os.environ`.

    Parameters
    ----------
    path:
        Path to the ``.env`` file. A missing file is not an error — the loader
        simply returns an empty list so a run never fails because the file is
        absent.
    override:
        When ``False`` (the default) a key already present in the environment is
        left untouched, so a real environment variable takes precedence over the
        file. When ``True`` the file value replaces the existing one.

    Returns
    -------
    list[str]
        The names of the keys this call set (never their values). Callers can
        use this to confirm presence without ever surfacing a secret.
    """

    env_path = Path(path)
    if not env_path.is_file():
        return []

    set_keys: list[str] = []
    try:
        text = env_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # A ``.env`` that cannot be read must not crash the pipeline.
        return []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = _strip_quotes(value.strip())
        if override or key not in os.environ:
            os.environ[key] = value
            set_keys.append(key)

    return set_keys
