"""General date and utility helpers shared by ingestion and UI code."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_int_list(s: str) -> List[int]:
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def parse_age_buckets(spec: str) -> List[Tuple[int, int]]:
    buckets: List[Tuple[int, int]] = []
    for part in (p.strip() for p in spec.split(",") if p.strip()):
        if part.startswith(">"):
            lo = int(part[1:])
            buckets.append((lo, 10**9))
        elif "-" in part:
            lo_s, hi_s = part.split("-", 1)
            buckets.append((int(lo_s), int(hi_s)))
    return buckets
