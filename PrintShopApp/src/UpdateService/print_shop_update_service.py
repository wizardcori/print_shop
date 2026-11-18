# print_shop_update_service.py
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

from Protocol.update_service_protocol import (
    DEFAULT_PORT, HEARTBEAT_TIMEOUT_SEC,
    HEARTBEAT_INTERVAL_SEC, HEARTBEAT_LOG_BURST_COUNT, HEARTBEAT_MISSING_THRESHOLD,
    HEARTBEAT_RESET_COUNTER_THRESHOLD, COMMAND_COOLDOWN_MAP,
    UpdateServicePacket, UpdateServiceToUpdateClientPacketBuilder,
    parse_client_request, parse_bool_payload, ShutdownMode, ResponseCode, Cmd
)

SERVICE_NAME = "PrintShopUpdateService"
PORT = DEFAULT_PORT

try:
    from version import VERSION as UPDATER_VERSION, NAME as UPDATER_NAME
except ImportError:
    UPDATER_VERSION = "1.2.0"
    UPDATER_NAME = "PrintShopUpdateService"

SERVICE_DISPLAY_NAME = f"PrintShop Updater & Watchdog Service v{UPDATER_VERSION}"
REG_KEY_PATH = f"SOFTWARE\\{UPDATER_NAME}"

APP_NAME = "PrintShopApp.exe"
MAIN_APP_CURRENT_VERSION = "1.2.0"

