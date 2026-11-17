import os
import sys
from PySide6.QtWidgets import QApplication

# 경로 동적 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

common_version_dir = os.path.join(parent_dir, 'Common', 'Version')
if common_version_dir not in sys.path:
    sys.path.insert(0, common_version_dir)

common_dir = os.path.join(parent_dir, 'Common')
if common_dir not in sys.path:
    sys.path.insert(0, common_dir)

import Common.paths as paths
from Common.log import logd, loge
from github_config_manager import GitHubConfigManager
from printshop_update_manager_github import GitHubSettingsDialog

if __name__ == "__main__":
    logd("PrintShop Update Manager 애플리케이션 실행 시작 [main_app.py]")
    
    # 주요 디렉토리 경로 초기화 및 로그 출력
    #paths.refresh_paths("c:\\temp")

    logd(f"[환경 설정] APPLICATION_DIR: {paths.APPLICATION_DIR}")
    logd(f"[환경 설정] PROGRAM_DATA_DIR: {paths.PROGRAM_DATA_DIR}")
    logd(f"[환경 설정] CUSTOM_DATA_DIR: {paths.CUSTOM_DATA_DIR}")
    logd(f"[환경 설정] DATA_DIR: {paths.DATA_DIR}")    
    logd(f"[환경 설정] CONFIG_DIR: {paths.CONFIG_DIR}")    

    app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
    config_mgr = GitHubConfigManager(config_dir=paths.CONFIG_DIR, filename="github_config.ini")
    dialog = GitHubSettingsDialog(config_mgr)
    dialog.exec()
    logd("PrintShop Update Manager 애플리케이션 종료")
