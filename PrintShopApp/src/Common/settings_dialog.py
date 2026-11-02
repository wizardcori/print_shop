"""Runtime registry for feature-owned settings tabs."""

_tabs = {}

from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QDialogButtonBox
from PySide6.QtCore import Qt

class SettingsDialog(QDialog):
    _instance = None

    def __new__(cls, parent=None):
        # 싱글톤 패턴 적용: 이미 인스턴스가 존재하면 기존 객체를 반환
        if cls._instance is not None:
            return cls._instance
        cls._instance = super(SettingsDialog, cls).__new__(cls)
        return cls._instance

    def __init__(self, parent=None):
        if hasattr(self, '_initialized') and self._initialized:
            return
        super().__init__(parent)
        self._initialized = True

        self.setWindowTitle("Preferences / Settings")
        self.resize(850, 600)
        
        # 모달리스 설정 및 닫힐 때 객체 소멸 방지
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # UI 및 탭 초기화 함수 호출
        self._init_ui()

    def _init_ui(self):
        """다이얼로그 레이아웃 구성 및 탭 위젯 생성"""
        layout = QVBoxLayout(self)
        
        self.settings_tabs = QTabWidget(self)
        layout.addWidget(self.settings_tabs)
        
        # 레지스트리 탭 동적 로드 함수 호출
        self._load_registered_tabs()
                
        # 하단 닫기 버튼 추가 (클릭 시 창을 숨김)
        button_box = QDialogButtonBox(QDialogButtonBox.Close, self)
        button_box.rejected.connect(self.hide)  # close() 대신 hide() 연결
        layout.addWidget(button_box)

    def _load_registered_tabs(self):
        """settings_registry에 등록된 모든 탭 항목을 order 순서대로 순회하여 추가합니다."""
        for tab_id, order, title, factory in iter_settings_tabs():
            print(f"[Debug] Attempting to load tab -> id: {tab_id}, title: {title}, order: {order}")
            try:
                tab_widget = factory(self) if callable(factory) else None
                if tab_widget:
                    self.settings_tabs.addTab(tab_widget, title)
                    print(f"[Settings] Successfully loaded tab '{title}'")
                else:
                    print(f"[Settings] Factory for '{tab_id}' returned None.")
            except Exception as e:
                print(f"[Settings] Error creating settings tab '{tab_id}': {e}")


    @classmethod
    def show_dialog(cls, parent=None):
        """외부에서 호출 시 생성되어 있거나 숨겨져 있는 창을 활성화하여 표시"""
        if cls._instance is None:
            cls._instance = cls(parent)
        
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    def closeEvent(self, event):
        """창의 'X' 버튼 등으로 닫을 때, 완전 종료 대신 hide() 처리하고 인스턴스는 유지"""
        event.ignore()  # 기본 종료 이벤트를 무시
        self.hide()     # 창을 숨김 처리하여 객체와 상태 유지[cite: 1]


def register_settings_tab(*args, **kwargs):
    """
    지원하는 호출 형태 (인자 개수별 명확한 분기):
    1개: register_settings_tab(factory)
    2개: register_settings_tab(factory, order)
    3개: register_settings_tab(tab_id, title, factory)
    4개: register_settings_tab(tab_id, title, factory, order)
    """
    num_args = len(args)

    if num_args == 1:
        # 1개: factory만 전달 (속성 자동 추출, order 기본값 100)
        factory = args[0]
        if not callable(factory):
            raise TypeError("첫 번째 인자는 팩토리(클래스/함수)여야 합니다.")
        tab_id = getattr(factory, 'tab_id', factory.__name__)
        title = getattr(factory, 'title', tab_id)
        order = kwargs.get('order', 100)

    elif num_args == 2:
        # 2개: factory와 order 전달 (속성 자동 추출)
        factory = args[0]
        order = args[1]
        if not callable(factory):
            raise TypeError("첫 번째 인자는 팩토리(클래스/함수)여야 합니다.")
        tab_id = getattr(factory, 'tab_id', factory.__name__)
        title = getattr(factory, 'title', tab_id)

    elif num_args == 3:
        # 3개: tab_id, title, factory 전달 (order 기본값 100)
        tab_id, title, factory = args[0], args[1], args[2]
        order = kwargs.get('order', 100)

    elif num_args == 4:
        # 4개: tab_id, title, factory, order 모두 전달
        tab_id, title, factory, order = args[0], args[1], args[2], args[3]

    else:
        raise TypeError(f"register_settings_tab 함수는 1~4개의 인자만 허용합니다. (현재 인자 개수: {num_args})")

    # 탭 저장소에 등록
    _tabs[str(tab_id)] = (int(order), str(title), factory)

    

def iter_settings_tabs():
    for tab_id, (order, title, factory) in sorted(_tabs.items(), key=lambda item: (item[1][0], item[0])):
        # order를 함께 yield하도록 수정합니다.
        yield tab_id, order, title, factory
