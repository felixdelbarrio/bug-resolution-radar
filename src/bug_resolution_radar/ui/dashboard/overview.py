"""Compatibility wrapper for moved dashboard Overview tab module."""

from bug_resolution_radar.ui.dashboard.tabs import overview_tab as _impl

globals().update(
    {
        name: getattr(_impl, name)
        for name in dir(_impl)
        if not (name.startswith("__") and name.endswith("__"))
    }
)
