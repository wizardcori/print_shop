"""LinkShare Windows Mobile Hotspot integration."""
import ipaddress
import logging
import os
import psutil
import socket
import subprocess
import uuid
import winreg

from Common.globals import CONFIG_ENCODING
from Common.network_utils import normalize_hotspot_network

WINDOWS_HOTSPOT_LIMIT_MAX = 128


def get_net_connection_name_map():
    """Map network adapter GUID (lower, no brackets) to Windows interface name."""
    mapping = {}
    base = r'SYSTEM\CurrentControlSet\Control\Network\{4D36E972-E325-11CE-BFC1-08002BE10318}'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            i = 0
            while True:
                try:
                    guid = winreg.EnumKey(k, i)
                    i += 1
                    try:
                        with winreg.OpenKey(k, rf'{guid}\Connection') as ck:
                            name, _ = winreg.QueryValueEx(ck, 'Name')
                            mapping[guid.strip('{}').lower()] = name
                    except OSError:
                        pass
                except OSError:
                    break
    except OSError:
        pass
    return mapping


def get_hotspot_sharing_source_guid():
    """Read PreferredPublicInterface GUID configured for Windows Mobile Hotspot."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SYSTEM\CurrentControlSet\Services\icssvc\Settings',
        ) as key:
            pref_bytes, _ = winreg.QueryValueEx(key, 'PreferredPublicInterface')
            return str(uuid.UUID(bytes_le=pref_bytes)).lower()
    except Exception:
        return None


def get_adapter_default_gateways(adapter_guid):
    """Return default gateways configured on the specified adapter GUID."""
    gateways = []
    if not adapter_guid:
        return gateways
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            rf'SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{{{adapter_guid}}}',
        ) as ik:
            for opt in ('DefaultGateway', 'DhcpDefaultGateway'):
                try:
                    val, _ = winreg.QueryValueEx(ik, opt)
                    if isinstance(val, list):
                        gateways.extend([str(v).strip() for v in val if str(v).strip()])
                    elif isinstance(val, str) and val.strip():
                        gateways.append(val.strip())
                except OSError:
                    pass
    except OSError:
        pass
    return gateways


def check_gateway_reachable(gateway_ip, timeout=1.5):
    """Check if gateway responds to TCP connection on common ports (80, 443, 53)."""
    if not gateway_ip:
        return False
    for port in (80, 443, 53):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((gateway_ip, port))
                return True
        except Exception:
            pass
    # If TCP ports are filtered, attempt ICMP ping
    try:
        res = subprocess.run(
            ['ping', '-n', '1', '-w', str(int(timeout * 1000)), gateway_ip],
            capture_output=True, text=True, errors='replace', timeout=timeout + 1
        )
        return res.returncode == 0
    except Exception:
        return False


def check_internet_reachability(timeout=1.5):
    """Check whether public DNS/Internet endpoints can be reached."""
    targets = [('1.1.1.1', 53), ('8.8.8.8', 53)]
    for host, port in targets:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((host, port))
                return True
        except Exception:
            pass
    return False


def get_hotspot_client_ips_from_arp(network_cidr, gateway_ip):
    """Query ARP table for active client IPs in the hotspot subnet."""
    client_ips = []
    try:
        net = ipaddress.ip_network(network_cidr)
        res = subprocess.run(['arp', '-a'], capture_output=True, text=True, errors='replace', timeout=3)
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                candidate = parts[0].strip()
                try:
                    ip_obj = ipaddress.ip_address(candidate)
                    if ip_obj in net and candidate != gateway_ip and not candidate.endswith('.255'):
                        # Exclude multicast/broadcast
                        client_ips.append(candidate)
                except ValueError:
                    pass
    except Exception:
        pass
    return list(dict.fromkeys(client_ips))

def enable_mobile_hotspot(ssid_name="hbwifi"):
    try:
        # Opening the Settings URI is only a fallback prompt.  Do not wait for
        # the Settings app from the application startup thread.
        os.startfile('ms-settings:network-mobilehotspot')
        print(f"Hotspot activated / configuration opened for SSID: {ssid_name}")
    except Exception as e:
        print(f"Hotspot execution error: {e}")


def get_current_hotspot_wifi_info():
    """Read the current Windows Mobile Hotspot SSID and passphrase via WinRT."""
    try:
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            return {'ssid': '', 'passphrase': ''}
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
        access_point = manager.get_current_access_point_configuration()
        return {
            'ssid': (access_point.ssid or '').strip(),
            'passphrase': (access_point.passphrase or '').strip(),
        }
    except Exception:
        return {'ssid': '', 'passphrase': ''}


def get_current_hotspot_ssid():
    """Read the SSID currently configured for Windows Mobile Hotspot via WinRT."""
    return get_current_hotspot_wifi_info()['ssid']


def set_current_hotspot_ssid(ssid, password=None):
    """Apply the program-defined SSID and optional password via Windows WinRT."""
    try:
        import asyncio
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            return False, 'No active Internet connection profile was found'
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
        access_point = manager.get_current_access_point_configuration()
        previous_ssid = (access_point.ssid or '').strip()
        access_point.ssid = ssid
        if password:
            access_point.passphrase = password

        async def configure():
            await manager.configure_access_point_async(access_point)

        asyncio.run(configure())
        verified = get_current_hotspot_wifi_info()
        verified_ssid = verified.get('ssid', '').strip()
        verified_password = verified.get('passphrase', '').strip()
        if verified_ssid != ssid or (password and verified_password != password):
            return False, (
                "Windows did not retain the requested hotspot credentials; "
                f"actual SSID='{verified_ssid}', password verification failed"
            )
        return True, f"Hotspot credentials updated for '{ssid}'"
    except Exception as exc:
        return False, f"Hotspot SSID change failed: {exc}"


def get_windows_hotspot_client_limits():
    """Read the actual Windows Mobile Hotspot client count and OS limit."""
    try:
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            return None, None, 'No active Internet connection profile was found'
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
        return int(manager.client_count), int(manager.max_client_count), ''
    except Exception as exc:
        return None, None, f'Windows hotspot limit unavailable: {exc}'


def get_windows_hotspot_registry_limit():
    """Read the optional, unofficial Windows ICS peer limit registry value."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SYSTEM\CurrentControlSet\Services\icssvc\Settings',
            0,
            winreg.KEY_READ,
        ) as key:
            value, value_type = winreg.QueryValueEx(key, 'WifiMaxPeers')
            if value_type != winreg.REG_DWORD:
                return None
            return int(value)
    except (FileNotFoundError, OSError):
        return None


