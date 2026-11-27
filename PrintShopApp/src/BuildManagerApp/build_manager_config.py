from __future__ import annotations

from pathlib import Path
from typing import Any

from Common.config import ConfigType, FileConfigManager
from Common.path_mgr import PathMgr

BUILD_MANAGER_INI_NAME: str = f"{PathMgr.APP_NAME}.ini"

SECTION_MANAGER_CONFIG: str = "BuildManagerConfig"
SECTION_DIRS_CONFIG: str = "BuildDirsConfig"
SECTION_APPS_CONFIG: str = "BuildAppsConfig"
SECTION_INSTALLER_CONFIG: str = "BuildInstallerConfig"

SECTION_ORDER_MANAGER: int = 30
SECTION_ORDER_DIRS: int = 31
SECTION_ORDER_APPS: int = 32
SECTION_ORDER_INSTALLER: int = 33

DEFAULT_BUILD_MODE: str = "production"
DEFAULT_WORK_DIR_NAME: str = "work"
DEFAULT_DIST_DIR_NAME: str = "dist"
DEFAULT_RELEASE_DIR_NAME: str = "release"
DEFAULT_INSTALL_DIR_NAME: str = "installer"

KEY_PROJECT_ROOT: str = "project_root"
KEY_SELECTED_TARGETS: str = "selected_targets"
KEY_MODE: str = "mode"
KEY_BUMP_UNIT: str = "bump_unit"
KEY_SKIP_INSTALLER: str = "skip_installer"
KEY_INSTALLER_ONLY: str = "installer_only"
KEY_CLEAN_BUILD: str = "clean_build"
KEY_CLEAN_WORK_OUT: str = "clean_work_out"
KEY_CLEAN_DIST_OUT: str = "clean_dist_out"
KEY_CLEAN_SPEC: str = "clean_spec"
KEY_AUTO_SCROLL_LOG: str = "auto_scroll_log"

KEY_WORK_DIR_NAME: str = "work_dir_name"
KEY_DIST_DIR_NAME: str = "dist_dir_name"
KEY_RELEASE_DIR_NAME: str = "release_dir_name"
KEY_INSTALL_DIR_NAME: str = "install_dir_name"

KEY_APP_OVERRIDES: str = "app_overrides"
KEY_SCANNED_LIBS: str = "scanned_libs"
KEY_EXCLUDE_LIBS: str = "exclude_libs"

KEY_TARGETS: str = "targets"
KEY_NAME: str = "name"
KEY_VERSION_SOURCE_ID: str = "version_source_id"
KEY_EXTRA: str = "extra"

DIR_CONFIG_KEYS: tuple[str, ...] = (
    KEY_WORK_DIR_NAME,
    KEY_DIST_DIR_NAME,
    KEY_RELEASE_DIR_NAME,
    KEY_INSTALL_DIR_NAME,
)

__all__ = [
    "BUILD_MANAGER_INI_NAME",
    "BuildInstallerConfig",
    "BuildManagerConfig",
    "BuildManagerIniStore",
    "BuildTargetConfig",
    "BuildDirsConfig",
    "DEFAULT_BUILD_MODE",
    "DEFAULT_DIST_DIR_NAME",
    "DEFAULT_INSTALL_DIR_NAME",
    "DEFAULT_RELEASE_DIR_NAME",
    "DEFAULT_WORK_DIR_NAME",
    "DIR_CONFIG_KEYS",
    "KEY_APP_OVERRIDES",
    "KEY_AUTO_SCROLL_LOG",
    "KEY_BUMP_UNIT",
    "KEY_CLEAN_BUILD",
    "KEY_CLEAN_DIST_OUT",
    "KEY_CLEAN_SPEC",
    "KEY_CLEAN_WORK_OUT",
    "KEY_DIST_DIR_NAME",
    "KEY_EXCLUDE_LIBS",
    "KEY_EXTRA",
    "KEY_INSTALLER_ONLY",
    "KEY_INSTALL_DIR_NAME",
    "KEY_MODE",
    "KEY_NAME",
    "KEY_PROJECT_ROOT",
    "KEY_RELEASE_DIR_NAME",
    "KEY_SCANNED_LIBS",
    "KEY_SELECTED_TARGETS",
    "KEY_SKIP_INSTALLER",
    "KEY_TARGETS",
    "KEY_VERSION_SOURCE_ID",
    "KEY_WORK_DIR_NAME",
    "SECTION_APPS_CONFIG",
    "SECTION_DIRS_CONFIG",
    "SECTION_INSTALLER_CONFIG",
    "SECTION_MANAGER_CONFIG",
    "SECTION_ORDER_APPS",
    "SECTION_ORDER_DIRS",
    "SECTION_ORDER_INSTALLER",
    "SECTION_ORDER_MANAGER",
]


