"""Lead-lag utilities for append-only market memory observations."""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Mapping, Sequence

def bookmaker_first_seen(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Return earliest captured_at timestamp observed for each bookmaker."""
    first: dict[str, str] = {}
    for row in rows:
        ts = str(row.get("captured_at") or "")
        for quote in row.get("quotes") or []:
            if not isinstance(quote, Mapping): continue
            b = str(quote.get("bookmaker") or "")
            if b and ts and (b not in first or ts < first[b]): first[b] = ts
    return dict(sorted(first.items()))

def line_change_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count fingerprint changes by bookmaker in temporal order."""
    last: dict[str, str] = {}; counts: dict[str, int] = defaultdict(int)
    for row in sorted(rows, key=lambda r: str(r.get("captured_at") or "")):
        for quote in row.get("quotes") or []:
            if not isinstance(quote, Mapping): continue
            b = str(quote.get("bookmaker") or "")
            meta = quote.get("metadata") if isinstance(quote.get("metadata"), Mapping) else {}
            fp = str(meta.get("fingerprint") or row.get("fingerprint") or "")
            if not b or not fp: continue
            if b in last and last[b] != fp: counts[b] += 1
            last[b] = fp
    return dict(sorted(counts.items()))
