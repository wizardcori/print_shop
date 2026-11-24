"""Canonical runtime data paths shared by the integrated applications."""

import os
import sys
import threading

from .singleton_base import ThreadSafeSingletonBase


class PathMgr(ThreadSafeSingletonBase):
    """애플리케이션의 실행 환경 및 데이터 경로 설정을 총괄하는 싱글톤 매니저"""

    # 하위 호환성 및 직관적 접근을 위한 기본 클래스 변수
    APP_NAME = "PrintShopApp"
    CUSTOM_DATA_DIR = None
    FROZEN_EXE_MODE = False

    SRC_DIR = ""
    PROJECT_ROOT = ""

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

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.refresh_paths()

    @staticmethod
    def _parse_custom_data_dir() -> str | None:
        """명령줄 인자(sys.argv)에서 --DATA 파라미터 값을 추출합니다."""
        args = sys.argv
        for i in range(len(args) - 1):
            if args[i].lower() == "--data":
                return args[i + 1]
        return None

    @classmethod
    def refresh_paths(
        cls,
        user_data_dir: str | None = None,
        app_name: str | None = None,
        project_root: str | None = None,
    ) -> "PathMgr":
        """명령줄 인자나 주입된 환경에 따라 모든 경로 설정을 다시 계산합니다."""
        instance = cls()

        cls.FROZEN_EXE_MODE = getattr(sys, "frozen", False)

        if app_name is not None:
            cls.APP_NAME = app_name
            try:
                from Common.log import logd
                logd(f"APP_NAME : {cls.APP_NAME}")
            except Exception:
                pass

        if project_root:
            root_path = os.path.abspath(project_root)
            src_path = os.path.join(root_path, "src")
        else:
            here = os.path.abspath(os.path.dirname(__file__))
            if cls.FROZEN_EXE_MODE:
                root_path = os.path.dirname(sys.executable)
                src_path = os.path.join(root_path, "src")
            else:
                src_path = os.path.abspath(os.path.join(here, ".."))
                root_path = os.path.abspath(os.path.join(src_path, ".."))

        cls.SRC_DIR = src_path
        cls.PROJECT_ROOT = root_path

        cls.CUSTOM_DATA_DIR = user_data_dir if user_data_dir else cls._parse_custom_data_dir()

        if cls.CUSTOM_DATA_DIR:
            cls.PROGRAM_DATA_DIR = os.path.abspath(cls.CUSTOM_DATA_DIR)
            cls.APPLICATION_DIR = (
                os.path.dirname(sys.executable)
                if cls.FROZEN_EXE_MODE
                else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            )
            cls.DATA_DIR = cls.PROGRAM_DATA_DIR
        else:
            if cls.FROZEN_EXE_MODE:
                cls.APPLICATION_DIR = os.path.dirname(sys.executable)
                app_data_dir = os.path.expanduser(r"~\AppData\Roaming")
                cls.PROGRAM_DATA_DIR = os.path.join(app_data_dir, cls.APP_NAME)
            else:
                cls.APPLICATION_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                cls.PROGRAM_DATA_DIR = os.path.join(cls.APPLICATION_DIR, "data", cls.APP_NAME)
            cls.DATA_DIR = os.path.join(cls.PROGRAM_DATA_DIR, "data")

        cls.CONFIG_DIR = os.path.join(cls.DATA_DIR, "config")
        cls.CONFIG_FILE = f"{cls.APP_NAME}.ini"

        cls.LOG_DIR = os.path.join(cls.DATA_DIR, "log")
        cls.DB_DIR = os.path.join(cls.DATA_DIR, "db")

        cls.SOUND_DIR = os.path.join(cls.DATA_DIR, "sound")
        cls.APPROVAL_SOUND_DIR = os.path.join(cls.SOUND_DIR, "approval")
        cls.PRINT_MONITOR_SOUND_DIR = os.path.join(cls.SOUND_DIR, "print_monitor_sounds")
        cls.PRINT_REQUEST_ADDED_SOUND = os.path.join(cls.SOUND_DIR, "print_request_added.wav")

        cls.TRANSFER_REGISTRY_FILE = os.path.join(cls.DATA_DIR, "linkbox_transfer_files.json")

        cls.QRCODE_DIR = os.path.join(cls.DATA_DIR, "qrcode")
        cls.PRINT_REQUEST_QRCODE_FULLPATH = os.path.join(cls.QRCODE_DIR, "print_request.png")
        cls.NETWORK_QR_OUTPUT_DIR = os.path.join(cls.QRCODE_DIR, "network")
        cls.CAPTIVE_QR_OUTPUT_DIR = os.path.join(cls.QRCODE_DIR, "captive")
        cls.PRINTJOB_QR_OUTPUT_DIR = os.path.join(cls.QRCODE_DIR, "printjob")

        cls.QRCODE_LOG_DIR = os.path.join(cls.LOG_DIR, "qrcode")
        cls.QRCODE_LOG_FULLPATH = os.path.join(cls.QRCODE_LOG_DIR, "qrcode.log")

        # 싱글톤 인스턴스 속성에도 동일하게 동기화 (PathMgr().DATA_DIR 방식 지원)
        for key, value in cls.__dict__.items():
            if key.isupper():
                setattr(instance, key, value)

        return instance

    @classmethod
    def path_info(cls) -> None:
        print("[INFO] APP_NAME        : " + cls.APP_NAME)
        print("[INFO] APPLICATION_DIR : " + cls.APPLICATION_DIR)
        print("[INFO] DATA_DIR        : " + cls.DATA_DIR)


# 모듈 로드 시 싱글톤 인스턴스 생성 및 기본 경로 1회 초기화
#path_mgr = PathMgr()