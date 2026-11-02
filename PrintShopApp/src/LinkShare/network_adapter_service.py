"""LinkShare network-adapter discovery and Wi-Fi diagnostics helpers."""

import logging
import socket
import winreg

import psutil


def log_wifi(logger, message, level=logging.INFO):
    """Write a hotspot diagnostic message through the supplied logger."""
    logger.log(level, message)


def check_global_internet() -> bool:
    """Verify outbound internet connectivity using Microsoft NCSI endpoint and DNS probe."""
    import urllib.request
    try:
        req = urllib.request.Request('http://www.msftconnecttest.com/connecttest.txt', headers={'User-Agent': 'NCSI'})
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            if resp.status == 200 and b'Microsoft Connect Test' in resp.read():
                return True
    except Exception:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as c:
            c.settimeout(1.2)
            c.connect(('1.1.1.1', 53))
        return True
    except Exception:
        return False


def get_adapter_hardware_info():
    """Retrieve physical adapter set, driver descriptions, and default gateways from registry."""
    guid_to_name = {}
    base_net = r'SYSTEM\CurrentControlSet\Control\Network\{4D36E972-E325-11CE-BFC1-08002BE10318}'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_net) as k:
            i = 0
            while True:
                try:
                    g = winreg.EnumKey(k, i)
                    i += 1
                    try:
                        with winreg.OpenKey(k, rf'{g}\Connection') as ck:
                            name, _ = winreg.QueryValueEx(ck, 'Name')
                            guid_to_name[g.strip('{}').lower()] = name
                    except OSError:
                        pass
                except OSError:
                    break
    except OSError:
        pass

    physical_set = set()
    desc_map = {}
    base_class = r'SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_class) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    i += 1
                    if not sub.isdigit():
                        continue
                    with winreg.OpenKey(k, sub) as sk:
                        try:
                            cfg_id, _ = winreg.QueryValueEx(sk, 'NetCfgInstanceId')
                            chars, _ = winreg.QueryValueEx(sk, 'Characteristics')
                            desc, _ = winreg.QueryValueEx(sk, 'DriverDesc')
                            clean_id = cfg_id.strip('{}').lower()
                            if clean_id in guid_to_name:
                                conn_name = guid_to_name[clean_id]
                                desc_map[conn_name] = desc
                                # NCF_PHYSICAL (0x4) and not NCF_VIRTUAL (0x1)
                                if bool(chars & 0x4) and not bool(chars & 0x1):
                                    physical_set.add(conn_name)
                        except OSError:
                            pass
                except OSError:
                    break
    except OSError:
        pass

    gw_map = {}
    base_tcp = r'SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_tcp) as k:
            i = 0
            while True:
                try:
                    guid = winreg.EnumKey(k, i)
                    i += 1
                    with winreg.OpenKey(k, guid) as sk:
                        def q(val):
                            try:
                                v = winreg.QueryValueEx(sk, val)[0]
                                if isinstance(v, list):
                                    return [x for x in v if x and x != '0.0.0.0']
                                return [v] if v and v != '0.0.0.0' else []
                            except Exception:
                                return []
                        gw_list = q('DefaultGateway') or q('DhcpDefaultGateway')
                        clean_guid = guid.strip('{}').lower()
                        conn_name = guid_to_name.get(clean_guid)
                        if conn_name and gw_list:
                            gw_map[conn_name] = gw_list[0]
                except OSError:
                    break
    except OSError:
        pass

    return physical_set, desc_map, gw_map


def check_internet_via_ip(ip_address, nic_name=None, gw_map=None, global_internet=None):
    """Check if the given IP address/adapter currently routes out to the Internet."""
    # Never consider APIPA (169.254.x.x) or loopback as having internet
    if not ip_address or ip_address.startswith('169.254.') or ip_address.startswith('127.'):
        return False

    if gw_map is not None:
        if nic_name and not gw_map.get(nic_name):
            return False
        if global_internet is not None:
            return bool(global_internet)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.8)
            connection.bind((ip_address, 0))
            connection.connect(("google.com", 80))
        return True
    except Exception:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
                connection.settimeout(0.8)
                connection.bind((ip_address, 0))
                connection.connect(("1.1.1.1", 53))
            return True
        except Exception:
            return False


