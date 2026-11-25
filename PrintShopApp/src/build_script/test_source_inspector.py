from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SOURCE_ENCODING: str = "utf-8"
PYCACHE_DIR_NAME: str = "__pycache__"
MAIN_DUUNDER_NAME: str = "__name__"
MAIN_MODULE_VALUE: str = "__main__"
TARGET_IMPORT_MODULE_NAME: str = "main_app"

GUI_IMPORT_MARKERS: frozenset[str] = frozenset(
    {"PySide6", "PyQt5", "PyQt6", "tkinter", "nicegui"}
)
CLI_IMPORT_MARKERS: frozenset[str] = frozenset(
    {"argparse", "click", "typer"}
)
GUI_BASE_CLASS_KEYWORDS: tuple[str, ...] = (
    "MainWindow",
    "Dialog",
    "Widget",
    "Window",
)
PRIVATE_PREFIX: str = "_"
INIT_MODULE_STEM: str = "__init__"

__all__ = [
    "AppSourceProfile",
    "CLI_IMPORT_MARKERS",
    "DEFAULT_SOURCE_ENCODING",
    "GUI_BASE_CLASS_KEYWORDS",
    "GUI_IMPORT_MARKERS",
    "INIT_MODULE_STEM",
    "MAIN_DUUNDER_NAME",
    "MAIN_MODULE_VALUE",
    "PRIVATE_PREFIX",
    "PYCACHE_DIR_NAME",
    "TARGET_IMPORT_MODULE_NAME",
    "inspect_app_source",
]


@dataclass
class AppSourceProfile:
    app_key: str
    source_dirs: list[Path] = field(default_factory=list)
    py_file_count: int = 0
    uses_gui: bool = False
    uses_cli_parser: bool = False
    has_main_guard: bool = False
    gui_classes: list[str] = field(default_factory=list)
    top_functions: list[str] = field(default_factory=list)
    safe_import_modules: list[str] = field(default_factory=list)


def _is_safe_module_name(mod_name: str) -> bool:
    if not mod_name:
        return False
    parts = mod_name.split(".")
    return all(
        part and not part.startswith(PRIVATE_PREFIX) and part.isidentifier()
        for part in parts
    )


def _is_target_import_module(
    mod_name: str,
    target_leaf_name: str = TARGET_IMPORT_MODULE_NAME,
) -> bool:
    return mod_name == target_leaf_name or mod_name.endswith(f".{target_leaf_name}")


def _collect_project_modules(
    source_dirs: list[Path],
    src_root: Path | None = None,
    target_leaf_name: str = TARGET_IMPORT_MODULE_NAME,
) -> list[str]:
    """실제 프로젝트 소스 디렉터리 기준으로 테스트 대상 모듈(main_app)만 수집합니다."""
    mods: set[str] = set()
    base_candidates: list[Path] = []
    if src_root is not None:
        base_candidates.append(src_root)
    base_candidates.extend(source_dirs)

    roots: list[Path] = []
    seen_roots: set[Path] = set()
    for b in base_candidates:
        if not b:
            continue
        resolved = b.resolve()
        if resolved.is_dir() and resolved not in seen_roots:
            seen_roots.add(resolved)
            roots.append(resolved)

    for sdir in source_dirs:
        if not sdir.is_dir():
            continue
        for py_file in sdir.rglob("*.py"):
            if PYCACHE_DIR_NAME in py_file.parts:
                continue
            if py_file.stem.startswith(PRIVATE_PREFIX) and py_file.stem != INIT_MODULE_STEM:
                continue

            resolved_file = py_file.resolve()
            for base in roots:
                try:
                    rel = resolved_file.relative_to(base)
                except ValueError:
                    continue

                if any(part.startswith(PRIVATE_PREFIX) for part in rel.parts[:-1]):
                    continue

                parts = list(rel.parts[:-1]) + [py_file.stem]
                if parts and parts[-1] == INIT_MODULE_STEM:
                    parts = parts[:-1]
                mod_name = ".".join(parts)
                if _is_safe_module_name(mod_name) and _is_target_import_module(
                    mod_name, target_leaf_name=target_leaf_name
                ):
                    mods.add(mod_name)
                break

    return sorted(mods)


def inspect_app_source(
    source_dirs: list[Path],
    app_key: str,
    src_root: Path | None = None,
) -> AppSourceProfile:
    profile = AppSourceProfile(app_key=app_key, source_dirs=source_dirs)

    for sdir in source_dirs:
        if not sdir.is_dir():
            continue
        for py_file in sdir.rglob("*.py"):
            if PYCACHE_DIR_NAME in py_file.parts:
                continue
            profile.py_file_count += 1
            try:
                src = py_file.read_text(encoding=DEFAULT_SOURCE_ENCODING, errors="replace")
                tree = ast.parse(src, filename=str(py_file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top in GUI_IMPORT_MARKERS:
                            profile.uses_gui = True
                        if top in CLI_IMPORT_MARKERS:
                            profile.uses_cli_parser = True
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0]
                    if top in GUI_IMPORT_MARKERS:
                        profile.uses_gui = True
                    if top in CLI_IMPORT_MARKERS:
                        profile.uses_cli_parser = True
                elif isinstance(node, ast.If):
                    dumped = ast.dump(node.test)
                    if MAIN_DUUNDER_NAME in dumped and MAIN_MODULE_VALUE in dumped:
                        profile.has_main_guard = True
                elif isinstance(node, ast.ClassDef):
                    bases_dump = " ".join(ast.dump(b) for b in node.bases)
                    if any(k in bases_dump for k in GUI_BASE_CLASS_KEYWORDS):
                        profile.gui_classes.append(node.name)

            for stmt in tree.body:
                if isinstance(stmt, ast.FunctionDef) and not stmt.name.startswith(PRIVATE_PREFIX):
                    profile.top_functions.append(stmt.name)

    profile.safe_import_modules = _collect_project_modules(source_dirs, src_root=src_root)
    return profile

