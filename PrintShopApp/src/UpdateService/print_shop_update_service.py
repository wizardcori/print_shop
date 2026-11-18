### 2. 실행 코드가 제거된 순수 서비스 및 설정 모듈: `print_shop_update_service.py`
# 파이썬 프로그램 업데이트 시스템 및 설정 관리 소스 코드 총정리
# (메인앱 프로세스 정밀 체크 및 versions\버전별 폴더 저장 적용 버전)

import os
import sys
import time
import socket
import json
import zipfile
import psutil
import shutil
import subprocess
import threading
import configparser
import winreg
import requests
from packaging import version
import win32serviceutil
import win32service
import win32event
import servicemanager
from datetime import datetime

import ctypes
from ctypes import wintypes
import win32security
import win32ts


APP_CHECK_INTERVAL_SEC = 30.0   # 메인 앱 프로세스 검사 주기 (초)
HEARTBEAT_TIMEOUT_SEC =  90.0    # 메인 앱 하트비트 응답 대기 제한 시간 (타임아웃)

SERVICE_NAME = "PrintShopUpdateService"
PORT = 54321

# ==============================================================================
# [시스템 아키텍처 기획 문서: 업데이트 & 롤백 및 가용성 보장 정책]
# ==============================================================================
#
# 1. 동시성 및 중복 실행 제어 정책 (Concurrency & Cooldown Policy)
#    - 상호 배타적 실행 (Mutual Exclusion):
#      'APPLY_UPDATE'와 'ROLLBACK'은 둘 다 메인 앱 종료, 파일 덮어쓰기(xcopy),
#      프로세스 재기동을 수행하므로 동시에 실행될 경우 파일 락(File Lock) 충돌 및
#      실행 파일 손상을 유발합니다. 따라서 단일 스레드 락(heavy_task_lock)과 상태 플래그
#      (is_heavy_task_running)를 통해 한 번에 오직 하나의 작업만 수행되도록 강제합니다.
#    - 쿨다운 제한 (Throttling / 명령어별 개별 적용):
#      COMMAND_COOLDOWN_MAP에 정의된 최소 허용 간격 이내에 들어오는 중복/교차 요청은 
#      시스템 안정화를 위해 즉시 거부(FREQUENT_REQUEST_THROTTLED)합니다. (GET_HEARTBEAT는 5초)
#    - 비동기 위임 처리:
#      압축 해제 및 파일 복사 소요 시간으로 인한 UDP 소켓 블로킹을 방지하기 위해,
#      요청 수신 즉시 "OK:PROCESSING"을 응답하고 실제 작업은 백그라운드 스레드로 분리합니다.
#
# 2. HEARTBEAT 및 카운터/시간 변수 추적 관리 정책
#    - 메인 앱은 카운터와 별개로 4바이트 정수형 시간 변수를 포함하여 "HEARTBEAT:<counter>:<time_val>" 형태로 전송합니다.
#    - 리셋(초기화) 조건: 보낸 카운터가 마지막 카운터보다 작고, 보낸 카운터가 지정된 임계값(HEARTBEAT_RESET_COUNTER_THRESHOLD)
#      이하인 경우(메인 앱 재시작 등) 최초 시간/카운터 및 서버 측 측정 시간을 새롭게 클리어하고 세션을 재시작합니다.
#    - 'GET_HEARTBEAT' 명령을 통해 5초 간격으로 해당 상태 정보를 모두 조회할 수 있습니다.
# ==============================================================================

REJECT_REASON_FREQUENT = "FREQUENT_REQUEST_THROTTLED"
REJECT_REASON_HEAVY_RUNNING = "HEAVY_TASK_ALREADY_RUNNING"

# 1. HEARTBEAT 관련 제어 상수
HEARTBEAT_INTERVAL_SEC = 10.0                 # 기본 하트비트 주기 간격
HEARTBEAT_LOG_BURST_COUNT = 5                 # 연결 복구 시점부터 연속으로 로그를 출력할 횟수
HEARTBEAT_MISSING_THRESHOLD = 3               # 유실 판단 임계 횟수 (3회 이상 미수신 시 단절로 간주)
HEARTBEAT_RESET_COUNTER_THRESHOLD = 10        # 메인앱 재시작 판정을 위한 카운터 리셋 기준 상한선 (50 이하)

