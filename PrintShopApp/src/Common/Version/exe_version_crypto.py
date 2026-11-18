import os
import sys
import json
import time
import getpass
import argparse
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from Common.log import logd, loge

# .env 파일 로드 (프로젝트 루트 경로에 .env가 위치할 경우)
load_dotenv()

# 1. 메인 키와 디폴트(백업) 키를 환경 변수 또는 직접 선언에서 불러오기
env_key = os.getenv("EXE_VERSION_SECRET_KEY", "")
env_key_def = os.getenv("EXE_VERSION_SECRET_KEY_DEF", "")

def parse_key(k_str: str) -> bytes:
    """문자열 형태의 키를 안전한 bytes 타입으로 변환"""
    if not k_str:
        return b''
    if k_str.startswith("b'") and k_str.endswith("'"):
        return k_str[2:-1].encode("utf-8")
    return k_str.encode("utf-8")

if not env_key_def:
    env_key_def = "b'A1b2C3d4E5f6G7h8I9J0K1L2M3N4O5P6Q7R8S9T0U1V='"

# 사용할 두 개의 키 리스트 정의 (순서대로 시도: 메인 키 -> 디폴트 키)
EXE_VERSION_SECRET_KEYS = [parse_key(env_key), parse_key(env_key_def)]


def generate_win_version_info(version_str: str, output_path: str = "version_info.txt", app_name: str = "PrintShopApp"):
    """SemVer(예: 1.2.0)를 파싱하여 PyInstaller용 Windows 리소스(version_info.txt) 동적 생성"""
    parts = [int(p) for p in version_str.split(".")]
    while len(parts) < 4:
        parts.append(0)
    ver_tuple = tuple(parts[:4])

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
        '040904B0',
        [StringStruct('CompanyName', 'PrintShop'),
         StringStruct('FileDescription', '{app_name} Executable'),
         StringStruct('FileVersion', '{version_str}'),
         StringStruct('InternalName', '{app_name}'),
         StringStruct('OriginalFilename', '{app_name}.exe'),
         StringStruct('ProductName', '{app_name}'),
         StringStruct('ProductVersion', '{version_str}')])
      ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def create_metadata_footer(user_name: str = None) -> bytes:
    """언제(타임스탬프), 누가(계정명) 마킹했는지 정보를 담은 정확히 64바이트 고정 크기 바이트 생성"""
    if not user_name:
        try:
            user_name = getpass.getuser()  # 현재 윈도우 시스템 계정명 탐색
        except Exception:
            user_name = "Unknown"
            
    # UTC 기준 연월일시분초 (YYYYMMDDHHMMSS)
    timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    
    meta = {
        "time": timestamp,
        "who": user_name
    }
    
    # JSON 문자열 변환 후 바이트 인코딩
    meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    
    # 정확히 64바이트로 패딩 또는 잘라내기
    if len(meta_bytes) < 64:
        meta_bytes = meta_bytes.ljust(64, b'\x00')  # 남는 공간은 널(\x00) 바이트로 채움
    else:
        meta_bytes = meta_bytes[:64]
        
    return meta_bytes


def read_metadata_footer(exe_path: str) -> dict:
    """파일 맨 마지막 64바이트에서 마킹 정보(누가, 언제)를 읽어 파싱"""
    if not os.path.exists(exe_path):
        return {}
    try:
        with open(exe_path, "rb") as f:
            f.seek(-64, os.SEEK_END)
            footer_bytes = f.read(64)
            cleaned = footer_bytes.rstrip(b'\x00').decode("utf-8")
            return json.loads(cleaned)
    except Exception:
        return {}


def encrypt_and_append_version(exe_path: str, version_str: str, user_name: str = None):
    """빌드된 .exe 파일의 끝(EOF)에 [암호화된 버전 토큰] + [64바이트 메타데이터 푸터] 순서로 마킹"""
    if not os.path.exists(exe_path):
        raise FileNotFoundError(f"대상 실행 파일을 찾을 수 없습니다: {exe_path}")

    # 💡 암호화할 때는 첫 번째 유효한 키(메인 키 또는 디폴트 키)를 사용
    active_key = None
    for k in EXE_VERSION_SECRET_KEYS:
        if k:
            active_key = k
            break
            
    if not active_key:
        raise ValueError("사용 가능한 유효한 대칭키가 없습니다.")

    cipher = Fernet(active_key)
    encrypted_data = cipher.encrypt(version_str.encode("utf-8"))
    
    # 64바이트 마킹 푸터 생성
    metadata_footer = create_metadata_footer(user_name)

    with open(exe_path, "ab") as f:
        f.write(encrypted_data)   # 1. 암호화된 버전 토큰 주입
        f.write(metadata_footer)  # 2. 파일 맨 끝에 64바이트 메타데이터 주입
        
    print(f"[SUCCESS] '{version_str}' 토큰 및 64바이트 마킹 정보가 {exe_path} 끝에 기록되었습니다.")


