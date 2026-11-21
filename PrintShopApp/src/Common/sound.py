import time

try:
    import winsound
except Exception:
    winsound = None  # type: ignore

_LAST_ERROR_SOUND_TS: float = 0.0
_ERROR_SOUND_COOLDOWN_SEC: float = 1.5


def play_error_alert_sound() -> None:
    """loge 출력 시 소리 알림을 재생합니다."""
    global _LAST_ERROR_SOUND_TS
    now = time.monotonic()
    if now - _LAST_ERROR_SOUND_TS < _ERROR_SOUND_COOLDOWN_SEC:
        return
    _LAST_ERROR_SOUND_TS = now

    if winsound is None:
        return
    try:
        winsound.MessageBeep(winsound.MB_ICONHAND)
    except Exception:
        pass