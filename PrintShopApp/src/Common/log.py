from __future__ import annotations

import ast
import inspect
import logging
import logging.handlers
import os
import queue
import time
import warnings
import weakref
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import colorlog
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# from Common.log_config import LogConfig, log_config_instance
from Common.path_mgr import PathMgr

try:
    from shiboken6 import isValid as _qt_is_valid  # type: ignore
except Exception:

    def _qt_is_valid(_obj: Any) -> bool:
        return True


DEFAULT_LOG_FILE = "system.log"
DEFAULT_LOG_ALL_FILE = "log_all.log"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_TAG_WIDTH = 12  # [PRIO_QUEUE] 기준 10자 + 여유 2자
DEFAULT_LOG_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}
FALLBACK_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(fixed_path)s | [%(fixed_tag)s] | %(message)s"
)

COLOR_NAME_TO_HEX: dict[str, str] = {
    "black": "#343a40",
    "red": "#ff6b6b",
    "green": "#51cf66",
    "yellow": "#fcc419",
    "blue": "#4dabf7",
    "purple": "#cc5de8",
    "magenta": "#cc5de8",
    "cyan": "#3bc9db",
    "white": "#f8f9fa",
    "light_gray": "#adb5bd",
    "dark_gray": "#868e96",
}


def parse_color_spec(color_spec: str) -> tuple[str | None, bool]:
    """'bold_red', 'cyan' 등을 (hex_str, is_bold)로 파싱합니다."""
    raw = (color_spec or "").strip().lower()
    is_bold = False

    if raw.startswith("bold_"):
        is_bold = True
        raw = raw[len("bold_") :]

    hex_color = COLOR_NAME_TO_HEX.get(raw)
    return hex_color, is_bold


from PySide6.QtGui import QColor, QFont, QTextCharFormat


def _build_format_from_color_spec(color_spec: str) -> QTextCharFormat:
    fmt = QTextCharFormat()
    hex_color, is_bold = parse_color_spec(color_spec)

    if hex_color is not None:
        fmt.setForeground(QColor(hex_color))
    if is_bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    return fmt


# _COLOR_NAME_TO_QCOLOR: dict[str, QColor] = {
#     "black": QColor("#343a40"),
#     "red": QColor("#ff6b6b"),
#     "green": QColor("#51cf66"),
#     "yellow": QColor("#fcc419"),
#     "blue": QColor("#4dabf7"),
#     "purple": QColor("#cc5de8"),
#     "magenta": QColor("#cc5de8"),
#     "cyan": QColor("#3bc9db"),
#     "white": QColor("#f8f9fa"),
#     "light_gray": QColor("#adb5bd"),
#     "dark_gray": QColor("#868e96"),
# }

# def _build_format_from_color_spec(color_spec: str) -> QTextCharFormat:
#     fmt = QTextCharFormat()
#     raw = (color_spec or "").strip().lower()
#     is_bold = False

#     if raw.startswith("bold_"):
#         is_bold = True
#         raw = raw[len("bold_") :]

#     qcolor = _COLOR_NAME_TO_QCOLOR.get(raw)
#     if qcolor is not None:
#         fmt.setForeground(qcolor)
#     if is_bold:
#         fmt.setFontWeight(QFont.Weight.Bold)
#     return fmt


# ==============================================================================
# 1. 태그 및 파일별 태그 관리자
# ==============================================================================
class LogTag:
    SYSTEM = "SYSTEM"
    DATABASE = "DB"
    NETWORK = "NET"
    SECURITY = "SEC"
    USER = "USER"
    DEFAULT = "DEFAULT"

    def __init__(self, name: str) -> None:
        self.name = str(name).upper()

    def __str__(self) -> str:
        return self.name


class FileTagManager:
    """파일(모듈)별 기본 로그 태그 및 레벨/모듈 활성화 맵을 소유하는 관리 클래스."""

    _file_default_tags: dict[str, list[str]] = {}

    _level_enabled: dict[str, bool] = {
        "DEBUG": True,
        "INFO": True,
        "WARNING": True,
        "ERROR": True,
        "CRITICAL": True,
    }

    _module_enabled: dict[str, bool] = {
        "SYSTEM": True,
        "DB": True,
        "NET": True,
        "SEC": True,
        "USER": True,
        "DEFAULT": True,
    }

    @classmethod
    def get_level_enabled(cls) -> dict[str, bool]:
        return cls._level_enabled

    @classmethod
    def get_module_enabled(cls) -> dict[str, bool]:
        return cls._module_enabled

    @classmethod
    def set_level_enabled(cls, level_cfg: dict[str, bool]) -> None:
        if isinstance(level_cfg, dict):
            cls._level_enabled.update(level_cfg)

    @classmethod
    def set_module_enabled(cls, module_cfg: dict[str, bool]) -> None:
        if isinstance(module_cfg, dict):
            cls._module_enabled.update(module_cfg)

    @classmethod
    def _normalize_path(cls, path: str) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(path)))

    @classmethod
    def set_file_tag(cls, *tags: Any) -> None:
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        try:
            if caller is None:
                return
            filename = cls._normalize_path(caller.f_code.co_filename)
            upper_tags = [str(t).upper() for t in tags if str(t).strip()]

            cls._file_default_tags[filename] = upper_tags
            for tag in upper_tags:
                if tag not in cls._module_enabled:
                    cls._module_enabled[tag] = True
        finally:
            del frame
            del caller

    @classmethod
    def get_current_file_mods(cls, default_tag: Any) -> list[str]:
        frame = inspect.currentframe()
        cur = frame.f_back if frame is not None else None
        try:
            depth = 0
            while cur is not None and depth < 8:
                filename = cls._normalize_path(cur.f_code.co_filename)
                if filename in cls._file_default_tags:
                    return cls._file_default_tags[filename]
                cur = cur.f_back
                depth += 1
        finally:
            del frame
            del cur

        if isinstance(default_tag, (list, tuple)):
            return [str(t).upper() for t in default_tag]
        return [str(default_tag).upper()]


