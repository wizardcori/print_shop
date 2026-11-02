"""Shared window geometry persistence helpers."""

from PySide6.QtCore import QPoint, QRect, QSettings, QSize
from PySide6.QtGui import QGuiApplication


def _available_geometry(position):
    for screen in QGuiApplication.screens():
        if screen.availableGeometry().contains(position):
            return screen.availableGeometry()
    return QGuiApplication.primaryScreen().availableGeometry()


def restore_window_geometry(window, settings, key, default_size=None):
    """Restore a window and keep it visible on an available screen."""
    size = settings.value(f'{key}/size', default_size, type=QSize) if default_size else settings.value(f'{key}/size', type=QSize)
    position_key = f'{key}/position'
    position = settings.value(position_key, type=QPoint)
    if size and size.isValid():
        window.resize(size)
    # PySide6.QPoint does not expose QSize's isValid() method.  QSettings
    # returns a default QPoint() when the key is absent, so check the key
    # explicitly and validate the coordinate object without calling isValid.
    if settings.contains(position_key) and position is not None:
        window.move(position)
    keep_window_visible(window)


def save_window_geometry(window, settings, key):
    settings.setValue(f'{key}/size', window.size())
    settings.setValue(f'{key}/position', window.pos())
    settings.sync()


def keep_window_visible(window):
    """Move a window into the available desktop when its saved position is off-screen."""
    available = _available_geometry(window.frameGeometry().topLeft())
    frame = window.frameGeometry()
    x = min(max(frame.x(), available.left()), available.right() - min(frame.width(), available.width()) + 1)
    y = min(max(frame.y(), available.top()), available.bottom() - min(frame.height(), available.height()) + 1)
    window.move(x, y)
