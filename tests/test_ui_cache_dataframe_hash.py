from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.cache import dataframe_signature, streamlit_cache_df_hash


def test_streamlit_cache_df_hash_supports_unhashable_object_values() -> None:
    df = pd.DataFrame(
        [
            {"key": "A-1", "labels": ["foo", "bar"], "meta": {"n": 1}},
            {"key": "A-2", "labels": ["baz"], "meta": {"n": 2}},
        ]
    )

    digest = streamlit_cache_df_hash(df)
    assert isinstance(digest, str)
    assert digest


def test_streamlit_cache_df_hash_is_stable_for_same_dataframe_content() -> None:
    df1 = pd.DataFrame([{"k": "x", "labels": ["a", "b"]}, {"k": "y", "labels": ["c"]}])
    df2 = pd.DataFrame([{"k": "x", "labels": ["a", "b"]}, {"k": "y", "labels": ["c"]}])

    assert streamlit_cache_df_hash(df1) == streamlit_cache_df_hash(df2)


def test_dataframe_signature_fallback_handles_list_columns() -> None:
    df = pd.DataFrame([{"id": "1", "components": ["api", "db"]}, {"id": "2", "components": []}])

    sig = dataframe_signature(df, columns=["id", "components"], salt="unit-test")
    assert isinstance(sig, str)
    assert sig