set_file_tag = FileTagManager.set_file_tag


# ==============================================================================
# 2. 커스텀 포맷터 및 파일 핸들러
# ==============================================================================
def _format_fixed_tag(raw_tag: str, width: int = DEFAULT_TAG_WIDTH) -> str:
    tag_str = str(raw_tag or LogTag.DEFAULT).strip() or LogTag.DEFAULT
    w = max(4, int(width))
    if len(tag_str) > w:
        tag_str = "..." + tag_str[-(w - 3) :]
    return f"{tag_str:<{w}}"


def _populate_record_location_and_tag(record: logging.LogRecord) -> None:
    """CustomLogFormatter / CustomColoredFormatter 공통 레코드 필드 보정."""
    if not hasattr(record, "tag") or not getattr(record, "tag"):
        record.tag = LogTag.DEFAULT
    from Common.log_config import log_config_instance

    path_style = log_config_instance.get("path_style")
    fixed_width = log_config_instance.get("fixed_width_size")
    do_tabular = bool(log_config_instance.get("enable_tabular_alignment"))

    tag_width = DEFAULT_TAG_WIDTH
    try:
        raw_tag_width = log_config_instance.get("tag_width_size")
        if raw_tag_width is not None:
            tag_width = int(raw_tag_width)
    except Exception:
        tag_width = DEFAULT_TAG_WIDTH

    raw_tag_str = str(record.tag)
    if do_tabular:
        fixed_tag_str = _format_fixed_tag(raw_tag_str, tag_width)
        record.fixed_tag = fixed_tag_str
        record.tag = fixed_tag_str
    else:
        record.fixed_tag = raw_tag_str

    try:
        fixed_width_int = int(fixed_width) if fixed_width is not None else 50
    except Exception:
        fixed_width_int = 50
    fixed_width_int = max(12, fixed_width_int)

    path_str = getattr(record, "pathname", "")
    if path_style == "relative" and path_str:
        try:
            path_str = os.path.relpath(path_str, os.getcwd())
        except Exception:
            pass

    lineno = getattr(record, "lineno", "")
    loc_str = f"{path_str}:{lineno}" if lineno else str(path_str)

    if do_tabular or path_style == "fixed":
        if len(loc_str) > fixed_width_int:
            loc_str = "..." + loc_str[-(fixed_width_int - 3) :]
        record.fixed_path = f"{loc_str:<{fixed_width_int}}"
    else:
        record.fixed_path = loc_str


def _resolve_safe_format_string() -> str:
    """log_config_instance에서 포맷 문자열을 조회하고 비어 있으면 기본 포맷을 반환."""
    try:
        from Common.log_config import log_config_instance

        fmt = log_config_instance.build_format_string()
        if isinstance(fmt, str) and fmt.strip():
            return fmt
    except Exception:
        pass
    return FALLBACK_LOG_FORMAT


class CustomLogFormatter(logging.Formatter):
    """[노컬러 포맷터] 상대경로 및 고정폭 패딩을 적용하여 런타임 정렬 수행."""

    def format(self, record: logging.LogRecord) -> str:
        _populate_record_location_and_tag(record)
        return super().format(record)


class CustomColoredFormatter(colorlog.ColoredFormatter):
    """[컬러 포맷터] 콘솔 및 컬러 파일용 정렬 수행."""

    def format(self, record: logging.LogRecord) -> str:
        _populate_record_location_and_tag(record)
        return super().format(record)


class PeriodicFlushFileHandler(logging.FileHandler):
    """주기적으로 파일 버퍼를 플러시하는 FileHandler."""

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        encoding: str | None = "utf-8",
        delay: bool = False,
        flush_interval: float = 5.0,
    ) -> None:
        super().__init__(filename, mode, encoding, delay)
        self.flush_interval = flush_interval
        self.last_flush_time = time.time()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
            current_time = time.time()
            if current_time - self.last_flush_time >= self.flush_interval:
                self.flush()
                self.last_flush_time = current_time
        except Exception:
            self.handleError(record)

    def force_flush(self) -> None:
        try:
            self.flush()
            self.last_flush_time = time.time()
        except Exception:
            pass


# ==============================================================================
# 3. 윈도우 로그 핸들러 Base 및 검증 유틸리티
# ==============================================================================
def _is_qt_object_alive(obj: Any) -> bool:
    """Qt/C++ 객체가 아직 살아 있고 접근 가능한지 확인."""
    if obj is None:
        return False
    if not _qt_is_valid(obj):
        return False
    try:
        _ = obj.objectName()
        return True
    except RuntimeError:
        return False


def _validate_window_object(owner_window: Any, *, require_top_level: bool = False) -> QWidget:
    """등록 대상 객체가 유효하고 살아 있는 Qt 윈도우(QWidget)인지 검증."""
    if owner_window is None:
        raise ValueError("핸들러 등록 대상 윈도우(owner_window)가 None일 수 없습니다.")
    if not isinstance(owner_window, QWidget):
        raise TypeError(
            f"owner_window는 QWidget(윈도우) 인스턴스여야 합니다. 전달된 타입: {type(owner_window).__name__}"
        )
    if not _is_qt_object_alive(owner_window):
        raise RuntimeError("owner_window가 이미 소멸되었거나 유효하지 않은 Qt 객체입니다.")
    if require_top_level and not owner_window.isWindow():
        raise ValueError(
            f"owner_window는 최상위 윈도우여야 합니다(isWindow() == False): {type(owner_window).__name__}"
        )
    return owner_window


