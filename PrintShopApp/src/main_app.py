# main.py 등 최초 진입점에서 딱 한 번 실행
from Common.log import setup_global_logd, logd, LogManagerRegistry  # 또는 dlog
setup_global_logd()

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
from PySide6.QtWidgets import QApplication
from print_shop_app import PrintShopApp, initialize_all_configurations
from login_dialog import check_login


if __name__ == "__main__":
    
    logd("[DEBUG] Step 1: Starting QApplication...")

    app = QApplication(sys.argv)
    
    logd("[DEBUG] Step 2: Creating PrintShopApp...")

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
