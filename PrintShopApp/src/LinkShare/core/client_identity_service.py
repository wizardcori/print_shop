"""LinkShare browser/client identity tracking."""
def get_client_identity(request, cookie_name, client_identity_map, shared_sessions, identity_lock, client_metadata_map, secrets_module, datetime_module, hashlib_module):
    """Identify a portal user across reconnects without relying on a changing IP.

    The browser cookie is the primary identifier.  The IP remains a transport
    detail and is refreshed on every request.  Device name is only a friendly
    label supplied by the browser; it is not treated as a security identity.
    """
    token = request.cookies.get(cookie_name)
    if not token or len(token) > 256:
        token = secrets_module.token_urlsafe(24)
    token_id = hashlib_module.sha256(token.encode('utf-8')).hexdigest()
    client_ip = request.remote_addr or '-'
    with identity_lock:
        previous_ip = client_identity_map.get(token_id)
        if not previous_ip:
            for candidate_ip, candidate in shared_sessions.items():
                if candidate.get('client_token_id') == token_id:
                    previous_ip = candidate_ip
                    break
        if previous_ip and previous_ip != client_ip and previous_ip in shared_sessions:
            session = shared_sessions.pop(previous_ip)
            existing = shared_sessions.get(client_ip)
            if existing and existing.get('client_token_id') == token_id:
                # Prefer the newer record while preserving the active timer.
                if str(session.get('last_seen', '')) > str(existing.get('last_seen', '')):
                    existing.update(session)
                existing['client_ip'] = client_ip
            else:
                session['client_ip'] = client_ip
                shared_sessions[client_ip] = session
        client_identity_map[token_id] = client_ip
    user_agent = (request.headers.get('User-Agent') or '').strip()[:500]
    if 'Android' in user_agent:
        device_type, operating_system = 'Mobile', 'Android'
    elif any(item in user_agent for item in ('iPhone', 'iPad', 'iPod')):
        device_type, operating_system = 'Mobile', 'iOS'
    elif 'Windows' in user_agent:
        device_type, operating_system = 'PC', 'Windows'
    elif 'Mac OS X' in user_agent:
        device_type, operating_system = 'PC', 'macOS'
    else:
        device_type, operating_system = 'Unknown', 'Unknown'
    if 'Edg/' in user_agent:
        browser = 'Edge'
    elif 'Chrome/' in user_agent:
        browser = 'Chrome'
    elif 'Safari/' in user_agent and 'Chrome/' not in user_agent:
        browser = 'Safari'
    elif 'Firefox/' in user_agent:
        browser = 'Firefox'
    else:
        browser = 'Unknown'
    client_metadata_map[token_id] = {
        'user_name': (request.headers.get('X-Client-Name') or '').strip()[:80],
        'device_name': (request.headers.get('X-Client-Device') or '').strip()[:120],
        'device_type': device_type,
        'operating_system': operating_system,
        'browser': browser,
        'user_agent': user_agent,
        'accept_language': (request.headers.get('Accept-Language') or '').strip()[:120],
        'screen_size': (request.headers.get('X-Client-Screen') or '').strip()[:40],
        'timezone': (request.headers.get('X-Client-Timezone') or '').strip()[:80],
        'last_seen': datetime_module.datetime.now().isoformat(timespec='seconds'),
    }
    device_name = client_metadata_map[token_id]['device_name']
    return token, token_id, client_ip, device_name


