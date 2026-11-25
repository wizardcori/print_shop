from __future__ import annotations

import configparser
import ctypes
import io
import re
import sys
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from build_script.target_config import TargetConfig

PLATFORM_WIN32: str = "win32"
DEFAULT_ENCODING: str = "utf-8-sig"
DATETIME_FORMAT_FULL: str = "%Y-%m-%d %H:%M:%S"

DEFAULT_DIST_DIR_NAME: str = "dist"
DEFAULT_RELEASE_DIR_NAME: str = "release"
DEFAULT_SRC_DIR_NAME: str = "src"
DEFAULT_VERSION_FILENAME: str = "version.txt"

BUCKET_RELEASE: str = "release"
BUCKET_DIST: str = "dist"
SOURCE_VERSION_TXT: str = "version.txt"
STATUS_ZIP_CHECKING: str = "ZIP 확인 중..."
EMPTY_DASH: str = "-"

PE_MAGIC: bytes = b"MZ"
PE_MIN_BYTES: int = 64
PE_MAX_STR_LEN: int = 128
PE_CHAR_MIN: int = 32
PE_CHAR_MAX: int = 0xFFFE
NS_PER_SEC: int = 1_000_000_000

PE_VERSION_FIELDS: tuple[str, ...] = (
    "ProductVersion",
    "FileVersion",
    "ProductName",
    "FileDescription",
    "OriginalFilename",
)

DEFAULT_PE_CODEPAGES: tuple[str, ...] = (
    "040904B0",
    "040904E4",
    "041204B0",
    "041204E4",
)

META_ITEM_KEYS: tuple[str, ...] = (
    "version",
    "build_id",
    "commit",
    "dirty",
    "time",
)

EMBEDDED_MODULE_CANDIDATES: tuple[str, ...] = (
    "build_script.exe_version_desc_v2",
    "build_script.exe_version_desc_v1",
    "build_script.exe_version_crypto_2",
    "exe_version_desc_v2",
    "exe_version_desc_v1",
    "exe_version_crypto_2",
)

EMBEDDED_FUNC_CANDIDATES: tuple[str, ...] = (
    "inspect_exe_bytes",
    "read_exe_bytes",
    "decrypt_exe_bytes",
    "decode_exe_bytes",
    "inspect_exe_metadata",
    "read_exe_metadata",
    "decrypt_exe_metadata",
    "decode_exe_metadata",
    "parse_exe_metadata",
    "extract_exe_metadata",
    "verify_and_extract",
)

VERSION_PATH_LIST_ATTRS: tuple[str, ...] = (
    "version_paths",
    "version_files",
    "version_rel_paths",
)

INI_SECTION_DIRS: str = "BuildDirsConfig"
INI_KEY_DIST_DIR: str = "dist_dir_name"
INI_KEY_RELEASE_DIR: str = "release_dir_name"

_CACHE_LOCK = threading.Lock()
_ZIP_INSPECT_CACHE: dict[tuple[str, str], tuple[tuple[int, int], dict[str, Any]]] = {}
_EXE_INSPECT_CACHE: dict[tuple[str, str], tuple[tuple[int, int], dict[str, Any]]] = {}
_PREV_META_CACHE: dict[tuple[Any, ...], tuple[tuple[tuple[str, int, int], ...], dict[str, Any]]] = {}


def clear_prev_version_cache() -> None:
    """저장된 ZIP/EXE/이전버전 메타데이터 캐시를 초기화합니다."""
    with _CACHE_LOCK:
        _ZIP_INSPECT_CACHE.clear()
        _EXE_INSPECT_CACHE.clear()
        _PREV_META_CACHE.clear()


def _file_fingerprint(path: Path) -> tuple[int, int] | None:
    """파일 변경 여부를 판별하기 위한 (st_size, st_mtime_ns) 지문을 반환합니다."""
    try:
        st = path.stat()
        return (int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * NS_PER_SEC))))
    except OSError:
        return None


