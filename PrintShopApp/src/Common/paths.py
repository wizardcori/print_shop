"""Canonical runtime data paths shared by the integrated applications."""

import os
import sys
from PySide6.QtUiTools import QUiLoader

APP_NAME = 'PrintShopApp'

# 전역 변수 선언 (초기값 지정 또는 None)
CUSTOM_DATA_DIR = None
FROZEN_EXE_MODE = False
APPLICATION_DIR = ""
PROGRAM_DATA_DIR = ""
DATA_DIR = ""
CONFIG_DIR = ""
CONFIG_FILE = ""
LOG_DIR = ""
DB_DIR = ""
SOUND_DIR = ""
APPROVAL_SOUND_DIR = ""
PRINT_MONITOR_SOUND_DIR = ""
TRANSFER_REGISTRY_FILE = ""
PRINT_REQUEST_QRCODE_FULLPATH = ""
PRINT_REQUEST_ADDED_SOUND = ""
QRCODE_DIR = ""
NETWORK_QR_OUTPUT_DIR = ""
CAPTIVE_QR_OUTPUT_DIR = ""
PRINTJOB_QR_OUTPUT_DIR = ""
QRCODE_LOG_DIR = ""
QRCODE_LOG_FULLPATH = ""


class ArgvParser:
    """명령줄 인자(sys.argv) 파싱을 전담하는 클래스"""

    def __init__(self, args=None):
        self.args = args if args is not None else sys.argv

    def get_custom_data_dir(self) -> str | None:
        """--DATA 파라미터 뒤에 오는 경로 값을 추출합니다."""
        for i in range(len(self.args) - 1):
            if self.args[i].lower() == '--data':
                return self.args[i + 1]
        return None


def get_custom_data_dir() -> str | None:
    """ArgvParser 클래스를 활용하여 커스텀 데이터 경로를 반환하는 함수"""
    parser = ArgvParser()
    return parser.get_custom_data_dir()


# 1. 명령줄 인자로부터 커스텀 데이터 경로 탐색
CUSTOM_DATA_DIR = get_custom_data_dir()

# 2. 실행 환경 및 커스텀 인자에 따른 경로 설정
FROZEN_EXE_MODE = getattr(sys, 'frozen', False)

def refresh_paths(user_data_dir=None):
    """
    명령줄 인자(옵션)나 현재 환경을 기반으로 모든 경로 변수들을 다시 계산하고,
    모듈 전역 변수에 재할당합니다.
    """
    global CUSTOM_DATA_DIR, FROZEN_EXE_MODE, APPLICATION_DIR, PROGRAM_DATA_DIR
    global DATA_DIR, CONFIG_DIR, CONFIG_FILE, LOG_DIR, DB_DIR, SOUND_DIR
    global APPROVAL_SOUND_DIR, PRINT_MONITOR_SOUND_DIR, TRANSFER_REGISTRY_FILE
    global PRINT_REQUEST_QRCODE_FULLPATH, PRINT_REQUEST_ADDED_SOUND
    global QRCODE_DIR, NETWORK_QR_OUTPUT_DIR, CAPTIVE_QR_OUTPUT_DIR, PRINTJOB_QR_OUTPUT_DIR
    global QRCODE_LOG_DIR, QRCODE_LOG_FULLPATH

    # 1. 인자로 직접 문자열이 들어왔다면 그것을 우선 사용 (디버그/테스트용)
    if user_data_dir:
        CUSTOM_DATA_DIR = user_data_dir
    else:
        # 기존 방식대로 명령줄 인자 파싱
        CUSTOM_DATA_DIR = get_custom_data_dir()


    # 2. 실행 환경 및 커스텀 인자에 따른 경로 설정
    FROZEN_EXE_MODE = getattr(sys, 'frozen', False)

    if CUSTOM_DATA_DIR:
        # [경우 A] 사용자가 '--DATA' 인자로 경로를 직접 지정한 경우
        PROGRAM_DATA_DIR = os.path.abspath(CUSTOM_DATA_DIR)
        APPLICATION_DIR = os.path.dirname(sys.executable) if FROZEN_EXE_MODE else os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    else:
        if FROZEN_EXE_MODE:
            # [경우 B-1] .exe 파일로 실행 중이고 인자가 없을 때: 사용자 AppData\Roaming 경로 사용
            APPLICATION_DIR = os.path.dirname(sys.executable)
            APP_DATA_DIR = os.path.expanduser(r'~\AppData\Roaming')
            PROGRAM_DATA_DIR = os.path.join(APP_DATA_DIR, APP_NAME)
        else: 
            # [경우 B-2] .py 스크립트로 개발/실행 중이고 인자가 없을 때: 소스 파일 상위 폴더 기준 사용
            APPLICATION_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            APP_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            PROGRAM_DATA_DIR = APP_DATA_DIR

    # 3. 프로그램 데이터 폴더(DATA_DIR) 및 하위 경로 설정
    DATA_DIR = os.path.join(PROGRAM_DATA_DIR, 'data')

    CONFIG_DIR = os.path.join(DATA_DIR, 'config')
    CONFIG_FILE = APP_NAME + '.ini'

    LOG_DIR = os.path.join(DATA_DIR, 'log')
    DB_DIR = os.path.join(DATA_DIR, 'db')
    SOUND_DIR = os.path.join(DATA_DIR, 'sound')
    APPROVAL_SOUND_DIR = os.path.join(SOUND_DIR, 'approval')
    PRINT_MONITOR_SOUND_DIR = os.path.join(SOUND_DIR, 'print_monitor_sounds')
    TRANSFER_REGISTRY_FILE = os.path.join(DATA_DIR, 'linkbox_transfer_files.json')

    PRINT_REQUEST_QRCODE_FULLPATH = os.path.join(SOUND_DIR, 'print_monitor_sounds')
    PRINT_REQUEST_ADDED_SOUND = os.path.join(DATA_DIR, 'linkbox_transfer_files.json')

    QRCODE_DIR = os.path.join(DATA_DIR, 'qrcode')
    NETWORK_QR_OUTPUT_DIR = os.path.join(QRCODE_DIR, 'network')
    CAPTIVE_QR_OUTPUT_DIR = os.path.join(QRCODE_DIR, 'captive')
    PRINTJOB_QR_OUTPUT_DIR = os.path.join(QRCODE_DIR, 'printjob')

    QRCODE_LOG_DIR = os.path.join(LOG_DIR, 'qrcode')
    QRCODE_LOG_FULLPATH = os.path.join(QRCODE_LOG_DIR, 'qrcode.log')


