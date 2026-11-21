import argparse
import base64
import os
import tempfile
import types
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from Common.log import set_file_tag, logd, loge ;set_file_tag("CRYPTO")

DEFAULT_PUBLIC_KEY_FILENAME = "ed25519_public.pem"
DEFAULT_MODULE_FILENAME = "exe_version_public_key.py"
DEFAULT_CLASS_NAME = "EmbeddedPublicKey"
DEFAULT_VAR_NAME = "EMBEDDED_PUBLIC_KEY_PEM"

DEFAULT_SAMPLE_PAYLOAD = b"PRINTSHOP_PUBKEY_SELFTEST_V1"
DEFAULT_SAMPLE_SIGNATURE_B64 = os.getenv("EXE_VERSION_SAMPLE_SIG_B64", "").strip()


def resolve_default_public_key_module_path(project_root: str | Path | None = None) -> Path:
    """기본 공개키 상수 모듈(.py) 출력/조회 경로를 결정합니다."""
    if project_root:
        root = Path(project_root).resolve()
        candidate = root / "src" / "Common" / "Version" / DEFAULT_MODULE_FILENAME
        if candidate.parent.is_dir():
            return candidate
    here = Path(__file__).resolve()
    if here.parent.name == "Version":
        return here.with_name(DEFAULT_MODULE_FILENAME)
    return here.parent / DEFAULT_MODULE_FILENAME


def candidate_public_key_paths(
    filename: str = DEFAULT_PUBLIC_KEY_FILENAME,
    start_dir: Path | None = None,
) -> list[Path]:
    """공개키 PEM 파일을 찾을 후보 경로 목록을 우선순위대로 생성합니다."""
    candidates: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path | None) -> None:
        if p is None:
            return
        try:
            resolved = str(p.resolve())
        except Exception:
            resolved = str(p)
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(p)

    env_key_file = os.getenv("EXE_VERSION_PUBLIC_KEY_PATH", "").strip()
    if env_key_file:
        _add(Path(env_key_file))

    env_secrets_dir = os.getenv("SECRETS_DIR", "").strip()
    if env_secrets_dir:
        sdir = Path(env_secrets_dir)
        _add(sdir / filename)
        _add(sdir / "keys" / filename)

    base = (start_dir or Path(__file__).resolve().parent).resolve()
    cur_script = base
    for _ in range(6):
        _add(cur_script / "secrets" / filename)
        _add(cur_script / "secrets" / "keys" / filename)
        _add(cur_script / "keys" / filename)
        _add(cur_script / filename)
        if cur_script.parent == cur_script:
            break
        cur_script = cur_script.parent

    cur_cwd = Path.cwd().resolve()
    for _ in range(6):
        _add(cur_cwd / "secrets" / filename)
        _add(cur_cwd / "secrets" / "keys" / filename)
        _add(cur_cwd / "keys" / filename)
        _add(cur_cwd / filename)
        if cur_cwd.parent == cur_cwd:
            break
        cur_cwd = cur_cwd.parent

    return candidates


def find_public_key_file(
    pem_path: Path | None = None,
    filename: str = DEFAULT_PUBLIC_KEY_FILENAME,
) -> Path:
    """지정된 경로 또는 후보 경로에서 공개키 PEM 파일을 찾습니다."""
    if pem_path is not None:
        if pem_path.is_file():
            return pem_path
        raise FileNotFoundError(f"지정한 공개키 PEM 파일을 찾을 수 없습니다: {pem_path}")

    searched = candidate_public_key_paths(filename=filename)
    for candidate in searched:
        if candidate.is_file():
            return candidate

    searched_text = "\n  - ".join(str(p) for p in searched)
    raise FileNotFoundError(
        f"공개키 파일 '{filename}'을(를) 찾을 수 없습니다. 탐색 경로:\n  - {searched_text}"
    )


def load_ed25519_public_key_from_pem_text(pem_text: str) -> Ed25519PublicKey:
    """PEM 문자열에서 Ed25519 공개키 객체를 로드합니다."""
    if not isinstance(pem_text, str) or not pem_text.strip():
        raise ValueError("공개키 PEM 문자열이 비어 있습니다.")
    pub_key = serialization.load_pem_public_key(pem_text.strip().encode("utf-8"))
    if not isinstance(pub_key, Ed25519PublicKey):
        raise TypeError("Ed25519 공개키 형식만 지원합니다.")
    return pub_key


def load_embedded_public_key_from_source(
    source_code: str,
    virtual_name: str = "_memory_exe_version_public_key",
) -> tuple[str, Ed25519PublicKey]:
    """메모리 문자열(source_code)에서 동적 모듈을 구성해 공개키를 로드합니다."""
    if not isinstance(source_code, str) or not source_code.strip():
        raise ValueError("공개키 모듈 소스 문자열이 비어 있습니다.")

    mod = types.ModuleType(virtual_name)
    compiled = compile(source_code, filename=f"<{virtual_name}>", mode="exec")
    exec(compiled, mod.__dict__)

    key_cls = getattr(mod, DEFAULT_CLASS_NAME, None)
    embedded_pem = getattr(key_cls, DEFAULT_VAR_NAME, None) if key_cls is not None else None
    if not embedded_pem:
        embedded_pem = getattr(mod, DEFAULT_VAR_NAME, None)

    pub_key = load_ed25519_public_key_from_pem_text(embedded_pem or "")
    return embedded_pem.strip(), pub_key