def _parse_version_tuple(raw: str | None) -> tuple[int, ...]:
    """문자열에서 숫자 버전(예: 1.2.3.4, v2.0.1)을 추출해 비교용 튜플로 변환합니다."""
    if not raw:
        return ()
    parts = re.findall(r"\d+", str(raw))
    return tuple(int(p) for p in parts)


def _extract_version_from_archive_name(stem_or_name: str) -> str:
    """예: PrintShopBuildManagerApp_v1.2.6.zip, App-1.2.6.4 -> '1.2.6' / '1.2.6.4' 추정."""
    if not stem_or_name:
        return ""
    s = Path(stem_or_name).stem
    m = re.search(r"(?:^|[_\-\s])v(\d+(?:\.\d+){1,3})(?=$|[_\-\s])", s, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"(?:^|[_\-\s])(\d+(?:\.\d+){1,3})(?=$|[_\-\s])", s)
    if m:
        return m.group(1)
    return ""


def _read_single_version_txt(path: Path) -> str:
    """version.txt가 있으면 읽어서 주석/공백을 제외한 유효 버전 문자열 하나만 반환합니다."""
    try:
        if path.is_file():
            for line in path.read_text(encoding=DEFAULT_ENCODING).splitlines():
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("#") and not cleaned.startswith("//"):
                    return cleaned.split()[0]
    except Exception:
        pass
    return ""


def _iter_resolved_paths(root: Path, raw_paths: Any) -> list[Path]:
    """문자열 또는 Path 목록을 중복 없이 절대 경로 리스트로 변환합니다."""
    if not raw_paths:
        return []
    if isinstance(raw_paths, (str, Path)):
        items = [raw_paths]
    else:
        try:
            items = list(raw_paths)
        except TypeError:
            items = [raw_paths]

    resolved: list[Path] = []
    seen: set[Path] = set()
    for item in items:
        if not item:
            continue
        p = Path(str(item))
        abs_p = (p if p.is_absolute() else (root / p)).resolve()
        if abs_p not in seen:
            seen.add(abs_p)
            resolved.append(abs_p)
    return resolved


def _read_ini_dir_overrides(config_path: str | Path | None) -> dict[str, str]:
    if not config_path:
        return {}
    ini_file = Path(config_path).resolve()
    if not ini_file.is_file():
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(ini_file, encoding=DEFAULT_ENCODING)
    except Exception:
        return {}
    if not parser.has_section(INI_SECTION_DIRS):
        return {}
    result: dict[str, str] = {}
    for key in (INI_KEY_DIST_DIR, INI_KEY_RELEASE_DIR):
        if parser.has_option(INI_SECTION_DIRS, key):
            val = parser.get(INI_SECTION_DIRS, key).strip()
            if val:
                result[key] = val
    return result


def _resolve_bucket_dir_names(
    root: Path,
    ov: dict[str, Any],
    config_path: str | Path | None,
) -> tuple[str, str]:
    ini_dirs = _read_ini_dir_overrides(config_path)
    try:
        dcfg = TargetConfig.get_dir_config(root)
        cfg_dist = getattr(dcfg, INI_KEY_DIST_DIR, None)
        cfg_release = getattr(dcfg, INI_KEY_RELEASE_DIR, None)
    except Exception:
        cfg_dist = None
        cfg_release = None

    dist_dir_name = str(
        ov.get(INI_KEY_DIST_DIR)
        or ini_dirs.get(INI_KEY_DIST_DIR)
        or cfg_dist
        or DEFAULT_DIST_DIR_NAME
    )
    release_dir_name = str(
        ov.get(INI_KEY_RELEASE_DIR)
        or ini_dirs.get(INI_KEY_RELEASE_DIR)
        or cfg_release
        or DEFAULT_RELEASE_DIR_NAME
    )
    return dist_dir_name, release_dir_name


