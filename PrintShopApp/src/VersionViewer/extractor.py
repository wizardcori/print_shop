import os
from cryptography.fernet import Fernet

# 빌드 시 사용한 대칭키와 동일해야 합니다.
SECRET_KEY = b'A1b2C3d4E5f6G7h8I9J0K1L2M3N4O5P6Q7R8S9T0U1V='


def extract_version_from_exe(exe_path: str) -> str | None:
    """실행 파일(.exe) 끝(EOF)에 삽입된 암호화된 버전 토큰을 추출 및 복호화합니다."""
    if not os.path.exists(exe_path):
        print(f"[오류] 파일을 찾을 수 없습니다: {exe_path}")
        return None

    try:
        cipher = Fernet(SECRET_KEY)
        with open(exe_path, "rb") as f:
            # 파일의 맨 뒤에서 200바이트를 읽어옵니다.
            f.seek(-200, 2)
            tail_data = f.read(200)

            # Fernet 암호화 토큰의 시작점 탐색 (gAAAAA로 시작)
            start_idx = tail_data.find(b'gAAAAA')
            if start_idx == -1:
                print("[실패] 해당 파일에서 암호화된 버전 정보를 찾을 수 없습니다.")
                return None

            encrypted_token = tail_data[start_idx:]
            version_str = cipher.decrypt(encrypted_token).decode("utf-8")

            print("=" * 40)
            print(f"📁 대상 파일: {os.path.basename(exe_path)}")
            print(f"🔍 추출된 버전: {version_str}")
            print("=" * 40)

            return version_str

    except Exception as e:
        print(f"[오류] 복호화 중 문제가 발생했습니다: {e}")
        return None