"""Canonical runtime data paths shared by the integrated applications."""

import os
import sys
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget, QMainWindow


class PathMgr:
    """애플리케이션의 실행 환경 및 데이터 경로 설정을 총괄하는 클래스 (클래스 변수 및 클래스 메서드 전용)"""

    APP_NAME = 'PrintShopApp'
    CUSTOM_DATA_DIR = None
    FROZEN_EXE_MODE = False

    SRC_DIR = ""
    PROJECT_ROOT = ""

    # 클래스 변수 선언
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

    @classmethod
    def _parse_custom_data_dir(cls) -> str | None:
        """명령줄 인자(sys.argv)에서 --DATA 파라미터 값을 추출합니다."""
        args = sys.argv
        for i in range(len(args) - 1):
            if args[i].lower() == '--data':
                return args[i + 1]
        return None

    @classmethod
    def refresh_paths(cls, user_data_dir=None, project_root: str | None = None):
        """
        명령줄 인자나 환경에 따라 모든 경로 클래스 변수들을 다시 계산합니다.
        """

        if project_root:
            root_path = os.path.abspath(project_root)
            src_path = os.path.join(root_path, "src")
        else:
            # path_mgr.py 위치 기준으로 프로젝트 루트/src 추론 (필요에 맞게 단계 조정)
            here = os.path.abspath(os.path.dirname(__file__))
            if cls.FROZEN_EXE_MODE:
                root_path = os.path.dirname(sys.executable)
                src_path = os.path.join(root_path, "src")
            else:
                # 예: src/<패키지>/path_mgr.py 구조인 경우
                src_path = os.path.abspath(os.path.join(here, ".."))
                root_path = os.path.abspath(os.path.join(src_path, ".."))

        cls.SRC_DIR = src_path
        cls.PROJECT_ROOT = root_path


        if user_data_dir:
            cls.CUSTOM_DATA_DIR = user_data_dir
        else:
            cls.CUSTOM_DATA_DIR = cls._parse_custom_data_dir()

        cls.FROZEN_EXE_MODE = getattr(sys, 'frozen', False)

        if cls.CUSTOM_DATA_DIR:
            cls.PROGRAM_DATA_DIR = os.path.abspath(cls.CUSTOM_DATA_DIR)
            cls.APPLICATION_DIR = (
                os.path.dirname(sys.executable)
                if cls.FROZEN_EXE_MODE
                else os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            )
        else:
            if cls.FROZEN_EXE_MODE:
                cls.APPLICATION_DIR = os.path.dirname(sys.executable)
                app_data_dir = os.path.expanduser(r'~\AppData\Roaming')
                cls.PROGRAM_DATA_DIR = os.path.join(app_data_dir, cls.APP_NAME)
            else:
                cls.APPLICATION_DIR = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '..')
                )
                app_data_dir = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '..', '..')
                )
                cls.PROGRAM_DATA_DIR = app_data_dir

        if cls.CUSTOM_DATA_DIR:
            cls.DATA_DIR = cls.PROGRAM_DATA_DIR
        else:
            cls.DATA_DIR = os.path.join(cls.PROGRAM_DATA_DIR, 'data')

        cls.CONFIG_DIR = os.path.join(cls.DATA_DIR, 'config')
        cls.CONFIG_FILE = cls.APP_NAME + '.ini'

        cls.LOG_DIR = os.path.join(cls.DATA_DIR, 'log')
        cls.DB_DIR = os.path.join(cls.DATA_DIR, 'db')
        cls.SOUND_DIR = os.path.join(cls.DATA_DIR, 'sound')
        cls.APPROVAL_SOUND_DIR = os.path.join(cls.SOUND_DIR, 'approval')
        cls.print_monitor_sound_dir = os.path.join(
            cls.SOUND_DIR, 'print_monitor_sounds'
        )
        cls.TRANSFER_REGISTRY_FILE = os.path.join(
            cls.DATA_DIR, 'linkbox_transfer_files.json'
        )

        cls.PRINT_REQUEST_QRCODE_FULLPATH = os.path.join(
            cls.SOUND_DIR, 'print_monitor_sounds'
        )
        cls.print_request_added_sound = os.path.join(
            cls.DATA_DIR, 'linkbox_transfer_files.json'
        )

        cls.QRCODE_DIR = os.path.join(cls.DATA_DIR, 'qrcode')
        cls.NETWORK_QR_OUTPUT_DIR = os.path.join(cls.QRCODE_DIR, 'network')
        cls.CAPTIVE_QR_OUTPUT_DIR = os.path.join(cls.QRCODE_DIR, 'captive')
        cls.PRINTJOB_QR_OUTPUT_DIR = os.path.join(cls.QRCODE_DIR, 'printjob')

        cls.QRCODE_LOG_DIR = os.path.join(cls.LOG_DIR, 'qrcode')
        cls.QRCODE_LOG_FULLPATH = os.path.join(
            cls.QRCODE_LOG_DIR, 'qrcode.log'
        )

    @classmethod
    def path_info(cls):
        from Common.log import logd
        logd("[INFO] APP_NAME        : " + cls.APP_NAME)
        logd("[INFO] APPLICATION_DIR : " + cls.APPLICATION_DIR)
        logd("[INFO] DATA_DIR        : " + cls.DATA_DIR)


# 모듈 로드 시 최초 1회 클래스 메서드를 통해 경로 초기화 실행
PathMgr.refresh_paths()