import sys
import logging
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox, QMessageBox
from setting.general_settings import GeneralSettingsConfig
from setting.operator_settings import OperatorConfig  # 연동된 Operator DB 설정

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("로그인")
        self.config = GeneralSettingsConfig()
        self.operator_config = OperatorConfig() # DB 연동을 위한 설정 객체
        
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

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.handle_login)
        self.button_box.rejected.connect(self.reject)
        
        layout.addWidget(self.button_box)

    def load_saved_config(self):
        # 설정에 저장된 값 불러오기
        self.username_input.setText(self.config.get('login_user_name'))
        self.password_input.setText(self.config.get('login_user_password'))
        self.auto_login_chk.setChecked(self.config.get('auto_login'))

    def verify_credentials(self, username, password):
        """DB(operators 테이블)에서 사용자 정보 검색 및 일치 여부 확인"""
        items = self.operator_config.get_items(active_only=True)
        for item in items:
            if item["user_name"] == username and str(item["user_password"]) == str(password):
                return True
        return False

    def handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        auto_login = self.auto_login_chk.isChecked()

        if not username or not password:
            QMessageBox.warning(self, "경고", "아이디와 비밀번호를 모두 입력해주세요.")
            return

        # DB 검증 수행
        if self.verify_credentials(username, password):
            # 로그인 성공 시 설정 값 저장
            self.config.set('login_user_name', username)
            self.config.set('login_user_password', password if auto_login else "")
            self.config.set('auto_login', auto_login)
            self.config.save()
            self.accept()
        else:
            # 로그인 다이얼로그에서는 로그인 실패 정보 알림
            QMessageBox.warning(self, "로그인 실패", "아이디 또는 비밀번호가 일치하지 않습니다.")

def check_login():
    config = GeneralSettingsConfig()
    operator_config = OperatorConfig()
    
    auto_login = config.get('auto_login')
    saved_user = config.get('login_user_name')
    saved_pass = config.get('login_user_password')

    # 자동 로그인 조건 충족 여부 확인
    is_auto_login_valid = auto_login and saved_user and saved_pass

    if is_auto_login_valid:
        # DB에서 저장된 정보 검증
        items = operator_config.get_items(active_only=True)
        matched = any(item["user_name"] == saved_user and str(item["user_password"]) == str(saved_pass) for item in items)
        
        if matched:
            # auto login 성공시 사용자에게 메시지 표시하지 않고 로그만 출력
            logging.info(f"Auto login successful for user: {saved_user}")
            return True
        else:
            # auto login 실패 시 (비밀번호 변경 등) 로그 출력 후 다이얼로그 오픈
            logging.warning(f"Auto login failed (invalid credentials) for user: {saved_user}")

    # 자동 로그인이 아니거나 유효하지 않으면 로그인 다이얼로그 표시
    while True:
        login_dialog = LoginDialog()
        if login_dialog.exec() == LoginDialog.DialogCode.Accepted:
            return True
        else:
            sys.exit(0)  # 사용자가 로그인을 취소하거나 닫으면 프로그램 종료