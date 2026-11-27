import os
import sys
from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from Common.current_user_session import CurrentUserSession
from Common.log import logd
from setting.general_settings import GeneralConfig
from setting.operator_settings import OperatorConfig


def verify_operator_credentials(
    operator_config: OperatorConfig,
    username: str,
    password: str,
) -> Optional[Dict[str, Any]]:
    """DB(operators 테이블)에서 활성 사용자 정보 검색 및 자격 증명 일치 여부 확인"""
    items = operator_config.get_items(active_only=True)
    for item in items:
        if item.get("user_name") == username and str(item.get("user_password", "")) == str(
            password
        ):
            return item
    return None


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("로그인")
        self.general_config = GeneralConfig()
        self.operator_config = OperatorConfig()

        logd(f"LoginDialog config filepath: {self.general_config.filepath}")

        self.init_ui()
        self.load_saved_config()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.auto_login_chk = QCheckBox("자동 로그인")

        form_layout.addRow("아이디:", self.username_input)
        form_layout.addRow("비밀번호:", self.password_input)
        form_layout.addRow("", self.auto_login_chk)

        layout.addLayout(form_layout)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.handle_login)
        self.button_box.rejected.connect(self.reject)

        layout.addWidget(self.button_box)

    def load_saved_config(self):
        username = self.general_config.get("login_user_name")
        password = self.general_config.get("login_user_password")
        auto_login = self.general_config.get("auto_login")

        self.username_input.setText(str(username or ""))
        self.password_input.setText(str(password or ""))
        self.auto_login_chk.setChecked(bool(auto_login))

    def handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        auto_login = self.auto_login_chk.isChecked()

        if not username or not password:
            QMessageBox.warning(self, "경고", "아이디와 비밀번호를 모두 입력해주세요.")
            return

        matched_user_info = verify_operator_credentials(self.operator_config, username, password)
        if matched_user_info:
            self.general_config.set("login_user_name", username)
            self.general_config.set("login_user_password", password if auto_login else "")
            self.general_config.set("auto_login", auto_login)
            self.general_config.save()

            logd(
                f"[LoginSave] filepath={self.general_config.filepath}, exists={os.path.exists(self.general_config.filepath)}"
            )
            logd(
                f"[LoginSave] readback auto_login={self.general_config.get('auto_login')}, user={self.general_config.get('login_user_name')}"
            )

            session = CurrentUserSession()
            session.login(
                username=matched_user_info.get("user_name"),
                authority=matched_user_info.get("authority", "user"),
                privilege=matched_user_info.get("privilege", {}),
            )
            self.accept()
        else:
            QMessageBox.warning(self, "로그인 실패", "아이디 또는 비밀번호가 일치하지 않습니다.")


def check_login() -> bool:
    config = GeneralConfig()
    operator_config = OperatorConfig()

    logd(f"config.filepath: {config.filepath}")

    auto_login = config.get("auto_login")
    saved_user = config.get("login_user_name")
    saved_pass = config.get("login_user_password")

    is_auto_login_valid = bool(auto_login and saved_user and saved_pass)

    if is_auto_login_valid:
        matched_user_info = verify_operator_credentials(operator_config, saved_user, saved_pass)
        if matched_user_info:
            logd(f"Auto login successful for user: {saved_user}", level="info")

            session = CurrentUserSession()
            session.login(
                username=matched_user_info.get("user_name"),
                authority=matched_user_info.get("authority", "user"),
                privilege=matched_user_info.get("privilege", {}),
            )
            return True

        logd(f"Auto login failed (invalid credentials) for user: {saved_user}", level="warning")

    while True:
        login_dialog = LoginDialog()
        if login_dialog.exec() == LoginDialog.DialogCode.Accepted:
            return True
        sys.exit(0)
