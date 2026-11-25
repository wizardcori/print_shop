from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

APP_DIR = Path(__file__).resolve().parent
SRC_DIR = APP_DIR.parent

for p in (str(APP_DIR), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app_name import APP_NAME

# 1
from Common.path_mgr import PathMgr

PathMgr.refresh_paths(app_name=APP_NAME)

# 2
from Common.config import DbConfigManager, FileConfigManager  # noqa: F401

# 3
from Common.log import FileTagManager, LogManagerRegistry, logd, loge, set_file_tag, setup_global_log  # noqa: F401

setup_global_log()
set_file_tag("UPDATE_MGR")

# 경로 동적 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

common_version_dir = os.path.join(parent_dir, "Common", "Version")
if common_version_dir not in sys.path:
    sys.path.insert(0, common_version_dir)

common_dir = os.path.join(parent_dir, "Common")
if common_dir not in sys.path:
    sys.path.insert(0, common_dir)

from Common.app_control import QtAppControlReceiver
from Common.log import DEFAULT_LOG_FILE, logd, loge, reopen_global_log  # noqa: F401
from Common.path_mgr import PathMgr
from Common.prio_worker_queue import TaskManager
from UpdateManager.printshop_update_manager import UpdateManagerWindow
from UpdateManager.update_manager_config import GitHubConfigManager


def _cleanup_update_manager() -> None:
    """작업 큐 정리를 수행합니다."""
    try:
        TaskManager.on_about_to_quit()
    except Exception:
        pass


def run_app(app_name: str | None = None, argv: list[str] | None = None) -> int:
    resolved_name = (app_name or APP_NAME or "UpdateManager").strip()

    PathMgr.refresh_paths("data_update_mgr")
    # reopen_global_log()

    logd(f"PrintShop Update Manager 애플리케이션 실행 시작 [main_app.py] (app_name={resolved_name})")

    logd(f"[환경 설정] APPLICATION_DIR: {PathMgr.APPLICATION_DIR}")
    logd(f"[환경 설정] PROGRAM_DATA_DIR: {PathMgr.PROGRAM_DATA_DIR}")
    logd(f"[환경 설정] CUSTOM_DATA_DIR: {PathMgr.CUSTOM_DATA_DIR}")
    logd(f"[환경 설정] DATA_DIR: {PathMgr.DATA_DIR}")
    logd(f"[환경 설정] CONFIG_DIR: {PathMgr.CONFIG_DIR}")
    logd(f"[환경 설정] LOG_DIR: {PathMgr.LOG_DIR}")

    app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
    app.aboutToQuit.connect(_cleanup_update_manager)

    ctrl = QtAppControlReceiver(
        resolved_name,
        app,
        cleanup_fn=_cleanup_update_manager,
        auto_start=True,
    )

    config_mgr = GitHubConfigManager(config_dir=PathMgr.CONFIG_DIR, filename="github_config.ini")

    window = UpdateManagerWindow(config_mgr)
    window.show()

    logd("PrintShop Update Manager 애플리케이션 진입점 실행 완료")

    exec_code = 0
    try:
        exec_code = app.exec()
        return ctrl.finalize_shutdown_or_restart(
            cleanup_fn=_cleanup_update_manager,
            exit_code=exec_code,
        )
    finally:
        ctrl.stop()


def main(app_name: str | None = None, argv: list[str] | None = None) -> int:
    return run_app(app_name=app_name, argv=argv)


if __name__ == "__main__":
    sys.exit(main(APP_NAME))