def _validate_log_widget(log_widget: Any) -> Any:
    """로그를 표시할 위젯이 유효하고 텍스트 추가 메서드를 지원하는지 검증."""
    if log_widget is None:
        raise ValueError("log_widget이 None일 수 없습니다.")
    if not isinstance(log_widget, QObject):
        raise TypeError(
            f"log_widget은 Qt 객체(QObject)여야 합니다. 전달된 타입: {type(log_widget).__name__}"
        )
    if not _is_qt_object_alive(log_widget):
        raise RuntimeError("log_widget이 이미 소멸되었거나 유효하지 않습니다.")
    if not (
        isinstance(log_widget, (QPlainTextEdit, QTextEdit))
        or callable(getattr(log_widget, "appendPlainText", None))
        or callable(getattr(log_widget, "append", None))
    ):
        raise TypeError(
            f"log_widget은 appendPlainText 또는 append 메서드를 지원해야 합니다: {type(log_widget).__name__}"
        )
    return log_widget


def _normalize_log_level(level: int | str) -> int:
    """로그 레벨 인자를 검증하고 정수 레벨로 정규화."""
    if isinstance(level, bool):
        raise TypeError("level은 bool 값이 될 수 없습니다.")
    if isinstance(level, int):
        return logging._checkLevel(level)
    if isinstance(level, str):
        stripped = level.strip().upper()
        if not stripped:
            raise ValueError("level 문자열이 비어 있을 수 없습니다.")
        if stripped.isdigit():
            return logging._checkLevel(int(stripped))
        return logging._checkLevel(stripped)
    raise TypeError(f"지원하지 않는 level 타입입니다: {type(level).__name__}")


class _LogTextRelay(QObject):
    """백그라운드/워커 스레드 로그 문자열을 메인 스레드로 전달하는 릴레이."""

    line_ready = Signal(str)