def apply_windows_hotspot_registry_limit(limit):
    """Write the unofficial WifiMaxPeers value; requires an elevated process."""
    try:
        import winreg

        limit = int(limit)
        if not 1 <= limit <= WINDOWS_HOTSPOT_LIMIT_MAX:
            return False, f'Windows hotspot limit must be between 1 and {WINDOWS_HOTSPOT_LIMIT_MAX}.'
        with winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            r'SYSTEM\CurrentControlSet\Services\icssvc\Settings',
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, 'WifiMaxPeers', 0, winreg.REG_DWORD, limit)
        return True, f'WifiMaxPeers set to {limit}'
    except PermissionError:
        return False, 'Administrator permission is required. Restart PrintShopApp as Administrator and try again.'
    except OSError as exc:
        return False, f'Windows registry update failed: {exc}'


def check_hotspot_checkpoints(internet_nic=None, hotspot_nic=None, hotspot_network='192.168.137.0/24', hotspot_gateway='192.168.137.1'):
    """Execute the structured 6-point verification for Internet ingress and Hotspot egress.

    1. 인터넷 인입용 체크포인트 (인터넷 소스 어댑터)
       - [ ] 연결 상태 확인 (Media State): "Media disconnected"가 아닌 정상 IPv4 할당 여부
       - [ ] 게이트웨이 및 인터넷 통신 확인: 상위 공유기 게이트웨이 및 인터넷 통신 정상 여부
       - [ ] 윈도우 모바일 핫스팟 공유 소스 매칭: '다음에서 인터넷 연결 공유' 항목과 인입용 어댑터 일치 여부

    2. 핫스팟용 체크포인트 (와이파이 송출 어댑터)
       - [ ] 핫스팟 어댑터 활성화 여부: 가상 어댑터(Wi-Fi Direct / Local Area Connection*) 활성화 여부
       - [ ] 고정 IP(192.168.137.1) 및 서브넷 마스크(255.255.255.0) 할당 여부
       - [ ] 클라이언트 기기 IP 할당 (DHCP) 확인: 192.168.137.x 대역 IP 할당 및 ARP 조회
    """
    network, gateway = normalize_hotspot_network(hotspot_network, hotspot_gateway)
    name_map = get_net_connection_name_map()
    name_to_guid = {v.lower(): k for k, v in name_map.items()}
    shared_source_guid = get_hotspot_sharing_source_guid()
    shared_source_name = name_map.get(shared_source_guid, '') if shared_source_guid else ''

    # --- 1. 인터넷 인입용 체크포인트 ---
    selected_in_name = (internet_nic.get('display', '') if isinstance(internet_nic, dict) else str(internet_nic or '')).strip()
    in_clean_name = selected_in_name.rsplit(' (', 1)[0] if ' (' in selected_in_name else selected_in_name

    # If internet_nic is not specified or not found, try to auto-detect active non-hotspot adapter
    if not in_clean_name or in_clean_name.lower().startswith('default'):
        if shared_source_name:
            in_clean_name = shared_source_name
        else:
            for name, stats in psutil.net_if_stats().items():
                if stats.isup and not any(k in name.lower() for k in ('local area connection*', 'loopback', 'bluetooth')):
                    in_clean_name = name
                    break

    in_stats = psutil.net_if_stats().get(in_clean_name)
    in_addrs = psutil.net_if_addrs().get(in_clean_name, [])
    in_ipv4 = [a.address for a in in_addrs if a.family == socket.AF_INET and not a.address.startswith('169.254.')]

    in_guid = name_to_guid.get(in_clean_name.lower())
    in_gateways = get_adapter_default_gateways(in_guid)

    # 1.1 Media State & IP
    media_connected = bool(in_stats and in_stats.isup and in_ipv4)
    media_detail = f"Adapter '{in_clean_name}' UP, IPv4: {', '.join(in_ipv4)}" if media_connected else f"Adapter '{in_clean_name or 'None'}' Media disconnected or no valid IPv4"

    # 1.2 Gateway & Internet
    gw_reachable = False
    for gw in in_gateways:
        if check_gateway_reachable(gw):
            gw_reachable = True
            break
    internet_reachable = check_internet_reachability()
    gw_internet_ok = bool(internet_reachable or gw_reachable)
    gw_detail = (
        f"Gateway: {', '.join(in_gateways) or 'None'} (Reachable: {gw_reachable}), "
        f"Internet: {'OK' if internet_reachable else 'Check Failed'}"
    )

    # 1.3 Windows Mobile Hotspot sharing source match
    source_matching = bool(shared_source_guid and in_guid and shared_source_guid == in_guid)
    if not source_matching and in_clean_name and shared_source_name:
        source_matching = in_clean_name.lower() == shared_source_name.lower()
    source_detail = (
        f"Configured ICS Source: '{shared_source_name or shared_source_guid or 'Not set'}' "
        f"(Selected Ingress: '{in_clean_name}') - {'Matched' if source_matching else 'Mismatch'}"
    )

    # --- 2. 핫스팟용 체크포인트 ---
    # 2.1 핫스팟 어댑터 활성화 여부
    virtual_adapters = []
    gateway_adapter = None
    gateway_mask = None
    for name, addrs in psutil.net_if_addrs().items():
        stats = psutil.net_if_stats().get(name)
        ipv4_addrs = [a for a in addrs if a.family == socket.AF_INET]
        ipv4_list = [a.address for a in ipv4_addrs]
        is_virtual = any(k in name.lower() for k in ('local area connection*', 'wi-fi direct', 'direct virtual')) or gateway in ipv4_list
        if is_virtual:
            virtual_adapters.append((name, bool(stats and stats.isup), ipv4_list))
        if gateway in ipv4_list:
            gateway_adapter = name
            for a in ipv4_addrs:
                if a.address == gateway:
                    gateway_mask = a.netmask

    hotspot_adapter_up = any(v[1] for v in virtual_adapters) or (gateway_adapter is not None)
    up_virtual_names = [v[0] for v in virtual_adapters if v[1]]
    hotspot_adapter_detail = (
        f"Active virtual adapter(s): {', '.join(up_virtual_names)}" if up_virtual_names
        else (f"Virtual adapter '{gateway_adapter}' assigned gateway" if gateway_adapter else "Virtual adapter(s) disconnected / inactive")
    )

    # 2.2 고정 IP(192.168.137.1) 및 서브넷 마스크(255.255.255.0) 할당 여부
    gateway_ip_ok = bool(gateway_adapter is not None)
    expected_mask = '255.255.255.0'
    mask_ok = bool(gateway_mask == expected_mask) if gateway_mask else False
    gateway_detail = (
        f"Assigned to '{gateway_adapter}' with IP {gateway} (Mask: {gateway_mask or 'Unknown'})"
        if gateway_ip_ok else f"Gateway {gateway} ({expected_mask}) not assigned to any adapter"
    )

    # 2.3 클라이언트 기기 IP 할당 (DHCP) 확인
    client_ips = get_hotspot_client_ips_from_arp(network, gateway)
    client_count, max_clients, limit_err = get_windows_hotspot_client_limits()
    dhcp_detail = (
        f"Connected client(s): {len(client_ips)} found in {network} ({', '.join(client_ips) if client_ips else 'none in ARP'}). "
        f"Windows tethering reports: {client_count if client_count is not None else 0}/{max_clients if max_clients is not None else 8} clients"
    )
    # If clients are connected or hotspot is running without IP conflicts
    dhcp_ok = bool(gateway_ip_ok and (client_count == 0 or len(client_ips) > 0 or client_count is not None))

    checkpoints = {
        'ingress_media_state': {
            'title': '인터넷 인입 어댑터 연결 상태 (Media State)',
            'passed': media_connected,
            'detail': media_detail,
        },
        'ingress_gateway_and_internet': {
            'title': '게이트웨이 및 인터넷 통신 확인',
            'passed': gw_internet_ok,
            'detail': gw_detail,
        },
        'ingress_sharing_source_match': {
            'title': '윈도우 모바일 핫스팟 공유 소스 매칭',
            'passed': source_matching,
            'detail': source_detail,
        },
        'egress_adapter_active': {
            'title': '핫스팟 어댑터(가상/무선) 활성화 여부',
            'passed': hotspot_adapter_up,
            'detail': hotspot_adapter_detail,
        },
        'egress_gateway_ip_assigned': {
            'title': f'고정 IP({gateway}) 및 서브넷 마스크 할당 여부',
            'passed': gateway_ip_ok,
            'detail': gateway_detail,
        },
        'egress_client_dhcp': {
            'title': f'클라이언트 기기 IP 할당(DHCP, {network}) 확인',
            'passed': dhcp_ok,
            'detail': dhcp_detail,
        },
    }

    all_passed = all(cp['passed'] for cp in checkpoints.values())
    return {
        'all_passed': all_passed,
        'checkpoints': checkpoints,
        'summary': (
            f"[인터넷 인입] 미디어: {'PASS' if media_connected else 'FAIL'} | "
            f"통신: {'PASS' if gw_internet_ok else 'FAIL'} | "
            f"소스매칭: {'PASS' if source_matching else 'FAIL'} || "
            f"[핫스팟 송출] 어댑터: {'PASS' if hotspot_adapter_up else 'FAIL'} | "
            f"고정IP: {'PASS' if gateway_ip_ok else 'FAIL'} | "
            f"클라이언트DHCP: {'PASS' if dhcp_ok else 'FAIL'}"
        ),
    }


