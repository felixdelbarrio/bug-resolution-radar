from __future__ import annotations

import plotly.graph_objects as go

from bug_resolution_radar.ui.style import apply_plotly_bbva


def test_apply_plotly_bbva_template_drops_deprecated_scattermapbox() -> None:
    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[2, 3], name="Serie")])

    styled = apply_plotly_bbva(fig, showlegend=True)
    template_payload = styled.layout.template.to_plotly_json()
    template_data = template_payload.get("data") if isinstance(template_payload, dict) else {}

    assert isinstance(template_data, dict)
    assert "scattermapbox" not in template_data