class WindowLogHandlerBase(CustomLogFormatter, logging.Handler):
    """
    윈도우 멤버 객체로 생성해 사용하는 GUI 로그 핸들러 Base 클래스.
    - Common.log 포맷(CustomLogFormatter / log_config_instance)을 그대로 적용합니다.
    - owner_window와 log_widget을 weakref로만 참조하므로 명시적 해제가 없어도 안전합니다.
    - 활성 핸들러 레지스트리에 등록되어 포맷 변경 및 로그 재오픈 시 함께 갱신됩니다.
    """

    _active_handlers: list[weakref.ref[WindowLogHandlerBase]] = []

    def __init__(
        self,
        owner_window: QWidget,
        log_widget: Any,
        level: int | str = logging.DEBUG,
        datefmt: str = DEFAULT_DATE_FORMAT,
        require_top_level: bool = False,
    ) -> None:
        valid_window = _validate_window_object(owner_window, require_top_level=require_top_level)
        valid_widget = _validate_log_widget(log_widget)
        normalized_level = _normalize_log_level(level)

        if not isinstance(datefmt, str) or not datefmt.strip():
            datefmt = DEFAULT_DATE_FORMAT

        fmt = _resolve_safe_format_string()
        CustomLogFormatter.__init__(self, fmt, datefmt=datefmt)
        logging.Handler.__init__(self, level=normalized_level)

        self._owner_ref: weakref.ref[QWidget] = weakref.ref(valid_window)
        self._widget_ref: weakref.ref[Any] = weakref.ref(valid_widget)
        self._targets: list[logging.Logger] = []
        self._detached = False

        relay_parent = QApplication.instance()
        self._relay = _LogTextRelay(relay_parent)
        self._relay.line_ready.connect(self._append_to_widget)
        self._line_ready_connected = True

        WindowLogHandlerBase._register_instance(self)

    @classmethod
    def _register_instance(cls, handler: WindowLogHandlerBase) -> None:
        cls._prune_dead_refs()
        cls._active_handlers.append(weakref.ref(handler))

    @classmethod
    def _prune_dead_refs(cls) -> None:
        alive: list[weakref.ref[WindowLogHandlerBase]] = []
        for ref in cls._active_handlers:
            inst = ref()
            if inst is not None and not inst._detached:
                alive.append(ref)
        cls._active_handlers = alive

    @classmethod
    def refresh_all_formats(cls) -> None:
        """모든 활성 WindowLogHandlerBase 인스턴스의 포맷을 갱신."""
        cls._prune_dead_refs()
        for ref in list(cls._active_handlers):
            inst = ref()
            if inst is not None:
                inst.refresh_format()

    @classmethod
    def reattach_all_to_loggers(cls, loggers: Iterable[logging.Logger]) -> None:
        """로그 재오픈(reopen_global_log) 후 생존한 핸들러들을 새 로거들에 재연결."""
        cls._prune_dead_refs()
        valid_loggers = [lg for lg in loggers if isinstance(lg, logging.Logger)]
        for ref in list(cls._active_handlers):
            inst = ref()
            if inst is None:
                continue
            if not inst._is_target_alive():
                inst.detach()
                continue
            inst._targets = [lg for lg in inst._targets if isinstance(lg, logging.Logger)]
            for lg in valid_loggers:
                if lg not in inst._targets:
                    inst._targets.append(lg)
                if inst not in lg.handlers:
                    lg.addHandler(inst)

    def refresh_format(self) -> None:
        """log_config_instance 포맷 설정 변경 시 핸들러 포맷을 갱신."""
        if self._detached:
            return
        fmt = _resolve_safe_format_string()
        self._fmt = fmt
        if hasattr(self, "_style") and hasattr(self._style, "_fmt"):
            self._style._fmt = fmt

    def _is_target_alive(self) -> bool:
        if self._detached:
            return False
        owner = self._owner_ref()
        widget = self._widget_ref()
        if not _is_qt_object_alive(owner) or not _is_qt_object_alive(widget):
            return False
        return True

    def _append_to_widget(self, text: str) -> None:
        if not isinstance(text, str):
            return
        if not self._is_target_alive():
            self.detach()
            return

        widget = self._widget_ref()
        if widget is None:
            self.detach()
            return

        try:
            if isinstance(widget, QPlainTextEdit):
                widget.appendPlainText(text)
            elif isinstance(widget, QTextEdit):
                widget.append(text)
            elif callable(getattr(widget, "appendPlainText", None)):
                widget.appendPlainText(text)
            elif callable(getattr(widget, "append", None)):
                widget.append(text)
        except RuntimeError:
            self.detach()

    def attach_to_loggers(self, loggers: Iterable[logging.Logger]) -> list[logging.Logger]:
        """유효한 Logger 인스턴스만 검증하여 핸들러를 연결."""
        if self._detached:
            raise RuntimeError("이미 분리(detach)된 핸들러에는 로거를 연결할 수 없습니다.")
        if not self._is_target_alive():
            self.detach()
            raise RuntimeError("연결 대상 윈도우 또는 로그 위젯이 이미 소멸되었습니다.")
        if isinstance(loggers, (str, bytes)) or not isinstance(loggers, Iterable):
            raise TypeError("loggers는 Logger 객체들의 반복 가능(Iterable) 컬렉션이어야 합니다.")

        attached: list[logging.Logger] = []
        for lg in loggers:
            if not isinstance(lg, logging.Logger):
                raise TypeError(f"유효하지 않은 Logger 객체입니다: {type(lg).__name__}")
            if lg not in self._targets:
                self._targets.append(lg)
            if self not in lg.handlers:
                lg.addHandler(self)
                attached.append(lg)
        return attached

    def _disconnect_signal_safely(self, signal: Any, slot: Any, relay_obj: Any) -> None:
        if signal is None or not _is_qt_object_alive(relay_obj):
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                signal.disconnect(slot)
            except Exception:
                pass

    def detach(self) -> None:
        """연결된 로거에서 핸들러를 안전하게 제거(여러 번 호출해도 안전)."""
        if self._detached:
            self._targets.clear()
            return
        self._detached = True

        for lg in self._targets:
            try:
                if isinstance(lg, logging.Logger) and self in lg.handlers:
                    lg.removeHandler(self)
            except Exception:
                pass
        self._targets.clear()

        if getattr(self, "_line_ready_connected", False):
            self._line_ready_connected = False
            relay = getattr(self, "_relay", None)
            self._disconnect_signal_safely(
                getattr(relay, "line_ready", None),
                self._append_to_widget,
                relay,
            )

    def emit(self, record: logging.LogRecord) -> None:
        if not isinstance(record, logging.LogRecord):
            return
        if not self._is_target_alive():
            self.detach()
            return
        try:
            msg = self.format(record)
            self._relay.line_ready.emit(msg)
        except RuntimeError:
            self.detach()
        except Exception:
            self.handleError(record)


class _ColorLogTextRelay(QObject):
    """컬러 로그 문자열과 로그 레벨을 메인 스레드로 전달하는 릴레이."""

    line_ready = Signal(str, int)


