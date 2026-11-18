"""
PrintShopApp Unified Build & Distribution Packaging Script (Object-Oriented with Result Tracking)
===========================================================================================
전체 빌드 파이프라인 단계별 요약:
  [Step 1] UI 컴파일           : 프로젝트 내 모든 .ui 파일을 PySide6 파이썬 코드(ui_*.py)로 변환
  [Step 2] 환경 검증 및 설정   : 가상환경(.venv) 확인, .env 파싱 및 빌드 설정 파일(build_config_gen.py) 생성
  [Step 3] 버전 및 리소스 동기화: version.txt/version.py 갱신(--bump 지원) 및 Windows 리소스(version_info.txt) 생성
  [Step 4-1] 메인 앱 빌드      : PyInstaller(.spec)로 메인 앱(PrintShopApp) 빌드 실행
  [Step 4-2] 서브 앱 빌드      : UpdateService 서브 빌드 실행 (venv_python 전달)
  [Step 4-3] 서브 앱 빌드      : UpdateManager 서브 빌드 실행 (venv_python 전달)
  [Step 4-4] 서브 앱 빌드      : VersionViewer 서브 빌드 실행 (venv_python 전달)
  [Step 5] EOF 버전 암호화/검증 : Fernet 암호화된 버전 정보를 PrintShopApp.exe 끝(EOF)에 삽입 및 Read-back 검증
  [Step 6] 테스트 환경 동기화   : 기존 test/data를 보존하면서 최신 빌드 결과물만 test 폴더에 덮어쓰기
  [Step 7] 업데이트 ZIP 생성    : GitHub Releases 배포용 update_v<버전>.zip 압축 패키지 생성
  [Step 8] 설치 파일(Setup) 빌드: Inno Setup(ISCC.exe)을 이용해 최종 Windows 인스톨러(.exe) 생성

사용 예시:
  python build.py                  # 현재 버전으로 전체 빌드
  python build.py --bump patch     # 패치 버전 1 증가(예: 1.2.0 -> 1.2.1) 후 빌드
  python build.py --skip-installer # 인스톨러(.exe) 생성을 건너뛰고 포터블/ZIP까지만 빌드
"""

import os
import sys
import glob
import shutil
import zipfile
import argparse
import subprocess

from Common.log import logd, loge

# ==============================================================================
# 0. 프로젝트 경로 초기화 및 내부 모듈 임포트
# ==============================================================================
build_script_dir = os.path.dirname(os.path.abspath(__file__))
raw_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../")
PROJECT_ROOT = os.path.normpath(raw_path)   # PrintShopApp
SRC_DIR = os.path.join(PROJECT_ROOT, "src") # PrintShopApp/src

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Common.Version.version_manager import VersionManager
from src.Common.Version.exe_version_crypto import (
    generate_win_version_info, 
    encrypt_and_append_version, 
    extract_version_from_exe
)


