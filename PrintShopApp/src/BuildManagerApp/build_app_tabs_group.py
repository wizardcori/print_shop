from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QGroupBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from BuildManagerApp.app_version_group import AppTargetCardWidget
from BuildManagerApp.build_progress_tracker import BuildProgressTracker

INSTALLER_TAB_KEY: str = "installer"
DEFAULT_TAB_GROUP_TITLE: str = "BuildApp"
DEFAULT_PACE_DURATION_SEC: float = 45.0
DEFAULT_TICK_INTERVAL_MS: int = 1000
TIME_FORMAT_HMS: str = "%H:%M:%S"
EMPTY_TIME_PLACEHOLDER: str = "-"
ZERO_ELAPSED_STR: str = "00:00:00"
PERCENT_MIN: int = 0
PERCENT_MAX: int = 100

STATUS_BUILDING: str = "빌드중"
STATUS_COMPLETED: str = "빌드완료"
STATUS_FAILED: str = "빌드실패"

LABEL_WAITING_BUILD: str = "빌드 대기"
LABEL_WAITING_DEFAULT: str = "대기 중"
LABEL_IN_PROGRESS: str = "진행 중"
LABEL_START_DEFAULT: str = "빌드 시작"

PROP_LOCATION_PATH: str = "_location_path"
META_KEY_EXE_PATH: str = "_exe_path"
META_KEY_ITEMS: str = "items"


