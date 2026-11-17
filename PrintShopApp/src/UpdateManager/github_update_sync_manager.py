import os
import re
import json
import base64
import zipfile
import shutil
import requests
from packaging import version

# logd, loge 임포트 시도 (없을 경우 기본 print 함수로 대체)
from Common.log import logd, loge
import github_config_manager as github_config_manager

from Common.Version.exe_version_crypto import extract_version_from_exe


class GitHubUpdateSyncManager:
    """하드디스크와 GitHub 간 동기화 및 릴리스 삭제/관리 클래스"""
    def __init__(self, repo_owner: str, repo_name: str, github_token: str = None, local_versions_dir: str = github_config_manager.DEF_LOCAL_VERSION_DIR, overwrite_release: bool = True):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.github_token = github_token
        self.local_versions_dir = local_versions_dir
        self.overwrite_release = overwrite_release
        
        os.makedirs(self.local_versions_dir, exist_ok=True)
        self.headers = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            self.headers["Authorization"] = f"Bearer {self.github_token}"
            logd("GitHub 토큰이 설정되었습니다. 인증 헤더가 활성화됩니다.")
        else:
            logd("GitHub 토큰이 설정되지 않았습니다. (읽기 전용 또는 제한된 기능)")

    def extract_version_from_package(self, file_path: str) -> str:
        logd(f"패키지 버전 추출 시작: {file_path}")
        if zipfile.is_zipfile(file_path):
            temp_extract_dir = os.path.join(self.local_versions_dir, "temp_extract")
            os.makedirs(temp_extract_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    exe_files = [name for name in zf.namelist() if name.lower().endswith(".exe")]
                    if exe_files:
                        target_exe = exe_files[0]
                        zf.extract(target_exe, temp_extract_dir)
                        extracted_exe_path = os.path.join(temp_extract_dir, target_exe)
                        
                        raw_ver = extract_version_from_exe(extracted_exe_path)
                        match = re.search(r"v?(\d+\.\d+\.\d+)", raw_ver)
                        if match:
                            detected = match.group(1)
                            logd(f"ZIP 내부 .exe 파일에서 버전 감지 성공: {detected} ({target_exe})")
                            return detected
            except Exception as e:
                loge(f"ZIP 패키지 내부 .exe 버전 추출 중 예외 발생 ({file_path}): {e}")
            finally:
                if os.path.exists(temp_extract_dir):
                    shutil.rmtree(temp_extract_dir, ignore_errors=True)

        filename = os.path.basename(file_path)
        match = re.search(r"v?(\d+\.\d+\.\d+)", filename)
        if match:
            detected = match.group(1)
            logd(f"파일명에서 버전 감지 성공: {detected} ({filename})")
            return detected
            
        loge(f"패키지에서 유효한 버전을 찾을 수 없습니다: {file_path}")
        return "0.0.0"

    def scan_local_versions(self, custom_dir: str = None) -> dict:
        target_dir = custom_dir if custom_dir else self.local_versions_dir
        logd(f"로컬 버전 디렉토리 스캔 중: {target_dir}")
        local_versions = {}
        if not os.path.exists(target_dir):
            logd(f"스캔 대상 디렉토리가 존재하지 않습니다: {target_dir}")
            return local_versions

        for root, dirs, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".zip"):
                    file_path = os.path.abspath(os.path.join(root, file))
                    ver = self.extract_version_from_package(file_path)
                    if ver != "0.0.0":
                        local_versions[ver] = file_path
                        logd(f"로컬 버전 발견: v{ver} -> {file_path}")
        logd(f"로컬 버전스캔 완료. 총 {len(local_versions)}개 발견")
        return local_versions

    def fetch_github_releases(self) -> dict:
        github_versions = {}
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases"
        logd(f"GitHub 릴리스 목록 조회 요청: {api_url}")
        try:
            res = requests.get(api_url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                releases = res.json()
                logd(f"GitHub 릴리스 조회 성공. 총 {len(releases)}개의 릴리스 확인됨")
                for rel in releases:
                    tag_name = rel.get("tag_name", "")
                    ver_match = re.search(r"v?(\d+\.\d+\.\d+)", tag_name)
                    if ver_match:
                        ver = ver_match.group(1)
                        for asset in rel.get("assets", []):
                            if asset.get("name", "").endswith(".zip"):
                                github_versions[ver] = {
                                    "release_id": rel.get("id"),
                                    "asset_id": asset.get("id"),
                                    "name": asset.get("name"),
                                    "download_url": asset.get("browser_download_url")
                                }
                                logd(f"GitHub 릴리스 에셋 등록됨: v{ver} ({asset.get('name')})")
            else:
                loge(f"GitHub 릴리스 조회 실패 - 상태 코드: {res.status_code}, 응답: {res.text}")
        except Exception as e:
            loge(f"GitHub 릴리스 목록 조회 중 예외 발생: {e}")
        return github_versions

    def fetch_github_tags(self) -> set:
        github_tags = set()
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/git/refs/tags"
        logd(f"GitHub 태그 목록 조회 요청: {api_url}")
        try:
            res = requests.get(api_url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                refs = res.json()
                for ref_item in refs:
                    ref_name = ref_item.get("ref", "")  # 예: "refs/tags/v1.3.2"
                    tag_match = re.search(r"v?(\d+\.\d+\.\d+)", ref_name)
                    if tag_match:
                        github_tags.add(tag_match.group(1))
                logd(f"GitHub 태그 조회 성공. 총 {len(github_tags)}개 확인됨")
            else:
                logd(f"GitHub 태그 조회 실패 또는 없음 - 상태 코드: {res.status_code}")
        except Exception as e:
            loge(f"GitHub 태그 목록 조회 중 예외 발생: {e}")
        return github_tags

    def fetch_github_releases_and_assets(self) -> dict:
        """GitHub 릴리스 정보 및 첨부된 .zip 에셋 유무를 정밀 조회"""
        github_data = {}
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases"
        logd(f"GitHub 릴리스 및 에셋 목록 조회 요청: {api_url}")
        try:
            res = requests.get(api_url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                releases = res.json()
                for rel in releases:
                    tag_name = rel.get("tag_name", "")
                    ver_match = re.search(r"v?(\d+\.\d+\.\d+)", tag_name)
                    if ver_match:
                        ver = ver_match.group(1)
                        has_zip = False
                        zip_info = None
                        
                        for asset in rel.get("assets", []):
                            asset_name = asset.get("name", "")
                            if asset_name.endswith(".zip"):
                                has_zip = True
                                zip_info = {
                                    "release_id": rel.get("id"),
                                    "asset_id": asset.get("id"),
                                    "name": asset_name,
                                    "download_url": asset.get("browser_download_url")
                                }
                                break
                        
                        github_data[ver] = {
                            "has_release": True,
                            "has_zip": has_zip,
                            "release_id": rel.get("id"),
                            "zip_info": zip_info
                        }
            else:
                loge(f"GitHub 릴리스 조회 실패 - 상태 코드: {res.status_code}, 응답: {res.text}")
        except Exception as e:
            loge(f"GitHub 릴리스 조회 중 예외 발생: {e}")
        return github_data

    def fetch_github_tags_safe(self) -> set:
        """GitHub 태그 존재 여부 안전 조회 (tags 엔드포인트 활용)"""
        github_tags = set()
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/tags"
        logd(f"GitHub 태그 목록 안전 조회 요청: {api_url}")
        try:
            res = requests.get(api_url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                tags = res.json()
                for t in tags:
                    t_name = t.get("name", "")
                    match = re.search(r"v?(\d+\.\d+\.\d+)", t_name)
                    if match:
                        github_tags.add(match.group(1))
                logd(f"GitHub 태그 조회 성공. 총 {len(github_tags)}개 확인됨")
            else:
                logd(f"GitHub 태그 조회 응답 코드: {res.status_code}")
        except Exception as e:
            loge(f"GitHub 태그 조회 중 예외 발생: {e}")
        return github_tags

    def get_version_sync_status(self, custom_local_dir: str = None) -> list:
        logd("버전 싱크 상태 정밀 분석 시작...")
        local_versions = self.scan_local_versions(custom_local_dir)
        github_releases_map = self.fetch_github_releases_and_assets()
        github_tags_set = self.fetch_github_tags_safe()
        
        all_versions = sorted(
            list(set(local_versions.keys()) | set(github_releases_map.keys()) | set(github_tags_set)), 
            key=version.parse, 
            reverse=True
        )
        sync_status_list = []
        
        for ver in all_versions:
            in_local = ver in local_versions
            rel_data = github_releases_map.get(ver, {})
            has_release = rel_data.get("has_release", False)
            has_zip = rel_data.get("has_zip", False)
            has_tag = ver in github_tags_set
            
            # 싱크 상태 결정 규칙
            if in_local and has_release and has_zip and has_tag:
                status = "SYNCED"
            elif in_local and not has_release and not has_tag:
                status = "ONLY_LOCAL"
            else:
                status = "PARTIAL"
                
            logd(f"버전 v{ver} 분석 -> Local: {in_local}, Release: {has_release}, ZIP: {has_zip}, Tag: {has_tag} [{status}]")
                
            sync_status_list.append({
                "version": ver,
                "in_local": in_local,
                "has_release": has_release,
                "has_zip": has_zip,
                "has_tag": has_tag,
                "local_path": local_versions.get(ver),
                "github_info": rel_data.get("zip_info"),
                "sync_status": status
            })
        logd(f"버전 싱크 상태 정밀 분석 완료. 총 {len(sync_status_list)}개 버전 검사됨")
        return sync_status_list

    def delete_github_release(self, version_str: str) -> bool:
        if not self.github_token:
            loge(f"토큰이 없어 v{version_str} 원격 릴리스를 삭제할 수 없습니다.")
            return False
            
        tag_name = f"v{version_str}"
        release_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases"
        tag_ref_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/git/refs/tags/{tag_name}"
        json_api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/version.json"
        
        logd(f"GitHub 릴리스 및 태그 삭제 시도: {tag_name}")
        deleted_successfully = False
        
        try:
            # 1. 릴리스(Release) 정보 조회 및 삭제
            tag_check_res = requests.get(f"{release_url}/tags/{tag_name}", headers=self.headers, timeout=10)
            if tag_check_res.status_code == 200:
                rel_id = tag_check_res.json().get("id")
                del_res = requests.delete(f"{release_url}/{rel_id}", headers=self.headers, timeout=10)
                if del_res.status_code in [200, 204]:
                    logd(f"✅ GitHub 릴리스 삭제 성공: {tag_name} (ID: {rel_id})")
                    deleted_successfully = True
                else:
                    loge(f"릴리스 삭제 API 호출 실패 - 상태 코드: {del_res.status_code}, 응답: {del_res.text}")
            else:
                logd(f"삭제할 릴리스 태그를 찾지 못했거나 이미 없음: {tag_name} (상태 코드: {tag_check_res.status_code})")

            # 2. 고아 Git 태그(Ref) 잔여 여부 확인 및 강제 삭제
            tag_ref_res = requests.get(tag_ref_url, headers=self.headers, timeout=10)
            if tag_ref_res.status_code == 200:
                del_tag_res = requests.delete(tag_ref_url, headers=self.headers, timeout=10)
                if del_tag_res.status_code in [200, 204]:
                    logd(f"✅ GitHub Git 태그 레퍼런스 삭제 성공: {tag_name}")
                    deleted_successfully = True
                else:
                    loge(f"Git 태그 레퍼런스 삭제 실패 - 상태 코드: {del_tag_res.status_code}, 응답: {del_tag_res.text}")
            else:
                logd(f"삭제할 Git 태그 레퍼런스가 존재하지 않음: {tag_name}")

            # 3. 원격 version.json 검사 및 삭제된 버전일 경우 이전 버전으로 갱신/롤백
            json_res = requests.get(json_api_url, headers=self.headers, timeout=10)
            if json_res.status_code == 200:
                json_data = json_res.json()
                file_sha = json_data.get("sha")
                try:
                    decoded_content = base64.b64decode(json_data["content"]).decode("utf-8")
                    remote_json_meta = json.loads(decoded_content)
                except Exception:
                    remote_json_meta = {}

                current_latest = remote_json_meta.get("latest_version")
                if current_latest == version_str:
                    logd(f"방금 삭제한 버전(v{version_str})이 원격 version.json의 최신 버전으로 지정되어 있습니다. 대체 버전을 검색합니다.")
                    
                    # 남아있는 릴리스 목록 다시 조회
                    remaining_releases = self.fetch_github_releases() # 또는 릴리스/태그 목록
                    remaining_versions = sorted(list(remaining_releases.keys()), key=version.parse, reverse=True)
                    
                    if remaining_versions:
                        next_ver = remaining_versions[0]
                        next_asset = remaining_releases[next_ver]
                        next_download_url = next_asset.get("download_url") or f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/v{next_ver}/{next_asset.get('name', f'update_v{next_ver}.zip')}"
                        
                        new_meta = {
                            "latest_version": next_ver,
                            "download_url": next_download_url,
                            "changelog": f"Rolled back to v{next_ver} due to deletion of v{version_str}"
                        }
                        logd(f"차상위 버전(v{next_ver})으로 원격 version.json 갱신 중...")
                    else:
                        # 더 이상 남은 릴리스가 없는 경우 초기화 또는 빈 값 처리
                        new_meta = {
                            "latest_version": "",
                            "download_url": "",
                            "changelog": f"Cleared latest version as v{version_str} was deleted"
                        }
                        logd("남아있는 릴리스가 없어 version.json의 최신 버전 정보를 비웁니다.")

                    encoded_new_content = base64.b64encode(json.dumps(new_meta, indent=4, ensure_ascii=False).encode("utf-8")).decode("utf-8")
                    update_payload = {
                        "message": f"Update version.json after deleting v{version_str}",
                        "content": encoded_new_content,
                        "branch": "main",
                        "sha": file_sha
                    }
                    put_res = requests.put(json_api_url, headers=self.headers, json=update_payload, timeout=10)
                    if put_res.status_code in [200, 201]:
                        logd("✅ 원격 version.json이 삭제된 버전에 맞춰 성공적으로 갱신되었습니다.")
                    else:
                        loge(f"❌ 원격 version.json 갱신 실패: {put_res.status_code} - {put_res.text}")

            return deleted_successfully
        except Exception as e:
            loge(f"GitHub 릴리스 및 태그 삭제 중 예외 발생 (v{version_str}): {e}")
            return False
### 📌 동작 방식
# 1. 사용자가 특정 버전(예: `v1.3.2`)을 원격에서 삭제합니다.
# 2. 릴리스와 Git 태그 레퍼런스가 정상적으로 삭제됩니다.
# 3. 곧바로 원격 저장소의 `version.json`을 읽어와서, 방금 삭제한 버전이 `latest_version`으로 등록되어 있었는지 확인합니다.
# 4. 맞다면, **남아있는 다른 릴리스 중 가장 최신 버전(예: `v1.3.1`)을 자동으로 찾아 `version.json`을 해당 버전으로 갱신(롤백)**합니다. 만약 더 이상 남은 릴리스가 없다면 필드를 안전하게 비워줍니다[cite: 7].


    def auto_sync_remote_version_json(self) -> bool:
        """GitHub에 실제 존재하는 유효한 릴리스들을 기반으로 원격 version.json을 자동 동기화"""
        if not self.github_token:
            loge("토큰이 없어 원격 version.json을 자동 동기화할 수 없습니다.")
            return False

        json_api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/version.json"
        logd("원격 version.json 자동 동기화 프로세스 시작...")

        try:
            # 1. GitHub의 실제 유효한 릴리스 및 에셋 목록 조회 (ZIP 에셋이 있는 버전 기준)
            valid_releases = self.fetch_github_releases_and_assets()
            if not valid_releases:
                logd("GitHub에 유효한 릴리스(ZIP 에셋 포함)가 존재하지 않습니다.")
                return False

            # 버전을 내림차순(최신순)으로 정렬
            sorted_versions = sorted(list(valid_releases.keys()), key=version.parse, reverse=True)
            true_latest_ver = sorted_versions[0]
            true_latest_asset = valid_releases[true_latest_ver]
            
            # 다운로드 URL 확정
            download_url = true_latest_asset.get("download_url")
            if not download_url:
                asset_name = true_latest_asset.get("name", f"update_v{true_latest_ver}.zip")
                download_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/v{true_latest_ver}/{asset_name}"

            # 2. 현재 원격 version.json 파일 및 SHA 조회
            current_sha = None
            current_remote_ver = None
            
            res = requests.get(json_api_url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                json_data = res.json()
                current_sha = json_data.get("sha")
                try:
                    decoded_content = base64.b64decode(json_data["content"]).decode("utf-8")
                    remote_meta = json.loads(decoded_content)
                    current_remote_ver = remote_meta.get("latest_version")
                except Exception:
                    pass

            # 3. 불일치할 경우에만 자동 갱신 수행
            if current_remote_ver == true_latest_ver and current_sha:
                logd(f"원격 version.json이 이미 최신 릴리스(v{true_latest_ver})와 일치합니다. 동기화 불필요.")
                return True

            logd(f"원격 version.json 불일치 감지 (현재 기록된 버전: {current_remote_ver} -> 실제 최신 릴리스: v{true_latest_ver}). 갱신을 진행합니다.")

            new_meta = {
                "latest_version": true_latest_ver,
                "download_url": download_url,
                "changelog": f"Auto-synced remote version.json to actual latest release v{true_latest_ver}"
            }

            encoded_content = base64.b64encode(json.dumps(new_meta, indent=4, ensure_ascii=False).encode("utf-8")).decode("utf-8")
            payload = {
                "message": f"Auto-sync version.json to match actual release v{true_latest_ver}",
                "content": encoded_content,
                "branch": "main",
            }
            if current_sha:
                payload["sha"] = current_sha

            put_res = requests.put(json_api_url, headers=self.headers, json=payload, timeout=10)
            if put_res.status_code in [200, 201]:
                logd(f"✅ 원격 version.json 자동 동기화 성공! (최신 버전: v{true_latest_ver})")
                return True
            else:
                loge(f"❌ 원격 version.json 자동 동기화 실패: {put_res.status_code} - {put_res.text}")
                return False

        except Exception as e:
            loge(f"원격 version.json 자동 동기화 중 예외 발생: {e}")
            return False

# ### 💡 활용 방법
# 이 메서드를 아래와 같은 타이밍에 호출하도록 연결해 두면 프로그램이 알아서 원격 상태를 검사하고 `version.json`을 릴리스에 맞게 척척 수정해 줍니다.

# 1. **싱크 상태를 확인할 때 (`check_sync_status_async` 등 실행 시)** 백그라운드나 필요에 따라 호출하여 자동으로 정렬
# 2. **원격 릴리스를 삭제하거나 업로드 완료한 직후** 
# 3. 메인 UI에 **[원격 version.json 자동 정렬/동기화]** 버튼을 하나 만들어 연결[cite: 7]


    def upload_to_github_with_progress(self, version: str, file_path: str, progress_callback=None, cancel_check=None):
        """
        GitHub 릴리스 및 태그 충돌 방지 로직이 포함된 안전한 업로드 메서드
        """
        tag_name = f"v{version}"
        release_name = f"Release v{version}"
        
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json"
        }
        
        base_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases"
        
        try:
            if progress_callback:
                progress_callback(10, f"[{version}] 원격 기존 릴리스 및 태그 존재 여부 확인 중...")
            
            # 1. 이미 존재하는 릴리스가 있는지 태그(tag_name)로 조회
            tag_lookup_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/tags/{tag_name}"
            res = requests.get(tag_lookup_url, headers=headers)
            
            if res.status_code == 200:
                # 이미 동일한 태그/릴리스가 존재함 -> Immutable 422 에러 방지를 위해 기존 릴리스 사전 삭제 처리
                existing_release = res.json()
                release_id = existing_release.get("id")
                logd(f"[{version}] 원격에 이미 존재하는 릴리스(ID: {release_id}) 및 태그 발견. 사전 정리 진행...")
                
                if progress_callback:
                    progress_callback(20, f"[{version}] 기존 릴리스 정리 중 (Immutable 에러 방지)...")
                
                # 릴리스 삭제
                del_rel_res = requests.delete(f"{base_url}/{release_id}", headers=headers)
                
                # 연동된 Git Ref(태그) 삭제 추가 요청
                tag_del_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/git/refs/tags/{tag_name}"
                requests.delete(tag_del_url, headers=headers)
                
                logd(f"[{version}] 기존 릴리스 및 태그 정리 완료.")

            if cancel_check and cancel_check():
                return False, "사용자에 의해 취소되었습니다."

            # 2. [3단계-1 & 2] 원격 GitHub 릴리스(Release) 및 태그(Tag) 생성 로그 추가 및 실행
            if progress_callback:
                progress_callback(30, f"[{version}] 1. 원격 GitHub 릴리스 및 2. 태그({tag_name}) 생성 중...")
            
            logd(f"[{version}] GitHub API 호출: 신규 릴리스 및 태그 생성 시도 (tag: {tag_name})")
            
            release_payload = {
                "tag_name": tag_name,
                "name": release_name,
                "body": f"Automated release for version {version}",
                "draft": False,
                "prerelease": False
            }
            
            create_res = requests.post(base_url, headers=headers, json=release_payload)
            
            if create_res.status_code not in (200, 201):
                err_json = create_res.json()
                err_msg = err_json.get("message", "Unknown error")
                loge(f"[{version}] 릴리스 생성 실패 (Status {create_res.status_code}): {err_msg}")
                return False, f"릴리스 생성 실패: {create_res.status_code} - {json.dumps(err_json)}"
            
            release_data = create_res.json()
            upload_url_template = release_data.get("upload_url")  # '{?name,label}' 형태 포함
            upload_url = upload_url_template.split("{")[0]
            
            logd(f"[{version}] ✅ 1. 원격 릴리스 생성 성공 및 2. 태그({tag_name}) 등록 완료 (Upload URL 확보)")

            if cancel_check and cancel_check():
                return False, "사용자에 의해 취소되었습니다."

            # 3. [4단계] 빌드된 에셋(Asset) 파일 업로드
            if progress_callback:
                progress_callback(50, f"[{version}] 3. 압축 파일 에셋 업로드 중...")
                
            file_name = os.path.basename(file_path)
            asset_upload_url = f"{upload_url}?name={file_name}"
            
            headers_asset = headers.copy()
            headers_asset["Content-Type"] = "application/zip" # 파일 형식에 맞게 조정
            
            with open(file_path, "rb") as f:
                file_data = f.read()
                
            asset_res = requests.post(asset_upload_url, headers=headers_asset, data=file_data)
            
            if asset_res.status_code not in (200, 201):
                err_msg = asset_res.text
                loge(f"[{version}] 에셋 업로드 실패: {err_msg}")
                return False, f"에셋 업로드 실패: {asset_res.status_code} - {err_msg}"
                
            logd(f"[{version}] ✅ 에셋 업로드 성공: {file_name}")
            if progress_callback:
                progress_callback(100, f"[{version}] 업로드 완료!")
                
            return True, ""

        except Exception as e:
            loge(f"[{version}] 업로드 프로세스 중 예외 발생: {str(e)}")
            return False, str(e)

    def download_from_github_with_progress(self, version_str: str, download_url: str, progress_callback=None, cancel_check=None) -> tuple:
        if not self.github_token or not download_url:
            err_msg = "토큰 또는 다운로드 URL이 없습니다."
            loge(err_msg)
            return False, err_msg
        
        logd(f"GitHub 다운로드 시작: v{version_str} <- {download_url}")
        try:
            res = requests.get(download_url, headers=self.headers, stream=True, timeout=60)
            if res.status_code == 200:
                target_folder = os.path.join(self.local_versions_dir, f"v{version_str}")
                os.makedirs(target_folder, exist_ok=True)
                dest_path = os.path.join(target_folder, f"update_v{version_str}.zip")
                
                total_size = int(res.headers.get('content-length', 0))
                downloaded = 0
                logd(f"다운로드 대상 경로 지정됨: {dest_path} (총 크기: {total_size} bytes)")
                
                with open(dest_path, "wb") as f:
                    for chunk in res.iter_content(chunk_size=8192):
                        if cancel_check and cancel_check():
                            logd(f"다운로드 중 취소 감지됨: v{version_str}")
                            return False, "사용자에 의해 취소됨"
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and progress_callback:
                                pct = int((downloaded / total_size) * 100)
                                progress_callback(pct, f"[{version_str}] 다운로드 중... ({pct}%)")
                                
                logd(f"✅ 버전 v{version_str} 다운로드 완료!")
                self.update_local_version_json(version_str, dest_path)
                return True, ""
            
            err_msg = f"다운로드 실패 응답: {res.status_code}"
            loge(err_msg)
            return False, err_msg
        except Exception as e:
            err_msg = f"다운로드 예외: {e}"
            loge(err_msg)
            return False, err_msg

    def update_local_version_json(self, version_str: str, file_path: str):
        json_path = os.path.join(self.local_versions_dir, "version.json")
        download_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/v{version_str}/{os.path.basename(file_path)}"
        meta_data = {
            "latest_version": version_str,
            "download_url": download_url,
            "changelog": f"Automated sync for version {version_str}"
        }
        logd(f"로컬 version.json 갱신 중: {json_path} (버전: {version_str})")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=4, ensure_ascii=False)
            logd("로컬 version.json 갱신 성공")
        except Exception as e:
            loge(f"로컬 version.json 저장 중 예외 발생: {e}")

    def fetch_remote_version_json_raw(self) -> tuple:
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/version.json"
        logd(f"원격 version.json 조회 요청: {api_url}")
        try:
            res = requests.get(api_url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                sha = data.get("sha")
                content_decoded = base64.b64decode(data["content"]).decode("utf-8")
                logd(f"원격 version.json 조회 및 디코딩 성공 (SHA: {sha})")
                return content_decoded, sha
            
            err_msg = f"조회 실패: {res.status_code}"
            loge(err_msg)
            return err_msg, None
        except Exception as e:
            err_msg = f"원격 version.json 조회 예외: {e}"
            loge(err_msg)
            return err_msg, None

    def force_update_remote_json_manual(self, target_version: str, file_sha: str, custom_download_url: str = None) -> bool:
        if not self.github_token or not file_sha:
            loge("토큰 또는 SHA 값이 없어 원격 version.json을 수정할 수 없습니다.")
            return False
            
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/version.json"
        download_url = custom_download_url if custom_download_url else f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/v{target_version}/update_v{target_version}.zip"
        
        meta_data = {
            "latest_version": target_version,
            "download_url": download_url,
            "changelog": f"Manual forced update to v{target_version}"
        }
        
        encoded_content = base64.b64encode(json.dumps(meta_data, indent=4, ensure_ascii=False).encode("utf-8")).decode("utf-8")
        payload = {
            "message": f"Force update version.json to v{target_version}",
            "content": encoded_content,
            "branch": "main",
            "sha": file_sha
        }
        
        logd(f"원격 version.json 강제 수정 요청 중... (목표 버전: {target_version})")
        try:
            put_res = requests.put(api_url, headers=self.headers, json=payload, timeout=10)
            logd(f"GitHub 응답 코드: {put_res.status_code}, 메시지: {put_res.text}")
            success = put_res.status_code in [200, 201]
            if success:
                logd("✅ 원격 version.json 강제 수정 성공!")
            else:
                loge(f"❌ 원격 version.json 강제 수정 실패 (상태 코드: {put_res.status_code})")
            return success
        except Exception as e:
            loge(f"원격 version.json 수정 중 예외 발생: {e}")
            return False
