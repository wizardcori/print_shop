"""General App Settings and Configuration."""

import os
import sys
import shutil
import ctypes
from dotenv import load_dotenv

from Common.paths import DATA_DIR
from Common.config import FileConfigManager, ConfigType
from Common.settings_registry import register_settings_tab
from Common.current_user_session import CurrentUserSession

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QLineEdit, QSpinBox, QPushButton, QMessageBox

# 프로그램 데이터 경로 설정 (환경에 맞게 조정 가능)
# PROGRAM_DATA_DIR = os.path.dirname(os.path.abspath(__file__))
# DATA_DIR = os.path.join(PROGRAM_DATA_DIR, 'data')

class EnvSettingsConfig(FileConfigManager):
    section = "EnvSettings"
    section_order = 10
    schema = {
        'runtime_mode': {"default": "development", "type": ConfigType.STRING},
        'is_admin': {"default": False, "type": ConfigType.BOOLEAN},
        'show_mode_in_title': {"default": True, "type": ConfigType.BOOLEAN},
        'show_feature_in_title': {"default": True, "type": ConfigType.BOOLEAN},
        'use_printer_watch': {"default": True, "type": ConfigType.BOOLEAN},
        'use_run_time_test': {"default": False, "type": ConfigType.BOOLEAN},
        'use_run_time_test2': {"default": False, "type": ConfigType.BOOLEAN},
        'use_run_time_test3': {"default": False, "type": ConfigType.BOOLEAN},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialize_environment()

    def initialize_environment(self):
        """환경 변수, 빌드 모드, 런타임 플래그 및 관리자 권한 초기화 후 Config 스키마와 동기화"""
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(self.project_root, '.env'), override=True)

        build_use_printer_watch = True
        build_use_build_time_test = False

        # PyInstaller(frozen) 환경 처리
        if getattr(sys, 'frozen', False):
            try:
                from build_config_generated import (
                    BUILD_MODE, BUILD_USE_PRINTER_WATCH, BUILD_USE_BUILD_TIME_TEST,
                )
                build_use_printer_watch = BUILD_USE_PRINTER_WATCH
                build_use_build_time_test = BUILD_USE_BUILD_TIME_TEST
                os.environ['MODE'] = BUILD_MODE
            except ImportError:
                pass

        # 개발 환경일 때만 feature runtime 환경 변수 로드
        if not getattr(sys, 'frozen', False):
            load_dotenv(os.path.join(self.project_root, '.env.feature.runtime'), override=True)

        # 런타임 모드 결정
        _default_mode = 'production' if getattr(sys, 'frozen', False) else 'development'
        saved_mode = self.get('runtime_mode')
        build_mode = os.environ.get('MODE', saved_mode).strip().lower()
        if build_mode not in {'development', 'production'}:
            build_mode = _default_mode

        self.build_mode = build_mode
        self.mode_can_switch = (build_mode == 'development')
        self.is_development_mode = (build_mode == 'development')

        # 환경 변수 및 FileConfigManager 저장
        os.environ['MODE'] = build_mode
        self.set('runtime_mode', build_mode)

        # 프린터 감시 및 런타임 테스트 플래그 설정
        _default_printer_watch = 'false' if getattr(sys, 'frozen', False) else 'true'
        _runtime_printer_watch = os.environ.get('USE_PRINTER_WATCH', _default_printer_watch).strip().lower() not in {
            '0', 'false', 'no', 'off', 'disabled',
        }
        
        use_printer_watch = build_use_printer_watch and _runtime_printer_watch

        _def_use_run_time_test = 'false'
        use_run_time_test = os.environ.get('USE_RUN_TIME_TEST', _def_use_run_time_test).strip().lower() in {
            '1', 'true', 'yes', 'on',
        }

        _def_use_run_time_test2 = 'false'
        use_run_time_test2 = os.environ.get('USE_RUN_TIME_TEST2', _def_use_run_time_test2).strip().lower() in {
            '1', 'true', 'yes', 'on',
        }

        _def_use_run_time_test3 = 'false'
        use_run_time_test3 = os.environ.get('USE_RUN_TIME_TEST3', _def_use_run_time_test3).strip().lower() in {
            '1', 'true', 'yes', 'on',
        }

        # 인스턴스 변수 및 스키마 값 동기화
        self.use_printer_watch = use_printer_watch
        self.use_run_time_test = use_run_time_test
        self.use_run_time_test2 = use_run_time_test2
        self.use_run_time_test3 = use_run_time_test3

        self.set('use_printer_watch', use_printer_watch)
        self.set('use_run_time_test', use_run_time_test)
        self.set('use_run_time_test2', use_run_time_test2)
        self.set('use_run_time_test3', use_run_time_test3)

        # 관리자 권한 확인 후 인스턴스 변수 및 Config 스키마에 저장
        admin_status = self.is_running_as_administrator()
        self.is_admin = admin_status
        self.set('is_admin', admin_status)

    def is_running_as_administrator(self):
        """현재 프로세스가 관리자 권한으로 실행 중인지 확인합니다."""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False

    def set_runtime_mode(self, mode):
        """실행 중에 런타임 모드를 변경합니다."""
        if not self.mode_can_switch:
            return False
            
        normalized = str(mode).strip().lower()
        if normalized not in {'development', 'production'}:
            return False
            
        os.environ['MODE'] = normalized
        self.build_mode = normalized
        self.is_development_mode = (normalized == 'development')
        self.set('runtime_mode', normalized)
            
        return True


class EnvSettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = EnvSettingsConfig()
        self.widgets = {}
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        
        layout.addWidget(QLabel("<h3>Environment Settings</h3>"))
        
        # schema에 정의된 모든 항목을 동적으로 순회하며 UI 생성
        for key, meta in self.config.schema.items():
            default_val = meta.get("default")
            config_type = meta.get("type")
            current_val = self.config.get(key)
            
            row_layout = QHBoxLayout()
            label = QLabel(key.replace('_', ' ').title())
            row_layout.addWidget(label)
            
            if config_type == ConfigType.BOOLEAN:
                widget = QCheckBox()
                widget.setChecked(bool(current_val if current_val is not None else default_val))
                if key == 'is_admin':
                    widget.setEnabled(False)
                row_layout.addWidget(widget)
                
            elif config_type == ConfigType.INTEGER:
                widget = QSpinBox()
                widget.setRange(-999999, 999999)
                widget.setValue(int(current_val if current_val is not None else default_val))
                row_layout.addWidget(widget)
                
            else:  # ConfigType.STRING 등
                widget = QLineEdit()
                widget.setText(str(current_val if current_val is not None else default_val))
                if key == 'runtime_mode' and not self.config.mode_can_switch:
                    widget.setEnabled(False)
                row_layout.addWidget(widget)
                
            self.widgets[key] = widget
            layout.addLayout(row_layout)
            
        layout.addStretch()

        # --- DeleteAllConfig 버튼 추가 ---
        self.delete_all_btn = QPushButton("Delete All Config")
        
        # 초기 버튼 상태 업데이트
        self.update_delete_button_state()
        
        self.delete_all_btn.clicked.connect(self.on_delete_all_config)
        layout.addWidget(self.delete_all_btn)

        main_layout.addWidget(scroll_content)

    def showEvent(self, event):
        """탭이 선택되어 화면에 보일 때마다 호출되어 버튼 상태를 갱신합니다."""
        super().showEvent(event)
        self.update_delete_button_state()

    def update_delete_button_state(self):
        """development 모드이면서 관리자(is_admin_user) 권한인 경우에만 보이 고 활성화"""
        is_dev = getattr(self.config, 'is_development_mode', False)
        current_user_session = CurrentUserSession()
        is_admin_user = current_user_session.is_admin_user()
        can_use_delete = is_dev and is_admin_user
        
        if hasattr(self, 'delete_all_btn'):
            self.delete_all_btn.setVisible(can_use_delete)
            self.delete_all_btn.setEnabled(can_use_delete)

    def on_delete_all_config(self):
        """DATA_DIR 하위의 모든 파일 및 폴더를 삭제하고 등록된 모든 로그 시스템을 재시작합니다."""
        if not os.path.exists(DATA_DIR):
            QMessageBox.information(self, "안내", f"데이터 디렉토리가 존재하지 않습니다:\n{DATA_DIR}")
            return

        reply = QMessageBox.question(
            self, 
            "경고", 
            f"다음 경로의 하위 모든 파일이 삭제됩니다:\n{DATA_DIR}\n\n정말 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # 1단계: 레지스트리를 통해 모든 로거 및 전역 핸들러 일괄 종료 (파일 잠금/WinError 32 방지)
                from Common.log import LogManagerRegistry
                LogManagerRegistry.close_all_logs()

                # 2단계: DATA_DIR 하위 파일 및 폴더 삭제
                for filename in os.listdir(DATA_DIR):
                    file_path = os.path.join(DATA_DIR, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as sub_e:
                        print(f"파일 삭제 실패 ({file_path}): {sub_e}")
                        continue  # 오류가 난 파일은 건너뛰고 다음 파일/폴더로 진행

                # 3단계: 삭제되었을 수 있는 로그 디렉토리 재생성
                log_dir = os.path.join(DATA_DIR, 'log')
                os.makedirs(log_dir, exist_ok=True)
                
                # 4단계: 레지스트리에 등록된 모든 로그 시스템 재오픈 (로깅 재개)
                LogManagerRegistry.reopen_all_logs()

                QMessageBox.information(self, "성공", "모든 설정 및 데이터가 삭제되었고, 전체 로그 시스템이 재시작되었습니다.")

            except Exception as e:
                QMessageBox.critical(self, "오류", f"처리 중 오류가 발생했습니다:\n{e}")
                
    def save_to_config(self):
        """UI에 입력된 모든 설정을 반영하고 저장"""
        for key, widget in self.widgets.items():
            if isinstance(widget, QCheckBox):
                if key == 'is_admin':
                    continue
                value = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QLineEdit):
                if not widget.isEnabled():
                    continue
                value = widget.text()
                if key == 'runtime_mode':
                    self.config.set_runtime_mode(value)
                    continue
            else:
                continue
                
            self.config.set(key, value)


# 설정 레지스트리에 탭 등록
register_settings_tab('env-settings', 'Environment', EnvSettingsTab, order=20)

# 다른 모듈에서 참조하여 사용할 수 있는 전역 설정 인스턴스 생성
config = EnvSettingsConfig()