from __future__ import annotations

from bug_resolution_radar.ui.insights.top_topics import _theme_color_map


def test_theme_color_map_keeps_login_and_credit_distinct_in_dark_mode() -> None:
    theme_order = [
        "Pagos",
        "Tareas",
        "Monetarias",
        "Crédito",
        "Login y acceso",
        "Softoken",
        "Transferencias",
        "Notificaciones",
        "Otros",
    ]
    color_map = _theme_color_map(theme_order=theme_order, dark_mode=True)
    assert color_map["Login y acceso"] != color_map["Crédito"]
    assert len({color_map[name] for name in theme_order}) == len(theme_order)


def test_theme_color_map_matches_credit_label_with_or_without_accent() -> None:
    accented = _theme_color_map(theme_order=["Crédito"], dark_mode=False)
    plain = _theme_color_map(theme_order=["Credito"], dark_mode=False)
    assert accented["Crédito"] == plain["Credito"]
