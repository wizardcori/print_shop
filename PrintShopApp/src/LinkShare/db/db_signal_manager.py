from PySide6.QtCore import QObject, Signal

class DBSignalManager(QObject):
    _instance = None
    
    # 각 DB 변경 시 전송되는 시그널 정의
    request_updated = Signal()
    history_added = Signal()
    approval_added = Signal()
    session_updated = Signal()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

signal_manager = DBSignalManager()