_driver_desc_cache = None


def get_adapter_driver_desc_map():
    """Retrieve Windows network adapter driver descriptions from registry."""
    global _driver_desc_cache
    if _driver_desc_cache is not None:
        return _driver_desc_cache

    net_map = {}
    base_net = r'SYSTEM\CurrentControlSet\Control\Network\{4D36E972-E325-11CE-BFC1-08002BE10318}'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_net) as k:
            i = 0
            while True:
                try:
                    guid = winreg.EnumKey(k, i)
                    i += 1
                    try:
                        with winreg.OpenKey(k, rf'{guid}\Connection') as ck:
                            name, _ = winreg.QueryValueEx(ck, 'Name')
                            net_map[guid.strip('{}').lower()] = name
                    except OSError:
                        pass
                except OSError:
                    break
    except OSError:
        pass

    desc_map = {}
    base_class = r'SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_class) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    i += 1
                    try:
                        with winreg.OpenKey(k, sub) as sk:
                            driver_desc, _ = winreg.QueryValueEx(sk, 'DriverDesc')
                            net_id, _ = winreg.QueryValueEx(sk, 'NetCfgInstanceId')
                            conn_name = net_map.get(net_id.strip('{}').lower())
                            if conn_name:
                                desc_map[conn_name] = driver_desc
                    except OSError:
                        pass
                except OSError:
                    break
    except OSError:
        pass

    _driver_desc_cache = desc_map
    return desc_map


def is_wireless_interface(name):
    """Detect if an interface is a physical or virtual wireless adapter."""
    name_lower = name.lower()
    if any(keyword in name_lower for keyword in ('wi-fi', 'wifi', 'wireless', 'wlan', '802.11')):
        return True
    try:
        desc = get_adapter_driver_desc_map().get(name, '').lower()
        if any(keyword in desc for keyword in ('wi-fi', 'wifi', 'wireless', 'wlan', '802.11', 'wi-fi direct', 'direct virtual')):
            return True
    except Exception:
        pass
    return False


def get_nic_mac_address(nic_name: str) -> str:
    """Return the physical/MAC address for a given adapter name."""
    clean = nic_name.rsplit(' (', 1)[0] if ' (' in nic_name else nic_name
    for a in psutil.net_if_addrs().get(clean, []):
        if getattr(a, 'family', None) in (psutil.AF_LINK, -1, 17) and a.address:
            if any(c in a.address for c in ':-'):
                return a.address.upper().replace('-', ':')
    return ''


def ping_ip_address(ip_address: str, timeout_ms: int = 800) -> bool:
    """Check if the given IP address responds to ICMP ping."""
    import subprocess
    try:
        res = subprocess.run(
            ['ping', '-n', '1', '-w', str(timeout_ms), ip_address],
            capture_output=True,
            text=True,
            errors='replace',
            timeout=int(timeout_ms / 1000) + 2,
        )
        out = res.stdout
        return bool(('TTL=' in out or 'bytes=' in out.lower()) and res.returncode == 0)
    except Exception:
        return False


