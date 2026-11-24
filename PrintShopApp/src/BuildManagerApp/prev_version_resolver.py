from __future__ import annotations

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

from build_script.build_targets import BuildTargets

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
        return (int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))))
    except OSError:
        return None


def _parse_version_tuple(raw: str | None) -> tuple[int, ...]:
    """문자열에서 숫자 버전(예: 1.2.3.4, v2.0.1)을 추출해 비교용 튜플로 변환합니다."""
    if not raw:
        return ()
    parts = re.findall(r"\d+", str(raw))
    return tuple(int(p) for p in parts)


def _extract_version_from_archive_name(stem_or_name: str) -> str:
    """
    예: PrintShopBuildManagerApp_v1.2.6.zip, App-1.2.6.4 -> '1.2.6' / '1.2.6.4' 추정
    """
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
            for line in path.read_text(encoding="utf-8-sig").splitlines():
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

    for field_name in ("version_paths", "version_files", "version_rel_paths"):
        val = ov.get(field_name)
        if val:
            raw_list.extend(val if isinstance(val, (list, tuple, set)) else [val])

    if ov.get("version_file"):
        raw_list.append(ov["version_file"])

    if spec is not None:
        for attr_name in ("version_paths", "version_files", "version_rel_paths"):
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
                raw_list.append(root / "src" / str(d) / "version.txt")
                raw_list.append(root / str(d) / "version.txt")

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


def _collect_zip_candidates(
    root: Path,
    target_key: str,
    spec: Any,
    ov: dict[str, Any],
    release_dir_name: str,
) -> list[Path]:
    """release 폴더에서 해당 앱의 .zip 후보 목록을 수집합니다."""
    app_folder_names = _get_app_folder_names(target_key, spec, ov)
    found: list[Path] = []
    seen: set[Path] = set()
    release_root = root / release_dir_name

    if not release_root.is_dir():
        return found

    for folder_name in app_folder_names:
        app_dir = release_root / folder_name
        if not app_dir.is_dir():
            continue
        for zp in app_dir.rglob("*.zip"):
            rp = zp.resolve()
            if rp.is_file() and rp not in seen:
                seen.add(rp)
                found.append(rp)

    if not found:
        for zp in release_root.rglob("*.zip"):
            rp = zp.resolve()
            if rp.is_file() and rp not in seen and target_key.lower() in zp.stem.lower():
                seen.add(rp)
                found.append(rp)

    return found


def _collect_exe_candidates(
    root: Path,
    target_key: str,
    spec: Any,
    ov: dict[str, Any],
    bucket_dir_name: str,
) -> list[Path]:
    """지정된 출력 폴더(dist 또는 release)에서 해당 앱의 .exe 후보 목록을 수집합니다."""
    app_folder_names = _get_app_folder_names(target_key, spec, ov)
    found: list[Path] = []
    seen: set[Path] = set()
    base_root = root / bucket_dir_name

    if not base_root.is_dir():
        return found

    for folder_name in app_folder_names:
        app_dir = base_root / folder_name
        if not app_dir.is_dir():
            continue
        for ep in app_dir.rglob("*.exe"):
            rp = ep.resolve()
            if rp.is_file() and rp not in seen:
                seen.add(rp)
                found.append(rp)

    if not found:
        for ep in base_root.rglob("*.exe"):
            rp = ep.resolve()
            if rp.is_file() and rp not in seen and target_key.lower() in ep.stem.lower():
                seen.add(rp)
                found.append(rp)

    return found


def _parse_pe_version_from_bytes(pe_bytes: bytes) -> dict[str, str]:
    """메모리 상의 PE 바이트에서 StringFileInfo 버전 문자열을 추출합니다."""
    if not pe_bytes or len(pe_bytes) < 64 or pe_bytes[:2] != b"MZ":
        return {}

    info: dict[str, str] = {}
    targets = ("ProductVersion", "FileVersion", "ProductName", "FileDescription", "OriginalFilename")

    for field in targets:
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
            if 32 <= ch < 0xFFFE:
                chars.append(chr(ch))
            else:
                break
            if len(chars) > 128:
                break
        text = "".join(chars).strip()
        if text:
            info[field] = text

    return info


