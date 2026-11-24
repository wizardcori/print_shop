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
from Common.config import FileConfigManager, DbConfigManager

# 3
from Common.log import setup_global_log, set_file_tag, logd, loge, LogManagerRegistry, FileTagManager  # 또는 dlog
setup_global_log()

set_file_tag("VERSION_VIEWER")



from VersionViewer.version_viewer import VersionViewerWindow


def main():
    app = QApplication(sys.argv)
    window = VersionViewerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()