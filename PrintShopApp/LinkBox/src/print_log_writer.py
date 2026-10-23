"""Low-overhead queued printer log writer.

Records are queued quickly, written in short batches, flushed, and the file
is closed after every batch so Explorer can manage the log file.
"""
import logging
import subprocess
import os
import queue
import threading
import time
import configparser
import atexit
import json
from datetime import datetime, timezone
from Common.paths import LOG_DIR, PRINT_MONITOR_SOUND_DIR, CONFIG_FILE, TRANSFER_REGISTRY_FILE
from Common.globals import CONFIG_ENCODING

try:
    import winsound
except ImportError:  # pragma: no cover - non-Windows development
    winsound = None

DEFAULT_BATCH_SIZE = 100
DEFAULT_FLUSH_INTERVAL = 5.0
LOG_SETTINGS_SECTION = 'PrintLog'
PRINT_MONITOR_SECTION = 'PrintMonitor'

# Printer-monitor values edited in Settings are persisted with application
# settings. The implementation config remains separate for standalone needs.
LOG_CONFIG_PATH = CONFIG_FILE
_sound_queue = queue.Queue(maxsize=32)
_sound_thread = None
_sound_stop = threading.Event()
_sound_start_lock = threading.Lock()
_sound_generation = 0
_sound_generation_lock = threading.Lock()
_transfer_files = {}
_transfer_files_lock = threading.RLock()
_transfer_registry_path = TRANSFER_REGISTRY_FILE


def _load_transfer_registry():
    try:
        with open(_transfer_registry_path, 'r', encoding=CONFIG_ENCODING) as stream:
            values = json.load(stream)
        if isinstance(values, dict):
            _transfer_files.update(values)
    except (OSError, ValueError, TypeError):
        pass


def _save_transfer_registry():
    try:
        os.makedirs(os.path.dirname(_transfer_registry_path), exist_ok=True)
        temporary_path = f'{_transfer_registry_path}.tmp'
        with open(temporary_path, 'w', encoding=CONFIG_ENCODING) as stream:
            json.dump(_transfer_files, stream, ensure_ascii=False, indent=2)
        os.replace(temporary_path, _transfer_registry_path)
    except (OSError, TypeError, ValueError):
        logging.getLogger('printshop.print_monitor').debug(
            'Failed to save LinkBox transfer registry', exc_info=True
        )


_load_transfer_registry()


def register_transfer_file(filename, file_path, **metadata):
    """Register a file received by LinkBox for later print matching."""
    if not filename or not file_path:
        logging.getLogger('printshop.print_monitor').warning(
            'Transfer file registration skipped: filename or path is empty'
        )
        write_print_detect_log('WARNING', 'Transfer file registration skipped: filename or path is empty')
        return False
    key = os.path.basename(os.fspath(filename)).casefold()
    with _transfer_files_lock:
        _transfer_files[key] = {
            'filename': os.path.basename(os.fspath(filename)),
            'source_path': os.path.abspath(os.fspath(file_path)),
            **metadata,
        }
        _save_transfer_registry()
    message = 'Transfer file registered: filename=%s path=%s metadata=%s'
    logging.getLogger('printshop.print_monitor').info(message, key, file_path, metadata)
    write_print_detect_log('INFO', message, key, file_path, metadata)
    return True


def register_today_transfer_file(filename, file_path, received_time, **metadata):
    """Register a received file only when its receive timestamp is today."""
    if not filename:
        return False
    try:
        received_date = datetime.strptime(str(received_time)[:8], '%Y%m%d').date()
    except (TypeError, ValueError):
        logging.getLogger('printshop.print_monitor').warning(
            'Transfer file registration skipped: invalid received_time=%s filename=%s',
            received_time, filename,
        )
        write_print_detect_log(
            'WARNING', 'Transfer file registration skipped: invalid received_time=%s filename=%s',
            received_time, filename,
        )
        return False
    if received_date != datetime.now().date():
        logging.getLogger('printshop.print_monitor').info(
            'Transfer file registration skipped: received_date=%s filename=%s',
            received_date.isoformat(), filename,
        )
        write_print_detect_log(
            'INFO', 'Transfer file registration skipped: received_date=%s filename=%s',
            received_date.isoformat(), filename,
        )
        return False
    return register_transfer_file(filename, file_path, received_time=received_time, **metadata)


def resolve_transfer_file(filename):
    """Find a LinkBox-received file by the printer-reported document name."""
    if not filename:
        return None
    key = os.path.basename(os.fspath(filename)).casefold()
    with _transfer_files_lock:
        return dict(_transfer_files.get(key, {})) or None


class PrintTreeLogFilter(logging.Filter):
    """Allow only printer-tree insertion records in print_detect.log."""

    TREE_MESSAGES = ('Tree item added:', 'Repeated print grouped under document=')

    def filter(self, record):
        message = str(record.getMessage())
        return any(message.startswith(prefix) for prefix in self.TREE_MESSAGES)


