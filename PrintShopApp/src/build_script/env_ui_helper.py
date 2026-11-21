from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from build_targets import BuildTargets, TARGET_LABELS
from Common.log import logd


def resolve_python_executable(project_root: str) -> str:
    candidates = [
        os.path.join(project_root, ".venv", "Scripts", "python.exe"),
        os.path.join(project_root, "venv", "Scripts", "python.exe"),
        os.path.join(project_root, ".venv", "bin", "python"),
        os.path.join(project_root, "venv", "bin", "python"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return sys.executable


def find_pyside6_uic(project_root: str, py_exe: str) -> list[str] | None:
    py_dir = os.path.dirname(os.path.abspath(py_exe))
    candidates = [
        os.path.join(py_dir, "pyside6-uic.exe"),
        os.path.join(py_dir, "Scripts", "pyside6-uic.exe"),
        os.path.join(project_root, ".venv", "Scripts", "pyside6-uic.exe"),
    ]
    for exe_p in candidates:
        if os.path.isfile(exe_p):
            return [exe_p]

    which_uic = shutil.which("pyside6-uic") or shutil.which("pyside6-uic.exe")
    if which_uic and os.path.isfile(which_uic):
        return [which_uic]

    check = subprocess.run(
        [py_exe, "-c", "import PySide6.scripts.uic"],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode == 0:
        return [py_exe, "-m", "PySide6.scripts.uic"]

    return None


def convert_ui_files(
    project_root: str,
    src_dir: str,
    py_exe: str | None = None,
    run_cmd_fn=None,
) -> tuple[int, int]:
    resolved_py = py_exe or resolve_python_executable(project_root)
    uic_cmd = find_pyside6_uic(project_root, resolved_py)
    ui_files = list(Path(src_dir).rglob("*.ui"))
    converted = 0
    skipped_tool = False

    for ui_path in ui_files:
        if any(part in {".venv", "venv", "__pycache__", "build", "dist"} for part in ui_path.parts):
            continue
        py_path = ui_path.with_suffix(".py")
        if not py_path.exists() or ui_path.stat().st_mtime > py_path.stat().st_mtime:
            if not uic_cmd:
                if not skipped_tool:
                    logd("  ⚠️ pyside6-uic 도구를 찾지 못해 .ui -> .py 자동 변환을 건너뜁니다.")
                    skipped_tool = True
                continue
            try:
                if callable(run_cmd_fn):
                    run_cmd_fn([*uic_cmd, str(ui_path), "-o", str(py_path)], check=False)
                else:
                    subprocess.run([*uic_cmd, str(ui_path), "-o", str(py_path)], check=False)
                converted += 1
            except FileNotFoundError:
                logd(f"  ⚠️ uic 실행 파일 미검출로 변환 건너뜀: {ui_path.name}")

    return converted, len(ui_files)


def resolve_built_exe_path(project_root: str, target_key: str, default_exe_name: str) -> str | None:
    label = TARGET_LABELS.get(target_key, target_key)
    app_dist_dir = BuildTargets.get_dist_dir(target_key, project_root)
    dist_root = BuildTargets.get_dist_root(project_root)

    candidates = [
        os.path.join(app_dist_dir, default_exe_name),
        os.path.join(app_dist_dir, f"{label}.exe"),
        os.path.join(dist_root, label, default_exe_name),
        os.path.join(dist_root, target_key, default_exe_name),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    for search_dir in (app_dist_dir, dist_root):
        if os.path.isdir(search_dir):
            for exe_file in Path(search_dir).rglob("*.exe"):
                if exe_file.name.lower() == default_exe_name.lower():
                    return str(exe_file)
    return None