import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from dotenv import load_dotenv

from Common.log import set_file_tag, logd, loge ;set_file_tag("CRYPTO")

try:
    from Common.Version.exe_version_public_key import EmbeddedPublicKey, EMBEDDED_PUBLIC_KEY_PEM
except ImportError:
    try:
        from Common.Version.exe_version_public_key import EmbeddedPublicKey, EMBEDDED_PUBLIC_KEY_PEM
    except ImportError:
        EmbeddedPublicKey = None
        EMBEDDED_PUBLIC_KEY_PEM = ""

try:
    from Common.Version.exe_version_desc_v1 import (
        ALL_META_KEYS_V1,
        DESCRIPTOR_VERSION as DESCRIPTOR_VERSION_V1,
        SIGN_MAGIC,
        SIGN_TRAILER_SIZE_V1,
        _SIGN_TRAILER_STRUCT_V1,
        _canonical_json_bytes,
        build_v1_payload,
        get_v1_block_size,
        sign_and_inject_v1,
        strip_v1_eof_metadata,
        verify_and_read_v1,
    )
    from Common.Version.exe_version_desc_v2 import (
        ALL_META_KEYS_V2,
        DESCRIPTOR_VERSION as DESCRIPTOR_VERSION_V2,
        SIGN_TRAILER_SIZE_V2,
        _SIGN_TRAILER_STRUCT_V2,
        build_v2_payload,
        format_host_with_cpuid,
        get_cpuid,
        get_v2_block_size,
        parse_host_and_cpuid,
        sign_and_inject_v2,
        strip_v2_eof_metadata,
        verify_and_read_v2,
    )
except ImportError:
    from Common.Version.exe_version_desc_v1 import (
        ALL_META_KEYS_V1,
        DESCRIPTOR_VERSION as DESCRIPTOR_VERSION_V1,
        SIGN_MAGIC,
        SIGN_TRAILER_SIZE_V1,
        _SIGN_TRAILER_STRUCT_V1,
        _canonical_json_bytes,
        build_v1_payload,
        get_v1_block_size,
        sign_and_inject_v1,
        strip_v1_eof_metadata,
        verify_and_read_v1,
    )
    from Common.Version.exe_version_desc_v2 import (
        ALL_META_KEYS_V2,
        DESCRIPTOR_VERSION as DESCRIPTOR_VERSION_V2,
        SIGN_TRAILER_SIZE_V2,
        _SIGN_TRAILER_STRUCT_V2,
        build_v2_payload,
        format_host_with_cpuid,
        get_cpuid,
        get_v2_block_size,
        parse_host_and_cpuid,
        sign_and_inject_v2,
        strip_v2_eof_metadata,
        verify_and_read_v2,
    )

DESCRIPTOR_VERSION = DESCRIPTOR_VERSION_V2
_SIGN_TRAILER_STRUCT = _SIGN_TRAILER_STRUCT_V2
SIGN_TRAILER_SIZE = SIGN_TRAILER_SIZE_V2
ALL_META_KEYS = ALL_META_KEYS_V2

load_dotenv()

