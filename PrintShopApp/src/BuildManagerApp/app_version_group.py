from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from BuildManagerApp.build_progress_badge import BuildProgressBadge

DEFAULT_BASE_PT: float = 10.5
DEFAULT_MIN_PT: float = 8.0
FONT_STEP_PT: float = 0.5
MIN_AVAIL_WIDTH_PX: int = 8
MIN_ELIDE_WIDTH_PX: int = 12
MIN_WIDGET_AVAIL_WIDTH_PX: int = 16
LABEL_MARGIN_SUB_PX: int = 2

CHECKBOX_BASE_PT: float = 11.0
CHECKBOX_MIN_PT: float = 8.5
CHECKBOX_INDICATOR_RESERVE_PX: int = 24

BUTTON_BASE_PT: float = 9.5
BUTTON_MIN_PT: float = 7.5
BUTTON_H_PAD_PX: int = 14

META_LABEL_BASE_PT: float = 10.0
META_LABEL_MIN_PT: float = 8.0
CARD_MIN_HEIGHT_PX: int = 140
CARD_CHECKBOX_BASE_PT: float = 10.5
CARD_CHECKBOX_MIN_PT: float = 8.0
CARD_CHECKBOX_RESERVE_PX: int = 22
CARD_BUMP_BASE_PT: float = 10.0
CARD_BUMP_MIN_PT: float = 8.5
CARD_BUMP_RESERVE_PX: int = 20
CARD_BUMP_MIN_WIDTH_PX: int = 72

EMPTY_VALUE_STR: str = "-"
STATUS_UNCHECKED: str = "미확인"
STATUS_NO_INFO: str = "정보 없음"
STATUS_NO_EXE: str = "EXE 없음"
STATUS_NO_PREV_EXE: str = "이전 EXE 없음"
STATUS_NO_NEXT_EXE: str = "이후 EXE 없음"
LABEL_BUMP_CHECKBOX: str = "버전증가"
TITLE_PREV_VERSION_DEFAULT: str = "이전버전 (EXE)"
TITLE_NEXT_VERSION_DEFAULT: str = "이후버전 (EXE)"

META_ROW_SPECS: tuple[tuple[str, str], ...] = (
    ("exe", "EXE"),
    ("version", "버전"),
    ("build_id", "빌드ID"),
    ("commit", "커밋"),
    ("dirty", "Dirty"),
    ("time", "시각"),
    ("size", "크기"),
)


def fit_font_size_only(
    widget: QWidget,
    text: str,
    available_width: int,
    base_pt: float = DEFAULT_BASE_PT,
    min_pt: float = DEFAULT_MIN_PT,
    allow_elide: bool = True,
) -> str:
    """가용 너비에 맞춰 폰트 크기만 줄이고, 필요 시 말줄임 문자열을 반환합니다."""
    clean_text = text or ""
    font = widget.font()

    if available_width <= MIN_AVAIL_WIDTH_PX:
        font.setPointSizeF(min_pt)
        widget.setFont(font)
        return clean_text

    pt = base_pt
    chosen_pt = min_pt
    while pt >= min_pt:
        font.setPointSizeF(pt)
        fm = QFontMetrics(font)
        if fm.horizontalAdvance(clean_text) <= available_width:
            chosen_pt = pt
            break
        pt -= FONT_STEP_PT

    font.setPointSizeF(chosen_pt)
    widget.setFont(font)

    if not allow_elide:
        return clean_text

    fm = QFontMetrics(font)
    if fm.horizontalAdvance(clean_text) > available_width:
        return fm.elidedText(
            clean_text,
            Qt.TextElideMode.ElideRight,
            max(MIN_ELIDE_WIDTH_PX, available_width),
        )
    return clean_text


