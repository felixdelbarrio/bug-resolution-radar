from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_python_toolchain_uses_supported_series() -> None:
    series = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    major, minor = map(int, series.split("."))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    target = f"py{major}{minor}"

    assert sys.version_info[:2] == (major, minor)
    assert project["project"]["requires-python"] == f">={series},<{major}.{minor + 1}"
    assert project["tool"]["ruff"]["target-version"] == target
    assert project["tool"]["black"]["target-version"] == [target]
    assert project["tool"]["mypy"]["python_version"] == series


def test_python_workflows_use_shared_version_file() -> None:
    workflows = ROOT / ".github" / "workflows"
    checked = 0
    for path in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
        text = path.read_text(encoding="utf-8")
        setups = text.count("uses: actions/setup-python@")
        if setups:
            assert text.count("python-version-file: .python-version") == setups, path.name
            assert "python-version:" not in text, path.name
            checked += setups
    assert checked > 0


@pytest.mark.skipif(os.name != "posix" or shutil.which("make") is None, reason="POSIX Make")
def test_make_checks_existing_python_environment() -> None:
    command = ["make", "_ensure-backend", f"VENV={sys.prefix}"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    major, minor = sys.version_info[:2]
    wrong_series = f"{major}.{minor + 1}"
    result = subprocess.run(
        [*command, f"PYTHON_VERSION={wrong_series}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert f"BRR requiere Python {wrong_series}" in result.stderr


@pytest.mark.skipif(os.name != "posix" or shutil.which("make") is None, reason="POSIX Make")
def test_make_setup_handles_make_path_with_spaces(tmp_path: Path) -> None:
    make = shutil.which("make")
    assert make is not None
    tool_dir = tmp_path / "Xcode Corporate.app" / "usr" / "bin"
    tool_dir.mkdir(parents=True)
    make_path = tool_dir / "make"
    make_path.symlink_to(make)

    # Exercise setup and its recursive make without installing dependencies.
    result = subprocess.run(
        [
            make,
            "setup",
            f"MAKE={make_path}",
            f"VENV={sys.prefix}",
            "PIP=true",
            "NPM=true",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