DEFAULT_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAExamplePublicKeyReplaceBeforeProduction1234567890=
-----END PUBLIC KEY-----"""

DEFAULT_COMPANY_NAME = "PrintShop"
DEFAULT_LEGAL_COPYRIGHT = f"Copyright (C) {DEFAULT_COMPANY_NAME}"
VERSION_TRANSLATION = "VarFileInfo([VarStruct(u'Translation', [1033, 1200])])"

VERSION_STRING_STRUCT_SPECS: tuple[tuple[str, str], ...] = (
    ("CompanyName", "{company_name}"),
    ("FileDescription", "{app_name} Executable"),
    ("FileVersion", "{dotted}"),
    ("InternalName", "{app_name}"),
    ("LegalCopyright", "{copyright}"),
    ("OriginalFilename", "{app_name}.exe"),
    ("ProductName", "{app_name}"),
    ("ProductVersion", "{version_str}"),
)


def _get_embedded_public_key_pem() -> str:
    if EmbeddedPublicKey is not None:
        cls_pem = getattr(EmbeddedPublicKey, "EMBEDDED_PUBLIC_KEY_PEM", "") or ""
        if cls_pem.strip():
            return cls_pem.strip()
    return (EMBEDDED_PUBLIC_KEY_PEM or "").strip()

def load_private_key_from_env(
    env_var: str = "EXE_VERSION_PRIVATE_KEY_PEM",
    file_env_var: str = "EXE_VERSION_PRIVATE_KEY_PATH",
    fallback_paths: tuple[str, ...] = (),
) -> Ed25519PrivateKey:
    """환경변수(PEM 문자열) 또는 개인키 파일에서 서명용 Ed25519 개인키를 로드합니다."""
    raw_pem = os.getenv(env_var, "").strip()
    pem_source = ""

    if raw_pem:
        pem_source = raw_pem
    else:
        key_file_path = os.getenv(file_env_var, "").strip()
        candidate_paths = [p for p in (key_file_path, *fallback_paths) if p]
        for path in candidate_paths:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    pem_source = f.read().strip()
                if pem_source:
                    break

    if not pem_source:
        raise RuntimeError(
            f"서명용 개인키 환경변수 '{env_var}'가 비어 있고, 개인키 파일('{file_env_var}')도 찾지 못했습니다."
        )

    normalized = (
        pem_source.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\r\n", "\n")
        .strip()
    )
    begin_idx = normalized.find("-----BEGIN ")
    if begin_idx > 0:
        normalized = normalized[begin_idx:]

    key = serialization.load_pem_private_key(normalized.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("Ed25519 개인키 형식만 지원합니다.")
    return key

def load_public_key(public_key_pem: str | bytes | None = None) -> Ed25519PublicKey:
    """앱 및 외부 검증기에서 서명 검증용 Ed25519 공개키(PEM)를 로드합니다."""
    env_pub = os.getenv("EXE_VERSION_PUBLIC_KEY_PEM", "").strip()
    embedded_pub = _get_embedded_public_key_pem()

    if public_key_pem is not None:
        source = public_key_pem
    elif env_pub:
        source = env_pub
    elif embedded_pub:
        source = embedded_pub
    else:
        source = DEFAULT_PUBLIC_KEY_PEM

    if isinstance(source, str):
        pem_bytes = source.replace("\\\\n", "\\n").encode("utf-8")
    else:
        pem_bytes = source

    key = serialization.load_pem_public_key(pem_bytes)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("Ed25519 공개키 형식만 지원합니다.")
    return key


def compute_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(file_path: str) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256_sidecar(target_file: str) -> str:
    """<파일명>.sha256 체크섬 파일을 생성하고 SHA-256 16진수 문자열을 반환합니다."""
    sha_hex = compute_file_sha256(target_file)
    sha_path = f"{target_file}.sha256"
    with open(sha_path, "w", encoding="utf-8") as f:
        f.write(f"{sha_hex}  {os.path.basename(target_file)}\\n")
    return sha_hex


def _parse_ver_tuple(version_str: str) -> tuple[int, int, int, int]:
    """버전 문자열에서 정수 4-튜플을 안전하게 추출합니다."""
    clean = (version_str or "1.0.0").strip().lstrip("vV").split("-")[0]
    nums = [int(m) for m in re.findall(r"\\d+", clean)]
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums[:4])

def _build_string_structs(
    version_str: str,
    dotted: str,
    app_name: str,
    company_name: str = DEFAULT_COMPANY_NAME,
) -> str:
    context = {
        "app_name": app_name,
        "company_name": company_name,
        "dotted": dotted,
        "version_str": version_str,
        "copyright": f"Copyright (C) {company_name}",
    }
    lines: list[str] = []
    for key, tmpl in VERSION_STRING_STRUCT_SPECS:
        val = tmpl.format(**context)
        lines.append(f"          StringStruct(u'{key}', u'{val}'),")
    return "\n".join(lines)


def generate_win_version_info(
    version_str: str,
    output_path: str = "version_info.txt",
    app_name: str = "PrintShopApp",
    company_name: str = DEFAULT_COMPANY_NAME,
):
    """SemVer(예: 1.2.0)를 파싱하여 PyInstaller용 Windows 리소스(version_info.txt) 동적 생성"""
    ver_tuple = _parse_ver_tuple(version_str)
    dotted = ".".join(str(n) for n in ver_tuple)
    string_structs_block = _build_string_structs(
        version_str=version_str,
        dotted=dotted,
        app_name=app_name,
        company_name=company_name,
    )

    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [
{string_structs_block}
          ]
        )
      ]
    ),
    {VERSION_TRANSLATION}
  ]
)
"""
    parent_dir = os.path.dirname(os.path.abspath(output_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def get_git_info(cwd: str = None) -> dict:
    """Git Commit 해시(단축), Commit 메시지, 작업트리 dirty 여부를 조회합니다."""
    try:
        from .exe_version_desc_v1 import _get_git_info as _v1_git_info
    except ImportError:
        from exe_version_desc_v1 import _get_git_info as _v1_git_info
    return _v1_git_info(cwd=cwd)


def build_all_items_payload(
    version_str: str,
    user_name: str = None,
    app_name: str = "PrintShopApp",
    git_commit: str = None,
    git_message: str = None,
    mode: str = "production",
    host_name: str = None,
    dirty: bool | str | None = None,
    build_id: str = None,
    cwd: str = None,
) -> dict:
    """DESCRIPTOR_VERSION = 1 페이로드 딕셔너리를 생성합니다."""
    return build_v1_payload(
        version_str=version_str,
        user_name=user_name,
        app_name=app_name,
        git_commit=git_commit,
        git_message=git_message,
        mode=mode,
        host_name=host_name,
        dirty=dirty,
        build_id=build_id,
        cwd=cwd,
    )


def _detect_eof_descriptor_version(exe_path: str) -> int | None:
    """파일 끝 트레일러에서 magic과 desc_ver(1 또는 2)를 확인합니다."""
    if not os.path.isfile(exe_path):
        return None
    file_size = os.path.getsize(exe_path)
    if file_size < SIGN_TRAILER_SIZE_V1:
        return None

    with open(exe_path, "rb") as f:
        f.seek(-SIGN_TRAILER_SIZE_V1, os.SEEK_END)
        trailer_raw = f.read(SIGN_TRAILER_SIZE_V1)
        magic, desc_ver, _payload_len, _sig_len, _reserved = _SIGN_TRAILER_STRUCT_V1.unpack(trailer_raw)
        if magic != SIGN_MAGIC:
            return None
        return desc_ver


def strip_existing_eof_metadata(exe_path: str) -> int:
    """EXE 끝에 이미 주입된 SIGVER3! 블록(v1 또는 v2)을 제거하고 제거된 바이트 수를 반환합니다."""
    desc_ver = _detect_eof_descriptor_version(exe_path)
    if desc_ver == DESCRIPTOR_VERSION_V2:
        return strip_v2_eof_metadata(exe_path)
    if desc_ver == DESCRIPTOR_VERSION_V1:
        return strip_v1_eof_metadata(exe_path)
    return 0


def sign_exe_authenticode(exe_path: str, cwd: str | None = None) -> bool:
    """
    signtool.exe를 이용해 EXE 코드 서명(Authenticode)을 적용합니다.
    CODESIGN_PFX_PATH가 설정되지 않으면 서명을 건너뛰고 False를 반환합니다.
    """
    if not exe_path or not os.path.isfile(exe_path):
        raise FileNotFoundError(f"서명할 EXE 파일이 없습니다: {exe_path}")

    pfx_path = os.getenv("CODESIGN_PFX_PATH", "").strip()
    if not pfx_path:
        logd(f"⚠️ [Authenticode 생략] CODESIGN_PFX_PATH 미설정: {exe_path}")
        return False

    pfx_password = os.getenv("CODESIGN_PFX_PASSWORD", "").strip()
    timestamp_url = os.getenv("CODESIGN_TIMESTAMP_URL", "http://timestamp.digicert.com").strip()

    signtool = shutil.which("signtool") or shutil.which("signtool.exe")
    if not signtool:
        raise RuntimeError("signtool.exe를 찾을 수 없습니다. Windows SDK 설치 경로를 확인하세요.")

    cmd = [signtool, "sign", "/fd", "SHA256", "/f", pfx_path]
    if pfx_password:
        cmd.extend(["/p", pfx_password])
    if timestamp_url:
        cmd.extend(["/tr", timestamp_url, "/td", "SHA256"])
    cmd.append(exe_path)

    res = subprocess.run(
        cmd,
        cwd=cwd or os.path.dirname(os.path.abspath(exe_path)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError(f"Authenticode 서명 실패(exit={res.returncode}): {res.stdout or res.stderr}")

    logd(f"🔏 [Authenticode 완료] {os.path.basename(exe_path)}")
    return True


def sign_and_inject_metadata_to_exe(
    exe_path: str,
    version_str: str,
    user_name: str = None,
    app_name: str = None,
    git_commit: str = None,
    git_message: str = None,
    mode: str = "production",
    host_name: str = None,
    cpuid: str = None,
    dirty: bool | str | None = None,
    build_id: str = None,
    cwd: str = None,
    private_key: Ed25519PrivateKey | None = None,
    authenticode: bool = False,
    write_sha256: bool = False,
    descriptor_version: int = DESCRIPTOR_VERSION_V1,
) -> dict:
    """
    메타데이터 payload + payload_sha256 + Ed25519 서명을 EXE 끝에 주입합니다.
    descriptor_version=1은 exe_version_desc_v1, descriptor_version=2는 exe_version_desc_v2로 위임합니다.
    """
    if not os.path.exists(exe_path):
        raise FileNotFoundError(f"대상 실행 파일을 찾을 수 없습니다: {exe_path}")

    removed_prev = strip_existing_eof_metadata(exe_path)
    if removed_prev > 0:
        logd(f"♻️ [기존 EOF 블록 제거] {removed_prev}B 제거 후 재주입합니다: {exe_path}")

    priv_key = private_key or load_private_key_from_env()
    resolved_app = app_name or os.path.splitext(os.path.basename(exe_path))[0]
    ver_int = int(descriptor_version)

    if ver_int == DESCRIPTOR_VERSION_V2:
        result = sign_and_inject_v2(
            exe_path=exe_path,
            version_str=version_str,
            private_key=priv_key,
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
    elif ver_int == DESCRIPTOR_VERSION_V1:
        result = sign_and_inject_v1(
            exe_path=exe_path,
            version_str=version_str,
            private_key=priv_key,
            user_name=user_name,
            app_name=resolved_app,
            git_commit=git_commit,
            git_message=git_message,
            mode=mode,
            host_name=host_name,
            dirty=dirty,
            build_id=build_id,
            cwd=cwd,
        )
    else:
        raise ValueError(f"지원하지 않는 descriptor_version입니다: {descriptor_version}")

    if authenticode:
        sign_exe_authenticode(exe_path, cwd=cwd)

    exe_sha256 = write_sha256_sidecar(exe_path) if write_sha256 else compute_file_sha256(exe_path)
    result["exe_sha256"] = exe_sha256
    result["file_size_bytes"] = os.path.getsize(exe_path)

    signed_payload = result["items"]
    total_injected = result["sizes"]["total_injected_bytes"]
    logd(
        f"[SIGNED METADATA INJECTED v{ver_int}] exe={os.path.abspath(exe_path)} | "
        f"version={signed_payload['version']} | host={signed_payload['host']} | "
        f"payload_sha256={signed_payload['payload_sha256'][:12]}... | "
        f"injected={total_injected}B | exe_sha256={exe_sha256[:12]}..."
    )
    return result


def verify_and_read_exe_metadata(
    exe_path: str,
    public_key_pem: str | bytes | None = None,
) -> dict:
    """
    EXE 파일 끝에서 서명된 메타데이터(v1 또는 v2)를 읽고,
    Ed25519 전자서명 및 payload_sha256 무결성을 검증합니다.
    """
    if not os.path.exists(exe_path):
        return {"verified": False, "error": "파일 없음"}

    file_size = os.path.getsize(exe_path)
    if file_size < SIGN_TRAILER_SIZE_V1:
        return {"verified": False, "error": "파일 크기 부족"}

    desc_ver = _detect_eof_descriptor_version(exe_path)
    if desc_ver not in (DESCRIPTOR_VERSION_V1, DESCRIPTOR_VERSION_V2):
        return {"verified": False, "error": "유효한 SIGVER3! 트레일러를 찾을 수 없습니다."}

    try:
        pub_key = load_public_key(public_key_pem)
    except Exception as exc:
        return {"verified": False, "error": f"공개키 로드/검증 오류: {exc}"}

    if desc_ver == DESCRIPTOR_VERSION_V2:
        return verify_and_read_v2(exe_path=exe_path, public_key=pub_key)
    return verify_and_read_v1(exe_path=exe_path, public_key=pub_key)


def extract_version_from_exe(exe_path: str) -> str | None:
    """EXE에서 서명/해시를 검증한 뒤 version 문자열을 반환합니다. 실패 시 None."""
    result = verify_and_read_exe_metadata(exe_path)
    if not result.get("verified"):
        loge(f"EXE 버전 추출/검증 실패 ({exe_path}): {result.get('error')}", tag="EXE_SIGN")
        return None

    items = result["items"]
    ver = items.get("version")
    return str(ver) if ver is not None else None


def get_runtime_decrypted_version(fallback_version: str = "1.2.0") -> str:
    """실행 중인 프로세스(.exe) 자신의 서명된 버전을 검증하여 반환합니다."""
    if not getattr(sys, "frozen", False):
        return f"{fallback_version} (Dev Mode)"
    extracted = extract_version_from_exe(sys.executable)
    return extracted if extracted else f"{fallback_version} (Verify Fallback)"


def read_bundled_version_txt(default_version: str = "1.2.0") -> str:
    """개발 환경 또는 빌드된 EXE(.exe) 내부/인접 경로에서 version.txt를 읽어 반환합니다."""
    candidate_paths: list[str] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate_paths.append(os.path.join(meipass, "version.txt"))
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidate_paths.append(os.path.join(exe_dir, "version.txt"))
        candidate_paths.append(os.path.join(os.path.dirname(exe_dir), "version.txt"))
    else:
        cur = os.path.abspath(os.path.dirname(__file__))
        for _ in range(6):
            candidate_paths.append(os.path.join(cur, "version.txt"))
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent

    for p in candidate_paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8-sig") as f:
                    ver = f.read().strip()
                if ver:
                    return ver
            except Exception:
                pass

    return default_version


def encrypt_all_items_to_exe(exe_path: str, version_str: str, **kwargs) -> dict:
    return sign_and_inject_metadata_to_exe(exe_path=exe_path, version_str=version_str, **kwargs)


def encrypt_and_append_version(exe_path: str, version_str: str, **kwargs) -> dict:
    return sign_and_inject_metadata_to_exe(exe_path=exe_path, version_str=version_str, **kwargs)


def decrypt_all_items_from_exe(exe_path: str) -> dict:
    return verify_and_read_exe_metadata(exe_path=exe_path)


def _parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EXE EOF 메타데이터 전자서명(SIGVER3! / Ed25519 / SHA-256 / Authenticode) 및 검증 CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_sign = subparsers.add_parser("sign", help="EXE 파일 끝에 서명된 메타데이터 주입")
    p_sign.add_argument("exe_path", help="대상 .exe 경로")
    p_sign.add_argument("--version", required=True, help="버전 문자열 (예: v1.2.0-production)")
    p_sign.add_argument("--app", default="PrintShopApp", help="앱 이름")
    p_sign.add_argument("--mode", default="production", help="빌드 모드")
    p_sign.add_argument("--desc-ver", type=int, default=DESCRIPTOR_VERSION_V1, choices=[1, 2], help="디스크립터 버전 (1 또는 2)")
    p_sign.add_argument("--cwd", default=None, help="Git 메타데이터 수집 기준 디렉터리")
    p_sign.add_argument("--authenticode", action="store_true", help="Authenticode 코드 서명 적용")
    p_sign.add_argument("--sha256", action="store_true", help=".sha256 체크섬 파일 생성")

    p_verify = subparsers.add_parser("verify", help="EXE 서명/해시 검증 및 전체 메타데이터 출력")
    p_verify.add_argument("exe_path", help="대상 .exe 경로")

    p_ver = subparsers.add_parser("version", help="서명 검증 후 버전 문자열 출력")
    p_ver.add_argument("exe_path", help="대상 .exe 경로")

    p_self = subparsers.add_parser("self", help="현재 실행 중인 프로세스(.exe)의 서명 검증 및 버전 출력")

    return parser.parse_args(argv)


def _cli_main(argv: list[str] | None = None) -> int:
    args = _parse_cli_args(argv)

    if args.command == "sign":
        res = sign_and_inject_metadata_to_exe(
            exe_path=args.exe_path,
            version_str=args.version,
            app_name=args.app,
            mode=args.mode,
            cwd=args.cwd,
            authenticode=args.authenticode,
            write_sha256=args.sha256,
            descriptor_version=args.desc_ver,
        )
        logd(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.command == "verify":
        res = verify_and_read_exe_metadata(args.exe_path)
        if os.path.isfile(args.exe_path):
            res["exe_sha256"] = compute_file_sha256(args.exe_path)
        logd(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("verified") else 1

    if args.command == "version":
        ver = extract_version_from_exe(args.exe_path)
        if ver is None:
            loge("버전 추출/검증 실패")
            return 1
        logd(ver)
        return 0

    if args.command == "self":
        ver = get_runtime_decrypted_version(fallback_version=read_bundled_version_txt())
        logd(ver)
        return 0

    loge(f"알 수 없는 명령: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(_cli_main())

# '''

# with open("exe_version_desc_v1.py", "w", encoding="utf-8") as f:
#     f.write(v1_code.lstrip("\n"))

# with open("exe_version_desc_v2.py", "w", encoding="utf-8") as f:
#     f.write(v2_code.lstrip("\n"))

# with open("exe_version_crypto_2.py", "w", encoding="utf-8") as f:
#     f.write(dispatcher_code.lstrip("\n"))

# print("Generated exe_version_desc_v1.py, exe_version_desc_v2.py, exe_version_crypto_2.py")