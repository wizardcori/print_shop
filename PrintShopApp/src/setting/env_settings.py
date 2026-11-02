"""General App Settings and Configuration."""

import os
import sys
import ctypes
from dotenv import load_dotenv

from Common.config import FileConfigManager, ConfigType
from Common.settings_dialog import register_settings_tab
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox

# 참고: FileConfigManager 및 ConfigType은 프로젝트 환경에 맞게 이미 정의되어 있다고 가정합니다.

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
        # get() 메서드의 두 번째 인자로 기본값을 넣어줍니다.
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
        use_run_time_test3 = os.environ.get('USE_RUN_TIME_TEST3', _def_use_run_time_test3   ).strip().lower() in {
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

# 다른 모듈에서 참조하여 사용할 수 있는 전역 설정 인스턴스 생성
config = EnvSettingsConfig()