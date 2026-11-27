"""Settings Dialog UI Implementation."""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QTabWidget,
    QDialogButtonBox,
    QScrollArea,
)
from PySide6.QtCore import Qt, Signal

from Common.geometry_manager import AutoGeometryDialog
from Common.settings_registry import iter_settings_tabs
from setting.general_settings import GeneralConfig  # noqa: F401
from setting.env_settings import EnvConfig  # 개발 모드 확인용 설정 임포트

tab_title_style = """
    QTabBar::tab {
        background: #263238;     /* 비선택 탭 배경색 (어두운 회색) */
        color: #90a4ae;          /* 비선택 탭 글자색 (흐린 회색) */
        padding: 6px 14px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        border: 1px solid #37474f;
        border-bottom: none;
        font-weight: normal;
    }
    QTabBar::tab:selected {
        background: #1976d2;     /* 선택된 탭 배경색 (선명한 파란색) */
        color: #ffffff;          /* 선택된 탭 글자색 (흰색) */
        font-weight: bold;       /* 굵은 글씨로 강조 */
        border: 1px solid #2196f3;
    }
    QTabBar::tab:hover:not(:selected) {
        background: #37474f;     /* 마우스 올렸을 때의 색상 */
        color: #cfd8dc;
    }

    /* 추가: 탭이 넘칠 때 나타나는 좌우 스크롤 버튼 스타일 */
    QTabBar::scroller {
        width: 25px;
    }

    QTabBar QToolButton {
        background-color: #263238;
        border: 1px solid #37474f;
        border-radius: 2px;
    }
    QTabBar QToolButton::ubic-left { /* 구버전 호환용 */
        subcontrol-position: left;
    }
    QTabBar QToolButton::right-arrow {
        image: none; /* 필요시 커스텀 화살표 아이콘 경로 지정 가능 */
    }
    QTabBar QToolButton::left-arrow {
        image: none;
    }
    QTabBar QToolButton:hover {
        background-color: #37474f;
    }
"""

# [추가] 각 탭 내부 QScrollArea 및 전체 애플리케이션에서 스크롤바가 명확히 보이도록 설정하는 스타일
scroll_bar_style = """
    QScrollBar:vertical {
        background: #1e272c;
        width: 24px;
        margin: 0px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #546e7a;
        min-height: 20px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical:hover {
        background: #78909c;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QScrollBar:horizontal {
        background: #1e272c;
        height: 24px;
        margin: 0px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal {
        background: #546e7a;
        min-width: 20px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #78909c;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
"""


