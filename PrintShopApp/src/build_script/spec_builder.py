"""
PyInstaller .spec 탐색·생성 및 빌드 실행 모듈 (spec_builder.py)
"""

from __future__ import annotations

import os
import shutil
import textwrap
import threading
from pathlib import Path
from typing import Any, Callable

from Common.log import logd
from build_script.target_config import (
    AppTargetSpec,
    BuildDirConfig,
    TargetConfig,
    DEFAULT_CONSOLE,
    DEFAULT_ENTRY_FILENAME,
    EXE_EXTENSION,
    SPEC_EXTENSION,
    TARGET_LABELS,
    TEST_DIR_NAME,
    get_target_spec,
)
from build_script.target_config_io import DEFAULT_TEXT_ENCODING
from build_script.version_service import VersionService

VERSION_INFO_FILENAME: str = "version_info.txt"

ENTRY_FILENAME_CANDIDATES: tuple[str, ...] = (
    DEFAULT_ENTRY_FILENAME,
    "main.py",
    "app.py",
)

STATIC_IGNORE_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        TEST_DIR_NAME,
        ".git",
    }
)

PYINSTALLER_BASE_ARGS: tuple[str, ...] = (
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
)

__all__ = [
    "ENTRY_FILENAME_CANDIDATES",
    "PYINSTALLER_BASE_ARGS",
    "STATIC_IGNORE_DIR_NAMES",
    "SpecAndPyInstallerBuilder",
    "VERSION_INFO_FILENAME",
]