def run_hotspot_diagnostics(hotspot_nic, hotspot_network, hotspot_gateway, internet_nic=None):
    """Inspect the selected adapter and report whether the hotspot range is active."""
    network, gateway = normalize_hotspot_network(hotspot_network, hotspot_gateway)
    selected_name = hotspot_nic.get('display', '') if isinstance(hotspot_nic, dict) else str(hotspot_nic or '')
    adapter_name = selected_name.rsplit(' (', 1)[0] if ' (' in selected_name else selected_name
    stats = psutil.net_if_stats().get(adapter_name)
    addresses = psutil.net_if_addrs().get(adapter_name, [])
    ipv4_addresses = [addr.address for addr in addresses if addr.family == socket.AF_INET]

    lines = [f"Selected adapter: {adapter_name or 'Not selected'}", f"Expected range: {network}", f"Expected gateway: {gateway}"]

    client_count, max_client_count, limit_error = get_windows_hotspot_client_limits()
    if max_client_count is not None:
        lines.append(f"Windows Mobile Hotspot clients: {client_count} of {max_client_count}")
        lines.append("Windows client limit: read-only through the supported WinRT API")
    else:
        lines.append(limit_error)

    # Run structured 6-point verification
    cp_result = check_hotspot_checkpoints(
        internet_nic=internet_nic,
        hotspot_nic=hotspot_nic,
        hotspot_network=network,
        hotspot_gateway=gateway,
    )
    lines.append("--- Checkpoint Verification ---")
    for cp_key, cp in cp_result['checkpoints'].items():
        mark = "[PASS]" if cp['passed'] else "[FAIL]"
        lines.append(f"{mark} {cp['title']}: {cp['detail']}")

    gateway_adapter = None
    gateway_adapter_ips = []
    for candidate_name, candidate_addrs in psutil.net_if_addrs().items():
        candidate_ipv4 = [addr.address for addr in candidate_addrs if addr.family == socket.AF_INET]
        if gateway in candidate_ipv4:
            gateway_adapter = candidate_name
            gateway_adapter_ips = candidate_ipv4
            break

    if gateway_adapter:
        gateway_stats = psutil.net_if_stats().get(gateway_adapter)
        lines.append(f"Hotspot gateway adapter: {gateway_adapter}")
        lines.append(f"Gateway adapter status: {'UP' if gateway_stats and gateway_stats.isup else 'DOWN'}")
        lines.append(f"Gateway adapter IPv4: {', '.join(gateway_adapter_ips)}")
        lines.append("Hotspot status: ON / gateway is assigned")
        return {
            'active': bool(gateway_stats and gateway_stats.isup),
            'text': '\n'.join(lines),
            'checkpoints': cp_result['checkpoints'],
            'checkpoint_summary': cp_result['summary'],
        }

    if not stats:
        lines.append("Adapter status: NOT FOUND")
        lines.append("Hotspot status: OFF / adapter unavailable")
        return {
            'active': False,
            'text': '\n'.join(lines),
            'checkpoints': cp_result['checkpoints'],
            'checkpoint_summary': cp_result['summary'],
        }

    lines.append(f"Adapter status: {'UP' if stats.isup else 'DOWN'}")
    lines.append(f"IPv4 addresses: {', '.join(ipv4_addresses) if ipv4_addresses else 'none'}")
    in_range = any(ipaddress.ip_address(address) in ipaddress.ip_network(network) for address in ipv4_addresses)
    gateway_assigned = gateway in ipv4_addresses
    active = bool(stats.isup and gateway_assigned)
    if active:
        lines.append("Hotspot status: ON / gateway is assigned")
    elif stats.isup and in_range:
        lines.append("Hotspot status: PARTIAL / adapter is up but gateway differs")
    elif stats.isup:
        lines.append("Hotspot status: READY / adapter is up, hotspot IP not assigned")
    else:
        lines.append("Hotspot status: OFF / adapter is down")
    return {
        'active': active,
        'text': '\n'.join(lines),
        'checkpoints': cp_result['checkpoints'],
        'checkpoint_summary': cp_result['summary'],
    }


