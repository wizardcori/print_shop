import ctypes
import datetime
import os
import tempfile
from typing import Dict, Optional, Tuple
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTableWidgetItem

from Common.log import logd
from Common.Version.exe_version_crypto import (
    DESCRIPTOR_VERSION as CRYPTO_DESCRIPTOR_VERSION,
    extract_version_from_exe,
    verify_and_read_exe_metadata,
)


def _query_win32_version_strings(file_path: str) -> Dict[str, str]:
    """Windows PE 리소스(StringFileInfo)에서 상세 버전 문자열 속성을 모두 추출"""
    fields = [
        "FileVersion",
        "ProductVersion",
        "CompanyName",
        "FileDescription",
        "ProductName",
        "InternalName",
        "OriginalFilename",
        "LegalCopyright",
        "Comments",
        "PrivateBuild",
        "SpecialBuild",
    ]
    result: Dict[str, str] = {k: "" for k in fields}

    if os.name != "nt" or not os.path.exists(file_path):
        return result

    try:
        version_dll = ctypes.windll.version
        size = version_dll.GetFileVersionInfoSizeW(file_path, None)
        if not size:
            return result

        buf = ctypes.create_string_buffer(size)
        if not version_dll.GetFileVersionInfoW(file_path, 0, size, buf):
            return result

        trans_ptr = ctypes.c_void_p()
        trans_len = ctypes.c_uint()
        lang_code = "040904B0"
        if version_dll.VerQueryValueW(
            buf, "\\VarFileInfo\\Translation", ctypes.byref(trans_ptr), ctypes.byref(trans_len)
        ) and trans_len.value >= 4:
            lang_pair = ctypes.cast(trans_ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
            lang_code = f"{lang_pair[0]:04X}{lang_pair[1]:04X}"

        for field in fields:
            val_ptr = ctypes.c_void_p()
            val_len = ctypes.c_uint()
            sub_block = f"\\StringFileInfo\\{lang_code}\\{field}"
            if version_dll.VerQueryValueW(
                buf, sub_block, ctypes.byref(val_ptr), ctypes.byref(val_len)
            ) and val_ptr.value and val_len.value > 0:
                raw_str = ctypes.wstring_at(val_ptr.value, val_len.value - 1)
                result[field] = raw_str.strip()
    except Exception as e:
        logd(f"Win32 version query failed for {file_path}: {e}")

    return result


class ExeFileRecord:
    """개별 EXE(디스크 또는 메모리 ZIP 내)의 폴더/파일/버전 상세 정보를 관리하는 레코드 클래스"""

    COLUMNS = [
        "No",
        "구분 (Type)",
        "폴더 (Folder)",
        "파일 (File)",
        "버전 (Version)",
        "환경 (Env)",
        "전체 버전 / 상태",
        "FileVersion",
        "ProductVersion",
        "DESCRIPTOR_VERSION",
        "CompanyName",
        "FileDescription",
        "ProductName",
        "InternalName",
        "OriginalFilename",
        "LegalCopyright",
        "Comments",
        "PrivateBuild",
        "SpecialBuild",
        "파일 크기",
        "최종 수정일",
        "전체 경로",
    ]

    def __init__(
        self,
        index: int,
        file_path: str,
        exe_bytes: Optional[bytes] = None,
        source_type: str = "EXE",
        zip_path: Optional[str] = None,
        inner_path: Optional[str] = None,
        uncompressed_size: Optional[int] = None,
        modified_time: Optional[datetime.datetime] = None,
    ):
        self.index = index
        self.source_type = source_type.upper()
        self.is_from_zip = self.source_type == "ZIP"
        self.zip_path = os.path.abspath(zip_path) if zip_path else ""
        self.inner_path = inner_path or ""
        self.exe_bytes = exe_bytes

        if self.is_from_zip:
            self.file_name = os.path.basename(inner_path or file_path)
            inner_dir = os.path.dirname(inner_path or "").replace("/", os.sep)
            self.folder_path = f"{self.zip_path} :: {inner_dir}" if inner_dir else self.zip_path
            self.file_path = f"{self.zip_path} :: {inner_path or self.file_name}"
            self.source_abs_path = self.zip_path
        else:
            abs_path = os.path.abspath(file_path)
            self.file_path = abs_path
            self.file_name = os.path.basename(abs_path)
            self.folder_path = os.path.dirname(abs_path)
            self.source_abs_path = abs_path

        self.raw_version: str = ""
        self.version_number: str = "-"
        self.environment: str = "-"
        self.is_valid: bool = False
        self.status_message: str = ""
        self.descriptor_version_str: str = ""
        self.signed_items: Dict[str, object] = {}
        self.details: Dict[str, str] = {
            "FileVersion": "",
            "ProductVersion": "",
            "CompanyName": "",
            "FileDescription": "",
            "ProductName": "",
            "InternalName": "",
            "OriginalFilename": "",
            "LegalCopyright": "",
            "Comments": "",
            "PrivateBuild": "",
            "SpecialBuild": "",
        }

        self.file_size_bytes: int = 0
        self.file_size_str: str = "-"
        self.modified_time_str: str = "-"

        self._collect_metadata(uncompressed_size=uncompressed_size, modified_time=modified_time)
        self._extract_version_info()

    @property
    def folder_and_file_key(self) -> Tuple[str, str]:
        norm_folder = os.path.normcase(os.path.normpath(self.folder_path))
        norm_file = self.file_name.strip().lower()
        return (norm_folder, norm_file)

    @property
    def product_name_for_sort(self) -> str:
        prod = (self.details.get("ProductName") or str(self.signed_items.get("app") or "")).strip()
        return (prod if prod else self.file_name).lower()

    @property
    def version_for_sort(self) -> str:
        ver_str = (self.raw_version or self.version_number or "").strip().lower()
        parts = []
        for token in ver_str.replace("-", ".").split("."):
            digits = "".join(ch for ch in token if ch.isdigit())
            if digits and digits == token.lstrip("v"):
                parts.append(digits.zfill(6))
            else:
                parts.append(token)
        return ".".join(parts)

    @property
    def sort_key(self) -> Tuple[str, str, Tuple[str, str], str]:
        return (
            self.product_name_for_sort,
            self.version_for_sort,
            self.folder_and_file_key,
            self.source_type.lower(),
        )

    def _collect_metadata(
        self,
        uncompressed_size: Optional[int] = None,
        modified_time: Optional[datetime.datetime] = None,
    ):
        if self.is_from_zip and self.exe_bytes is not None:
            size_bytes = uncompressed_size if uncompressed_size is not None else len(self.exe_bytes)
            self.file_size_bytes = size_bytes
            self.file_size_str = f"{size_bytes / (1024 * 1024):.2f} MB"

            if modified_time is not None:
                self.modified_time_str = modified_time.strftime("%Y-%m-%d %H:%M:%S")
            elif self.zip_path and os.path.exists(self.zip_path):
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(self.zip_path))
                self.modified_time_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
            return

        if os.path.exists(self.file_path):
            try:
                stat = os.stat(self.file_path)
                self.file_size_bytes = stat.st_size
                self.file_size_str = f"{stat.st_size / (1024 * 1024):.2f} MB"
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
                self.modified_time_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logd(f"Failed to read metadata for {self.file_path}: {e}")

    def _extract_version_info(self):
        target_path_for_api = self.file_path
        temp_file_path: Optional[str] = None

        try:
            if self.is_from_zip and self.exe_bytes is not None:
                with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
                    tmp.write(self.exe_bytes)
                    temp_file_path = tmp.name
                target_path_for_api = temp_file_path

            meta_result = verify_and_read_exe_metadata(target_path_for_api)
            if meta_result.get("verified"):
                desc_ver = meta_result.get("desc_ver")
                self.descriptor_version_str = (
                    str(desc_ver) if desc_ver is not None else str(CRYPTO_DESCRIPTOR_VERSION)
                )
                items = meta_result.get("items") or {}
                if isinstance(items, dict):
                    self.signed_items = items
                    ver_val = items.get("version")
                    self.raw_version = str(ver_val) if ver_val is not None else ""
            else:
                self.descriptor_version_str = ""
                extracted = extract_version_from_exe(target_path_for_api)
                self.raw_version = extracted if extracted else ""

            self.details.update(_query_win32_version_strings(target_path_for_api))
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass

        error_keywords = ("오류", "미적용", "부족", "없음")
        if not self.raw_version or any(kw in self.raw_version for kw in error_keywords):
            fallback_ver = self.details.get("FileVersion") or self.details.get("ProductVersion")
            if fallback_ver:
                self.raw_version = fallback_ver
                self.is_valid = True
                self.status_message = "정상 (PE StringInfo)"
            else:
                self.is_valid = False
                self.status_message = self.raw_version if self.raw_version else "추출 실패 / 정보 없음"
                self.version_number = "N/A"
                self.environment = "Unknown"
                return
        else:
            self.is_valid = True
            self.status_message = "정상 (Valid)"

        if "-" in self.raw_version:
            parts = self.raw_version.split("-", 1)
            self.version_number = parts[0].strip()
            self.environment = parts[1].strip().upper()
        else:
            self.version_number = self.raw_version.strip()
            self.environment = "DEFAULT"

    def get_detailed_tooltip(self) -> str:
        detail_lines = "\n".join(f"• {k}: {v or '-'}" for k, v in self.details.items())
        signed_lines = ""
        if self.signed_items:
            signed_lines = (
                "\n──────────────────────────────\n"
                + "\n".join(
                    f"• {k}: {v if v != '' else '-'}"
                    for k, v in self.signed_items.items()
                )
            )

        return (
            f"■ 구분: {self.source_type}\n"
            f"■ 폴더: {self.folder_path}\n"
            f"■ 파일: {self.file_name}\n"
            f"■ 전체 경로: {self.file_path}\n"
            f"──────────────────────────────\n"
            f"• DESCRIPTOR_VERSION: {self.descriptor_version_str or '-'}\n"
            f"• 요약 버전: {self.raw_version or '없음'} ({self.status_message})\n"
            f"{detail_lines}"
            f"{signed_lines}\n"
            f"──────────────────────────────\n"
            f"• 파일 크기: {self.file_size_str}\n"
            f"• 최종 수정일: {self.modified_time_str}"
        )

    def create_table_items(self) -> list[QTableWidgetItem]:
        tooltip = self.get_detailed_tooltip()

        if self.is_from_zip:
            row_bg = QBrush(QColor("#291E07"))
            default_fg = QBrush(QColor("#FFF3C4"))
            type_bg = QBrush(QColor("#6D4C00"))
            type_fg = QBrush(QColor("#FFE57F"))
            file_fg = QBrush(QColor("#FFD180"))
        else:
            row_bg = QBrush(QColor("#0E2419"))
            default_fg = QBrush(QColor("#E8F5E9"))
            type_bg = QBrush(QColor("#1B5E20"))
            type_fg = QBrush(QColor("#69F0AE"))
            file_fg = QBrush(QColor("#82B1FF"))

        values = [
            str(self.index),
            self.source_type,
            self.folder_path,
            self.file_name,
            self.version_number,
            self.environment,
            self.raw_version if self.is_valid else self.status_message,
            self.details.get("FileVersion", ""),
            self.details.get("ProductVersion", ""),
            self.descriptor_version_str,
            self.details.get("CompanyName", ""),
            self.details.get("FileDescription", ""),
            self.details.get("ProductName", ""),
            self.details.get("InternalName", ""),
            self.details.get("OriginalFilename", ""),
            self.details.get("LegalCopyright", ""),
            self.details.get("Comments", ""),
            self.details.get("PrivateBuild", ""),
            self.details.get("SpecialBuild", ""),
            self.file_size_str,
            self.modified_time_str,
            self.file_path,
        ]

        items: list[QTableWidgetItem] = []
        for col_idx, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setToolTip(tooltip)
            item.setBackground(row_bg)
            item.setForeground(default_fg)

            if col_idx == 0:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)

            if col_idx in (0, 1, 4, 5, 6, 9, 20):
                item.setTextAlignment(Qt.AlignCenter)
            elif col_idx == 19:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            else:
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            if col_idx == 0:
                item.setForeground(QBrush(QColor("#FFFF00")))
            elif col_idx == 1:
                item.setBackground(type_bg)
                item.setForeground(type_fg)
            elif col_idx == 3:
                item.setForeground(file_fg)
            elif col_idx == 9:
                item.setForeground(QBrush(QColor("#00E5FF")))
            elif col_idx in (4, 6):
                if self.is_valid:
                    item.setForeground(QBrush(QColor("#69F0AE")))
                else:
                    item.setForeground(QBrush(QColor("#FF5252")))
            elif col_idx == 5:
                if not self.is_valid:
                    item.setForeground(QBrush(QColor("#FF5252")))
                elif self.environment == "PRODUCTION":
                    item.setBackground(QBrush(QColor("#4A148C")))
                    item.setForeground(QBrush(QColor("#EA80FC")))
                else:
                    item.setForeground(QBrush(QColor("#80D8FF")))

            items.append(item)

        return items