APP_CHECK_INTERVAL_SEC = 5
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
        
        self.hb_missing_count = 0
        self.hb_log_remaining = 0
        self.last_hb_received_time = time.time()
        self.command_last_called_time = {}
        
        self.hb_first_time = None
        self.hb_first_server_time = None
        self.hb_first_counter = None
        self.hb_last_time = None
        self.hb_last_server_time = None
        self.hb_last_counter = None
        self.hb_total_count = 0

        self.is_heavy_task_running = False
        self.heavy_task_lock = threading.Lock()

        self.service_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        self.app_dir = os.path.abspath(os.path.join(self.service_dir, ".."))
        self.main_exe_path = os.path.join(self.app_dir, APP_NAME)

        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        self.data_dir = os.path.join(local_app_data, "PrintShopApp")
        self.versions_dir = os.path.join(self.data_dir, "versions")
        self.backup_dir = os.path.join(self.versions_dir, "backups")

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.versions_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self.config_mgr = ConfigManager(self.data_dir)
        self.saved_config = self.config_mgr.load_config()

        self.status_info = {
            "phase": "IDLE",
            "progress": 0,
            "message": "시스템 대기 중...",
            "version": ""
        }
        
        # 메인앱 자동 재실행(launch_main_app) 활성화 여부 기본값 True
        self.launch_main_app_enabled = True
        
        # 패킷 빌더 초기화 (UpdateService -> UpdateClient)
        self.packet_builder = UpdateServiceToUpdateClientPacketBuilder()

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
                    if self.launch_main_app_enabled:
                        self.info("LAUNCH", 0, f"메인 프로그램({APP_NAME})이 프로세스에 없어 자동 실행합니다.")
                        self.launch_main_app()
                    else:
                        self.info("LAUNCH_SKIPPED", 0, f"메인 프로그램({APP_NAME})이 비활성화 설정으로 인해 자동 실행되지 않습니다.")

                if current_time - self.last_hb_received_time > HEARTBEAT_INTERVAL_SEC:
                    self.hb_missing_count += 1
                    self.last_hb_received_time = current_time 

            if self.is_main_app_running() and (current_time - self.last_heartbeat > self.heartbeat_timeout_limit):
                self.info("WATCHDOG_TIMEOUT", 0, "⚠️ 메인 앱 응답 없음! 직전 안정 버전으로 긴급 롤백을 수행합니다.")
                self.trigger_latest_rollback()
                self.last_heartbeat = current_time

            try:
                data_bytes, addr = server_socket.recvfrom(4096)
                
                # 프로토콜 파싱 적용
                is_valid, pkt, err_code = parse_client_request(data_bytes)
                if not is_valid:
                    if pkt is not None:
                        fail_pkt = self.packet_builder.res_fail(err_code)
                        server_socket.sendto(fail_pkt.encode(), addr)
                    continue

                cmd_val = pkt.cmd
                base_cmd_val = pkt.base_cmd
                payload = pkt.payload

                # APPLY_UPDATE 또는 ROLLBACK 중인 경우 무거운 작업 검증
                if base_cmd_val in (Cmd.APPLY_UPDATE, Cmd.ROLLBACK):
                    cmd_key = "APPLY_UPDATE" if base_cmd_val == Cmd.APPLY_UPDATE else "ROLLBACK"
                    
                    with self.heavy_task_lock:
                        if self.is_heavy_task_running:
                            self.info("UDP_REJECT", 0, f"요청 거부 ({ResponseCode.to_str(ResponseCode.HEAVY_TASK_ALREADY_RUNNING)}): Cmd={pkt.cmd_full_name}")
                            fail_pkt = self.packet_builder.res_fail(ResponseCode.HEAVY_TASK_ALREADY_RUNNING)
                            server_socket.sendto(fail_pkt.encode(), addr)
                            continue

                        cooldown = COMMAND_COOLDOWN_MAP.get(cmd_val, 30.0)
                        last_update_time = self.command_last_called_time.get(Cmd.APPLY_UPDATE, 0)
                        last_rollback_time = self.command_last_called_time.get(Cmd.ROLLBACK, 0)
                        max_last_time = max(last_update_time, last_rollback_time)

                        if current_time - max_last_time < cooldown:
                            self.info("UDP_REJECT", 0, f"요청 거부 ({ResponseCode.to_str(ResponseCode.FREQUENT_REQUEST_THROTTLED)}): Cmd={pkt.cmd_full_name}")
                            fail_pkt = self.packet_builder.res_fail(ResponseCode.FREQUENT_REQUEST_THROTTLED)
                            server_socket.sendto(fail_pkt.encode(), addr)
                            continue

                        self.command_last_called_time[cmd_val] = current_time
                        self.is_heavy_task_running = True

                    processing_pkt = self.packet_builder.res_ok(ResponseCode.PROCESSING, req_cmd=cmd_val)
                    server_socket.sendto(processing_pkt.encode(), addr)
                    threading.Thread(target=self.handle_heavy_command_async, args=(base_cmd_val, payload), daemon=True).start()
                else:
                    response_pkt = self.handle_udp_command(pkt, current_time)
                    server_socket.sendto(response_pkt.encode(), addr)
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

    def handle_heavy_command_async(self, base_cmd_val: int, payload: str):
        self.info("HEAVY_CMD_START", 0, f"무거운 백그라운드 작업 시작: Cmd={base_cmd_val}")
        try:
            if base_cmd_val == Cmd.APPLY_UPDATE:
                parts = payload.split(":") if payload else []
                target_ver = parts[0] if len(parts) > 0 and parts[0] in [v.replace("v","") for v in self.get_available_backup_versions() or [""]] else (parts[0] if len(parts) > 0 and "." in parts[0] else "")
                self_shutdown = True
                if len(parts) > 1 and parts[1] == ShutdownMode.SERVICE:
                    self_shutdown = False
                elif len(parts) == 1 and parts[0] == ShutdownMode.SERVICE:
                    self_shutdown = False
                    target_ver = ""
                self.execute_update_process(target_ver, self_shutdown)
            elif base_cmd_val == Cmd.ROLLBACK:
                parts = payload.split(":") if payload else []
                target_ver = parts[0] if len(parts) > 0 else ""
                self_shutdown = True
                if len(parts) > 1 and parts[1] == ShutdownMode.SERVICE:
                    self_shutdown = False
                self.execute_rollback_process(target_ver, self_shutdown)
        finally:
            with self.heavy_task_lock:
                self.is_heavy_task_running = False
            self.info("HEAVY_CMD_END", 0, f"무거운 백그라운드 작업 종료 및 락 해제 완료: Cmd={base_cmd_val}")

    def handle_udp_command(self, pkt, current_time: float) -> UpdateServicePacket:
        cmd_val = pkt.cmd
        base_cmd_val = pkt.base_cmd
        payload = pkt.payload

        if base_cmd_val in COMMAND_COOLDOWN_MAP:
            cooldown = COMMAND_COOLDOWN_MAP[base_cmd_val]
            last_called = self.command_last_called_time.get(cmd_val, 0.0)
            if current_time - last_called < cooldown:
                self.info("UDP_REJECT", 0, f"요청 거부 ({ResponseCode.to_str(ResponseCode.FREQUENT_REQUEST_THROTTLED)}): {pkt.cmd_full_name}")
                return self.packet_builder.res_fail(ResponseCode.FREQUENT_REQUEST_THROTTLED)
            
            self.command_last_called_time[cmd_val] = current_time

        if base_cmd_val == Cmd.HEARTBEAT:
            self.last_heartbeat = current_time
            try:
                parts = payload.split(":") if payload else []
                current_counter = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
                current_time_val = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else int(time.time())
            except Exception:
                current_counter = 0
                current_time_val = int(time.time())

            server_measured_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                
                self.command_last_called_time.clear()
                self.info("HEARTBEAT_RESET", 0, "메인 앱 재시작(세션 리셋) 감지: 모든 명령어 쿨다운 타이머가 초기화되었습니다.")
            else:
                self.hb_last_time = current_time_val
                self.hb_last_server_time = server_measured_time
                self.hb_last_counter = current_counter
                self.hb_total_count += 1

            if self.hb_missing_count >= HEARTBEAT_MISSING_THRESHOLD:
                self.hb_log_remaining = HEARTBEAT_LOG_BURST_COUNT
            
            self.hb_missing_count = 0
            self.last_hb_received_time = current_time

            if self.hb_log_remaining > 0:
                self.info("UDP_REQUEST", 0, f"수신된 요청: {pkt.cmd_full_name} (서버수신시간: {server_measured_time}, 누적: {self.hb_total_count})")
                res_pkt = self.packet_builder.res_ok("", req_cmd=cmd_val)
                self.info("UDP_RESPONSE", 0, f"반환 응답: {res_pkt.cmd_full_name}")
                self.hb_log_remaining -= 1
                return res_pkt
            else:
                return self.packet_builder.res_ok("", req_cmd=cmd_val)

        if base_cmd_val == Cmd.GET_HEARTBEAT:
            heartbeat_status = {
                "first_time": self.hb_first_time,
                "first_server_time": self.hb_first_server_time,
                "first_counter": self.hb_first_counter,
                "last_time": self.hb_last_time,
                "last_server_time": self.hb_last_server_time,
                "last_counter": self.hb_last_counter,
                "total_count": self.hb_total_count
            }
            res_pkt = self.packet_builder.res_ok(heartbeat_status, req_cmd=cmd_val)
            self.info("UDP_RESPONSE", 0, f"하트비트 상태 반환: {res_pkt.cmd_full_name}")
            return res_pkt

        self.info("UDP_REQUEST", 0, f"수신된 요청: {pkt.cmd_full_name}")

        if base_cmd_val == Cmd.GET_STATUS:
            res_pkt = self.packet_builder.res_ok(self.status_info, req_cmd=cmd_val)
        elif base_cmd_val == Cmd.GET_VERSIONS:
            res_pkt = self.packet_builder.res_ok(self.get_available_backup_versions(), req_cmd=cmd_val)
        elif base_cmd_val == Cmd.GET_PATHS:
            paths_info = {
                "main_exe_path": self.main_exe_path,
                "updater_exe_path": sys.executable if getattr(sys, 'frozen', False) else __file__,
                "updater_service_dir": self.service_dir
            }
            res_pkt = self.packet_builder.res_ok(paths_info, req_cmd=cmd_val)
        elif base_cmd_val == Cmd.CONFIG_AND_TEST:
            try:
                cfg = json.loads(payload) if payload else {}
                repo_url, json_url = cfg.get("repo_url", ""), cfg.get("json_url", "")
                if self.config_mgr.save_config(repo_url, json_url):
                    r = requests.get(json_url, timeout=5)
                    if r.status_code == 200 and "version" in r.json():
                        res_pkt = self.packet_builder.res_ok(ResponseCode.TEST_SUCCESS, req_cmd=cmd_val)
                    else:
                        res_pkt = self.packet_builder.res_fail(ResponseCode.TEST_FAILED)
                else:
                    res_pkt = self.packet_builder.res_fail(ResponseCode.TEST_FAILED)
            except Exception:
                res_pkt = self.packet_builder.res_fail(ResponseCode.EXCEPTION)
        elif base_cmd_val == Cmd.SET_RESTART_FUNCTION:
            try:
                enabled = parse_bool_payload(payload)
                self.launch_main_app_enabled = enabled
                res_pkt = self.packet_builder.res_ok("1" if enabled else "0", req_cmd=cmd_val)
                self.info("SET_RESTART_FUNCTION", 0, f"메인 앱 자동 재실행 설정 변경: {enabled}")
            except Exception:
                res_pkt = self.packet_builder.res_fail(ResponseCode.EXCEPTION)
        elif base_cmd_val == Cmd.GET_RESTART_FUNCTION:
            res_pkt = self.packet_builder.res_ok("1" if self.launch_main_app_enabled else "0", req_cmd=cmd_val)
        else:
            res_pkt = self.packet_builder.res_fail(ResponseCode.UNKNOWN_CMD)

        self.info("UDP_RESPONSE", 0, f"반환 응답: {res_pkt.cmd_full_name}")
        return res_pkt

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