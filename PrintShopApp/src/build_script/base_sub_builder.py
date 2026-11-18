import os
import sys
import glob
import shutil
import subprocess

from Common.log import logd, loge

class BaseSubBuilder:
    """모든 서브 애플리케이션 빌더가 상속받는 공통 빌드 파이프라인 부모 클래스"""

    def __init__(
        self,
        source_dir: str,
        app_name: str,
        exe_name: str,
        spec_name: str,
        sub_folder_name: str,
        python_path: str = None,
        dist_to_main_folder: bool = True
    ):
        self.source_dir = os.path.abspath(source_dir)
        self.project_root = os.path.abspath(os.path.join(self.source_dir, "..", ".."))
        
        # 💡 python_path가 전달되지 않으면 프로젝트 루트의 .venv 경로를 자동으로 공통 탐색
        self.python_path = python_path or self._resolve_python_path()

        self.app_name = app_name
        self.exe_name = exe_name
        self.spec_name = spec_name
        self.sub_folder_name = sub_folder_name

        # 공용 버전 및 암호화 스크립트 경로
        self.version_dir = os.path.abspath(os.path.join(self.source_dir, "..", "Common", "Version"))
        self.crypto_script_path = os.path.join(self.version_dir, "exe_version_crypto.py")
        self.version_manager_path = os.path.join(self.version_dir, "version_manager.py")

        # 빌드 및 배포 경로 설정
        self.pyinst_path = self._get_pyinstaller_path()
        self.work_dir = os.path.join(self.project_root, "build", self.sub_folder_name)
        
        if dist_to_main_folder:
            self.dist_dir = os.path.join(self.project_root, "dist", "PrintShopApp")
        else:
            self.dist_dir = os.path.join(self.project_root, "dist", self.sub_folder_name)
            
        self.test_dir = os.path.join(self.project_root, "test", self.sub_folder_name)

        self.version = "0.0.0"
        self.results = {}

    def _resolve_python_path(self) -> str:
        """[공통] 프로젝트 내 가상환경(.venv) 파이썬 경로를 우선 탐색하고, 없으면 현재 실행 중인 파이썬을 반환합니다."""
        venv_python = os.path.join(self.project_root, ".venv", "Scripts", "python.exe")
        if os.path.exists(venv_python):
            return venv_python
        return sys.executable

    def _get_pyinstaller_path(self) -> str:
        """[공통] 가상환경 내 PyInstaller 실행 파일 경로를 반환합니다."""
        venv_pyinst = os.path.join(self.project_root, ".venv", "Scripts", "pyinstaller.exe")
        return venv_pyinst if os.path.exists(venv_pyinst) else "pyinstaller"

    def _record_result(self, step_name: str, status: str, message: str):
        self.results[step_name] = {"status": status, "message": message}

    def print_summary(self):
        logd("\n" + "-" * 65)
        logd(f"  📋 {self.sub_folder_name} Sub-Build Execution Summary")
        logd("-" * 65)
        for step, info in self.results.items():
            icon = "✅" if info["status"] == "SUCCESS" else ("⏭️" if info["status"] == "SKIPPED" else "❌")
            logd(f"  {icon} [{step}] - {info['status']}")
            logd(f"     └─ {info['message']}")
        logd("-" * 65)

    def step1_convert_ui_files(self):
        step_name = "Sub-Step 1: UI Compile"
        logd(f"🔍 [{step_name}] ({self.sub_folder_name}) .ui 파일 검색 및 변환 시작...")
        try:
            ui_files = glob.glob("**/*.ui", recursive=True)
            if not ui_files:
                msg = "변환할 .ui 파일이 없습니다."
                logd(f"  ℹ️ {msg}\n")
                self._record_result(step_name, "SUCCESS", msg)
                return

            venv_bin_dir = os.path.dirname(self.python_path)
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
                    subprocess.run([self.python_path, "-m", "PySide6.uic", ui_path, "-o", py_output_path], check=True)

            msg = f"총 {len(ui_files)}개 UI 파일 변환 완료"
            logd(f"  ✅ {msg}\n")
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"오류 발생: {e}"
            logd(f"  ❌ {msg}")
            self._record_result(step_name, "FAILED", msg)
            raise

    def step2_bump_version(self) -> str:
        step_name = "Sub-Step 2: Bump Version"
        logd("========================================================")
        logd(f" [{step_name}] {self.sub_folder_name} 버전 자동 증가 처리 중...")
        logd("========================================================")
        try:
            subprocess.run([self.python_path, self.version_manager_path, "patch", "--dir", "."], check=True)

            version_file = os.path.join(self.source_dir, "version.txt")
            if not os.path.exists(version_file):
                raise FileNotFoundError("version.txt 파일을 찾을 수 없습니다.")

            with open(version_file, "r", encoding="utf-8") as f:
                self.version = f.read().strip()

            msg = f"새 버전 v{self.version} 적용 완료"
            logd(f"  ✅ {msg}\n")
            self._record_result(step_name, "SUCCESS", msg)
            return self.version
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step3_generate_rc(self):
        step_name = "Sub-Step 3: Generate RC"
        logd("========================================================")
        logd(f" [{step_name}] PyInstaller용 버전 리소스 생성 중...")
        logd("========================================================")
        try:
            subprocess.run([
                self.python_path, self.crypto_script_path, "gen-rc",
                "--version-file", "version.txt",
                "--out", "version_info.txt",
                "--name", self.app_name
            ], check=True)
            msg = "version_info.txt 생성 완료"
            logd(f"  ✅ {msg}\n")
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step4_build_executable(self):
        step_name = "Sub-Step 4: PyInstaller Build"
        logd("========================================================")
        logd(f" [{step_name}] {self.spec_name} 빌드 중...")
        logd("========================================================")
        try:
            os.makedirs(self.work_dir, exist_ok=True)
            os.makedirs(self.dist_dir, exist_ok=True)

            # 💡 [추가] 지정된 spec 파일이 존재하지 않는 경우 자동 생성 루틴
            if not os.path.exists(self.spec_name):
                logd(f"  ℹ️ '{self.spec_name}' 파일이 없어 자동으로 생성합니다...")
                # 서브 프로젝트의 진입점 파일 이름 추정 (예: print_shop_update_service.py 등)
                entry_point = f"{'main_app'}.py"
                if not os.path.exists(entry_point):
                    # 만약 진입점 파일명이 다를 경우 현재 폴더의 메인 파이썬 파일 탐색
                    py_files = [f for f in os.listdir(".") if f.endswith(".py") and f != "build" and not f.startswith("ui_")]
                    if py_files:
                        entry_point = py_files[0]
                    else:
                        raise FileNotFoundError(f"빌드할 진입점 파이썬 파일을 찾을 수 없습니다.")

                subprocess.run([
                    self.pyinst_path,
                    "--onefile",
                    "--noconsole",  # GUI 앱인 경우 유지, 콘솔 앱이면 제거 가능
                    "--version-file", "version_info.txt",
                    "--name", self.app_name,
                    entry_point
                ], check=True)
                logd(f"  ✅ '{self.spec_name}' 자동 생성 완료")

            # 기존 빌드 실행
            subprocess.run([
                self.pyinst_path,
                self.spec_name,
                "--noconfirm",
                "--clean",
                "--distpath", self.dist_dir,
                "--workpath", self.work_dir
            ], check=True)
            
            msg = f"{self.exe_name} 빌드 완료"
            logd(f"  ✅ {msg}\n")
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            logd(f"  ❌ {msg}")
            self._record_result(step_name, "FAILED", msg)
            raise

    def step5_inject_eof_encryption(self):
        step_name = "Sub-Step 5: EOF Encryption"
        logd("========================================================")
        logd(f" [{step_name}] EXE 파일 EOF 암호화 토큰 주입 중...")
        logd("========================================================")
        try:
            target_exe_path = os.path.join(self.dist_dir, self.exe_name)
            if not os.path.exists(target_exe_path):
                raise FileNotFoundError(f"빌드된 실행 파일을 찾을 수 없습니다: {target_exe_path}")

            subprocess.run([
                self.python_path, self.crypto_script_path, "inject",
                "--exe", target_exe_path,
                "--version-file", "version.txt",
                "--mode", "production"
            ], check=True)
            msg = f"EOF 암호화 주입 완료 (v{self.version})"
            logd(f"  ✅ {msg}\n")
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def step6_sync_test_environment(self):
        step_name = "Sub-Step 6: Sync Test Env"
        logd("========================================================")
        logd(f" [{step_name}] 테스트 환경({self.test_dir}) 동기화 중...")
        logd("========================================================")
        try:
            os.makedirs(self.test_dir, exist_ok=True)
            src_exe = os.path.join(self.dist_dir, self.exe_name)
            dst_exe = os.path.join(self.test_dir, self.exe_name)
            shutil.copy2(src_exe, dst_exe)
            
            msg = f"동기화 완료 ({self.test_dir})"
            logd(f"  ✅ {msg}\n")
            self._record_result(step_name, "SUCCESS", msg)
        except Exception as e:
            msg = f"실패: {e}"
            self._record_result(step_name, "FAILED", msg)
            raise

    def run(self) -> dict:
        original_cwd = os.getcwd()
        os.chdir(self.source_dir)
        overall_success = False

        try:
            self.step1_convert_ui_files()
            self.step2_bump_version()
            self.step3_generate_rc()
            self.step4_build_executable()
            self.step5_inject_eof_encryption()
            self.step6_sync_test_environment()

            overall_success = True
            logd("========================================================")
            logd(f" 🎉 {self.sub_folder_name} 빌드 및 패키징 완료! (v{self.version})")
            logd("========================================================")
        except Exception as e:
            logd(f"\n❌ [FAILED] {self.sub_folder_name} 빌드 중 오류 발생: {e}")
        finally:
            os.chdir(original_cwd)
            self.print_summary()

        return {
            "success": overall_success,
            "version": self.version,
            "steps": self.results
        }