def _collect_app_version_files(
    root: Path,
    target_key: str,
    spec: Any,
    ov: dict[str, Any],
    app_version_paths: dict[str, list[str | Path]] | None = None,
) -> list[Path]:
    """해당 앱에 매핑된 버전 경로 목록을 순서대로 수집합니다."""
    raw_list: list[Any] = []

    if isinstance(app_version_paths, dict):
        raw_list.extend(app_version_paths.get(target_key) or ())

    for field_name in VERSION_PATH_LIST_ATTRS:
        val = ov.get(field_name)
        if val:
            raw_list.extend(val if isinstance(val, (list, tuple, set)) else [val])

    if ov.get("version_file"):
        raw_list.append(ov["version_file"])

    if spec is not None:
        for attr_name in VERSION_PATH_LIST_ATTRS:
            val = getattr(spec, attr_name, None)
            if val:
                raw_list.extend(val if isinstance(val, (list, tuple, set)) else [val])
        spec_ver_file = getattr(spec, "version_file", None)
        if spec_ver_file:
            raw_list.append(spec_ver_file)

    if not raw_list:
        dir_hints = list(
            ov.get("dir_hints")
            or (getattr(spec, "dir_hints", None) if spec else None)
            or (target_key,)
        )
        for d in dir_hints:
            if d:
                raw_list.append(root / DEFAULT_SRC_DIR_NAME / str(d) / DEFAULT_VERSION_FILENAME)
                raw_list.append(root / str(d) / DEFAULT_VERSION_FILENAME)

    return _iter_resolved_paths(root, raw_list)


def _get_app_folder_names(target_key: str, spec: Any, ov: dict[str, Any]) -> list[str]:
    dir_hints = list(
        ov.get("dir_hints")
        or (getattr(spec, "dir_hints", None) if spec else None)
        or (target_key,)
    )
    names: list[str] = []
    for name in (
        ov.get("app_folder_name"),
        ov.get("target_name"),
        getattr(spec, "target_name", None) if spec else None,
        target_key,
        *dir_hints,
    ):
        if name and str(name) not in names:
            names.append(str(name))
    return names


def _collect_archive_or_exe_candidates(
    root: Path,
    target_key: str,
    spec: Any,
    ov: dict[str, Any],
    bucket_dir_name: str,
    extension: str,
) -> list[Path]:
    """지정된 출력 폴더에서 해당 앱의 대상 확장자(.zip 또는 .exe) 후보 목록을 수집합니다."""
    app_folder_names = _get_app_folder_names(target_key, spec, ov)
    found: list[Path] = []
    seen: set[Path] = set()
    base_root = root / bucket_dir_name
    ext_lower = extension.lower()

    if not base_root.is_dir():
        return found

    for folder_name in app_folder_names:
        app_dir = base_root / folder_name
        if not app_dir.is_dir():
            continue
        for candidate in app_dir.rglob(f"*{ext_lower}"):
            rp = candidate.resolve()
            if rp.is_file() and rp not in seen:
                seen.add(rp)
                found.append(rp)

    if not found:
        for candidate in base_root.rglob(f"*{ext_lower}"):
            rp = candidate.resolve()
            if rp.is_file() and rp not in seen and target_key.lower() in candidate.stem.lower():
                seen.add(rp)
                found.append(rp)

    return found


def _collect_zip_candidates(
    root: Path,
    target_key: str,
    spec: Any,
    ov: dict[str, Any],
    release_dir_name: str,
) -> list[Path]:
    """release 폴더에서 해당 앱의 .zip 후보 목록을 수집합니다."""
    return _collect_archive_or_exe_candidates(
        root=root,
        target_key=target_key,
        spec=spec,
        ov=ov,
        bucket_dir_name=release_dir_name,
        extension=".zip",
    )


def _collect_exe_candidates(
    root: Path,
    target_key: str,
    spec: Any,
    ov: dict[str, Any],
    bucket_dir_name: str,
) -> list[Path]:
    """지정된 출력 폴더(dist 또는 release)에서 해당 앱의 .exe 후보 목록을 수집합니다."""
    return _collect_archive_or_exe_candidates(
        root=root,
        target_key=target_key,
        spec=spec,
        ov=ov,
        bucket_dir_name=bucket_dir_name,
        extension=".exe",
    )


