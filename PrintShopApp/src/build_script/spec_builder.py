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
    DEFAULT_CONSOLE,
    DEFAULT_ENTRY_FILENAME,
    DEFAULT_ONEFILE,
    DEFAULT_UAC_ADMIN,
    EXE_EXTENSION,
    PyInstallerSpec,
    SPEC_EXTENSION,
    TARGET_LABELS,
    TEST_DIR_NAME,
    TargetConfig,
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

# PrintShopApp 기본 포함 리소스 (상대경로: src_rel;dest_rel)
PRINTSHOP_DEFAULT_DATAS: tuple[str, ...] = (
    "src/LinkBox/templates;LinkBox/templates",
    "src/LinkShare/web/templates;LinkShare/web/templates",
    ".env.feature.runtime;.",
)

__all__ = [
    "ENTRY_FILENAME_CANDIDATES",
    "PRINTSHOP_DEFAULT_DATAS",
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
        token_set = bool(
            self.cancel_token is not None and getattr(self.cancel_token, "is_set", False)
        )
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

    def _resolve_app_bool_flag(self, target_key: str, field_name: str, default_val: bool) -> bool:
        ov = TargetConfig.get_app_overrides().get(target_key, {})
        if isinstance(ov, dict) and isinstance(ov.get(field_name), bool):
            return bool(ov[field_name])
        return default_val

    def _resolve_project_rel_path(self, raw_path: str) -> str:
        p = Path(raw_path.strip())
        if p.is_absolute():
            return str(p.resolve())
        return str((Path(self.project_root) / Path(*raw_path.strip().split("/"))).resolve())

    def _to_spec_rel_path(self, abs_or_rel_path: str, base_dir: str) -> str:
        """가능하면 base_dir 기준 상대 경로로 변환해 .spec 이식성을 높임."""
        try:
            rel = os.path.relpath(abs_or_rel_path, base_dir)
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except ValueError:
            pass
        return abs_or_rel_path.replace("\\", "/")

    def _parse_resource_pairs(self, items: tuple[str, ...]) -> list[tuple[str, str]]:
        """'src;dest' 또는 'src:dest' 또는 단일 경로 항목을 (abs_src, dest) 튜플 리스트로 변환."""
        pairs: list[tuple[str, str]] = []
        for raw in items:
            token = str(raw).strip()
            if not token:
                continue
            if ";" in token:
                src_part, dest_part = token.split(";", 1)
            elif ":" in token and not Path(token).drive:
                src_part, dest_part = token.split(":", 1)
            else:
                src_part, dest_part = token, "."
            abs_src = self._resolve_project_rel_path(src_part)
            dest = (dest_part.strip() or ".").replace("\\", "/")
            pairs.append((abs_src, dest))
        return pairs

    def _collect_datas_pairs(
        self,
        target_key: str,
        label: str,
        py_spec: PyInstallerSpec,
        base_dir: str | None = None,
    ) -> list[tuple[str, str]]:
        """빌드에 포함할 (존재하는_소스_경로, 대상_폴더) 리소스 목록 구성."""
        rel_base = base_dir or self.project_root
        raw_items: list[str] = list(py_spec.datas or ())
        if not raw_items and (target_key == "print_shop_app" or label == "PrintShopApp"):
            raw_items.extend(PRINTSHOP_DEFAULT_DATAS)

        parsed = self._parse_resource_pairs(tuple(raw_items))
        valid_pairs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for abs_src, dest in parsed:
            if not os.path.exists(abs_src):
                logd(f"  • [{target_key}] 리소스 경로가 존재하지 않아 제외됨: {abs_src} -> {dest}")
                continue
            spec_src = self._to_spec_rel_path(abs_src, rel_base)
            key = (spec_src, dest)
            if key not in seen:
                seen.add(key)
                valid_pairs.append(key)

        return valid_pairs

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
        py_spec: PyInstallerSpec = spec_obj.pyinstaller if spec_obj else PyInstallerSpec()

        onefile_flag = bool(getattr(py_spec, "onefile", DEFAULT_ONEFILE))
        uac_admin_flag = bool(getattr(py_spec, "uac_admin", DEFAULT_UAC_ADMIN))

        os.makedirs(work_out, exist_ok=True)
        generated_spec_path = self.resolve_spec_output_path(
            target_key, spec_obj, entry_script, work_out
        )
        spec_base_dir = os.path.dirname(generated_spec_path) or self.project_root

        raw_icon = getattr(py_spec, "icon_path", None)
        resolved_icon = self._resolve_project_rel_path(raw_icon) if raw_icon else None
        spec_icon = (
            self._to_spec_rel_path(resolved_icon, spec_base_dir)
            if (resolved_icon and os.path.isfile(resolved_icon))
            else None
        )
        icon_arg = f"r'{spec_icon}'" if spec_icon else "None"

        combined_hidden: list[str] = []
        if spec_obj and spec_obj.hidden_imports:
            combined_hidden.extend(spec_obj.hidden_imports)
        if py_spec.hidden_imports:
            combined_hidden.extend(py_spec.hidden_imports)
        hidden_imports = tuple(
            dict.fromkeys(str(m).strip() for m in combined_hidden if str(m).strip())
        )
        hidden_imports_literal = repr(list(hidden_imports))

        excludes_list = list(
            dict.fromkeys(str(x).strip() for x in (py_spec.excludes or ()) if str(x).strip())
        )
        excludes_literal = repr(excludes_list)

        datas_pairs = self._collect_datas_pairs(target_key, label, py_spec, base_dir=spec_base_dir)
        binaries_pairs = [
            (self._to_spec_rel_path(s, spec_base_dir), d)
            for s, d in self._parse_resource_pairs(py_spec.binaries or ())
            if os.path.exists(s)
        ]

        datas_literal = "[" + ", ".join(f"(r{repr(s)}, {repr(d)})" for s, d in datas_pairs) + "]"
        binaries_literal = (
            "[" + ", ".join(f"(r{repr(s)}, {repr(d)})" for s, d in binaries_pairs) + "]"
        )

        pathex_entries: list[str] = []
        for base_candidate in (spec_base_dir, self.project_root, self.src_dir):
            rel_base_p = self._to_spec_rel_path(base_candidate, spec_base_dir)
            if rel_base_p not in pathex_entries:
                pathex_entries.append(rel_base_p)

        raw_pathex_all: list[str] = []
        if spec_obj and getattr(spec_obj, "extra_pathex", None):
            raw_pathex_all.extend(spec_obj.extra_pathex)
        if py_spec.extra_pathex:
            raw_pathex_all.extend(py_spec.extra_pathex)

        for raw_p in raw_pathex_all:
            cleaned = str(raw_p).strip()
            if not cleaned:
                continue
            resolved_str = self._resolve_project_rel_path(cleaned)
            if os.path.isdir(resolved_str):
                rel_p = self._to_spec_rel_path(resolved_str, spec_base_dir)
                if rel_p not in pathex_entries:
                    pathex_entries.append(rel_p)

        pathex_literal = "[" + ", ".join(f"r{repr(p)}" for p in pathex_entries) + "]"

        spec_entry_script = self._to_spec_rel_path(entry_script, spec_base_dir)

        app_ver_files = self.version_service.get_version_files(target_key)
        app_rc_path = (
            os.path.join(os.path.dirname(app_ver_files[0]), VERSION_INFO_FILENAME)
            if app_ver_files
            else None
        )
        spec_version_path = (
            self._to_spec_rel_path(app_rc_path, spec_base_dir)
            if (app_rc_path and os.path.isfile(app_rc_path))
            else None
        )
        version_arg = f"r'{spec_version_path}'" if spec_version_path else "None"

        if onefile_flag:
            exe_and_collect_block = textwrap.dedent(f"""
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
                    uac_admin={uac_admin_flag},
                    icon={icon_arg},
                    version={version_arg},
                )
                """).strip()
        else:
            exe_and_collect_block = textwrap.dedent(f"""
                exe = EXE(
                    pyz,
                    a.scripts,
                    [],
                    exclude_binaries=True,
                    name=f'{exe_stem}',
                    debug=False,
                    bootloader_ignore_signals=False,
                    strip=False,
                    upx=True,
                    console={console_flag},
                    disable_windowed_traceback=False,
                    argv_emulation=False,
                    target_arch=None,
                    codesign_identity=None,
                    entitlements_file=None,
                    uac_admin={uac_admin_flag},
                    icon={icon_arg},
                    version={version_arg},
                )
                coll = COLLECT(
                    exe,
                    a.binaries,
                    a.zipfiles,
                    a.datas,
                    strip=False,
                    upx=True,
                    upx_exclude=[],
                    name=f'{exe_stem}',
                )
                """).strip()

        spec_content = textwrap.dedent(f"""
                # -*- mode: python ; coding: utf-8 -*-

                a = Analysis(
                    [r'{spec_entry_script}'],
                    pathex={pathex_literal},
                    binaries={binaries_literal},
                    datas={datas_literal},
                    hiddenimports={hidden_imports_literal},
                    hookspath=[],
                    hooksconfig={{}},
                    runtime_hooks=[],
                    excludes={excludes_literal},
                    noarchive=False,
                )
                pyz = PYZ(a.pure)

                """).lstrip() + exe_and_collect_block + "\n"

        with open(generated_spec_path, "w", encoding=DEFAULT_TEXT_ENCODING) as f:
            f.write(spec_content)

        logd(
            f"  • [{target_key}] 기본 .spec 생성 완료: {generated_spec_path} "
            f"(entry={spec_entry_script}, exe={exe_stem}{EXE_EXTENSION}, onefile={onefile_flag}, "
            f"uac_admin={uac_admin_flag}, datas_count={len(datas_pairs)}, "
            f"hiddenimports={list(hidden_imports)})"
        )
        return generated_spec_path

    def clean_target_outputs(self, target_key: str, work_out: str, dist_out: str) -> None:
        do_clean_work = self._resolve_app_bool_flag(target_key, "clean_work", self.clean_work_out)
        do_clean_dist = self._resolve_app_bool_flag(target_key, "clean_dist", self.clean_dist_out)
        do_clean_spec = self._resolve_app_bool_flag(target_key, "clean_spec", self.clean_spec)

        if do_clean_work and os.path.isdir(work_out):
            shutil.rmtree(work_out, ignore_errors=True)
            logd(f"  • work_out 정리 완료: {work_out}")

        if do_clean_dist and os.path.isdir(dist_out):
            shutil.rmtree(dist_out, ignore_errors=True)
            logd(f"  • dist_out 정리 완료: {dist_out}")

        if do_clean_spec:
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
                logd(
                    f"  • [{target_key}] 삭제할 .spec 파일을 후보 경로에서 찾지 못해 건너뜀: {sorted(candidate_specs)}"
                )

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
                spec_path = self.generate_default_spec_file(
                    target_key, spec_obj, entry_script, work_out
                )

        if not spec_path:
            logd(
                f"  ⚠️ [{target_key}] .spec 파일 및 진입점 스크립트를 찾지 못해 빌드를 건너뜁니다."
            )
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
