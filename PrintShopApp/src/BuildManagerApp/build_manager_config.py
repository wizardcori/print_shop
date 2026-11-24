from __future__ import annotations

from pathlib import Path
from typing import Any

from Common.config import ConfigType, FileConfigManager
from Common.path_mgr import PathMgr

BUILD_MANAGER_INI_NAME: str = f"{PathMgr.APP_NAME}.ini"


class BuildManagerConfig(FileConfigManager):
    """[BuildManagerConfig] 섹션: 앱 기본 설정 및 메인 UI 상태 통합 관리."""

    file_name = BUILD_MANAGER_INI_NAME
    auto_save = False
    section = "BuildManagerConfig"
    section_order = 30
    schema = {
        "project_root": {"default": "", "type": ConfigType.STRING},
        "selected_targets": {"default": [], "type": ConfigType.LIST},
        "mode": {"default": "production", "type": ConfigType.STRING},
        "bump_unit": {"default": "", "type": ConfigType.STRING},
        "skip_installer": {"default": False, "type": ConfigType.BOOLEAN},
        "installer_only": {"default": False, "type": ConfigType.BOOLEAN},
        "clean_build": {"default": False, "type": ConfigType.BOOLEAN},
        "clean_work_out": {"default": False, "type": ConfigType.BOOLEAN},
        "clean_dist_out": {"default": False, "type": ConfigType.BOOLEAN},
        "clean_spec": {"default": False, "type": ConfigType.BOOLEAN},
        "auto_scroll_log": {"default": True, "type": ConfigType.BOOLEAN},
    }


class BuildDirsConfig(FileConfigManager):
    """[BuildDirsConfig] 섹션: 전역 빌드 디렉터리 설정 (dirs)."""

    file_name = BUILD_MANAGER_INI_NAME
    auto_save = False
    section = "BuildDirsConfig"
    section_order = 31
    schema = {
        "work_dir_name": {"default": "work", "type": ConfigType.STRING},
        "dist_dir_name": {"default": "dist", "type": ConfigType.STRING},
        "release_dir_name": {"default": "release", "type": ConfigType.STRING},
        "install_dir_name": {"default": "installer", "type": ConfigType.STRING},
    }


class BuildAppsConfig(FileConfigManager):
    """[BuildAppsConfig] 섹션: 개별 앱 오버라이드 설정 (apps)."""

    file_name = BUILD_MANAGER_INI_NAME
    auto_save = False
    section = "BuildAppsConfig"
    section_order = 32
    schema = {
        "app_overrides": {"default": {}, "type": ConfigType.DICT},
    }


class BuildInstallerConfig(FileConfigManager):
    """[BuildInstallerConfig] 섹션: 인스톨러 조합 설정 (installer)."""

    file_name = BUILD_MANAGER_INI_NAME
    auto_save = False
    section = "BuildInstallerConfig"
    section_order = 33
    schema = {
        "targets": {"default": [], "type": ConfigType.LIST},
        "name": {"default": "", "type": ConfigType.STRING},
        "version_source_id": {"default": "", "type": ConfigType.STRING},
        "installer_only": {"default": False, "type": ConfigType.BOOLEAN},
        "skip_installer": {"default": False, "type": ConfigType.BOOLEAN},
        "extra": {"default": {}, "type": ConfigType.DICT},
    }