class BuildApp:
    def __init__(self):

        self.build_script_dir = build_script_dir

        self.project_root = PROJECT_ROOT
        
        self.dist_dir = os.path.join(self.project_root, "dist")
        
        # 💡 가상환경 및 주요 실행 파일 경로를 클래스 속성으로 깔끔하게 정의
        self.venv_dir = os.path.join(self.project_root, ".venv")
        self.venv_python = os.path.join(self.venv_dir, "Scripts", "python.exe")
        self.venv_pyinstaller = os.path.join(self.venv_dir, "Scripts", "pyinstaller.exe")
        
        # 단계별 성공/실패 및 결과를 기록할 딕셔너리 변수
        self.results = {}

    def _record_result(self, step_name: str, status: str, message: str):
        """단계별 결과를 기록합니다. (status: SUCCESS, FAILED, SKIPPED)"""
        self.results[step_name] = {
            "status": status,
            "message": message
        }

    def print_summary(self):
        """마지막에 단계별 실행 결과를 요약 출력합니다."""
        logd("\n" + "=" * 65)
        logd("  📋 Build Pipeline Execution Summary")
        logd("=" * 65)
        for step, info in self.results.items():
            if info["status"] == "SUCCESS":
                icon = "✅"
            elif info["status"] == "SKIPPED":
                icon = "⏭️"
            else:
                icon = "❌"
            logd(f"  {icon} [{step}] - {info['status']}")
            logd(f"     └─ {info['message']}")
        logd("=" * 65)

    def parse_env_file(self, filepath: str) -> dict:
        """지정된 .env 설정 파일을 읽어 대문자 키-값 딕셔너리로 반환합니다."""
        env_vars = {}
        if not os.path.exists(filepath):
            return env_vars

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                env_vars[key.strip().upper()] = val.strip().strip('"').strip("'")
        return env_vars

    def str_to_bool(self, val: str) -> bool:
        """문자열 불리언 표현('true', '1', 'yes', 'on')을 실제 bool 타입으로 변환합니다."""
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    def ensure_venv(self) -> str:
        """가상환경(.venv) 존재 여부를 확인하고, 없으면 setup.bat을 실행해 구축합니다."""
        if not os.path.exists(self.venv_python):
            logd("  • 가상환경(.venv)이 감지되지 않았습니다. setup.bat을 실행합니다...")
            setup_bat = os.path.join(self.project_root, "setup.bat")
            if os.path.exists(setup_bat):
                subprocess.run([setup_bat, "nopause"], check=True)
            else:
                raise FileNotFoundError(f"setup.bat 파일을 찾을 수 없습니다: {setup_bat}")

        if not os.path.exists(self.venv_python):
            raise RuntimeError(f"가상환경 파이썬 경로를 찾을 수 없습니다: {self.venv_python}")
        
        return self.venv_python

    def find_iscc(self) -> str | None:
        """시스템에 설치된 Inno Setup 컴파일러(ISCC.exe) 경로를 탐색하거나 자동 설치합니다."""
        iscc_path = shutil.which("iscc")
        if iscc_path:
            return iscc_path

        candidates = [
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path

        logd("  • Inno Setup 컴파일러가 감지되지 않았습니다. winget을 통해 자동 설치를 시도합니다...")
        if shutil.which("winget"):
            res = subprocess.run(
                [
                    "winget", "install", "--id", "JRSoftware.InnoSetup",
                    "--exact", "--silent", "--accept-source-agreements", "--accept-package-agreements"
                ]
            )
            if res.returncode == 0:
                for path in candidates:
                    if path and os.path.exists(path):
                        return path
        return None

    # ==========================================================================
    # 파이프라인 단계별 실행 메서드 영역 (Step 1 ~ Step 8)
    # ==========================================================================

    def step1_convert_ui_files(self):
        """[Step 1] 프로젝트 내의 모든 .ui 파일을 검색하여 ui_*.py 파이썬 모듈로 컴파일합니다."""
        step_name = "Step 1: UI Compile"
        logd(f"\n[{step_name}] 디렉토리 내 .ui 파일 검색 및 Python UI 모듈 변환 시작...")
        
        try:
            ui_files = glob.glob("**/*.ui", recursive=True)
            if not ui_files:
                msg = "변환할 .ui 파일이 없습니다."
                logd(f"  ℹ️ {msg}")
                self._record_result(step_name, "SUCCESS", msg)
                return

            venv_bin_dir = os.path.dirname(sys.executable)
            uic_executable = os.path.join(venv_bin_dir, "pyside6-uic.exe" if os.name == 'nt' else "pyside6-uic")

            for ui_path in ui_files:
                if any(excluded in ui_path for excluded in ("build", "dist", ".venv", "venv")):
                    continue
                    
                dir_name = os.path.dirname(ui_path)
                base_name = os.path.splitext(os.path.basename(ui_path))[0]
                py_output_path = os.path.join(dir_name, f"ui_{base_name}.py")
                
                logd(f"  • 변환 중: {ui_path} ➔ {py_output_path}")
                if os.path.exists(uic_executable):
                    subprocess.run([uic_executable, ui_path, "-o", py_output_path], check=True)
                else:
                    subprocess.run([sys.executable, "-m", "PySide6.uic", ui_path, "-o", py_output_path], check=True)
            
            msg = f"총 {len(ui_files)}개 관련 파일 처리 완료"
            logd(f"  ✅ {msg}")
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"오류 발생: {e}"
            logd(f"  ❌ {msg}")
            self._record_result(step_name, "FAILED", msg)
            raise

    def step2_setup_environment_and_config(self) -> tuple[str, str]:
        """[Step 2] 가상환경을 검증하고 .env 설정을 파싱한 뒤 빌드 설정 스크립트를 실행합니다."""
        step_name = "Step 2: Environment & Config"
        logd(f"\n[{step_name}] 가상환경 검증 및 빌드 환경 설정 로드...")
        try:
            venv_python = self.ensure_venv()

            buildtime_env = self.parse_env_file(os.path.join(self.project_root, ".env.feature.buildtime"))
            dot_env = self.parse_env_file(os.path.join(self.project_root, ".env"))

            use_printer_watch = self.str_to_bool(buildtime_env.get("USE_PRINTER_WATCH", "false"))
            use_build_time_test = self.str_to_bool(buildtime_env.get("USE_BUILD_TIME_TEST", "false"))
            mode = "development" if dot_env.get("MODE", "production").lower() == "development" else "production"

            logd(f"  • BUILD MODE           : {mode}")
            logd(f"  • USE_PRINTER_WATCH    : {str(use_printer_watch).lower()}")
            logd(f"  • USE_BUILD_TIME_TEST  : {str(use_build_time_test).lower()}")

            subprocess.run([venv_python, os.path.join(self.build_script_dir, "build_config_gen.py")], check=True)
            msg = f"Mode: {mode}, Venv verified"
            self._record_result(step_name, "SUCCESS", msg)
            return venv_python, mode
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step3_sync_version_and_resources(self, bump_unit: str | None) -> str:
        """[Step 3] 버전을 증가 및 동기화하고 Windows 실행 파일 리소스(version_info.txt)를 생성합니다."""
        step_name = "Step 3: Version & Resources"
        logd(f"\n[{step_name}] 버전 동기화 및 Windows 리소스 파일 생성...")
        try:
            vm = VersionManager(base_dir=self.project_root, app_name="PrintShopApp")
            
            if bump_unit:
                app_version = vm.bump_version(bump_unit)
                logd(f"  • 버전 증가 완료 ({bump_unit}): v{app_version}")
            else:
                app_version = vm.get_current_version()
                logd(f"  • 현재 버전 유지: v{app_version}")

            rc_file = os.path.join(self.project_root, "version_info.txt")
            generate_win_version_info(app_version, output_path=rc_file, app_name="PrintShopApp")
            logd(f"  • 리소스 파일 생성 완료: {rc_file}")

            msg = f"Version v{app_version} synchronized"
            self._record_result(step_name, "SUCCESS", msg)
            return app_version
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step4_1_build_main_app(self, venv_python: str):
        """[Step 4-1] PyInstaller(.spec)를 이용해 메인 애플리케이션(PrintShopApp)을 빌드합니다."""
        step_name = "Step 4-1: Build Main App"
        logd(f"\n[{step_name}] 메인 애플리케이션(PrintShopApp) PyInstaller 패키지 빌드...")
        try:
            subprocess.run([self.venv_python, "-m", "pip", "install", "pyinstaller"], stdout=subprocess.DEVNULL, check=True)

            spec_file = "PrintShopApp.spec"
            if not os.path.exists(spec_file):
                logd("  • PrintShopApp.spec 파일이 없어 자동 생성합니다...")
                subprocess.run([
                    self.venv_pyinstaller,
                    "--onefile",
                    "--noconsole",
                    "--name", "PrintShopApp",
                    os.path.join("src", "main_app.py")
                ], check=True)

            logd("  • 메인 애플리케이션(PrintShopApp.spec) 빌드 실행 중...")
            target_dist_dir = os.path.join(self.dist_dir, "PrintShopApp")
            target_work_dir = os.path.join(self.project_root, "build", "PrintShopApp")

            pyinstaller_cmd = [
                self.venv_pyinstaller,
                "PrintShopApp.spec",
                "--noconfirm",
                "--distpath", target_dist_dir,
                "--workpath", target_work_dir,                
                "--log-level=DEBUG",
            ]
            subprocess.run(pyinstaller_cmd, check=True)

            msg = "Main application built successfully"
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step4_2_build_sub_app(self, venv_python: str):
        """[Step 4-2] UpdateServiceBuilder를 호출하여 venv_python을 사용해 서브 앱을 빌드합니다."""
        step_name = "Step 4-2: Build Sub App (UpdateService)"
        logd(f"\n[{step_name}] 서브 모듈(UpdateService) 빌드 실행 (Venv Python: {venv_python})...")
        try:
            from src.build_script.build_update_service import UpdateServiceBuilder

            # venv_python을 전달하여 서브 빌더 초기화 (서브 빌더 클래스 생성자에 python_path 인자 추가 필요)
            sub_builder = UpdateServiceBuilder(python_path=venv_python)
            sub_result = sub_builder.run()

            for sub_step_name, info in sub_result["steps"].items():
                self._record_result(f"  └─ {sub_step_name}", info["status"], info["message"])

            if not sub_result["success"]:
                raise RuntimeError("UpdateService 서브 빌드 단계 중 실패가 발생했습니다.")

            msg = f"Sub application v{sub_result['version']} built successfully"
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step4_3_build_sub_app(self, venv_python: str):
        """[Step 4-3] UpdateManagerBuilder를 호출하여 venv_python을 사용해 서브 앱을 빌드합니다."""
        step_name = "Step 4-3: Build Sub App (UpdateManager)"
        logd(f"\n[{step_name}] 서브 모듈(UpdateManager) 빌드 실행 (Venv Python: {venv_python})...")
        try:
            from src.build_script.build_update_manager import UpdateManagerBuilder

            sub_builder = UpdateManagerBuilder(python_path=venv_python)
            sub_result = sub_builder.run()

            for sub_step_name, info in sub_result["steps"].items():
                self._record_result(f"  └─ {sub_step_name}", info["status"], info["message"])

            if not sub_result["success"]:
                raise RuntimeError("UpdateManager 서브 빌드 단계 중 실패가 발생했습니다.")

            msg = f"Sub application v{sub_result['version']} built successfully"
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step4_4_build_sub_app(self, venv_python: str):
        """[Step 4-4] VersionViewerBuilder를 호출하여 venv_python을 사용해 서브 앱을 빌드합니다."""
        step_name = "Step 4-4: Build Sub App (VersionViewer)"
        logd(f"\n[{step_name}] 서브 모듈(VersionViewer) 빌드 실행 (Venv Python: {venv_python})...")
        try:
            from src.build_script.build_version_viewer import VersionViewerBuilder

            sub_builder = VersionViewerBuilder(python_path=venv_python)
            sub_result = sub_builder.run()

            for sub_step_name, info in sub_result["steps"].items():
                self._record_result(f"  └─ {sub_step_name}", info["status"], info["message"])

            if not sub_result["success"]:
                raise RuntimeError("VersionViewer 서브 빌드 단계 중 실패가 발생했습니다.")

            msg = f"Sub application v{sub_result['version']} built successfully"
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step5_inject_eof_encryption(self, app_version: str, mode: str):
        """[Step 5] dist/PrintShopApp 폴더 내부의 실행 파일에 EOF 버전 암호화를 주입하고 검증합니다."""
        step_name = "Step 5: EOF Encryption & Verify"
        logd(f"\n[{step_name}] 실행 파일 EOF 버전 암호화 주입 및 검증...")
        try:
            app_folder = os.path.join(self.dist_dir, "PrintShopApp")
            exe_path = os.path.join(app_folder, "PrintShopApp.exe")
            expected_payload = f"v{app_version}-{mode}"

            if not os.path.exists(exe_path):
                raise FileNotFoundError(f"암호화 대상 실행 파일을 찾을 수 없습니다: {exe_path}")

            encrypt_and_append_version(exe_path, expected_payload)
            logd(f"  • EOF 암호화 페이로드 삽입 완료: {expected_payload}")

            read_payload = extract_version_from_exe(exe_path)
            if read_payload == expected_payload:
                logd(f"  ✅ EOF 버전 검증 성공: 일치함 ({read_payload})")
            else:
                raise ValueError(f"예상값('{expected_payload}')과 읽어온 값('{read_payload}')이 일치하지 않습니다.")

            msg = f"Encrypted & Verified ({expected_payload})"
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step6_sync_test_environment(self):
        """[Step 6] 기존 test/data 폴더를 보존한 채 최신 빌드 결과물만 test 폴더에 덮어씁니다."""
        step_name = "Step 6: Sync Test Environment"
        logd(f"\n[{step_name}] 내부 테스트 환경('test') 동기화...")
        try:
            test_dir = os.path.join(self.project_root, "test")
            os.makedirs(test_dir, exist_ok=True)
            os.makedirs(os.path.join(test_dir, "data"), exist_ok=True)

            for item in os.listdir(self.dist_dir):
                if item.lower() == "data":
                    continue

                src_path = os.path.join(self.dist_dir, item)
                dst_path = os.path.join(test_dir, item)

                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dst_path)

            msg = "Test directory synchronized (data preserved)"
            logd(f"  ✅ '{test_dir}' 폴더 내 실행 파일 최신화 완료")
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step7_create_update_zip(self, app_version: str) -> str:
        """[Step 7] GitHub Releases 업로드용 update_v<버전>.zip 압축 패키지를 생성합니다."""
        step_name = "Step 7: Create Update ZIP"
        logd(f"\n[{step_name}] GitHub Releases용 자동 업데이트 패키지(.zip) 생성...")
        try:
            releases_dir = os.path.join(self.project_root, "releases")
            os.makedirs(releases_dir, exist_ok=True)
            
            zip_filename = f"update_v{app_version}.zip"
            zip_output_path = os.path.join(releases_dir, zip_filename)

            if os.path.exists(zip_output_path):
                os.remove(zip_output_path)

            with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(self.dist_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, self.dist_dir)
                        zf.write(full_path, rel_path)

            msg = f"Created {zip_filename}"
            logd(f"  ✅ 업데이트 패키지 생성 완료: releases\\{zip_filename}")
            self._record_result(step_name, "SUCCESS", msg)
            return zip_output_path
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step8_create_windows_installer(self, mode: str, skip_installer: bool):
        """[Step 8] Inno Setup(ISCC.exe)을 사용하여 최종 Windows 인스톨러(.exe)를 생성합니다."""
        step_name = "Step 8: Windows Installer"
        logd(f"\n[{step_name}] Inno Setup Windows 설치 프로그램(.exe) 컴파일...")
        
        if skip_installer:
            msg = "Skipped by option (--skip-installer)"
            logd(f"  ℹ️ {msg}")
            self._record_result(step_name, "SKIPPED", msg)
            return

        try:
            iscc_exe = self.find_iscc()
            if not iscc_exe:
                msg = "ISCC.exe not found. Installer generation skipped."
                logd(f"  ⚠️ {msg}")
                self._record_result(step_name, "SKIPPED", msg)
                return

            installer_dir = os.path.join(self.project_root, "installer")
            os.makedirs(installer_dir, exist_ok=True)

            setup_name = "PrintShopAppDev_Setup" if mode == "development" else "PrintShopApp_Setup"
            setup_output = os.path.join(installer_dir, f"{setup_name}.exe")
            if os.path.exists(setup_output):
                os.remove(setup_output)

            updater_version_file = os.path.join(self.project_root, "src", "UpdateService", "version.txt")
            updater_version = "1.2.0"
            if os.path.exists(updater_version_file):
                with open(updater_version_file, "r", encoding="utf-8") as f:
                    updater_version = f.read().strip()

            include_iss_path = os.path.join(self.project_root, "version_include.iss")
            with open(include_iss_path, "w", encoding="utf-8") as f:
                f.write(f'#define UpdaterVersion "{updater_version}"\n')
            logd(f"  • 버전 헤더 생성 완료: {include_iss_path} (Updater v{updater_version})")

            iss_script = os.path.join(self.project_root, "installer.iss")
            subprocess.run(
                [
                    iscc_exe,
                    f"/DSourceDir={self.project_root}",
                    f"/DOutputBaseFilename={setup_name}",
                    iss_script
                ],
                check=True
            )
            msg = f"Created {setup_name}.exe"
            logd(f"  ✅ 최종 설치 파일 생성 완료: installer\\{setup_name}.exe")
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def run(self, bump_unit: str | None, skip_installer: bool):
        """전체 빌드 파이프라인 오케스트레이션을 실행하고 최종 결과를 요약합니다."""
        logd("=" * 65)
        logd("  🚀 Starting PrintShopApp Distribution Build Pipeline (BuildApp)")
        logd("=" * 65)

        try:
            self.step1_convert_ui_files()
            venv_python, mode = self.step2_setup_environment_and_config()
            app_version = self.step3_sync_version_and_resources(bump_unit)
            
            # 메인 앱 및 서브 앱 빌드 함수 호출 (venv_python 전달)
            self.step4_1_build_main_app(venv_python)
            self.step4_2_build_sub_app(venv_python)
            self.step4_3_build_sub_app(venv_python)
            self.step4_4_build_sub_app(venv_python)
            
            self.step5_inject_eof_encryption(app_version, mode)
            self.step6_sync_test_environment()
            self.step7_create_update_zip(app_version)
            self.step8_create_windows_installer(mode, skip_installer)

            logd("\n" + "=" * 65)
            logd(f"  🎉 모든 빌드 및 패키징 파이프라인이 성공적으로 완료되었습니다! (v{app_version})")
            logd("=" * 65)

        except Exception as e:
            logd(f"\n[FAILED] 빌드 프로세스 중 예외가 발생했습니다: {e}")
            
        finally:
            self.print_summary()


def main():
    parser = argparse.ArgumentParser(description="PrintShopApp Unified Build and Distribution Packaging Script")
    parser.add_argument(
        "--bump", choices=["major", "minor", "patch"], default=None,
        help="빌드 전 자동으로 증가시킬 버전 단위 (생략 시 현재 버전 유지)"
    )
    parser.add_argument(
        "--skip-installer", action="store_true",
        help="Inno Setup(.exe 인스톨러) 생성 단계를 건너뜁니다"
    )
    args = parser.parse_args()

    builder = BuildApp()
    builder.run(bump_unit=args.bump, skip_installer=args.skip_installer)


if __name__ == "__main__":
    main()