def load_embedded_public_key_pem(module_path: Path) -> tuple[str, Ed25519PublicKey]:
    """디스크에 저장된 공개키 .py 모듈을 읽어 메모리 동적 모듈 경유로 공개키를 로드합니다."""
    resolved = Path(module_path).resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise FileNotFoundError(f"공개키 모듈 파일이 없거나 비어 있습니다: {resolved}")

    source_code = resolved.read_text(encoding="utf-8")
    return load_embedded_public_key_from_source(
        source_code=source_code,
        virtual_name=f"_file_exe_version_public_key_{resolved.stem}",
    )


def verify_public_key_with_sample(
    pub_key: Ed25519PublicKey,
    sample_payload: bytes = DEFAULT_SAMPLE_PAYLOAD,
    sample_signature_b64: str | None = None,
) -> tuple[bool, str]:
    """로드된 Ed25519 공개키로 샘플을 검증해 (성공여부, 사유)를 반환합니다."""
    sig_b64 = (
        sample_signature_b64
        if sample_signature_b64 is not None
        else os.getenv("EXE_VERSION_SAMPLE_SIG_B64", DEFAULT_SAMPLE_SIGNATURE_B64)
    ).strip()

    try:
        der_bytes = pub_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if not der_bytes:
            return False, "공개키 DER 직렬화 결과가 비어 있습니다."

        if sig_b64:
            signature = base64.b64decode(sig_b64, validate=True)
            pub_key.verify(signature, sample_payload)
            return True, f"샘플 서명 검증 성공 (payload={sample_payload.decode('utf-8', errors='replace')})"

        return True, f"공개키 객체 검증 성공 (DER={len(der_bytes)}B, 샘플 서명 미지정)"
    except InvalidSignature:
        return False, "샘플 서명 검증 실패: 서명이 공개키와 일치하지 않거나 데이터가 변조되었습니다."
    except Exception as exc:
        return False, f"샘플 검증 실패: {exc}"


def _format_indented_str_literal(value: str, indent: str = "        ") -> str:
    """여러 줄 문자열 리터럴을 PEP 8 스타일의 괄호 감싼 줄별 문자열로 포맷합니다."""
    lines = value.splitlines(keepends=True)
    if not lines:
        return '""'
    formatted = "\n".join(f"{indent}{line!r}" for line in lines)
    return f"(\n{formatted}\n    )"


def build_public_key_module_content(pem_path: Path | None = None) -> tuple[str, Path]:
    """공개키 PEM을 검증하고 EmbeddedPublicKey 클래스 모듈 소스 문자열과 원본 PEM 경로를 반환합니다."""
    resolved_pem = find_public_key_file(pem_path=pem_path)

    raw_bytes = resolved_pem.read_bytes().strip()
    pub_key = serialization.load_pem_public_key(raw_bytes)
    if not isinstance(pub_key, Ed25519PublicKey):
        raise TypeError("Ed25519 공개키 형식만 지원합니다.")

    normalized_pem = pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8").strip()

    pem_literal = _format_indented_str_literal(normalized_pem)

    content = (
        "# AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.\n"
        f"# Source: {resolved_pem.name}\n\n\n"
        f"class {DEFAULT_CLASS_NAME}:\n"
        f"    {DEFAULT_VAR_NAME}: str = {pem_literal}\n\n\n"
        f"{DEFAULT_VAR_NAME}: str = {DEFAULT_CLASS_NAME}.{DEFAULT_VAR_NAME}\n"
    )
    return content, resolved_pem


