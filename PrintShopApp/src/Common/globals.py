"""Canonical runtime data paths shared by the integrated applications."""

import os
import sys

import os
from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader



# 인코딩 방식을 전역 변수(상수)로 선언
DEFAULT_ENCODING = 'utf-8-sig'
CONFIG_ENCODING = DEFAULT_ENCODING

# 전역 로그인 관련 상태 변수 선언
GLOBAL_LOGIN_USER_NAME = ""


# 기본 상수 설정
DEFAULT_HOTSPOT_SSID = 'hbwifi'
DEFAULT_HOTSPOT_PASSWORD = 'hbwifihb'
DEFAULT_FILE_TRANSFER_MINUTES = 10
DEFAULT_COLOR_OPTIONS = ['Color', 'B&W']
DEFAULT_INTERNET_FARES = [{'minutes': 30, 'price': 5}]
WINDOWS_HOTSPOT_LIMIT_MAX = 128

APP_MODE_LABEL = 'OpMode'
APP_PRINTER_WATCH_ENABLED = False
APP_PRINTER_WATCH_BUILD_ENABLED = False
APP_BUILD_TIME_TEST_ENABLED = False
APP_BUILD_MODE_DEVELOPMENT = False
APP_MODE_CAN_SWITCH = False
APP_SET_RUNTIME_MODE = lambda mode: False
APP_RUNTIME_TEST_ENABLED = False
APP_RUNTIME_FEATURES = {}
APP_RUNTIME_FEATURE_FILE = ''



def resource_path(relative_path):
    """ PyInstaller로 빌드된 환경과 일반 개발 환경 모두에서 파일 경로를 찾아주는 함수 """
    try:
        # PyInstaller가 생성하는 임시 폴더 경로 (exe로 실행될 때)
        base_path = sys._MEIPASS
    except Exception:
        # 일반 파이썬 코드로 실행될 때 (현재 파일 기준)
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


def load_ui_safely(ui_file_path, parent=None):
    if not os.path.exists(ui_file_path):
        raise FileNotFoundError(f"[오류] UI 파일을 찾을 수 없습니다: {ui_file_path}")
    
    if os.path.getsize(ui_file_path) == 0:
        raise ValueError(f"[오류] UI 파일이 비어있습니다 (0바이트): {ui_file_path}")
        
    file = QFile(ui_file_path)
    if not file.open(QFile.ReadOnly):
        raise RuntimeError(f"[오류] UI 파일을 열 수 없습니다: {ui_file_path}")
    file.close()
    
    try:
        loader = QUiLoader()
        ui = loader.load(ui_file_path, parent)
        if ui is None:
            raise RuntimeError(f"[오류] QUiLoader 파싱 실패: {ui_file_path}")
        return ui
    except Exception as e:
        raise RuntimeError(f"[오류] UI 로딩 중 에러 발생: {e}")

