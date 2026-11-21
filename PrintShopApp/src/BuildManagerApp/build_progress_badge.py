from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics, QResizeEvent
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QWidget,
)

# 빌드 상태별 텍스트(배지/시간) 컬러 및 배경 테마 정의
_STATE_THEMES: dict[str, dict[str, str]] = {
    "waiting": {
        "badge_bg": "#23272f",
        "badge_border": "#3c424e",
        "badge_fg": "#b0b7c3",
        "times_bg": "#1a1e26",
        "times_border": "#2d333f",
        "times_fg": "#a1a8b3",
        "bar_chunk": "#4b5563",
    },
    "building": {
        "badge_bg": "#382c0e",
        "badge_border": "#8a6914",
        "badge_fg": "#fde047",
        "times_bg": "#262011",
        "times_border": "#524116",
        "times_fg": "#f3dfa2",
        "bar_chunk": "#2563eb",
    },
    "success": {
        "badge_bg": "#122d1e",
        "badge_border": "#23643d",
        "badge_fg": "#86efac",
        "times_bg": "#112219",
        "times_border": "#1c472e",
        "times_fg": "#b8e6c9",
        "bar_chunk": "#16a34a",
    },
    "failed": {
        "badge_bg": "#361619",
        "badge_border": "#84252d",
        "badge_fg": "#fca5a5",
        "times_bg": "#241214",
        "times_border": "#521c21",
        "times_fg": "#eab8bd",
        "bar_chunk": "#dc2626",
    },
}