def _open_utf8_log(path):
    """Open an append-only log while marking newly-created files as UTF-8.

    The BOM is written only once, when the file is first created, so repeated
    append operations do not insert BOM characters into the log body.  This
    keeps the logs readable by Windows viewers that otherwise assume ANSI.
    """
    is_new = not os.path.exists(path) or os.path.getsize(path) == 0
    stream = open(path, 'a', encoding=CONFIG_ENCODING, newline='')
    if is_new:
        stream.write('\ufeff')
    return stream


def _write_sound_log(level, message, *args):
    """Append one sound event and close the file immediately."""
    try:
        log_dir = LOG_DIR
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, datetime.now().strftime('%Y%m%d_sound.log'))
        rendered = message % args if args else message
        with _open_utf8_log(path) as stream:
            stream.write(
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]} '
                f'[{level}] {rendered}{os.linesep}'
            )
    except (OSError, TypeError, ValueError):
        # Sound logging must never affect the sound worker or the application.
        pass


def write_print_detect_log(level, message, *args):
    """Write printer detection/tree-registration details to a daily log."""
    try:
        log_dir = LOG_DIR
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, datetime.now().strftime('%Y%m%d_print_detect.log'))
        rendered = message % args if args else message
        with _open_utf8_log(path) as stream:
            stream.write(
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]} '
                f'[{level}] {rendered}{os.linesep}'
            )
    except (OSError, TypeError, ValueError):
        logging.getLogger('printshop.print_monitor').debug(
            'Print detection log write failed', exc_info=True
        )

def write_system_log(level, message, *args):
    """Write system log."""
    try:
        log_dir = LOG_DIR
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, datetime.now().strftime('%Y%m%d_system.log'))
        rendered = message % args if args else message
        with _open_utf8_log(path) as stream:
            stream.write(
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]} '
                f'[{level}] {rendered}{os.linesep}'
            )
    except (OSError, TypeError, ValueError):
        logging.getLogger('printshop.system_monitor').debug(
            'System log write failed', exc_info=True
        )

def _sound_worker():
    while not _sound_stop.is_set():
        try:
            request = _sound_queue.get(timeout=0.25)
        except queue.Empty:
            continue
        if request is None:
            _write_sound_log('INFO', 'Sound worker stop requested')
            _sound_queue.task_done()
            break
        generation, sound_path, frequency, duration = request
        try:
            with _sound_generation_lock:
                if generation != _sound_generation:
                    _write_sound_log('INFO', 'Sound request skipped as obsolete: path=%s', sound_path or '<beep>')
                    continue
            _write_sound_log('INFO', 'Sound playback started: path=%s', sound_path or '<beep>')
            if winsound is not None:
                if sound_path and os.path.isfile(os.fspath(sound_path)):
                    winsound.PlaySound(os.fspath(sound_path), winsound.SND_FILENAME)
                else:
                    winsound.Beep(int(frequency), int(duration))
            _write_sound_log('INFO', 'Sound playback completed: path=%s', sound_path or '<beep>')
        except (OSError, RuntimeError, ValueError):
            _write_sound_log('ERROR', 'Sound playback failed: path=%s', sound_path or '<beep>')
            logging.getLogger('printshop.print_monitor').debug(
                'Notification sound playback failed: %s', sound_path, exc_info=True
            )
        finally:
            _sound_queue.task_done()


def _ensure_sound_worker():
    global _sound_thread
    if winsound is None:
        return False
    with _sound_start_lock:
        if _sound_thread is None or not _sound_thread.is_alive():
            _sound_stop.clear()
            _sound_thread = threading.Thread(
                target=_sound_worker, name='PrintSoundWorker', daemon=True
            )
            _sound_thread.start()
    return True


def play_notification_sound(sound_path=None, frequency=880, duration=120, sound_type=None):
    """Play a short notification or an optional user-selected WAV file.

    Sound errors are intentionally swallowed so printer monitoring and file
    transfer never stop because an audio device or file is unavailable.
    """
    if not _ensure_sound_worker():
        return False
    if not sound_path and sound_type in ('detection', 'tree'):
        sound_path = load_sound_settings().get(f'{sound_type}_sound', '')
    stop_notification_sound()
    with _sound_generation_lock:
        generation = _sound_generation
    try:
        _sound_queue.put_nowait((generation, sound_path, frequency, duration))
        _write_sound_log('INFO', 'Sound request queued: path=%s', sound_path or '<beep>')
        return True
    except queue.Full:
        logging.getLogger('printshop.print_monitor').warning(
            'Notification sound skipped: sound queue is full'
        )
        return False


def stop_notification_sound():
    """Stop the current sound and discard queued sounds immediately."""
    global _sound_generation
    with _sound_generation_lock:
        _sound_generation += 1
        generation = _sound_generation
    if winsound is not None:
        try:
            winsound.PlaySound(None, 0)
        except (OSError, RuntimeError):
            pass
    discarded = 0
    while True:
        try:
            _sound_queue.get_nowait()
            _sound_queue.task_done()
            discarded += 1
        except queue.Empty:
            break
    _write_sound_log(
        'INFO', 'Previous sound stopped: generation=%s discarded_queued=%s',
        generation, discarded
    )


