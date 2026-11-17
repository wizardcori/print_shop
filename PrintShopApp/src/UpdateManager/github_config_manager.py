import os
import configparser

from Common.log import logd, loge

DEF_REPO_OWNER = "wizardcori"
DEF_REPO_NAME = "printshop_update"
DEF_GITHUB_TOKEN = ""
DEF_LOCAL_VERSION_DIR = "versions_printshop"
DEF_BACKUP_DIR = "printshop_versions_backup"
DEF_OVERWRITE_RELEASE = True
DEF_UDP_PORT = 54321
DEF_HEARTBEAT_INTERVAL = 10

import os
from dotenv import load_dotenv

load_dotenv()  # .env 파일 로드
DEF_GITHUB_TOKEN = os.environ.get("DEF_GITHUB_PRINT_SHOP_SHARE")


class GitHubConfigManager:
    """GitHub 저장소 및 추가 설정값 INI 관리 클래스"""
    def __init__(self, config_dir: str = "./data", filename: str = "github_config.ini"):
        self.config_dir = config_dir
        self.filename = filename
        self.ini_path = os.path.join(config_dir, filename)
        
        os.makedirs(self.config_dir, exist_ok=True)
        self.config = configparser.ConfigParser()
        
        self.default_config = {
            "GitHub": {
                "repo_owner": DEF_REPO_OWNER,
                "repo_name": DEF_REPO_NAME,
                "github_token": DEF_GITHUB_TOKEN
            },
            "Settings": {
                "version_dir": DEF_LOCAL_VERSION_DIR,
                "backup_dir": DEF_BACKUP_DIR,
                "overwrite_release": str(DEF_OVERWRITE_RELEASE),
                "udp_port": str(DEF_UDP_PORT),
                "heartbeat_interval": str(DEF_HEARTBEAT_INTERVAL)
            }
        }
        
        if not os.path.exists(self.ini_path):
            logd(f"INI 설정 파일이 없어 기본 설정을 생성합니다: {self.ini_path}")
            self.create_default_config()

    def create_default_config(self):
        try:
            for section, keys in self.default_config.items():
                if not self.config.has_section(section):
                    self.config.add_section(section)
                for key, val in keys.items():
                    self.config.set(section, key, str(val))
                    
            with open(self.ini_path, "w", encoding="utf-8") as f:
                self.config.write(f)
            logd(f"기본 INI 설정 파일 생성 완료: {self.ini_path}")
        except Exception as e:
            loge(f"기본 INI 설정 파일 생성 실패 ({self.ini_path}): {e}")

    def load_config(self) -> dict:
        if not os.path.exists(self.ini_path):
            logd(f"설정 로드 중 파일이 누락되어 재생성합니다: {self.ini_path}")
            self.create_default_config()
            
        try:
            self.config.read(self.ini_path, encoding="utf-8")
            cfg = {
                "repo_owner": self.config.get("GitHub", "repo_owner", fallback=DEF_REPO_OWNER),
                "repo_name": self.config.get("GitHub", "repo_name", fallback=DEF_REPO_NAME),
                "github_token": self.config.get("GitHub", "github_token", fallback=DEF_GITHUB_TOKEN),
                "version_dir": self.config.get("Settings", "version_dir", fallback=DEF_LOCAL_VERSION_DIR),
                "backup_dir": self.config.get("Settings", "backup_dir", fallback=DEF_BACKUP_DIR),
                "overwrite_release": self.config.getboolean("Settings", "overwrite_release", fallback=DEF_OVERWRITE_RELEASE),
                "udp_port": self.config.getint("Settings", "udp_port", fallback=DEF_UDP_PORT),
                "heartbeat_interval": self.config.getint("Settings", "heartbeat_interval", fallback=DEF_HEARTBEAT_INTERVAL)
            }
            logd(f"INI 설정 로드 완료 (Owner: {cfg['repo_owner']}, Repo: {cfg['repo_name']}, Token유무: {bool(cfg['github_token'])})")
            return cfg
        except Exception as e:
            loge(f"INI 설정 로드 중 예외 발생 - 기본값으로 대체합니다: {e}")
            return {
                "repo_owner": DEF_REPO_OWNER, "repo_name": DEF_REPO_NAME,
                "github_token": DEF_GITHUB_TOKEN, "version_dir": DEF_LOCAL_VERSION_DIR,
                "backup_dir": DEF_BACKUP_DIR, "overwrite_release": DEF_OVERWRITE_RELEASE,
                "udp_port": DEF_UDP_PORT, "heartbeat_interval": DEF_HEARTBEAT_INTERVAL
            }

    def save_config(self, settings: dict):
        logd(f"INI 설정 저장 요청: {self.ini_path}")
        try:
            if not self.config.has_section("GitHub"):
                self.config.add_section("GitHub")
            if not self.config.has_section("Settings"):
                self.config.add_section("Settings")
                
            self.config.set("GitHub", "repo_owner", settings.get("repo_owner", DEF_REPO_OWNER))
            self.config.set("GitHub", "repo_name", settings.get("repo_name", DEF_REPO_NAME))
            self.config.set("GitHub", "github_token", settings.get("github_token", DEF_GITHUB_TOKEN))
            self.config.set("Settings", "version_dir", settings.get("version_dir", DEF_LOCAL_VERSION_DIR))
            self.config.set("Settings", "backup_dir", settings.get("backup_dir", DEF_BACKUP_DIR))
            self.config.set("Settings", "overwrite_release", str(settings.get("overwrite_release", DEF_OVERWRITE_RELEASE)))
            self.config.set("Settings", "udp_port", str(settings.get("udp_port", DEF_UDP_PORT)))
            self.config.set("Settings", "heartbeat_interval", str(settings.get("heartbeat_interval", DEF_HEARTBEAT_INTERVAL)))
            
            with open(self.ini_path, "w", encoding="utf-8") as f:
                self.config.write(f)
            logd(f"✅ INI 설정 저장 완료 (Owner: {settings.get('repo_owner')}, Repo: {settings.get('repo_name')})")
            return True
        except Exception as e:
            loge(f"❌ INI 설정 저장 중 예외 발생: {e}")
            return False
