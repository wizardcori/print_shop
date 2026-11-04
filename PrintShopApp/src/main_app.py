# main.py 등 최초 진입점에서 딱 한 번 실행
from Common.log import setup_global_logd, logd  # 또는 dlog
setup_global_logd()

from Common.log_settings import LogSettingsTab

import sys
from PySide6.QtWidgets import QApplication
from print_shop_app import PrintShopApp, initialize_all_configurations
from login_dialog import check_login


if __name__ == "__main__":
    logd("[DEBUG] Step 1: Starting QApplication...")

    initialize_all_configurations()

    app = QApplication(sys.argv)
    logd("[DEBUG] Step 2: Creating PrintShopApp...")

    check_login()  # 로그인 체크 및 설정 로직 호출

    window = PrintShopApp()
    logd("[DEBUG] Step 3: Calling window.show()...")

    window.show()
    logd(f"[DEBUG] Step 4: Window shown, isVisible = {window.isVisible()}, geometry = {window.geometry()}")    

    window.raise_()
    window.activateWindow()
    logd("[DEBUG] Step 5: Entering app.exec()...")
    sys.exit(app.exec())