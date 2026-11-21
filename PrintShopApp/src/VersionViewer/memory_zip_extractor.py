import io
import os
import zipfile
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ExtractedExeEntry:
    """메모리상 ZIP에서 추출된 개별 EXE 항목"""
    zip_path: str
    zip_name: str
    inner_path: str          # ZIP 내부 경로 (예: dist/App/App.exe)
    file_name: str           # 실행 파일명 (예: App.exe)
    data: bytes              # EXE 바이너리 데이터
    uncompressed_size: int   # 압축 해제 크기 (bytes)
    compressed_size: int     # 압축 크기 (bytes)


class MemoryZipExtractor:
    """ZIP 파일을 메모리에 로드 및 압축 해제하여 EXE 항목을 추출하는 클래스"""

    def __init__(self, max_single_exe_mb: int = 512):
        self.max_single_exe_bytes = max_single_exe_mb * 1024 * 1024

    def extract_exe_entries_from_file(self, zip_path: str) -> List[ExtractedExeEntry]:
        """디스크의 ZIP 파일을 메모리 버퍼로 읽어 압축 해제 후 EXE 목록 반환"""
        norm_zip = os.path.normpath(zip_path)
        if not os.path.exists(norm_zip) or not zipfile.is_zipfile(norm_zip):
            return []

        with open(norm_zip, "rb") as f:
            zip_bytes = f.read()

        return self.extract_exe_entries_from_bytes(
            zip_bytes=zip_bytes,
            zip_source_path=norm_zip,
        )

    def extract_exe_entries_from_bytes(
        self,
        zip_bytes: bytes,
        zip_source_path: str = "<memory.zip>",
    ) -> List[ExtractedExeEntry]:
        """바이트 스트림 형태의 ZIP을 메모리에서 압축 해제하여 EXE 항목 추출"""
        entries: List[ExtractedExeEntry] = []
        zip_name = os.path.basename(zip_source_path)

        with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                inner_name = info.filename.replace("\\", "/")
                if not inner_name.lower().endswith(".exe"):
                    continue
                if info.file_size > self.max_single_exe_bytes:
                    continue

                exe_bytes = zf.read(info)
                entries.append(
                    ExtractedExeEntry(
                        zip_path=zip_source_path,
                        zip_name=zip_name,
                        inner_path=inner_name,
                        file_name=os.path.basename(inner_name),
                        data=exe_bytes,
                        uncompressed_size=info.file_size,
                        compressed_size=info.compress_size,
                    )
                )

        return entries

    @staticmethod
    def get_zip_memory_footprint(entries: List[ExtractedExeEntry]) -> int:
        """현재 메모리에 유지 중인 추출 EXE 바이트 총량(bytes)"""
        return sum(len(entry.data) for entry in entries)