def _extract_pe_version_info_from_file(file_path: Path) -> dict[str, str]:
    """Windows PE 파일의 버전 리소스를 추출합니다."""
    if sys.platform != "win32" or not file_path.is_file():
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
        lang_codepages: list[str] = ["040904B0", "040904E4", "041204B0", "041204E4"]
        if ver_query(buf, r"\VarFileInfo\Translation", ctypes.byref(trans_ptr), ctypes.byref(trans_len)):
            if trans_len.value >= 4 and trans_ptr.value:
                pair = ctypes.cast(trans_ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
                lang_codepages.insert(0, f"{pair[0]:04X}{pair[1]:04X}")

        fields = ("ProductVersion", "FileVersion", "ProductName", "FileDescription", "OriginalFilename")
        for cp in lang_codepages:
            found_any = False
            for field in fields:
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
    for k in ("version", "build_id", "commit", "dirty", "time"):
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
    module_candidates = (
        "build_script.exe_version_desc_v2",
        "build_script.exe_version_desc_v1",
        "build_script.exe_version_crypto_2",
        "exe_version_desc_v2",
        "exe_version_desc_v1",
        "exe_version_crypto_2",
    )
    func_candidates = (
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

    for mod_name in module_candidates:
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception:
            continue

        for fn_name in func_candidates:
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
    mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
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
    mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
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
    mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
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
            "_source_label": "version.txt",
            "_has_deferred_zip": has_deferred_zip,
            "file_size_bytes": None,
            "items": {
                "version": txt_version,
                "source": "version.txt",
                "version_file": str(txt_source_path) if txt_source_path else "-",
                "build_id": "-",
                "commit": "-",
                "dirty": "-",
                "time": "-",
            },
        }

    dec_items = dict(selected.get("items") or {})
    final_version = (
        str(dec_items.get("version") or "").strip()
        or str(selected.get("version") or "").strip()
        or txt_version
        or "-"
    )

    items: dict[str, Any] = {
        "version": final_version,
        "source": selected["source_label"],
        "build_id": str(dec_items.get("build_id") or ("ZIP 확인 중..." if selected.get("deferred_zip") else "-")),
        "commit": str(dec_items.get("commit") or "-"),
        "dirty": str(dec_items.get("dirty") or "-"),
        "time": str(dec_items.get("time") or selected["mtime_str"]),
        "version_file": str(txt_source_path) if txt_source_path else "-",
        "file_version": txt_version or "-",
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


def resolve_zip_prev_version_meta(
    project_root: str | Path,
    target_key: str,
    config_path: str | Path | None = None,
    app_override: dict[str, Any] | None = None,
    app_version_paths: dict[str, list[str | Path]] | None = None,
) -> dict[str, Any]:
    """TaskQueue 워커에서 호출: release의 .zip을 메모리에서 열어 최신 버전을 추출합니다."""
    root = Path(project_root).resolve()
    ov = app_override if isinstance(app_override, dict) else {}
    spec = BuildTargets.get_spec(target_key)

    try:
        dcfg = BuildTargets.get_dir_config(root)
        dist_dir_name = str(ov.get("dist_dir_name") or dcfg.dist_dir_name or "dist")
        release_dir_name = str(ov.get("release_dir_name") or dcfg.release_dir_name or "release")
    except Exception:
        dist_dir_name = "dist"
        release_dir_name = "release"

    version_files = _collect_app_version_files(
        root=root,
        target_key=target_key,
        spec=spec,
        ov=ov,
        app_version_paths=app_version_paths,
    )
    zip_paths = _collect_zip_candidates(root, target_key, spec, ov, release_dir_name)
    exe_paths = _collect_exe_candidates(root, target_key, spec, ov, dist_dir_name)

    meta_cache_key = ("zip_meta", str(root), target_key, release_dir_name, dist_dir_name)
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
        _inspect_zip_candidate(zp, "release", target_key) for zp in zip_paths
    ]
    candidates.extend(_inspect_exe_candidate(ep, "dist") for ep in exe_paths)

    if not candidates and not txt_version:
        return {}

    for cand in candidates:
        if not _parse_version_tuple(cand.get("version")) and txt_version:
            cand["version"] = txt_version

    def _rank_key(cand: dict[str, Any]) -> tuple[tuple[int, ...], int, float]:
        ver_tuple = _parse_version_tuple(cand.get("version"))
        bucket_rank = 1 if cand.get("bucket") == "release" else 0
        mtime = float(cand.get("mtime") or 0.0)
        return (ver_tuple, bucket_rank, mtime)

    selected = max(candidates, key=_rank_key) if candidates else None
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
    ov = app_override if isinstance(app_override, dict) else {}
    spec = BuildTargets.get_spec(target_key)

    try:
        dcfg = BuildTargets.get_dir_config(root)
        dist_dir_name = str(ov.get("dist_dir_name") or dcfg.dist_dir_name or "dist")
        release_dir_name = str(ov.get("release_dir_name") or dcfg.release_dir_name or "release")
    except Exception:
        dist_dir_name = "dist"
        release_dir_name = "release"

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

    meta_cache_key = ("prev_meta", str(root), target_key, release_dir_name, dist_dir_name, bool(defer_zip))
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
            candidates.extend(_quick_zip_candidate(zp, "release") for zp in zip_paths)
        else:
            candidates.extend(_inspect_zip_candidate(zp, "release", target_key) for zp in zip_paths)

    candidates.extend(_inspect_exe_candidate(ep, "dist") for ep in exe_paths)

    if not candidates and not txt_version:
        return {}

    for cand in candidates:
        if not _parse_version_tuple(cand.get("version")) and txt_version:
            cand["version"] = txt_version

    def _rank_key(cand: dict[str, Any]) -> tuple[tuple[int, ...], int, float]:
        ver_tuple = _parse_version_tuple(cand.get("version"))
        bucket_rank = 1 if cand.get("bucket") == "release" else 0
        mtime = float(cand.get("mtime") or 0.0)
        return (ver_tuple, bucket_rank, mtime)

    selected = max(candidates, key=_rank_key) if candidates else None
    result = _build_meta_from_selected(
        selected=selected,
        txt_version=txt_version,
        txt_source_path=txt_source_path,
        has_deferred_zip=has_deferred_zip,
    )

    with _CACHE_LOCK:
        _PREV_META_CACHE[meta_cache_key] = (snap_sig, dict(result))

    return result