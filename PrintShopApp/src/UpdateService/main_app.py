import sys
from pathlib import Path
import servicemanager
import win32serviceutil


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

set_file_tag("UPDATE_SERVICE")


from print_shop_update_service import CentralUpdaterService, check_single_instance, logd



if __name__ == '__main__':
    arg_count = len(sys.argv)
    logd(f"[ARGV INFO] Argument Count (len): {arg_count}")
    logd(f"[ARGV INFO] Arguments List (sys.argv): {sys.argv}")

    if check_single_instance():
        logd("[WARNING] PrintShop Update Service is already running. Exiting duplicate instance.")
        sys.exit(0)

    if arg_count == 1:
        try:
            logd(f"[INFO] Windows 서비스 백그라운드 모드(SCM) 진입 시도 중...")
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(CentralUpdaterService)
            servicemanager.StartServiceCtrlDispatcher()
        except Exception as e:
            logd(f"[INFO] 서비스 컨트롤러(SCM) 연결 예외 또는 콘솔 직접 실행 모드: {e}")
    else:
        try:
            logd(f"[INFO] 경우 2: 인자가 존재할 때 install, start, stop 등 명령어 제어 모드")
            win32serviceutil.HandleCommandLine(CentralUpdaterService)
        except Exception as e:
            logd(f"[ERROR] 서비스 명령어 처리 중 예외 발생: {e}")
            