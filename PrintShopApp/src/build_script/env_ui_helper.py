"""
빌드 환경(Python, pyside6-uic) 탐색, .ui -> .py 변환 및 빌드된 EXE 경로 해석 모듈 (env_ui_helper.py)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from Common.log import logd
from build_script.build_targets import BuildTargets, EXE_EXTENSION
from build_script.target_config_io import DIST_DIR_NAME, WORK_DIR_NAME

VENV_DIR_NAMES: tuple[str, ...] = (".venv", "venv")
WINDOWS_SCRIPTS_DIR_NAME: str = "Scripts"
POSIX_BIN_DIR_NAME: str = "bin"

PYTHON_WINDOWS_EXE_NAME: str = "python.exe"
PYTHON_POSIX_EXE_NAME: str = "python"

UIC_EXECUTABLE_NAMES: tuple[str, ...] = ("pyside6-uic", "pyside6-uic.exe")
UIC_WINDOWS_EXE_NAME: str = "pyside6-uic.exe"
UIC_MODULE_NAME: str = "PySide6.scripts.uic"

UI_FILE_EXTENSION: str = ".ui"
PY_FILE_EXTENSION: str = ".py"

IGNORE_UI_WALK_DIRS: frozenset[str] = frozenset(
    {
        *VENV_DIR_NAMES,
        "__pycache__",
        WORK_DIR_NAME,
        DIST_DIR_NAME,
    }
)

__all__ = [
    "IGNORE_UI_WALK_DIRS",
    "POSIX_BIN_DIR_NAME",
    "PYTHON_POSIX_EXE_NAME",
    "PYTHON_WINDOWS_EXE_NAME",
    "PY_FILE_EXTENSION",
    "UIC_EXECUTABLE_NAMES",
    "UIC_MODULE_NAME",
    "UIC_WINDOWS_EXE_NAME",
    "UI_FILE_EXTENSION",
    "VENV_DIR_NAMES",
    "WINDOWS_SCRIPTS_DIR_NAME",
    "convert_ui_files",
    "find_pyside6_uic",
    "resolve_built_exe_path",
    "resolve_python_executable",
]


def resolve_python_executable(project_root: str) -> str:
    candidates: list[str] = []
    for venv_name in VENV_DIR_NAMES:
        candidates.append(
            os.path.join(project_root, venv_name, WINDOWS_SCRIPTS_DIR_NAME, PYTHON_WINDOWS_EXE_NAME)
        )
    for venv_name in VENV_DIR_NAMES:
        candidates.append(
            os.path.join(project_root, venv_name, POSIX_BIN_DIR_NAME, PYTHON_POSIX_EXE_NAME)
        )

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return sys.executable


def find_pyside6_uic(project_root: str, py_exe: str) -> list[str] | None:
    py_dir = os.path.dirname(os.path.abspath(py_exe))
    candidates: list[str] = [
        os.path.join(py_dir, UIC_WINDOWS_EXE_NAME),
        os.path.join(py_dir, WINDOWS_SCRIPTS_DIR_NAME, UIC_WINDOWS_EXE_NAME),
    ]
    for venv_name in VENV_DIR_NAMES:
        candidates.append(
            os.path.join(project_root, venv_name, WINDOWS_SCRIPTS_DIR_NAME, UIC_WINDOWS_EXE_NAME)
        )

    for exe_p in candidates:
        if os.path.isfile(exe_p):
            return [exe_p]

    for exe_name in UIC_EXECUTABLE_NAMES:
        which_uic = shutil.which(exe_name)
        if which_uic and os.path.isfile(which_uic):
            return [which_uic]

    check = subprocess.run(
        [py_exe, "-c", f"import {UIC_MODULE_NAME}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode == 0:
        return [py_exe, "-m", UIC_MODULE_NAME]

    return None


def convert_ui_files(
    project_root: str,
    src_dir: str,
    py_exe: str | None = None,
    run_cmd_fn: Callable[..., object] | None = None,
) -> tuple[int, int]:
    resolved_py = py_exe or resolve_python_executable(project_root)
    uic_cmd = find_pyside6_uic(project_root, resolved_py)
    ui_files = list(Path(src_dir).rglob(f"*{UI_FILE_EXTENSION}"))
    converted = 0
    skipped_tool = False

    for ui_path in ui_files:
        if any(part in IGNORE_UI_WALK_DIRS for part in ui_path.parts):
            continue
        py_path = ui_path.with_suffix(PY_FILE_EXTENSION)
        if not py_path.exists() or ui_path.stat().st_mtime > py_path.stat().st_mtime:
            if not uic_cmd:
                if not skipped_tool:
                    logd("  ⚠️ pyside6-uic 도구를 찾지 못해 .ui -> .py 자동 변환을 건너뜁니다.")
                    skipped_tool = True
                continue
            cmd = [*uic_cmd, str(ui_path), "-o", str(py_path)]
            try:
                if callable(run_cmd_fn):
                    run_cmd_fn(cmd, check=False)
                else:
                    subprocess.run(cmd, check=False)
                converted += 1
            except FileNotFoundError:
                logd(f"  ⚠️ uic 실행 파일 미검출로 변환 건너뜀: {ui_path.name}")

    return converted, len(ui_files)


def resolve_built_exe_path(project_root: str, target_key: str, default_exe_name: str) -> str | None:
    label = BuildTargets.get_label(target_key)
    app_dist_dir = BuildTargets.get_dist_dir(target_key, project_root)
    dist_root = BuildTargets.get_dist_root(project_root)

    candidates = [
        os.path.join(app_dist_dir, default_exe_name),
        os.path.join(app_dist_dir, f"{label}{EXE_EXTENSION}"),
        os.path.join(dist_root, label, default_exe_name),
        os.path.join(dist_root, target_key, default_exe_name),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    for search_dir in (app_dist_dir, dist_root):
        if os.path.isdir(search_dir):
            for exe_file in Path(search_dir).rglob(f"*{EXE_EXTENSION}"):
                if exe_file.name.lower() == default_exe_name.lower():
                    return str(exe_file)
    return None