def format_hms(seconds: float) -> str:
    """초 단위 경과 시간을 HH:MM:SS 문자열로 변환합니다."""
    total_sec = max(0, int(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _measure_text_width(text: str, base_font: QFont, point_size: float) -> int:
    """지정한 폰트 크기로 문자열이 차지하는 실제 픽셀 폭을 추정합니다."""
    font = QFont(base_font)
    font.setPointSizeF(point_size)
    fm = QFontMetrics(font)
    return fm.horizontalAdvance(text or "")


def _fit_font_to_width(
    widget: QWidget,
    text: str,
    max_width: int,
    base_pt: float = 9.0,
    min_pt: float = 7.0,
) -> tuple[str, int]:
    """
    max_width 내에서 가능한 가장 큰 폰트 크기를 찾고,
    필요 시 말줄임 처리된 문자열과 실제 차지 폭(px)을 반환합니다.
    """
    clean_text = text or ""
    font = QFont(widget.font())

    if max_width <= 4:
        font.setPointSizeF(min_pt)
        widget.setFont(font)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(clean_text) if clean_text else 0
        return clean_text, w

    chosen_pt = min_pt
    pt = base_pt
    while pt >= min_pt:
        if _measure_text_width(clean_text, font, pt) <= max_width:
            chosen_pt = pt
            break
        pt -= 0.5

    font.setPointSizeF(chosen_pt)
    widget.setFont(font)
    fm = QFontMetrics(font)
    raw_w = fm.horizontalAdvance(clean_text)

    if raw_w > max_width:
        elided = fm.elidedText(clean_text, Qt.TextElideMode.ElideRight, max_width)
        return elided, min(max_width, fm.horizontalAdvance(elided))

    return clean_text, raw_w


class _ExactFitLabel(QLabel):
    """실제 표시 문자열 폭을 추정해 겹침 없이 폭을 맞추는 라벨."""

    def __init__(
        self,
        text: str = "",
        base_pt: float = 9.0,
        min_pt: float = 7.0,
        h_pad: int = 12,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._full_text = text
        self._custom_tooltip: str = ""
        self._base_pt = base_pt
        self._min_pt = min_pt
        self._h_pad = h_pad
        self._preferred_width = 0
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def fullText(self) -> str:
        return self._full_text

    def setCustomTooltip(self, tip: str) -> None:
        self._custom_tooltip = tip or ""
        if self._custom_tooltip:
            super().setToolTip(self._custom_tooltip)
        else:
            super().setToolTip(self._full_text if self._full_text not in ("", "-") else "")

    def estimatedWidth(self) -> int:
        """현재 텍스트 기준 권장 가로 폭(여백 포함)을 반환합니다."""
        if not self._full_text:
            return 0
        w = _measure_text_width(self._full_text, self.font(), self._base_pt)
        return w + self._h_pad

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text or ""
        if not self._custom_tooltip:
            super().setToolTip(self._full_text if self._full_text not in ("", "-") else "")
        target_w = self.width() if self.width() > 0 else self.estimatedWidth()
        self.apply_budget(target_w)

    def apply_budget(self, budget_width: int) -> int:
        """할당된 budget_width 안에서 글자를 맞추고 실제 점유 폭을 반환합니다."""
        if not self._full_text or budget_width <= 0:
            self._preferred_width = 0
            self.setFixedWidth(0)
            super().setText("")
            return 0

        fitted_text, text_w = _fit_font_to_width(
            self,
            self._full_text,
            max(1, budget_width - self._h_pad),
            base_pt=self._base_pt,
            min_pt=self._min_pt,
        )
        used_w = min(budget_width, max(0, text_w + self._h_pad))
        self._preferred_width = used_w
        self.setFixedWidth(used_w)
        super().setText(fitted_text)
        return used_w


class BuildProgressBadge(QGroupBox):
    """
    한 줄 구성:
    [빌드 상태] [시작 / 소요 / 종료] [빌드 퍼센트(최대 가용폭)]
    """

    MIN_BAR_WIDTH = 70

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._init_ui()
        self.set_waiting()

    def _init_ui(self):
        self.setStyleSheet(
            """
            QGroupBox {
                background-color: #161a22;
                border: 1px solid #303744;
                border-radius: 4px;
                margin-top: 0px;
                padding: 3px 6px;
            }
            """
        )

        self._row_layout = QHBoxLayout(self)
        self._row_layout.setContentsMargins(2, 1, 2, 1)
        self._row_layout.setSpacing(6)

        # 1칸: 빌드 상태 배지 (대기중, 빌드중, 빌드완료, 빌드실패)
        self.lbl_status = _ExactFitLabel("대기중", base_pt=9.0, min_pt=7.5, h_pad=14)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        # 2칸: 시작 / 소요 / 종료 텍스트 배지
        self.lbl_times = _ExactFitLabel(
            "시작 - | 소요 00:00:00 | 종료 -",
            base_pt=8.5,
            min_pt=7.0,
            h_pad=16,
        )
        self.lbl_times.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # 3칸: 빌드 퍼센트 프로그레스 바 (남은 공간 최대 확보)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setMinimumWidth(self.MIN_BAR_WIDTH)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._row_layout.addWidget(self.lbl_status, 0)
        self._row_layout.addWidget(self.lbl_times, 0)
        self._row_layout.addWidget(self.progress_bar, 1)

    def _apply_state_theme(self, state_key: str) -> None:
        theme = _STATE_THEMES.get(state_key, _STATE_THEMES["waiting"])

        self.lbl_status.setStyleSheet(
            f"""
            QLabel {{
                background-color: {theme["badge_bg"]};
                border: 1px solid {theme["badge_border"]};
                border-radius: 3px;
                color: {theme["badge_fg"]};
                font-weight: 700;
                padding: 1px 5px;
            }}
            """
        )

        self.lbl_times.setStyleSheet(
            f"""
            QLabel {{
                background-color: {theme["times_bg"]};
                border: 1px solid {theme["times_border"]};
                border-radius: 3px;
                color: {theme["times_fg"]};
                padding: 1px 6px;
            }}
            """
        )

        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: #101318;
                border: 1px solid #303744;
                border-radius: 3px;
                color: #f8fafc;
                font-size: 9px;
                font-weight: 700;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {theme["bar_chunk"]};
                border-radius: 2px;
            }}
            """
        )

    def _recalc_widths(self) -> None:
        """표시될 텍스트 폭을 추정해 상태/시간 라벨 폭을 정하고 바 공간을 확보합니다."""
        inner_width = self.contentsRect().width()
        margins = self._row_layout.contentsMargins()
        avail = inner_width - margins.left() - margins.right()
        spacing = self._row_layout.spacing()

        status_est = self.lbl_status.estimatedWidth()
        times_est = self.lbl_times.estimatedWidth()

        if avail <= 0:
            self.lbl_status.apply_budget(status_est)
            self.lbl_times.apply_budget(times_est)
            self.progress_bar.setMinimumWidth(self.MIN_BAR_WIDTH)
            return

        # 3개 위젯(lbl_status, lbl_times, progress_bar) 사이 간격 수: 2개
        gap_count = 2
        total_spacing = spacing * gap_count
        max_text_budget = max(0, avail - total_spacing - self.MIN_BAR_WIDTH)

        if status_est + times_est <= max_text_budget:
            status_budget = status_est
            times_budget = times_est
        else:
            status_budget = min(status_est, max_text_budget)
            times_budget = min(times_est, max(0, max_text_budget - status_budget))

        self.lbl_status.apply_budget(status_budget)
        self.lbl_times.apply_budget(times_budget)
        self.progress_bar.setMinimumWidth(self.MIN_BAR_WIDTH)
        self._row_layout.invalidate()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._recalc_widths()

    def set_waiting(
        self,
        start_time: str = "-",
        elapsed_str: str = "00:00:00",
        end_time: str = "-",
        percent: int = 0,
    ):
        self._apply_state_theme("waiting")
        self.lbl_status.setCustomTooltip("")
        self.lbl_status.setText("대기중")
        self.lbl_times.setText(f"시작 {start_time} | 소요 {elapsed_str} | 종료 {end_time}")
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        self._recalc_widths()

    def set_building(
        self,
        percent: int,
        start_time: str,
        elapsed_str: str = "00:00:00",
        end_time: str = "-",
        detail: str = "",
    ):
        self._apply_state_theme("building")
        self.lbl_status.setCustomTooltip(f"빌드중 ({detail})" if detail else "빌드중")
        self.lbl_status.setText("빌드중")
        self.lbl_times.setText(f"시작 {start_time} | 소요 {elapsed_str} | 종료 {end_time}")
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        self._recalc_widths()

    def set_completed(
        self,
        success: bool,
        start_time: str,
        elapsed_str: str,
        end_time: str,
        percent: int = 100,
    ):
        state_key = "success" if success else "failed"
        self._apply_state_theme(state_key)
        self.lbl_status.setCustomTooltip("")
        self.lbl_status.setText("빌드완료" if success else "빌드실패")
        self.lbl_times.setText(f"시작 {start_time} | 소요 {elapsed_str} | 종료 {end_time}")
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        self._recalc_widths()
