"""Session-scoped aggregation cache keyed by dataframe content signatures."""

from __future__ import annotations

from collections import OrderedDict
from hashlib import blake2b
from typing import Any, Callable, Iterable, TypeVar

import pandas as pd
import streamlit as st

T = TypeVar("T")

_CACHE_ROOT_KEY = "__signature_aggregation_cache"


def dataframe_signature(
    df: pd.DataFrame | None,
    *,
    columns: Iterable[str] | None = None,
    salt: str = "",
) -> str:
    """Build a stable signature for a dataframe slice used by filter-aware caches."""
    h = blake2b(digest_size=16)
    h.update(str(salt).encode("utf-8"))

    if not isinstance(df, pd.DataFrame):
        h.update(b"no_df")
        return h.hexdigest()
    if df.empty:
        h.update(b"empty_df")
        return h.hexdigest()

    if columns is None:
        cols = list(df.columns)
    else:
        cols = [c for c in columns if c in df.columns]

    h.update(str(tuple(cols)).encode("utf-8"))
    h.update(str(len(df)).encode("utf-8"))

    if cols:
        hashed = pd.util.hash_pandas_object(
            df.loc[:, cols],
            index=True,
            categorize=True,
        ).to_numpy(dtype="uint64", copy=False)
    else:
        hashed = pd.util.hash_pandas_object(
            df.index.to_series(),
            index=False,
            categorize=True,
        ).to_numpy(dtype="uint64", copy=False)

    h.update(hashed.tobytes())
    return h.hexdigest()


def _cache_root() -> dict[str, OrderedDict[str, Any]]:
    root = st.session_state.get(_CACHE_ROOT_KEY)
    if isinstance(root, dict):
        return root
    root = {}
    st.session_state[_CACHE_ROOT_KEY] = root
    return root


def cached_by_signature(
    namespace: str,
    signature: str,
    compute: Callable[[], T],
    *,
    max_entries: int = 8,
) -> tuple[T, bool]:
    """Return cached value by signature or compute+store it (LRU per namespace)."""
    root = _cache_root()
    bucket = root.get(namespace)
    if not isinstance(bucket, OrderedDict):
        bucket = OrderedDict()
        root[namespace] = bucket

    if signature in bucket:
        bucket.move_to_end(signature)
        return bucket[signature], True

    value = compute()
    bucket[signature] = value
    bucket.move_to_end(signature)
    while len(bucket) > max_entries:
        bucket.popitem(last=False)
    return value, False