# 2. 명령어별 최소 요청 허용 간격 (Cooldown / Throttling, 단위: 초)
COMMAND_COOLDOWN_MAP = {
    "GET_STATUS": 2.0,       # 상태 조회는 빈번한 폴링 부하를 막기 위해 최소 2초 간격 제한
    "GET_VERSIONS": 5.0,     # 백업 버전 목록 조회는 디스크 I/O를 고려해 최소 5초 간격 제한
    "GET_PATHS": 10.0,       # 경로 정보 조회는 고정값이므로 최소 10초 간격 제한
    "CONFIG_AND_TEST": 5.0,  # 외부 네트워크(JSON)를 호출하는 테스트는 최소 5초 간격 제한
    "APPLY_UPDATE": 60.0,    # 업데이트 적용은 파일 다운로드/압축 해제가 수반되므로 중복/동시 실행 방지를 위해 60초 제한
    "ROLLBACK": 60.0,        # 롤백 역시 파일 교체 및 재기동이 수반되므로 업데이트와 동일하게 60초 제한
    "GET_HEARTBEAT": 5.0     # 하트비트 상태 통계 조회는 5초 간격 요청 가능
}

# version.py에서 VERSION과 NAME 가져오기 (없을 경우 기본값 사용)
try:
    from version import VERSION as UPDATER_VERSION, NAME as UPDATER_NAME
except ImportError:
    UPDATER_VERSION = "1.2.0"
    UPDATER_NAME = "PrintShopUpdateService"

SERVICE_DISPLAY_NAME = f"PrintShop Updater & Watchdog Service v{UPDATER_VERSION}"
REG_KEY_PATH = f"SOFTWARE\\{UPDATER_NAME}"

APP_NAME = "PrintShopApp.exe"
MAIN_APP_CURRENT_VERSION = "1.2.0"
GIT_HUB_UPDATE_VERSIOC_CHECK_INTERVAL = 1800


