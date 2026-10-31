"""Data integrity and authenticity enforcement (Phase 1, Task 2.3).

This module enforces three responsible-use rules from the requirements so that
no fabricated, mismatched, or placeholder value can leak into downstream
processing:

* **Req 4.2 — checksum rejection.** :func:`verify_checksum` recomputes a
  SHA-256 over the file/bytes in use and compares it to the recorded checksum.
  :func:`enforce_checksum` turns a mismatch into an explicit rejection that
  names the dataset and excludes it from downstream processing.
* **Req 4.5 — no placeholders in empirical data.** Placeholder sentinels
  (``PLACEHOLDER``, ``FIXME``, ``TODO``, ``9999``, ``-9999`` and similar dummy
  values) are permitted **only** in datasets labeled synthetic/SIMULATED.
  :func:`assert_no_placeholder_in_empirical` raises for any other dataset.
* **Req 4.6 — gaps, never fabricated numbers.** :func:`record_gap` appends a
  structured gap entry describing a missing field and **never** emits a numeric
  value for that field.

A small helper, :func:`write_checksum_manifest`, persists a name -> checksum
mapping to ``data/interim/checksums.json`` so a later run can re-verify files.

Nothing here invents data: every function either confirms authenticity, records
an honest gap, or refuses to proceed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional, Union

try:  # pandas is a hard pipeline dependency, but keep imports resilient.
    import pandas as pd
except Exception:  # pragma: no cover - pandas always present in this project
    pd = None  # type: ignore[assignment]


__all__ = [
    "IntegrityError",
    "PlaceholderError",
    "verify_checksum",
    "enforce_checksum",
    "assert_no_placeholder_in_empirical",
    "record_gap",
    "write_checksum_manifest",
    "PLACEHOLDER_SENTINELS",
    "SYNTHETIC_LABELS",
]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class IntegrityError(RuntimeError):
    """Raised when a dataset fails a hard integrity rule (checksum mismatch)."""


class PlaceholderError(ValueError):
    """Raised when placeholder sentinels appear in a non-synthetic dataset."""


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: Dataset labels that mark data as synthetic/demonstration (Req 4.4, 4.5).
#: Placeholder sentinels are allowed only when the dataset carries one of these.
SYNTHETIC_LABELS: frozenset[str] = frozenset(
    {"simulated", "synthetic", "synthetic_operational_network", "demo", "demonstration"}
)

#: Case-insensitive string placeholder sentinels forbidden in empirical data.
_STRING_SENTINELS: frozenset[str] = frozenset(
    {
        "placeholder",
        "fixme",
        "todo",
        "tbd",
        "dummy",
        "xxx",
        "n/a placeholder",
        "lorem ipsum",
        "foo",
        "bar",
        "baz",
    }
)

#: Numeric sentinel values commonly used as missing/placeholder markers.
_NUMERIC_SENTINELS: frozenset[float] = frozenset({9999.0, -9999.0, 99999.0, -99999.0})

#: Public, de-duplicated view of every sentinel (strings + numeric literals),
#: handy for tests and documentation.
PLACEHOLDER_SENTINELS: frozenset[str] = frozenset(
    {s.upper() for s in _STRING_SENTINELS}
    | {"9999", "-9999", "99999", "-99999"}
)

_CHUNK = 1 << 20  # 1 MiB streaming read for large files.


# --------------------------------------------------------------------------- #
# Req 4.2 — checksum verification and enforcement
# --------------------------------------------------------------------------- #

def _sha256_of(data_or_path: Union[bytes, bytearray, str, Path]) -> str:
    """Return the hex SHA-256 of raw bytes or of a file's contents.

    Accepts ``bytes``/``bytearray`` (hashed directly) or a ``str``/``Path``
    pointing at an existing file (streamed in chunks so a large file never has
    to be fully resident in memory).
    """

    if isinstance(data_or_path, (bytes, bytearray)):
        return hashlib.sha256(bytes(data_or_path)).hexdigest()

    path = Path(data_or_path)
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(
    data_or_path: Union[bytes, bytearray, str, Path], recorded: str
) -> bool:
    """Return ``True`` iff the SHA-256 of the data/file equals ``recorded``.

    The comparison is case-insensitive on the hex digest and tolerant of
    surrounding whitespace. A blank ``recorded`` checksum can never match
    (an unknown checksum is treated as a failure, never a silent pass).
    """

    recorded_norm = (recorded or "").strip().lower()
    if not recorded_norm:
        return False
    try:
        actual = _sha256_of(data_or_path)
    except (OSError, ValueError):
        return False
    return actual == recorded_norm


def enforce_checksum(
    data_or_path: Union[bytes, bytearray, str, Path],
    recorded: str,
    dataset_label: str,
) -> None:
    """Reject a dataset whose checksum does not match the recorded one (Req 4.2).

    On mismatch this raises :class:`IntegrityError` naming ``dataset_label`` so
    the caller can report the verification error and exclude the dataset from
    any downstream processing. On a match it returns ``None`` and the dataset
    may proceed.
    """

    if not verify_checksum(data_or_path, recorded):
        actual = ""
        try:
            actual = _sha256_of(data_or_path)
        except (OSError, ValueError):
            actual = "<unreadable>"
        raise IntegrityError(
            f"checksum verification failed for dataset '{dataset_label}': "
            f"recorded={ (recorded or '').strip().lower() or '<empty>'} "
            f"actual={actual}. Dataset rejected and excluded from downstream "
            f"processing (Req 4.2)."
        )


# --------------------------------------------------------------------------- #
# Req 4.5 — no placeholder values in empirical datasets
# --------------------------------------------------------------------------- #

def _is_synthetic(dataset_label: str) -> bool:
    """Return ``True`` if the label marks the dataset synthetic/SIMULATED."""
    label = (dataset_label or "").strip().lower()
    if not label:
        return False
    tokens = set(re.split(r"[\s_\-:/]+", label))
    return bool(tokens & SYNTHETIC_LABELS) or label in SYNTHETIC_LABELS


def _cell_is_placeholder(value: Any) -> bool:
    """Return ``True`` if a single cell value is a placeholder sentinel."""
    if value is None:
        return False
    # Numeric sentinels (int/float, and numpy scalars which compare like floats).
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        try:
            return float(value) in _NUMERIC_SENTINELS
        except (ValueError, OverflowError):
            return False
    text = str(value).strip()
    if not text:
        return False
    low = text.lower()
    if low in _STRING_SENTINELS:
        return True
    # A purely numeric string that equals a numeric sentinel.
    try:
        if float(text) in _NUMERIC_SENTINELS:
            return True
    except ValueError:
        pass
    return False


def assert_no_placeholder_in_empirical(df: Any, dataset_label: str) -> None:
    """Raise if placeholder sentinels appear in a non-synthetic dataset (Req 4.5).

    Placeholders are permitted only when ``dataset_label`` marks the dataset
    synthetic/SIMULATED (see :data:`SYNTHETIC_LABELS`); otherwise the presence
    of any sentinel means an empirical value was fabricated or stubbed, which is
    forbidden. The check scans every cell and raises :class:`PlaceholderError`
    naming the dataset, the offending column, and an example value.

    A ``None``/empty frame passes trivially (there is nothing fabricated).
    """

    if _is_synthetic(dataset_label):
        return
    if df is None:
        return
    if pd is None:  # pragma: no cover - pandas present in this project
        raise RuntimeError("pandas is required for assert_no_placeholder_in_empirical")
    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            f"assert_no_placeholder_in_empirical expects a DataFrame for "
            f"'{dataset_label}', got {type(df).__name__}"
        )
    if df.empty:
        return

    for column in df.columns:
        series = df[column]
        for value in series.tolist():
            if _cell_is_placeholder(value):
                raise PlaceholderError(
                    f"placeholder value {value!r} found in column '{column}' of "
                    f"empirical dataset '{dataset_label}'. Placeholders are "
                    f"allowed only in SIMULATED/synthetic datasets (Req 4.5)."
                )


# --------------------------------------------------------------------------- #
# Req 4.6 — structured gaps, never a fabricated number
# --------------------------------------------------------------------------- #

def record_gap(
    gaps: list[dict[str, Any]],
    field: str,
    reason: str,
    *,
    dataset: Optional[str] = None,
) -> dict[str, Any]:
    """Append a structured gap entry for a missing empirical value (Req 4.6).

    The entry records the ``field`` name and the ``reason`` it is unavailable
    and deliberately carries **no numeric value** for the field — the caller
    must never substitute a fabricated, estimated, or placeholder number. The
    appended entry is also returned for convenience.
    """

    entry: dict[str, Any] = {
        "field": field,
        "reason": reason,
        "value_available": False,
    }
    if dataset is not None:
        entry["dataset"] = dataset
    gaps.append(entry)
    return entry


# --------------------------------------------------------------------------- #
# Checksum manifest persistence
# --------------------------------------------------------------------------- #

def write_checksum_manifest(
    mapping: dict[str, str], path: Union[str, Path] = "data/interim/checksums.json"
) -> Path:
    """Write a ``{name: sha256}`` mapping to ``path`` as JSON and return it.

    Parent directories are created as needed. The manifest lets a later run
    re-verify each file via :func:`verify_checksum` / :func:`enforce_checksum`.
    """

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(dict(sorted(mapping.items())), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path