def get_network_interfaces():
    """Return (display name, IPv4, internet reachable, wireless) entries ordered by usability."""
    interfaces = []
    physical_set, desc_map, gw_map = get_adapter_hardware_info()
    global_internet = check_global_internet()

    try:
        for nic_name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ip = addr.address
                    mac = get_nic_mac_address(nic_name)
                    mac_suffix = f" [MAC: {mac}]" if mac else ""
                    is_connected = check_internet_via_ip(ip, nic_name=nic_name, gw_map=gw_map, global_internet=global_internet)
                    interfaces.append((
                        f"{nic_name} ({ip}){mac_suffix}",
                        ip,
                        is_connected,
                        is_wireless_interface(nic_name),
                    ))
    except Exception:
        pass

    if not interfaces:
        interfaces.append(("Default (192.168.137.1)", "192.168.137.1", False, True))

    def nic_priority(item):
        display_name, ip, connected, wireless = item
        nic_name = display_name.rsplit(' (', 1)[0] if ' (' in display_name else display_name
        stats = psutil.net_if_stats().get(nic_name)
        is_up = stats.isup if stats else False
        is_apipa = ip.startswith('169.254.')
        is_hotspot_gw = (ip == '192.168.137.1')
        is_physical = nic_name in physical_set

        # Physical score: physical first (0) over virtual (1)
        phys_score = 0 if is_physical else 1

        # Status score prioritization:
        # 0: Up and assigned 192.168.137.1 (active hotspot gateway)
        # 1: Connected to Internet and UP
        # 2: UP with regular IP
        # 3: UP but APIPA
        # 4: DOWN with regular IP
        # 5: DOWN with APIPA
        if is_hotspot_gw and is_up:
            status_score = 0
        elif connected and is_up:
            status_score = 1
        elif is_up and not is_apipa:
            status_score = 2
        elif is_up:
            status_score = 3
        elif not is_apipa:
            status_score = 4
        else:
            status_score = 5

        wifi_score = 0 if wireless else 1
        speed = -(stats.speed if stats and stats.speed else 0)
        return phys_score, status_score, wifi_score, speed

    interfaces.sort(key=nic_priority)
    return interfaces


