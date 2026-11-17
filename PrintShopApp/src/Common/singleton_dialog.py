from PySide6.QtWidgets import QDialog, QApplication
from Common.log import logd

class SingletonDialog(QDialog):
    """프로그램 전체에서 단 하나의 인스턴스만 존재하도록 보장하는 공통 싱글톤 다이얼로그 클래스"""
    _instances = {}  # 클래스별로 싱글톤 인스턴스를 관리하기 위한 딕셔너리

    @classmethod
    def get_instance(cls, parent=None):
        """해당 클래스의 유일한 인스턴스를 반환 (없으면 생성)"""
        if cls not in cls._instances or cls._instances[cls] is None:
            instance = cls(parent)
            cls._instances[cls] = instance
            
            # 앱 종료 시점에 자동 메모리 해제 바인딩
            app = QApplication.instance()
            if app:
                # 람다를 사용하여 현재 클래스(cls)의 인스턴스를 정확히 타겟팅하여 정리
                app.aboutToQuit.connect(lambda: cls.cleanup_instance(cls))
                
        return cls._instances[cls]

    @classmethod
    def cleanup_instance(cls, target_cls=None):
        """프로그램 종료 시 C++ 메모리 안전 해제"""
        target = target_cls or cls
        if target in cls._instances and cls._instances[target] is not None:
            logd(f"[{target.__name__}] Cleaning up singleton instance on app quit.")
            cls._instances[target].deleteLater()
            cls._instances[target] = None

    @classmethod
    def show_unique_dialog(cls, parent=None):
        """외부에서 창을 띄울 때 사용하는 공통 진입점"""
        dialog = cls.get_instance(parent)
        if hasattr(dialog, "slot_load_request"):
            dialog.slot_load_request()  # 데이터 갱신 메서드가 있다면 자동 호출
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def closeEvent(self, event):
        """X 버튼으로 닫을 때 파괴하지 않고 숨김 처리 (재사용성 극대화)"""
        if hasattr(self, "save_window_geometry"):
            self.save_window_geometry(self)
        event.ignore()
        self.hide()