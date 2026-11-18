import os
import re
import argparse

try:
    from .exe_version_crypto import generate_win_version_info
except ImportError:
    from exe_version_crypto import generate_win_version_info

class VersionManager:
    """
    버전 텍스트 파일명을 지정할 수 있고, 
    version.py의 VERSION 및 NAME 변수, Windows 리소스(version_info.txt)를 동기화하는 클래스
    """

    def __init__(
        self, 
        base_dir: str = ".", 
        version_filename: str = "version.txt", 
        default_version: str = "1.2.0", 
        version_var_name: str = "VERSION",
        app_name: str = "PrintShopUpdateService"
    ):
        self.base_dir = base_dir
        self.version_filename = version_filename        
        self.txt_path = os.path.join(base_dir, version_filename)
        self.py_path = os.path.join(base_dir, "version.py")
        self.rc_path = os.path.join(base_dir, "version_info.txt")  # [신규] Windows 리소스 경로
        self.default_version = default_version
        self.version_var_name = version_var_name
        self.app_name = app_name

    def get_current_version(self) -> str:
        """현재 버전을 읽어옴 (파일이 없으면 기본 버전으로 초기화)"""
        if not os.path.exists(self.txt_path):
            self._save_version(self.default_version)
            return self.default_version

        with open(self.txt_path, "r", encoding="utf-8") as f:
            ver = f.read().strip()

        if not re.match(r"^\d+\.\d+\.\d+$", ver):
            raise ValueError(f"올바르지 않은 버전 형식입니다: '{ver}' (예: 1.2.0)")
        return ver

    def bump_version(self, part: str = "patch") -> str:
        """지정된 단위(major, minor, patch)의 버전을 1 증가시키고 파일에 저장"""
        current = self.get_current_version()
        major, minor, patch = map(int, current.split("."))

        part = part.lower()
        if part == "major":
            major += 1
            minor = 0
            patch = 0
        elif part == "minor":
            minor += 1
            patch = 0
        elif part == "patch":
            patch += 1
        else:
            raise ValueError("part 인자는 'major', 'minor', 'patch' 중 하나여야 합니다.")

        new_version = f"{major}.{minor}.{patch}"
        self._save_version(new_version)
        return new_version

    def _save_version(self, ver: str):
        """지정된 버전 파일, version.py, 그리고 Windows 리소스 파일에 동시 기록"""
        with open(self.txt_path, "w", encoding="utf-8") as f:
            f.write(ver + "\n")

        if os.path.exists(self.py_path):
            with open(self.py_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            ver_pattern = rf'({self.version_var_name}\s*=\s*")[^"]*(")'
            if re.search(ver_pattern, content):
                content = re.sub(ver_pattern, rf'\g<1>{ver}\g<2>', content)
            else:
                content += f'\n{self.version_var_name} = "{ver}"\n'

            name_pattern = r'(NAME\s*=\s*")[^"]*(")'
            if re.search(name_pattern, content):
                content = re.sub(name_pattern, rf'\g<1>{self.app_name}\g<2>', content)
            else:
                content += f'\nNAME = "{self.app_name}"\n'

            new_content = content
        else:
            new_content = (
                f'# version.py\n'
                f'{self.version_var_name} = "{ver}"\n'
                f'NAME = "{self.app_name}"\n'
            )

        with open(self.py_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # [신규 연동] 메인 앱의 경우 Windows 리소스 버전 파일(version_info.txt)도 함께 갱신
        if self.app_name == "PrintShopApp":
            try:
                generate_win_version_info(ver, self.rc_path, self.app_name)
            except Exception:
                pass

    def set_base_dir(self, base_dir: str):
        self.base_dir = base_dir
        self.txt_path = os.path.join(base_dir, self.version_filename)
        self.py_path = os.path.join(base_dir, "version.py")
        self.rc_path = os.path.join(base_dir, "version_info.txt")


vm_inst = VersionManager()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Semantic Version Manager")
    parser.add_argument("part", nargs="?", default="patch", choices=["major", "minor", "patch"], help="증가시킬 버전 단위")
    parser.add_argument("--dir", default=".", help="version.txt 및 version.py가 위치한 대상 폴더")
    parser.add_argument("--txt", default="version.txt", help="버전 텍스트 파일 이름 (기본값: version.txt)")
    parser.add_argument("--name", default="PrintShopUpdateService", help="version.py에 기록할 NAME 값")

    args = parser.parse_args()

    vm = VersionManager(
        base_dir=os.path.abspath(args.dir),
        version_filename=args.txt,
        app_name=args.name
    )
    new_ver = vm.bump_version(args.part)
    print(new_ver)