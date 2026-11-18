import os
import configparser
from datetime import date, datetime, time
from typing import Any, Dict
from dotenv import load_dotenv

from Common.log import logd, loge
from Common.path_mgr import PathMgr
from Common.config import FileConfigManager, ConfigType

load_dotenv()  # .env 파일 로드

DEF_REPO_OWNER = "wizardcori"
DEF_REPO_NAME = "printshop_update"
DEF_GITHUB_TOKEN = os.environ.get("DEF_GITHUB_PRINT_SHOP_SHARE", "")
DEF_VERSION_DIR = "versions_printshop"
DEF_BACKUP_DIR = "printshop_versions_backup"
DEF_OVERWRITE_RELEASE = True
DEF_UDP_PORT = 54321
DEF_HEARTBEAT_INTERVAL = 10
DEF_LAST_UPDATE_DIR = ""


class GitHubConfigManager(FileConfigManager):
    """GitHub 저장소 및 추가 설정값 INI 관리 클래스 (config.py 상속)"""
    file_dir: str = PathMgr.CONFIG_DIR
    file_name: str = "github_config.ini"
    config_encoding: str = "utf-8"

    # config.py의 스키마 구조 및 섹션 매핑 정의
    schema: Dict[str, Dict[str, Any]] = {
        "repo_owner": {"type": ConfigType.STRING, "default": DEF_REPO_OWNER, "section": "GitHub"},
        "repo_name": {"type": ConfigType.STRING, "default": DEF_REPO_NAME, "section": "GitHub"},
        "github_token": {"type": ConfigType.STRING, "default": DEF_GITHUB_TOKEN, "section": "GitHub"},
        "version_dir": {"type": ConfigType.STRING, "default": DEF_VERSION_DIR, "section": "Settings"},
        "overwrite_release": {"type": ConfigType.BOOLEAN, "default": DEF_OVERWRITE_RELEASE, "section": "Settings"},
        "udp_port": {"type": ConfigType.INTEGER, "default": DEF_UDP_PORT, "section": "Settings"},
        "heartbeat_interval": {"type": ConfigType.INTEGER, "default": DEF_HEARTBEAT_INTERVAL, "section": "Settings"},
        "last_update_dir": {"type": ConfigType.STRING, "default": DEF_LAST_UPDATE_DIR, "section": "Settings"},
    }

    def __init__(self, config_dir: str = None, filename: str = "github_config.ini"):
        if config_dir:
            self.file_dir = config_dir
        if filename:
            self.file_name = filename
        super().__init__()

    def _load_and_inject(self):
        """다중 섹션(GitHub, Settings) 지원 INI 로드 및 기본값 주입"""
        if self.file_dir and not os.path.exists(self.file_dir):
            os.makedirs(self.file_dir, exist_ok=True)

        if os.path.exists(self.filepath):
            self.config.read(self.filepath, encoding=self.current_encoding)

        for key, meta in self.schema.items():
            section = meta.get("section", "Settings")
            if not self.config.has_section(section):
                self.config.add_section(section)
            if not self.config.has_option(section, key):
                default_val = meta.get("default", "")
                if isinstance(default_val, (date, datetime, time)):
                    default_val = default_val.isoformat()
                elif isinstance(default_val, (list, tuple)):
                    default_val = str(default_val)
                self.config.set(section, key, str(default_val))

        self.save()

    def get(self, key: str) -> Any:
        """설정값 조회 (다중 섹션 지원)"""
        if key not in self.schema:
            raise KeyError(f"Non-existent configuration key: {key}")
        
        meta = self.schema[key]
        section = meta.get("section", "Settings")
        expected_type = meta.get("type", ConfigType.STRING)
        
        try:
            raw_val = self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return meta.get("default", "")

        if expected_type == ConfigType.BOOLEAN:
            if isinstance(raw_val, bool):
                return raw_val
            return str(raw_val).lower() in ["true", "1", "yes", "on"]
        elif expected_type == ConfigType.INTEGER:
            return int(raw_val)
        elif expected_type == ConfigType.FLOAT:
            return float(raw_val)
        return raw_val

    def set(self, key: str, value: Any):
        """설정값 검증 및 설정 (다중 섹션 지원)"""
        if key not in self.schema:
            raise KeyError(f"Allowed configuration key not found: '{key}'")

        meta = self.schema[key]
        section = meta.get("section", "Settings")
        expected_type = meta.get("type", ConfigType.STRING)

        try:
            if expected_type == ConfigType.BOOLEAN:
                if isinstance(value, str):
                    value = value.lower() in ["true", "1", "yes", "on"]
                else:
                    value = bool(value)
                stored_value = str(value)
            elif expected_type == ConfigType.INTEGER:
                value = int(value)
                stored_value = str(value)
            elif expected_type == ConfigType.FLOAT:
                value = float(value)
                stored_value = str(value)
            else:
                stored_value = str(value)
        except (ValueError, TypeError):
            raise TypeError(f"The value('{value}') for key '{key}' does not match the expected type.")

        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, stored_value)

        if self.auto_save:
            self.save()

    def load_config(self) -> dict:
        """기존 코드 호환성을 위한 딕셔너리 반환 메서드"""
        try:
            cfg = {key: self.get(key) for key in self.schema.keys()}
            logd(f"INI 설정 로드 완료 (Owner: {cfg.get('repo_owner')}, Repo: {cfg.get('repo_name')}, Token유무: {bool(cfg.get('github_token'))})")
            return cfg
        except Exception as e:
            loge(f"INI 설정 로드 중 예외 발생 - 기본값으로 대체합니다: {e}")
            return {key: meta.get("default") for key, meta in self.schema.items()}

    def save_config(self, settings: dict) -> bool:
        """기존 코드 호환성을 위한 딕셔너리 저장 메서드"""
        logd(f"INI 설정 저장 요청: {self.filepath}")
        try:
            for key, val in settings.items():
                if key in self.schema:
                    self.set(key, val)
            self.save()
            logd(f"✅ INI 설정 저장 완료 (Owner: {settings.get('repo_owner')}, Repo: {settings.get('repo_name')})")
            return True
        except Exception as e:
            loge(f"❌ INI 설정 저장 중 예외 발생: {e}")
            return False

    def get_last_update_dir(self) -> str:
        """마지막으로 열었던 업데이트 파일 디렉토리 경로를 반환합니다."""
        try:
            last_dir = self.get("last_update_dir")
            if last_dir and os.path.exists(last_dir):
                return last_dir
        except Exception:
            pass
        return DEF_LAST_UPDATE_DIR

    def save_last_update_dir(self, dir_path: str):
        """마지막으로 열었던 업데이트 파일 디렉토리 경로를 저장합니다."""
        try:
            self.set("last_update_dir", dir_path)
            logd(f"마지막 업데이트 디렉토리 저장됨: {dir_path}")
        except Exception as e:
            loge(f"마지막 디렉토리 저장 중 예외 발생: {e}")