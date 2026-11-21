from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication  # noqa: E402


def find_dir_parent_direction(start_file: str | Path, target_dir_name: str) -> Path | None:
    current = Path(start_file).resolve()
    if current.is_file():
        current = current.parent
    for parent in [current, *current.parents]:
        candidate = parent / target_dir_name
        if candidate.is_dir():
            return candidate
    return None


SRC_DIR = find_dir_parent_direction(__file__, "src")
if SRC_DIR and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

PROJECT_ROOT = SRC_DIR.parent if SRC_DIR else Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, str(APP_DIR))

from Common.log import logd, set_file_tag, setup_global_log  # noqa: E402

set_file_tag("BUILD_MGR")
setup_global_log()

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