def _parse_pe_version_from_bytes(pe_bytes: bytes) -> dict[str, str]:
    """메모리 상의 PE 바이트에서 StringFileInfo 버전 문자열을 추출합니다."""
    if not pe_bytes or len(pe_bytes) < PE_MIN_BYTES or pe_bytes[:2] != PE_MAGIC:
        return {}

    info: dict[str, str] = {}
    for field in PE_VERSION_FIELDS:
        needle_utf16 = field.encode("utf-16-le") + b"\x00\x00"
        idx = pe_bytes.find(needle_utf16)
        if idx == -1:
            continue
        val_start = idx + len(needle_utf16)
        while val_start < len(pe_bytes) - 1 and pe_bytes[val_start : val_start + 2] == b"\x00\x00":
            val_start += 2
        chars: list[str] = []
        pos = val_start
        while pos + 1 < len(pe_bytes):
            ch = int.from_bytes(pe_bytes[pos : pos + 2], "little")
            pos += 2
            if ch == 0:
                break
            if PE_CHAR_MIN <= ch < PE_CHAR_MAX:
                chars.append(chr(ch))
            else:
                break
            if len(chars) > PE_MAX_STR_LEN:
                break
        text = "".join(chars).strip()
        if text:
            info[field] = text

    return info


def _extract_pe_version_info_from_file(file_path: Path) -> dict[str, str]:
    """Windows PE 파일의 버전 리소스를 추출합니다."""
    if sys.platform != PLATFORM_WIN32 or not file_path.is_file():
        return {}

    info: dict[str, str] = {}
    path_str = str(file_path)

    try:
        version_dll = ctypes.WinDLL("version", use_last_error=True)
        get_size = version_dll.GetFileVersionInfoSizeW
        get_size.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        get_size.restype = ctypes.c_ulong

        get_info = version_dll.GetFileVersionInfoW
        get_info.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        get_info.restype = ctypes.c_int

        ver_query = version_dll.VerQueryValueW
        ver_query.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint),
        ]
        ver_query.restype = ctypes.c_int

        dummy = ctypes.c_ulong(0)
        size = get_size(path_str, ctypes.byref(dummy))
        if size <= 0:
            return {}

        buf = ctypes.create_string_buffer(size)
        if not get_info(path_str, 0, size, buf):
            return {}

        trans_ptr = ctypes.c_void_p()
        trans_len = ctypes.c_uint(0)
        lang_codepages: list[str] = list(DEFAULT_PE_CODEPAGES)
        if ver_query(buf, r"\VarFileInfo\Translation", ctypes.byref(trans_ptr), ctypes.byref(trans_len)):
            if trans_len.value >= 4 and trans_ptr.value:
                pair = ctypes.cast(trans_ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
                lang_codepages.insert(0, f"{pair[0]:04X}{pair[1]:04X}")

        for cp in lang_codepages:
            found_any = False
            for field in PE_VERSION_FIELDS:
                val_ptr = ctypes.c_void_p()
                val_len = ctypes.c_uint(0)
                sub_block = rf"\StringFileInfo\{cp}\{field}"
                if ver_query(buf, sub_block, ctypes.byref(val_ptr), ctypes.byref(val_len)):
                    if val_len.value > 0 and val_ptr.value:
                        text = ctypes.wstring_at(val_ptr.value, max(0, val_len.value - 1)).strip()
                        if text and field not in info:
                            info[field] = text
                            found_any = True
            if found_any:
                break
    except Exception:
        pass

    return info


def _normalize_decrypt_result(raw: Any, display_path: str, size_bytes: int | None) -> dict[str, Any] | None:
    """디코더 반환 형태를 정규화합니다."""
    if not isinstance(raw, dict):
        return None
    if "error" in raw and not raw.get("items") and not raw.get("version"):
        return {"error": str(raw["error"]), "_exe_path": display_path}

    items = dict(raw.get("items") or {})
    for k in META_ITEM_KEYS:
        if not items.get(k) and raw.get(k) is not None:
            items[k] = raw[k]

    if not items and not raw:
        return None

    normalized: dict[str, Any] = {
        "_exe_path": str(raw.get("_exe_path") or display_path),
        "file_size_bytes": raw.get("file_size_bytes", size_bytes),
        "items": items,
    }
    if "error" in raw:
        normalized["error"] = raw["error"]
    return normalized


def _extract_embedded_metadata_from_bytes(
    exe_bytes: bytes,
    display_path: str,
    size_bytes: int | None,
) -> dict[str, Any] | None:
    """메모리 상의 EXE 바이트에서 임베디드 암호화 메타데이터를 복호화합니다."""
    for mod_name in EMBEDDED_MODULE_CANDIDATES:
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception:
            continue

        for fn_name in EMBEDDED_FUNC_CANDIDATES:
            fn = getattr(mod, fn_name, None)
            if not callable(fn):
                continue

            for mem_arg in (exe_bytes, io.BytesIO(exe_bytes)):
                try:
                    res = fn(mem_arg)
                    norm = _normalize_decrypt_result(res, display_path, size_bytes)
                    if norm and (norm.get("items") or "error" in norm):
                        return norm
                except TypeError:
                    continue
                except Exception:
                    break

            tmp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tf:
                    tf.write(exe_bytes)
                    tmp_path = Path(tf.name)
                for path_arg in (tmp_path, str(tmp_path)):
                    try:
                        res = fn(path_arg)
                        norm = _normalize_decrypt_result(res, display_path, size_bytes)
                        if norm and (norm.get("items") or "error" in norm):
                            return norm
                    except TypeError:
                        continue
            except Exception:
                pass
            finally:
                if tmp_path is not None:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

    return None


def _quick_zip_candidate(zip_path: Path, bucket_name: str) -> dict[str, Any]:
    """지연 검사 전 단계: 메모리 해제 없이 ZIP 파일명/수정시각 기준으로 후보만 구성합니다."""
    stat_info = zip_path.stat()
    mtime = stat_info.st_mtime
    mtime_str = datetime.fromtimestamp(mtime).strftime(DATETIME_FORMAT_FULL)
    source_label = f"zip({bucket_name})"
    zip_name_ver = _extract_version_from_archive_name(zip_path.name)

    return {
        "kind": "zip",
        "bucket": bucket_name,
        "source_label": source_label,
        "path": zip_path,
        "display_path": str(zip_path),
        "mtime": mtime,
        "mtime_str": mtime_str,
        "file_size_bytes": stat_info.st_size,
        "version": zip_name_ver or zip_path.stem,
        "items": {},
        "error": None,
        "deferred_zip": True,
    }


def _inspect_zip_candidate(zip_path: Path, bucket_name: str, target_key: str) -> dict[str, Any]:
    """
    release 폴더의 .zip 후보를 메모리에서 열어 내부 .exe 메타데이터와 버전을 추출합니다.
    파일 크기와 수정 시각이 이전과 같으면 캐시된 결과를 반환해 재해제를 피합니다.
    """
    fp = _file_fingerprint(zip_path)
    cache_key = (str(zip_path), target_key.lower())
    if fp is not None:
        with _CACHE_LOCK:
            cached = _ZIP_INSPECT_CACHE.get(cache_key)
            if cached is not None and cached[0] == fp:
                return dict(cached[1])

    stat_info = zip_path.stat()
    mtime = stat_info.st_mtime
    mtime_str = datetime.fromtimestamp(mtime).strftime(DATETIME_FORMAT_FULL)
    source_label = f"zip({bucket_name})"
    zip_name_ver = _extract_version_from_archive_name(zip_path.name)

    best_version = zip_name_ver
    best_items: dict[str, Any] = {}
    best_size = stat_info.st_size
    best_display_path = str(zip_path)
    best_error: Any = None

    try:
        zip_bytes = zip_path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            exe_names = [
                name for name in zf.namelist()
                if not name.endswith("/") and name.lower().endswith(".exe")
            ]
            exe_names.sort(
                key=lambda n: (0 if target_key.lower() in Path(n).stem.lower() else 1, len(n))
            )

            for inner_name in exe_names:
                info = zf.getinfo(inner_name)
                exe_bytes = zf.read(inner_name)
                display_path = f"{zip_path}::{inner_name}"

                pe_info = _parse_pe_version_from_bytes(exe_bytes)
                embedded = _extract_embedded_metadata_from_bytes(
                    exe_bytes=exe_bytes,
                    display_path=display_path,
                    size_bytes=info.file_size,
                )
                dec_items = dict((embedded or {}).get("items") or {})
                pe_ver = (pe_info.get("ProductVersion") or pe_info.get("FileVersion") or "").strip()
                inner_name_ver = _extract_version_from_archive_name(inner_name)

                ver = (
                    str(dec_items.get("version") or "").strip()
                    or pe_ver
                    or zip_name_ver
                    or inner_name_ver
                    or ""
                )
                if ver or dec_items:
                    best_version = ver
                    best_items = dec_items
                    best_size = info.file_size
                    best_display_path = display_path
                    if embedded and "error" in embedded:
                        best_error = embedded["error"]
                    break
    except Exception as exc:
        best_error = str(exc)

    if not best_version:
        best_version = zip_name_ver or zip_path.stem

    result = {
        "kind": "zip",
        "bucket": bucket_name,
        "source_label": source_label,
        "path": zip_path,
        "display_path": best_display_path,
        "mtime": mtime,
        "mtime_str": mtime_str,
        "file_size_bytes": best_size,
        "version": best_version,
        "items": best_items,
        "error": best_error,
        "deferred_zip": False,
    }

    if fp is not None:
        with _CACHE_LOCK:
            _ZIP_INSPECT_CACHE[cache_key] = (fp, dict(result))

    return result


def _inspect_exe_candidate(exe_path: Path, bucket_name: str) -> dict[str, Any]:
    """
    dist(또는 release) 폴더의 .exe 후보에서 정보를 추출합니다.
    파일 크기와 수정 시각이 이전과 같으면 캐시된 결과를 반환해 재읽기를 피합니다.
    """
    fp = _file_fingerprint(exe_path)
    cache_key = (str(exe_path), bucket_name)
    if fp is not None:
        with _CACHE_LOCK:
            cached = _EXE_INSPECT_CACHE.get(cache_key)
            if cached is not None and cached[0] == fp:
                return dict(cached[1])

    stat_info = exe_path.stat()
    mtime = stat_info.st_mtime
    mtime_str = datetime.fromtimestamp(mtime).strftime(DATETIME_FORMAT_FULL)
    source_label = f"exe({bucket_name})"

    pe_info = _extract_pe_version_info_from_file(exe_path)
    exe_bytes = exe_path.read_bytes()
    embedded = _extract_embedded_metadata_from_bytes(
        exe_bytes=exe_bytes,
        display_path=str(exe_path),
        size_bytes=stat_info.st_size,
    )
    dec_items = dict((embedded or {}).get("items") or {})
    pe_ver = (pe_info.get("ProductVersion") or pe_info.get("FileVersion") or "").strip()
    name_ver = _extract_version_from_archive_name(exe_path.name)

    ver = str(dec_items.get("version") or "").strip() or pe_ver or name_ver or exe_path.stem

    result = {
        "kind": "exe",
        "bucket": bucket_name,
        "source_label": source_label,
        "path": exe_path,
        "display_path": str(exe_path),
        "mtime": mtime,
        "mtime_str": mtime_str,
        "file_size_bytes": stat_info.st_size,
        "version": ver,
        "items": dec_items,
        "error": (embedded or {}).get("error"),
        "deferred_zip": False,
    }

    if fp is not None:
        with _CACHE_LOCK:
            _EXE_INSPECT_CACHE[cache_key] = (fp, dict(result))

    return result


def _build_meta_from_selected(
    selected: dict[str, Any] | None,
    txt_version: str,
    txt_source_path: Path | None,
    has_deferred_zip: bool,
) -> dict[str, Any]:
    if selected is None:
        if not txt_version:
            return {}
        return {
            "_exe_path": str(txt_source_path) if txt_source_path else "",
            "_source_label": SOURCE_VERSION_TXT,
            "_has_deferred_zip": has_deferred_zip,
            "file_size_bytes": None,
            "items": {
                "version": txt_version,
                "source": SOURCE_VERSION_TXT,
                "version_file": str(txt_source_path) if txt_source_path else EMPTY_DASH,
                "build_id": EMPTY_DASH,
                "commit": EMPTY_DASH,
                "dirty": EMPTY_DASH,
                "time": EMPTY_DASH,
            },
        }

    dec_items = dict(selected.get("items") or {})
    final_version = (
        str(dec_items.get("version") or "").strip()
        or str(selected.get("version") or "").strip()
        or txt_version
        or EMPTY_DASH
    )

    items: dict[str, Any] = {
        "version": final_version,
        "source": selected["source_label"],
        "build_id": str(dec_items.get("build_id") or (STATUS_ZIP_CHECKING if selected.get("deferred_zip") else EMPTY_DASH)),
        "commit": str(dec_items.get("commit") or EMPTY_DASH),
        "dirty": str(dec_items.get("dirty") or EMPTY_DASH),
        "time": str(dec_items.get("time") or selected["mtime_str"]),
        "version_file": str(txt_source_path) if txt_source_path else EMPTY_DASH,
        "file_version": txt_version or EMPTY_DASH,
    }

    result: dict[str, Any] = {
        "_exe_path": selected["display_path"],
        "_source_label": selected["source_label"],
        "_has_deferred_zip": has_deferred_zip,
        "file_size_bytes": selected.get("file_size_bytes"),
        "items": items,
    }
    if selected.get("error"):
        result["error"] = selected["error"]
    return result


def _build_snapshot_sig(paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
    sig: list[tuple[str, int, int]] = []
    for p in paths:
        fp = _file_fingerprint(p)
        if fp is not None:
            sig.append((str(p), fp[0], fp[1]))
    sig.sort()
    return tuple(sig)


def _rank_candidate(cand: dict[str, Any]) -> tuple[tuple[int, ...], int, float]:
    ver_tuple = _parse_version_tuple(cand.get("version"))
    bucket_rank = 1 if cand.get("bucket") == BUCKET_RELEASE else 0
    mtime = float(cand.get("mtime") or 0.0)
    return (ver_tuple, bucket_rank, mtime)


def resolve_zip_prev_version_meta(
    project_root: str | Path,
    target_key: str,
    config_path: str | Path | None = None,
    app_override: dict[str, Any] | None = None,
    app_version_paths: dict[str, list[str | Path]] | None = None,
) -> dict[str, Any]:
    """TaskQueue 워커에서 호출: release의 .zip을 메모리에서 열어 최신 버전을 추출합니다."""
    root = Path(project_root).resolve()
    resolved_cfg = str(Path(config_path).resolve()) if config_path else ""
    ov = app_override if isinstance(app_override, dict) else {}
    spec = TargetConfig.get_spec(target_key)
    dist_dir_name, release_dir_name = _resolve_bucket_dir_names(root, ov, config_path)

    version_files = _collect_app_version_files(
        root=root,
        target_key=target_key,
        spec=spec,
        ov=ov,
        app_version_paths=app_version_paths,
    )
    zip_paths = _collect_zip_candidates(root, target_key, spec, ov, release_dir_name)
    exe_paths = _collect_exe_candidates(root, target_key, spec, ov, dist_dir_name)

    meta_cache_key = ("zip_meta", str(root), resolved_cfg, target_key, release_dir_name, dist_dir_name)
    snap_sig = _build_snapshot_sig([*version_files, *zip_paths, *exe_paths])
    with _CACHE_LOCK:
        cached_meta = _PREV_META_CACHE.get(meta_cache_key)
        if cached_meta is not None and cached_meta[0] == snap_sig:
            return dict(cached_meta[1])

    txt_version = ""
    txt_source_path: Path | None = None
    for vp in version_files:
        ver_str = _read_single_version_txt(vp)
        if ver_str:
            txt_version = ver_str
            txt_source_path = vp
            break

    candidates: list[dict[str, Any]] = [
        _inspect_zip_candidate(zp, BUCKET_RELEASE, target_key) for zp in zip_paths
    ]
    candidates.extend(_inspect_exe_candidate(ep, BUCKET_DIST) for ep in exe_paths)

    if not candidates and not txt_version:
        return {}

    for cand in candidates:
        if not _parse_version_tuple(cand.get("version")) and txt_version:
            cand["version"] = txt_version

    selected = max(candidates, key=_rank_candidate) if candidates else None
    result = _build_meta_from_selected(
        selected=selected,
        txt_version=txt_version,
        txt_source_path=txt_source_path,
        has_deferred_zip=False,
    )

    with _CACHE_LOCK:
        _PREV_META_CACHE[meta_cache_key] = (snap_sig, dict(result))

    return result


def resolve_prev_version_meta(
    project_root: str | Path,
    target_key: str,
    config_path: str | Path | None = None,
    app_override: dict[str, Any] | None = None,
    app_version_paths: dict[str, list[str | Path]] | None = None,
    defer_zip: bool = False,
) -> dict[str, Any]:
    """
    이전버전 선택 기준:
    1) 최신 버전 우선순위
    2) 버전이 같으면 release > dist 우선순위
    3) 출처 표기: zip(release), exe(dist)
    4) 변경되지 않은 ZIP/EXE는 캐시를 재사용해 디스크 재읽기/재검사를 피함
    """
    root = Path(project_root).resolve()
    resolved_cfg = str(Path(config_path).resolve()) if config_path else ""
    ov = app_override if isinstance(app_override, dict) else {}
    spec = TargetConfig.get_spec(target_key)
    dist_dir_name, release_dir_name = _resolve_bucket_dir_names(root, ov, config_path)

    version_files = _collect_app_version_files(
        root=root,
        target_key=target_key,
        spec=spec,
        ov=ov,
        app_version_paths=app_version_paths,
    )
    zip_paths = _collect_zip_candidates(root, target_key, spec, ov, release_dir_name)
    exe_paths = _collect_exe_candidates(root, target_key, spec, ov, dist_dir_name)
    has_deferred_zip = bool(defer_zip and zip_paths)

    meta_cache_key = (
        "prev_meta",
        str(root),
        resolved_cfg,
        target_key,
        release_dir_name,
        dist_dir_name,
        bool(defer_zip),
    )
    snap_sig = _build_snapshot_sig([*version_files, *zip_paths, *exe_paths])
    with _CACHE_LOCK:
        cached_meta = _PREV_META_CACHE.get(meta_cache_key)
        if cached_meta is not None and cached_meta[0] == snap_sig:
            return dict(cached_meta[1])

    txt_version = ""
    txt_source_path: Path | None = None
    for vp in version_files:
        ver_str = _read_single_version_txt(vp)
        if ver_str:
            txt_version = ver_str
            txt_source_path = vp
            break

    candidates: list[dict[str, Any]] = []
    if zip_paths:
        if defer_zip:
            candidates.extend(_quick_zip_candidate(zp, BUCKET_RELEASE) for zp in zip_paths)
        else:
            candidates.extend(_inspect_zip_candidate(zp, BUCKET_RELEASE, target_key) for zp in zip_paths)

    candidates.extend(_inspect_exe_candidate(ep, BUCKET_DIST) for ep in exe_paths)

    if not candidates and not txt_version:
        return {}

    for cand in candidates:
        if not _parse_version_tuple(cand.get("version")) and txt_version:
            cand["version"] = txt_version

    selected = max(candidates, key=_rank_candidate) if candidates else None
    result = _build_meta_from_selected(
        selected=selected,
        txt_version=txt_version,
        txt_source_path=txt_source_path,
        has_deferred_zip=has_deferred_zip,
    )

    with _CACHE_LOCK:
        _PREV_META_CACHE[meta_cache_key] = (snap_sig, dict(result))

    return result