class WindowLogColorHandlerBase(WindowLogHandlerBase):
    """
    DEFAULT_LOG_COLORS를 상속하고 추가/재정의 색상을 지원하는 GUI 컬러 로그 핸들러.
    """

    default_log_colors: dict[str, str] = dict(DEFAULT_LOG_COLORS)

    def __init__(
        self,
        owner_window: QWidget,
        log_widget: Any,
        level: int | str = logging.DEBUG,
        datefmt: str = DEFAULT_DATE_FORMAT,
        require_top_level: bool = False,
        log_colors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            owner_window=owner_window,
            log_widget=log_widget,
            level=level,
            datefmt=datefmt,
            require_top_level=require_top_level,
        )
        self._log_colors: dict[str, str] = self._merge_log_colors(log_colors)
        fmt = _resolve_safe_format_string()
        logging.Formatter.__init__(self, fmt, datefmt=datefmt)

        if getattr(self, "_line_ready_connected", False):
            self._line_ready_connected = False
            relay = getattr(self, "_relay", None)
            self._disconnect_signal_safely(
                getattr(relay, "line_ready", None),
                self._append_to_widget,
                relay,
            )

        relay_parent = QApplication.instance()
        self._color_relay = _ColorLogTextRelay(relay_parent)
        self._color_relay.line_ready.connect(self._append_colored_to_widget)
        self._color_line_ready_connected = True

    @classmethod
    def _merge_log_colors(cls, extra_colors: dict[str, str] | None) -> dict[str, str]:
        merged: dict[str, str] = dict(DEFAULT_LOG_COLORS)
        cls_colors = getattr(cls, "default_log_colors", None)
        if isinstance(cls_colors, dict):
            for k, v in cls_colors.items():
                if isinstance(k, str) and isinstance(v, str) and k.strip():
                    merged[k.strip().upper()] = v.strip()
        if isinstance(extra_colors, dict):
            for k, v in extra_colors.items():
                if isinstance(k, str) and isinstance(v, str) and k.strip():
                    merged[k.strip().upper()] = v.strip()
        return merged

    def set_log_colors(
        self, extra_colors: dict[str, str], *, reset_to_default: bool = False
    ) -> None:
        """기존 색상을 유지하거나 초기화한 뒤 추가/재정의 색상을 반영."""
        base = dict(DEFAULT_LOG_COLORS) if reset_to_default else dict(self._log_colors)
        for k, v in extra_colors.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip():
                base[k.strip().upper()] = v.strip()
        self._log_colors = base

    def _resolve_level_format(self, levelno: int) -> QTextCharFormat:
        level_name = str(logging.getLevelName(levelno)).upper()
        spec = self._log_colors.get(level_name)

        if not spec:
            for std_level, std_name in (
                (logging.DEBUG, "DEBUG"),
                (logging.INFO, "INFO"),
                (logging.WARNING, "WARNING"),
                (logging.ERROR, "ERROR"),
                (logging.CRITICAL, "CRITICAL"),
            ):
                if levelno >= std_level:
                    spec = self._log_colors.get(std_name)

        return _build_format_from_color_spec(spec or "")

    def _append_colored_to_widget(self, text: str, levelno: int = logging.INFO) -> None:
        if not isinstance(text, str):
            return
        if not self._is_target_alive():
            self.detach()
            return

        widget = self._widget_ref()
        if widget is None:
            self.detach()
            return

        try:
            if isinstance(widget, QPlainTextEdit):
                fmt = self._resolve_level_format(levelno)
                cursor = widget.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                if not widget.document().isEmpty():
                    cursor.insertText("\n", QTextCharFormat())
                cursor.insertText(text, fmt)
                widget.setTextCursor(cursor)
                widget.ensureCursorVisible()
            elif isinstance(widget, QTextEdit):
                widget.append(text)
            elif callable(getattr(widget, "appendPlainText", None)):
                widget.appendPlainText(text)
            elif callable(getattr(widget, "append", None)):
                widget.append(text)
        except RuntimeError:
            self.detach()

    def detach(self) -> None:
        super().detach()
        if getattr(self, "_color_line_ready_connected", False):
            self._color_line_ready_connected = False
            color_relay = getattr(self, "_color_relay", None)
            self._disconnect_signal_safely(
                getattr(color_relay, "line_ready", None),
                self._append_colored_to_widget,
                color_relay,
            )

    def emit(self, record: logging.LogRecord) -> None:
        if not isinstance(record, logging.LogRecord):
            return
        if not self._is_target_alive():
            self.detach()
            return
        try:
            msg = self.format(record)
            self._color_relay.line_ready.emit(msg, int(record.levelno))
        except RuntimeError:
            self.detach()
        except Exception:
            self.handleError(record)


# ==============================================================================
# 4. 로거 매니저 및 레지스트리
# ==============================================================================
class LogManagerRegistry:
    """등록된 모든 로거 매니저 인스턴스를 중앙에서 관리하는 레지스트리 클래스."""

    _instances: list[LoggerManager] = []

    @classmethod
    def register(cls, logger_manager: LoggerManager) -> None:
        if logger_manager not in cls._instances:
            cls._instances.append(logger_manager)

    @classmethod
    def unregister(cls, logger_manager: LoggerManager) -> None:
        if logger_manager in cls._instances:
            cls._instances.remove(logger_manager)

    @classmethod
    def close_all_logs(cls) -> None:
        for manager in list(cls._instances):
            try:
                manager.close_logs()
            except Exception as e:
                print(f"로그 매니저 닫기 실패: {e}")

        LoggerManager.stop_all()
        if LoggerManager._global_listener:
            try:
                LoggerManager._global_listener.stop()
            except Exception:
                pass
            LoggerManager._global_listener = None
            LoggerManager._global_initialized = False

        for handler in LoggerManager._all_file_handlers:
            try:
                handler.close()
            except Exception:
                pass
        LoggerManager._all_file_handlers.clear()

    @classmethod
    def reopen_all_logs(cls) -> None:
        for manager in list(cls._instances):
            try:
                manager.reopen_logs()
            except Exception as e:
                print(f"로그 매니저 재시작 실패: {e}")