class BuildAppTabGroupBox(QGroupBox):
    """
    '빌드 로그' 그룹박스 위에 배치되는 'BuildApp' 그룹박스.
    - 상단 '빌드 대상 선택'에서 체크된 항목 및 인스톨러를 개별 탭(AppTargetCardWidget)으로 추가/유지합니다.
    - 빌드 시작 시 해당 앱/인스톨러 탭을 자동으로 선택하고, BuildProgressBadge에 진행 상황을 업데이트합니다.
    """

    target_selection_changed = Signal(str, bool)  # (target_key, checked)
    target_bump_changed = Signal(str, bool)       # (target_key, checked)

    def __init__(self, title: str = DEFAULT_TAB_GROUP_TITLE, parent: QWidget | None = None):
        super().__init__(title, parent)
        self._cards_by_key: dict[str, AppTargetCardWidget] = {}
        self._ordered_keys: list[str] = []
        self._start_times: dict[str, str] = {}
        self._started_keys: set[str] = set()

        self._init_ui()
        self.tracker = BuildProgressTracker(
            group_lookup=self.get_card,
            pace_duration_sec=DEFAULT_PACE_DURATION_SEC,
            tick_interval_ms=DEFAULT_TICK_INTERVAL_MS,
            parent=self,
        )

    def _init_ui(self) -> None:
        self.setStyleSheet(
            """
            QGroupBox {
                background-color: #101318;
                border: 1px solid #d4c42a;
                border-radius: 5px;
                margin-top: 8px;
                padding: 6px;
                font-weight: 700;
                color: #f1f3f4;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setTabsClosable(False)
        self.tab_widget.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #2b313c;
                border-radius: 4px;
                background-color: #15181e;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #1c2028;
                color: #b0b7c3;
                border: 1px solid #2b313c;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 5px 14px;
                margin-right: 2px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background-color: #202632;
                color: #9ec5ff;
                border-color: #4b5563;
            }
            QTabBar::tab:hover:!selected {
                background-color: #252b36;
                color: #f1f3f4;
            }
            """
        )
        layout.addWidget(self.tab_widget)

    def sync_selected_targets(
        self,
        ordered_selected_keys: list[str],
        meta_provider: Callable[[str], dict[str, Any]],
        include_installer_tab: bool = False,
    ) -> None:
        """
        체크된 대상 목록(ordered_selected_keys) 및 인스톨러 탭 포함 여부에 따라 탭 목록을 동기화합니다.
        """
        desired_keys: list[str] = list(ordered_selected_keys)
        if include_installer_tab and INSTALLER_TAB_KEY not in desired_keys:
            desired_keys.append(INSTALLER_TAB_KEY)

        selected_set = set(desired_keys)

        for key in list(self._cards_by_key.keys()):
            if key not in selected_set:
                card = self._cards_by_key.pop(key)
                self._start_times.pop(key, None)
                self._started_keys.discard(key)
                idx = self.tab_widget.indexOf(card)
                if idx >= 0:
                    self.tab_widget.removeTab(idx)
                card.deleteLater()

        prev_current = self.tab_widget.currentWidget()
        for target_pos, key in enumerate(desired_keys):
            info = meta_provider(key) or {}
            target_name = str(info.get("target_name") or key)
            label_text = str(info.get("label_text") or key)
            display_name = str(info.get("display_name") or key)
            loc_path = info.get("location_path")
            bump_checked = bool(info.get("bump_checked", False))
            prev_meta = info.get("prev_meta")
            is_installer = key == INSTALLER_TAB_KEY

            card = self._cards_by_key.get(key)
            if card is None:
                card = AppTargetCardWidget(
                    key=key,
                    target_name=target_name,
                    label_text=label_text,
                    display_name=display_name,
                    parent=self.tab_widget,
                )
                card.checkbox.setChecked(True)
                if is_installer:
                    card.chk_bump.setVisible(False)
                    card.prev_box.setTitle("인스톨러 대상")
                    card.next_box.setTitle("인스톨러 산출물")
                    card.prev_box.clear_info(label_text)
                    card.next_box.clear_info(LABEL_WAITING_DEFAULT)
                else:
                    card.chk_bump.setVisible(True)
                    card.set_bump_checked(bump_checked, block_signals=True)

                card.checkbox.stateChanged.connect(
                    lambda state, k=key: self.target_selection_changed.emit(
                        k, state == Qt.CheckState.Checked.value
                    )
                )
                card.chk_bump.stateChanged.connect(
                    lambda state, k=key: self.target_bump_changed.emit(
                        k, state == Qt.CheckState.Checked.value
                    )
                )
                card.open_location_requested.connect(self._on_open_location)
                self._cards_by_key[key] = card
                self.tab_widget.insertTab(target_pos, card, display_name)
            else:
                card.label_text = label_text
                card.display_name = display_name
                card.checkbox.setText(label_text)
                card.btn_open_loc.setText(display_name)
                if is_installer:
                    card.chk_bump.setVisible(False)
                    card.prev_box.setTitle("인스톨러 대상")
                    card.next_box.setTitle("인스톨러 산출물")
                    card.prev_box.clear_info(label_text)
                else:
                    card.chk_bump.setVisible(True)
                    card.set_bump_checked(bump_checked, block_signals=True)

                cur_idx = self.tab_widget.indexOf(card)
                if cur_idx >= 0:
                    self.tab_widget.setTabText(cur_idx, display_name)
                    if cur_idx != target_pos:
                        self.tab_widget.tabBar().moveTab(cur_idx, target_pos)

            card.set_location_tooltip(str(loc_path) if loc_path else None)
            card.setProperty(PROP_LOCATION_PATH, str(loc_path) if loc_path else "")

            if not is_installer and (isinstance(prev_meta, dict) or prev_meta is None):
                card.set_prev_meta(prev_meta)

        self._ordered_keys = list(desired_keys)

        if prev_current is not None and self.tab_widget.indexOf(prev_current) >= 0:
            self.tab_widget.setCurrentWidget(prev_current)
        elif self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)

    def get_card(self, key: str) -> AppTargetCardWidget | None:
        return self._cards_by_key.get(key)

    def focus_tab(self, key: str) -> None:
        card = self._cards_by_key.get(key)
        if card is not None:
            idx = self.tab_widget.indexOf(card)
            if idx >= 0 and self.tab_widget.currentIndex() != idx:
                self.tab_widget.setCurrentIndex(idx)

    def reset_all_progress(self, target_keys: list[str] | None = None) -> None:
        """빌드 시작 전 대상 탭들의 배지를 대기중으로 초기화합니다."""
        self.tracker.reset()
        self._start_times.clear()
        self._started_keys.clear()
        keys = target_keys if target_keys is not None else list(self._cards_by_key.keys())
        for key in keys:
            card = self._cards_by_key.get(key)
            if card is not None:
                card.clear_next_meta(LABEL_WAITING_BUILD)
                card.progress_badge.set_waiting(
                    start_time=EMPTY_TIME_PLACEHOLDER,
                    elapsed_str=ZERO_ELAPSED_STR,
                    end_time=EMPTY_TIME_PLACEHOLDER,
                    percent=PERCENT_MIN,
                )

    def notify_target_started(self, target_key: str, detail: str = LABEL_START_DEFAULT) -> None:
        """해당 앱/인스톨러 빌드가 시작될 때 탭을 자동 선택하고 '빌드중' 배지를 시작합니다."""
        if target_key not in self._start_times:
            self._start_times[target_key] = datetime.now().strftime(TIME_FORMAT_HMS)
        self._started_keys.add(target_key)
        self.focus_tab(target_key)
        card = self._cards_by_key.get(target_key)
        if card is not None and target_key == INSTALLER_TAB_KEY:
            card.set_next_meta(
                {
                    META_KEY_EXE_PATH: str(card.property(PROP_LOCATION_PATH) or ""),
                    META_KEY_ITEMS: {
                        "version": EMPTY_TIME_PLACEHOLDER,
                        "build_id": LABEL_IN_PROGRESS,
                        "commit": EMPTY_TIME_PLACEHOLDER,
                        "dirty": EMPTY_TIME_PLACEHOLDER,
                        "time": detail,
                    },
                }
            )
        self.tracker.handle_progress(
            target_key=target_key,
            status=STATUS_BUILDING,
            percent=PERCENT_MIN,
            start_time=self._start_times[target_key],
            end_time=EMPTY_TIME_PLACEHOLDER,
            detail=detail,
        )

    def notify_target_progress(self, target_key: str, percent: int, detail: str) -> None:
        """빌드 진행 중 탭을 유지/선택하고 BuildProgressBadge 진행률을 업데이트합니다."""
        if target_key not in self._started_keys:
            self.notify_target_started(target_key, detail=detail)

        start_str = self._start_times.setdefault(
            target_key, datetime.now().strftime(TIME_FORMAT_HMS)
        )
        self.tracker.handle_progress(
            target_key=target_key,
            status=STATUS_BUILDING,
            percent=percent,
            start_time=start_str,
            end_time=EMPTY_TIME_PLACEHOLDER,
            detail=detail,
        )

    def notify_target_finished(
        self,
        target_key: str,
        success: bool,
        percent: int = PERCENT_MAX,
    ) -> None:
        """빌드 완료/실패 시 해당 앱/인스톨러의 BuildProgressBadge 최종 상태를 반영합니다."""
        start_str = self._start_times.get(target_key, EMPTY_TIME_PLACEHOLDER)
        end_str = datetime.now().strftime(TIME_FORMAT_HMS)
        self._started_keys.discard(target_key)
        final_status = STATUS_COMPLETED if success else STATUS_FAILED
        card = self._cards_by_key.get(target_key)
        if card is not None and target_key == INSTALLER_TAB_KEY:
            card.set_next_meta(
                {
                    META_KEY_EXE_PATH: str(card.property(PROP_LOCATION_PATH) or ""),
                    META_KEY_ITEMS: {
                        "version": EMPTY_TIME_PLACEHOLDER,
                        "build_id": final_status,
                        "commit": EMPTY_TIME_PLACEHOLDER,
                        "dirty": EMPTY_TIME_PLACEHOLDER,
                        "time": end_str,
                    },
                }
            )
        self.tracker.handle_progress(
            target_key=target_key,
            status=final_status,
            percent=PERCENT_MAX if success else percent,
            start_time=start_str,
            end_time=end_str,
            detail="",
        )

    def _on_open_location(self, key: str) -> None:
        card = self._cards_by_key.get(key)
        if card is None:
            return
        raw_path = str(card.property(PROP_LOCATION_PATH) or "").strip()
        if not raw_path:
            return
        p = Path(raw_path)
        target_dir = p.parent if p.is_file() else p
        if target_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))