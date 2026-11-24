import sys
from pathlib import Path

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
from Common.log import setup_global_log, logd, LogManagerRegistry, FileTagManager  # 또는 dlog
setup_global_log()

from Common.log import set_file_tag, logd, loge; set_file_tag("SYSTEM")


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

#PROJECT_ROOT = SRC_DIR.parent
PROJECT_ROOT = find_dir_parent_direction(SRC_DIR, "PrintShopApp")
if PROJECT_ROOT and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logd(f"PROJECT_ROOT:{PROJECT_ROOT}, SRC_DIR:{SRC_DIR}")

from Common.Version.version_tab  import VersionTab
from redis_server.redis_session_manager import redis_session_manager


# from Common.log_config import LogConfig
# log_config = LogConfig()


#1. atexit 모듈 활용 (정상 종료 시 자동 수행)
import atexit
# 프로그램 시작 부분(예: setup_global_logd 함수 내부 등)에 등록
atexit.register(LogManagerRegistry.close_all_logs)

#2. signal 모듈 활용 (Ctrl+C, 강제 종료 시그널 감지)
import signal
import sys
def signal_handler(sig, frame):
    print("\n[Logger] 종료 시그널 감지. 남은 로그를 저장합니다...")
    LogManagerRegistry.close_all_logs()
    sys.exit(0)

# 시그널 핸들러 등록
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# from Common.log_settings import LogSettingsTab

import sys
import ctypes
from PySide6.QtWidgets import QApplication, QMessageBox
from print_shop_app import PrintShopApp, initialize_all_configurations
from login_dialog import check_login

import sys
import ctypes
from datetime import datetime  # 💡 시간 데이터 처리를 위한 모듈 임포트
from PySide6.QtWidgets import QApplication, QMessageBox

# 가비지 컬렉션으로 인한 뮤텍스 해제 방지를 위해 전역 변수로 유지
_h_mutex = None

def check_single_instance(mutex_name="PrintShopApp_SingleInstance_Mutex"):
    global _h_mutex
    kernel32 = ctypes.windll.kernel32
    # 뮤텍스 생성 및 핸들 보관
    _h_mutex = kernel32.CreateMutexW(None, False, mutex_name)
    # ERROR_ALREADY_EXISTS (코드 183)
    if kernel32.GetLastError() == 183:
        return False
    return True


if __name__ == "__main__":

    if not check_single_instance():
        # 이미 실행 중인 경우 메시지를 띄우거나 조용히 종료
        print("PrintShopApp is already running.")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")        
        logd(f"[{current_time}] PrintShopApp is already running.")
        LogManagerRegistry.close_all_logs()
        sys.exit(0)    
    
    logd("[DEBUG] Step 1: Starting QApplication...")

    app = QApplication(sys.argv)
    
    logd("[DEBUG] Step 2: Creating PrintShopApp...")

    # 💡 [선택] 경로 설정 확인용 로그 추가
    from Common.path_mgr import PathMgr
    logd(f"[INFO] APPLICATION_DIR : {PathMgr.APPLICATION_DIR}")
    logd(f"[INFO] CUSTOM_DATA_DIR : {PathMgr.DATA_DIR}")    

    initialize_all_configurations()

    check_login()  # 로그인 체크 및 설정 로직 호출

    window = PrintShopApp()
    logd("[DEBUG] Step 3: Calling window.show()...")

    window.show()
    logd(f"[DEBUG] Step 4: Window shown, isVisible = {window.isVisible()}, geometry = {window.geometry()}")    

    window.raise_()
    window.activateWindow()
    logd("[DEBUG] Step 5: Entering app.exec()...")

    app.aboutToQuit.connect(LogManagerRegistry.close_all_logs)

    sys.exit(app.exec())
