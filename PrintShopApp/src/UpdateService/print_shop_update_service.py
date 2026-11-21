# print_shop_update_service.py
import configparser
import ctypes
from ctypes import wintypes
from datetime import datetime
import os
import shutil
import subprocess
import sys
import threading
import time
import winreg
import zipfile

from packaging import version
import psutil
import requests
import servicemanager
import win32event
import win32security
import win32service
import win32serviceutil
import win32ts

from Protocol.update_service_protocol import DEFAULT_PORT, ResponseCode
from UpdateService.update_service_protocol_handler import UpdateServiceProtocolHandler
from UpdateService.update_service_commands import UpdateServiceCommands

SERVICE_NAME = "PrintShopUpdateService"
PORT = DEFAULT_PORT

try:
    from version import VERSION as UPDATER_VERSION, NAME as UPDATER_NAME
except ImportError:
    UPDATER_VERSION = "1.2.0"
    UPDATER_NAME = "PrintShopUpdateService"

SERVICE_DISPLAY_NAME = f"PrintShop Updater & Watchdog Service v{UPDATER_VERSION}"
REG_KEY_PATH = f"SOFTWARE\\{UPDATER_NAME}"

APP_EXE_NAME = "PrintShopApp.exe"
MAIN_APP_CURRENT_VERSION = "1.2.0"

APP_CHECK_INTERVAL_SEC = 5
GITHUB_UPDATE_VERSION_CHECK_INTERVAL = 1800


class ConfigManager:
    """INI 파일과 Windows 레지스트리에 서버 설정을 동시 저장 및 로드하는 클래스"""

    def __init__(self, app_dir: str):
        self.app_dir = app_dir
        self.ini_path = os.path.join(app_dir, "config.ini")
        self.reg_key_path = REG_KEY_PATH
        self.config = configparser.ConfigParser()

    def save_config(self, repo_url: str, json_url: str) -> bool:
        success_ini = False
        success_reg = False

        try:
            if not self.config.has_section("ServerConfig"):
                self.config.add_section("ServerConfig")
            self.config.set("ServerConfig", "repo_url", repo_url)
            self.config.set("ServerConfig", "json_url", json_url)
            with open(self.ini_path, "w", encoding="utf-8") as f:
                self.config.write(f)
            success_ini = True
        except Exception as e:
            servicemanager.LogErrorMsg(f"[Config] INI 저장 실패: {e}")

        try:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, self.reg_key_path)
            winreg.SetValueEx(key, "RepoUrl", 0, winreg.REG_SZ, repo_url)
            winreg.SetValueEx(key, "JsonUrl", 0, winreg.REG_SZ, json_url)
            winreg.CloseKey(key)
            success_reg = True
        except Exception as e:
            servicemanager.LogErrorMsg(f"[Config] 레지스트리 저장 실패: {e}")

        return success_ini or success_reg

    def load_config(self) -> dict:
        repo_url, json_url = "", ""
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.reg_key_path, 0, winreg.KEY_READ)
            repo_url, _ = winreg.QueryValueEx(key, "RepoUrl")
            json_url, _ = winreg.QueryValueEx(key, "JsonUrl")
            winreg.CloseKey(key)
            if repo_url or json_url:
                return {"repo_url": repo_url, "json_url": json_url}
        except Exception:
            pass

        if os.path.exists(self.ini_path):
            try:
                self.config.read(self.ini_path, encoding="utf-8")
                if self.config.has_section("ServerConfig"):
                    repo_url = self.config.get("ServerConfig", "repo_url", fallback="")
                    json_url = self.config.get("ServerConfig", "json_url", fallback="")
                    if repo_url or json_url:
                        self.save_config(repo_url, json_url)
                    return {"repo_url": repo_url, "json_url": json_url}
            except Exception:
                pass

        return {"repo_url": "", "json_url": ""}


