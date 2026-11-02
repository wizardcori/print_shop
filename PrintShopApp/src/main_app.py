import sys
from PySide6.QtWidgets import QApplication
from print_shop_app import PrintShopApp, initialize_all_configurations
from login_dialog import check_login

if __name__ == "__main__":
    print("[DEBUG] Step 1: Starting QApplication...", flush=True)

    initialize_all_configurations()

    app = QApplication(sys.argv)
    print("[DEBUG] Step 2: Creating PrintShopApp...", flush=True)

    check_login()  # 로그인 체크 및 설정 로직 호출

    window = PrintShopApp()
    print("[DEBUG] Step 3: Calling window.show()...", flush=True)

    window.show()
    print("[DEBUG] Step 4: Window shown, isVisible =", window.isVisible(), "geometry =", window.geometry(), flush=True)
    window.raise_()
    window.activateWindow()
    print("[DEBUG] Step 5: Entering app.exec()...", flush=True)
    sys.exit(app.exec())