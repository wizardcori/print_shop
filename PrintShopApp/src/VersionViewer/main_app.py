from __future__ import annotations

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
set_file_tag("VERSION_VIEWER")

from Common.app_control import QtAppControlReceiver
from VersionViewer.version_viewer import VersionViewerWindow


def _cleanup_before_exit() -> None:
    """종료 또는 재시작 직전 로그 리소스를 정리합니다."""
    try:
        LogManagerRegistry.close_all_logs()
    except Exception:
        pass


def run_app(app_name: str | None = None, argv: list[str] | None = None) -> int:
    resolved_name = (app_name or APP_NAME or "VersionViewer").strip()
    logd(f"[VersionViewer] 애플리케이션 시작 준비 (app_name={resolved_name})")

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    ctrl = QtAppControlReceiver(
        resolved_name,
        app,
        cleanup_fn=_cleanup_before_exit,
        auto_start=True,
    )

    window = VersionViewerWindow()
    window.show()

    exec_code = 0
    try:
        exec_code = app.exec()
        return ctrl.finalize_shutdown_or_restart(
            cleanup_fn=_cleanup_before_exit,
            exit_code=exec_code,
        )
    finally:
        ctrl.stop()
        _cleanup_before_exit()


def main(app_name: str | None = None, argv: list[str] | None = None) -> int:
    return run_app(app_name=app_name, argv=argv)


if __name__ == "__main__":
    sys.exit(main(APP_NAME))