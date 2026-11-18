import os
import re
import json
import base64
import zipfile
import shutil
import requests
from packaging import version
from github import Github, Auth, GithubException

from Common.log import logd, loge
import UpdateManager.update_manager_config as update_manager_config
from Common.Version.exe_version_crypto import extract_version_from_exe
from local_version_map import LocalVersionMap, LocalVersionInfo


class GitHubUpdateSyncManager:
    """PyGithub를 활용한 하드디스크와 GitHub 간 동기화 및 릴리스 삭제/관리 클래스"""
    def __init__(self, repo_owner: str, repo_name: str, github_token: str = None, local_versions_dir: str = update_manager_config.DEF_VERSION_DIR, overwrite_release: bool = True):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.github_token = github_token
        self.local_versions_dir = local_versions_dir
        self.overwrite_release = overwrite_release
        
        os.makedirs(self.local_versions_dir, exist_ok=True)
        
        # PyGithub 클라이언트 및 저장소 객체 초기화
        try:
            if self.github_token:
                auth = Auth.Token(self.github_token)
                self.g = Github(auth=auth)
                logd("PyGithub: GitHub 토큰 인증이 활성화되었습니다.")
            else:
                self.g = Github()
                logd("PyGithub: 토큰이 없어 읽기 전용으로 초기화되었습니다.")
            
            self.repo = self.g.get_repo(f"{self.repo_owner}/{self.repo_name}")
            logd(f"PyGithub 저장소 연동 성공: {self.repo_owner}/{self.repo_name}")
        except Exception as e:
            loge(f"PyGithub 초기화 중 예외 발생: {e}")
            self.g = None
            self.repo = None

    def extract_inner_exe_version(self, file_path: str) -> str:
        """ZIP 패키지 내부 .exe 파일의 실제 주입된 버전 추출"""
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
                            logd(f"ZIP 내부 .exe 버전 추출 성공 ({file_path} -> v{match.group(1)})")
                            return match.group(1)
            except Exception as e:
                loge(f"ZIP 내부 .exe 버전 추출 중 예외 발생 ({file_path}): {e}")
            finally:
                if os.path.exists(temp_extract_dir):
                    shutil.rmtree(temp_extract_dir, ignore_errors=True)
        return None

    def scan_local_versions(self, custom_dir: str = None) -> dict:
        target_dir = custom_dir if custom_dir else self.local_versions_dir
        logd(f"로컬 버전 디렉토리 스캔 중: {target_dir}")
        local_versions = {}
        if not os.path.exists(target_dir):
            logd(f"스캔 대상 디렉토리가 존재하지 않습니다: {target_dir}")
            return local_versions

        for file in os.listdir(target_dir):
            file_path = os.path.abspath(os.path.join(target_dir, file))
            if os.path.isfile(file_path) and file.lower().endswith(".zip"):
                match = re.search(r"v?(\d+\.\d+\.\d+)", file)
                if not match:
                    continue
                
                file_ver = match.group(1)
                inner_ver = self.extract_inner_exe_version(file_path)
                is_mismatch = bool(inner_ver and inner_ver != file_ver)
                
                if is_mismatch:
                    loge(f"버전 불일치 감지: 파일명(v{file_ver}) != 내부 EXE(v{inner_ver})")

                local_versions[file_ver] = {
                    "path": file_path,
                    "inner_version": inner_ver,
                    "version_mismatch": is_mismatch
                }
        logd(f"로컬 버전 스캔 완료. 총 {len(local_versions)}개 발견")
        return local_versions

    def fetch_github_releases(self) -> dict:
        github_versions = {}
        if not self.repo:
            loge("GitHub 릴리스 조회 실패: 저장소 객체가 초기화되지 않았습니다.")
            return github_versions
        try:
            logd("GitHub 릴리스 목록 조회 시작...")
            releases = self.repo.get_releases()
            for rel in releases:
                tag_name = rel.tag_name or ""
                ver_match = re.search(r"v?(\d+\.\d+\.\d+)", tag_name)
                if ver_match:
                    ver = ver_match.group(1)
                    for asset in rel.get_assets():
                        if asset.name.endswith(".zip"):
                            github_versions[ver] = {
                                "release_id": rel.id,
                                "asset_id": asset.id,
                                "name": asset.name,
                                "download_url": asset.browser_download_url
                            }
            logd(f"GitHub 릴리스 목록 조회 완료. 총 {len(github_versions)}개 유효 릴리스 확인")
        except Exception as e:
            loge(f"PyGithub 릴리스 목록 조회 중 예외 발생: {e}")
        return github_versions

    def fetch_github_releases_and_assets(self) -> dict:
        github_data = {}
        if not self.repo:
            return github_data
        try:
            releases = self.repo.get_releases()
            for rel in releases:
                tag_name = rel.tag_name or ""
                ver_match = re.search(r"v?(\d+\.\d+\.\d+)", tag_name)
                if ver_match:
                    ver = ver_match.group(1)
                    has_zip = False
                    zip_info = None
                    
                    for asset in rel.get_assets():
                        asset_name = asset.name
                        if asset_name.endswith(".zip"):
                            has_zip = True
                            zip_info = {
                                "release_id": rel.id,
                                "asset_id": asset.id,
                                "name": asset_name,
                                "download_url": asset.browser_download_url
                            }
                            break
                    
                    github_data[ver] = {
                        "has_release": True,
                        "has_zip": has_zip,
                        "release_id": rel.id,
                        "zip_info": zip_info
                    }
        except Exception as e:
            loge(f"PyGithub 릴리스 및 에셋 조회 중 예외 발생: {e}")
        return github_data

    def fetch_github_tags_safe(self) -> set:
        github_tags = set()
        if not self.repo:
            return github_tags
        try:
            tags = self.repo.get_tags()
            for t in tags:
                match = re.search(r"v?(\d+\.\d+\.\d+)", t.name)
                if match:
                    github_tags.add(match.group(1))
        except Exception as e:
            loge(f"PyGithub 태그 조회 중 예외 발생: {e}")
        return github_tags


    def delete_github_release(self, version_str: str) -> bool:
        if not self.github_token or not self.repo:
            loge(f"v{version_str} 원격 릴리스 삭제 실패: 토큰 또는 저장소 객체 누락")
            return False
            
        tag_name = f"v{version_str}"
        logd(f"==================================================")
        logd(f"🗑️ [v{version_str}] 원격 항목 삭제 프로세스 시작")
        logd(f"==================================================")

        deleted_release = False
        deleted_assets_count = 0
        deleted_tag = False

        try:
            # [1단계] 릴리스 및 ZIP 에셋 존재 유무 확인 및 삭제
            try:
                releases = self.repo.get_releases()
                target_release = None
                for rel in releases:
                    if rel.tag_name == tag_name:
                        target_release = rel
                        break

                if target_release:
                    logd(f"  - [Release 발견] ID: {target_release.id}, 제목: {target_release.title}")
                    
                    assets = list(target_release.get_assets())
                    logd(f"  - [ZIP 에셋 검사] 총 {len(assets)}개의 에셋 발견")
                    
                    assets = list(target_release.get_assets())
                    logd(f"  - [ZIP 에셋 검사] 총 {len(assets)}개의 에셋 발견")
                    
                    for asset in assets:
                        asset_name = asset.name
                        try:
                            asset.delete_asset()
                            deleted_assets_count += 1
                            logd(f"    ㄴ [ZIP 에셋 삭제 성공] '{asset_name}'")
                        except Exception as ae:
                            # 💡 422 에러(Immutable) 등으로 개별 삭제가 안 되더라도 에러 대신 에셋 명만 logd로 기록
                            logd(f"    ㄴ [ZIP 에셋 대상] '{asset_name}' (릴리스 삭제 시 함께 정리됨)")

                    try:
                        target_release.delete_release()
                        deleted_release = True
                        logd(f"  - [Release 삭제 성공] v{version_str} 릴리스가 완전히 제거되었습니다.")
                    except Exception as re:
                        loge(f"  - ❌ [Release 삭제 실패 구체적 원인]: {re}")
                else:
                    logd(f"  - [Release 미발견] 삭제할 릴리스가 존재하지 않습니다.")
            except Exception as e:
                loge(f"  - ❌ [Release/Asset 전체 예외]: {e}")

            # [2단계] Git 태그(Tag) 존재 유무 확인 및 삭제
            try:
                ref_path = f"tags/{tag_name}"
                logd(f"  - [Tag 검사] Git 참조 'refs/{ref_path}' 확인 중...")
                ref = self.repo.get_git_ref(ref_path)
                if ref:
                    ref.delete()
                    deleted_tag = True
                    logd(f"  - [Tag 삭제 성공] Git 태그 '{tag_name}' 레퍼런스가 완전히 제거되었습니다.")
            except Exception as te:
                # 💡 GitHub API 예외 객체에서 상세 status 및 data 추출
                err_status = getattr(te, "status", "Unknown")
                err_data = getattr(te, "data", str(te))
                loge(f"  - ❌ [Tag 삭제 오류 상세] Status: {err_status} | Data: {err_data}")

            # [3단계] version.json 갱신 처리
            try:
                contents = self.repo.get_contents("version.json")
                file_sha = contents.sha
                try:
                    remote_json_meta = json.loads(contents.decoded_content.decode("utf-8"))
                except Exception:
                    remote_json_meta = {}

                current_latest = remote_json_meta.get("latest_version")
                if current_latest == version_str:
                    logd(f"  - [version.json 갱신] 삭제된 v{version_str}이(가) 최신 버전이므로 다음 버전 탐색 중...")
                    remaining_releases = self.fetch_github_releases()
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
                        logd(f"  - [version.json 갱신] 새 최신 버전으로 변경: v{next_ver}")
                    else:
                        new_meta = {
                            "latest_version": "",
                            "download_url": "",
                            "changelog": f"Cleared latest version as v{version_str} was deleted"
                        }
                        logd(f"  - [version.json 갱신] 남은 릴리스가 없어 초기화됨")

                    self.repo.update_file(
                        "version.json",
                        f"Update version.json after deleting v{version_str}",
                        json.dumps(new_meta, indent=4, ensure_ascii=False),
                        file_sha,
                        branch="main"
                    )
            except Exception as e:
                logd(f"  - [version.json 갱신 생략/예외]: {e}")

            # 최종 결과 요약 로그 (삭제된 부분만 상세 표시)
            logd(f"--------------------------------------------------")
            logd(f"🎉 [v{version_str}] 삭제 프로세스 완료 요약:")
            logd(f"  - Release 삭제 여부 : {'성공 (O)' if deleted_release else '해당 없음 (X)'}")
            logd(f"  - ZIP 에셋 삭제 개수 : {deleted_assets_count}개")
            logd(f"  - Tag 삭제 여부      : {'성공 (O)' if deleted_tag else '해당 없음 (X)'}")
            logd(f"--------------------------------------------------")

            return deleted_release or deleted_tag
        except Exception as e:
            loge(f"❌ GitHub 릴리스 및 태그 삭제 중 치명적 예외 발생 (v{version_str}): {e}")
            return False

    def auto_sync_remote_version_json(self) -> bool:
        if not self.github_token or not self.repo:
            return False
        try:
            valid_releases = self.fetch_github_releases_and_assets()
            if not valid_releases:
                return False

            sorted_versions = sorted(list(valid_releases.keys()), key=version.parse, reverse=True)
            true_latest_ver = sorted_versions[0]
            true_latest_asset = valid_releases[true_latest_ver]
            
            download_url = true_latest_asset.get("download_url")
            if not download_url:
                asset_name = true_latest_asset.get("name", f"update_v{true_latest_ver}.zip")
                download_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/v{true_latest_ver}/{asset_name}"

            try:
                contents = self.repo.get_contents("version.json")
                current_sha = contents.sha
                remote_meta = json.loads(contents.decoded_content.decode("utf-8"))
                current_remote_ver = remote_meta.get("latest_version")
                if current_remote_ver == true_latest_ver:
                    logd(f"원격 version.json이 이미 최신 버전(v{true_latest_ver})과 일치합니다.")
                    return True
            except Exception:
                current_sha = None

            new_meta = {
                "latest_version": true_latest_ver,
                "download_url": download_url,
                "changelog": f"Auto-synced remote version.json to actual latest release v{true_latest_ver}"
            }

            if current_sha:
                self.repo.update_file(
                    "version.json",
                    f"Auto-sync version.json to match actual release v{true_latest_ver}",
                    json.dumps(new_meta, indent=4, ensure_ascii=False),
                    current_sha,
                    branch="main"
                )
                logd(f"원격 version.json 업데이트 완료 (latest: v{true_latest_ver})")
            else:
                self.repo.create_file(
                    "version.json",
                    f"Create version.json for release v{true_latest_ver}",
                    json.dumps(new_meta, indent=4, ensure_ascii=False),
                    branch="main"
                )
                logd(f"원격 version.json 생성 완료 (latest: v{true_latest_ver})")
            return True
        except Exception as e:
            loge(f"원격 version.json 자동 동기화 중 예외 발생: {e}")
            return False

    def upload_to_github_with_progress(self, version: str, file_path: str, progress_callback=None, cancel_check=None):
        tag_name = f"v{version}"
        release_name = f"Release v{version}"
        
        if not self.repo:
            loge(f"[{version}] 업로드 실패: PyGithub 저장소 객체가 초기화되지 않았습니다.")
            return False, "PyGithub 저장소 객체가 초기화되지 않았습니다."
        
        try:
            logd(f"[{version}] GitHub 업로드 프로세스 시작 -> 파일 경로: {file_path}")
            
            # [단계 1] 로컬 파일 존재 여부 및 크기 검증
            if progress_callback:
                progress_callback(5, f"[{version}] 1단계: 로컬 파일 존재 여부 검증 중...")
            
            if not os.path.exists(file_path):
                err_msg = f"로컬 파일이 존재하지 않습니다: {file_path}"
                loge(f"[{version}] 업로드 오류: {err_msg}")
                return False, err_msg
                
            file_size = os.path.getsize(file_path)
            logd(f"[{version}] 로컬 파일 확인 완료 (크기: {file_size:,} bytes)")

            # [취소 검증]
            if cancel_check and cancel_check():
                logd(f"[{version}] 업로드 중 사용자 취소 감지 (1단계 직후)")
                return False, "사용자에 의해 취소되었습니다."

            # [단계 2] 기존 릴리스 및 태그 중복 확인 및 정리
            if progress_callback:
                progress_callback(20, f"[{version}] 2단계: 기존 릴리스 및 태그 중복 확인 및 정리 중...")
            
            try:
                releases = self.repo.get_releases()
                for rel in releases:
                    if rel.tag_name == tag_name:
                        logd(f"[{version}] 기존 동일 태그 릴리스 발견 (ID: {rel.id}), 에셋 및 릴리스 삭제 중...")
                        for asset in rel.get_assets():
                            asset.delete_asset()
                        rel.delete_release()
                        logd(f"[{version}] 기존 릴리스 삭제 완료")
                        break
            except Exception as e:
                logd(f"[{version}] 기존 릴리스 정리 중 예외 (무시 가능): {e}")

            try:
                ref = self.repo.get_git_ref(f"tags/{tag_name}")
                ref.delete()
                logd(f"[{version}] 기존 Git 태그 참조 삭제 완료")
            except Exception as e:
                logd(f"[{version}] 기존 태그 참조 삭제 중 예외 (무시 가능): {e}")

            # [취소 검증]
            if cancel_check and cancel_check():
                logd(f"[{version}] 업로드 중 사용자 취소 감지 (2단계 직후)")
                return False, "사용자에 의해 취소되었습니다."

            # [단계 3] GitHub 초안 릴리스 생성 (사용된 파라미터 모두 로그 기록)
            if progress_callback:
                progress_callback(35, f"[{version}] 3단계: GitHub 초안 릴리스 생성 중...")
            
            release_params = {
                "tag": tag_name,
                "name": release_name,
                "message": f"Automated release for version {version}",
                "draft": True,
                "prerelease": True
            }
            
            logd(f"[{version}] create_git_release 파라미터 설정값:")
            logd(f"  - tag: {release_params['tag']}")
            logd(f"  - name: {release_params['name']}")
            logd(f"  - message: {release_params['message']}")
            logd(f"  - draft: {release_params['draft']}")
            logd(f"  - prerelease: {release_params['prerelease']}")

            release = self.repo.create_git_release(
                tag=release_params["tag"],
                name=release_params["name"],
                message=release_params["message"],
                draft=release_params["draft"],
                prerelease=release_params["prerelease"]
            )
            
            # 리턴값 검증
            if not release or not hasattr(release, "id"):
                err_msg = "GitHub 초안 릴리스 생성 실패: 유효한 릴리스 객체를 반환받지 못했습니다."
                loge(f"[{version}] ❌ {err_msg}")
                return False, err_msg
                
            logd(f"[{version}] 초안 릴리스 생성 성공 (Release ID: {release.id})")

            # [취소 검증]
            if cancel_check and cancel_check():
                logd(f"[{version}] 업로드 중 사용자 취소 감지 (3단계 직후)")
                return False, "사용자에 의해 취소되었습니다."

            # [단계 4] 파일 에셋 업로드
            if progress_callback:
                progress_callback(50, f"[{version}] 4단계: 파일 에셋 업로드 중... (총 {file_size:,} bytes)")
                
            file_name = os.path.basename(file_path)
            logd(f"[{version}] 에셋 업로드 시작 -> 파일명: {file_name}")
            
            uploaded_asset = release.upload_asset(path=file_path, name=file_name, content_type="application/zip")
            
            # 리턴값 검증
            if not uploaded_asset or not hasattr(uploaded_asset, "id"):
                err_msg = "에셋 업로드 실패: 유효한 에셋 객체를 반환받지 못했습니다."
                loge(f"[{version}] ❌ {err_msg}")
                return False, err_msg
                
            logd(f"[{version}] 에셋 업로드 성공 (Asset ID: {uploaded_asset.id}, 이름: {uploaded_asset.name})")

            # [취소 검증]
            if cancel_check and cancel_check():
                logd(f"[{version}] 업로드 중 사용자 취소 감지 (4단계 직후)")
                return False, "사용자에 의해 취소되었습니다."

         
            # [단계 5] 릴리스 최종 공개 (Publish) 처리 (사용된 파라미터 모두 로그 기록)
            if progress_callback:
                progress_callback(90, f"[{version}] 5단계: 릴리스 최종 공개(Publish) 처리 중...")
            
            update_params = {
                "name": release.title,
                "message": release.body,
                "draft": False,
                "prerelease": release.prerelease
            }

            logd(f"[{version}] update_release 파라미터 설정값:")
            logd(f"  - name: {update_params['name']}")
            logd(f"  - message: {update_params['message']}")
            logd(f"  - draft: {update_params['draft']}")
            logd(f"  - prerelease: {update_params['prerelease']}")

            updated_release = release.update_release(
                name=update_params["name"],
                message=update_params["message"],
                draft=update_params["draft"],
                prerelease=update_params["prerelease"]
            )
           
            if not updated_release:
                err_msg = "릴리스 퍼블리시(Publish) 처리에 실패했습니다."
                loge(f"[{version}] ❌ {err_msg}")
                return False, err_msg
                
            logd(f"[{version}] 릴리스 퍼블리시(Publish) 완료")
            
            if progress_callback:
                progress_callback(100, f"[{version}] 🎉 모든 업로드 프로세스가 성공적으로 완료되었습니다!")
                
            return True, ""
        except Exception as e:
            err_str = str(e)
            loge(f"[{version}] ❌ GitHub 업로드 중 예외 발생: {err_str}")
            return False, err_str

    def download_from_github_with_progress(self, version_str: str, download_url: str, progress_callback=None, cancel_check=None) -> tuple:
        if not self.github_token or not download_url:
            err_msg = "토큰 또는 다운로드 URL이 없습니다."
            loge(f"[v{version_str}] 다운로드 실패: {err_msg}")
            return False, err_msg
        
        try:
            logd(f"[v{version_str}] GitHub 다운로드 시작 -> URL: {download_url}")
            
            # [단계 1] 다운로드 요청 전송 및 응답 상태 검증
            res = requests.get(download_url, headers={"Authorization": f"Bearer {self.github_token}"}, stream=True, timeout=60)
            logd(f"[v{version_str}] 다운로드 응답 상태 코드: {res.status_code}")
            
            if res.status_code != 200:
                err_msg = f"다운로드 실패 응답: {res.status_code} - {res.text}"
                loge(f"[v{version_str}] ❌ {err_msg}")
                return False, err_msg

            os.makedirs(self.local_versions_dir, exist_ok=True)
            dest_path = os.path.join(self.local_versions_dir, f"update_v{version_str}.zip")
            
            total_size = int(res.headers.get('content-length', 0))
            downloaded = 0
            logd(f"[v{version_str}] 파일 저장 경로: {dest_path} (총 크기: {total_size:,} bytes)")
            
            # [단계 2] 스트림 청크 단위 다운로드 및 매 청크마다 취소/상태 검증
            with open(dest_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=8192):
                    if cancel_check and cancel_check():
                        logd(f"[v{version_str}] 다운로드 중 사용자 취소 감지")
                        return False, "사용자에 의해 취소됨"
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            pct = int((downloaded / total_size) * 100)
                            progress_callback(pct, f"[{version_str}] 다운로드 중... ({pct}%) [{downloaded:,}/{total_size:,} bytes]")

            # [단계 3] 파일 다운로드 완료 후 로컬 version.json 갱신 검증
            logd(f"[v{version_str}] 파일 다운로드 완료, 로컬 version.json 갱신 중...")
            self.update_local_version_json(version_str, dest_path)
            
            logd(f"[v{version_str}] 🎉 다운로드 프로세스가 성공적으로 완료되었습니다!")
            return True, ""
        except Exception as e:
            err_str = str(e)
            loge(f"[v{version_str}] ❌ GitHub 다운로드 중 예외 발생: {err_str}")
            return False, f"다운로드 예외: {err_str}"

    def update_local_version_json(self, version_str: str, file_path: str):
        json_path = os.path.join(self.local_versions_dir, "version.json")
        download_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/v{version_str}/{os.path.basename(file_path)}"
        meta_data = {
            "latest_version": version_str,
            "download_url": download_url,
            "changelog": f"Automated sync for version {version_str}"
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=4, ensure_ascii=False)
            logd(f"로컬 version.json 갱신 완료 (최신 버전: v{version_str})")
        except Exception as e:
            loge(f"로컬 version.json 저장 중 예외 발생: {e}")

    def fetch_remote_version_json_raw(self) -> tuple:
        if not self.repo:
            return "PyGithub 저장소 미초기화", None
        try:
            contents = self.repo.get_contents("version.json")
            sha = contents.sha
            content_decoded = contents.decoded_content.decode("utf-8")
            return content_decoded, sha
        except Exception as e:
            return f"원격 version.json 조회 예외: {e}", None

    def force_update_remote_json_manual(self, target_version: str, file_sha: str, custom_download_url: str = None) -> bool:
        if not self.github_token or not file_sha or not self.repo:
            return False
            
        download_url = custom_download_url if custom_download_url else f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/v{target_version}/update_v{target_version}.zip"
        
        meta_data = {
            "latest_version": target_version,
            "download_url": download_url,
            "changelog": f"Manual forced update to v{target_version}"
        }
        
        try:
            self.repo.update_file(
                "version.json",
                f"Force update version.json to v{target_version}",
                json.dumps(meta_data, indent=4, ensure_ascii=False),
                file_sha,
                branch="main"
            )
            return True
        except Exception as e:
            loge(f"원격 version.json 수정 중 예외 발생: {e}")
            return False

    def scan_local_versions_map_object(self, custom_dir: str = None) -> dict:
        target_dir = custom_dir if custom_dir else self.local_versions_dir
        version_map_mgr = LocalVersionMap(target_dir)
        return version_map_mgr.scan_and_build()        

    def update_remote_status_to_map(self, version_map: dict) -> dict:
        """GitHub 원격 릴리스 및 태그 정보를 조회하여 기존 LocalVersionMap의 원격 상태만 업데이트"""
        logd("GitHub 원격 버전 정보 조회 및 맵 업데이트 시작...")
        github_releases_map = self.fetch_github_releases_and_assets()
        github_tags_set = self.fetch_github_tags_safe()

        # 🔍 조회된 원격 버전 목록을 logd로 상세 출력
        logd(f"=== [원격 버전 체크 결과] 발견된 GitHub 릴리스 버전: {list(github_releases_map.keys())} ===")
        for ver, rel_data in github_releases_map.items():
            logd(f"  - 원격 릴리스 v{ver}: has_release={rel_data.get('has_release')}, has_zip={rel_data.get('has_zip')}, zip_info={rel_data.get('zip_info')}")
        logd(f"=== 발견된 GitHub 태그 목록: {list(github_tags_set)} ===")

        # 1. 기존 로컬 맵에 있는 항목들의 원격 정보 갱신
        for filename, info in version_map.items():
            ver = info.version
            # 파일명 버전과 내부 버전이 다를 경우 내부(실제) 버전을 우선하여 원격 매칭
            target_ver = info.inner_version if (info.inner_version and info.inner_version != "0.0.0") else ver
            rel_data = github_releases_map.get(target_ver, {})
            
            info.has_release = rel_data.get("has_release", False)
            info.has_zip = rel_data.get("has_zip", False)
            info.has_tag = target_ver in github_tags_set
            info.github_info = rel_data.get("zip_info")
            
            if info.has_release:
                info.github_version = f"v{target_ver}"
            else:
                info.github_version = "-"

            # 싱크 상태 재판단
            if info.in_local and info.has_release and info.has_zip and info.has_tag:
                info.sync_status = "SYNCED"
            elif info.in_local and not info.has_release and not info.has_tag:
                info.sync_status = "LOCAL_ONLY"
            else:
                info.sync_status = "PARTIAL"

        # 2. 로컬에는 없지만 원격에만 존재하는 버전이 있다면 맵에 추가 반영
        for ver, rel_data in github_releases_map.items():
            dummy_filename = f"remote_v{ver}"
            matched_key = None
            for fname, info in version_map.items():
                if info.version == ver or info.inner_version == ver:
                    matched_key = fname
                    break
            
            if not matched_key:
                has_tag = ver in github_tags_set
                zip_info = rel_data.get("zip_info")
                version_map[dummy_filename] = LocalVersionInfo(
                    filename=dummy_filename,
                    version=ver,
                    local_path="",
                    inner_version=ver,
                    github_version=f"v{ver}",
                    version_mismatch=False,
                    sync_status="REMOTE_ONLY",
                    in_local=False,
                    has_zip=rel_data.get("has_zip", False),
                    has_release=True,
                    has_tag=has_tag,
                    github_info=zip_info
                )
                logd(f"원격에만 존재하는 버전 맵에 추가됨: v{ver}")

        logd("원격 버전 상태 맵 업데이트 완료")
        return version_map