def extract_version_from_exe(exe_path: str) -> str:
    """지정된 .exe 파일 끝(EOF)에서 암호화된 버전 토큰을 순차적인 키로 복호화 시도"""
    if not os.path.exists(exe_path):
        return "파일 없음"

    try:
        with open(exe_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size < 64:
                return "파일 크기 부족 (메타데이터 없음)"

            read_size = min(320, file_size)
            f.seek(-read_size, os.SEEK_END)
            tail_data = f.read(read_size)

            search_area = tail_data[:-64]
            start_idx = search_area.find(b'gAAAAA')
            if start_idx == -1:
                return "미적용 (EOF 토큰 없음)"

            encrypted_token = search_area[start_idx:]
            
            # 💡 등록된 키들을 순서대로 복호화 시도 (메인 키 실패 시 def 키로 시도)
            version_str = None
            for key in EXE_VERSION_SECRET_KEYS:
                if not key:
                    continue
                try:
                    cipher = Fernet(key)
                    version_str = cipher.decrypt(encrypted_token).decode("utf-8")
                    break  # 복호화 성공 시 루프 탈출
                except InvalidToken:
                    continue  # 현재 키로 실패하면 다음 키 시도
                except Exception:
                    continue

            if not version_str:
                return "복호화 오류 (유효한 키 없음)"
            
            # 64바이트 마킹 정보(누가, 언제) 확인
            meta = read_metadata_footer(exe_path)
            if meta:
                logd(f"   📌 [마킹 이력] 일시: {meta.get('time')} | 작업자/PC: {meta.get('who')}")
                
            return version_str
    except Exception as e:
        return f"복호화 오류 ({e})"


def get_runtime_decrypted_version(fallback_version: str = "1.2.0") -> str:
    """실행 중인 프로세스(.exe) 자신의 암호화된 버전을 반환 (개발 모드 시 fallback 반환)"""
    if not getattr(sys, 'frozen', False):
        return f"{fallback_version} (Dev Mode)"
    return extract_version_from_exe(sys.executable)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PrintShopApp EXE 버전 리소스 생성 및 EOF 암호화/메타데이터 마킹 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. 리소스 파일 생성 서브커맨드
    p_gen = subparsers.add_parser("gen-rc", help="version.txt 기반 version_info.txt 생성")
    p_gen.add_argument("--version-file", default="version.txt")
    p_gen.add_argument("--out", default="version_info.txt")
    p_gen.add_argument("--name", default="PrintShopApp")

    # 2. EXE 끝 암호화 주입 서브커맨드 (64바이트 마킹 포함)
    p_inject = subparsers.add_parser("inject", help="EXE 파일 끝에 버전 문자열 암호화 및 64바이트 마킹 삽입")
    p_inject.add_argument("--exe", required=True, help="대상 .exe 경로")
    p_inject.add_argument("--version-file", default="version.txt")
    p_inject.add_argument("--mode", default="production")
    p_inject.add_argument("--who", default=None, help="마킹 작업자명 (미입력 시 현재 윈도우 계정 자동 입력)")

    # 3. EXE 끝 복호화 추출 서브커맨드 (마킹 정보 확인 포함)
    p_extract = subparsers.add_parser("extract", help="EXE 파일 끝에서 암호화된 버전 및 마킹 정보 추출")
    p_extract.add_argument("exe_path", help="대상 .exe 경로")

    args = parser.parse_args()

    if args.command == "gen-rc":
        with open(args.version_file, "r", encoding="utf-8") as f:
            ver = f.read().strip()
        generate_win_version_info(ver, args.out, args.name)
        print(f"[INFO] {args.out} 생성 완료 (v{ver})")

    elif args.command == "inject":
        with open(args.version_file, "r", encoding="utf-8") as f:
            ver = f.read().strip()
        payload = f"v{ver}-{args.mode}"
        encrypt_and_append_version(args.exe, payload, user_name=args.who)

    elif args.command == "extract":
        extracted = extract_version_from_exe(args.exe_path)
        print("=" * 50)
        print(f"📁 대상 파일: {os.path.basename(args.exe_path)}")
        print(f"🔍 추출된 버전: {extracted}")
        print("=" * 50)
