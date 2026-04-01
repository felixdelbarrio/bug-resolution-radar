import pandas as pd

from bug_resolution_radar.ui.insights import top_topics


def test_sort_topics_by_volume_keeps_others_last() -> None:
    top_tbl = pd.DataFrame(
        {
            "tema": ["Otros", "Pagos", "Crédito", "Monetarias"],
            "open_count": [67, 30, 15, 9],
            "pct_open": [55.0, 24.0, 12.0, 9.0],
        }
    )

    out = top_topics._sort_topics_by_volume_with_others_last(top_tbl)

    assert out["tema"].tolist() == ["Pagos", "Crédito", "Monetarias", "Otros"]
    assert out["open_count"].tolist() == [30, 15, 9, 67]


def test_sort_topics_by_volume_treats_otros_case_insensitive() -> None:
    top_tbl = pd.DataFrame(
        {
            "tema": ["oTrOs", "Tareas", "Login y acceso"],
            "open_count": [99, 8, 8],
            "pct_open": [86.0, 7.0, 7.0],
        }
    )

    out = top_topics._sort_topics_by_volume_with_others_last(top_tbl)

    assert out["tema"].tolist() == ["Login y acceso", "Tareas", "oTrOs"]


def test_stacked_theme_order_keeps_others_as_topmost_segment() -> None:
    order = top_topics._stacked_theme_order(
        ["Otros", "Pagos", "Monetarias", "Tareas"],
        theme_count_by_label={"Otros": 202, "Pagos": 54, "Monetarias": 44, "Tareas": 47},
    )

    assert order == ["Pagos", "Tareas", "Monetarias", "Otros"]


def test_stacked_theme_order_normalizes_other_aliases() -> None:
    order = top_topics._stacked_theme_order(
        ["Pagos", "other", "Tareas"],
        theme_count_by_label={"Pagos": 10, "other": 500, "Tareas": 12},
    )

    assert order == ["Tareas", "Pagos", "other"]
