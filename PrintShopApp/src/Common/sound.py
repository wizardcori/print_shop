import sys
import time
import Path

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

def play_task_completion_sound(
    status: str,
    wav_map: dict[str, str | Path] | None = None,
) -> None:
    """단일 작업 종료 시 비동기로 알림음을 재생합니다."""
    if sys.platform != "win32":
        return

    try:
        custom_path = wav_map.get(status) if wav_map else None
        if custom_path:
            wav_file = Path(custom_path)
            if wav_file.is_file():
                winsound.PlaySound(
                    str(wav_file),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
                return

        beep_type = {
            "SUCCESS": winsound.MB_OK,
            "ERROR": winsound.MB_ICONHAND,
            "CANCELLED": winsound.MB_ICONEXCLAMATION,
        }.get(status, winsound.MB_OK)
        winsound.MessageBeep(beep_type)
    except Exception as exc:
        from Common.log import loge
        loge(f"[BuildManager] 작업 완료 사운드 재생 실패 (status={status}): {exc}")    