"""Compatibility wrapper for moved dashboard Issues tab module."""

from bug_resolution_radar.ui.dashboard.tabs import issues_tab as _impl

globals().update(
    {
        name: getattr(_impl, name)
        for name in dir(_impl)
        if not (name.startswith("__") and name.endswith("__"))
    }
)
