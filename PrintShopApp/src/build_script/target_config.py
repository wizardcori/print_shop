"""
앱별 빌드 대상 상수 및 스펙 정의 모듈 (target_config.py)
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from Common.path_mgr import PathMgr
from build_script.target_config_io import (
    APP_OVERRIDE_FIELDS,
    BuildDirConfig,
    DEFAULT_CONFIG_FILENAME,
    DIST_DIR_NAME,
    ENV_APP_OVERRIDES_KEY,
    ENV_DIR_KEYS,
    INSTALL_DIR_NAME,
    RELEASE_DIR_NAME,
    WORK_DIR_NAME,
    merge_app_override_dicts,
    normalize_str_tuple,
    parse_cli_app_override_tokens,
    resolve_app_overrides,
    write_build_config_json,
)

PREFIX: str = "PrintShop"
MAIN_APP_ORDER: str = "1"
MAIN_APP_RAW_NAME: str = "App"
MAIN_APP_OVERRIDE_NAME: str = f"{PREFIX}{MAIN_APP_RAW_NAME}"
INSTALLER_TARGET_KEY: str = "Installer"
INSTALLER_DEFAULT_LABEL: str = f"{PREFIX}{INSTALLER_TARGET_KEY}"
TEST_DIR_NAME: str = "test"

DEFAULT_ENTRY_FILENAME: str = "main_app.py"
DEFAULT_VERSION_FILENAME: str = "version.txt"
SRC_DIR_NAME: str = "src"
EXE_EXTENSION: str = ".exe"
SPEC_EXTENSION: str = ".spec"
UNKNOWN_ORDER_SORT_KEY: int = 999999

# 빌드 및 배포 정책 기본값 상수
DEFAULT_CONSOLE: bool = True
DEFAULT_COPY_TO_TEST: bool = True
DEFAULT_COPY_TO_ARCHIVE: bool = True
DEFAULT_INCLUDE_IN_INSTALLER: bool = True
DEFAULT_STANDALONE_INSTALLER: bool = False
DEFAULT_IS_INSTALLER: bool = False
DEFAULT_RUN_TEST: bool = True

DEFAULT_ONEFILE: bool = True
DEFAULT_UAC_ADMIN: bool = False

LEGACY_TARGET_ALIASES: dict[str, str] = {
    "app": MAIN_APP_OVERRIDE_NAME,
    "main_app": MAIN_APP_OVERRIDE_NAME,
    "update_service": "UpdateService",
    "update_manager": "UpdateManager",
    "version_viewer": "VersionViewer",
    "build_manager_app": "BuildManagerApp",
    "installer": INSTALLER_TARGET_KEY,
}

__all__ = [
    "ALL_TARGETS",
    "APP_OVERRIDE_FIELDS",
    "AppTargetSpec",
    "BuildDirConfig",
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_CONSOLE",
    "DEFAULT_COPY_TO_ARCHIVE",
    "DEFAULT_COPY_TO_TEST",
    "DEFAULT_ENTRY_FILENAME",
    "DEFAULT_INCLUDE_IN_INSTALLER",
    "DEFAULT_IS_INSTALLER",
    "DEFAULT_ONEFILE",
    "DEFAULT_RUN_TEST",
    "DEFAULT_STANDALONE_INSTALLER",
    "DEFAULT_UAC_ADMIN",
    "DEFAULT_VERSION_FILENAME",
    "DIST_DIR_NAME",
    "ENV_APP_OVERRIDES_KEY",
    "ENV_DIR_KEYS",
    "EXE_EXTENSION",
    "INSTALLER_DEFAULT_LABEL",
    "INSTALLER_TARGET_KEY",
    "INSTALL_DIR_NAME",
    "InnoSetupSpec",
    "LABELS",
    "LEGACY_TARGET_ALIASES",
    "MAIN_APP_ORDER",
    "MAIN_APP_OVERRIDE_NAME",
    "MAIN_APP_RAW_NAME",
    "PREFIX",
    "PyInstallerSpec",
    "RELEASE_DIR_NAME",
    "SPEC_EXTENSION",
    "SRC_DIR_NAME",
    "TARGET_CLASSES",
    "TARGET_LABELS",
    "TARGET_SPECS",
    "TEST_DIR_NAME",
    "TargetConfig",
    "UNKNOWN_ORDER_SORT_KEY",
    "WORK_DIR_NAME",
    "get_build_target_helpers",
    "get_target_spec",
    "inject_target_records",
    "parse_cli_app_override_tokens",
]


def _validate_single_segment_name(name: str, kind: str) -> str:
    """루트 폴더명 및 앱/인스톨러 폴더명이 단일 디렉터리 세그먼트인지 검증."""
    cleaned = str(name or "").strip()
    if not cleaned or cleaned in (".", ".."):
        raise ValueError(f"유효하지 않은 {kind} 이름입니다: '{name}'")
    if "/" in cleaned or "\\" in cleaned or Path(cleaned).is_absolute():
        raise ValueError(f"{kind} 이름에는 경로 구분자나 절대경로를 사용할 수 없습니다: '{name}'")
    return cleaned


def _order_sort_key(order_val: Any) -> int:
    return int(order_val) if str(order_val).isdigit() else UNKNOWN_ORDER_SORT_KEY


@dataclass(frozen=True)
class PyInstallerSpec:
    """PyInstaller 빌드 전용 예비/세부 설정."""

    onefile: bool = DEFAULT_ONEFILE
    uac_admin: bool = DEFAULT_UAC_ADMIN
    icon_path: str | None = None
    hidden_imports: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    datas: tuple[str, ...] = ()
    binaries: tuple[str, ...] = ()
    extra_pathex: tuple[str, ...] = ()


@dataclass(frozen=True)
class InnoSetupSpec:
    """Inno Setup 인스톨러 전용 예비/세부 설정."""

    install_subdir: str = ""
    excludes: str = ""
    flags: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    extra_defines: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AppTargetSpec:
    order: str
    key: str
    name: str
    label: str
    exe_name: str
    spec_hints: tuple[str, ...]
    dir_hints: tuple[str, ...]
    entry_hints: tuple[str, ...] = field(default_factory=tuple)
    console: bool = DEFAULT_CONSOLE
    version_rel_paths: tuple[str, ...] = field(default_factory=tuple)
    copy_to_test: bool = DEFAULT_COPY_TO_TEST
    run_test: bool = DEFAULT_RUN_TEST
    copy_to_archive: bool = DEFAULT_COPY_TO_ARCHIVE
    include_in_installer: bool = DEFAULT_INCLUDE_IN_INSTALLER
    standalone_installer: bool = DEFAULT_STANDALONE_INSTALLER
    is_installer: bool = DEFAULT_IS_INSTALLER
    hidden_imports: tuple[str, ...] = field(default_factory=tuple)
    extra_pathex: tuple[str, ...] = field(default_factory=tuple)
    pyinstaller: PyInstallerSpec = field(default_factory=PyInstallerSpec)
    inno: InnoSetupSpec = field(default_factory=InnoSetupSpec)
    extra: dict[str, Any] = field(default_factory=dict)


class _TargetConfigMeta(type):
    """RECORDS 변경 시 클래스 변수(TARGET_CLASSES, TARGET_SPECS, ALL_TARGETS, LABELS 등)를 갱신."""

    def __setattr__(cls, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name == "RECORDS":
            cls._rebuild_target_mappings(value)


class TargetConfig(metaclass=_TargetConfigMeta):
    """앱 및 인스톨러 대상 레코드, 설정 및 경로 헬퍼를 관리하는 클래스."""

    PREFIX: str = PREFIX
    TEST_DIR_NAME: str = TEST_DIR_NAME
    _dir_config: BuildDirConfig | None = None
    _base_records: list[dict] = []
    _app_overrides: dict[str, dict[str, Any]] = {}
    RECORDS: list[dict] = []

    TARGET_CLASSES: tuple[type[AppTargetSpec], ...] = ()
    TARGET_SPECS: tuple[AppTargetSpec, ...] = ()
    SPECS: tuple[AppTargetSpec, ...] = ()
    BY_KEY: dict[str, AppTargetSpec] = {}
    BY_ORDER: dict[str, AppTargetSpec] = {}
    ALL_TARGETS: dict[str, str] = {}
    LABELS: dict[str, str] = {}
    TARGET_LABELS: dict[str, str] = LABELS

    @classmethod
    def _build_pyinstaller_dict(cls, raw: Any) -> dict[str, Any]:
        src = raw if isinstance(raw, dict) else {}
        icon_val = src.get("icon_path")
        return {
            "onefile": bool(src.get("onefile", DEFAULT_ONEFILE)),
            "uac_admin": bool(src.get("uac_admin", DEFAULT_UAC_ADMIN)),
            "icon_path": str(icon_val).strip() if icon_val else None,
            "hidden_imports": normalize_str_tuple(src.get("hidden_imports")) or (),
            "excludes": normalize_str_tuple(src.get("excludes")) or (),
            "datas": normalize_str_tuple(src.get("datas")) or (),
            "binaries": normalize_str_tuple(src.get("binaries")) or (),
            "extra_pathex": normalize_str_tuple(src.get("extra_pathex")) or (),
        }

    @classmethod
    def _build_inno_dict(cls, raw: Any) -> dict[str, Any]:
        src = raw if isinstance(raw, dict) else {}
        raw_defines = src.get("extra_defines")
        defines_clean: dict[str, str] = {}
        if isinstance(raw_defines, dict):
            for k, v in raw_defines.items():
                if str(k).strip() and v is not None:
                    defines_clean[str(k).strip()] = str(v)
        return {
            "install_subdir": str(src.get("install_subdir") or "").strip(),
            "excludes": str(src.get("excludes") or "").strip(),
            "flags": normalize_str_tuple(src.get("flags")) or (),
            "components": normalize_str_tuple(src.get("components")) or (),
            "tasks": normalize_str_tuple(src.get("tasks")) or (),
            "extra_defines": defines_clean,
        }

    @classmethod
    def _apply_override_to_record(cls, base_rec: dict, override: dict[str, Any]) -> dict:
        rec = dict(base_rec)
        prefix = rec.get("prefix", cls.PREFIX)

        if "label" in override and isinstance(override["label"], str) and override["label"].strip():
            rec["label"] = _validate_single_segment_name(override["label"].strip(), "폴더 라벨")

        resolved_label = rec["label"]

        if "dir_hints" in override:
            dh = normalize_str_tuple(override["dir_hints"])
            if dh:
                rec["dir_hints"] = dh

        primary_dir = rec["dir_hints"][0] if rec.get("dir_hints") else rec["name"]

        if "exe_name" in override and isinstance(override["exe_name"], str) and override["exe_name"].strip():
            rec["exe_name"] = override["exe_name"].strip()
        elif "label" in override:
            rec["exe_name"] = f"{resolved_label}{EXE_EXTENSION}"

        if "spec_hints" in override:
            sh = normalize_str_tuple(override["spec_hints"])
            if sh:
                rec["spec_hints"] = sh
        elif "label" in override:
            rec["spec_hints"] = (f"{resolved_label}{SPEC_EXTENSION}",)

        if "entry_hints" in override:
            eh = normalize_str_tuple(override["entry_hints"])
            if eh:
                rec["entry_hints"] = eh
        elif "entry_file" in override and isinstance(override["entry_file"], str) and override["entry_file"].strip():
            entry_fn = override["entry_file"].strip().lstrip("/\\")
            rec["entry_hints"] = (
                (entry_fn,)
                if entry_fn.startswith(f"{SRC_DIR_NAME}/")
                else (f"{SRC_DIR_NAME}/{primary_dir}/{entry_fn}",)
            )

        if "version_rel_paths" in override:
            vr = normalize_str_tuple(override["version_rel_paths"])
            if vr:
                rec["version_rel_paths"] = vr
        elif "version_file" in override and isinstance(override["version_file"], str) and override["version_file"].strip():
            ver_fn = override["version_file"].strip().lstrip("/\\")
            rec["version_rel_paths"] = (
                (ver_fn,)
                if ver_fn.startswith(f"{SRC_DIR_NAME}/")
                else (f"{SRC_DIR_NAME}/{primary_dir}/{ver_fn}",)
            )

        if "console" in override and isinstance(override["console"], bool):
            rec["console"] = override["console"]

        for flag_key in (
            "copy_to_test",
            "run_test",
            "copy_to_archive",
            "include_in_installer",
            "standalone_installer",
            "is_installer",
        ):
            if flag_key in override and isinstance(override[flag_key], bool):
                rec[flag_key] = override[flag_key]

        for tuple_key in ("hidden_imports", "extra_pathex"):
            if tuple_key in override:
                norm_t = normalize_str_tuple(override[tuple_key])
                if norm_t is not None:
                    rec[tuple_key] = norm_t

        py_dict = cls._build_pyinstaller_dict(rec.get("pyinstaller"))
        if isinstance(override.get("pyinstaller"), dict):
            py_dict.update(cls._build_pyinstaller_dict({**py_dict, **override["pyinstaller"]}))
        py_flat_map = {
            "pyinstaller_onefile": ("onefile", lambda v: bool(v) if isinstance(v, bool) else py_dict["onefile"]),
            "pyinstaller_uac_admin": ("uac_admin", lambda v: bool(v) if isinstance(v, bool) else py_dict["uac_admin"]),
            "pyinstaller_icon_path": ("icon_path", lambda v: str(v).strip() if v else None),
            "pyinstaller_hidden_imports": ("hidden_imports", lambda v: normalize_str_tuple(v) or ()),
            "pyinstaller_excludes": ("excludes", lambda v: normalize_str_tuple(v) or ()),
            "pyinstaller_datas": ("datas", lambda v: normalize_str_tuple(v) or ()),
            "pyinstaller_binaries": ("binaries", lambda v: normalize_str_tuple(v) or ()),
            "pyinstaller_extra_pathex": ("extra_pathex", lambda v: normalize_str_tuple(v) or ()),
        }
        for flat_k, (sub_k, conv_fn) in py_flat_map.items():
            if flat_k in override:
                py_dict[sub_k] = conv_fn(override[flat_k])
        rec["pyinstaller"] = py_dict

        inno_dict = cls._build_inno_dict(rec.get("inno"))
        if isinstance(override.get("inno"), dict):
            merged_inno_src = {
                **inno_dict,
                **override["inno"],
                "extra_defines": {
                    **inno_dict.get("extra_defines", {}),
                    **(
                        override["inno"].get("extra_defines")
                        if isinstance(override["inno"].get("extra_defines"), dict)
                        else {}
                    ),
                },
            }
            inno_dict = cls._build_inno_dict(merged_inno_src)
        inno_flat_map = {
            "inno_install_subdir": ("install_subdir", lambda v: str(v or "").strip()),
            "inno_excludes": ("excludes", lambda v: str(v or "").strip()),
            "inno_flags": ("flags", lambda v: normalize_str_tuple(v) or ()),
            "inno_components": ("components", lambda v: normalize_str_tuple(v) or ()),
            "inno_tasks": ("tasks", lambda v: normalize_str_tuple(v) or ()),
        }
        for flat_k, (sub_k, conv_fn) in inno_flat_map.items():
            if flat_k in override:
                inno_dict[sub_k] = conv_fn(override[flat_k])
        rec["inno"] = inno_dict

        if isinstance(override.get("extra"), dict):
            merged_extra = dict(rec.get("extra") or {})
            merged_extra.update(override["extra"])
            rec["extra"] = merged_extra

        rec["prefix"] = prefix
        return rec

    @classmethod
    def _refresh_records_with_overrides(cls) -> None:
        if not cls._base_records:
            return
        cls.RECORDS = [
            cls._apply_override_to_record(base_rec, cls._app_overrides.get(base_rec["key"], {}))
            for base_rec in cls._base_records
        ]

    @classmethod
    def configure(
        cls,
        *,
        project_root: str | Path | None = None,
        json_path: str | Path | None = None,
        app_config_json: str | Path | None = None,
        cli_overrides: dict[str, Any] | None = None,
        code_overrides: dict[str, Any] | None = None,
        app_overrides: dict[str, dict[str, Any]] | None = None,
        cli_app_overrides: dict[str, dict[str, Any]] | None = None,
        reset: bool = False,
    ) -> BuildDirConfig:
        if reset:
            cls._dir_config = None
            cls._app_overrides = {}
            cls._refresh_records_with_overrides()
            return cls.get_dir_config(project_root=project_root)

        resolved_cfg = BuildDirConfig.resolve(
            project_root=project_root,
            json_path=json_path,
            cli_overrides=cli_overrides,
            code_overrides=code_overrides,
        )
        for field_name, label in (
            ("work_dir_name", "work 루트 폴더"),
            ("dist_dir_name", "dist 루트 폴더"),
            ("release_dir_name", "release 루트 폴더"),
            ("install_dir_name", "install 루트 폴더"),
        ):
            _validate_single_segment_name(getattr(resolved_cfg, field_name), label)

        cls._dir_config = resolved_cfg
        cls._app_overrides = resolve_app_overrides(
            project_root=project_root,
            json_path=json_path,
            app_config_json=app_config_json,
            code_app_overrides=app_overrides,
            cli_app_overrides=cli_app_overrides,
        )
        cls._refresh_records_with_overrides()
        return cls._dir_config

    @classmethod
    def get_app_overrides(cls) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in cls._app_overrides.items()}

    @classmethod
    def set_app_overrides(
        cls,
        overrides: dict[str, dict[str, Any]] | None,
        *,
        replace: bool = True,
    ) -> dict[str, dict[str, Any]]:
        if replace:
            cls._app_overrides = merge_app_override_dicts({}, overrides)
        else:
            cls._app_overrides = merge_app_override_dicts(cls._app_overrides, overrides)
        cls._refresh_records_with_overrides()
        return cls.get_app_overrides()

    @classmethod
    def save_config_json(
        cls,
        json_path: str | Path,
        *,
        dir_config: BuildDirConfig | None = None,
        app_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> Path:
        dcfg = dir_config or cls.get_dir_config(Path(json_path).parent)
        apps_data = cls.get_app_overrides() if app_overrides is None else app_overrides
        return write_build_config_json(json_path, dir_config=dcfg, app_overrides=apps_data)

    @classmethod
    def get_dir_config(cls, project_root: str | Path | None = None) -> BuildDirConfig:
        if cls._dir_config is not None:
            return cls._dir_config
        return BuildDirConfig.resolve(project_root=project_root)

    @classmethod
    def get_install_root_name(cls, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str:
        """install_dir_name이 기본값('Installer')이고 명시적 변경이 없으면 release_dir_name을 유지하고,
        별도 루트 폴더명이 지정된 경우 해당 루트 폴더명을 반환."""
        dcfg = cls.get_dir_config(project_root)
        inst_name = str(getattr(dcfg, "install_dir_name", "") or "").strip()
        if inst_name and inst_name != INSTALL_DIR_NAME:
            return _validate_single_segment_name(inst_name, "install 루트 폴더")
        return _validate_single_segment_name(dcfg.release_dir_name, "release 루트 폴더")

    @classmethod
    def _make_record(
        cls,
        order: str,
        name: str,
        *,
        prefix: str = PREFIX,
        label: str | None = None,
        exe_name: str | None = None,
        spec_hints: tuple[str, ...] | None = None,
        dir_hints: tuple[str, ...] | None = None,
        entry_file: str = DEFAULT_ENTRY_FILENAME,
        entry_hints: tuple[str, ...] | None = None,
        version_file: str = DEFAULT_VERSION_FILENAME,
        version_rel_paths: tuple[str, ...] | None = None,
        console: bool = DEFAULT_CONSOLE,
        copy_to_test: bool = DEFAULT_COPY_TO_TEST,
        run_test: bool = DEFAULT_RUN_TEST,
        copy_to_archive: bool = DEFAULT_COPY_TO_ARCHIVE,
        include_in_installer: bool = DEFAULT_INCLUDE_IN_INSTALLER,
        standalone_installer: bool = DEFAULT_STANDALONE_INSTALLER,
        is_installer: bool = DEFAULT_IS_INSTALLER,
        hidden_imports: tuple[str, ...] = (),
        extra_pathex: tuple[str, ...] = (),
        pyinstaller: dict[str, Any] | PyInstallerSpec | None = None,
        inno: dict[str, Any] | InnoSetupSpec | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict:
        is_main_app_exception = str(order) == MAIN_APP_ORDER and name == MAIN_APP_RAW_NAME
        resolved_name = MAIN_APP_OVERRIDE_NAME if is_main_app_exception else name
        resolved_key = MAIN_APP_OVERRIDE_NAME if is_main_app_exception else name
        resolved_label = (
            label.strip()
            if isinstance(label, str) and label.strip()
            else (MAIN_APP_OVERRIDE_NAME if is_main_app_exception else f"{prefix}{name}")
        )
        _validate_single_segment_name(resolved_label, "폴더 라벨")
        resolved_dirs = dir_hints or (
            (MAIN_APP_OVERRIDE_NAME, MAIN_APP_RAW_NAME) if is_main_app_exception else (name,)
        )
        primary_dir = resolved_dirs[0]

        py_raw = (
            {
                "onefile": pyinstaller.onefile,
                "uac_admin": pyinstaller.uac_admin,
                "icon_path": pyinstaller.icon_path,
                "hidden_imports": pyinstaller.hidden_imports,
                "excludes": pyinstaller.excludes,
                "datas": pyinstaller.datas,
                "binaries": pyinstaller.binaries,
                "extra_pathex": pyinstaller.extra_pathex,
            }
            if isinstance(pyinstaller, PyInstallerSpec)
            else (pyinstaller or {})
        )
        inno_raw = (
            {
                "install_subdir": inno.install_subdir,
                "excludes": inno.excludes,
                "flags": inno.flags,
                "components": inno.components,
                "tasks": inno.tasks,
                "extra_defines": inno.extra_defines,
            }
            if isinstance(inno, InnoSetupSpec)
            else (inno or {})
        )

        return {
            "order": order,
            "key": resolved_key,
            "name": resolved_name,
            "prefix": prefix,
            "label": resolved_label,
            "exe_name": exe_name or f"{resolved_label}{EXE_EXTENSION}",
            "spec_hints": spec_hints or (f"{resolved_label}{SPEC_EXTENSION}",),
            "dir_hints": resolved_dirs,
            "entry_hints": entry_hints or (f"{SRC_DIR_NAME}/{primary_dir}/{entry_file}",),
            "console": bool(console),
            "version_rel_paths": version_rel_paths or (f"{SRC_DIR_NAME}/{primary_dir}/{version_file}",),
            "copy_to_test": bool(copy_to_test),
            "run_test": bool(run_test),
            "copy_to_archive": bool(copy_to_archive),
            "include_in_installer": bool(include_in_installer),
            "standalone_installer": bool(standalone_installer),
            "is_installer": bool(is_installer),
            "hidden_imports": tuple(hidden_imports),
            "extra_pathex": tuple(extra_pathex),
            "pyinstaller": cls._build_pyinstaller_dict(py_raw),
            "inno": cls._build_inno_dict(inno_raw),
            "extra": dict(extra) if isinstance(extra, dict) else {},
        }

    @classmethod
    def set_base_records(cls, records: list[dict]) -> None:
        cls._base_records = [dict(r) for r in records]
        cls._refresh_records_with_overrides()

    @classmethod
    def _record_to_spec(cls, record: dict) -> AppTargetSpec:
        py_d = cls._build_pyinstaller_dict(record.get("pyinstaller"))
        inno_d = cls._build_inno_dict(record.get("inno"))
        return AppTargetSpec(
            order=record["order"],
            key=record["key"],
            name=record["name"],
            label=record["label"],
            exe_name=record["exe_name"],
            spec_hints=record["spec_hints"],
            dir_hints=record["dir_hints"],
            entry_hints=record.get("entry_hints", ()),
            console=bool(record.get("console", DEFAULT_CONSOLE)),
            version_rel_paths=record.get("version_rel_paths", ()),
            copy_to_test=bool(record.get("copy_to_test", DEFAULT_COPY_TO_TEST)),
            run_test=bool(record.get("run_test", DEFAULT_RUN_TEST)),
            copy_to_archive=bool(record.get("copy_to_archive", DEFAULT_COPY_TO_ARCHIVE)),
            include_in_installer=bool(record.get("include_in_installer", DEFAULT_INCLUDE_IN_INSTALLER)),
            standalone_installer=bool(record.get("standalone_installer", DEFAULT_STANDALONE_INSTALLER)),
            is_installer=bool(record.get("is_installer", DEFAULT_IS_INSTALLER)),
            hidden_imports=tuple(record.get("hidden_imports", ())),
            extra_pathex=tuple(record.get("extra_pathex", ())),
            pyinstaller=PyInstallerSpec(**py_d),
            inno=InnoSetupSpec(**inno_d),
            extra=dict(record.get("extra") or {}),
        )

    @classmethod
    def _build_target_class(cls, record: dict) -> type[AppTargetSpec]:
        class_name = f"{record['name']}Target"

        def __init__(self) -> None:
            spec = cls._record_to_spec(record)
            AppTargetSpec.__init__(
                self,
                order=spec.order,
                key=spec.key,
                name=spec.name,
                label=spec.label,
                exe_name=spec.exe_name,
                spec_hints=spec.spec_hints,
                dir_hints=spec.dir_hints,
                entry_hints=spec.entry_hints,
                console=spec.console,
                version_rel_paths=spec.version_rel_paths,
                copy_to_test=spec.copy_to_test,
                run_test=spec.run_test,
                copy_to_archive=spec.copy_to_archive,
                include_in_installer=spec.include_in_installer,
                standalone_installer=spec.standalone_installer,
                is_installer=spec.is_installer,
                hidden_imports=spec.hidden_imports,
                extra_pathex=spec.extra_pathex,
                pyinstaller=spec.pyinstaller,
                inno=spec.inno,
                extra=spec.extra,
            )

        return type(class_name, (AppTargetSpec,), {"__init__": __init__})

    @classmethod
    def _rebuild_target_mappings(cls, records: list[dict] | None = None) -> None:
        recs = list(records if records is not None else cls.RECORDS)
        target_classes = tuple(cls._build_target_class(rec) for rec in recs)
        specs = tuple(cls._record_to_spec(rec) for rec in recs)
        by_key = {spec.key: spec for spec in specs}
        by_order = {spec.order: spec for spec in specs}
        all_targets = {spec.order: spec.key for spec in specs}
        labels = {spec.key: spec.label for spec in specs}

        all_targets_cls = getattr(cls, "ALL_TARGETS", None)
        if isinstance(all_targets_cls, dict):
            all_targets_cls.clear()
            all_targets_cls.update(all_targets)
        else:
            all_targets_cls = dict(all_targets)

        labels_cls = getattr(cls, "LABELS", None)
        if isinstance(labels_cls, dict):
            labels_cls.clear()
            labels_cls.update(labels)
        else:
            labels_cls = dict(labels)

        type.__setattr__(cls, "TARGET_CLASSES", target_classes)
        type.__setattr__(cls, "TARGET_SPECS", specs)
        type.__setattr__(cls, "SPECS", specs)
        type.__setattr__(cls, "BY_KEY", by_key)
        type.__setattr__(cls, "BY_ORDER", by_order)
        type.__setattr__(cls, "ALL_TARGETS", all_targets_cls)
        type.__setattr__(cls, "LABELS", labels_cls)
        type.__setattr__(cls, "TARGET_LABELS", labels_cls)

    @classmethod
    def app_keys(cls) -> list[str]:
        """인스톨러 전용 대상을 제외한 일반 앱 target key 목록."""
        return [
            spec.key
            for spec in sorted(cls.SPECS, key=lambda s: _order_sort_key(s.order))
            if not spec.is_installer
        ]

    @classmethod
    def ordered_keys(cls, *, include_installer: bool = False) -> list[str]:
        if include_installer:
            return [cls.ALL_TARGETS[k] for k in sorted(cls.ALL_TARGETS.keys(), key=_order_sort_key)]
        return cls.app_keys()

    @classmethod
    def parse_targets(cls, raw_targets: list[str] | str | None) -> list[str]:
        if not raw_targets:
            return cls.ordered_keys(include_installer=False)

        tokens: list[str] = []
        if isinstance(raw_targets, str):
            for item in raw_targets.split(","):
                t = item.strip()
                if t:
                    tokens.append(t)
        else:
            for item in raw_targets:
                for part in str(item).split(","):
                    t = part.strip()
                    if t:
                        tokens.append(t)

        reverse_map = {v.lower(): v for v in cls.ALL_TARGETS.values()}

        resolved: list[str] = []
        for tok in tokens:
            low = tok.lower()
            if tok in cls.ALL_TARGETS:
                mapped = cls.ALL_TARGETS[tok]
            elif low in reverse_map:
                mapped = reverse_map[low]
            elif low in LEGACY_TARGET_ALIASES and LEGACY_TARGET_ALIASES[low] in cls.BY_KEY:
                mapped = LEGACY_TARGET_ALIASES[low]
            else:
                raise ValueError(
                    f"알 수 없는 빌드 대상입니다: '{tok}' "
                    f"(허용: {list(cls.ALL_TARGETS.keys())} 또는 {list(cls.ALL_TARGETS.values())})"
                )
            if mapped not in resolved:
                resolved.append(mapped)
        return resolved

    @classmethod
    def get_spec(cls, target_key: str) -> AppTargetSpec | None:
        return cls.BY_KEY.get(target_key)

    @classmethod
    def get_label(cls, target_key: str) -> str:
        return cls.LABELS.get(target_key, target_key)

    @classmethod
    def get_folder_name(cls, target_key: str) -> str:
        spec = cls.get_spec(target_key)
        folder = spec.label if spec else cls.get_label(target_key)
        return _validate_single_segment_name(folder, "폴더")

    @classmethod
    def _resolve_root_folder_path(
        cls,
        project_root: str | Path,
        root_folder_name: str,
    ) -> Path:
        root = Path(project_root).resolve()
        safe_root_folder = _validate_single_segment_name(root_folder_name, "루트 폴더")
        resolved = (root / safe_root_folder).resolve()
        if resolved.parent != root:
            raise ValueError(
                f"루트 폴더가 project_root 직하위가 아닙니다: {resolved} (project_root={root})"
            )
        return resolved

    @classmethod
    def _resolve_app_folder_path(
        cls,
        project_root: str | Path,
        root_folder_name: str,
        target_key: str,
        *,
        create: bool = False,
    ) -> str:
        root = Path(project_root).resolve()
        root_dir = cls._resolve_root_folder_path(root, root_folder_name)
        app_folder = cls.get_folder_name(target_key)
        app_dir = (root_dir / app_folder).resolve()
        if app_dir.parent != root_dir or app_dir.parent.parent != root:
            raise ValueError(
                f"산출물 경로는 <project_root>/<루트폴더>/<대상폴더> 구조여야 합니다: {app_dir}"
            )
        if create:
            app_dir.mkdir(parents=True, exist_ok=True)
        return str(app_dir)

    @classmethod
    def validate_app_artifact_layout(
        cls,
        project_root: str | Path,
        root_folder_name: str,
        target_key: str,
        candidate_path: str | Path,
    ) -> Path:
        expected_app_dir = Path(
            cls._resolve_app_folder_path(project_root, root_folder_name, target_key, create=False)
        ).resolve()
        actual = Path(candidate_path).resolve()
        if actual != expected_app_dir and expected_app_dir not in actual.parents:
            raise ValueError(
                f"산출물 경로 불일치: expected={expected_app_dir}, actual={actual}"
            )
        return actual

    @classmethod
    def get_managed_root_names(
        cls,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        include_test: bool = True,
    ) -> tuple[str, ...]:
        dcfg = cls.get_dir_config(project_root)
        names = [
            _validate_single_segment_name(dcfg.work_dir_name, "work 루트 폴더"),
            _validate_single_segment_name(dcfg.dist_dir_name, "dist 루트 폴더"),
            _validate_single_segment_name(dcfg.release_dir_name, "release 루트 폴더"),
            cls.get_install_root_name(project_root),
        ]
        if include_test:
            names.append(_validate_single_segment_name(cls.TEST_DIR_NAME, "test 루트 폴더"))
        deduped: list[str] = []
        for n in names:
            if n not in deduped:
                deduped.append(n)
        return tuple(deduped)

    @classmethod
    def clean_output_dirs(
        cls,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        include_test: bool = True,
    ) -> list[str]:
        removed: list[str] = []
        for folder_name in cls.get_managed_root_names(project_root, include_test=include_test):
            target_dir = cls._resolve_root_folder_path(project_root, folder_name)
            if target_dir.is_dir():
                shutil.rmtree(target_dir, ignore_errors=True)
                removed.append(str(target_dir))
        return removed

    @classmethod
    def get_work_root(cls, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str:
        return str(cls._resolve_root_folder_path(project_root, cls.get_dir_config(project_root).work_dir_name))

    @classmethod
    def get_dist_root(cls, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str:
        return str(cls._resolve_root_folder_path(project_root, cls.get_dir_config(project_root).dist_dir_name))

    @classmethod
    def get_release_root(cls, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str:
        return str(cls._resolve_root_folder_path(project_root, cls.get_dir_config(project_root).release_dir_name))

    @classmethod
    def get_install_root(cls, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str:
        """인스톨러 저장 루트 경로 반환 (install_dir_name 오버라이드 반영)."""
        return str(cls._resolve_root_folder_path(project_root, cls.get_install_root_name(project_root)))

    @classmethod
    def get_test_root(cls, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str:
        return str(cls._resolve_root_folder_path(project_root, cls.TEST_DIR_NAME))

    @classmethod
    def get_work_dir(
        cls,
        target_key: str,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        create: bool = False,
    ) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.get_dir_config(project_root).work_dir_name,
            target_key,
            create=create,
        )

    @classmethod
    def get_dist_dir(
        cls,
        target_key: str,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        create: bool = False,
    ) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.get_dir_config(project_root).dist_dir_name,
            target_key,
            create=create,
        )

    @classmethod
    def get_release_dir(
        cls,
        target_key: str,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        create: bool = False,
    ) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.get_dir_config(project_root).release_dir_name,
            target_key,
            create=create,
        )

    @classmethod
    def get_install_dir(
        cls,
        target_key: str = INSTALLER_TARGET_KEY,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        create: bool = False,
    ) -> str:
        """인스톨러 루트 아래 레코드 폴더명으로 경로를 반환."""
        key = target_key if target_key in cls.BY_KEY else INSTALLER_TARGET_KEY
        return cls._resolve_app_folder_path(
            project_root,
            cls.get_install_root_name(project_root),
            key,
            create=create,
        )

    @classmethod
    def get_installer_dist_dir(
        cls,
        target_key: str = INSTALLER_TARGET_KEY,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        create: bool = False,
    ) -> str:
        """dist 루트 아래 인스톨러 폴더 경로를 반환."""
        key = target_key if target_key in cls.BY_KEY else INSTALLER_TARGET_KEY
        return cls.get_dist_dir(key, project_root, create=create)

    @classmethod
    def get_test_dir(
        cls,
        target_key: str,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        create: bool = False,
    ) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.TEST_DIR_NAME,
            target_key,
            create=create,
        )

    @classmethod
    def get_app_dirs(
        cls,
        target_key: str,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        *,
        create: bool = False,
    ) -> dict[str, str]:
        return {
            "work_dir": cls.get_work_dir(target_key, project_root, create=create),
            "dist_dir": cls.get_dist_dir(target_key, project_root, create=create),
            "release_dir": cls.get_release_dir(target_key, project_root, create=create),
            "install_dir": cls.get_install_dir(target_key, project_root, create=create),
            "test_dir": cls.get_test_dir(target_key, project_root, create=create),
        }

    @classmethod
    def ensure_all_app_dirs(
        cls,
        project_root: str | Path = PathMgr.PROJECT_ROOT,
        targets: list[str] | None = None,
    ) -> dict[str, dict[str, str]]:
        target_keys = targets or cls.ordered_keys(include_installer=True)
        return {key: cls.get_app_dirs(key, project_root, create=True) for key in target_keys}

    @classmethod
    def get_all_version_rel_paths(cls) -> list[str]:
        paths: list[str] = []
        for spec in cls.SPECS:
            for rel in spec.version_rel_paths:
                if rel not in paths:
                    paths.append(rel)
        return paths

    @classmethod
    def get_version_files(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT) -> list[str]:
        spec = cls.get_spec(target_key)
        if not spec:
            return []
        root = Path(project_root)
        paths: list[str] = []
        for rel in spec.version_rel_paths:
            full_p = str(root / Path(*rel.split("/")))
            if full_p not in paths:
                paths.append(full_p)
        return paths

    @classmethod
    def get_version_fullpath(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str | None:
        spec = cls.get_spec(target_key)
        root = Path(project_root)

        if spec and spec.version_rel_paths:
            return str(root / Path(*spec.version_rel_paths[0].split("/")))

        for attr in ("version_path", "version_file", "version_rel_path"):
            val = getattr(spec, attr, None) if spec else None
            if val:
                p = Path(val)
                return str(p if p.is_absolute() else root / p)

        if spec:
            for rel in cls.get_all_version_rel_paths():
                norm_rel = rel.replace("\\", "/").lower()
                if any(sd.lower() in norm_rel for sd in spec.dir_hints):
                    return str(root / Path(*rel.split("/")))

            for sd in spec.dir_hints:
                candidate = root / SRC_DIR_NAME / sd / DEFAULT_VERSION_FILENAME
                if candidate.is_file():
                    return str(candidate)

        return None

    @classmethod
    def get_version_dir(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str | None:
        full_path = cls.get_version_fullpath(target_key, project_root=project_root)
        if full_path:
            return os.path.dirname(full_path)

        spec = cls.get_spec(target_key)
        root = Path(project_root)
        if spec:
            for sd in spec.dir_hints:
                candidate_dir = root / SRC_DIR_NAME / sd
                if candidate_dir.is_dir():
                    return str(candidate_dir)

        return None


TARGET_CLASSES: tuple[type[AppTargetSpec], ...] = TargetConfig.TARGET_CLASSES
TARGET_SPECS: tuple[AppTargetSpec, ...] = TargetConfig.TARGET_SPECS
ALL_TARGETS: dict[str, str] = TargetConfig.ALL_TARGETS
LABELS: dict[str, str] = TargetConfig.LABELS
TARGET_LABELS: dict[str, str] = TargetConfig.TARGET_LABELS


def inject_target_records(
    records: list[dict[str, Any]],
    *,
    dir_config: BuildDirConfig | None = None,
    app_overrides: dict[str, dict[str, Any]] | None = None,
) -> type[TargetConfig]:
    """외부에서 정의한 레코드 목록을 TargetConfig 클래스 변수에 주입."""
    global TARGET_CLASSES, TARGET_SPECS, ALL_TARGETS, LABELS, TARGET_LABELS

    if dir_config is not None:
        TargetConfig._dir_config = dir_config
    if app_overrides is not None:
        TargetConfig.set_app_overrides(app_overrides, replace=True)
    TargetConfig.set_base_records(records)

    TARGET_CLASSES = TargetConfig.TARGET_CLASSES
    TARGET_SPECS = TargetConfig.TARGET_SPECS
    ALL_TARGETS = TargetConfig.ALL_TARGETS
    LABELS = TargetConfig.LABELS
    TARGET_LABELS = TargetConfig.TARGET_LABELS
    return TargetConfig


def get_target_spec(target_key: str) -> AppTargetSpec | None:
    return TargetConfig.get_spec(target_key)


def get_build_target_helpers(project_root: str | Path = PathMgr.PROJECT_ROOT) -> dict[str, Any]:
    root = Path(project_root)
    return {
        "prefix": TargetConfig.PREFIX,
        "work_dir_name": TargetConfig.get_dir_config(root).work_dir_name,
        "dist_dir_name": TargetConfig.get_dir_config(root).dist_dir_name,
        "release_dir_name": TargetConfig.get_dir_config(root).release_dir_name,
        "install_dir_name": TargetConfig.get_install_root_name(root),
        "test_dir_name": TargetConfig.TEST_DIR_NAME,
        "app_overrides": TargetConfig.get_app_overrides(),
        "get_work_root": lambda: TargetConfig.get_work_root(root),
        "get_dist_root": lambda: TargetConfig.get_dist_root(root),
        "get_release_root": lambda: TargetConfig.get_release_root(root),
        "get_install_root": lambda: TargetConfig.get_install_root(root),
        "get_test_root": lambda: TargetConfig.get_test_root(root),
        "get_work_dir": lambda k, create=False: TargetConfig.get_work_dir(k, root, create=create),
        "get_dist_dir": lambda k, create=False: TargetConfig.get_dist_dir(k, root, create=create),
        "get_release_dir": lambda k, create=False: TargetConfig.get_release_dir(k, root, create=create),
        "get_install_dir": lambda k=INSTALLER_TARGET_KEY, create=False: TargetConfig.get_install_dir(
            k, root, create=create
        ),
        "get_installer_dist_dir": lambda k=INSTALLER_TARGET_KEY, create=False: TargetConfig.get_installer_dist_dir(
            k, root, create=create
        ),
        "get_test_dir": lambda k, create=False: TargetConfig.get_test_dir(k, root, create=create),
        "get_app_dirs": lambda k, create=False: TargetConfig.get_app_dirs(k, root, create=create),
        "get_version_files": lambda k: TargetConfig.get_version_files(k, root),
        "get_version_fullpath": lambda k: TargetConfig.get_version_fullpath(k, root),
        "get_version_dir": lambda k: TargetConfig.get_version_dir(k, root),
    }