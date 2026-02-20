from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.insights.copilot import (
    answer_copilot_question,
    build_copilot_suggestions,
    choose_next_best_action,
    classify_question_intent,
    learned_intents_caption,
    list_next_best_actions,
    normalize_intent_counts,
    resolve_filters_against_open_df,
    route_copilot_action,
)


def test_classify_question_intent_routes_core_business_questions() -> None:
    assert classify_question_intent("Cual es el mayor riesgo cliente hoy?") == "risk"
    assert classify_question_intent("Que cuello de botella penaliza mas el flujo?") == "bottleneck"
    assert classify_question_intent("Que accion concreta priorizo esta semana?") == "action"
    assert classify_question_intent("Como cambio respecto a mi ultima sesion?") == "change"


def test_normalize_intent_counts_clamps_invalid_values() -> None:
    counts = normalize_intent_counts({"risk": "2", "action": -5, "other": "bad"})
    assert counts["risk"] == 2
    assert counts["action"] == 0
    assert counts["other"] == 0


def test_build_copilot_suggestions_adapts_to_learned_intent() -> None:
    snapshot = {
        "critical_pct": 0.18,
        "critical_unassigned_count": 2,
        "blocked_pct": 0.02,
        "net_14": 4,
        "duplicate_share": 0.04,
    }
    suggestions = build_copilot_suggestions(
        snapshot=snapshot,
        baseline_snapshot={"open_total": 100},
        next_action=None,
        intent_counts={"bottleneck": 5, "risk": 2},
        limit=6,
    )
    assert suggestions
    assert "cuello de botella" in suggestions[0].lower()
    assert any("ultima sesion" in x.lower() for x in suggestions)


def test_learned_intents_caption_exposes_personalization_signal() -> None:
    caption = learned_intents_caption({"action": 4, "risk": 2})
    assert caption is not None
    assert "accion recomendada" in caption


def test_choose_next_best_action_prioritizes_critical_unassigned() -> None:
    action = choose_next_best_action(
        {
            "critical_unassigned_count": 3,
            "blocked_count": 6,
            "blocked_pct": 0.2,
            "net_14": 8,
            "aged30_pct": 0.30,
            "duplicate_share": 0.15,
            "top_status": "In Progress",
        }
    )
    assert action.title == "Asignacion de ownership critico"
    assert action.assignee_filters == ["(sin asignar)"]


def test_answer_copilot_question_compares_baseline() -> None:
    ans = answer_copilot_question(
        question="Como ha cambiado la situacion desde mi ultima sesion?",
        snapshot={"open_total": 50, "blocked_count": 6, "net_14": 3, "critical_count": 8},
        baseline_snapshot={"open_total": 42, "blocked_count": 4},
    )
    assert "Comparado con la ultima sesion" in ans.answer
    assert ans.confidence > 0.7


def test_route_copilot_action_uses_next_action_filters_for_risk_intent() -> None:
    next_action = choose_next_best_action(
        {
            "critical_unassigned_count": 2,
            "blocked_count": 0,
            "blocked_pct": 0.0,
            "net_14": 0,
            "aged30_pct": 0.0,
            "duplicate_share": 0.0,
            "top_status": "In Progress",
        }
    )
    route = route_copilot_action(
        question="Cual es el mayor riesgo cliente hoy?",
        snapshot={"blocked_count": 1, "top_status": "In Progress"},
        next_action=next_action,
    )
    assert route.section == "issues"
    assert route.priority_filters is not None and "High" in route.priority_filters
    assert route.assignee_filters == ["(sin asignar)"]


def test_route_copilot_action_routes_duplicates_to_insights_tab() -> None:
    route = route_copilot_action(
        question="Cuanto backlog perdemos en duplicidades?",
        snapshot={"duplicate_share": 0.22},
        next_action=None,
    )
    assert route.section == "insights"
    assert route.insights_tab == "duplicates"


def test_route_copilot_action_uses_final_stage_cta_for_terminal_status() -> None:
    route = route_copilot_action(
        question="Que cuello de botella tenemos ahora?",
        snapshot={"blocked_count": 0, "top_status": "Accepted"},
        next_action=None,
    )
    assert route.section == "issues"
    assert route.cta == "Revisar tramo final en Issues"
    assert route.status_filters == ["Accepted"]


def test_resolve_filters_against_open_df_maps_blocked_variants() -> None:
    open_df = pd.DataFrame(
        {
            "status": ["Blocked by vendor", "In Progress"],
            "priority": ["High", "Medium"],
            "assignee": ["ana", "luis"],
        }
    )
    status, priority, assignee = resolve_filters_against_open_df(
        open_df=open_df,
        status_filters=["Blocked", "Bloqueado"],
        priority_filters=[],
        assignee_filters=[],
    )
    assert "Blocked by vendor" in status
    assert priority == []
    assert assignee == []


def test_resolve_filters_against_open_df_relaxes_to_avoid_empty_result() -> None:
    open_df = pd.DataFrame(
        {
            "status": ["Blocked by vendor", "In Progress"],
            "priority": ["High", "Medium"],
            "assignee": ["ana", "luis"],
        }
    )
    status, priority, assignee = resolve_filters_against_open_df(
        open_df=open_df,
        status_filters=["Blocked"],
        priority_filters=["Highest"],
        assignee_filters=["(sin asignar)"],
    )
    # The strict combination has no matches; resolver must relax to a non-empty route.
    assert status or priority or assignee


def test_list_next_best_actions_returns_ordered_sequence() -> None:
    actions = list_next_best_actions(
        snapshot={
            "critical_unassigned_count": 2,
            "blocked_count": 4,
            "blocked_pct": 0.11,
            "net_14": 6,
            "aged30_pct": 0.30,
            "duplicate_share": 0.18,
            "top_status": "In Progress",
        }
    )
    assert len(actions) >= 4
    assert actions[0].title == "Asignacion de ownership critico"
    assert any(a.title == "Revision de bloqueos activos" for a in actions)


def test_answer_copilot_bottleneck_avoids_neck_language_for_final_status() -> None:
    ans = answer_copilot_question(
        question="Que cuello de botella tenemos?",
        snapshot={
            "top_status": "Accepted",
            "top_status_share": 0.42,
            "blocked_count": 0,
            "open_total": 100,
            "net_14": 2,
            "critical_count": 12,
        },
    )
    assert "no se interpreta como cuello de botella" in ans.answer.lower()
    assert "ready to deploy" in ans.answer.lower()


def test_build_copilot_suggestions_uses_final_stage_wording() -> None:
    suggestions = build_copilot_suggestions(
        snapshot={
            "top_status": "Accepted",
            "top_status_is_final": True,
            "critical_pct": 0.0,
            "critical_unassigned_count": 0,
            "blocked_pct": 0.0,
            "net_14": 0,
            "duplicate_share": 0.0,
        },
        baseline_snapshot=None,
        next_action=None,
        intent_counts={"bottleneck": 3},
        limit=4,
    )
    assert any("friccion del tramo final" in s.lower() for s in suggestions)
    assert not any("cuello de botella" in s.lower() for s in suggestions)
