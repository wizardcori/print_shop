"""Qt signals shared by the integrated LinkBox and LinkShare services."""

from PySide6.QtCore import QObject, Signal


class ServerSignals(QObject):
    """Bridge worker-thread web events into the Qt application thread."""

    approval_requested = Signal(str, int, str)
    transfer_updated = Signal(str, str, int, str)
