"""Common queued logging system with tag and feature-based directory separation.

File naming convention: <YYYYMMDD>_<FEATURE_OR_TAG>.LOG
Format: YYYY-MM-DD HH:MM:SS,mmm [LEVEL] [TAG] message
"""

import atexit
import datetime
import logging
import os
import queue
import threading
import time
from typing import Optional, Dict

from Common.paths import DATA_DIR, LOG_DIR

DEFAULT_BATCH_SIZE = 50
DEFAULT_FLUSH_INTERVAL = 2.0


def _open_utf8_log(path: str):
    """Open an append-only log file with UTF-8 encoding, writing BOM on creation."""
    is_new = not os.path.exists(path) or os.path.getsize(path) == 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    stream = open(path, "a", encoding="utf-8", newline="")
    if is_new:
        stream.write("\ufeff")
    return stream


class CommonQueuedBatchFileHandler(logging.Handler):
    """Asynchronous queued batch file handler for non-blocking disk I/O."""

    def __init__(
        self,
        filepath: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
    ):
        super().__init__()
        self.filepath = os.path.abspath(filepath)
        self.batch_size = max(1, int(batch_size))
        self.flush_interval = max(0.05, float(flush_interval))
        self._records = queue.Queue()
        self._stop = threading.Event()
        self._sentinel = object()
        self._thread = threading.Thread(
            target=self._writer_loop,
            name=f"LogWriter-{os.path.basename(filepath)}",
            daemon=True,
        )
        self._thread.start()

    def emit(self, record: logging.LogRecord):
        try:
            if self._stop.is_set():
                return
            self._records.put_nowait(self.format(record))
        except Exception:
            self.handleError(record)

    def _writer_loop(self):
        pending = []
        deadline = time.monotonic() + self.flush_interval
        while True:
            timeout = max(0.01, deadline - time.monotonic())
            try:
                item = self._records.get(timeout=timeout)
            except queue.Empty:
                if self._stop.is_set():
                    self._write_batch(pending)
                    break
                item = None

            if item is self._sentinel:
                self._write_batch(pending)
                pending.clear()
                if self._stop.is_set() and self._records.empty():
                    break
                deadline = time.monotonic() + self.flush_interval
                continue

            if item is not None:
                pending.append(item)

            if len(pending) >= self.batch_size or time.monotonic() >= deadline:
                self._write_batch(pending)
                pending.clear()
                deadline = time.monotonic() + self.flush_interval

    def _write_batch(self, records):
        if not records:
            return
        try:
            with _open_utf8_log(self.filepath) as stream:
                stream.write(os.linesep.join(records) + os.linesep)
                stream.flush()
        except OSError:
            pass

    def close(self):
        if not self._stop.is_set():
            self._stop.set()
            self._records.put_nowait(self._sentinel)
            self._thread.join(timeout=3)
        super().close()


class TaggedFormatter(logging.Formatter):
    """Formatter that ensures a [TAG] is present in log outputs."""

    def __init__(self, default_tag: str = "SYSTEM"):
        super().__init__("%(asctime)s [%(levelname)s] [%(log_tag)s] %(message)s")
        self.default_tag = default_tag

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "log_tag"):
            record.log_tag = getattr(record, "tag", self.default_tag)
        return super().format(record)


_loggers: Dict[str, logging.Logger] = {}
_lock = threading.Lock()


def get_feature_log_dir(feature_name: str, base_dir: Optional[str] = None) -> str:
    """Return directory path partitioned by feature name: <DATA_DIR>/log/<feature_name>."""
    base = base_dir or LOG_DIR
    target = os.path.join(base, feature_name.lower())
    os.makedirs(target, exist_ok=True)
    return target


def get_dated_log_filename(tag: str, date_str: Optional[str] = None) -> str:
    """Generate filename adhering to 20261011_XXX.LOG convention."""
    d = date_str or datetime.datetime.now().strftime("%Y%m%d")
    return f"{d}_{tag.upper()}.LOG"


def get_feature_logger(
    feature: str,
    tag: str,
    base_dir: Optional[str] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    flush_interval: float = DEFAULT_FLUSH_INTERVAL,
) -> logging.Logger:
    """Get or configure a logger bound to a feature directory, tag, and queued handler."""
    logger_name = f"printshop.{feature.lower()}.{tag.lower()}"
    with _lock:
        if logger_name in _loggers:
            return _loggers[logger_name]

        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)

        feature_dir = get_feature_log_dir(feature, base_dir)
        filename = get_dated_log_filename(tag)
        filepath = os.path.join(feature_dir, filename)

        handler = CommonQueuedBatchFileHandler(
            filepath, batch_size=batch_size, flush_interval=flush_interval
        )
        handler.setFormatter(TaggedFormatter(default_tag=tag.upper()))
        logger.addHandler(handler)
        logger.propagate = False

        # Store attributes for inspection or log viewer helpers
        logger._log_filepath = filepath
        logger._feature = feature
        logger._tag = tag.upper()

        _loggers[logger_name] = logger
        return logger


def log_event(
    feature: str,
    tag: str,
    message: str,
    level: int = logging.INFO,
    *args,
    **kwargs,
):
    """Convenience function to log via common queued logger."""
    lg = get_feature_logger(feature, tag)
    extra = kwargs.setdefault("extra", {})
    extra["log_tag"] = tag.upper()
    lg.log(level, message, *args, **kwargs)


def flush_all_loggers():
    """Flush and close all registered queued handlers."""
    with _lock:
        for lg in _loggers.values():
            for h in lg.handlers[:]:
                h.close()
                lg.removeHandler(h)
        _loggers.clear()


atexit.register(flush_all_loggers)
