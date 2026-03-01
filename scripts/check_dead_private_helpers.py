#!/usr/bin/env python3
"""Fail when private top-level helper functions in src are unreferenced.

This guard keeps the codebase lean over time by catching orphan helpers early.
Only private top-level functions (`_name`) are checked.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

PACKAGE_NAME = "bug_resolution_radar"


@dataclass(frozen=True)
class Candidate:
    name: str
    file_path: Path
    lineno: int
    module_name: str


@dataclass(frozen=True)
class ScanRoot:
    root: Path
    module_prefix: str
    collect_candidates: bool = False


@dataclass
class ModuleInfo:
    file_path: Path
    module_name: str
    tree: ast.Module
    private_defs: List[Candidate]
    name_load_counts: Dict[str, int]


def _iter_py_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _module_name_for(file_path: Path, *, scan_root: ScanRoot) -> str:
    rel = file_path.relative_to(scan_root.root).with_suffix("")
    rel_parts = list(rel.parts)
    if rel_parts and rel_parts[-1] == "__init__":
        rel_parts = rel_parts[:-1]
    parts = [scan_root.module_prefix] + rel_parts
    return ".".join(part for part in parts if part)


def _top_level_private_defs(
    tree: ast.Module, *, file_path: Path, module_name: str
) -> List[Candidate]:
    out: List[Candidate] = []
    for node in list(tree.body):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = str(node.name or "")
        if not name.startswith("_") or name.startswith("__"):
            continue
        out.append(
            Candidate(
                name=name,
                file_path=file_path,
                lineno=int(getattr(node, "lineno", 1) or 1),
                module_name=module_name,
            )
        )
    return out


def _name_load_counts(tree: ast.Module) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            token = str(node.id or "")
            if not token:
                continue
            counts[token] = int(counts.get(token, 0) or 0) + 1
    return counts


def _resolve_from_import_module(
    current_module: str, *, level: int, module: str | None
) -> str | None:
    if level <= 0:
        return module

    current_parts = current_module.split(".")
    if len(current_parts) <= 1:
        return None
    package_parts = current_parts[:-1]
    if level - 1 > len(package_parts):
        return None
    base = package_parts[: len(package_parts) - (level - 1)]
    if module:
        base.extend(module.split("."))
    return ".".join(base) if base else None


def _collect_modules(*, scan_roots: List[ScanRoot]) -> List[ModuleInfo]:
    modules: List[ModuleInfo] = []
    for scan_root in scan_roots:
        if not scan_root.root.exists():
            continue
        for file_path in _iter_py_files(scan_root.root):
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
            module_name = _module_name_for(file_path, scan_root=scan_root)
            private_defs: List[Candidate] = []
            if scan_root.collect_candidates:
                private_defs = _top_level_private_defs(
                    tree, file_path=file_path, module_name=module_name
                )
            modules.append(
                ModuleInfo(
                    file_path=file_path,
                    module_name=module_name,
                    tree=tree,
                    private_defs=private_defs,
                    name_load_counts=_name_load_counts(tree),
                )
            )
    return modules


def _external_import_references(
    modules: List[ModuleInfo],
) -> Dict[tuple[str, str], int]:
    refs: Dict[tuple[str, str], int] = {}
    for module in modules:
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target_module = _resolve_from_import_module(
                module.module_name,
                level=int(getattr(node, "level", 0) or 0),
                module=getattr(node, "module", None),
            )
            if not target_module:
                continue
            for alias in list(node.names or []):
                imported_name = str(getattr(alias, "name", "") or "")
                if not imported_name:
                    continue
                key = (target_module, imported_name)
                refs[key] = int(refs.get(key, 0) or 0) + 1
    return refs


def _find_dead_private_helpers(*, src_root: Path, tests_root: Path) -> List[Candidate]:
    modules = _collect_modules(
        scan_roots=[
            ScanRoot(root=src_root, module_prefix=PACKAGE_NAME, collect_candidates=True),
            ScanRoot(root=tests_root, module_prefix="tests", collect_candidates=False),
        ]
    )
    import_refs = _external_import_references(modules)
    module_texts = {
        module.module_name: module.file_path.read_text(encoding="utf-8") for module in modules
    }
    dead: List[Candidate] = []

    for module in modules:
        for candidate in module.private_defs:
            internal_loads = int(module.name_load_counts.get(candidate.name, 0) or 0)
            external_direct = int(import_refs.get((candidate.module_name, candidate.name), 0) or 0)
            external_star = int(import_refs.get((candidate.module_name, "*"), 0) or 0)

            if internal_loads > 0 or external_direct > 0 or external_star > 0:
                continue

            # Defensive fallback for rare `mod._helper(...)` usage:
            # if the module itself is imported elsewhere and the attribute appears
            # as a load name, keep it.
            basename = candidate.module_name.split(".")[-1]
            attr_like_refs = 0
            for other in modules:
                if other.module_name == candidate.module_name:
                    continue
                if int(other.name_load_counts.get(basename, 0) or 0) <= 0:
                    continue
                text = module_texts.get(other.module_name, "")
                if f".{candidate.name}" in text:
                    attr_like_refs += 1
            if attr_like_refs > 0:
                continue

            dead.append(candidate)

    return sorted(dead, key=lambda c: (str(c.file_path), int(c.lineno), c.name))


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src" / PACKAGE_NAME
    tests_root = repo_root / "tests"
    dead = _find_dead_private_helpers(src_root=src_root, tests_root=tests_root)
    if not dead:
        print("No dead private helpers found.")
        return 0

    print("Dead private helpers found:")
    for item in dead:
        rel = item.file_path.relative_to(repo_root)
        print(f"- {rel}:{item.lineno} {item.name}")
    print("")
    print("Remove or wire these helpers to keep the codebase lean.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
