"""
기본 빌드 대상 레코드 및 상수 정의 모듈 (target_records.py)
"""

from __future__ import annotations

from build_script.build_targets import (
    BuildTargets,
    INSTALLER_DEFAULT_LABEL,
    INSTALLER_TARGET_KEY,
    MAIN_APP_ORDER,
    MAIN_APP_OVERRIDE_NAME,
    MAIN_APP_RAW_NAME,
    inject_target_records,
)

# 대상 순서(order) 상수
ORDER_MAIN_APP: str = MAIN_APP_ORDER
ORDER_UPDATE_SERVICE: str = "2"
ORDER_UPDATE_MANAGER: str = "3"
ORDER_VERSION_VIEWER: str = "4"
ORDER_BUILD_MANAGER_APP: str = "5"
ORDER_INSTALLER: str = "6"

# 대상 이름(name) 상수
NAME_MAIN_APP: str = MAIN_APP_RAW_NAME
NAME_UPDATE_SERVICE: str = "UpdateService"
NAME_UPDATE_MANAGER: str = "UpdateManager"
NAME_VERSION_VIEWER: str = "VersionViewer"
NAME_BUILD_MANAGER_APP: str = "BuildManagerApp"
NAME_INSTALLER: str = INSTALLER_TARGET_KEY

# 메인 앱 디렉터리 힌트 상수
DIR_HINTS_MAIN_APP: tuple[str, ...] = (MAIN_APP_OVERRIDE_NAME, NAME_MAIN_APP)

# BuildManagerApp 추가 경로 및 hidden_imports 상수
BUILD_MANAGER_EXTRA_PATH: str = "src/build_script"
BUILD_MANAGER_EXTRA_PATHEX: tuple[str, ...] = (BUILD_MANAGER_EXTRA_PATH,)
BUILD_MANAGER_HIDDEN_IMPORTS: tuple[str, ...] = (
    "env_ui_helper",
    "build_script.env_ui_helper",
    "packaging_service",
    "build_script.packaging_service",
    "spec_builder",
    "build_script.spec_builder",
    "target_config_io",
    "build_script.target_config_io",
    "version_service",
    "build_script.version_service",
)

# 인스톨러 정책 상수
INSTALLER_LABEL: str = INSTALLER_DEFAULT_LABEL
INSTALLER_COPY_TO_TEST: bool = False
INSTALLER_COPY_TO_ARCHIVE: bool = True
INSTALLER_INCLUDE_IN_INSTALLER: bool = False
INSTALLER_IS_INSTALLER: bool = True
INSTALLER_RUN_TEST: bool = False

__all__ = [
    "BUILD_MANAGER_EXTRA_PATH",
    "BUILD_MANAGER_EXTRA_PATHEX",
    "BUILD_MANAGER_HIDDEN_IMPORTS",
    "DIR_HINTS_MAIN_APP",
    "INSTALLER_COPY_TO_ARCHIVE",
    "INSTALLER_COPY_TO_TEST",
    "INSTALLER_INCLUDE_IN_INSTALLER",
    "INSTALLER_IS_INSTALLER",
    "INSTALLER_LABEL",
    "NAME_BUILD_MANAGER_APP",
    "NAME_INSTALLER",
    "NAME_MAIN_APP",
    "NAME_UPDATE_MANAGER",
    "NAME_UPDATE_SERVICE",
    "NAME_VERSION_VIEWER",
    "ORDER_BUILD_MANAGER_APP",
    "ORDER_INSTALLER",
    "ORDER_MAIN_APP",
    "ORDER_UPDATE_MANAGER",
    "ORDER_UPDATE_SERVICE",
    "ORDER_VERSION_VIEWER",
    "build_default_records",
    "ensure_default_targets_injected",
]


def build_default_records() -> list[dict]:
    return [
        BuildTargets._make_record(
            ORDER_MAIN_APP,
            NAME_MAIN_APP,
            dir_hints=DIR_HINTS_MAIN_APP,
            run_test=True,            
        ),
        BuildTargets._make_record(
            ORDER_UPDATE_SERVICE,
            NAME_UPDATE_SERVICE,
            run_test=True,            
        ),
        BuildTargets._make_record(
            ORDER_UPDATE_MANAGER,
            NAME_UPDATE_MANAGER,
            run_test=True,            
        ),
        BuildTargets._make_record(
            ORDER_VERSION_VIEWER,
            NAME_VERSION_VIEWER,
            run_test=True,            
        ),
        BuildTargets._make_record(
            ORDER_BUILD_MANAGER_APP,
            NAME_BUILD_MANAGER_APP,
            run_test=True,            
            extra_pathex=BUILD_MANAGER_EXTRA_PATHEX,
            hidden_imports=BUILD_MANAGER_HIDDEN_IMPORTS,
        ),
        BuildTargets._make_record(
            ORDER_INSTALLER,
            NAME_INSTALLER,
            label=INSTALLER_LABEL,
            copy_to_test=INSTALLER_COPY_TO_TEST,
            run_test=INSTALLER_RUN_TEST,            
            copy_to_archive=INSTALLER_COPY_TO_ARCHIVE,
            include_in_installer=INSTALLER_INCLUDE_IN_INSTALLER,
            is_installer=INSTALLER_IS_INSTALLER,
        ),
    ]


def ensure_default_targets_injected() -> type[BuildTargets]:
    if not BuildTargets.RECORDS:
        return inject_target_records(build_default_records())
    return BuildTargets