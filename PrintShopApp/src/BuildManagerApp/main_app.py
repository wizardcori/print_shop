from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication  # noqa: E402


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
from Common.config import FileConfigManager, DbConfigManager

# 3
from Common.log import setup_global_log, set_file_tag, logd, loge, LogManagerRegistry, FileTagManager  # 또는 dlog
setup_global_log()

set_file_tag("BUILD_MGR")


from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_dir_parent_direction(target_name: str, start_path: str | Path | None = None) -> Path:
    current = Path(start_path).resolve() if start_path is not None else get_base_dir()

    for candidate in (current, *current.parents):
        if candidate.name == target_name or (candidate / target_name).is_dir():
            return candidate if candidate.name == target_name else candidate / target_name

    # 찾지 못했을 때 None 대신 안전한 폴백 경로 반환
    return current


SRC_DIR = find_dir_parent_direction(__file__, "src")
if SRC_DIR and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

PROJECT_ROOT = SRC_DIR.parent if SRC_DIR else Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, str(APP_DIR))


from Common.prio_worker_queue import TaskManager  # noqa: E402
from BuildManagerApp.build_manager_app import BuildManagerWindow  # noqa: E402


def run_app(argv: list[str] | None = None) -> int:
    """PrintShopApp PySide6 빌드 매니저 애플리케이션을 실행합니다."""
    logd("[MainApp] 애플리케이션 시작 준비")
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    # 앱 전체 종료(aboutToQuit) 시 큐 작업 취소/외부 프로세스 kill/워커 종료 연결
    app.aboutToQuit.connect(TaskManager.on_about_to_quit)

    window = BuildManagerWindow(project_root=PROJECT_ROOT) if PROJECT_ROOT else BuildManagerWindow()
    window.show()
    logd("[MainApp] BuildManagerWindow 표시 완료")
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    return run_app(argv)


if __name__ == "__main__":
    sys.exit(main())