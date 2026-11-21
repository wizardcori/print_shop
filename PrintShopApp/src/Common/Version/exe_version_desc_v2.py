import base64
import getpass
import hashlib
import json
import os
import platform
import struct
import subprocess
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from Common.log import logd

# ==============================================================================
# DESCRIPTOR_VERSION = 2 (SIGVER3!) 전용 패킹/언패킹/검증/스트립 로직
#
# v1과의 차이점:
#   - desc_ver = 2 (uint8)
#   - host 필드 포맷: "<호스트이름>|<CPUID>" (예: "DESKTOP-ABC123|BFEBFBFF000906EA")
#   - 트레일러 예약 영역(49B) 중 선두 1바이트를 flags(uint8)로 활용 가능 (0x00 기본값)
# ==============================================================================
SIGN_MAGIC = b"SIGVER3!"
DESCRIPTOR_VERSION = 2

_SIGN_TRAILER_STRUCT_V2 = struct.Struct("<8sBIHB48s")
SIGN_TRAILER_SIZE_V2 = _SIGN_TRAILER_STRUCT_V2.size

ALL_META_KEYS_V2 = (
    "version",
    "mode",
    "build_id",
    "time",
    "who",
    "host",
    "dirty",
    "app",
    "commit",
    "message",
)


def _canonical_json_bytes(data: dict[str, Any]) -> bytes:
    """서명 및 SHA-256 계산의 일관성을 위해 키를 정렬한 UTF-8 JSON 바이트를 반환합니다."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _compute_file_sha256(file_path: str) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_cpuid() -> str:
    """현재 시스템의 CPU ID 문자열을 조회합니다."""
    if os.name == "nt":
        try:
            res = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1 -ExpandProperty ProcessorId)",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                proc_id = res.stdout.strip().splitlines()[0].strip()
                if proc_id:
                    return proc_id
        except Exception:
            pass

        try:
            res = subprocess.run(
                ["wmic", "cpu", "get", "ProcessorId"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0:
                lines = [
                    ln.strip()
                    for ln in res.stdout.splitlines()
                    if ln.strip() and ln.strip().lower() != "processorid"
                ]
                if lines:
                    return lines[0]
        except Exception:
            pass

    try:
        if os.path.isfile("/proc/cpuinfo"):
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if any(k in line.lower() for k in ("serial", "model name", "vendor_id")):
                        parts = line.split(":", 1)
                        if len(parts) == 2 and parts[1].strip():
                            return parts[1].strip()
    except Exception:
        pass

    fallback = platform.processor() or platform.machine() or "unknown-cpuid"
    return fallback.strip()


def format_host_with_cpuid(host_name: str | None = None, cpuid: str | None = None) -> str:
    """호스트 이름 뒤에 '|' 구분자로 CPUID를 붙여 '<host>|<cpuid>' 형식으로 반환합니다."""
    resolved_host = (host_name or platform.node() or "unknown-host").strip()
    resolved_cpuid = (cpuid if cpuid is not None else get_cpuid()).strip() or "unknown-cpuid"
    if "|" in resolved_host:
        return resolved_host
    return f"{resolved_host}|{resolved_cpuid}"


def parse_host_and_cpuid(host_value: str | None) -> tuple[str, str]:
    """'<host>|<cpuid>' 문자열을 (host_name, cpuid) 튜플로 분리합니다."""
    raw = (host_value or "").strip()
    if "|" in raw:
        host_part, cpuid_part = raw.split("|", 1)
        return host_part.strip(), cpuid_part.strip()
    return raw, ""


def _get_git_info(cwd: str | None = None) -> dict[str, str]:
    repo_dir = cwd or os.path.dirname(os.path.abspath(__file__))
    commit_hash = "unknown"
    commit_msg = ""
    dirty_str = "false"

    try:
        res_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if res_hash.returncode == 0 and res_hash.stdout.strip():
            commit_hash = res_hash.stdout.strip()
    except Exception:
        pass

    try:
        res_msg = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if res_msg.returncode == 0 and res_msg.stdout.strip():
            commit_msg = res_msg.stdout.strip().splitlines()[0]
    except Exception:
        pass

    try:
        res_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if res_status.returncode == 0:
            dirty_str = "true" if res_status.stdout.strip() else "false"
    except Exception:
        pass

    return {
        "commit": commit_hash,
        "message": commit_msg,
        "dirty": dirty_str,
    }


def build_v2_payload(
    version_str: str,
    user_name: str | None = None,
    app_name: str = "PrintShopApp",
    git_commit: str | None = None,
    git_message: str | None = None,
    mode: str = "production",
    host_name: str | None = None,
    cpuid: str | None = None,
    dirty: bool | str | None = None,
    build_id: str | None = None,
    cwd: str | None = None,
) -> dict[str, str]:
    """DESCRIPTOR_VERSION = 2 페이로드 딕셔너리를 생성합니다 (host 필드에 '<host>|<cpuid>' 기록)."""
    if not user_name:
        try:
            user_name = getpass.getuser()
        except Exception:
            user_name = "Unknown"

    resolved_host_with_cpuid = format_host_with_cpuid(host_name=host_name, cpuid=cpuid)
    git_info = _get_git_info(cwd=cwd)
    resolved_commit = git_commit if git_commit is not None else git_info["commit"]
    resolved_msg = git_message if git_message is not None else git_info["message"]

    if dirty is None:
        resolved_dirty = git_info["dirty"]
    elif isinstance(dirty, bool):
        resolved_dirty = "true" if dirty else "false"
    else:
        resolved_dirty = "true" if str(dirty).strip().lower() in ("1", "true", "yes", "dirty") else "false"

    timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    resolved_build_id = build_id or f"{timestamp}-{resolved_commit}"

    return {
        "version": str(version_str),
        "mode": str(mode or "production"),
        "build_id": str(resolved_build_id),
        "time": str(timestamp),
        "who": str(user_name),
        "host": resolved_host_with_cpuid,
        "dirty": resolved_dirty,
        "app": str(app_name),
        "commit": str(resolved_commit),
        "message": str(resolved_msg),
    }


def get_v2_block_size(exe_path: str) -> int:
    """파일 끝이 SIGVER3! + desc_ver=2 트레일러인 경우 전체 블록 바이트 길이를 반환합니다."""
    if not os.path.isfile(exe_path):
        return 0
    file_size = os.path.getsize(exe_path)
    if file_size < SIGN_TRAILER_SIZE_V2:
        return 0

    with open(exe_path, "rb") as f:
        f.seek(-SIGN_TRAILER_SIZE_V2, os.SEEK_END)
        trailer_raw = f.read(SIGN_TRAILER_SIZE_V2)
        magic, desc_ver, payload_len, sig_len, _flags, _reserved = _SIGN_TRAILER_STRUCT_V2.unpack(trailer_raw)
        if magic != SIGN_MAGIC or desc_ver != DESCRIPTOR_VERSION:
            return 0
        total_block = payload_len + sig_len + SIGN_TRAILER_SIZE_V2
        if SIGN_TRAILER_SIZE_V2 <= total_block <= file_size:
            return total_block
    return 0


def strip_v2_eof_metadata(exe_path: str) -> int:
    """EXE 끝에 주입된 desc_ver=2 블록을 제거하고 제거된 바이트 수를 반환합니다."""
    total_block = get_v2_block_size(exe_path)
    if total_block <= 0:
        return 0
    file_size = os.path.getsize(exe_path)
    with open(exe_path, "r+b") as f:
        f.truncate(file_size - total_block)
    return total_block


def sign_and_inject_v2(
    exe_path: str,
    version_str: str,
    private_key: Ed25519PrivateKey,
    user_name: str | None = None,
    app_name: str | None = None,
    git_commit: str | None = None,
    git_message: str | None = None,
    mode: str = "production",
    host_name: str | None = None,
    cpuid: str | None = None,
    dirty: bool | str | None = None,
    build_id: str | None = None,
    cwd: str | None = None,
    flags: int = 0,
) -> dict[str, Any]:
    """DESCRIPTOR_VERSION = 2 서명 메타데이터를 EXE 끝에 주입합니다."""
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f"대상 실행 파일을 찾을 수 없습니다: {exe_path}")

    removed_prev = strip_v2_eof_metadata(exe_path)
    if removed_prev > 0:
        logd(f"♻️ [기존 v2 EOF 블록 제거] {removed_prev}B 제거 후 재주입합니다: {exe_path}")

    resolved_app = app_name or os.path.splitext(os.path.basename(exe_path))[0]
    base_payload = build_v2_payload(
        version_str=version_str,
        user_name=user_name,
        app_name=resolved_app,
        git_commit=git_commit,
        git_message=git_message,
        mode=mode,
        host_name=host_name,
        cpuid=cpuid,
        dirty=dirty,
        build_id=build_id,
        cwd=cwd,
    )

    signed_payload = dict(base_payload)
    signed_payload["payload_sha256"] = _compute_sha256_hex(_canonical_json_bytes(base_payload))

    payload_bytes = _canonical_json_bytes(signed_payload)
    sig_bytes = private_key.sign(payload_bytes)
    trailer_bytes = _SIGN_TRAILER_STRUCT_V2.pack(
        SIGN_MAGIC,
        DESCRIPTOR_VERSION,
        len(payload_bytes),
        len(sig_bytes),
        int(flags) & 0xFF,
        b"\\x00" * 48,
    )

    with open(exe_path, "ab") as f:
        f.write(payload_bytes)
        f.write(sig_bytes)
        f.write(trailer_bytes)

    total_injected = len(payload_bytes) + len(sig_bytes) + SIGN_TRAILER_SIZE_V2
    exe_sha256 = _compute_file_sha256(exe_path)

    return {
        "items": signed_payload,
        "desc_ver": DESCRIPTOR_VERSION,
        "flags": int(flags) & 0xFF,
        "signature_b64": base64.b64encode(sig_bytes).decode("ascii"),
        "exe_sha256": exe_sha256,
        "sizes": {
            "payload_bytes": len(payload_bytes),
            "signature_bytes": len(sig_bytes),
            "trailer_bytes": SIGN_TRAILER_SIZE_V2,
            "total_injected_bytes": total_injected,
            "fields": {k: len(str(signed_payload.get(k, "")).encode("utf-8")) for k in ALL_META_KEYS_V2},
        },
        "file_size_bytes": os.path.getsize(exe_path),
    }


def verify_and_read_v2(exe_path: str, public_key: Ed25519PublicKey) -> dict[str, Any]:
    """DESCRIPTOR_VERSION = 2 서명 메타데이터를 읽고 Ed25519 서명 및 payload_sha256를 검증합니다."""
    if not os.path.isfile(exe_path):
        return {"verified": False, "error": "파일 없음"}

    file_size = os.path.getsize(exe_path)
    if file_size < SIGN_TRAILER_SIZE_V2:
        return {"verified": False, "error": "파일 크기 부족"}

    with open(exe_path, "rb") as f:
        f.seek(-SIGN_TRAILER_SIZE_V2, os.SEEK_END)
        trailer_raw = f.read(SIGN_TRAILER_SIZE_V2)
        magic, desc_ver, payload_len, sig_len, flags, _reserved = _SIGN_TRAILER_STRUCT_V2.unpack(trailer_raw)

        if magic != SIGN_MAGIC or desc_ver != DESCRIPTOR_VERSION:
            return {"verified": False, "error": "유효한 SIGVER3! (v2) 트레일러를 찾을 수 없습니다."}

        total_block = payload_len + sig_len + SIGN_TRAILER_SIZE_V2
        if payload_len <= 0 or sig_len <= 0 or total_block > file_size:
            return {"verified": False, "error": "서명 데이터 크기 불일치"}

        f.seek(-total_block, os.SEEK_END)
        payload_bytes = f.read(payload_len)
        sig_bytes = f.read(sig_len)

    try:
        public_key.verify(sig_bytes, payload_bytes)
    except InvalidSignature:
        return {"verified": False, "error": "전자서명 검증 실패 (메타데이터 변조 또는 공개키 불일치)"}
    except Exception as exc:
        return {"verified": False, "error": f"공개키 검증 오류: {exc}"}

    try:
        items = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        return {"verified": False, "error": f"JSON 파싱 실패: {exc}"}

    recorded_sha = items.get("payload_sha256")
    core_items = {k: v for k, v in items.items() if k != "payload_sha256"}
    recalculated_sha = _compute_sha256_hex(_canonical_json_bytes(core_items))
    if not recorded_sha or recorded_sha != recalculated_sha:
        return {"verified": False, "error": "페이로드 SHA-256 해시 불일치"}

    host_only, cpuid_val = parse_host_and_cpuid(items.get("host"))

    return {
        "verified": True,
        "items": items,
        "host_name": host_only,
        "cpuid": cpuid_val,
        "desc_ver": desc_ver,
        "flags": flags,
        "payload_sha256": recalculated_sha,
        "sizes": {
            "payload_bytes": payload_len,
            "signature_bytes": sig_len,
            "trailer_bytes": SIGN_TRAILER_SIZE_V2,
            "total_injected_bytes": total_block,
            "fields": {k: len(str(items.get(k, "")).encode("utf-8")) for k in ALL_META_KEYS_V2},
        },
        "file_size_bytes": file_size,
    }