class LoggerManager:
    _global_queue: queue.Queue[Any] = queue.Queue(-1)
    _global_listener: logging.handlers.QueueListener | None = None
    _global_initialized: bool = False
    _all_file_handlers: list[logging.Handler] = []
    _all_console_handlers: list[logging.Handler] = []
    _global_normal_handler: PeriodicFlushFileHandler | None = None
    _global_color_handler: PeriodicFlushFileHandler | None = None

    def __init__(
        self,
        log_file: str | None = None,
        flush_interval: float = 5.0,
        logger_name: str = "BaseLogger",
        individual_format: str | None = None,
        global_format: str | None = None,
    ) -> None:
        self.base_log_file = log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
        self.flush_interval = flush_interval
        self.logger_name = logger_name
        self.file_handlers: list[logging.Handler] = []
        self.console_handlers: list[logging.Handler] = []
        self.file_handler_color: PeriodicFlushFileHandler | None = None

        from Common.log_config import log_config_instance

        default_fmt = log_config_instance.build_format_string()
        self.default_individual_format = individual_format or default_fmt
        self.default_global_format = global_format or default_fmt
        self.enable_color_file = log_config_instance.get("enable_color_file")

        self._initialize_global_system()

        self.log_queue: queue.Queue[Any] = queue.Queue(-1)
        self.listener: logging.handlers.QueueListener | None = None
        self.logger = self._initialize_logger()

        LogManagerRegistry.register(self)

    @classmethod
    def _get_dated_file_path(cls, base_path: str, is_color: bool = False) -> str:
        dir_name, file_name = os.path.split(base_path)
        name, ext = os.path.splitext(file_name)
        today_str = datetime.now().strftime("%Y-%m-%d")

        if is_color:
            new_file_name = f"{name}_{today_str}_color{ext}"
        else:
            new_file_name = f"{name}_{today_str}{ext}"

        return os.path.join(dir_name, new_file_name) if dir_name else new_file_name

    @classmethod
    def _initialize_global_system(cls, force: bool = False) -> None:
        if cls._global_initialized and not force:
            return

        from Common.log_config import log_config_instance

        initial_global_fmt = log_config_instance.build_format_string()
        enable_global = log_config_instance.get("enable_global_log")
        enable_global_color = log_config_instance.get("enable_global_color_file")

        if cls._global_normal_handler:
            try:
                cls._global_normal_handler.close()
            except Exception:
                pass
        if cls._global_color_handler:
            try:
                cls._global_color_handler.close()
            except Exception:
                pass
        cls._all_file_handlers.clear()

        all_target_handlers: list[logging.Handler] = []
        default_log_all_file_path = os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_ALL_FILE)

        dir_name = os.path.dirname(default_log_all_file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        all_normal_path = cls._get_dated_file_path(default_log_all_file_path, is_color=False)
        cls._global_normal_handler = PeriodicFlushFileHandler(
            all_normal_path, encoding="utf-8", flush_interval=5.0
        )
        cls._global_normal_handler.setLevel(logging.DEBUG)
        cls._global_normal_handler.setFormatter(
            CustomLogFormatter(initial_global_fmt, datefmt=DEFAULT_DATE_FORMAT)
        )
        if enable_global:
            all_target_handlers.append(cls._global_normal_handler)
        cls._all_file_handlers.append(cls._global_normal_handler)

        all_color_path = cls._get_dated_file_path(default_log_all_file_path, is_color=True)
        cls._global_color_handler = PeriodicFlushFileHandler(
            all_color_path, encoding="utf-8", flush_interval=5.0
        )
        cls._global_color_handler.setLevel(logging.DEBUG)
        cls._global_color_handler.setFormatter(
            CustomColoredFormatter(
                "%(log_color)s" + initial_global_fmt + "%(reset)s",
                datefmt=DEFAULT_DATE_FORMAT,
                log_colors=DEFAULT_LOG_COLORS,
            )
        )
        if enable_global and enable_global_color:
            all_target_handlers.append(cls._global_color_handler)
        cls._all_file_handlers.append(cls._global_color_handler)

        if cls._global_listener:
            try:
                cls._global_listener.stop()
            except Exception:
                pass

        cls._global_listener = logging.handlers.QueueListener(
            cls._global_queue, *all_target_handlers, respect_handler_level=True
        )
        cls._global_listener.start()
        cls._global_initialized = True

    def _build_local_handlers(self) -> list[logging.Handler]:
        target_handlers: list[logging.Handler] = []
        self.file_handlers.clear()
        self.console_handlers.clear()

        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(
            CustomColoredFormatter(
                "%(log_color)s" + self.default_individual_format + "%(reset)s",
                datefmt=DEFAULT_DATE_FORMAT,
                log_colors=DEFAULT_LOG_COLORS,
            )
        )
        target_handlers.append(console_handler)
        self.console_handlers.append(console_handler)

        actual_base_log_file = self.base_log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
        dir_name = os.path.dirname(actual_base_log_file)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        normal_log_path = self._get_dated_file_path(actual_base_log_file, is_color=False)
        file_handler_normal = PeriodicFlushFileHandler(
            normal_log_path, encoding="utf-8", flush_interval=self.flush_interval
        )
        file_handler_normal.setLevel(logging.DEBUG)
        file_handler_normal.setFormatter(
            CustomLogFormatter(self.default_individual_format, datefmt=DEFAULT_DATE_FORMAT)
        )
        target_handlers.append(file_handler_normal)
        self.file_handlers.append(file_handler_normal)

        color_log_path = self._get_dated_file_path(actual_base_log_file, is_color=True)
        self.file_handler_color = PeriodicFlushFileHandler(
            color_log_path, encoding="utf-8", flush_interval=self.flush_interval
        )
        self.file_handler_color.setLevel(logging.DEBUG)
        self.file_handler_color.setFormatter(
            CustomColoredFormatter(
                "%(log_color)s" + self.default_individual_format + "%(reset)s",
                datefmt=DEFAULT_DATE_FORMAT,
                log_colors=DEFAULT_LOG_COLORS,
            )
        )
        if self.enable_color_file:
            target_handlers.append(self.file_handler_color)
        self.file_handlers.append(self.file_handler_color)

        return target_handlers

    def _initialize_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.logger_name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        if not logger.handlers:
            target_handlers = self._build_local_handlers()
            self.listener = logging.handlers.QueueListener(
                self.log_queue, *target_handlers, respect_handler_level=True
            )
            self.listener.start()

            queue_handler = logging.handlers.QueueHandler(self.log_queue)
            logger.addHandler(queue_handler)

            global_queue_handler = logging.handlers.QueueHandler(self._global_queue)
            logger.addHandler(global_queue_handler)

        return logger

    def close_logs(self) -> None:
        if self.listener:
            self.listener.stop()
            self.listener = None

        for handler in self.file_handlers:
            try:
                handler.close()
            except Exception:
                pass

    def reopen_logs(self) -> None:
        self.file_handlers.clear()

        LoggerManager._initialize_global_system(force=True)
        self.logger.handlers.clear()

        target_handlers = self._build_local_handlers()
        self.listener = logging.handlers.QueueListener(
            self.log_queue, *target_handlers, respect_handler_level=True
        )
        self.listener.start()

        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        self.logger.addHandler(queue_handler)

        global_queue_handler = logging.handlers.QueueHandler(self._global_queue)
        self.logger.addHandler(global_queue_handler)

    def get_logger(self) -> logging.Logger:
        return self.logger

    def set_individual_format(self, new_format_str: str) -> None:
        for handler in self.console_handlers:
            handler.setFormatter(
                CustomColoredFormatter(
                    "%(log_color)s" + new_format_str + "%(reset)s",
                    datefmt=DEFAULT_DATE_FORMAT,
                    log_colors=DEFAULT_LOG_COLORS,
                )
            )
        for handler in self.file_handlers:
            if isinstance(handler.formatter, colorlog.ColoredFormatter):
                handler.setFormatter(
                    CustomColoredFormatter(
                        "%(log_color)s" + new_format_str + "%(reset)s",
                        datefmt=DEFAULT_DATE_FORMAT,
                        log_colors=DEFAULT_LOG_COLORS,
                    )
                )
            else:
                handler.setFormatter(
                    CustomLogFormatter(new_format_str, datefmt=DEFAULT_DATE_FORMAT)
                )

    def update_settings(self, new_format_str: str, enable_color_file: bool) -> None:
        self.set_individual_format(new_format_str)
        self.enable_color_file = enable_color_file

        if self.listener and self.file_handler_color:
            target_handlers = [h for h in self.listener.handlers if h != self.file_handler_color]
            if self.enable_color_file:
                target_handlers.append(self.file_handler_color)

            self.listener.stop()
            self.listener = logging.handlers.QueueListener(
                self.log_queue, *target_handlers, respect_handler_level=True
            )
            self.listener.start()

    @classmethod
    def set_global_format(cls, new_format_str: str) -> None:
        for handler in cls._all_file_handlers:
            if isinstance(handler.formatter, colorlog.ColoredFormatter):
                handler.setFormatter(
                    CustomColoredFormatter(
                        "%(log_color)s" + new_format_str + "%(reset)s",
                        datefmt=DEFAULT_DATE_FORMAT,
                        log_colors=DEFAULT_LOG_COLORS,
                    )
                )
            else:
                handler.setFormatter(
                    CustomLogFormatter(new_format_str, datefmt=DEFAULT_DATE_FORMAT)
                )

    @classmethod
    def update_global_settings(
        cls, new_format_str: str, enable_global_log: bool, enable_global_color: bool
    ) -> None:
        cls.set_global_format(new_format_str)
        if cls._global_listener:
            target_handlers: list[logging.Handler] = []
            if enable_global_log:
                if cls._global_normal_handler:
                    target_handlers.append(cls._global_normal_handler)
                if enable_global_color and cls._global_color_handler:
                    target_handlers.append(cls._global_color_handler)

            cls._global_listener.stop()
            cls._global_listener = logging.handlers.QueueListener(
                cls._global_queue, *target_handlers, respect_handler_level=True
            )
            cls._global_listener.start()

    def flush(self) -> None:
        while not self.log_queue.empty():
            time.sleep(0.01)
        for handler in self.file_handlers:
            if hasattr(handler, "force_flush"):
                handler.force_flush()
            else:
                handler.flush()

        while not self._global_queue.empty():
            time.sleep(0.01)
        for handler in self._all_file_handlers:
            if hasattr(handler, "force_flush"):
                handler.force_flush()
            else:
                handler.flush()

    @classmethod
    def stop_all(cls) -> None:
        if cls._global_listener:
            cls._global_listener.stop()

    def stop(self) -> None:
        self.flush()
        if self.listener:
            self.listener.stop()
        LogManagerRegistry.unregister(self)

    @classmethod
    def update_all_logger_formats(cls) -> None:
        from Common.log_config import log_config_instance

        new_fmt = log_config_instance.build_format_string()

        if cls._global_normal_handler:
            cls._global_normal_handler.setFormatter(
                CustomLogFormatter(new_fmt, datefmt=DEFAULT_DATE_FORMAT)
            )
        if cls._global_color_handler:
            cls._global_color_handler.setFormatter(
                CustomColoredFormatter(
                    "%(log_color)s" + new_fmt + "%(reset)s",
                    datefmt=DEFAULT_DATE_FORMAT,
                    log_colors=DEFAULT_LOG_COLORS,
                )
            )

        for manager in list(LogManagerRegistry._instances):
            manager.set_individual_format(new_fmt)

        WindowLogHandlerBase.refresh_all_formats()


class SubLoggerManager(LoggerManager):
    def __init__(
        self,
        log_file: str | None = None,
        flush_interval: float = 5.0,
        module_name: str = "SubModule",
        default_tag: Any = LogTag.DEFAULT,
        individual_format: str | None = None,
        global_format: str | None = None,
    ) -> None:
        actual_log_file = log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
        super().__init__(
            log_file=actual_log_file,
            flush_interval=flush_interval,
            logger_name=module_name,
            individual_format=individual_format,
            global_format=global_format,
        )
        self.default_mod = str(default_tag)

    def _log(self, level: str, message: str, tag: Any = None) -> None:
        current_tag = str(tag) if tag is not None else self.default_mod
        extra_dict = {"tag": current_tag}
        if level == "debug":
            self.logger.debug(message, extra=extra_dict, stacklevel=3)
        elif level == "info":
            self.logger.info(message, extra=extra_dict, stacklevel=3)
        elif level == "warning":
            self.logger.warning(message, extra=extra_dict, stacklevel=3)
        elif level == "error":
            self.logger.error(message, extra=extra_dict, stacklevel=3)
        elif level == "critical":
            self.logger.critical(message, extra=extra_dict, stacklevel=3)

    def debug(self, message: str, tag: Any = None) -> None:
        self._log("debug", message, tag)

    def info(self, message: str, tag: Any = None) -> None:
        self._log("info", message, tag)

    def warning(self, message: str, tag: Any = None) -> None:
        self._log("warning", message, tag)

    def error(self, message: str, tag: Any = None) -> None:
        self._log("error", message, tag)

    def critical(self, message: str, tag: Any = None) -> None:
        self._log("critical", message, tag)

    def log_database_query(self, query: str, tag: Any = LogTag.DATABASE) -> None:
        self.info(f"Executing Query: {query}", tag=tag)

    def log_user_action(self, user_id: str, action: str, tag: Any = LogTag.USER) -> None:
        self.warning(f"User ID: {user_id} performed '{action}'", tag=tag)


# ==============================================================================
# 5. 전역 로거 헬퍼 및 빌트인 등록
# ==============================================================================
_shared_logger: SubLoggerManager | None = None


def setup_global_log(
    log_file: str | None = None,
    module_name: str = "GlobalModule",
    default_tag: Any = LogTag.DEFAULT,
) -> None:
    global _shared_logger
    if _shared_logger is None:
        actual_log_file = log_file or os.path.join(PathMgr.LOG_DIR, DEFAULT_LOG_FILE)
        os.makedirs(PathMgr.LOG_DIR, exist_ok=True)
        _shared_logger = SubLoggerManager(
            log_file=actual_log_file,
            module_name=module_name,
            default_tag=default_tag,
        )

    import builtins

    builtins.logd = logd
    builtins.loge = loge
    builtins.LogTag = LogTag
    builtins.set_file_tag = set_file_tag


def reset_global_log() -> None:
    global _shared_logger
    if _shared_logger is not None:
        _shared_logger.stop()
        _shared_logger = None


def reopen_global_log(new_log_file: str | None = None) -> None:
    reset_global_log()
    LoggerManager._initialize_global_system(force=True)
    LogManagerRegistry.reopen_all_logs()
    setup_global_log(log_file=new_log_file)

    active_loggers: list[logging.Logger] = [logging.getLogger()]
    if _shared_logger is not None and getattr(_shared_logger, "logger", None) is not None:
        active_loggers.append(_shared_logger.logger)
    WindowLogHandlerBase.reattach_all_to_loggers(active_loggers)
    WindowLogHandlerBase.refresh_all_formats()


def logd(message: str, mod: Any = None, level: str = "debug") -> None:
    global _shared_logger
    if _shared_logger is None:
        setup_global_log()
    from Common.log_config import log_config_instance

    if not log_config_instance.is_level_enabled(level):
        return

    current_mods = mod
    if not current_mods:
        current_mods = FileTagManager.get_current_file_mods(_shared_logger.default_mod)

    if isinstance(current_mods, str):
        current_mods = [current_mods]

    if not log_config_instance.is_module_enabled(current_mods):
        return

    mod_str = "/".join(str(m) for m in current_mods)
    lev = str(level).lower()
    extra_dict = {"tag": mod_str}

    if lev == "info":
        _shared_logger.logger.info(message, extra=extra_dict, stacklevel=2)
    elif lev == "warning":
        _shared_logger.logger.warning(message, extra=extra_dict, stacklevel=2)
    elif lev == "error":
        _shared_logger.logger.error(message, extra=extra_dict, stacklevel=2)
    elif lev == "critical":
        _shared_logger.logger.critical(message, extra=extra_dict, stacklevel=2)
    else:
        _shared_logger.logger.debug(message, extra=extra_dict, stacklevel=2)


def loge(message: str, tag: Any = None, level: str = "error", sound: bool = True) -> None:
    global _shared_logger
    if _shared_logger is None:
        setup_global_log()

    current_tags = tag
    if not current_tags:
        current_tags = FileTagManager.get_current_file_mods(_shared_logger.default_mod)

    if isinstance(current_tags, str):
        current_tags = [current_tags]

    tag_str = "/".join(str(t) for t in current_tags)
    lev = str(level).lower()
    extra_dict = {"tag": tag_str}

    if lev == "info":
        _shared_logger.logger.info(message, extra=extra_dict, stacklevel=2)
    elif lev == "warning":
        _shared_logger.logger.warning(message, extra=extra_dict, stacklevel=2)
    elif lev == "error":
        _shared_logger.logger.error(message, extra=extra_dict, stacklevel=2)
    elif lev == "critical":
        _shared_logger.logger.critical(message, extra=extra_dict, stacklevel=2)
    else:
        _shared_logger.logger.debug(message, extra=extra_dict, stacklevel=2)

    if sound and level in ("error", "critical"):
        try:
            from Common.sound import play_error_alert_sound

            play_error_alert_sound()
        except Exception:
            pass
