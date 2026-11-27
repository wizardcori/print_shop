from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable

from Common.log import logd, loge, set_file_tag

set_file_tag("PYLIB_MGR")
"""
[사용법 안내]
1. CLI / 대화형 실행
   $ python python_lib_manager.py
   $ python python_lib_manager.py venv_setup --source_root ./src --no-confirm

2. 코드에서 직접 호출 (전체 일괄 실행)
   mgr = PythonLibManager(
       source_root="./src",          # .py 파일을 순회 검색할 소스 루트 폴더
       venv_root="./venvs/app1",     # .venv 폴더를 찾거나 생성할 루트 폴더 (None이면 source_root 사용)
       venv_dir_name=".venv",        # 가상환경 폴더 이름 (기본: ".venv")
       debug=True,                   # logd() 출력 여부 (loge()는 항상 출력)
   )
   mgr.run(create_venv=True, confirm=True)
"""


class PythonLibManager:
    """소스 루트 폴더 스캔, 가상환경 루트 폴더 확인/구축, 패키지 확인 및 설치를 수행하는 클래스."""

    DEFAULT_EXCLUDE_DIRS: set[str] = {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "venv",
        ".venv",
        "env",
        ".env",
        "virtualenv",
        "build",
        "dist",
        "release",
        "install",
        "test",
        "node_modules",
        ".tox",
    }

    DEFAULT_VENV_CANDIDATES: tuple[str, ...] = (".venv", "venv", "env")

    DEFAULT_PACKAGE_MAP: dict[str, str] = {
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "sklearn": "scikit-learn",
        "yaml": "PyYAML",
        "bs4": "beautifulsoup4",
        "dotenv": "python-dotenv",
        "dateutil": "python-dateutil",
        "Crypto": "pycryptodome",
        "github": "PyGithub",
        "win32api": "pywin32",
        "win32con": "pywin32",
        "win32event": "pywin32",
        "win32evtlog": "pywin32",
        "win32print": "pywin32",
        "win32security": "pywin32",
        "win32service": "pywin32",
        "win32serviceutil": "pywin32",
        "win32ts": "pywin32",
        "servicemanager": "pywin32",
        "Path": "pathlib",
    }

    # 표준 라이브러리 보완(특히 Windows / 일부 하위 모듈명) 및 비-PyPI/로컬/빌드 전용 이름
    DEFAULT_IGNORE_MODULES: set[str] = {
        "Path",
        "pathlib",
        "redis_server",
        "winrt",
        "wmi",
        "build_script",
        "setting",
        "ui",
        "Common",
        "UpdateManager",
        "UpdateService",
        "BuildManagerApp",
        "PrintShopApp",
        "VersionViewer",
        "LinkBox",
        "LinkShare",
        "app_name",
        "exe_version_desc_v1",
        "local_version_map",
    }

    def __init__(
        self,
        source_root: str | Path = ".",
        venv_root: str | Path | None = None,
        venv_dir_name: str = ".venv",
        exclude_dirs: Iterable[str] | None = None,
        package_map: dict[str, str] | None = None,
        ignore_modules: Iterable[str] | None = None,
        follow_symlinks: bool = False,
        debug: bool = True,
    ) -> None:
        self.debug = debug

        self.source_root = Path(source_root).resolve()
        if not self.source_root.exists() or not self.source_root.is_dir():
            msg = f"유효하지 않은 소스 루트 폴더입니다: {self.source_root}"
            loge(msg)
            raise NotADirectoryError(msg)

        self.venv_root = Path(venv_root).resolve() if venv_root is not None else self.source_root
        self.venv_dir_name = venv_dir_name
        self.exclude_dirs: set[str] = (
            set(exclude_dirs) if exclude_dirs is not None else set(self.DEFAULT_EXCLUDE_DIRS)
        )
        merged_pkg_map = dict(self.DEFAULT_PACKAGE_MAP)
        if package_map:
            merged_pkg_map.update(package_map)
        self.package_map: dict[str, str] = merged_pkg_map

        merged_ignore = set(self.DEFAULT_IGNORE_MODULES)
        if ignore_modules:
            merged_ignore.update(ignore_modules)
        self.ignore_modules: set[str] = merged_ignore

        self.follow_symlinks = follow_symlinks

        self.venv_path: Path | None = None
        self.venv_python: Path | None = None
        self.file_imports: dict[Path, set[str]] = {}
        self.installed: list[str] = []
        self.missing: list[str] = []
        self.failed_packages: list[str] = []

        logd("PythonLibManager 초기화 완료")
        logd(f"  - 소스 루트 폴더: {self.source_root}")
        logd(f"  - 가상환경 루트 폴더: {self.venv_root}")
        logd(f"  - 가상환경 폴더명: {self.venv_dir_name}")

    # ------------------------------------------------------------------
    # 가상환경 체크 및 구축 (venv_root 기준)
    # ------------------------------------------------------------------
    @staticmethod
    def _get_venv_python_path(venv_dir: Path) -> Path:
        if os.name == "nt":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def find_venv(self) -> Path | None:
        logd(f"가상환경 탐색 시작 (가상환경 루트: {self.venv_root})")
        if not self.venv_root.exists():
            logd(f"가상환경 루트 폴더가 아직 존재하지 않습니다: {self.venv_root}")
            self.venv_path = None
            self.venv_python = None
            return None

        candidates = [self.venv_dir_name] + [
            name for name in self.DEFAULT_VENV_CANDIDATES if name != self.venv_dir_name
        ]

        for name in candidates:
            candidate_dir = self.venv_root / name
            candidate_py = self._get_venv_python_path(candidate_dir)
            if candidate_dir.is_dir() and candidate_py.is_file():
                self.venv_path = candidate_dir
                self.venv_python = candidate_py
                logd(f"기존 가상환경 발견: {candidate_dir} ({candidate_py})")
                return candidate_dir

        self.venv_path = None
        self.venv_python = None
        logd("기존 가상환경을 찾지 못했습니다.")
        return None

    def create_venv(self, upgrade_pip: bool = True) -> Path:
        if not self.venv_root.exists():
            logd(f"가상환경 루트 폴더 생성: {self.venv_root}")
            self.venv_root.mkdir(parents=True, exist_ok=True)
        elif not self.venv_root.is_dir():
            msg = f"가상환경 루트 경로가 디렉토리가 아닙니다: {self.venv_root}"
            loge(msg)
            raise NotADirectoryError(msg)

        venv_dir = self.venv_root / self.venv_dir_name
        venv_python = self._get_venv_python_path(venv_dir)

        logd(f"가상환경 생성 시작: {venv_dir}")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        except subprocess.CalledProcessError as e:
            loge(f"가상환경 생성 실패: {e}")
            raise

        if not venv_python.is_file():
            msg = f"가상환경 Python 실행 파일을 찾을 수 없습니다: {venv_python}"
            loge(msg)
            raise RuntimeError(msg)

        if upgrade_pip:
            logd("가상환경 pip 업그레이드 중...")
            try:
                subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                loge(f"pip 업그레이드 실패: {e}")
                raise

        self.venv_path = venv_dir
        self.venv_python = venv_python
        logd(f"가상환경 구축 완료: {venv_dir} ({venv_python})")
        return venv_dir

    def ensure_venv(self, create_if_missing: bool = True, confirm: bool = True) -> str:
        logd(f"가상환경 확보 절차 시작 (create_if_missing={create_if_missing}, confirm={confirm})")
        if self.find_venv() is None:
            if not create_if_missing:
                loge("가상환경이 없지만 생성 옵션이 비활성화되어 현재 Python을 사용합니다.")
                return sys.executable

            if confirm:
                target_venv_dir = self.venv_root / self.venv_dir_name
                answer = (
                    input(f"'{target_venv_dir}' 가상환경을 새로 생성할까요? (y/N): ")
                    .strip()
                    .lower()
                )
                if answer != "y":
                    loge("사용자에 의해 가상환경 생성이 취소되어 현재 Python을 사용합니다.")
                    return sys.executable

            self.create_venv()

        resolved_py = str(self.venv_python) if self.venv_python else sys.executable
        logd(f"사용할 Python 실행 경로 결정: {resolved_py}")
        return resolved_py

    # ------------------------------------------------------------------
    # 하위 폴더 순회 및 import 스캔 (source_root 기준)
    # ------------------------------------------------------------------
    def iter_python_files(self):
        logd(f"Python 파일 순회 시작: {self.source_root}")
        for current_root, dirnames, filenames in os.walk(
            self.source_root, topdown=True, followlinks=self.follow_symlinks
        ):
            dirnames[:] = sorted(
                d for d in dirnames if d not in self.exclude_dirs and not d.endswith(".egg-info")
            )
            for filename in sorted(filenames):
                if filename.endswith(".py"):
                    yield Path(current_root) / filename

    def _collect_local_module_names(self) -> set[str]:
        logd("로컬 패키지/모듈명 수집 시작")
        local_names: set[str] = set()

        roots_to_scan = [self.source_root]
        project_root = (
            self.source_root.parent if self.source_root.name.lower() == "src" else self.source_root
        )
        if project_root not in roots_to_scan and project_root.exists():
            roots_to_scan.append(project_root)

        for root in roots_to_scan:
            try:
                for _current_root, dirnames, filenames in os.walk(
                    root, topdown=True, followlinks=self.follow_symlinks
                ):
                    dirnames[:] = sorted(
                        d
                        for d in dirnames
                        if d not in self.exclude_dirs and not d.endswith(".egg-info")
                    )
                    for d in dirnames:
                        if not d.startswith((".", "__")):
                            local_names.add(d)
                    for filename in sorted(filenames):
                        if filename.endswith(".py"):
                            stem = Path(filename).stem
                            if not stem.startswith("__"):
                                local_names.add(stem)
            except OSError as exc:
                loge(f"로컬 모듈 디렉토리 순회 실패 ({root}): {exc}")

        logd(f"로컬 모듈 {len(local_names)}개 수집 완료")
        return local_names

    def _read_source(self, py_file: Path) -> str | None:
        for encoding in ("utf-8-sig", "utf-8", "cp949"):
            try:
                content = py_file.read_text(encoding=encoding)
                logd(f"소스 읽기 성공 ({encoding}): {py_file}")
                return content
            except UnicodeDecodeError:
                continue
            except OSError as exc:
                loge(f"파일 읽기 실패 ({py_file}): {exc}")
                return None
        loge(f"인코딩 디코딩 실패 (utf-8-sig/utf-8/cp949): {py_file}")
        return None

    def _extract_imports(self, py_file: Path) -> set[str]:
        source = self._read_source(py_file)
        if source is None:
            return set()

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as e:
            loge(f"문법 오류로 스캔 생략 ({py_file}): {e}")
            return set()

        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    modules.add(node.module.split(".")[0])
        return modules

    def scan_imports(self) -> dict[Path, set[str]]:
        logd(f"하위 폴더 .py 파일 스캔 시작: {self.source_root}")
        self.file_imports.clear()
        for py_file in self.iter_python_files():
            mods = self._extract_imports(py_file)
            self.file_imports[py_file] = mods
            logd(f"파일 스캔 완료 - {py_file}: {sorted(mods)}")
        logd(f"총 {len(self.file_imports)}개 파일 스캔 완료")
        return self.file_imports

    def get_imported_modules(self) -> set[str]:
        if not self.file_imports:
            logd("기존 import 스캔 캐시가 없어 scan_imports()를 실행합니다.")
            self.scan_imports()
        all_mods: set[str] = set()
        for mods in self.file_imports.values():
            all_mods.update(mods)
        logd(f"전체 추출 모듈 수: {len(all_mods)}")
        return all_mods

    # ------------------------------------------------------------------
    # 패키지 확인 및 설치
    # ------------------------------------------------------------------
    def _get_installed_names(self, python_exe: str) -> set[str]:
        logd(f"설치된 패키지 목록 조회 중 ({python_exe})")
        code = (
            "import importlib.metadata, json; "
            "names = set(); "
            "p2m = importlib.metadata.packages_distributions(); "
            "[names.update(m.lower().replace('-', '_')) for mods in p2m.values() for m in mods]; "
            "[names.add(d.metadata['Name'].lower().replace('-', '_')) for d in importlib.metadata.distributions() if d.metadata.get('Name')]; "
            "print(json.dumps(sorted(names)))"
        )
        try:
            res = subprocess.run(
                [python_exe, "-c", code],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            loge(f"설치된 패키지 조회 실패: {e}")
            raise

        names = set(json.loads(res.stdout.strip()))
        logd(f"설치된 패키지/모듈 이름 {len(names)}개 확인")
        return names

    def map_to_pip_package(self, module_name: str) -> str:
        mapped = self.package_map.get(module_name, module_name)
        logd(f"패키지명 매핑: {module_name} -> {mapped}")
        return mapped

    def check_packages(self, python_exe: str | None = None) -> tuple[list[str], list[str]]:
        target_py = python_exe or (str(self.venv_python) if self.venv_python else sys.executable)
        logd(f"의존성 패키지 설치 여부 확인 시작 ({target_py})")

        stdlib = getattr(sys, "stdlib_module_names", set())
        local_modules = self._collect_local_module_names()
        imported = self.get_imported_modules()

        candidates = sorted(
            m
            for m in imported
            if m not in stdlib and m not in local_modules and m not in self.ignore_modules
        )
        logd(f"외부 라이브러리 후보: {candidates}")

        installed_env = self._get_installed_names(target_py)
        installed_list: list[str] = []
        missing_list: list[str] = []

        for mod in candidates:
            norm = mod.lower().replace("-", "_")
            pip_pkg = self.map_to_pip_package(mod)
            norm_pkg = pip_pkg.lower().replace("-", "_")
            if mod in installed_env or norm in installed_env or norm_pkg in installed_env:
                if pip_pkg not in installed_list:
                    installed_list.append(pip_pkg)
                logd(f"[설치됨] {mod} -> {pip_pkg}")
            else:
                if pip_pkg not in missing_list:
                    missing_list.append(pip_pkg)
                logd(f"[미설치] {mod} -> {pip_pkg}")

        self.installed = installed_list
        self.missing = missing_list
        logd(f"확인 완료 - 설치됨: {self.installed}, 미설치: {self.missing}")
        return self.installed, self.missing

    def install_missing(
        self,
        python_exe: str | None = None,
        confirm: bool = True,
        fail_on_error: bool = False,
    ) -> bool:
        target_py = python_exe or (str(self.venv_python) if self.venv_python else sys.executable)
        logd(
            f"미설치 패키지 설치 절차 시작 (target={target_py}, confirm={confirm}, fail_on_error={fail_on_error})"
        )

        if not self.missing:
            logd("미설치 목록이 비어 있어 check_packages()를 먼저 수행합니다.")
            self.check_packages(target_py)

        if not self.missing:
            logd("설치할 미설치 패키지가 없습니다.")
            return True

        self.failed_packages.clear()
        logd(f"설치 대상 Python: {target_py}")
        logd(f"미설치 패키지 목록: {', '.join(self.missing)}")

        if confirm:
            answer = input("위 패키지를 대상 환경에 설치할까요? (y/N): ").strip().lower()
            if answer != "y":
                loge("사용자에 의해 패키지 설치가 취소되었습니다.")
                return False

        batch_cmd = [target_py, "-m", "pip", "install", *self.missing]
        logd(f"실행 명령(일괄): {' '.join(batch_cmd)}")
        batch_res = subprocess.run(batch_cmd, check=False)

        if batch_res.returncode != 0:
            loge(
                f"일괄 설치 실패 (returncode={batch_res.returncode}) -> 개별 패키지 단위로 재시도합니다."
            )
            for pkg in list(self.missing):
                single_cmd = [target_py, "-m", "pip", "install", pkg]
                logd(f"실행 명령(개별): {' '.join(single_cmd)}")
                single_res = subprocess.run(single_cmd, check=False)
                if single_res.returncode != 0:
                    loge(f"패키지 설치 실패(건너뜀): {pkg} (returncode={single_res.returncode})")
                    if pkg not in self.failed_packages:
                        self.failed_packages.append(pkg)
                else:
                    logd(f"개별 패키지 설치 성공: {pkg}")

        self.check_packages(target_py)

        if self.failed_packages:
            loge(f"일부 패키지 설치 실패: {self.failed_packages}")
            if fail_on_error:
                loge("fail_on_error=True 조건으로 install_missing() 실패 반환")
                return False

        logd("미설치 패키지 설치 및 상태 갱신 완료")
        return True

    # ------------------------------------------------------------------
    # 전체 일괄 실행
    # ------------------------------------------------------------------
    def run(
        self,
        create_venv: bool = True,
        confirm: bool = True,
        fail_on_error: bool = False,
    ) -> None:
        logd("=== 프로젝트 환경 설정 및 의존성 점검 시작 ===")
        python_exe = self.ensure_venv(create_if_missing=create_venv, confirm=confirm)
        self.scan_imports()
        self.check_packages(python_exe)

        if self.missing:
            self.install_missing(
                python_exe=python_exe, confirm=confirm, fail_on_error=fail_on_error
            )

        logd("=== 프로젝트 환경 설정 및 의존성 점검 종료 ===")


def _parse_bool_option(raw: str | None, default: bool) -> bool:
    if raw is None or not raw.strip():
        logd(f"불리언 옵션 미입력 -> 기본값 사용: {default}")
        return default
    parsed = raw.strip().lower() in ("1", "true", "t", "yes", "y", "on")
    logd(f"불리언 옵션 파싱: '{raw.strip()}' -> {parsed}")
    return parsed


def _prompt_with_default(prompt_text: str, default_value: str) -> str:
    entered = input(prompt_text).strip()
    return entered if entered else default_value


def print_venv_setup_help() -> None:
    logd("print_venv_setup_help() 호출")
    print(
        "\n[venv_setup Help]\n"
        "  Function:\n"
        "    venv_setup   : Check/create virtual environment and check/install packages.\n\n"
        "  Options:\n"
        "    source_root  : Source root directory path (default: '.').\n"
        "    venv_root    : Virtual environment root directory path (optional).\n"
        "    venv_dir     : Virtual environment directory name (default: '.venv').\n"
        "    create_venv  : Create venv if missing ('true' or 'false', default: 'true').\n"
        "    confirm      : Prompt for confirmation ('true' or 'false', default: 'true').\n"
        "    debug        : Enable debug logs ('true' or 'false', default: 'true').\n"
    )


def execute_venv_setup(
    *,
    interactive: bool = False,
    source_root: str | Path | None = None,
    venv_root: str | Path | None = None,
    venv_dir: str = ".venv",
    create_venv: bool = True,
    confirm: bool = True,
    debug: bool = True,
) -> None:
    """Execute virtual environment setup and dependency check/install."""
    logd("venv_setup 라우트 옵션 수집 시작")
    if interactive:
        src_default = str(source_root) if source_root is not None else "."
        src_opt = _prompt_with_default(f"source_root (default: {src_default}): ", src_default)
        venv_root_default = str(venv_root) if venv_root is not None else ""
        venv_root_raw = _prompt_with_default(
            f"venv_root (default: {venv_root_default or 'none'}): ", venv_root_default
        )
        venv_root_opt: str | None = venv_root_raw or None
        venv_dir_opt = _prompt_with_default(f"venv_dir (default: {venv_dir}): ", venv_dir)
        create_venv_opt = _parse_bool_option(
            input(f"create_venv [true/false] (default: {str(create_venv).lower()}): "),
            create_venv,
        )
        confirm_opt = _parse_bool_option(
            input(f"confirm [true/false] (default: {str(confirm).lower()}): "),
            confirm,
        )
        debug_opt = _parse_bool_option(
            input(f"debug [true/false] (default: {str(debug).lower()}): "),
            debug,
        )
    else:
        src_opt = str(source_root) if source_root is not None else "."
        venv_root_opt = str(venv_root) if venv_root is not None else None
        venv_dir_opt = venv_dir.strip() or ".venv"
        create_venv_opt = bool(create_venv)
        confirm_opt = bool(confirm)
        debug_opt = bool(debug)

    logd(
        f"venv_setup 실행 인자: source_root={src_opt}, venv_root={venv_root_opt}, venv_dir={venv_dir_opt}, create_venv={create_venv_opt}, confirm={confirm_opt}, debug={debug_opt}"
    )
    mgr = PythonLibManager(
        source_root=src_opt,
        venv_root=venv_root_opt,
        venv_dir_name=venv_dir_opt,
        debug=debug_opt,
    )
    mgr.run(create_venv=create_venv_opt, confirm=confirm_opt)
    logd("venv_setup 라우트 실행 완료")


def run_venv_route(
    function: str | None = None,
    *,
    source_root: str | Path | None = None,
    venv_root: str | Path | None = None,
    venv_dir: str = ".venv",
    create_venv: bool = True,
    confirm: bool = True,
    debug: bool = True,
) -> None:
    """Run virtual environment setup route."""
    logd(f"run_venv_route 시작 (function={function})")
    try:
        interactive = False
        func_name = (function or "").strip().lower()
        if not func_name:
            interactive = True
            func_name = "venv_setup"

        if func_name in ("help", "--help", "-h", "h", "?"):
            print_venv_setup_help()
        elif func_name in ("venv_setup", "venv"):
            execute_venv_setup(
                interactive=interactive,
                source_root=source_root,
                venv_root=venv_root,
                venv_dir=venv_dir,
                create_venv=create_venv,
                confirm=confirm,
                debug=debug,
            )
        else:
            loge(f"알 수 없는 가상환경 기능명 입력됨: '{func_name}'")
            print(f"Unknown function: '{func_name}'")
            print_venv_setup_help()
    except (KeyboardInterrupt, EOFError):
        loge("사용자 입력 중단 또는 EOF로 가상환경 라우트 실행 종료")
        print("\n실행이 중단되었습니다.")


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PythonLibManager CLI entrypoint",
        add_help=False,
    )
    parser.add_argument(
        "function",
        nargs="?",
        default=None,
        help="Target function ('venv_setup' or 'help')",
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")
    parser.add_argument("--source_root", default=None, help="Source root directory")
    parser.add_argument("--venv_root", default=None, help="Virtual environment root directory")
    parser.add_argument("--venv_dir", default=".venv", help="Virtual environment directory name")
    parser.add_argument(
        "--no-create-venv",
        dest="create_venv",
        action="store_false",
        default=True,
        help="Do not create virtual environment if missing",
    )
    parser.add_argument(
        "--no-confirm",
        dest="confirm",
        action="store_false",
        default=True,
        help="Skip interactive confirmation prompts",
    )
    parser.add_argument(
        "--no-debug",
        dest="debug",
        action="store_false",
        default=True,
        help="Disable debug mode in PythonLibManager",
    )
    return parser


if __name__ == "__main__":
    logd("__main__ 진입 -> CLI 인자 파싱 및 run_venv_route() 호출")
    cli_args = _build_cli_parser().parse_args()
    selected_fn = "help" if cli_args.help else (cli_args.function or "venv_setup")
    run_venv_route(
        selected_fn,
        source_root=cli_args.source_root,
        venv_root=cli_args.venv_root,
        venv_dir=cli_args.venv_dir,
        create_venv=cli_args.create_venv,
        confirm=cli_args.confirm,
        debug=cli_args.debug,
    )