class SpecAndPyInstallerBuilder:
    def __init__(
        self,
        project_root: str,
        src_dir: str,
        dir_config: BuildDirConfig,
        version_service: VersionService,
        clean_work_out: bool = False,
        clean_dist_out: bool = False,
        clean_spec: bool = False,
        cancel_event: threading.Event | None = None,
        cancel_token: Any | None = None,
    ):
        self.project_root = os.path.abspath(project_root)
        self.src_dir = os.path.abspath(src_dir)
        self.dir_config = dir_config
        self.version_service = version_service
        self.clean_work_out = clean_work_out
        self.clean_dist_out = clean_dist_out
        self.clean_spec = clean_spec
        self.cancel_token = cancel_token
        self.cancel_event: threading.Event | None = (
            getattr(cancel_token, "event", None) if cancel_token is not None else cancel_event
        )

    def _is_cancelled(self) -> bool:
        token_set = bool(self.cancel_token is not None and getattr(self.cancel_token, "is_set", False))
        event_set = bool(self.cancel_event is not None and self.cancel_event.is_set())
        return token_set or event_set

    def _check_cancelled(self, reason: str = "사용자에 의해 빌드가 취소되었습니다.") -> None:
        if self._is_cancelled():
            raise InterruptedError(reason)

    def _get_ignored_dir_names(self) -> set[str]:
        ignored = set(STATIC_IGNORE_DIR_NAMES)
        ignored.update(
            {
                self.dir_config.work_dir_name,
                self.dir_config.dist_dir_name,
                self.dir_config.release_dir_name,
                self.dir_config.install_dir_name,
            }
        )
        return ignored

    def find_spec_file(self, target_key: str) -> str | None:
        spec = get_target_spec(target_key)
        hints = list(spec.spec_hints) if spec else [f"{target_key}{SPEC_EXTENSION}"]
        subdirs = list(spec.dir_hints) if spec else [target_key]

        candidates: list[str] = [os.path.join(self.project_root, h) for h in hints]
        for sd in subdirs:
            for h in hints:
                candidates.append(os.path.join(self.src_dir, sd, h))
                candidates.append(os.path.join(self.project_root, sd, h))

        for c in candidates:
            if os.path.isfile(c):
                return c

        lower_hints = {h.lower() for h in hints}
        ignore_parts = self._get_ignored_dir_names()
        for search_root in (self.src_dir, self.project_root):
            if not os.path.isdir(search_root):
                continue
            for spec_path in Path(search_root).rglob(f"*{SPEC_EXTENSION}"):
                if any(part in ignore_parts for part in spec_path.parts):
                    continue
                if spec_path.name.lower() in lower_hints:
                    return str(spec_path)
        return None

    def find_entry_script(self, spec_obj: AppTargetSpec | None, target_key: str) -> str | None:
        candidates: list[str] = []
        if spec_obj:
            for rel in spec_obj.entry_hints:
                candidates.append(os.path.join(self.project_root, *rel.split("/")))
            entry_names = (*ENTRY_FILENAME_CANDIDATES, f"{target_key}.py", f"{spec_obj.label}.py")
            for sd in spec_obj.dir_hints:
                for fn in entry_names:
                    candidates.append(os.path.join(self.src_dir, sd, fn))

        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    def resolve_spec_output_path(
        self,
        target_key: str,
        spec_obj: AppTargetSpec | None,
        entry_script: str,
        work_out: str,
    ) -> str:
        label = spec_obj.label if spec_obj else target_key
        entry_dir = os.path.dirname(entry_script)
        if entry_dir and os.path.isdir(entry_dir):
            return os.path.join(entry_dir, f"{label}{SPEC_EXTENSION}")

        if spec_obj:
            for sd in spec_obj.dir_hints:
                candidate_dir = os.path.join(self.src_dir, sd)
                if os.path.isdir(candidate_dir):
                    return os.path.join(candidate_dir, f"{label}{SPEC_EXTENSION}")

        os.makedirs(work_out, exist_ok=True)
        return os.path.join(work_out, f"{label}{SPEC_EXTENSION}")

    def generate_default_spec_file(
        self,
        target_key: str,
        spec_obj: AppTargetSpec | None,
        entry_script: str,
        work_out: str,
    ) -> str:
        label = spec_obj.label if spec_obj else target_key
        exe_stem = Path(spec_obj.exe_name).stem if (spec_obj and spec_obj.exe_name) else label
        console_flag = spec_obj.console if spec_obj else DEFAULT_CONSOLE
        hidden_imports = (
            tuple(dict.fromkeys(str(m).strip() for m in spec_obj.hidden_imports if str(m).strip()))
            if (spec_obj and spec_obj.hidden_imports)
            else ()
        )
        hidden_imports_literal = repr(list(hidden_imports))

        pathex_entries: list[str] = [self.project_root, self.src_dir]
        if spec_obj and getattr(spec_obj, "extra_pathex", None):
            root_path = Path(self.project_root)
            for raw_p in spec_obj.extra_pathex:
                cleaned = str(raw_p).strip()
                if not cleaned:
                    continue
                p_obj = Path(cleaned)
                resolved = (
                    p_obj.resolve()
                    if p_obj.is_absolute()
                    else (root_path / Path(*cleaned.split("/"))).resolve()
                )
                resolved_str = str(resolved)
                if os.path.isdir(resolved_str) and resolved_str not in pathex_entries:
                    pathex_entries.append(resolved_str)

        pathex_literal = "[" + ", ".join(f"r{repr(p)}" for p in pathex_entries) + "]"

        app_ver_files = self.version_service.get_version_files(target_key)
        app_rc_path = (
            os.path.join(os.path.dirname(app_ver_files[0]), VERSION_INFO_FILENAME)
            if app_ver_files
            else None
        )
        version_arg = f"r'{app_rc_path}'" if (app_rc_path and os.path.isfile(app_rc_path)) else "None"

        os.makedirs(work_out, exist_ok=True)
        generated_spec_path = self.resolve_spec_output_path(target_key, spec_obj, entry_script, work_out)

        spec_content = textwrap.dedent(
            f"""
            # -*- mode: python ; coding: utf-8 -*-

            a = Analysis(
                [r'{entry_script}'],
                pathex={pathex_literal},
                binaries=[],
                datas=[],
                hiddenimports={hidden_imports_literal},
                hookspath=[],
                hooksconfig={{}},
                runtime_hooks=[],
                excludes=[],
                noarchive=False,
            )
            pyz = PYZ(a.pure)

            exe = EXE(
                pyz,
                a.scripts,
                a.binaries,
                a.zipfiles,
                a.datas,
                [],
                name=f'{exe_stem}',
                debug=False,
                bootloader_ignore_signals=False,
                strip=False,
                upx=True,
                upx_exclude=[],
                runtime_tmpdir=None,
                console={console_flag},
                disable_windowed_traceback=False,
                argv_emulation=False,
                target_arch=None,
                codesign_identity=None,
                entitlements_file=None,
                version={version_arg},
            )
            """
        ).lstrip()

        with open(generated_spec_path, "w", encoding=DEFAULT_TEXT_ENCODING) as f:
            f.write(spec_content)

        logd(
            f"  • [{target_key}] 기본 .spec 생성 완료: {generated_spec_path} "
            f"(entry={entry_script}, exe={exe_stem}{EXE_EXTENSION}, hiddenimports={list(hidden_imports)})"
        )
        return generated_spec_path

    def clean_target_outputs(self, target_key: str, work_out: str, dist_out: str) -> None:
        if self.clean_work_out and os.path.isdir(work_out):
            shutil.rmtree(work_out, ignore_errors=True)
            logd(f"  • work_out 정리 완료: {work_out}")

        if self.clean_dist_out and os.path.isdir(dist_out):
            shutil.rmtree(dist_out, ignore_errors=True)
            logd(f"  • dist_out 정리 완료: {dist_out}")

        if self.clean_spec:
            spec_obj = get_target_spec(target_key)
            label = spec_obj.label if spec_obj else TARGET_LABELS.get(target_key, target_key)
            candidate_specs: set[str] = {
                os.path.join(work_out, f"{label}{SPEC_EXTENSION}"),
                os.path.join(self.src_dir, label, f"{label}{SPEC_EXTENSION}"),
            }
            if spec_obj:
                for sd in spec_obj.dir_hints:
                    candidate_specs.add(os.path.join(self.src_dir, sd, f"{label}{SPEC_EXTENSION}"))
                for h in spec_obj.spec_hints:
                    candidate_specs.add(os.path.join(self.project_root, h))
                    for sd in spec_obj.dir_hints:
                        candidate_specs.add(os.path.join(self.src_dir, sd, h))

            removed_any = False
            for sp in sorted(candidate_specs):
                if os.path.isfile(sp):
                    os.remove(sp)
                    logd(f"  • spec 정리 완료: {sp}")
                    removed_any = True

            if not removed_any:
                logd(f"  • [{target_key}] 삭제할 .spec 파일을 후보 경로에서 찾지 못해 건너뜀: {sorted(candidate_specs)}")

    def build_target(self, target_key: str, py_exe: str, run_cmd_fn: Callable[..., Any]) -> bool:
        self._check_cancelled(f"대상({target_key}) 빌드 시작 전 취소되었습니다.")
        work_out = TargetConfig.get_work_dir(target_key, self.project_root, create=True)
        dist_out = TargetConfig.get_dist_dir(target_key, self.project_root, create=True)
        self.clean_target_outputs(target_key, work_out, dist_out)
        self._check_cancelled(f"대상({target_key}) 산출물 정리 후 취소되었습니다.")

        spec_path = self.find_spec_file(target_key)
        if not spec_path:
            spec_obj = get_target_spec(target_key)
            entry_script = self.find_entry_script(spec_obj, target_key)
            if entry_script:
                spec_path = self.generate_default_spec_file(target_key, spec_obj, entry_script, work_out)

        if not spec_path:
            logd(f"  ⚠️ [{target_key}] .spec 파일 및 진입점 스크립트를 찾지 못해 빌드를 건너뜁니다.")
            return False

        self._check_cancelled(f"PyInstaller 실행 전 취소되었습니다 ({target_key}).")
        run_cmd_fn(
            [
                py_exe,
                *PYINSTALLER_BASE_ARGS,
                "--distpath",
                dist_out,
                "--workpath",
                work_out,
                spec_path,
            ],
            cwd=self.project_root,
        )
        return True