def _normalize_str_list(val: Any) -> list[str]:
    if isinstance(val, (list, tuple, set)):
        return sorted({str(x).strip() for x in val if str(x).strip()})
    if isinstance(val, str) and val.strip():
        sep = "|" if "|" in val and "," not in val else ","
        return sorted({part.strip() for part in val.split(sep) if part.strip()})
    return []


class BuildManagerConfig(FileConfigManager):
    """[BuildManagerConfig] 섹션: 앱 기본 설정 및 메인 UI 상태 통합 관리."""

    file_name = BUILD_MANAGER_INI_NAME
    auto_save = False
    section = SECTION_MANAGER_CONFIG
    section_order = SECTION_ORDER_MANAGER
    schema = {
        KEY_PROJECT_ROOT: {"default": "", "type": ConfigType.STRING},
        KEY_SELECTED_TARGETS: {"default": [], "type": ConfigType.LIST},
        KEY_MODE: {"default": DEFAULT_BUILD_MODE, "type": ConfigType.STRING},
        KEY_BUMP_UNIT: {"default": "", "type": ConfigType.STRING},
        KEY_SKIP_INSTALLER: {"default": False, "type": ConfigType.BOOLEAN},
        KEY_INSTALLER_ONLY: {"default": False, "type": ConfigType.BOOLEAN},
        KEY_CLEAN_BUILD: {"default": False, "type": ConfigType.BOOLEAN},
        KEY_CLEAN_WORK_OUT: {"default": False, "type": ConfigType.BOOLEAN},
        KEY_CLEAN_DIST_OUT: {"default": False, "type": ConfigType.BOOLEAN},
        KEY_CLEAN_SPEC: {"default": False, "type": ConfigType.BOOLEAN},
        KEY_AUTO_SCROLL_LOG: {"default": True, "type": ConfigType.BOOLEAN},
    }


class BuildDirsConfig(FileConfigManager):
    """[BuildDirsConfig] 섹션: 전역 빌드 디렉터리 설정 (dirs)."""

    file_name = BUILD_MANAGER_INI_NAME
    auto_save = False
    section = SECTION_DIRS_CONFIG
    section_order = SECTION_ORDER_DIRS
    schema = {
        KEY_WORK_DIR_NAME: {"default": DEFAULT_WORK_DIR_NAME, "type": ConfigType.STRING},
        KEY_DIST_DIR_NAME: {"default": DEFAULT_DIST_DIR_NAME, "type": ConfigType.STRING},
        KEY_RELEASE_DIR_NAME: {"default": DEFAULT_RELEASE_DIR_NAME, "type": ConfigType.STRING},
        KEY_INSTALL_DIR_NAME: {"default": DEFAULT_INSTALL_DIR_NAME, "type": ConfigType.STRING},
    }


class BuildTargetConfig(FileConfigManager):
    """[BuildAppsConfig] 섹션: 개별 앱 오버라이드 설정 (apps)."""

    file_name = BUILD_MANAGER_INI_NAME
    auto_save = False
    section = SECTION_APPS_CONFIG
    section_order = SECTION_ORDER_APPS
    schema = {
        KEY_APP_OVERRIDES: {"default": {}, "type": ConfigType.DICT},
    }


class BuildInstallerConfig(FileConfigManager):
    """[BuildInstallerConfig] 섹션: 인스톨러 조합 설정 (installer)."""

    file_name = BUILD_MANAGER_INI_NAME
    auto_save = False
    section = SECTION_INSTALLER_CONFIG
    section_order = SECTION_ORDER_INSTALLER
    schema = {
        KEY_TARGETS: {"default": [], "type": ConfigType.LIST},
        KEY_NAME: {"default": "", "type": ConfigType.STRING},
        KEY_VERSION_SOURCE_ID: {"default": "", "type": ConfigType.STRING},
        KEY_INSTALLER_ONLY: {"default": False, "type": ConfigType.BOOLEAN},
        KEY_SKIP_INSTALLER: {"default": False, "type": ConfigType.BOOLEAN},
        KEY_EXTRA: {"default": {}, "type": ConfigType.DICT},
    }