class CentralUpdaterService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME

    def __init__(self, args):
        super().__init__(args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = True

        self.service_dir = os.path.dirname(
            os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
        )
        self.app_dir = os.path.abspath(os.path.join(self.service_dir, ".."))
        self.main_exe_path = os.path.join(self.app_dir, APP_EXE_NAME)

        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        self.data_dir = os.path.join(local_app_data, "PrintShopApp")
        self.versions_dir = os.path.join(self.data_dir, "versions")
        self.backup_dir = os.path.join(self.versions_dir, "backups")

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.versions_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self.config_mgr = ConfigManager(self.data_dir)
        self.saved_config = self.config_mgr.load_config()
        self.current_app_version = MAIN_APP_CURRENT_VERSION

        self.status_info = {
            "phase": "IDLE",
            "progress": 0,
            "message": "시스템 대기 중...",
            "version": "",
        }

        # 메인앱 자동 재실행(launch_main_app) 활성화 여부 기본값 True
        self.launch_main_app_enabled = True

        # 프로토콜/UDP 핸들러 및 표준 커맨드 구현체 초기화
        self.protocol_handler = UpdateServiceProtocolHandler(
            port=PORT,
            log_fn=self.info,
            on_apply_update=self.execute_update_process,
            on_rollback=self.execute_rollback_process,
        )
        self.command_impl = UpdateServiceCommands(
            packet_builder=self.protocol_handler.packet_builder,
            on_get_status=lambda: self.status_info,
            on_get_versions=self.get_available_backup_versions,
            on_get_paths=self._get_service_paths,
            on_get_heartbeat=self.protocol_handler.get_heartbeat_status,
            on_set_github_config=self._handle_set_github_config,
            on_get_github_config=self.config_mgr.load_config,
            on_github_test=self._handle_github_test,
            on_set_restart_function=self._handle_set_restart_function,
            on_get_restart_function=lambda: self.launch_main_app_enabled,
        )
        self.protocol_handler.command_impl = self.command_impl

    def info(self, phase: str, progress: int, msg: str, ver: str = ""):
        self.status_info["phase"] = phase
        self.status_info["progress"] = progress
        self.status_info["message"] = msg
        if ver:
            self.status_info["version"] = ver
        servicemanager.LogInfoMsg(f"[SCENARIO INFO] Phase: {phase} ({progress}%) - {msg}")

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.is_running = False
        self.protocol_handler.stop_server()
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        self.info("IDLE", 0, "중앙 업데이터 및 Watchdog 서비스가 기동되었습니다.")
        self.verify_main_app_existence()

        threading.Thread(target=self._github_background_downloader, daemon=True).start()

        if not self.protocol_handler.start_server():
            return

        check_app_timer = time.time()
        while self.is_running:
            current_time = time.time()
            if current_time - check_app_timer > APP_CHECK_INTERVAL_SEC:
                check_app_timer = current_time
                if not self.is_main_app_running():
                    if self.launch_main_app_enabled:
                        self.info("LAUNCH", 0, f"메인 프로그램({APP_EXE_NAME})이 프로세스에 없어 자동 실행합니다.")
                        self.launch_main_app()
                    else:
                        self.info("LAUNCH_SKIPPED", 0, f"메인 프로그램({APP_EXE_NAME})이 비활성화 설정으로 인해 자동 실행되지 않습니다.")

            if self.protocol_handler.check_heartbeat_health(current_time, self.is_main_app_running()):
                self.info("WATCHDOG_TIMEOUT", 0, "⚠️ 메인 앱 응답 없음! 직전 안정 버전으로 긴급 롤백을 수행합니다.")
                self.trigger_latest_rollback()

            self.protocol_handler.poll_once()

        self.protocol_handler.stop_server()

    # ------------------------------------------------------------------
    # 프로토콜 커맨드 콜백 메서드
    # ------------------------------------------------------------------
    def _get_service_paths(self) -> dict:
        return {
            "main_exe_path": self.main_exe_path,
            "updater_exe_path": sys.executable if getattr(sys, "frozen", False) else __file__,
            "updater_service_dir": self.service_dir,
        }

    def _handle_set_restart_function(self, enabled: bool):
        self.launch_main_app_enabled = enabled
        self.info("SET_RESTART_FUNCTION", 0, f"메인 앱 자동 재실행 설정 변경: {enabled}")

    def _handle_set_github_config(self, repo_url: str, json_url: str) -> tuple[int, dict]:
        if not repo_url or not json_url:
            return ResponseCode.INVALID_PACKET, {}
        if self.config_mgr.save_config(repo_url, json_url):
            self.saved_config = {"repo_url": repo_url, "json_url": json_url}
            return ResponseCode.TEST_SUCCESS, {"saved": True, "repo_url": repo_url, "json_url": json_url}
        return ResponseCode.EXCEPTION, {}

    def _handle_github_test(self, repo_url: str, json_url: str) -> tuple[int, dict]:
        saved = self.config_mgr.load_config()
        target_repo = repo_url or saved.get("repo_url", "")
        target_json = json_url or saved.get("json_url", "")
        if not target_json:
            return ResponseCode.INVALID_PACKET, {}

        try:
            r = requests.get(target_json, timeout=5)
            if r.status_code != 200:
                return ResponseCode.TEST_FAILED, {}

            data = r.json()
            if not isinstance(data, dict) or "version" not in data:
                return ResponseCode.TEST_FAILED, {}

            return ResponseCode.TEST_SUCCESS, {
                "result": ResponseCode.TEST_SUCCESS,
                "status_code": r.status_code,
                "repo_url": target_repo,
                "json_url": target_json,
                "version": data.get("version"),
                "download_url": data.get("download_url", ""),
            }
        except Exception:
            return ResponseCode.EXCEPTION, {}

    # ------------------------------------------------------------------
    # 서비스 핵심 로직 (다운로드 / 업데이트 / 롤백 / 프로세스 실행)
    # ------------------------------------------------------------------
    def verify_main_app_existence(self) -> bool:
        if os.path.exists(self.main_exe_path):
            self.info("PATH_CHECK", 0, f"✅ 메인 앱 경로 확인됨: {self.main_exe_path}")
            return True
        self.info("PATH_CHECK_FAIL", 0, f"❌ 경고: 지정된 경로에 메인 앱이 존재하지 않습니다! ({self.main_exe_path})")
        return False

    def _github_background_downloader(self):
        while self.is_running:
            json_url = self.config_mgr.load_config().get("json_url", "")
            if json_url:
                try:
                    res = requests.get(json_url, timeout=5)
                    if res.status_code == 200:
                        data = res.json()
                        latest_ver = str(data.get("version", "")).strip()
                        download_url = str(data.get("download_url", "")).strip()

                        if latest_ver and download_url and version.parse(latest_ver) > version.parse(self.current_app_version):
                            ver_folder = os.path.join(self.versions_dir, f"v{latest_ver}")
                            os.makedirs(ver_folder, exist_ok=True)
                            zip_path = os.path.join(ver_folder, f"update_v{latest_ver}.zip")

                            if not os.path.exists(zip_path):
                                self.info("DOWNLOADING", 0, f"새 버전 v{latest_ver} 다운로드 중...", latest_ver)
                                r = requests.get(download_url, stream=True, timeout=10)
                                r.raise_for_status()
                                with open(zip_path, "wb") as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        if chunk:
                                            f.write(chunk)

                            if zipfile.is_zipfile(zip_path):
                                self.info("DOWNLOADED", 100, f"새 버전 v{latest_ver} 검증 완료 및 저장됨: {zip_path}", latest_ver)
                except Exception as e:
                    self.info("DOWNLOAD_ERROR", 0, f"다운로드 중 예외 발생: {e}")

            for _ in range(GITHUB_UPDATE_VERSION_CHECK_INTERVAL):
                if not self.is_running:
                    break
                time.sleep(1)

    def _terminate_main_app_if_needed(self, self_shutdown: bool):
        if self.is_main_app_running() and not self_shutdown:
            self.info("UPDATE_KILL", 40, f"실행 중인 메인 앱({APP_EXE_NAME})을 종료합니다.")
            subprocess.run(["taskkill", "/f", "/im", APP_EXE_NAME], capture_output=True)
            time.sleep(1)

    def execute_update_process(self, target_version: str, self_shutdown: bool) -> bool:
        success = False
        try:
            self.info("UPDATE_START", 20, f"버전 v{target_version} 업데이트 적용 프로세스를 시작합니다.", target_version)

            zip_path = os.path.join(self.versions_dir, f"v{target_version}", f"update_v{target_version}.zip")
            if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
                self.info("UPDATE_FAIL", 0, f"업데이트 패키지를 찾을 수 없습니다: {zip_path}", target_version)
                return False

            self._terminate_main_app_if_needed(self_shutdown)
            self.backup_current_version(self.current_app_version)

            extract_dir = os.path.join(self.versions_dir, f"v{target_version}", "extracted")
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir, ignore_errors=True)
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            self.info("UPDATE_COPY", 70, "파일 교체 복사 중...", target_version)
            shutil.copytree(extract_dir, self.app_dir, dirs_exist_ok=True)

            if target_version:
                self.current_app_version = target_version

            self.info("UPDATE_RELAUNCH", 90, "🔄 업데이트 패키지 적용 완료. 메인 앱을 재기동합니다.", target_version)
            self.launch_main_app()
            self.info("UPDATE_SUCCESS", 100, f"버전 v{target_version} 업데이트 완료.", target_version)
            success = True
            return True
        except Exception as e:
            self.info("UPDATE_ERROR", 0, f"업데이트 중 예외 발생: {e}", target_version)
            return False
        finally:
            if not success:
                self.info("UPDATE_RECOVERY", 0, "⚠️ 업데이트 실패 감지: 자동 복구(롤백 또는 강제 기동)를 시도합니다.")
                versions = self.get_available_backup_versions()
                recovered = False
                if versions:
                    latest_backup = versions[0]
                    self.info("UPDATE_RECOVERY", 50, f"직전 백업 버전(v{latest_backup})으로 긴급 롤백을 시도합니다.")
                    recovered = self.execute_rollback_process(latest_backup, True)

                if not recovered:
                    self.info("UPDATE_RECOVERY", 100, "🚨 복구 가능한 백업이 없거나 롤백 실패. 시스템 가동을 위해 메인 앱을 강제 기동합니다.")
                    self.launch_main_app()

    def execute_rollback_process(self, target_version: str, self_shutdown: bool) -> bool:
        success = False
        try:
            self.info("ROLLBACK_START", 20, f"버전 v{target_version}으로 롤백을 시작합니다.", target_version)
            base_name = APP_EXE_NAME.replace(".exe", "").lower()
            target_zip = os.path.join(self.backup_dir, f"{base_name}_v{target_version}.zip")
            if not os.path.exists(target_zip) or not zipfile.is_zipfile(target_zip):
                self.info("ROLLBACK_FAIL", 0, f"롤백 대상 백업 파일을 찾을 수 없습니다: {target_zip}", target_version)
                return False

            self._terminate_main_app_if_needed(self_shutdown)

            temp_dir = os.environ.get("TEMP", "C:\\Temp")
            extract_dir = os.path.join(temp_dir, "extracted_rollback")
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir, ignore_errors=True)
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(target_zip, "r") as zf:
                zf.extractall(extract_dir)

            shutil.copytree(extract_dir, self.app_dir, dirs_exist_ok=True)

            if target_version:
                self.current_app_version = target_version

            self.info("ROLLBACK_RELAUNCH", 90, "🔄 롤백 패키지 적용 완료. 메인 앱을 재기동합니다.", target_version)
            self.launch_main_app()
            self.info("ROLLBACK_SUCCESS", 100, f"버전 v{target_version} 롤백 완료.", target_version)
            success = True
            return True
        except Exception as e:
            self.info("ROLLBACK_ERROR", 0, f"롤백 중 예외 발생: {e}", target_version)
            return False
        finally:
            if not success:
                self.info("ROLLBACK_RECOVERY", 100, "🚨 롤백 실패. 메인 앱이 꺼진 상태로 방치되지 않도록 강제 기동을 시도합니다.")
                self.launch_main_app()

    def trigger_latest_rollback(self):
        versions = self.get_available_backup_versions()
        if versions:
            self.execute_rollback_process(versions[0], False)

    def backup_current_version(self, ver: str):
        base_name = APP_EXE_NAME.replace(".exe", "").lower()
        backup_zip = os.path.join(self.backup_dir, f"{base_name}_v{ver}.zip")
        if not os.path.exists(backup_zip) and os.path.exists(self.main_exe_path):
            with zipfile.ZipFile(backup_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(self.main_exe_path, arcname=APP_EXE_NAME)

    def get_available_backup_versions(self) -> list[str]:
        versions_list = []
        base_name = APP_EXE_NAME.replace(".exe", "").lower()
        prefix = f"{base_name}_v"

        if os.path.exists(self.backup_dir):
            for f in os.listdir(self.backup_dir):
                if f.startswith(prefix) and f.endswith(".zip"):
                    ver_str = f.replace(prefix, "").replace(".zip", "")
                    versions_list.append(ver_str)
        versions_list.sort(key=lambda s: version.parse(s), reverse=True)
        return versions_list

    def is_main_app_running(self) -> bool:
        try:
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] and proc.info["name"].lower() == APP_EXE_NAME.lower():
                    return True
            return False
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception:
            return False

    def launch_main_app(self):
        if not os.path.exists(self.main_exe_path):
            self.info("LAUNCH_FAIL", 0, f"❌ 메인 앱 실행 실패: 파일 경로를 찾을 수 없습니다 ({self.main_exe_path})")
            return

        self.protocol_handler.notify_app_launched()

        try:
            subprocess.run(["taskkill", "/f", "/im", APP_EXE_NAME], capture_output=True)
            time.sleep(0.5)

            active_session_id = win32ts.WTSGetActiveConsoleSessionId()
            if active_session_id == 0xFFFFFFFF:
                self.info("LAUNCH_FAIL", 0, "❌ 활성화된 사용자 세션을 찾을 수 없습니다.")
                return

            h_user_token = None
            for proc in psutil.process_iter(["name", "pid", "username"]):
                try:
                    if proc.info["name"] and proc.info["name"].lower() == "explorer.exe":
                        pid = proc.info["pid"]
                        if ctypes.windll.kernel32.ProcessIdToSessionId(pid) == active_session_id:
                            PROCESS_QUERY_INFORMATION = 0x0400
                            h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
                            if h_proc:
                                h_tok = wintypes.HANDLE()
                                if ctypes.windll.advapi32.OpenProcessToken(h_proc, 0x0002 | 0x0008, ctypes.byref(h_tok)):
                                    h_user_token = h_tok
                                ctypes.windll.kernel32.CloseHandle(h_proc)
                                break
                except Exception:
                    continue

            if not h_user_token:
                h_user_token = wintypes.HANDLE()
                wtsapi32 = ctypes.windll.wtsapi32
                if not wtsapi32.WTSQueryUserToken(active_session_id, ctypes.byref(h_user_token)):
                    self.info("LAUNCH_FAIL", 0, "❌ 사용자 토큰 획득 실패")
                    return

            h_duplicated_token = wintypes.HANDLE()
            advapi32 = ctypes.windll.advapi32

            if not advapi32.DuplicateTokenEx(
                h_user_token,
                0xF01FF,
                None,
                win32security.SecurityIdentification,
                win32security.TokenPrimary,
                ctypes.byref(h_duplicated_token),
            ):
                self.info("LAUNCH_FAIL", 0, "❌ 토큰 복제 실패")
                ctypes.windll.kernel32.CloseHandle(h_user_token)
                return

            lp_environment = ctypes.c_void_p()
            userenv = ctypes.windll.userenv
            userenv.CreateEnvironmentBlock(ctypes.byref(lp_environment), h_duplicated_token, False)

            class STARTUPINFOW(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("lpReserved", wintypes.LPWSTR),
                    ("lpDesktop", wintypes.LPWSTR),
                    ("lpTitle", wintypes.LPWSTR),
                    ("dwX", wintypes.DWORD),
                    ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD),
                    ("dwYSize", wintypes.DWORD),
                    ("dwXCountChars", wintypes.DWORD),
                    ("dwYCountChars", wintypes.DWORD),
                    ("dwFillAttribute", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("wShowWindow", wintypes.WORD),
                    ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
                    ("hStdInput", wintypes.HANDLE),
                    ("hStdOutput", wintypes.HANDLE),
                    ("hStdError", wintypes.HANDLE),
                ]

            class PROCESS_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("hProcess", wintypes.HANDLE),
                    ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD),
                    ("dwThreadId", wintypes.DWORD),
                ]

            si = STARTUPINFOW()
            si.cb = ctypes.sizeof(STARTUPINFOW)
            si.lpDesktop = "winsta0\\default"
            pi = PROCESS_INFORMATION()

            success = advapi32.CreateProcessAsUserW(
                h_duplicated_token,
                None,
                ctypes.c_wchar_p(self.main_exe_path),
                None,
                None,
                False,
                0x00000400,
                lp_environment,
                None,
                ctypes.byref(si),
                ctypes.byref(pi),
            )

            if success:
                self.info("LAUNCH_SUCCESS", 100, f"✅ 메인 앱 실행 성공 (PID: {pi.dwProcessId})")
                ctypes.windll.kernel32.CloseHandle(pi.hProcess)
                ctypes.windll.kernel32.CloseHandle(pi.hThread)
            else:
                err = ctypes.GetLastError()
                self.info("LAUNCH_FAIL", 0, f"❌ CreateProcessAsUserW 최종 실패 (ErrorCode: {err})")

            userenv.DestroyEnvironmentBlock(lp_environment)
            ctypes.windll.kernel32.CloseHandle(h_duplicated_token)
            ctypes.windll.kernel32.CloseHandle(h_user_token)

        except Exception as e:
            self.info("LAUNCH_FAIL", 0, f"❌ 메인 앱 실행 중 예외 발생: {e}")


_service_mutex = None


def check_single_instance(mutex_name="Global\\PrintShopUpdateService_Mutex") -> bool:
    global _service_mutex
    kernel32 = ctypes.windll.kernel32
    _service_mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:
        return True
    return False


def logd(message: str):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] {message}")