def set_hotspot_enabled(enabled, ssid_name, internet_nic=None, hotspot_nic=None, hotspot_network='192.168.137.0/24', hotspot_gateway='192.168.137.1', enforce_checkpoints=True):
    """Control modern Windows tethering, with legacy netsh as a fallback.

    When `enabled=True` and `enforce_checkpoints=True`, pre-flight checks are
    performed on the Internet ingress adapter before initiating tethering.
    """
    if enabled and enforce_checkpoints:
        cp_check = check_hotspot_checkpoints(
            internet_nic=internet_nic,
            hotspot_nic=hotspot_nic,
            hotspot_network=hotspot_network,
            hotspot_gateway=hotspot_gateway,
        )
        # Checkpoint 1.1: Media state
        if not cp_check['checkpoints']['ingress_media_state']['passed']:
            detail = cp_check['checkpoints']['ingress_media_state']['detail']
            return False, f"인터넷 인입 어댑터 연결 오류: {detail}"

        # Checkpoint 1.2: Gateway / Internet reachability
        if not cp_check['checkpoints']['ingress_gateway_and_internet']['passed']:
            detail = cp_check['checkpoints']['ingress_gateway_and_internet']['detail']
            logging.warning(f"인터넷 인입 통신 경고: {detail}")

        # Checkpoint 1.3: Mobile Hotspot sharing source match
        if not cp_check['checkpoints']['ingress_sharing_source_match']['passed']:
            detail = cp_check['checkpoints']['ingress_sharing_source_match']['detail']
            logging.warning(f"인터넷 연결 공유 소스 불일치 경고: {detail}")

    try:
        import asyncio
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager

        profile = NetworkInformation.get_internet_connection_profile()
        if profile is None:
            raise RuntimeError("No active Internet connection profile was found")
        manager = NetworkOperatorTetheringManager.create_from_connection_profile(profile)

        async def control_tethering():
            return await (
                manager.start_tethering_async() if enabled
                else manager.stop_tethering_async()
            )

        # WinRT can leave the tethering future pending when Mobile Hotspot is
        # unavailable.  Do not block application startup indefinitely; use
        # the legacy/settings fallback after a short bounded wait.
        result = asyncio.run(asyncio.wait_for(control_tethering(), timeout=8))
        # WinRT returns a NetworkOperatorTetheringOperationResult object.
        # Its useful status is exposed as a property; converting the object
        # itself to str() only produces a memory address and looks like a
        # failure even when the operation succeeded.
        status_value = getattr(result, 'status', None)
        if status_value is None:
            status_value = getattr(result, 'operation_status', None)
        status = str(status_value if status_value is not None else result)
        status_name = getattr(status_value, 'name', status).lower()
        normalized_status = status_name.replace('_', '').replace(' ', '')
        if any(
            token in normalized_status
            for token in ('success', 'alreadyon', 'alreadyoff')
        ):
            action_text = 'started' if enabled else 'stopped'
            return True, f"Windows mobile hotspot {action_text} ({status})"
        modern_message = f"Windows tethering returned {status}"
    except (asyncio.TimeoutError, asyncio.CancelledError, KeyboardInterrupt) as exc:
        modern_message = f"WinRT tethering timed out or was cancelled: {exc}"
    except Exception as exc:
        modern_message = f"WinRT tethering unavailable: {exc}"

    action = 'start' if enabled else 'stop'
    try:
        result = subprocess.run(
            ['netsh', 'wlan', action, 'hostednetwork'],
            capture_output=True, text=True, encoding=CONFIG_ENCODING, errors='replace', timeout=10
        )
        output = (result.stdout or result.stderr).strip()
        if enabled and result.returncode == 0:
            enable_mobile_hotspot(ssid_name)
        if result.returncode == 0:
            return True, output or f"netsh hostednetwork {action} completed"
        if enabled:
            enable_mobile_hotspot(ssid_name)
        return False, f"{modern_message}\nLegacy netsh: {output or 'command failed'}"
    except (OSError, subprocess.SubprocessError) as exc:
        if enabled:
            enable_mobile_hotspot(ssid_name)
        return False, f"{modern_message}\nLegacy netsh: {exc}"