class BuildManagerIniStore:
    """각 섹션 Config 인스턴스를 통해 개별 로드/저장합니다."""

    def __init__(self, ini_dir: str | Path | None = None) -> None:
        self.ini_dir: Path | None = Path(ini_dir).resolve() if ini_dir else None
        self.manager_cfg = BuildManagerConfig()
        self.dirs_cfg = BuildDirsConfig()
        self.apps_cfg = BuildTargetConfig()
        self.installer_cfg = BuildInstallerConfig()
        self.reload_all(self.ini_dir)

    def _all_managers(self) -> tuple[FileConfigManager, ...]:
        return (self.manager_cfg, self.dirs_cfg, self.apps_cfg, self.installer_cfg)

    def _apply_ini_dir(self, ini_dir: str | Path | None) -> None:
        if ini_dir is None:
            return
        target_dir = Path(ini_dir).resolve()
        self.ini_dir = target_dir
        target_file = target_dir / BUILD_MANAGER_INI_NAME
        for mgr in self._all_managers():
            if hasattr(mgr, "filepath"):
                try:
                    mgr.filepath = target_file
                except Exception:
                    pass

    def reload_all(self, ini_dir: str | Path | None = None) -> None:
        self._apply_ini_dir(ini_dir if ini_dir is not None else self.ini_dir)
        for mgr in self._all_managers():
            mgr.auto_save = False
            if hasattr(mgr, "_create_parser") and hasattr(mgr, "_load_and_inject"):
                try:
                    mgr.config = mgr._create_parser()
                    mgr._load_and_inject()
                except Exception:
                    pass

    def load_ui_state(self) -> dict[str, Any]:
        ini_path = Path(self.manager_cfg.filepath)
        if not ini_path.is_file():
            return {}
        self.reload_all(ini_path.parent)
        bump_raw = str(self.manager_cfg.get(KEY_BUMP_UNIT) or "").strip()
        auto_scroll_raw = self.manager_cfg.get(KEY_AUTO_SCROLL_LOG)
        return {
            KEY_PROJECT_ROOT: str(self.manager_cfg.get(KEY_PROJECT_ROOT) or "").strip(),
            KEY_SELECTED_TARGETS: list(self.manager_cfg.get(KEY_SELECTED_TARGETS) or []),
            KEY_MODE: str(self.manager_cfg.get(KEY_MODE) or DEFAULT_BUILD_MODE).strip()
            or DEFAULT_BUILD_MODE,
            KEY_BUMP_UNIT: bump_raw if bump_raw else None,
            KEY_SKIP_INSTALLER: bool(self.manager_cfg.get(KEY_SKIP_INSTALLER)),
            KEY_INSTALLER_ONLY: bool(self.manager_cfg.get(KEY_INSTALLER_ONLY)),
            KEY_CLEAN_BUILD: bool(self.manager_cfg.get(KEY_CLEAN_BUILD)),
            KEY_CLEAN_WORK_OUT: bool(self.manager_cfg.get(KEY_CLEAN_WORK_OUT)),
            KEY_CLEAN_DIST_OUT: bool(self.manager_cfg.get(KEY_CLEAN_DIST_OUT)),
            KEY_CLEAN_SPEC: bool(self.manager_cfg.get(KEY_CLEAN_SPEC)),
            KEY_AUTO_SCROLL_LOG: True if auto_scroll_raw is None else bool(auto_scroll_raw),
        }

    def save_ui_state(self, state: dict[str, Any]) -> Path:
        self.manager_cfg.set(KEY_PROJECT_ROOT, str(state.get(KEY_PROJECT_ROOT) or ""))
        self.manager_cfg.set(KEY_SELECTED_TARGETS, list(state.get(KEY_SELECTED_TARGETS) or []))
        self.manager_cfg.set(KEY_MODE, str(state.get(KEY_MODE) or DEFAULT_BUILD_MODE))
        bump_val = state.get(KEY_BUMP_UNIT)
        self.manager_cfg.set(KEY_BUMP_UNIT, str(bump_val) if bump_val else "")
        self.manager_cfg.set(KEY_SKIP_INSTALLER, bool(state.get(KEY_SKIP_INSTALLER, False)))
        self.manager_cfg.set(KEY_INSTALLER_ONLY, bool(state.get(KEY_INSTALLER_ONLY, False)))
        self.manager_cfg.set(KEY_CLEAN_BUILD, bool(state.get(KEY_CLEAN_BUILD, False)))
        self.manager_cfg.set(KEY_CLEAN_WORK_OUT, bool(state.get(KEY_CLEAN_WORK_OUT, False)))
        self.manager_cfg.set(KEY_CLEAN_DIST_OUT, bool(state.get(KEY_CLEAN_DIST_OUT, False)))
        self.manager_cfg.set(KEY_CLEAN_SPEC, bool(state.get(KEY_CLEAN_SPEC, False)))
        if KEY_AUTO_SCROLL_LOG in state:
            self.manager_cfg.set(KEY_AUTO_SCROLL_LOG, bool(state.get(KEY_AUTO_SCROLL_LOG, True)))
        self.manager_cfg.save()
        return Path(self.manager_cfg.filepath)

    def load_target_sections(self) -> dict[str, Any]:
        self.reload_all(self.ini_dir)
        dirs = {k: str(self.dirs_cfg.get(k) or "").strip() for k in DIR_CONFIG_KEYS}
        raw_apps = self.apps_cfg.get(KEY_APP_OVERRIDES)
        app_overrides: dict[str, dict[str, Any]] = {}
        if isinstance(raw_apps, dict):
            for k, v in raw_apps.items():
                if isinstance(v, dict):
                    entry = dict(v)
                    if KEY_SCANNED_LIBS in entry:
                        scanned = _normalize_str_list(entry[KEY_SCANNED_LIBS])
                        if scanned:
                            entry[KEY_SCANNED_LIBS] = scanned
                        else:
                            entry.pop(KEY_SCANNED_LIBS, None)
                    if KEY_EXCLUDE_LIBS in entry:
                        excluded = _normalize_str_list(entry[KEY_EXCLUDE_LIBS])
                        if excluded:
                            entry[KEY_EXCLUDE_LIBS] = excluded
                        else:
                            entry.pop(KEY_EXCLUDE_LIBS, None)
                    app_overrides[str(k)] = entry

        has_targets_key = self.installer_cfg.config.has_option(
            self.installer_cfg.section, KEY_TARGETS
        )
        raw_targets = self.installer_cfg.get(KEY_TARGETS)
        if isinstance(raw_targets, list):
            inst_targets: list[str] | None = [str(x).strip() for x in raw_targets if str(x).strip()]
        elif has_targets_key:
            inst_targets = []
        else:
            inst_targets = None

        raw_extra = self.installer_cfg.get(KEY_EXTRA)
        inst_extra = dict(raw_extra) if isinstance(raw_extra, dict) else {}

        installer = {
            KEY_TARGETS: inst_targets or None,
            KEY_NAME: str(self.installer_cfg.get(KEY_NAME) or "").strip() or None,
            KEY_VERSION_SOURCE_ID: str(self.installer_cfg.get(KEY_VERSION_SOURCE_ID) or "").strip()
            or None,
            KEY_INSTALLER_ONLY: bool(self.installer_cfg.get(KEY_INSTALLER_ONLY)),
            KEY_SKIP_INSTALLER: bool(self.installer_cfg.get(KEY_SKIP_INSTALLER)),
            KEY_EXTRA: inst_extra,
        }

        return {
            "dirs": dirs,
            "app_overrides": app_overrides,
            "installer": installer,
        }

    def save_target_sections(
        self,
        *,
        dir_values: dict[str, Any] | None = None,
        app_overrides: dict[str, dict[str, Any]] | None = None,
        installer_values: dict[str, Any] | None = None,
    ) -> Path:
        if dir_values is not None:
            for k in DIR_CONFIG_KEYS:
                val = str(dir_values.get(k) or "").strip()
                if val:
                    self.dirs_cfg.set(k, val)
            self.dirs_cfg.save()

        if app_overrides is not None:
            cleaned_apps: dict[str, dict[str, Any]] = {}
            for k, v in app_overrides.items():
                if not isinstance(v, dict) or not v:
                    continue
                entry = dict(v)
                if KEY_SCANNED_LIBS in entry:
                    scanned = _normalize_str_list(entry[KEY_SCANNED_LIBS])
                    if scanned:
                        entry[KEY_SCANNED_LIBS] = scanned
                    else:
                        entry.pop(KEY_SCANNED_LIBS, None)
                if KEY_EXCLUDE_LIBS in entry:
                    excluded = _normalize_str_list(entry[KEY_EXCLUDE_LIBS])
                    if excluded:
                        entry[KEY_EXCLUDE_LIBS] = excluded
                    else:
                        entry.pop(KEY_EXCLUDE_LIBS, None)
                if entry:
                    cleaned_apps[str(k)] = entry
            self.apps_cfg.set(KEY_APP_OVERRIDES, cleaned_apps)
            self.apps_cfg.save()

        if installer_values is not None:
            targets = installer_values.get(KEY_TARGETS)
            self.installer_cfg.set(
                KEY_TARGETS,
                (
                    [str(x).strip() for x in targets if str(x).strip()]
                    if isinstance(targets, (list, tuple))
                    else []
                ),
            )
            self.installer_cfg.set(KEY_NAME, str(installer_values.get(KEY_NAME) or "").strip())
            self.installer_cfg.set(
                KEY_VERSION_SOURCE_ID,
                str(installer_values.get(KEY_VERSION_SOURCE_ID) or "").strip(),
            )
            self.installer_cfg.set(
                KEY_INSTALLER_ONLY, bool(installer_values.get(KEY_INSTALLER_ONLY, False))
            )
            self.installer_cfg.set(
                KEY_SKIP_INSTALLER, bool(installer_values.get(KEY_SKIP_INSTALLER, False))
            )
            extra = installer_values.get(KEY_EXTRA)
            self.installer_cfg.set(KEY_EXTRA, dict(extra) if isinstance(extra, dict) else {})
            self.installer_cfg.save()

        return Path(self.manager_cfg.filepath)
