"""
앱별 빌드 대상 상수 및 스펙 정의 모듈 (build_targets.py)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from Common.path_mgr import PathMgr
from target_config_io import (
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
MAIN_APP_OVERRIDE_NAME: str = "PrintShopApp"
TEST_DIR_NAME: str = "test"

# 빌드 및 배포 정책 기본값 상수
DEFAULT_CONSOLE: bool = True
DEFAULT_COPY_TO_TEST: bool = True
DEFAULT_COPY_TO_ARCHIVE: bool = True
DEFAULT_INCLUDE_IN_INSTALLER: bool = True
DEFAULT_STANDALONE_INSTALLER: bool = False

__all__ = [
    "ALL_TARGETS",
    "APP_OVERRIDE_FIELDS",
    "AppTargetSpec",
    "BuildDirConfig",
    "BuildTargets",
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_CONSOLE",
    "DEFAULT_COPY_TO_ARCHIVE",
    "DEFAULT_COPY_TO_TEST",
    "DEFAULT_INCLUDE_IN_INSTALLER",
    "DEFAULT_STANDALONE_INSTALLER",
    "DIST_DIR_NAME",
    "ENV_APP_OVERRIDES_KEY",
    "ENV_DIR_KEYS",
    "INSTALL_DIR_NAME",
    "LABELS",
    "MAIN_APP_OVERRIDE_NAME",
    "PREFIX",
    "RELEASE_DIR_NAME",
    "TARGET_CLASSES",
    "TARGET_LABELS",
    "TARGET_SPECS",
    "TEST_DIR_NAME",
    "WORK_DIR_NAME",
    "get_build_target_helpers",
    "get_target_spec",
    "parse_cli_app_override_tokens",
]


def _validate_single_segment_name(name: str, kind: str) -> str:
    """루트 폴더명 및 앱 폴더명이 단일 디렉터리 세그먼트인지 검증."""
    cleaned = str(name or "").strip()
    if not cleaned or cleaned in (".", ".."):
        raise ValueError(f"유효하지 않은 {kind} 이름입니다: '{name}'")
    if "/" in cleaned or "\\" in cleaned or Path(cleaned).is_absolute():
        raise ValueError(f"{kind} 이름에는 경로 구분자나 절대경로를 사용할 수 없습니다: '{name}'")
    return cleaned


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
    copy_to_archive: bool = DEFAULT_COPY_TO_ARCHIVE
    include_in_installer: bool = DEFAULT_INCLUDE_IN_INSTALLER
    standalone_installer: bool = DEFAULT_STANDALONE_INSTALLER


class _BuildTargetsMeta(type):
    """RECORDS 변경 시 파생 맵(ALL_TARGETS, LABELS, SPECS 등)을 자동 갱신하는 메타클래스."""

    def __setattr__(cls, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name == "RECORDS":
            cls._rebuild_target_mappings(value)


class BuildTargets(metaclass=_BuildTargetsMeta):
    """앱별 빌드 대상 레코드 및 조회/경로 헬퍼를 제공하는 클래스."""

    PREFIX: str = PREFIX
    TEST_DIR_NAME: str = TEST_DIR_NAME
    _dir_config: BuildDirConfig | None = None
    _base_records: list[dict] = []
    _app_overrides: dict[str, dict[str, Any]] = {}
    RECORDS: list[dict] = []
    TARGET_CLASSES: tuple[type[AppTargetSpec], ...] = ()
    SPECS: tuple[AppTargetSpec, ...] = ()
    BY_KEY: dict[str, AppTargetSpec] = {}
    BY_ORDER: dict[str, AppTargetSpec] = {}
    ALL_TARGETS: dict[str, str] = {}
    LABELS: dict[str, str] = {}

    @classmethod
    def _apply_override_to_record(cls, base_rec: dict, override: dict[str, Any]) -> dict:
        rec = dict(base_rec)
        prefix = rec.get("prefix", cls.PREFIX)

        if "label" in override and isinstance(override["label"], str) and override["label"].strip():
            rec["label"] = _validate_single_segment_name(override["label"].strip(), "앱 라벨")

        resolved_label = rec["label"]

        if "dir_hints" in override:
            dh = normalize_str_tuple(override["dir_hints"])
            if dh:
                rec["dir_hints"] = dh

        primary_dir = rec["dir_hints"][0] if rec.get("dir_hints") else rec["name"]

        if "exe_name" in override and isinstance(override["exe_name"], str) and override["exe_name"].strip():
            rec["exe_name"] = override["exe_name"].strip()
        elif "label" in override:
            rec["exe_name"] = f"{resolved_label}.exe"

        if "spec_hints" in override:
            sh = normalize_str_tuple(override["spec_hints"])
            if sh:
                rec["spec_hints"] = sh
        elif "label" in override:
            rec["spec_hints"] = (f"{resolved_label}.spec",)

        if "entry_hints" in override:
            eh = normalize_str_tuple(override["entry_hints"])
            if eh:
                rec["entry_hints"] = eh
        elif "entry_file" in override and isinstance(override["entry_file"], str) and override["entry_file"].strip():
            entry_fn = override["entry_file"].strip().lstrip("/\\")
            if entry_fn.startswith("src/"):
                rec["entry_hints"] = (entry_fn,)
            else:
                rec["entry_hints"] = (f"src/{primary_dir}/{entry_fn}",)

        if "version_rel_paths" in override:
            vr = normalize_str_tuple(override["version_rel_paths"])
            if vr:
                rec["version_rel_paths"] = vr
        elif "version_file" in override and isinstance(override["version_file"], str) and override["version_file"].strip():
            ver_fn = override["version_file"].strip().lstrip("/\\")
            if ver_fn.startswith("src/"):
                rec["version_rel_paths"] = (ver_fn,)
            else:
                rec["version_rel_paths"] = (f"src/{primary_dir}/{ver_fn}",)

        if "console" in override and isinstance(override["console"], bool):
            rec["console"] = override["console"]

        for flag_key in (
            "copy_to_test",
            "copy_to_archive",
            "include_in_installer",
            "standalone_installer",
        ):
            if flag_key in override and isinstance(override[flag_key], bool):
                rec[flag_key] = override[flag_key]

        rec["prefix"] = prefix
        return rec

    @classmethod
    def _refresh_records_with_overrides(cls) -> None:
        if not cls._base_records:
            return
        merged_recs = [
            cls._apply_override_to_record(base_rec, cls._app_overrides.get(base_rec["key"], {}))
            for base_rec in cls._base_records
        ]
        cls.RECORDS = merged_recs

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

    @staticmethod
    def _make_record(
        order: str,
        name: str,
        *,
        prefix: str = PREFIX,
        label: str | None = None,
        exe_name: str | None = None,
        spec_hints: tuple[str, ...] | None = None,
        dir_hints: tuple[str, ...] | None = None,
        entry_file: str = "main_app.py",
        entry_hints: tuple[str, ...] | None = None,
        version_file: str = "version.txt",
        version_rel_paths: tuple[str, ...] | None = None,
        console: bool = DEFAULT_CONSOLE,
        copy_to_test: bool = DEFAULT_COPY_TO_TEST,
        copy_to_archive: bool = DEFAULT_COPY_TO_ARCHIVE,
        include_in_installer: bool = DEFAULT_INCLUDE_IN_INSTALLER,
        standalone_installer: bool = DEFAULT_STANDALONE_INSTALLER,
    ) -> dict:
        is_main_app_exception = str(order) == "1" and name == "App"
        resolved_name = MAIN_APP_OVERRIDE_NAME if is_main_app_exception else name
        resolved_key = MAIN_APP_OVERRIDE_NAME if is_main_app_exception else name
        resolved_label = label or (MAIN_APP_OVERRIDE_NAME if is_main_app_exception else f"{prefix}{name}")
        _validate_single_segment_name(resolved_label, "앱 폴더 라벨")
        resolved_dirs = dir_hints or ((MAIN_APP_OVERRIDE_NAME, "App") if is_main_app_exception else (name,))
        primary_dir = resolved_dirs[0]

        return {
            "order": order,
            "key": resolved_key,
            "name": resolved_name,
            "prefix": prefix,
            "label": resolved_label,
            "exe_name": exe_name or f"{resolved_label}.exe",
            "spec_hints": spec_hints or (f"{resolved_label}.spec",),
            "dir_hints": resolved_dirs,
            "entry_hints": entry_hints or (f"src/{primary_dir}/{entry_file}",),
            "console": bool(console),
            "version_rel_paths": version_rel_paths or (f"src/{primary_dir}/{version_file}",),
            "copy_to_test": bool(copy_to_test),
            "copy_to_archive": bool(copy_to_archive),
            "include_in_installer": bool(include_in_installer),
            "standalone_installer": bool(standalone_installer),
        }

    @classmethod
    def set_base_records(cls, records: list[dict]) -> None:
        cls._base_records = [dict(r) for r in records]
        cls._refresh_records_with_overrides()

    @classmethod
    def _record_to_spec(cls, record: dict) -> AppTargetSpec:
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
            copy_to_archive=bool(record.get("copy_to_archive", DEFAULT_COPY_TO_ARCHIVE)),
            include_in_installer=bool(record.get("include_in_installer", DEFAULT_INCLUDE_IN_INSTALLER)),
            standalone_installer=bool(record.get("standalone_installer", DEFAULT_STANDALONE_INSTALLER)),
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
                copy_to_archive=spec.copy_to_archive,
                include_in_installer=spec.include_in_installer,
                standalone_installer=spec.standalone_installer,
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

        type.__setattr__(cls, "TARGET_CLASSES", target_classes)
        type.__setattr__(cls, "SPECS", specs)
        type.__setattr__(cls, "BY_KEY", by_key)
        type.__setattr__(cls, "BY_ORDER", by_order)
        type.__setattr__(cls, "ALL_TARGETS", all_targets)
        type.__setattr__(cls, "LABELS", labels)

        mod = globals()
        if "TARGET_CLASSES" in mod:
            mod["TARGET_CLASSES"] = target_classes
        if "TARGET_SPECS" in mod:
            mod["TARGET_SPECS"] = specs
        if "ALL_TARGETS" in mod and isinstance(mod["ALL_TARGETS"], dict):
            mod["ALL_TARGETS"].clear()
            mod["ALL_TARGETS"].update(all_targets)
        if "LABELS" in mod and isinstance(mod["LABELS"], dict):
            mod["LABELS"].clear()
            mod["LABELS"].update(labels)
        if "TARGET_LABELS" in mod and isinstance(mod["TARGET_LABELS"], dict):
            mod["TARGET_LABELS"].clear()
            mod["TARGET_LABELS"].update(labels)

    @classmethod
    def ordered_keys(cls) -> list[str]:
        return [cls.ALL_TARGETS[k] for k in sorted(cls.ALL_TARGETS.keys(), key=int)]

    @classmethod
    def parse_targets(cls, raw_targets: list[str] | str | None) -> list[str]:
        if not raw_targets:
            return cls.ordered_keys()

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

        legacy_alias = {
            "app": MAIN_APP_OVERRIDE_NAME,
            "main_app": MAIN_APP_OVERRIDE_NAME,
            "update_service": "UpdateService",
            "update_manager": "UpdateManager",
            "version_viewer": "VersionViewer",
            "build_manager_app": "BuildManagerApp",
        }
        reverse_map = {v.lower(): v for v in cls.ALL_TARGETS.values()}

        resolved: list[str] = []
        for tok in tokens:
            low = tok.lower()
            if tok in cls.ALL_TARGETS:
                mapped = cls.ALL_TARGETS[tok]
            elif low in reverse_map:
                mapped = reverse_map[low]
            elif low in legacy_alias and legacy_alias[low] in cls.BY_KEY:
                mapped = legacy_alias[low]
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
        return _validate_single_segment_name(folder, "앱 폴더")

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
                f"산출물 경로는 <project_root>/<루트폴더>/<앱폴더> 구조여야 합니다: {app_dir}"
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
        """candidate_path가 <project_root>/<루트폴더>/<앱폴더> 또는 그 하위 경로인지 검증."""
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
            _validate_single_segment_name(dcfg.install_dir_name, "install 루트 폴더"),
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
        """<project_root>/<루트폴더> 산출물 디렉터리를 일관된 규칙으로 정리."""
        import shutil

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
        return str(cls._resolve_root_folder_path(project_root, cls.get_dir_config(project_root).install_dir_name))

    @classmethod
    def get_test_root(cls, project_root: str | Path = PathMgr.PROJECT_ROOT) -> str:
        return str(cls._resolve_root_folder_path(project_root, cls.TEST_DIR_NAME))

    @classmethod
    def get_work_dir(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT, *, create: bool = False) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.get_dir_config(project_root).work_dir_name,
            target_key,
            create=create,
        )

    @classmethod
    def get_dist_dir(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT, *, create: bool = False) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.get_dir_config(project_root).dist_dir_name,
            target_key,
            create=create,
        )

    @classmethod
    def get_release_dir(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT, *, create: bool = False) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.get_dir_config(project_root).release_dir_name,
            target_key,
            create=create,
        )

    @classmethod
    def get_install_dir(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT, *, create: bool = False) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.get_dir_config(project_root).install_dir_name,
            target_key,
            create=create,
        )

    @classmethod
    def get_test_dir(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT, *, create: bool = False) -> str:
        return cls._resolve_app_folder_path(
            project_root,
            cls.TEST_DIR_NAME,
            target_key,
            create=create,
        )

    @classmethod
    def get_app_dirs(cls, target_key: str, project_root: str | Path = PathMgr.PROJECT_ROOT, *, create: bool = False) -> dict[str, str]:
        return {
            "work_dir": cls.get_work_dir(target_key, project_root, create=create),
            "dist_dir": cls.get_dist_dir(target_key, project_root, create=create),
            "release_dir": cls.get_release_dir(target_key, project_root, create=create),
            "install_dir": cls.get_install_dir(target_key, project_root, create=create),
            "test_dir": cls.get_test_dir(target_key, project_root, create=create),
        }

    @classmethod
    def ensure_all_app_dirs(cls, project_root: str | Path = PathMgr.PROJECT_ROOT, targets: list[str] | None = None) -> dict[str, dict[str, str]]:
        target_keys = targets or cls.ordered_keys()
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
                candidate = root / "src" / sd / "version.txt"
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
                candidate_dir = root / "src" / sd
                if candidate_dir.is_dir():
                    return str(candidate_dir)

        return None


TARGET_CLASSES: tuple[type[AppTargetSpec], ...] = ()
TARGET_SPECS: tuple[AppTargetSpec, ...] = ()
ALL_TARGETS: dict[str, str] = {}
LABELS: dict[str, str] = {}
TARGET_LABELS: dict[str, str] = LABELS

BuildTargets.set_base_records(
    [
        BuildTargets._make_record("1", "App", dir_hints=("PrintShopApp", "App")),
        BuildTargets._make_record("2", "UpdateService"),
        BuildTargets._make_record("3", "UpdateManager"),
        BuildTargets._make_record("4", "VersionViewer"),
        BuildTargets._make_record("5", "BuildManagerApp"),
    ]
)


def get_target_spec(target_key: str) -> AppTargetSpec | None:
    return BuildTargets.get_spec(target_key)


def get_build_target_helpers(project_root: str | Path = PathMgr.PROJECT_ROOT) -> dict[str, Any]:
    root = Path(project_root)
    return {
        "prefix": BuildTargets.PREFIX,
        "work_dir_name": BuildTargets.get_dir_config(root).work_dir_name,
        "dist_dir_name": BuildTargets.get_dir_config(root).dist_dir_name,
        "release_dir_name": BuildTargets.get_dir_config(root).release_dir_name,
        "install_dir_name": BuildTargets.get_dir_config(root).install_dir_name,
        "test_dir_name": BuildTargets.TEST_DIR_NAME,
        "app_overrides": BuildTargets.get_app_overrides(),
        "get_work_root": lambda: BuildTargets.get_work_root(root),
        "get_dist_root": lambda: BuildTargets.get_dist_root(root),
        "get_release_root": lambda: BuildTargets.get_release_root(root),
        "get_install_root": lambda: BuildTargets.get_install_root(root),
        "get_test_root": lambda: BuildTargets.get_test_root(root),
        "get_work_dir": lambda k, create=False: BuildTargets.get_work_dir(k, root, create=create),
        "get_dist_dir": lambda k, create=False: BuildTargets.get_dist_dir(k, root, create=create),
        "get_release_dir": lambda k, create=False: BuildTargets.get_release_dir(k, root, create=create),
        "get_install_dir": lambda k, create=False: BuildTargets.get_install_dir(k, root, create=create),
        "get_test_dir": lambda k, create=False: BuildTargets.get_test_dir(k, root, create=create),
        "get_app_dirs": lambda k, create=False: BuildTargets.get_app_dirs(k, root, create=create),
        "get_version_files": lambda k: BuildTargets.get_version_files(k, root),
        "get_version_fullpath": lambda k: BuildTargets.get_version_fullpath(k, root),
        "get_version_dir": lambda k: BuildTargets.get_version_dir(k, root),
    }