def choose_optimal_adapters(interfaces, saved_internet_display='', saved_internet_ip='',
                            saved_hotspot_display='', saved_hotspot_ip=''):
    """Determine optimal (Internet NIC, Hotspot NIC) based on hardware rules:

    1. 인터넷이 되는 nic는 인터넷 nic로
    2. 두개가 다되면 유선우선
    3. 두개중 하나만 되면 되는것은 인터넷, 안되는것은 핫스팟
    4. 두개가 다 안되면 인터넷 nic fail (None 또는 빈 어댑터)
    5. 물리적인 장치만 판단 (가상 어댑터 배제)
    6. nic가 여러개면 인터넷은 유선, 무선, 속도 빠른 순으로 결정
    """
    physical_set, desc_map, gw_map = get_adapter_hardware_info()
    global_internet = check_global_internet()

    # Index candidates by clean nic name
    iface_by_name = {}
    for item in interfaces:
        display, ip, conn, wireless = item
        clean = display.rsplit(' (', 1)[0] if ' (' in display else display
        if clean not in iface_by_name:
            iface_by_name[clean] = item

    # Rule 5: Only evaluate physical adapters
    physical_candidates = [nic for nic in physical_set if nic in iface_by_name]
    if not physical_candidates:
        physical_candidates = [nic for nic in physical_set if nic in psutil.net_if_addrs()]
    if not physical_candidates:
        # Fallback if no physical adapter metadata available
        physical_candidates = list(iface_by_name.keys())

    # Internet candidate sorting key:
    # Rule 2: wired preferred over wireless
    # Rule 6: wired (1) > wireless (0), higher speed, is_up
    def internet_sort_key(nic):
        stats = psutil.net_if_stats().get(nic)
        is_up = 1 if (stats and stats.isup) else 0
        speed = (stats.speed if stats and stats.speed else 0)
        desc = desc_map.get(nic, '')
        is_wireless = 1 if is_wireless_interface(nic) else 0
        is_wired = 1 if not is_wireless else 0
        return (is_wired, is_wireless, speed, is_up)

    # Hotspot candidate sorting key:
    # Hotspot preferentially selects a wireless adapter (Rule: Wi-Fi broadcast), higher speed, is_up
    def hotspot_sort_key(nic):
        stats = psutil.net_if_stats().get(nic)
        is_up = 1 if (stats and stats.isup) else 0
        speed = (stats.speed if stats and stats.speed else 0)
        is_wireless = 1 if is_wireless_interface(nic) else 0
        return (is_wireless, speed, is_up)

    # Separate candidates into internet capable vs non-internet
    internet_capable = []
    non_internet = []
    for nic in physical_candidates:
        stats = psutil.net_if_stats().get(nic)
        # If adapter is in interfaces list with is_connected=True or stats report isup with default gateway
        is_up = bool(stats.isup) if stats else bool(iface_by_name.get(nic))
        has_gw = bool(gw_map.get(nic))
        iface_conn = bool(iface_by_name.get(nic, (None, None, False))[2])
        can_internet = bool(global_internet and (has_gw or iface_conn) and is_up)
        if can_internet:
            internet_capable.append(nic)
        else:
            non_internet.append(nic)

    internet_capable.sort(key=internet_sort_key, reverse=True)
    non_internet.sort(key=hotspot_sort_key, reverse=True)

    # Determine Internet NIC:
    # Rule 4: If no adapters have internet, internet nic fails
    if not internet_capable:
        selected_internet = None
    else:
        selected_internet = internet_capable[0]

    # Hotspot priority: If an adapter is currently active and assigned the hotspot gateway (192.168.137.1),
    # it is definitely the active hotspot broadcasting adapter.
    selected_hotspot = None
    for nic, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET and a.address == '192.168.137.1':
                if nic in iface_by_name:
                    selected_hotspot = nic
                    break
        if selected_hotspot:
            break

    # If no active 192.168.137.1 adapter found, apply standard decision rules
    if not selected_hotspot:
        # Rule 4: If no adapters have internet, internet nic fails
        if not internet_capable:
            selected_hotspot = non_internet[0] if non_internet else (physical_candidates[0] if physical_candidates else None)
        # Rule 3: Exactly one has internet -> that one is Internet, the other is Hotspot
        elif len(physical_candidates) >= 2 and len(internet_capable) == 1:
            selected_hotspot = non_internet[0] if non_internet else None
        else:
            # Rule 1, 2, 6: Multiple have internet or 1 candidate total
            remaining = [nic for nic in physical_candidates if nic != selected_internet]
            remaining.sort(key=hotspot_sort_key, reverse=True)
            selected_hotspot = remaining[0] if remaining else None

    def make_entry(nic_name):
        if not nic_name:
            return ('', '', False, False)
        if nic_name in iface_by_name:
            return iface_by_name[nic_name]
        # Build entry directly from psutil
        addrs = psutil.net_if_addrs().get(nic_name, [])
        ipv4 = next((a.address for a in addrs if a.family == socket.AF_INET and not a.address.startswith('127.')), '')
        mac = get_nic_mac_address(nic_name)
        mac_suffix = f" [MAC: {mac}]" if mac else ""
        stats = psutil.net_if_stats().get(nic_name)
        is_up = bool(stats and stats.isup)
        has_gw = bool(gw_map.get(nic_name))
        is_conn = bool(global_internet and has_gw and is_up)
        is_wireless = is_wireless_interface(nic_name)
        return (f"{nic_name} ({ipv4}){mac_suffix}" if ipv4 else f"{nic_name}{mac_suffix}", ipv4, is_conn, is_wireless)

    return make_entry(selected_internet), make_entry(selected_hotspot)


def choose_preferred_interface(interfaces, saved_display='', saved_ip='', wireless_only=False):
    """Choose a saved NIC when valid and not disconnected/APIPA, otherwise the best matching NIC."""
    candidates = [item for item in interfaces if not wireless_only or item[3]] or interfaces

    # Check if saved NIC is still active and valid (not APIPA 169.254.x.x unless nothing else exists)
    for item in candidates:
        display_name, ip, _, _ = item
        if (display_name == saved_display or ip == saved_ip):
            nic_name = display_name.rsplit(' (', 1)[0] if ' (' in display_name else display_name
            stats = psutil.net_if_stats().get(nic_name)
            is_up = stats.isup if stats else False
            is_apipa = ip.startswith('169.254.')
            # If saved adapter is UP and has a valid IP, keep it
            if is_up and not is_apipa:
                return item

    # If wireless_only is True (Hotspot NIC recommendation), prefer an active adapter with 192.168.137.1
    if wireless_only:
        for item in candidates:
            if item[1] == '192.168.137.1':
                return item

    # Otherwise return the top ranked candidate
    fallback = ("Default (192.168.137.1)", "192.168.137.1", False, True)
    return candidates[0] if candidates else fallback
