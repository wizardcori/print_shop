import os
from Common.log import logd, loge

class UpdateManagerWorkHandler:
    """개별 작업(업로드, 다운로드, 동기화 등)의 실행 로직을 담당하는 클래스"""
    
    @staticmethod
    def handle_check_sync(manager, item):
        version_dir = item.get("version_dir")
        status_list = manager.get_version_sync_status(version_dir)
        logd(f"CHECK_SYNC 작업 완료 (결과 {len(status_list)}건)")
        return "CHECK_SYNC", status_list

    @staticmethod
    def handle_fetch_remote_json(manager):
        content, sha = manager.fetch_remote_version_json_raw()
        logd(f"FETCH_REMOTE_JSON 작업 완료 (SHA: {sha})")
        return "FETCH_REMOTE_JSON", {"content": content, "sha": sha}

    @staticmethod
    def handle_force_update_remote_json(manager, item):
        ver_target = item.get("version")
        sha = item.get("sha")
        url = item.get("url")
        success = manager.force_update_remote_json_manual(ver_target, sha, url)
        logd(f"FORCE_UPDATE_REMOTE_JSON 작업 완료 (성공여부: {success})")
        return "FORCE_UPDATE_REMOTE_JSON", success

    @staticmethod
    def handle_auto_sync_json(manager):
        success = manager.auto_sync_remote_version_json()
        logd(f"AUTO_SYNC_JSON 작업 완료 (결과: {success})")
        return "AUTO_SYNC_JSON", success

    @staticmethod
    def handle_upload(manager, item, current_idx, total_tasks, progress_callback, cancel_check):
        ver = item.get("version")
        path = item.get("local_path")
        
        if not path or not os.path.exists(path):
            return False, "로컬 파일 경로가 존재하지 않습니다."

        logd(f"[{current_idx}/{total_tasks}] 업로드 작업 실행: v{ver} ({path})")
        success, err_msg = manager.upload_to_github_with_progress(
            ver, path, progress_callback=progress_callback, cancel_check=cancel_check
        )
        return success, err_msg

    @staticmethod
    def handle_download(manager, item, current_idx, total_tasks, progress_callback, cancel_check):
        ver = item.get("version")
        gh_info = item.get("github_info")
        download_url = gh_info.get("download_url") if gh_info else None
        
        if not download_url:
            return False, "다운로드 URL이 존재하지 않습니다."

        logd(f"[{current_idx}/{total_tasks}] 다운로드 작업 실행: v{ver} ({download_url})")
        success, err_msg = manager.download_from_github_with_progress(
            ver, download_url, progress_callback=progress_callback, cancel_check=cancel_check
        )
        return success, err_msg