class AutoFitLabel(QLabel):
    """가용 폭이 줄어들면 글자 크기를 축소하고 넘칠 때 말줄임/툴팁을 적용하는 라벨."""

    def __init__(
        self,
        text: str = "",
        base_pt: float = DEFAULT_BASE_PT,
        min_pt: float = DEFAULT_MIN_PT,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._full_text = text
        self._base_pt = base_pt
        self._min_pt = min_pt
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text or ""
        super().setToolTip(self._full_text if self._full_text not in ("", EMPTY_VALUE_STR) else "")
        self._refresh_fit()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_fit()

    def _refresh_fit(self) -> None:
        avail = max(MIN_ELIDE_WIDTH_PX, self.contentsRect().width() - LABEL_MARGIN_SUB_PX)
        fitted = fit_font_size_only(
            self,
            self._full_text,
            avail,
            base_pt=self._base_pt,
            min_pt=self._min_pt,
            allow_elide=True,
        )
        super().setText(fitted)


class AutoFitCheckBox(QCheckBox):
    """가용 폭이 줄어들면 체크박스 라벨 글자를 축소하는 체크박스."""

    def __init__(
        self,
        text: str = "",
        base_pt: float = CHECKBOX_BASE_PT,
        min_pt: float = CHECKBOX_MIN_PT,
        indicator_reserve_px: int = CHECKBOX_INDICATOR_RESERVE_PX,
        allow_elide: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._full_text = text
        self._base_pt = base_pt
        self._min_pt = min_pt
        self._indicator_reserve_px = indicator_reserve_px
        self._allow_elide = allow_elide
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored if allow_elide else QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Preferred,
        )
        self.setText(text)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text or ""
        super().setToolTip(self._full_text)
        self._refresh_fit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_fit()

    def _refresh_fit(self) -> None:
        avail = max(MIN_WIDGET_AVAIL_WIDTH_PX, self.width() - self._indicator_reserve_px)
        fitted = fit_font_size_only(
            self,
            self._full_text,
            avail,
            base_pt=self._base_pt,
            min_pt=self._min_pt,
            allow_elide=self._allow_elide,
        )
        super().setText(fitted)


class AutoFitButton(QPushButton):
    """가용 폭이 줄어들면 글자 크기를 축소하고 툴팁으로 전체 텍스트를 보여주는 버튼."""

    def __init__(
        self,
        text: str = "",
        base_pt: float = BUTTON_BASE_PT,
        min_pt: float = BUTTON_MIN_PT,
        h_pad: int = BUTTON_H_PAD_PX,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._full_text = text
        self._base_pt = base_pt
        self._min_pt = min_pt
        self._h_pad = h_pad
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText(text)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text or ""
        super().setToolTip(self._full_text)
        self._refresh_fit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_fit()

    def _refresh_fit(self) -> None:
        avail = max(MIN_WIDGET_AVAIL_WIDTH_PX, self.width() - self._h_pad)
        fitted = fit_font_size_only(
            self,
            self._full_text,
            avail,
            base_pt=self._base_pt,
            min_pt=self._min_pt,
            allow_elide=True,
        )
        super().setText(fitted)


class VersionMetaPanel(QGroupBox):
    """이전버전 또는 이후버전 EXE에서 복호화된 정보를 표시하는 서브 그룹."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        self._value_labels: dict[str, AutoFitLabel] = {}
        self._key_labels: list[AutoFitLabel] = []
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._init_ui()
        self.clear_info(STATUS_UNCHECKED)

    def _init_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(6, 10, 6, 5)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(2)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        for r, (key, caption) in enumerate(META_ROW_SPECS):
            lbl_k = AutoFitLabel(f"{caption}:", base_pt=META_LABEL_BASE_PT, min_pt=META_LABEL_MIN_PT)
            lbl_k.setStyleSheet("color: #9aa0a6;")
            lbl_v = AutoFitLabel(EMPTY_VALUE_STR, base_pt=META_LABEL_BASE_PT, min_pt=META_LABEL_MIN_PT)
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_v.setStyleSheet("color: #e8eaed; font-weight: 500;")
            layout.addWidget(lbl_k, r, 0)
            layout.addWidget(lbl_v, r, 1)
            self._key_labels.append(lbl_k)
            self._value_labels[key] = lbl_v

    def clear_info(self, version_status: str = STATUS_NO_INFO):
        for k, lbl in self._value_labels.items():
            lbl.setText(version_status if k == "version" else EMPTY_VALUE_STR)
            lbl.setToolTip("")

    def update_from_decrypt_result(self, result: dict[str, Any] | None, empty_msg: str = STATUS_NO_EXE):
        if not result:
            self.clear_info(empty_msg)
            return
        if "error" in result:
            self.clear_info(f"오류 ({result['error']})")
            return

        items = result.get("items") or {}
        file_size = result.get("file_size_bytes")
        size_text = f"{file_size:,} B" if isinstance(file_size, int) else EMPTY_VALUE_STR
        exe_path = str(result.get("_exe_path") or "")
        exe_name = exe_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] if exe_path else EMPTY_VALUE_STR

        lbl_exe = self._value_labels["exe"]
        lbl_exe.setText(exe_name)
        if exe_path:
            lbl_exe.setToolTip(exe_path)

        self._value_labels["version"].setText(str(items.get("version") or EMPTY_VALUE_STR))
        self._value_labels["build_id"].setText(str(items.get("build_id") or EMPTY_VALUE_STR))
        self._value_labels["commit"].setText(str(items.get("commit") or EMPTY_VALUE_STR))
        self._value_labels["dirty"].setText(str(items.get("dirty") or EMPTY_VALUE_STR))
        self._value_labels["time"].setText(str(items.get("time") or EMPTY_VALUE_STR))
        self._value_labels["size"].setText(size_text)


class AppTargetCardWidget(QGroupBox):
    """앱 1개 단위 카드 위젯 (체크박스 + 위치 버튼 + 진행 배지 + 버전증가 + 이전/이후 EXE 패널)."""

    open_location_requested = Signal(str)

    def __init__(
        self,
        key: str,
        target_name: str,
        label_text: str,
        display_name: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.key = key
        self.target_name = target_name
        self.label_text = label_text
        self.display_name = display_name
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._init_ui()

    def _init_ui(self):
        self.setMinimumHeight(CARD_MIN_HEIGHT_PX)
        self.setStyleSheet(
            """
            QGroupBox {
                background-color: #15181e;
                border: 1px solid #2b313c;
                border-radius: 5px;
                margin-top: 2px;
                padding: 4px;
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        self.checkbox = AutoFitCheckBox(
            self.label_text,
            base_pt=CARD_CHECKBOX_BASE_PT,
            min_pt=CARD_CHECKBOX_MIN_PT,
            indicator_reserve_px=CARD_CHECKBOX_RESERVE_PX,
            allow_elide=True,
        )
        self.checkbox.setStyleSheet(
            """
            QCheckBox {
                color: #f1f3f4;
                font-weight: 600;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 3px;
                border: 2px solid #c5b329;
                background-color: transparent;
            }
            QCheckBox::indicator:checked {
                background-color: #c5b329;
                border: 2px solid #e0cd38;
            }
            """
        )

        self.btn_open_loc = AutoFitButton(
            self.display_name,
            base_pt=BUTTON_BASE_PT,
            min_pt=BUTTON_MIN_PT,
            h_pad=BUTTON_H_PAD_PX,
            parent=self,
        )
        self.btn_open_loc.setToolTip(f"{self.display_name} 위치 열기")
        self.btn_open_loc.setStyleSheet(
            """
            QPushButton {
                background-color: #202632;
                color: #9ec5ff;
                border: 1px solid #384357;
                border-radius: 3px;
                padding: 2px 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2b3548;
                border-color: #5b8def;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #19202b;
            }
            """
        )
        self.btn_open_loc.clicked.connect(lambda: self.open_location_requested.emit(self.key))

        self.progress_badge = BuildProgressBadge(self)

        self.chk_bump = AutoFitCheckBox(
            LABEL_BUMP_CHECKBOX,
            base_pt=CARD_BUMP_BASE_PT,
            min_pt=CARD_BUMP_MIN_PT,
            indicator_reserve_px=CARD_BUMP_RESERVE_PX,
            allow_elide=False,
        )
        self.chk_bump.setToolTip("체크 시 해당 개별 앱의 버전을 증가시킨 뒤 빌드합니다.")
        self.chk_bump.setMinimumWidth(CARD_BUMP_MIN_WIDTH_PX)
        self.chk_bump.setStyleSheet(
            """
            QCheckBox {
                color: #8ab4f8;
                font-weight: 600;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1.5px solid #5f8dd8;
                background-color: transparent;
            }
            QCheckBox::indicator:checked {
                background-color: #4285f4;
                border: 1.5px solid #8ab4f8;
            }
            """
        )

        header_row.addWidget(self.checkbox, stretch=2)
        header_row.addWidget(self.btn_open_loc, stretch=2)
        header_row.addWidget(self.progress_badge, stretch=4)
        header_row.addWidget(self.chk_bump, stretch=0)
        outer.addLayout(header_row)

        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(0, 0, 0, 0)
        ver_row.setSpacing(4)

        sub_style = """
            QGroupBox {
                background-color: #1c2028;
                border: 1px solid #303744;
                border-radius: 4px;
                margin-top: 4px;
                font-size: 10px;
                font-weight: 600;
                color: #bdc1c6;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
            }
        """
        self.prev_box = VersionMetaPanel(TITLE_PREV_VERSION_DEFAULT)
        self.next_box = VersionMetaPanel(TITLE_NEXT_VERSION_DEFAULT)
        self.prev_box.setStyleSheet(sub_style)
        self.next_box.setStyleSheet(sub_style)

        ver_row.addWidget(self.prev_box, stretch=1)
        ver_row.addWidget(self.next_box, stretch=1)
        outer.addLayout(ver_row, stretch=1)

    def set_location_tooltip(self, path_str: str | None):
        if path_str:
            self.btn_open_loc.setToolTip(f"{self.display_name} 위치 열기:\n{path_str}")
        else:
            self.btn_open_loc.setToolTip(f"{self.display_name} 위치 열기")

    def is_build_checked(self) -> bool:
        return self.checkbox.isChecked()

    def is_bump_checked(self) -> bool:
        return self.chk_bump.isChecked()

    def set_bump_checked(self, checked: bool, block_signals: bool = False):
        if block_signals:
            self.chk_bump.blockSignals(True)
        self.chk_bump.setChecked(checked)
        if block_signals:
            self.chk_bump.blockSignals(False)

    def set_prev_meta(self, result: dict[str, Any] | None):
        source_label = ""
        if isinstance(result, dict):
            source_label = str(
                result.get("_source_label")
                or (result.get("items") or {}).get("source")
                or ""
            ).strip()

        if hasattr(self, "prev_box") and hasattr(self.prev_box, "setTitle"):
            self.prev_box.setTitle(
                f"이전버전 ({source_label})" if source_label else TITLE_PREV_VERSION_DEFAULT
            )

        self.prev_box.update_from_decrypt_result(result, empty_msg=STATUS_NO_PREV_EXE)

    def set_next_meta(self, result: dict[str, Any] | None):
        self.next_box.update_from_decrypt_result(result, empty_msg=STATUS_NO_NEXT_EXE)

    def clear_next_meta(self, status_msg: str = ""):
        self.next_box.clear_info(status_msg)