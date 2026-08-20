from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_gpc_quality_script_validates_the_real_local_webapp() -> None:
    result = subprocess.run(
        ["node", "scripts/check_gpc_quality.mjs"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "GPC quality gate OK" in result.stdout
    assert "17 nodos de arranque" in result.stdout


def test_webapp_reports_incomplete_html_deployments_without_null_errors() -> None:
    app = _text("apps-script/App.html")

    assert "const REQUIRED_SHELL_IDS = Object.freeze([" in app
    assert "WEBAPP_SHELL_MISMATCH" in app
    assert "Publica una versión nueva incluyendo todos los archivos HTML." in app
    assert "showAccessError(error);" in app
    assert "const table = $('runsTable');" in app


def test_navigation_resets_each_section_to_its_primary_view() -> None:
    app = _text("apps-script/App.html")

    assert "if (panel === 'insights') state.insightsId = 'evolution';" in app
    assert "if (panel === 'trends') state.trendChart = 'timeseries';" in app
    assert "if (panel === 'issues') state.issuesView = 'Cards';" in app
    assert "if (state.route === 'settings') state.settingsTab = 'health';" in app


def test_theme_is_only_toggled_from_shell_and_persisted_across_contract_versions() -> None:
    app = _text("apps-script/App.html")

    assert "window.localStorage.setItem('bug-resolution-radar:theme'" in app
    assert "window.localStorage.getItem('bug-resolution-radar:theme')" in app
    assert "$('themeToggle').addEventListener('click'" in app
    assert 'id="themeLight"' not in app
    assert 'id="themeDark"' not in app


def test_snapshot_import_has_visible_busy_state_and_prevents_repeated_actions() -> None:
    app = _text("apps-script/App.html")
    design = _text("apps-script/DesignSystem.html")

    assert 'id="transferOperationStatus"' in app
    assert "setTransferBusy(true, {" in app
    assert "button.disabled = Boolean(active)" in app
    assert "Validando integridad y preparando el traslado" in app
    assert "Publicando el nuevo snapshot" in app
    assert ".transfer-operation-status" in design


def test_makefile_exposes_local_webapp_and_gpc_gate() -> None:
    makefile = _text("Makefile")

    assert "runWebapp: _ensure-source-current _ensure-node" in makefile
    assert 'node scripts/run_webapp_local.mjs --host "$(WEBAPP_HOST)"' in makefile
    assert "$(WEBAPP_ARGS)" in makefile
    assert "ci-gpc: _ensure-backend _ensure-node" in makefile
    assert "tests/test_apps_script_cloud_contract.py" in makefile
    assert "tests/test_gpc_delivery_controls.py" in makefile
    assert "ci: ci-format ci-typecheck ci-coverage ci-quality ci-gpc" in makefile


def test_gpc_workflow_guards_develop_and_master() -> None:
    workflow = _text(".github/workflows/gpc-quality-gate.yml")

    assert "name: GPC Quality Gate" in workflow
    assert workflow.count("- develop") == 2
    assert workflow.count("- master") == 2
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "run: make ci-gpc" in workflow
    assert "timeout-minutes: 15" in workflow
    assert "contents: read" in workflow


def test_master_promotion_runs_all_platform_builds_before_merge() -> None:
    for name in ("build-linux.yml", "build-macos.yml", "build-windows.yml"):
        workflow = _text(f".github/workflows/{name}")
        assert "pull_request:" in workflow
        assert "      - master" in workflow
        assert "github.event_name == 'pull_request'" in workflow


def test_documented_wow_has_branch_protection_and_release_evidence() -> None:
    wow = _text("docs/GPC_WOW.md")

    for expected in (
        "feature → develop",
        "develop → master",
        "GPC Quality Gate",
        "Build Binary (Linux)",
        "Build Binary (macOS)",
        "Build Binary (Windows)",
        "Require branches to be up to date",
        "Bloquear pushes directos",
        "setupApplication()",
        "snapshot `.brr` v3",
    ):
        assert expected in wow


def test_pr_template_and_codeowners_cover_critical_gpc_changes() -> None:
    template = _text(".github/pull_request_template.md")
    owners = _text(".github/CODEOWNERS")

    for expected in (
        "make CI",
        "make runWebapp",
        "plan de rollback",
        "develop → master",
        "dataVersion",
    ):
        assert expected in template

    for expected in (
        "/apps-script/",
        "/src/bug_resolution_radar/services/cloud_projection.py",
        "/src/bug_resolution_radar/services/data_transfer.py",
        "/src/bug_resolution_radar/common/security.py",
        "/.github/workflows/",
    ):
        assert expected in owners