class SettingsDialog(AutoGeometryDialog):
    _instance = None

    # AutoGeometryWidget이 QWidget 기반일 경우를 대비한 다이얼로그 호환 상수/시그널
    Rejected = 0
    Accepted = 1
    finished = Signal(int)
    accepted = Signal()
    rejected = Signal()

    def __new__(cls, parent=None):
        if cls._instance is not None:
            return cls._instance
        cls._instance = super(SettingsDialog, cls).__new__(cls)
        return cls._instance

    def __init__(self, parent=None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        super().__init__(parent)
        self._initialized = True

        self._dialog_result = self.Rejected
        self.setWindowTitle("Preferences / Settings")

        # AutoGeometryWidget에서 기하 정보(위치/크기)를 복원하지 않은 경우 기본 크기 적용
        if self.width() <= 0 or self.height() <= 0:
            self.resize(850, 300)

        if hasattr(self, "setModal"):
            self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self.general_settings_config = GeneralConfig()
        self._init_ui()

    def _init_ui(self):
        """다이얼로그 레이아웃 구성 및 탭 위젯 생성"""
        layout = QVBoxLayout(self)

        self.settings_tabs = QTabWidget(self)

        # [핵심 추가] 탭 개수가 많아져 창 폭이 좁아질 때 양옆으로 스크롤 화살표 버튼 표시
        self.settings_tabs.setUsesScrollButtons(True)

        # 탭 바에만 직접 스타일 적용
        self.settings_tabs.tabBar().setStyleSheet(scroll_bar_style)

        self.settings_tabs.setMinimumWidth(0)

        layout.addWidget(self.settings_tabs)

        # 최초 UI 초기화 시 탭 로드
        self._load_registered_tabs()

        # 저장된 active 탭이 있으면 해당 탭으로 자동 선택
        saved_tab_index = self.general_settings_config.get("settings_active_tab")
        if saved_tab_index is not None and isinstance(saved_tab_index, int):
            if 0 <= saved_tab_index < self.settings_tabs.count():
                self.settings_tabs.setCurrentIndex(saved_tab_index)

        # 탭 변경 시그널 연결 (값 자동 저장)
        self.settings_tabs.currentChanged.connect(self._on_tab_changed)

        button_box = QDialogButtonBox(QDialogButtonBox.Close, self)
        button_box.rejected.connect(self.hide)
        layout.addWidget(button_box)

    def _on_tab_changed(self, index):
        """탭이 변경될 때 현재 인덱스를 settings_active_tab으로 저장합니다."""
        if index >= 0:
            self.general_settings_config.set("settings_active_tab", index)

    def _load_registered_tabs(self):
        from Common.log import logd, loge

        """settings_registry에 등록된 모든 탭 항목을 order 순서대로 순회하여 추가합니다. (동적 갱신 지원)"""

        if not hasattr(self, "_loaded_tab_ids"):
            self._loaded_tab_ids = set()

        # runtime_mode가 development인지 확인
        env_config = EnvConfig()
        is_development = (
            env_config.get("runtime_mode") == "development"
            or __import__("os").environ.get("MODE", "").strip().lower() == "development"
        )

        _config_load_count = 0
        for tab_id, order, title, factory in iter_settings_tabs():
            if str(tab_id) in self._loaded_tab_ids:
                continue

            try:
                tab_widget = factory(self) if callable(factory) else None
                _config_load_count += 1

                if tab_widget:
                    # 개발 모드인 경우 탭 이름 앞에 order 표시 (예: "[10] General")
                    display_title = f"[{order}] {title}" if is_development else title

                    # [핵심 추가] 각 탭 위젯을 QScrollArea로 감싸기
                    scroll_area = QScrollArea(self)
                    scroll_area.setWidget(tab_widget)
                    scroll_area.setWidgetResizable(True)  # 창 크기에 맞춰 내부 위젯 너비 자동 조절
                    scroll_area.setHorizontalScrollBarPolicy(
                        Qt.ScrollBarAsNeeded
                    )  # 가로 스크롤바 (필요할 때만 표시)
                    scroll_area.setVerticalScrollBarPolicy(
                        Qt.ScrollBarAsNeeded
                    )  # 세로 스크롤바 (필요할 때만 표시)
                    # 탭 위젯 대신 스크롤 영역을 추가
                    self.settings_tabs.addTab(scroll_area, display_title)

                    self._loaded_tab_ids.add(str(tab_id))
                    logd(f"{_config_load_count:02d} : Successfully loaded tab '{display_title}'")
                else:
                    logd(f"{_config_load_count:02d} : Factory for '{tab_id}' returned None.")
            except Exception as e:
                loge(f"{_config_load_count:02d} : Error creating settings tab '{tab_id}': {e}")

    def result(self) -> int:
        if hasattr(super(), "result"):
            return super().result()
        return self._dialog_result

    def done(self, r: int):
        if hasattr(super(), "done"):
            super().done(r)
            return
        self._dialog_result = r
        self.hide()
        self.finished.emit(r)
        if r == self.Accepted:
            self.accepted.emit()
        elif r == self.Rejected:
            self.rejected.emit()

    def accept(self):
        if hasattr(super(), "accept"):
            super().accept()
            return
        self.done(self.Accepted)

    def reject(self):
        if hasattr(super(), "reject"):
            super().reject()
            return
        self.done(self.Rejected)

    @classmethod
    def show_dialog(cls, parent=None):
        """외부에서 호출 시 생성되어 있거나 숨겨져 있는 창을 활성화하여 표시하며, 최신 등록 탭을 동기화합니다."""
        if cls._instance is None:
            cls._instance = cls(parent)
        else:
            # 이미 생성된 다이얼로그라면, 창을 열 때 새로 등록된 탭이 있는지 동기화
            cls._instance._load_registered_tabs()

        # 창을 띄울 때도 저장된 활성 탭 인덱스가 유효한지 확인 후 복원
        saved_tab_index = cls._instance.general_settings_config.get("settings_active_tab")
        if saved_tab_index is not None and isinstance(saved_tab_index, int):
            if 0 <= saved_tab_index < cls._instance.settings_tabs.count():
                cls._instance.settings_tabs.setCurrentIndex(saved_tab_index)

        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    def closeEvent(self, event):
        event.ignore()
        self.hide()