class ConfigManager:
    """INI 파일과 Windows 레지스트리에 서버 설정을 동시 저장 및 로드하는 클래스"""
    def __init__(self, app_dir: str):
        self.app_dir = app_dir
        self.ini_path = os.path.join(app_dir, "config.ini")
        self.reg_key_path = REG_KEY_PATH
        self.config = configparser.ConfigParser()

    def save_config(self, repo_url: str, json_url: str):
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
            if repo_url and json_url:
                return {"repo_url": repo_url, "json_url": json_url}
        except Exception:
            pass

        if os.path.exists(self.ini_path):
            try:
                self.config.read(self.ini_path, encoding="utf-8")
                if self.config.has_section("ServerConfig"):
                    repo_url = self.config.get("ServerConfig", "repo_url", fallback="")
                    json_url = self.config.get("ServerConfig", "json_url", fallback="")
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
        self.last_heartbeat = time.time()
        self.heartbeat_timeout_limit = HEARTBEAT_TIMEOUT_SEC
        
        # 하트비트 및 명령어별 제어를 위한 상태 변수
        self.hb_missing_count = 0
        self.hb_log_remaining = 0
        self.last_hb_received_time = time.time()
        self.command_last_called_time = {}  # 쿨다운 관리를 위한 명령어별 최근 호출 타임스탬프
        
        # 💡 [HEARTBEAT 시간 변수, 서버 측정 시간 및 카운터 추적 상태 변수]
        self.hb_first_time = None           # 메인앱 전송 최초 시간 변수
        self.hb_first_server_time = None    # 최초 수신 시 서버 측 측정 시간
        self.hb_first_counter = None        # 최초 카운터
        self.hb_last_time = None            # 메인앱 전송 마지막 시간 변수
        self.hb_last_server_time = None     # 마지막 수신 시 서버 측 측정 시간
        self.hb_last_counter = None         # 마지막 카운터
        self.hb_total_count = 0             # 누적 수신 횟수

        # 상호 배타적 제어 변수 (업데이트 및 롤백 동시 실행 방지)
        self.is_heavy_task_running = False
        self.heavy_task_lock = threading.Lock()

        self.service_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        self.app_dir = os.path.abspath(os.path.join(self.service_dir, ".."))
        self.main_exe_path = os.path.join(self.app_dir, APP_NAME)

        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        self.data_dir = os.path.join(local_app_data, "PrintShopApp")
        
        self.versions_dir = os.path.join(self.data_dir, "versions")

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.versions_dir, exist_ok=True)

        self.config_mgr = ConfigManager(self.data_dir)
        self.saved_config = self.config_mgr.load_config()

        self.status_info = {
            "phase": "IDLE",
            "progress": 0,
            "message": "시스템 대기 중...",
            "version": ""
        }

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
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        self.info("IDLE", 0, "중앙 업데이터 및 Watchdog 서비스가 기동되었습니다.")
        self.verify_main_app_existence()

        threading.Thread(target=self._github_background_downloader, daemon=True).start()

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_socket.bind(("127.0.0.1", PORT))
            server_socket.settimeout(1.0)
        except Exception as e:
            self.info("ERROR", 0, f"UDP 소켓 바인드 실패: {e}")
            return

        check_app_timer = time.time()
        while self.is_running:
            current_time = time.time()
            if current_time - check_app_timer > APP_CHECK_INTERVAL_SEC:
                check_app_timer = current_time
                if not self.is_main_app_running():
                    self.info("LAUNCH", 0, f"메인 프로그램({APP_NAME})이 프로세스에 없어 자동 실행합니다.")
                    self.launch_main_app()

                if current_time - self.last_hb_received_time > HEARTBEAT_INTERVAL_SEC:
                    self.hb_missing_count += 1
                    self.last_hb_received_time = current_time 

            if self.is_main_app_running() and (current_time - self.last_heartbeat > self.heartbeat_timeout_limit):
                self.info("WATCHDOG_TIMEOUT", 0, "⚠️ 메인 앱 응답 없음! 직전 안정 버전으로 긴급 롤백을 수행합니다.")
                self.trigger_latest_rollback()
                self.last_heartbeat = current_time

            try:
                data_bytes, addr = server_socket.recvfrom(4096)
                command = data_bytes.decode('utf-8')
                
                # UPDATE 및 ROLLBACK 요청 처리 (상호 배타적 검증 및 쿨다운 체크)
                if command.startswith("APPLY_UPDATE:") or command.startswith("ROLLBACK:"):
                    cmd_key = "APPLY_UPDATE" if command.startswith("APPLY_UPDATE:") else "ROLLBACK"
                    
                    with self.heavy_task_lock:
                        if self.is_heavy_task_running:
                            self.info("UDP_REJECT", 0, f"요청 거부 ({REJECT_REASON_HEAVY_RUNNING}): {command}")
                            server_socket.sendto(f"FAIL:{REJECT_REASON_HEAVY_RUNNING}".encode('utf-8'), addr)
                            continue

                        cooldown = COMMAND_COOLDOWN_MAP.get(cmd_key, 30.0)
                        last_update_time = self.command_last_called_time.get("APPLY_UPDATE", 0)
                        last_rollback_time = self.command_last_called_time.get("ROLLBACK", 0)
                        max_last_time = max(last_update_time, last_rollback_time)

                        if current_time - max_last_time < cooldown:
                            self.info("UDP_REJECT", 0, f"요청 거부 ({REJECT_REASON_FREQUENT}): {command}")
                            server_socket.sendto(f"FAIL:{REJECT_REASON_FREQUENT}".encode('utf-8'), addr)
                            continue

                        self.command_last_called_time[cmd_key] = current_time
                        self.is_heavy_task_running = True

                    server_socket.sendto("OK:PROCESSING".encode('utf-8'), addr)
                    threading.Thread(target=self.handle_heavy_command_async, args=(command,), daemon=True).start()
                else:
                    response = self.handle_udp_command(command, current_time)
                    server_socket.sendto(response.encode('utf-8'), addr)
            except socket.timeout:
                continue
            except Exception:
                pass

        server_socket.close()

    def verify_main_app_existence(self):
        if os.path.exists(self.main_exe_path):
            self.info("PATH_CHECK", 0, f"✅ 메인 앱 경로 확인됨: {self.main_exe_path}")
            return True
        else:
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
                        latest_ver = data.get("version")
                        download_url = data.get("download_url")
                        
                        if version.parse(latest_ver) > version.parse(MAIN_APP_CURRENT_VERSION):
                            ver_folder = os.path.join(self.versions_dir, f"v{latest_ver}")
                            os.makedirs(ver_folder, exist_ok=True)
                            zip_path = os.path.join(ver_folder, f"update_v{latest_ver}.zip")

                            if not os.path.exists(zip_path):
                                self.info("DOWNLOADING", 0, f"새 버전 v{latest_ver} 다운로드 중...", latest_ver)
                                r = requests.get(download_url, stream=True, timeout=10)
                                with open(zip_path, "wb") as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        if chunk: f.write(chunk)
                                
                            if zipfile.is_zipfile(zip_path):
                                self.info("DOWNLOADED", 100, f"새 버전 v{latest_ver} 검증 완료 및 저장됨: {zip_path}", latest_ver)
                except Exception as e:
                    self.info("DOWNLOAD_ERROR", 0, f"다운로드 중 예외 발생: {e}")
            time.sleep(GIT_HUB_UPDATE_VERSIOC_CHECK_INTERVAL)

    def handle_heavy_command_async(self, command: str):
        self.info("HEAVY_CMD_START", 0, f"무거운 백그라운드 작업 시작: {command}")
        try:
            if command.startswith("APPLY_UPDATE:"):
                parts = command.split(":")
                target_ver = parts[1] if len(parts) > 1 else ""
                self_shutdown = parts[2] == "SELF" if len(parts) > 2 else False
                self.execute_update_process(target_ver, self_shutdown)
            elif command.startswith("ROLLBACK:"):
                parts = command.split(":")
                target_ver = parts[1] if len(parts) > 1 else ""
                self_shutdown = parts[2] == "SELF" if len(parts) > 2 else False
                self.execute_rollback_process(target_ver, self_shutdown)
        finally:
            with self.heavy_task_lock:
                self.is_heavy_task_running = False
            self.info("HEAVY_CMD_END", 0, f"무거운 백그라운드 작업 종료 및 락 해제 완료: {command}")

    def handle_udp_command(self, command: str, current_time: float) -> str:
        base_cmd = command.split(":")[0] if ":" in command else command

        # 일반 명령어 쿨다운(Throttling) 검증
        if base_cmd in COMMAND_COOLDOWN_MAP:
            cooldown = COMMAND_COOLDOWN_MAP[base_cmd]
            last_called = self.command_last_called_time.get(base_cmd, 0.0)
            if current_time - last_called < cooldown:
                self.info("UDP_REJECT", 0, f"요청 거부 ({REJECT_REASON_FREQUENT}): {command}")
                return f"FAIL:{REJECT_REASON_FREQUENT}"
            
            self.command_last_called_time[base_cmd] = current_time

        # 💡 [HEARTBEAT 처리 및 상수로 정의된 리셋 조건 적용]
        if command.startswith("HEARTBEAT"):
            self.last_heartbeat = current_time
            
            # 파싱 형식: HEARTBEAT:<counter>:<time_val> (예: HEARTBEAT:10:1718000000)
            try:
                parts = command.split(":")
                current_counter = int(parts[1]) if len(parts) > 1 else 0
                current_time_val = int(parts[2]) if len(parts) > 2 else int(time.time())
            except Exception:
                current_counter = 0
                current_time_val = int(time.time())

            # 서버 측 수신 측정 시간
            server_measured_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 💡 [세션 초기화(리셋) 조건 - 상수 활용]
            is_reset_condition = (
                self.hb_first_counter is None or 
                (
                    self.hb_last_counter is not None and 
                    current_counter < self.hb_last_counter and 
                    current_counter <= HEARTBEAT_RESET_COUNTER_THRESHOLD
                )
            )

            if is_reset_condition:
                self.hb_first_time = current_time_val
                self.hb_first_server_time = server_measured_time
                self.hb_first_counter = current_counter
                self.hb_last_time = current_time_val
                self.hb_last_server_time = server_measured_time
                self.hb_last_counter = current_counter
                self.hb_total_count = 1
                
                # 💡 [신규 추가] 하트비트 세션 리셋 시 모든 명령어 쿨다운 초기화
                self.command_last_called_time.clear()
                self.info("HEARTBEAT_RESET", 0, "메인 앱 재시작(세션 리셋) 감지: 모든 명령어 쿨다운 타이머가 초기화되었습니다.")
            else:
                self.hb_last_time = current_time_val
                self.hb_last_server_time = server_measured_time
                self.hb_last_counter = current_counter
                self.hb_total_count += 1

            # 하트비트 로그 버스트 제어 정책
            if self.hb_missing_count >= HEARTBEAT_MISSING_THRESHOLD:
                self.hb_log_remaining = HEARTBEAT_LOG_BURST_COUNT
            
            self.hb_missing_count = 0
            self.last_hb_received_time = current_time

            if self.hb_log_remaining > 0:
                self.info("UDP_REQUEST", 0, f"수신된 요청: {command} (서버수신시간: {server_measured_time}, 누적: {self.hb_total_count})")
                response = "OK"
                self.info("UDP_RESPONSE", 0, f"반환 응답: {response}")
                self.hb_log_remaining -= 1
                return response
            else:
                return "OK"

        # 💡 [GET_HEARTBEAT 상태 조회 명령어 처리]
        if base_cmd == "GET_HEARTBEAT":
            heartbeat_status = {
                "first_time": self.hb_first_time,
                "first_server_time": self.hb_first_server_time,
                "first_counter": self.hb_first_counter,
                "last_time": self.hb_last_time,
                "last_server_time": self.hb_last_server_time,
                "last_counter": self.hb_last_counter,
                "total_count": self.hb_total_count
            }
            response = f"OK:{json.dumps(heartbeat_status)}"
            self.info("UDP_RESPONSE", 0, f"하트비트 상태 반환: {response}")
            return response

        # 일반 명령어 로그 출력 및 처리
        self.info("UDP_REQUEST", 0, f"수신된 요청: {command}")
        
        response = "FAIL:UNKNOWN_CMD"

        if command == "GET_STATUS":
            response = f"OK:{json.dumps(self.status_info)}"
        elif command == "GET_VERSIONS":
            response = f"OK:{json.dumps(self.get_available_backup_versions())}"
        elif command == "GET_PATHS":
            paths_info = {
                "main_exe_path": self.main_exe_path,
                "updater_exe_path": sys.executable if getattr(sys, 'frozen', False) else __file__,
                "updater_service_dir": self.service_dir
            }
            response = f"OK:{json.dumps(paths_info)}"
        elif command.startswith("CONFIG_AND_TEST:"):
            try:
                cfg = json.loads(command.split("CONFIG_AND_TEST:", 1)[1])
                repo_url, json_url = cfg.get("repo_url", ""), cfg.get("json_url", "")
                if self.config_mgr.save_config(repo_url, json_url):
                    r = requests.get(json_url, timeout=5)
                    if r.status_code == 200 and "version" in r.json():
                        response = "OK:TEST_SUCCESS"
                    else:
                        response = "FAIL:TEST_FAILED"
                else:
                    response = "FAIL:TEST_FAILED"
            except Exception:
                response = "FAIL:EXCEPTION"

        self.info("UDP_RESPONSE", 0, f"반환 응답: {response}")
        return response

    def execute_update_process(self, target_version: str, self_shutdown: bool) -> bool:
        success = False
        try:
            self.info("UPDATE_START", 20, f"버전 v{target_version} 업데이트 적용 프로세스를 시작합니다.")
            
            zip_path = os.path.join(self.versions_dir, f"v{target_version}", f"update_v{target_version}.zip")
            if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
                self.info("UPDATE_FAIL", 0, f"업데이트 패키지를 찾을 수 없습니다: {zip_path}")
                return False

            if self.is_main_app_running() and not self_shutdown:
                self.info("UPDATE_KILL", 40, f"실행 중인 메인 앱({APP_NAME})을 종료합니다.")
                subprocess.run(f"taskkill /f /im {APP_NAME}", shell=True, capture_output=True)
                time.sleep(1)

            self.backup_current_version(MAIN_APP_CURRENT_VERSION)
            
            extract_dir = os.path.join(self.versions_dir, f"v{target_version}", "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)

            self.info("UPDATE_COPY", 70, "파일 교체 복사 중...")
            subprocess.run(f'xcopy /s /y "{extract_dir}\\*" "{self.app_dir}\\"', shell=True, capture_output=True)

            self.info("UPDATE_RELAUNCH", 90, "🔄 업데이트 패키지 적용 완료. 메인 앱을 재기동합니다.")            
            self.launch_main_app()
            self.info("UPDATE_SUCCESS", 100, f"버전 v{target_version} 업데이트 완료.")
            success = True
            return True
        except Exception as e:
            self.info("UPDATE_ERROR", 0, f"업데이트 중 예외 발생: {e}")
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
            self.info("ROLLBACK_START", 20, f"버전 v{target_version}으로 롤백을 시작합니다.")
            base_name = APP_NAME.replace(".exe", "").lower()
            target_zip = os.path.join(self.backup_dir, f"{base_name}_v{target_version}.zip")
            if not os.path.exists(target_zip):
                self.info("ROLLBACK_FAIL", 0, f"롤백 대상 백업 파일을 찾을 수 없습니다: {target_zip}")
                return False
            
            if self.is_main_app_running() and not self_shutdown:
                subprocess.run(f"taskkill /f /im {APP_NAME}", shell=True, capture_output=True)
                time.sleep(1)

            temp_dir = os.environ.get("TEMP", "C:\\Temp")
            extract_dir = os.path.join(temp_dir, "extracted_rollback")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(target_zip, 'r') as zf:
                zf.extractall(extract_dir)

            subprocess.run(f'xcopy /s /y "{extract_dir}\\*" "{self.app_dir}\\"', shell=True, capture_output=True)

            self.info("ROLLBACK_RELAUNCH", 90, "🔄 롤백 패키지 적용 완료. 메인 앱을 재기동합니다.")            
            self.launch_main_app()
            self.info("ROLLBACK_SUCCESS", 100, f"버전 v{target_version} 롤백 완료.")
            success = True
            return True
        except Exception as e:
            self.info("ROLLBACK_ERROR", 0, f"롤백 중 예외 발생: {e}")
            return False
        finally:
            if not success:
                self.info("ROLLBACK_RECOVERY", 100, "🚨 롤백 실패. 메인 앱이 꺼진 상태로 방치되지 않도록 강제 기동을 시도합니다.")
                self.launch_main_app()

    def trigger_latest_rollback(self):
        versions = self.get_available_backup_versions()
        if versions:
            self.execute_rollback_process(versions[0], False)

    def backup_current_version(self, ver):
        base_name = APP_NAME.replace(".exe", "").lower()
        backup_zip = os.path.join(self.backup_dir, f"{base_name}_v{ver}.zip")
        if not os.path.exists(backup_zip) and os.path.exists(self.main_exe_path):
            with zipfile.ZipFile(backup_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(self.main_exe_path, arcname=APP_NAME)

    def get_available_backup_versions(self):
        versions = []
        base_name = APP_NAME.replace(".exe", "").lower()
        prefix = f"{base_name}_v"
        
        if os.path.exists(self.backup_dir):
            for f in os.listdir(self.backup_dir):
                if f.startswith(prefix) and f.endswith(".zip"):
                    ver_str = f.replace(prefix, "").replace(".zip", "")
                    versions.append(ver_str)
        versions.sort(key=lambda s: version.parse(s), reverse=True)
        return versions

    def is_main_app_running(self):
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and proc.info['name'].lower() == APP_NAME.lower():
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

        # 하트비트 로깅 초기화 정책 (재시작 직후 버스트 로그 허용)
        self.hb_missing_count = HEARTBEAT_MISSING_THRESHOLD
        self.hb_log_remaining = HEARTBEAT_LOG_BURST_COUNT
        self.last_hb_received_time = time.time()

        try:
            subprocess.run(f"taskkill /f /im {APP_NAME}", shell=True, capture_output=True)
            time.sleep(0.5)

            active_session_id = win32ts.WTSGetActiveConsoleSessionId()
            if active_session_id == 0xFFFFFFFF:
                self.info("LAUNCH_FAIL", 0, "❌ 활성화된 사용자 세션을 찾을 수 없습니다.")
                return

            h_user_token = None
            for proc in psutil.process_iter(['name', 'pid', 'username']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == 'explorer.exe':
                        pid = proc.info['pid']
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
                h_user_token, 0xF01FF, None,
                win32security.SecurityIdentification,
                win32security.TokenPrimary,
                ctypes.byref(h_duplicated_token)
            ):
                self.info("LAUNCH_FAIL", 0, "❌ 토큰 복제 실패")
                ctypes.windll.kernel32.CloseHandle(h_user_token)
                return

            lp_environment = ctypes.c_void_p()
            userenv = ctypes.windll.userenv
            userenv.CreateEnvironmentBlock(ctypes.byref(lp_environment), h_duplicated_token, False)

            class STARTUPINFOW(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                    ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                    ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
                    ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE),
                ]

            class PROCESS_INFORMATION(ctypes.Structure):
                _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE), ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

            si = STARTUPINFOW()
            si.cb = ctypes.sizeof(STARTUPINFOW)
            si.lpDesktop = "winsta0\\default"
            pi = PROCESS_INFORMATION()

            success = advapi32.CreateProcessAsUserW(
                h_duplicated_token, None, ctypes.c_wchar_p(self.main_exe_path),
                None, None, False, 0x00000400, lp_environment, None,
                ctypes.byref(si), ctypes.byref(pi)
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

def check_single_instance(mutex_name="Global\\PrintShopUpdateService_Mutex"):
    global _service_mutex
    kernel32 = ctypes.windll.kernel32
    _service_mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:
        return True
    return False

def logd(message: str):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] {message}")
