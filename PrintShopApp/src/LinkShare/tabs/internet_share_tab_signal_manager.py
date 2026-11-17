"""Qt signals shared by the integrated LinkBox and LinkShare services."""

from PySide6.QtCore import QObject, Signal

class InternetShareTabSignalManager(QObject):
    _instance = None
    
    # tab update 전송되는 시그널 정의
    approval_load_filtered_signal = Signal(str, str, str)
    connected_load_filtered_signal = Signal(str, str, str)
    history_load_filtered_signal = Signal(str, str, str)
    request_load_filtered_signal = Signal(str, str, str)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

ist_signal_manager = InternetShareTabSignalManager()