class BuildManagerIniStore:
    """각 섹션 Config 인스턴스를 통해 개별 로드/저장합니다."""

    def __init__(self, ini_dir: str | Path | None = None) -> None:
        self.manager_cfg = BuildManagerConfig()
        self.dirs_cfg = BuildDirsConfig()
        self.apps_cfg = BuildAppsConfig()
        self.installer_cfg = BuildInstallerConfig()
        self.reload_all()

    def _all_managers(self) -> tuple[FileConfigManager, ...]:
        return (self.manager_cfg, self.dirs_cfg, self.apps_cfg, self.installer_cfg)

    def reload_all(self, ini_dir: str | Path | None = None) -> None:
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
        self.reload_all()
        bump_raw = str(self.manager_cfg.get("bump_unit") or "").strip()
        return {
            "project_root": str(self.manager_cfg.get("project_root") or "").strip(),
            "selected_targets": list(self.manager_cfg.get("selected_targets") or []),
            "mode": str(self.manager_cfg.get("mode") or "production").strip() or "production",
            "bump_unit": bump_raw if bump_raw else None,
            "skip_installer": bool(self.manager_cfg.get("skip_installer")),
            "installer_only": bool(self.manager_cfg.get("installer_only")),
            "clean_build": bool(self.manager_cfg.get("clean_build")),
            "clean_work_out": bool(self.manager_cfg.get("clean_work_out")),
            "clean_dist_out": bool(self.manager_cfg.get("clean_dist_out")),
            "clean_spec": bool(self.manager_cfg.get("clean_spec")),
            "auto_scroll_log": bool(self.manager_cfg.get("auto_scroll_log")),
        }

    def save_ui_state(self, state: dict[str, Any]) -> Path:
        self.manager_cfg.set("project_root", str(state.get("project_root") or ""))
        self.manager_cfg.set("selected_targets", list(state.get("selected_targets") or []))
        self.manager_cfg.set("mode", str(state.get("mode") or "production"))
        bump_val = state.get("bump_unit")
        self.manager_cfg.set("bump_unit", str(bump_val) if bump_val else "")
        self.manager_cfg.set("skip_installer", bool(state.get("skip_installer", False)))
        self.manager_cfg.set("installer_only", bool(state.get("installer_only", False)))
        self.manager_cfg.set("clean_build", bool(state.get("clean_build", False)))
        self.manager_cfg.set("clean_work_out", bool(state.get("clean_work_out", False)))
        self.manager_cfg.set("clean_dist_out", bool(state.get("clean_dist_out", False)))
        self.manager_cfg.set("clean_spec", bool(state.get("clean_spec", False)))
        if "auto_scroll_log" in state:
            self.manager_cfg.set("auto_scroll_log", bool(state.get("auto_scroll_log", True)))
        self.manager_cfg.save()
        return Path(self.manager_cfg.filepath)

    def load_target_sections(self) -> dict[str, Any]:
        self.reload_all()
        dirs = {
            k: str(self.dirs_cfg.get(k) or "").strip()
            for k in ("work_dir_name", "dist_dir_name", "release_dir_name", "install_dir_name")
        }
        raw_apps = self.apps_cfg.get("app_overrides")
        app_overrides: dict[str, dict[str, Any]] = {}
        if isinstance(raw_apps, dict):
            for k, v in raw_apps.items():
                if isinstance(v, dict):
                    app_overrides[str(k)] = dict(v)

        has_targets_key = self.installer_cfg.config.has_option(
            self.installer_cfg.section, "targets"
        )
        raw_targets = self.installer_cfg.get("targets")
        if isinstance(raw_targets, list):
            inst_targets: list[str] | None = [
                str(x).strip() for x in raw_targets if str(x).strip()
            ]
        elif has_targets_key:
            inst_targets = []
        else:
            inst_targets = None

        raw_extra = self.installer_cfg.get("extra")
        inst_extra = dict(raw_extra) if isinstance(raw_extra, dict) else {}

        installer = {
            "targets": inst_targets or None,
            "name": str(self.installer_cfg.get("name") or "").strip() or None,
            "version_source_id": str(self.installer_cfg.get("version_source_id") or "").strip() or None,
            "installer_only": bool(self.installer_cfg.get("installer_only")),
            "skip_installer": bool(self.installer_cfg.get("skip_installer")),
            "extra": inst_extra,
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
            for k in ("work_dir_name", "dist_dir_name", "release_dir_name", "install_dir_name"):
                val = str(dir_values.get(k) or "").strip()
                if val:
                    self.dirs_cfg.set(k, val)
            self.dirs_cfg.save()

        if app_overrides is not None:
            cleaned_apps = {
                str(k): dict(v)
                for k, v in app_overrides.items()
                if isinstance(v, dict) and v
            }
            self.apps_cfg.set("app_overrides", cleaned_apps)
            self.apps_cfg.save()

        if installer_values is not None:
            targets = installer_values.get("targets")
            self.installer_cfg.set(
                "targets",
                [str(x).strip() for x in targets if str(x).strip()]
                if isinstance(targets, (list, tuple))
                else [],
            )
            self.installer_cfg.set("name", str(installer_values.get("name") or "").strip())
            self.installer_cfg.set(
                "version_source_id",
                str(installer_values.get("version_source_id") or "").strip(),
            )
            self.installer_cfg.set(
                "installer_only", bool(installer_values.get("installer_only", False))
            )
            self.installer_cfg.set(
                "skip_installer", bool(installer_values.get("skip_installer", False))
            )
            extra = installer_values.get("extra")
            self.installer_cfg.set("extra", dict(extra) if isinstance(extra, dict) else {})
            self.installer_cfg.save()

        return Path(self.manager_cfg.filepath)