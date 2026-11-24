"""
빌드 산출물 해시 생성 및 EXE 서명/검증 모듈 (artifact_signing.py)
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Callable

from Common.Version.exe_version_crypto import (
    compute_file_sha256,
    decrypt_all_items_from_exe,
    encrypt_and_append_version,
    extract_version_from_exe,
    sign_exe_authenticode,
)
from Common.log import logd
from build_script.target_config_io import DEFAULT_TEXT_ENCODING

HASH_CHUNK_SIZE: int = 1024 * 1024
SHA256_FILE_EXTENSION: str = ".sha256"
HASH_PREVIEW_LEN: int = 12
PAYLOAD_VERSION_PREFIX: str = "v"

KEY_VERIFIED: str = "verified"
KEY_ERROR: str = "error"
KEY_ITEMS: str = "items"
KEY_PAYLOAD_SHA256: str = "payload_sha256"
KEY_COMMIT: str = "commit"

__all__ = [
    "HASH_CHUNK_SIZE",
    "HASH_PREVIEW_LEN",
    "KEY_COMMIT",
    "KEY_ERROR",
    "KEY_ITEMS",
    "KEY_PAYLOAD_SHA256",
    "KEY_VERIFIED",
    "PAYLOAD_VERSION_PREFIX",
    "SHA256_FILE_EXTENSION",
    "inject_and_verify_exe",
    "write_sha256_file",
]


def write_sha256_file(target_file: str | None) -> str | None:
    if not target_file or not os.path.isfile(target_file):
        return None

    digest = hashlib.sha256()
    with open(target_file, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)

    sha_hex = digest.hexdigest()
    sha_path = f"{target_file}{SHA256_FILE_EXTENSION}"
    with open(sha_path, "w", encoding=DEFAULT_TEXT_ENCODING) as f:
        f.write(f"{sha_hex}  {os.path.basename(target_file)}\n")

    logd(f"  • SHA-256 생성 완료 ({os.path.basename(sha_path)}): {sha_hex}")
    return sha_hex


def inject_and_verify_exe(
    exe_path: str | None,
    app_label: str,
    app_version: str,
    mode: str,
    cwd: str,
    reload_fn: Callable[[], Any] | None = None,
) -> dict[str, Any] | None:
    if not exe_path or not os.path.isfile(exe_path):
        logd(f"  ⚠️ [{app_label}] 대상 EXE가 없어 서명/주입을 건너뜁니다: {exe_path}")
        return None

    expected_payload = f"{PAYLOAD_VERSION_PREFIX}{app_version}-{mode}"
    encrypt_and_append_version(
        exe_path=exe_path,
        version_str=expected_payload,
        app_name=app_label,
        mode=mode,
        cwd=cwd,
        authenticode=False,
        write_sha256=False,
    )

    if callable(reload_fn):
        reloaded_mods = reload_fn()
        logd(f"  • [{app_label}] 검증 직전 모듈 리로드: {reloaded_mods}")

    read_payload = extract_version_from_exe(exe_path)
    if read_payload != expected_payload:
        raise ValueError(
            f"[{app_label}] 서명 메타데이터 버전 검증 불일치: 예상 '{expected_payload}', 실제 '{read_payload}'"
        )

    ver_info = decrypt_all_items_from_exe(exe_path)
    if not ver_info.get(KEY_VERIFIED) or KEY_ERROR in ver_info:
        raise ValueError(f"[{app_label}] 서명 메타데이터 검증 실패: {ver_info.get(KEY_ERROR)}")

    sign_exe_authenticode(exe_path, cwd=cwd)
    final_sha256 = write_sha256_file(exe_path) or compute_file_sha256(exe_path)

    items = ver_info.get(KEY_ITEMS) or {}
    payload_sha_preview = str(ver_info.get(KEY_PAYLOAD_SHA256, ""))[:HASH_PREVIEW_LEN]
    exe_sha_preview = str(final_sha256)[:HASH_PREVIEW_LEN]
    logd(
        f"  ✅ [{app_label}] 서명 및 무결성 검증 완료 ({read_payload}) | "
        f"payload_sha256={payload_sha_preview}... | "
        f"exe_sha256={exe_sha_preview}... | commit={items.get(KEY_COMMIT)}"
    )
    return ver_info