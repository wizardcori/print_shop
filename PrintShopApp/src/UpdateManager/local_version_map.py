import os
import re
import zipfile
import shutil
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional
from Common.log import logd, loge
from Common.Version.exe_version_crypto import extract_version_from_exe

@dataclass
class LocalVersionInfo:
    """개별 로컬 버전 파일의 메타데이터 및 검증 상태를 관리하는 데이터 클래스"""
    filename: str                      # 파일명 (Key 역할)
    version: str                       # 로컬 버전 (Local 버전)
    local_path: str                    # 로컬 파일 절대 경로
    inner_version: str = "0.0.0"       # .exe 내부에서 추출한 실제 버전
    github_version: str = "-"          # 🌐 GitHub 원격 버전 컬럼 추가
    version_mismatch: bool = False     # 버전 불일치 여부
    sync_status: str = "LOCAL_ONLY"    # 싱크 상태
    in_local: bool = True              # 로컬 존재 여부
    has_zip: bool = True               # ZIP 파일 여부
    has_release: bool = False          # 원격 릴리스 유무
    has_tag: bool = False              # 원격 태그 유무
    github_info: Optional[dict] = None # GitHub 관련 에셋 정보

    def to_dict(self) -> dict:
        return asdict(self)    


class LocalVersionMap:
    """파일명(Key)을 기준으로 로컬 버전 정보를 맵(Dictionary) 형태로 관리하는 클래스"""
    def __init__(self, versions_dir: str):
        self.versions_dir = versions_dir
        self.version_map: Dict[str, LocalVersionInfo] = {}

    def scan_and_build(self) -> Dict[str, LocalVersionInfo]:
        """지정된 디렉토리를 스캔하여 버전 맵을 구축"""
        logd(f"로컬 버전 맵 스캔 시작: {self.versions_dir}")
        self.version_map.clear()

        if not os.path.exists(self.versions_dir):
            return self.version_map

        for filename in os.listdir(self.versions_dir):
            file_path = os.path.abspath(os.path.join(self.versions_dir, filename))
            if os.path.isfile(file_path) and filename.lower().endswith(('.zip', '.exe')):
                match = re.search(r"v?(\d+\.\d+\.\d+)", filename)
                file_version = match.group(1) if match else "0.0.0"
                
                inner_version = file_version
                version_mismatch = False
                
                try:
                    if filename.lower().endswith('.zip'):
                        with zipfile.ZipFile(file_path, 'r') as zf:
                            exe_files = [f for f in zf.namelist() if f.lower().endswith('.exe')]
                            if exe_files:
                                temp_extracted = zf.extract(exe_files[0], path=self.versions_dir)
                                raw_inner = extract_version_from_exe(temp_extracted)
                                inner_match = re.search(r"v?(\d+\.\d+\.\d+)", raw_inner)
                                if inner_match:
                                    inner_version = inner_match.group(1)
                                if os.path.exists(temp_extracted):
                                    os.remove(temp_extracted)
                    elif filename.lower().endswith('.exe'):
                        raw_inner = extract_version_from_exe(file_path)
                        inner_match = re.search(r"v?(\d+\.\d+\.\d+)", raw_inner)
                        if inner_match:
                            inner_version = inner_match.group(1)
                            
                    if file_version != "0.0.0" and inner_version != "0.0.0" and file_version != inner_version:
                        version_mismatch = True
                except Exception as e:
                    loge(f"로컬 파일 버전 검사 중 오류 ({filename}): {e}")

                # 🔑 파일명을 Key로 하는 데이터 클래스 인스턴스 생성 및 저장
                self.version_map[filename] = LocalVersionInfo(
                    filename=filename,
                    version=file_version,
                    local_path=file_path,
                    inner_version=inner_version,
                    version_mismatch=version_mismatch,
                    has_zip=filename.lower().endswith('.zip')
                )
                
        logd(f"로컬 버전 맵 구축 완료. 총 {len(self.version_map)}개 파일 관리 중")
        return self.version_map

    def get(self, filename: str) -> Optional[LocalVersionInfo]:
        return self.version_map.get(filename)

    def get_as_list(self) -> list:
        """기존 테이블 반영용 리스트 형태로 변환"""
        return [info.to_dict() for info in self.version_map.values()]