def generate_public_key_module(pem_path: Path | None, out_path: Path) -> Path:
    """공개키 PEM을 검증한 뒤 EmbeddedPublicKey 클래스 변수를 포함한 .py 모듈로 출력합니다."""
    content, _ = build_public_key_module_content(pem_path=pem_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path


def sync_public_key_module_from_memory(
    mem_content: str,
    target_out: Path,
) -> dict[str, Any]:
    """메모리 상에서 생성된 모듈 소스를 기존 대상 파일과 비교해 다를 때만 저장합니다."""
    resolved_target = Path(target_out).resolve()

    if not resolved_target.is_file():
        resolved_target.parent.mkdir(parents=True, exist_ok=True)
        resolved_target.write_text(mem_content, encoding="utf-8")
        return {
            "mode": "memory",
            "py_path": str(resolved_target),
            "comparison": "new",
            "same_as_memory": False,
            "changed": True,
            "compare_message": f"기존 파일 없음 -> 메모리 생성본으로 신규 저장 ({resolved_target.name})",
        }

    existing_text = resolved_target.read_text(encoding="utf-8")
    if existing_text == mem_content:
        return {
            "mode": "memory",
            "py_path": str(resolved_target),
            "comparison": "same",
            "same_as_memory": True,
            "changed": False,
            "compare_message": f"메모리 생성본과 같음 -> 기존 파일 유지 ({resolved_target.name})",
        }

    resolved_target.write_text(mem_content, encoding="utf-8")
    return {
        "mode": "memory",
        "py_path": str(resolved_target),
        "comparison": "different",
        "same_as_memory": False,
        "changed": True,
        "compare_message": f"메모리 생성본과 다름 -> 기존 파일 변경 반영 ({resolved_target.name})",
    }


def generate_and_verify_public_key_module(
    pem_path: Path | None = None,
    out_path: Path | None = None,
    project_root: str | Path | None = None,
    sample_payload: bytes = DEFAULT_SAMPLE_PAYLOAD,
    sample_signature_b64: str | None = None,
    reverify_attempts: int = 2,
) -> dict[str, Any]:
    """메모리에서 공개키 모듈을 생성·검증하고, 기존 파일과 비교해 다를 때만 반영합니다."""
    target_out = (
        Path(out_path) if out_path is not None else resolve_default_public_key_module_path(project_root)
    ).resolve()

    info: dict[str, Any] = {
        "mode": "memory",
        "generated": False,
        "file_exists": False,
        "loaded_to_var": False,
        "sample_verified": False,
        "py_path": str(target_out),
        "comparison": "",
        "same_as_memory": False,
        "changed": False,
        "compare_message": "",
        "class_name": DEFAULT_CLASS_NAME,
        "var_name": DEFAULT_VAR_NAME,
        "pem_len": 0,
        "attempts": [],
        "last_reason": "",
        "error": "",
    }

    try:
        mem_content, _ = build_public_key_module_content(pem_path=pem_path)
        info["generated"] = True

        embedded_pem, pub_key = load_embedded_public_key_from_source(mem_content)
        info["loaded_to_var"] = True
        info["pem_len"] = len(embedded_pem)

        attempts = max(1, int(reverify_attempts))
        attempt_logs: list[dict[str, Any]] = []
        all_ok = True

        for attempt_idx in range(1, attempts + 1):
            ok, reason = verify_public_key_with_sample(
                pub_key=pub_key,
                sample_payload=sample_payload,
                sample_signature_b64=sample_signature_b64,
            )
            attempt_logs.append({"attempt": attempt_idx, "ok": ok, "reason": reason})
            if not ok:
                all_ok = False
                break

        info["attempts"] = attempt_logs
        info["last_reason"] = attempt_logs[-1]["reason"] if attempt_logs else ""
        info["sample_verified"] = all_ok

        if not all_ok:
            raise RuntimeError(f"샘플 검증 실패: {info['last_reason']}")

        sync_res = sync_public_key_module_from_memory(
            mem_content=mem_content,
            target_out=target_out,
        )
        info.update(sync_res)

        active_path = Path(info["py_path"]).resolve()
        file_ok = active_path.is_file() and active_path.stat().st_size > 0
        info["file_exists"] = file_ok
        if not file_ok:
            raise RuntimeError(f"공개키 모듈 파일이 비어 있거나 없습니다: {active_path}")

        logd(f"[pubkey][memory] {info['compare_message']}")
        return info
    except Exception as exc:
        info["error"] = str(exc)
        return info


def main() -> int:
    parser = argparse.ArgumentParser(description="메모리에서 공개키 모듈 생성·샘플 검증 후 기존 파일과 비교 반영")
    parser.add_argument(
        "--pem",
        default=None,
        help="원본 공개키 PEM 파일 경로 (미지정 시 환경변수 및 상위 secrets/ 폴더 자동 탐색)",
    )
    parser.add_argument(
        "--out",
        default=str(resolve_default_public_key_module_path()),
        help="반영할 대상 .py 파일 경로",
    )
    parser.add_argument(
        "--sample-sig",
        default=None,
        help="미리 작성된 샘플 페이로드 검증용 Ed25519 서명(Base64)",
    )
    parser.add_argument(
        "--reverify",
        type=int,
        default=2,
        help="샘플 검증 재검증 횟수 (기본 2회)",
    )
    args = parser.parse_args()
    pem_arg = Path(args.pem) if args.pem else None
    result = generate_and_verify_public_key_module(
        pem_path=pem_arg,
        out_path=Path(args.out),
        sample_signature_b64=args.sample_sig,
        reverify_attempts=args.reverify,
    )
    if result["error"]:
        loge(f"Error: {result['error']}")
        return 1
    status_str = "성공" if result["sample_verified"] else "실패"
    logd(
        f"Target: {result['py_path']} | Compare: {result['comparison']} | "
        f"Changed: {result['changed']} | Sample Verify: {status_str} ({result['last_reason']})"
    )
    return 0 if result["sample_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())