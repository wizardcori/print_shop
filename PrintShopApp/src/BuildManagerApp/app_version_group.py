from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
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
BUTTON_H_PAD_PX: int = 12

META_LABEL_BASE_PT: float = 10.0
META_LABEL_MIN_PT: float = 8.0
CARD_MIN_HEIGHT_PX: int = 165
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
LABEL_PREV_RUN: str = "이전 실행"
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
    """이전버전 또는 이후버전 영역(헤더 컨트롤 + 메타데이터 그리드)을 표시하는 서브 그룹."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        self._value_labels: dict[str, AutoFitLabel] = {}
        self._key_labels: list[AutoFitLabel] = []
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._init_ui()
        self.clear_info(STATUS_UNCHECKED)

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 12, 6, 6)
        outer_layout.setSpacing(5)

        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(5)
        outer_layout.addLayout(self.header_layout)

        self._divider = QFrame(self)
        self._divider.setFrameShape(QFrame.Shape.HLine)
        self._divider.setStyleSheet("background-color: #2b313c; max-height: 1px; border: none;")
        self._divider.setVisible(False)
        outer_layout.addWidget(self._divider)

        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(6)
        grid_layout.setVerticalSpacing(2)
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        for r, (key, caption) in enumerate(META_ROW_SPECS):
            lbl_k = AutoFitLabel(
                f"{caption}:", base_pt=META_LABEL_BASE_PT, min_pt=META_LABEL_MIN_PT
            )
            lbl_k.setStyleSheet("color: #9aa0a6;")
            lbl_k.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

            lbl_v = AutoFitLabel(
                EMPTY_VALUE_STR, base_pt=META_LABEL_BASE_PT, min_pt=META_LABEL_MIN_PT
            )
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_v.setStyleSheet("color: #e8eaed; font-weight: 500;")

            grid_layout.addWidget(lbl_k, r, 0)
            grid_layout.addWidget(lbl_v, r, 1)
            self._key_labels.append(lbl_k)
            self._value_labels[key] = lbl_v

        outer_layout.addLayout(grid_layout, stretch=1)

    def add_header_widget(self, widget: QWidget, stretch: int = 0) -> None:
        """패널 상단 헤더 행에 위젯을 추가하고 구분선을 활성화합니다."""
        self.header_layout.addWidget(widget, stretch=stretch)
        self._divider.setVisible(True)

    def clear_info(self, version_status: str = STATUS_NO_INFO) -> None:
        for k, lbl in self._value_labels.items():
            lbl.setText(version_status if k == "version" else EMPTY_VALUE_STR)
            lbl.setToolTip("")

    def update_from_decrypt_result(
        self, result: dict[str, Any] | None, empty_msg: str = STATUS_NO_EXE
    ) -> None:
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
    """앱 1개 단위 카드 위젯."""

    open_location_requested = Signal(str)
    open_prev_dir_requested = Signal(str)
    run_prev_requested = Signal(str)
    prev_log_emitted = Signal(str, str)  # (target_key, log_message)

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
        self._prev_artifact_path: str = ""
        self._fallback_location_path: str = ""
        self._extracted_temp_dirs: list[Path] = []
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._init_ui()

    def _emit_prev_log(self, message: str) -> None:
        formatted = f"[{self.display_name}] {message}"
        print(formatted)
        self.prev_log_emitted.emit(self.key, formatted)

    def _init_ui(self) -> None:
        self.setMinimumHeight(CARD_MIN_HEIGHT_PX)
        self.setStyleSheet("""
            QGroupBox {
                background-color: #15181e;
                border: 1px solid #2b313c;
                border-radius: 5px;
                margin-top: 2px;
                padding: 4px;
            }
            """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

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

        self.checkbox = AutoFitCheckBox(
            "",
            base_pt=CARD_CHECKBOX_BASE_PT,
            min_pt=CARD_CHECKBOX_MIN_PT,
            indicator_reserve_px=CARD_CHECKBOX_RESERVE_PX,
            allow_elide=False,
            parent=self.prev_box,
        )
        self.checkbox.setFixedWidth(20)
        self.checkbox.setToolTip(f"{self.label_text} 빌드 대상 선택")
        self.checkbox.setStyleSheet("""
            QCheckBox {
                spacing: 0px;
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
            """)

        prev_dir_btn_style = """
            QPushButton {
                background-color: #202632;
                color: #f1f3f4;
                border: 1px solid #384357;
                border-radius: 3px;
                padding: 2px 8px;
                font-weight: 600;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #2b3548;
                border-color: #5b8def;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #19202b;
            }
            QPushButton:disabled {
                color: #6b7280;
                border-color: #262c36;
                background-color: #171b22;
            }
        """

        run_btn_style = """
            QPushButton {
                background-color: #1d3528;
                color: #8ce99a;
                border: 1px solid #2f5e44;
                border-radius: 3px;
                padding: 2px 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #254634;
                border-color: #40916c;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #16291f;
            }
            QPushButton:disabled {
                color: #6b7280;
                border-color: #262c36;
                background-color: #171b22;
            }
        """

        self.btn_open_prev_dir = AutoFitButton(
            self.label_text,
            base_pt=BUTTON_BASE_PT,
            min_pt=BUTTON_MIN_PT,
            h_pad=BUTTON_H_PAD_PX,
            parent=self.prev_box,
        )
        self.btn_open_prev_dir.setToolTip("이전버전 폴더 열기")
        self.btn_open_prev_dir.setStyleSheet(prev_dir_btn_style)
        self.btn_open_prev_dir.clicked.connect(self._on_open_prev_dir_clicked)

        self.btn_open_loc = self.btn_open_prev_dir

        self.btn_run_prev = AutoFitButton(
            LABEL_PREV_RUN,
            base_pt=BUTTON_BASE_PT,
            min_pt=BUTTON_MIN_PT,
            h_pad=BUTTON_H_PAD_PX,
            parent=self.prev_box,
        )
        self.btn_run_prev.setToolTip("이전버전 실행")
        self.btn_run_prev.setStyleSheet(run_btn_style)
        self.btn_run_prev.setEnabled(False)
        self.btn_run_prev.clicked.connect(self._on_run_prev_clicked)

        self.prev_box.add_header_widget(self.checkbox, stretch=0)
        self.prev_box.add_header_widget(self.btn_open_prev_dir, stretch=4)
        self.prev_box.add_header_widget(self.btn_run_prev, stretch=1)

        self.progress_badge = BuildProgressBadge(self.next_box)

        self.chk_bump = AutoFitCheckBox(
            LABEL_BUMP_CHECKBOX,
            base_pt=CARD_BUMP_BASE_PT,
            min_pt=CARD_BUMP_MIN_PT,
            indicator_reserve_px=CARD_BUMP_RESERVE_PX,
            allow_elide=False,
            parent=self.next_box,
        )
        self.chk_bump.setToolTip("체크 시 해당 개별 앱의 버전을 증가시킨 뒤 빌드합니다.")
        self.chk_bump.setMinimumWidth(CARD_BUMP_MIN_WIDTH_PX)
        self.chk_bump.setStyleSheet("""
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
            """)

        self.next_box.add_header_widget(self.progress_badge, stretch=4)
        self.next_box.add_header_widget(self.chk_bump, stretch=0)

        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(0, 0, 0, 0)
        ver_row.setSpacing(6)
        ver_row.addWidget(self.prev_box, stretch=1)
        ver_row.addWidget(self.next_box, stretch=1)
        outer.addLayout(ver_row, stretch=1)

    def _resolve_prev_dir(self) -> Path | None:
        exe_raw = (self._prev_artifact_path or "").strip()
        if exe_raw:
            p = Path(exe_raw)
            target_dir = p.parent if p.suffix else p
            if target_dir.exists():
                return target_dir
            if p.parent.exists():
                return p.parent

        fallback_raw = (self._fallback_location_path or "").strip()
        if fallback_raw:
            fp = Path(fallback_raw)
            return fp.parent if fp.is_file() else fp

        return None

    def _refresh_prev_action_states(self) -> None:
        prev_dir = self._resolve_prev_dir()
        if prev_dir is not None:
            self.btn_open_prev_dir.setEnabled(True)
            self.btn_open_prev_dir.setToolTip(f"이전버전 폴더 열기:\n{prev_dir}")
        else:
            self.btn_open_prev_dir.setEnabled(False)
            self.btn_open_prev_dir.setToolTip("열 수 있는 이전버전 폴더가 없습니다.")

        exe_raw = (self._prev_artifact_path or "").strip()
        exe_path = Path(exe_raw) if exe_raw else None
        is_valid_file = exe_path is not None and exe_path.is_file()
        suffix = exe_path.suffix.lower() if exe_path is not None else ""
        can_run = is_valid_file and suffix in (".exe", ".zip")

        self.btn_run_prev.setEnabled(can_run)
        if can_run and exe_path is not None:
            if suffix == ".zip":
                self.btn_run_prev.setToolTip(f"ZIP을 메모리에 읽어 풀어 실행:\n{exe_path}")
            else:
                self.btn_run_prev.setToolTip(f"이전버전 실행:\n{exe_path}")
        else:
            self.btn_run_prev.setToolTip("실행 가능한 이전버전 EXE/ZIP이 없습니다.")

    def _extract_zip_from_memory_and_launch(self, zip_path: Path) -> Path | None:
        """ZIP 파일 바이트를 메모리로 읽은 뒤 임시 폴더에 압축을 해제하고 실행할 EXE 경로를 반환합니다."""
        self._emit_prev_log(f"압축해제 시작: 원본='{zip_path}'")
        zip_bytes = zip_path.read_bytes()
        mem_buf = io.BytesIO(zip_bytes)
        temp_root = Path(tempfile.mkdtemp(prefix=f"{self.target_name}_prev_"))
        self._extracted_temp_dirs.append(temp_root)

        exe_candidates: list[Path] = []
        extracted_count = 0
        with zipfile.ZipFile(mem_buf, mode="r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                target_file = (temp_root / member.filename).resolve()
                if not str(target_file).startswith(str(temp_root.resolve())):
                    raise ValueError(f"안전하지 않은 ZIP 경로 차단: {member.filename}")
                target_file.parent.mkdir(parents=True, exist_ok=True)
                data = zf.read(member.filename)
                target_file.write_bytes(data)
                extracted_count += 1
                if target_file.suffix.lower() == ".exe":
                    exe_candidates.append(target_file)

        self._emit_prev_log(
            f"압축해제 완료: 원본='{zip_path}' -> 대상폴더='{temp_root}' ({extracted_count}개 파일)"
        )

        if not exe_candidates:
            self._emit_prev_log(
                f"실행 실패: 압축 해제된 폴더('{temp_root}')에 EXE 파일이 없습니다."
            )
            return None

        preferred = [p for p in exe_candidates if self.target_name.lower() in p.stem.lower()]
        return preferred[0] if preferred else exe_candidates[0]

    def _spawn_process(self, exe_path: Path) -> None:
        self._emit_prev_log(f"실행: '{exe_path}'")
        if sys.platform.startswith("win"):
            subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), start_new_session=True)

    def _on_open_prev_dir_clicked(self) -> None:
        target_dir = self._resolve_prev_dir()
        if target_dir is not None:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                self._emit_prev_log(f"폴더 생성 실패: '{target_dir}' ({exc})")
            if target_dir.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))
        # self.open_location_requested.emit(self.key)
        self.open_prev_dir_requested.emit(self.key)

    def _on_run_prev_clicked(self) -> None:
        exe_raw = (self._prev_artifact_path or "").strip()
        if not exe_raw:
            self._emit_prev_log("실행 실패: 이전버전 경로가 비어 있습니다.")
            return
        artifact_path = Path(exe_raw)
        if not artifact_path.is_file():
            self._emit_prev_log(f"실행 실패: 파일을 찾을 수 없습니다 ('{artifact_path}').")
            return

        suffix = artifact_path.suffix.lower()
        if suffix == ".zip":
            launched_exe = self._extract_zip_from_memory_and_launch(artifact_path)
            if launched_exe is not None and launched_exe.is_file():
                self._spawn_process(launched_exe)
                self.run_prev_requested.emit(self.key)
        elif suffix == ".exe":
            self._spawn_process(artifact_path)
            self.run_prev_requested.emit(self.key)
        else:
            self._emit_prev_log(f"실행 실패: 지원하지 않는 파일 형식입니다 ('{artifact_path}').")

    def set_location_tooltip(self, path_str: str | None) -> None:
        self._fallback_location_path = (path_str or "").strip()
        self._refresh_prev_action_states()

    def is_build_checked(self) -> bool:
        return self.checkbox.isChecked()

    def is_bump_checked(self) -> bool:
        return self.chk_bump.isChecked()

    def set_bump_checked(self, checked: bool, block_signals: bool = False) -> None:
        if block_signals:
            self.chk_bump.blockSignals(True)
        self.chk_bump.setChecked(checked)
        if block_signals:
            self.chk_bump.blockSignals(False)

    def set_prev_meta(self, result: dict[str, Any] | None) -> None:
        source_label = ""
        exe_path = ""
        if isinstance(result, dict):
            source_label = str(
                result.get("_source_label") or (result.get("items") or {}).get("source") or ""
            ).strip()
            exe_path = str(result.get("_exe_path") or "").strip()

        self._prev_artifact_path = exe_path

        if hasattr(self, "prev_box") and hasattr(self.prev_box, "setTitle"):
            self.prev_box.setTitle(
                f"이전버전 ({source_label})" if source_label else TITLE_PREV_VERSION_DEFAULT
            )

        self.prev_box.update_from_decrypt_result(result, empty_msg=STATUS_NO_PREV_EXE)
        self._refresh_prev_action_states()

    def set_next_meta(self, result: dict[str, Any] | None) -> None:
        self.next_box.update_from_decrypt_result(result, empty_msg=STATUS_NO_NEXT_EXE)

    def clear_next_meta(self, status_msg: str = "") -> None:
        self.next_box.clear_info(status_msg)
