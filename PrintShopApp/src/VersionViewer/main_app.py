import argparse
from extractor import extract_version_from_exe


def main():
    parser = argparse.ArgumentParser(
        description="실행 파일(.exe) 맨 끝에 숨겨진 암호화된 버전 정보를 추출합니다."
    )
    parser.add_argument(
        "exe_path",
        nargs="?",
        help="버전을 확인할 .exe 파일의 경로"
    )
    args = parser.parse_args()

    target_path = args.exe_path
    if not target_path:
        target_path = input("버전을 추출할 .exe 파일 경로를 입력하세요: ").strip().strip('"')

    extract_version_from_exe(target_path)


if __name__ == "__main__":
    main()