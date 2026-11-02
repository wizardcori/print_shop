"""LinkShare approval-notification sound controller."""

import os

from PySide6.QtCore import QTimer


class ApprovalSoundController:
    """Play and stop the operator approval sound without shell logic."""

    def __init__(self, window, play_notification_sound, stop_notification_sound, winsound):
        self.window = window
        self.play_notification_sound = play_notification_sound
        self.stop_notification_sound = stop_notification_sound
        self.winsound = winsound

    def play(self):
        window = self.window
        if not window.approval_sound_enabled or self.winsound is None:
            return
        path = next((path for path in window.approval_sounds if path and os.path.isfile(path)), '')
        if not path:
            return
        try:
            self.play_notification_sound(path)
            if window.approval_sound_playback_timer:
                window.approval_sound_playback_timer.stop()
            window.approval_sound_playback_timer = QTimer(window)
            window.approval_sound_playback_timer.setSingleShot(True)
            window.approval_sound_playback_timer.timeout.connect(self.stop)
            window.approval_sound_playback_timer.start(15 * 60 * 1000)
        except (OSError, RuntimeError) as exc:
            print(f"Approval sound playback error: {exc}")

    def stop(self):
        window = self.window
        if window.approval_sound_playback_timer:
            window.approval_sound_playback_timer.stop()
            window.approval_sound_playback_timer = None
        self.stop_notification_sound()
