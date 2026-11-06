"""Hotspot client isolation and Windows Firewall management.

Implements the [Check -> Configure -> Verify] workflow:
Step 1. Check
  - [Check 1] Administrator privilege
  - [Check 2] Hotspot adapter and target subnet (192.168.137.0/24) active
  - [Check 3] Existing duplicate firewall rules check
Step 2. Configure
  - [Config 1] Add web service port inbound allow rule (Hotspot-Web-Allow)
  - [Config 2] Apply internal file sharing (SMB) block rule (FPS-SMB-In-TCP / Hotspot-SMB-Block)
Step 3. Verify
  - [Verify 1] Verify Hotspot-Web-Allow rule exists and is enabled
  - [Verify 2] Verify SMB block rule has RemoteAddress matching the hotspot range and Action is Block
"""

from __future__ import annotations

import ctypes
import ipaddress
import logging
import psutil
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from Common.logger_service import get_feature_logger

logger = get_feature_logger("firewall", "SECURITY")

WEB_ALLOW_RULE_NAME = "Hotspot-Web-Allow"
SMB_BLOCK_RULE_NAME = "Hotspot-SMB-Block"
SYSTEM_SMB_RULE_NAME = "FPS-SMB-In-TCP"


def is_admin_user() -> bool:
    """Check if the current process has Windows administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_hotspot_subnet_active(expected_network: str = "192.168.137.0/24", expected_gateway: str = "192.168.137.1") -> Tuple[bool, str]:
    """Check if the hotspot adapter is up and assigned the expected gateway IP."""
    target_net = ipaddress.ip_network(expected_network)
    gateway_found = False
    matching_adapter = ""
    for name, addrs in psutil.net_if_addrs().items():
        stats = psutil.net_if_stats().get(name)
        is_up = bool(stats and stats.isup)
        for a in addrs:
            if a.family == socket.AF_INET:
                if a.address == expected_gateway and is_up:
                    gateway_found = True
                    matching_adapter = name
                    break
        if gateway_found:
            break

    if gateway_found:
        return True, f"Hotspot active on adapter '{matching_adapter}' with IP {expected_gateway}"
    return False, f"Hotspot gateway {expected_gateway} not active on any UP adapter in {expected_network}"


def run_powershell(command: str, timeout: int = 10) -> Tuple[int, str, str]:
    """Execute a PowerShell command safely and return (returncode, stdout, stderr)."""
    full_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command]
    try:
        res = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except (subprocess.SubprocessError, OSError) as exc:
        return -1, "", str(exc)


def query_firewall_rule(rule_name: str) -> Optional[Dict[str, Any]]:
    """Query a Windows firewall rule by Name or DisplayName."""
    ps_cmd = (
        f"$r = Get-NetFirewallRule -Name '{rule_name}' -ErrorAction SilentlyContinue; "
        f"if (-not $r) {{ $r = Get-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue }}; "
        f"if ($r) {{ "
        f"  $af = $r | Get-NetFirewallAddressFilter; "
        f"  $pf = $r | Get-NetFirewallPortFilter; "
        f"  Write-Output ($r.Name + '|' + $r.DisplayName + '|' + $r.Enabled + '|' + $r.Direction + '|' + $r.Action + '|' + ($af.RemoteAddress -join ',') + '|' + ($pf.LocalPort -join ',')); "
        f"}}"
    )
    code, out, _ = run_powershell(ps_cmd)
    if code == 0 and out:
        parts = out.split("|")
        if len(parts) >= 7:
            return {
                "name": parts[0],
                "display_name": parts[1],
                "enabled": parts[2].lower() in {"true", "1"},
                "direction": parts[3],
                "action": parts[4],
                "remote_address": parts[5],
                "local_port": parts[6],
            }
    return None


def delete_firewall_rule(rule_name: str) -> Tuple[bool, str]:
    """Delete an existing firewall rule if present."""
    ps_cmd = (
        f"$r = Get-NetFirewallRule -Name '{rule_name}' -ErrorAction SilentlyContinue; "
        f"if (-not $r) {{ $r = Get-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue }}; "
        f"if ($r) {{ Remove-NetFirewallRule -InputObject $r -ErrorAction Stop; Write-Output 'DELETED' }} else {{ Write-Output 'NOT_FOUND' }}"
    )
    code, out, err = run_powershell(ps_cmd)
    if code == 0:
        return True, out
    return False, err or out


def is_firewall_configured_and_valid(web_port: int = 5000, hotspot_network: str = "192.168.137.0/24") -> bool:
    """Check if firewall rules are already configured and valid without making modifications."""
    rule_web_chk = query_firewall_rule(WEB_ALLOW_RULE_NAME)
    rule_fps_chk = query_firewall_rule(SYSTEM_SMB_RULE_NAME)
    rule_smb_chk = query_firewall_rule(SMB_BLOCK_RULE_NAME)
    web_ok = bool(rule_web_chk and rule_web_chk.get("enabled") and rule_web_chk.get("action") == "Allow")
    smb_ok = bool(
        (rule_fps_chk and rule_fps_chk.get("action") == "Block" and hotspot_network in rule_fps_chk.get("remote_address", ""))
        or (rule_smb_chk and rule_smb_chk.get("action") == "Block" and rule_smb_chk.get("enabled"))
    )
    return web_ok and smb_ok


def apply_hotspot_firewall_rules(
    web_port: int = 5000,
    hotspot_network: str = "192.168.137.0/24",
    hotspot_gateway: str = "192.168.137.1",
    enforce_hotspot_active: bool = False,
    skip_if_already_valid: bool = False,
) -> Dict[str, Any]:
    """Execute the [Check -> Configure -> Verify] scenario for Hotspot client isolation.

    When skip_if_already_valid is True, if existing rules already satisfy the requirements,
    returns success immediately to eliminate redundant configuration time.
    """
    if skip_if_already_valid and is_firewall_configured_and_valid(web_port, hotspot_network):
        return {
            "success": True,
            "step1_check": {
                "check_existing_valid": {"title": "기존 방화벽 규칙 검사", "passed": True, "detail": "기존 규칙이 이미 유효합니다."}
            },
            "step2_configure": {},
            "step3_verify": {},
            "summary": "[PASS] 기존 방화벽 규칙이 이미 유효하게 적용되어 있어 추가 설정을 건너뜁니다.",
        }

    result: Dict[str, Any] = {
        "success": False,
        "step1_check": {},
        "step2_configure": {},
        "step3_verify": {},
        "summary": "",
    }

    # =========================================================================
    # Step 1. 체크 (Check) 단계: 사전 상태 확인
    # =========================================================================
    # [Check 1] 관리자 권한 확인
    is_admin = is_admin_user()
    result["step1_check"]["check1_admin"] = {
        "title": "관리자 권한 확인",
        "passed": is_admin,
        "detail": "관리자 권한 확인됨" if is_admin else "관리자 권한이 없습니다 (UAC 관리자 승인 필요)",
    }
    if not is_admin:
        result["summary"] = "[FAIL] Check 1: 관리자 권한이 없어 방화벽 설정을 중단합니다."
        return result

    # [Check 2] 핫스팟 어댑터 및 IP 대역 확인
    hotspot_active, hotspot_msg = is_hotspot_subnet_active(hotspot_network, hotspot_gateway)
    # When enforce_hotspot_active is False, we allow configuration even if hotspot hasn't fully spun up yet
    # but still report the check accurately.
    passed_check2 = hotspot_active or (not enforce_hotspot_active)
    result["step1_check"]["check2_hotspot_active"] = {
        "title": "핫스팟 어댑터 및 IP 대역 확인",
        "passed": passed_check2,
        "detail": hotspot_msg,
    }
    if enforce_hotspot_active and not hotspot_active:
        result["summary"] = f"[FAIL] Check 2: 핫스팟이 활성화되지 않았습니다 ({hotspot_msg}). 핫스팟을 먼저 켜주세요."
        return result

    # [Check 3] 기존 방화벽 규칙 중복 여부 확인
    existing_web = query_firewall_rule(WEB_ALLOW_RULE_NAME)
    web_existed = existing_web is not None
    if web_existed:
        delete_firewall_rule(WEB_ALLOW_RULE_NAME)
    result["step1_check"]["check3_duplicate_rules"] = {
        "title": "기존 방화벽 규칙 중복 여부 확인",
        "passed": True,
        "detail": f"기존 규칙 '{WEB_ALLOW_RULE_NAME}' 발견되어 갱신 준비 완료" if web_existed else "중복 규칙 없음",
    }

    # =========================================================================
    # Step 2. 설정 (Configure) 단계: 방화벽 규칙 적용
    # =========================================================================
    # [Config 1] 웹 서비스 포트 허용 규칙 추가 (Hotspot-Web-Allow)
    add_web_cmd = (
        f"New-NetFirewallRule -Name '{WEB_ALLOW_RULE_NAME}' -DisplayName '{WEB_ALLOW_RULE_NAME}' "
        f"-Description 'Allow inbound web requests from hotspot clients' "
        f"-Direction Inbound -Action Allow -Protocol TCP -LocalPort {web_port} "
        f"-RemoteAddress '{hotspot_network}' -Enabled True -ErrorAction Stop"
    )
    code1, out1, err1 = run_powershell(add_web_cmd)
    cfg1_passed = code1 == 0
    result["step2_configure"]["config1_web_allow"] = {
        "title": "웹 서비스 포트 허용 규칙 추가",
        "passed": cfg1_passed,
        "detail": f"포트 {web_port} (대역 {hotspot_network}) 허용 등록 성공" if cfg1_passed else f"오류: {err1 or out1}",
    }

    # [Config 2] 내부 파일 공유(SMB) 차단 규칙 적용
    # 먼저 시스템 표준 FPS-SMB-In-TCP 규칙의 RemoteAddress 및 Action 수정을 시도하고,
    # 전용 차단 규칙 Hotspot-SMB-Block도 함께 적용하여 강력한 클라이언트 격리를 수행합니다.
    cfg2_details = []
    cfg2_success = True

    # 1) 시스템 FPS-SMB-In-TCP 설정 변경
    modify_smb_cmd = (
        f"$r = Get-NetFirewallRule -Name '{SYSTEM_SMB_RULE_NAME}' -ErrorAction SilentlyContinue; "
        f"if ($r) {{ "
        f"  Set-NetFirewallRule -InputObject $r -Action Block -RemoteAddress '{hotspot_network}' -Enabled True -ErrorAction Stop; "
        f"  Write-Output 'UPDATED_SYSTEM_SMB'; "
        f"}} else {{ Write-Output 'SYSTEM_SMB_NOT_FOUND'; }}"
    )
    code_smb1, out_smb1, err_smb1 = run_powershell(modify_smb_cmd)
    if code_smb1 == 0 and "UPDATED_SYSTEM_SMB" in out_smb1:
        cfg2_details.append(f"{SYSTEM_SMB_RULE_NAME} Action=Block, RemoteAddress={hotspot_network} 적용 완료")
    else:
        # If system rule update failed, note it
        cfg2_details.append(f"{SYSTEM_SMB_RULE_NAME} 수정: {err_smb1 or out_smb1}")

    # 2) 독립 차단 규칙 Hotspot-SMB-Block 보증 적용
    delete_firewall_rule(SMB_BLOCK_RULE_NAME)
    add_smb_block_cmd = (
        f"New-NetFirewallRule -Name '{SMB_BLOCK_RULE_NAME}' -DisplayName '{SMB_BLOCK_RULE_NAME}' "
        f"-Description 'Block SMB/file sharing traffic from hotspot clients' "
        f"-Direction Inbound -Action Block -Protocol TCP -LocalPort 445,139 -RemoteAddress '{hotspot_network}' -Enabled True -ErrorAction Stop"
    )
    code_smb2, out_smb2, err_smb2 = run_powershell(add_smb_block_cmd)
    if code_smb2 == 0:
        cfg2_details.append(f"{SMB_BLOCK_RULE_NAME} 차단 규칙 생성 성공")
    else:
        cfg2_details.append(f"{SMB_BLOCK_RULE_NAME} 생성 실패: {err_smb2 or out_smb2}")
        cfg2_success = False

    result["step2_configure"]["config2_smb_block"] = {
        "title": "내부 파일 공유(SMB) 차단 규칙 적용",
        "passed": cfg2_success,
        "detail": " | ".join(cfg2_details),
    }

    # =========================================================================
    # Step 3. 검증 (Verify) 단계: 결과 확인 및 테스트
    # =========================================================================
    # [Verify 1] 허용 규칙 등록 여부 검증
    rule_web = query_firewall_rule(WEB_ALLOW_RULE_NAME)
    v1_passed = bool(rule_web and rule_web.get("enabled") and rule_web.get("action") == "Allow")
    result["step3_verify"]["verify1_web_allow"] = {
        "title": "허용 규칙(Hotspot-Web-Allow) 등록 여부 검증",
        "passed": v1_passed,
        "detail": (
            f"규칙 활성화 확인: Action={rule_web.get('action')}, Port={rule_web.get('local_port')}, Remote={rule_web.get('remote_address')}"
            if v1_passed else f"규칙 없음 또는 비활성 ({rule_web})"
        ),
    }

    # [Verify 2] 차단 규칙 적용 여부 검증
    rule_fps_smb = query_firewall_rule(SYSTEM_SMB_RULE_NAME)
    rule_custom_smb = query_firewall_rule(SMB_BLOCK_RULE_NAME)

    fps_blocked = bool(
        rule_fps_smb
        and rule_fps_smb.get("action") == "Block"
        and (hotspot_network in rule_fps_smb.get("remote_address", ""))
    )
    custom_blocked = bool(
        rule_custom_smb
        and rule_custom_smb.get("action") == "Block"
        and rule_custom_smb.get("enabled")
    )
    v2_passed = fps_blocked or custom_blocked
    result["step3_verify"]["verify2_smb_block"] = {
        "title": "차단 규칙(FPS-SMB-In-TCP / Hotspot-SMB-Block) 적용 여부 검증",
        "passed": v2_passed,
        "detail": (
            f"FPS-SMB: Action={rule_fps_smb.get('action') if rule_fps_smb else 'None'}, Remote={rule_fps_smb.get('remote_address') if rule_fps_smb else 'None'} | "
            f"Hotspot-SMB-Block: {'Active' if custom_blocked else 'Inactive'}"
        ),
    }

    overall_success = (
        is_admin
        and cfg1_passed
        and cfg2_success
        and v1_passed
        and v2_passed
    )
    result["success"] = overall_success
    result["summary"] = (
        "[PASS] 핫스팟 방화벽 3단계 (체크 ➔ 설정 ➔ 검증) 모두 성공적으로 적용되었습니다."
        if overall_success else
        "[FAIL] 핫스팟 방화벽 설정 또는 검증 단계에서 실패 항목이 존재합니다."
    )
    return result
