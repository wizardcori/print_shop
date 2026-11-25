from __future__ import annotations

import atexit
import ctypes
import signal
import sys
from datetime import datetime
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
set_file_tag("SYSTEM")


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_dir_parent_direction(target_name: str, start_path: str | Path | None = None) -> Path:
    current = Path(start_path).resolve() if start_path is not None else get_base_dir()

    for candidate in (current, *current.parents):
        if candidate.name == target_name or (candidate / target_name).is_dir():
            return candidate if candidate.name == target_name else candidate / target_name

    return current


SRC_DIR = find_dir_parent_direction(__file__, "src")
if SRC_DIR and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

PROJECT_ROOT = find_dir_parent_direction(SRC_DIR, "PrintShopApp")
if PROJECT_ROOT and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Common.app_control import QtAppControlReceiver
from login_dialog import check_login
from print_shop_app import PrintShopApp, initialize_all_configurations

_h_mutex = None


def release_single_instance_mutex() -> None:
    global _h_mutex
    if _h_mutex:
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.ReleaseMutex(_h_mutex)
            kernel32.CloseHandle(_h_mutex)
        except Exception:
            pass
        finally:
            _h_mutex = None


def cleanup_before_exit() -> None:
    release_single_instance_mutex()
    try:
        LogManagerRegistry.close_all_logs()
    except Exception:
        pass


atexit.register(LogManagerRegistry.close_all_logs)


def signal_handler(sig, frame):  # noqa: ARG001
    cleanup_before_exit()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def check_single_instance(mutex_name="PrintShopApp_SingleInstance_Mutex"):
    global _h_mutex
    kernel32 = ctypes.windll.kernel32
    _h_mutex = kernel32.CreateMutexW(None, False, mutex_name)
    return kernel32.GetLastError() != 183


def run_app(app_name: str | None = None, argv: list[str] | None = None) -> int:
    resolved_name = (app_name or APP_NAME or "PrintShopApp").strip()

    if not check_single_instance():
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logd(f"[{now_str}] {resolved_name} is already running.")
        LogManagerRegistry.close_all_logs()
        return 0

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.aboutToQuit.connect(LogManagerRegistry.close_all_logs)

    # PySide6 메인 이벤트 루프(app.quit)를 경유하는 제어 신호 수신기 연결
    ctrl = QtAppControlReceiver(
        resolved_name,
        app,
        cleanup_fn=cleanup_before_exit,
        auto_start=True,
    )

    initialize_all_configurations()
    check_login()

    window = PrintShopApp()
    window.show()
    window.raise_()
    window.activateWindow()

    exec_code = 0
    try:
        exec_code = app.exec()
        return ctrl.finalize_shutdown_or_restart(
            cleanup_fn=cleanup_before_exit,
            exit_code=exec_code,
        )
    finally:
        ctrl.stop()
        release_single_instance_mutex()


def main(app_name: str | None = None, argv: list[str] | None = None) -> int:
    return run_app(app_name=app_name, argv=argv)


if __name__ == "__main__":
    sys.exit(main(APP_NAME))