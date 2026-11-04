"""Canonical runtime data paths shared by the integrated applications."""

import os
import sys

APP_NAME = 'PrintShopApp'

# 실행 환경에 따라 APPDATA_DIR 설정
if getattr(sys, 'frozen', False):
    # 1. .exe 파일로 실행 중일 때: AppData\Roaming 경로 사용
    RUN_ENV_EXE = True
else:
    # 2. .py 스크립트로 개발/실행 중일 때: 현재 소스 파일이 있는 폴더 사용
    RUN_ENV_EXE = False
  
if RUN_ENV_EXE == True:
    APPLICATION_DIR = os.path.dirname(sys.executable)
    # 1. .exe 파일로 실행 중일 때: AppData\Roaming 경로 사용
    APPDATA_DIR = os.path.expanduser(r'~\AppData\Roaming')
    PROGRAM_DATA_DIR = os.path.join(APPDATA_DIR, APP_NAME)
else: 
    APPLICATION_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    # 2. .py 스크립트로 개발/실행 중일 때: 현재 소스 파일이 있는 폴더 사용
    APPDATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    PROGRAM_DATA_DIR = APPDATA_DIR

# 프로그램 데이터 폴더 설정
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

DATA_DIR = os.path.join(PROGRAM_DATA_DIR, 'data')
QRCODE_DIR = os.path.join(DATA_DIR, 'qrcode')
NETWORK_QR_OUTPUT_DIR = os.path.join(QRCODE_DIR, 'network')
CAPTIVE_QR_OUTPUT_DIR = os.path.join(QRCODE_DIR, 'captive')
PRINTJOB_QR_OUTPUT_DIR = os.path.join(QRCODE_DIR, 'printjob')


QRCODE_LOG_DIR = os.path.join(LOG_DIR, 'qrcode')
QRCODE_LOG_FULLPATH = os.path.join(QRCODE_LOG_DIR, 'qrcode.log')


def get_ui_file_path(file_path, sub_folder, filename):
    """
    __file__, 서브 폴더명, 파일명을 인자로 받아 UI 파일의 절대 경로를 반환합니다.
    """
    current_dir = os.path.dirname(os.path.abspath(file_path))
    ui_path = os.path.join(current_dir, sub_folder, filename)
    if not os.path.exists(ui_path):
        ui_path = os.path.join(current_dir, filename)
    return ui_path

def get_ui_file_path(file_path, sub_folder, filename):
    # 💡 함수 내부에서 필요한 시점에 임포트 (순환 참조 방지)
    from .log import logd
    logd("[INFO] APP_NAME        : " + APP_NAME)
    logd("[INFO] APPLICATION_DIR : " + APPLICATION_DIR)
    logd("[INFO] DATA_DIR        : " + DATA_DIR)