def close_sound_worker():
    """Stop the sound worker without blocking application shutdown."""
    _sound_stop.set()
    try:
        _sound_queue.put_nowait(None)
    except queue.Full:
        pass


atexit.register(close_sound_worker)


def load_log_settings(config_path=LOG_CONFIG_PATH):
    config = configparser.ConfigParser()
    values = {'batch_size': DEFAULT_BATCH_SIZE, 'flush_interval': DEFAULT_FLUSH_INTERVAL}
    try:
        config.read(config_path, encoding=CONFIG_ENCODING)
        values['batch_size'] = max(1, config.getint(LOG_SETTINGS_SECTION, 'batch_size', fallback=DEFAULT_BATCH_SIZE))
        values['flush_interval'] = max(0.05, config.getfloat(LOG_SETTINGS_SECTION, 'flush_interval', fallback=DEFAULT_FLUSH_INTERVAL))
    except (OSError, ValueError, configparser.Error):
        pass
    return values


def save_log_settings(batch_size, flush_interval, config_path=LOG_CONFIG_PATH):
    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path, encoding=CONFIG_ENCODING)
    config[LOG_SETTINGS_SECTION] = {
        'batch_size': str(max(1, int(batch_size))),
        'flush_interval': str(max(0.05, float(flush_interval))),
    }
    with open(config_path, 'w', encoding=CONFIG_ENCODING) as stream:
        config.write(stream)


def load_log_viewer_path(config_path=LOG_CONFIG_PATH):
    config = configparser.ConfigParser()
    try:
        config.read(config_path, encoding=CONFIG_ENCODING)
        return config.get(LOG_SETTINGS_SECTION, 'log_viewer_path', fallback='').strip()
    except (OSError, configparser.Error):
        return ''


def save_log_viewer_path(path, config_path=LOG_CONFIG_PATH):
    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path, encoding=CONFIG_ENCODING)
    if not config.has_section(LOG_SETTINGS_SECTION):
        config.add_section(LOG_SETTINGS_SECTION)
    config.set(LOG_SETTINGS_SECTION, 'log_viewer_path', str(path or '').strip())
    with open(config_path, 'w', encoding=CONFIG_ENCODING) as stream:
        config.write(stream)


def load_print_event_cursor(config_path=LOG_CONFIG_PATH):
    """Load the UTC time after which PrintService events should be read."""
    config = configparser.ConfigParser()
    try:
        config.read(config_path, encoding=CONFIG_ENCODING)
        value = config.get(PRINT_MONITOR_SECTION, 'last_event_time', fallback='').strip()
        if value:
            datetime.fromisoformat(value.replace('Z', '+00:00'))
            return value
    except (OSError, ValueError, configparser.Error):
        pass
    # First startup intentionally starts at now; historical events are not
    # replayed into the monitor or notification sound.
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def save_print_event_cursor(value, config_path=LOG_CONFIG_PATH):
    """Persist the latest PrintService event cursor in the environment INI."""
    try:
        cursor = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if cursor.tzinfo is None:
            cursor = cursor.replace(tzinfo=timezone.utc)
        cursor_value = cursor.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        config = configparser.ConfigParser()
        if os.path.exists(config_path):
            config.read(config_path, encoding=CONFIG_ENCODING)
        if not config.has_section(PRINT_MONITOR_SECTION):
            config.add_section(PRINT_MONITOR_SECTION)
        config.set(PRINT_MONITOR_SECTION, 'last_event_time', cursor_value)
        with open(config_path, 'w', encoding=CONFIG_ENCODING) as stream:
            config.write(stream)
        return cursor_value
    except (OSError, ValueError, configparser.Error):
        logging.getLogger('printshop.print_monitor').exception('Failed to save PrintService event cursor')
        return None


class QueuedBatchFileHandler(logging.Handler):
    """Queue records and append them in bounded batches before closing."""

    def __init__(self, filename, batch_size=DEFAULT_BATCH_SIZE, flush_interval=DEFAULT_FLUSH_INTERVAL):
        super().__init__()
        self.filename = os.path.abspath(filename)
        self.batch_size = max(1, int(batch_size))
        self.flush_interval = max(0.05, float(flush_interval))
        self._records = queue.Queue()
        self._stop = threading.Event()
        self._sentinel = object()
        self._thread = threading.Thread(
            target=self._writer_loop,
            name='PrintLogWriter',
            daemon=True,
        )
        self._thread.start()

    def emit(self, record):
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
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)
            with _open_utf8_log(self.filename) as stream:
                stream.write(os.linesep.join(records) + os.linesep)
                stream.flush()
        except OSError:
            logging.getLogger('printshop.print_monitor').exception(
                'Queued printer log batch write failed: %s', self.filename
            )

    def close(self):
        if not self._stop.is_set():
            self._stop.set()
            self._records.put_nowait(self._sentinel)
            self._thread.join(timeout=3)
        # The writer loop drains the queue before exiting. This explicit
        # flush point makes shutdown behavior clear to callers and keeps the
        # file closed before the application process ends.
        super().close()
