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
    APPDATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    PROGRAM_DATA_DIR = APPDATA_DIR

# 프로그램 데이터 폴더 설정
DATA_DIR = os.path.join(PROGRAM_DATA_DIR, 'data')

print("[INFO] app dir : " + APPLICATION_DIR, flush=True)
print("[INFO] data dir : " + DATA_DIR, flush=True)


CONFIG_DIR = os.path.join(DATA_DIR, 'config')
LOG_DIR = os.path.join(DATA_DIR, 'log')
DB_DIR = os.path.join(DATA_DIR, 'db')
SOUND_DIR = os.path.join(DATA_DIR, 'sound')
APPROVAL_SOUND_DIR = os.path.join(SOUND_DIR, 'approval')
PRINT_MONITOR_SOUND_DIR = os.path.join(SOUND_DIR, 'print_monitor_sounds')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'print_shop_config.ini')
TRANSFER_REGISTRY_FILE = os.path.join(DATA_DIR, 'linkbox_transfer_files.json')
