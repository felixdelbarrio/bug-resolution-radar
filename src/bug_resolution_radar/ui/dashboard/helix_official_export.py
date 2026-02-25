"""Compatibility wrapper for moved Helix official export builder."""

from bug_resolution_radar.ui.dashboard.exports import helix_official_export as _impl

globals().update(
    {
        name: getattr(_impl, name)
        for name in dir(_impl)
        if not (name.startswith("__") and name.endswith("__"))
    }
)
