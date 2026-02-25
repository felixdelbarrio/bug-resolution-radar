"""Compatibility wrapper for moved dashboard export downloads module."""

from bug_resolution_radar.ui.dashboard.exports import downloads as _impl

globals().update(
    {
        name: getattr(_impl, name)
        for name in dir(_impl)
        if not (name.startswith("__") and name.endswith("__"))
    }
)