# 모듈 로드 시 최초 1회 자동 실행
refresh_paths()


from PySide6.QtWidgets import QWidget, QMainWindow


def load_ui_smart(loader: QUiLoader, UI_PATH: str = None, ui_name: str = "main", caller_file: str = None):
    """
    원본 .ui 파일을 거치지 않고, 오직 변환된 파이썬 UI 모듈(ui_*.py)만 임포트하여 로드합니다.
    """
    from Common.log import logd, loge
    from PySide6.QtWidgets import QWidget, QMainWindow

    caller_frame = sys._getframe(1)
    target_widget = caller_frame.f_locals.get('self', None)

    if target_widget is None:
        loge("[오류] load_ui_smart: 클래스 내부의 'self'를 감지할 수 없습니다.")
        return None

    if not caller_file:
        caller_file = caller_frame.f_globals.get('__file__', None)

    if caller_file:
        caller_dir = os.path.dirname(os.path.abspath(caller_file))
        if UI_PATH:
            UI_PATH = os.path.abspath(os.path.join(caller_dir, UI_PATH))
        else:
            UI_PATH = caller_dir

    # 파일 경로로 들어왔을 경우 디렉토리 경로로 변환
    if UI_PATH and os.path.isfile(UI_PATH):
        UI_PATH = os.path.dirname(UI_PATH)

    if ui_name:
        ui_name = os.path.splitext(ui_name)[0]

    module_name = f"ui_{ui_name}"
    
    # 검색 경로(UI_PATH 또는 PyInstaller 임시 폴더)를 sys.path에 등록
    if UI_PATH and UI_PATH not in sys.path:
        sys.path.insert(0, os.path.abspath(UI_PATH))

    # PyInstaller 임시 폴더(_MEIPASS) 지원
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        if sys._MEIPASS not in sys.path:
            sys.path.insert(0, sys._MEIPASS)

    try:
        logd(f"[DEBUG] UI 모듈 임포트 시도: '{module_name}' (경로: {UI_PATH})")
        ui_module = __import__(module_name, fromlist=[f"ui_{ui_name.capitalize()}"])
        
        ui_class_name = next((attr for attr in dir(ui_module) if attr.startswith("Ui_")), None)
        
        if ui_class_name:
            ui_class = getattr(ui_module, ui_class_name)
            
            # 윈도우 타입에 맞춰 QMainWindow 또는 QWidget 동적 생성
            if "MainWindow" in ui_class_name or ui_name.lower() in ["main", "print_shop_app"]:
                loaded_ui = QMainWindow(target_widget)
            else:
                loaded_ui = QWidget(target_widget)
                
            ui_instance = ui_class()
            ui_instance.setupUi(loaded_ui)
            
            target_widget.ui = loaded_ui
            logd(f"UI_LOAD (Python Module 성공) : 모듈명={module_name}, 클래스명={ui_class_name}")
            return loaded_ui
        else:
            loge(f"[오류] 모듈({module_name}) 내에 'Ui_'로 시작하는 클래스가 없습니다.")
            return None
            
    except Exception as e:
        loge(f"[오류] 파이썬 UI 모듈({module_name}) 로드 중 예외 발생: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_ui_file_path(file_path, sub_folder, filename):
    """__file__, 서브 폴더명, 파일명을 인자로 받아 UI 파일의 절대 경로를 반환합니다."""
    current_dir = os.path.dirname(os.path.abspath(file_path))
    ui_path = os.path.join(current_dir, sub_folder, filename)
    if not os.path.exists(ui_path):
        ui_path = os.path.join(current_dir, filename)
    return ui_path


def log_info():
    from .log import logd
    logd("[INFO] APP_NAME        : " + APP_NAME)
    logd("[INFO] APPLICATION_DIR : " + APPLICATION_DIR)
    logd("[INFO] DATA_DIR        : " + DATA_DIR)
