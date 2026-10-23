"""Windows print-request detection and DEVMODE normalization.

This module observes the Windows PrintService/Operational channel. It does
not decide billing; it only emits software-side job metadata for reconciliation
with the physical Brother SNMP counter.
"""
from dataclasses import dataclass, asdict, field
from enum import Enum
import datetime as _datetime
import os
import subprocess
import xml.etree.ElementTree as ET
import logging
import threading
try:
    from .print_log_writer import (QueuedBatchFileHandler, load_log_settings,
                                   play_notification_sound,
                                   load_print_event_cursor, save_print_event_cursor,
                                   PrintTreeLogFilter, resolve_transfer_file)
except ImportError:  # Support legacy direct execution/import by LinkBox.
    from print_log_writer import (QueuedBatchFileHandler, load_log_settings,
                                 play_notification_sound,
                                 load_print_event_cursor, save_print_event_cursor,
                                 PrintTreeLogFilter, resolve_transfer_file)
import datetime
import ctypes
from pathlib import Path
from Common.paths import LOG_DIR, CONFIG_FILE
from Common.globals import CONFIG_ENCODING


try:
    from .print_spooler_monitor import enumerate_print_jobs as enumerate_spooler_jobs
    from .print_wmi_monitor import enumerate_print_jobs as enumerate_wmi_jobs
except ImportError:
    from print_spooler_monitor import enumerate_print_jobs as enumerate_spooler_jobs
    from print_wmi_monitor import enumerate_print_jobs as enumerate_wmi_jobs

PRINT_SERVICE_CHANNEL = 'Microsoft-Windows-PrintService/Operational'
DEFAULT_EVENT_IDS = {805, 307, 310}  # 805: render/start, 307: printed, 310: cancelled
DEFAULT_CONFIG_PATH = CONFIG_FILE

logger = logging.getLogger('printshop.print_monitor')


def configure_print_logging(log_path=None):
    """Configure durable print-output logging once for the LinkBox process."""
    from Common.logger_service import get_feature_log_dir, get_dated_log_filename
    if log_path is None:
        pdir = get_feature_log_dir('printer')
        log_path = os.path.join(pdir, get_dated_log_filename('PRINT'))
    existing_path = getattr(logger, '_print_log_path', None)
    if logger.handlers and existing_path == os.path.abspath(log_path):
        return logger
    for old_handler in logger.handlers[:]:
        logger.removeHandler(old_handler)
        old_handler.close()
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    logger.setLevel(logging.DEBUG)
    settings = load_log_settings()
    handler = QueuedBatchFileHandler(
        log_path,
        batch_size=settings['batch_size'],
        flush_interval=settings['flush_interval'],
    )
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    pdir = os.path.dirname(os.path.abspath(log_path))
    detect_path = os.path.join(pdir, get_dated_log_filename('DETECT'))
    detect_handler = QueuedBatchFileHandler(
        detect_path,
        batch_size=settings['batch_size'],
        flush_interval=settings['flush_interval'],
    )
    detect_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    detect_handler.addFilter(PrintTreeLogFilter())
    logger.addHandler(detect_handler)
    logger._print_detect_log_path = os.path.abspath(detect_path)
    logger.propagate = False
    logger._print_log_path = os.path.abspath(log_path)
    logger.info('Print monitor logging initialized: path=%s', logger._print_log_path)
    return logger


def close_print_logging():
    """Flush and close the print log so Windows can rename or delete it."""
    if logger.handlers:
        logger.info('Print monitor shutdown requested; flushing queued logs')
    for handler in logger.handlers[:]:
        try:
            handler.flush()
            handler.close()
        finally:
            logger.removeHandler(handler)
    logger._print_log_path = None


def set_print_logging_enabled(log_print=True, print_detect=True):
    """Enable or disable the two development print-log outputs independently."""
    for handler in logger.handlers:
        path = os.path.basename(getattr(handler, 'baseFilename', '')).lower()
        if path.endswith('_print_detect.log'):
            handler.setLevel(logging.NOTSET if print_detect else logging.CRITICAL + 1)
        elif path.endswith('_print.log'):
            handler.setLevel(logging.NOTSET if log_print else logging.CRITICAL + 1)


@dataclass
class PrintRequest:
    event_id: int
    job_id: int | None
    printer_name: str
    document_name: str
    user_name: str
    output_path: str = ''
    source_path: str = ''
    source_metadata: dict = field(default_factory=dict)
    requested_pages: int = 0
    copies: int = 1
    color_type: str = 'UNKNOWN'
    paper_size: str = 'UNKNOWN'
    timestamp: str = ''
    status: str = 'UNKNOWN'
    print_tag: str = ''

    def as_dict(self):
        return asdict(self)


class VerificationStage(str, Enum):
    DETECTED = 'DETECTED'
    JOB_CONFIRMED = 'JOB_CONFIRMED'
    DEVMODE_CONFIRMED = 'DEVMODE_CONFIRMED'
    PRINT_COMPLETED = 'PRINT_COMPLETED'
    SNMP_CONFIRMED = 'SNMP_CONFIRMED'
    FAILED = 'FAILED'


class PrintMonitorDiagnostics:
    """Step-by-step validation and repair checks for Windows print monitoring."""
    def __init__(self, auto_enable=False):
        self.auto_enable = bool(auto_enable)

    @staticmethod
    def is_admin():
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False

    @staticmethod
    def _run(command):
        return subprocess.run(command, capture_output=True, text=True,
                              encoding=CONFIG_ENCODING, errors='replace', timeout=8, check=False)

    @staticmethod
    def _run_elevated_wevtutil():
        """Ask Windows UAC to run the PrintService repair command."""
        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, 'runas', 'wevtutil.exe',
                f'sl {PRINT_SERVICE_CHANNEL} /e:true', None, 0,
            )
            return int(result) > 32
        except (AttributeError, OSError):
            return False

    def run(self):
        configure_print_logging()
        results = []
        is_admin = self.is_admin()
        results.append(self._step(
            'admin-check', is_admin, '관리자 권한 확인',
            '관리자 권한으로 실행 중입니다.' if is_admin else '관리자 권한이 필요합니다.'
        ))
        try:
            query = self._run(['wevtutil', 'gl', PRINT_SERVICE_CHANNEL])
            query_output = (query.stdout or '').strip()
            enabled = 'enabled: true' in query_output.lower()
            results.append(self._step('event-log-query', query.returncode == 0,
                                      'PrintService 채널 조회',
                                      query_output if query.returncode == 0 else query.stderr.strip()))
            results.append(self._step('event-log-enabled', enabled,
                                      'PrintService Operational 활성화',
                                      '활성 상태입니다.' if enabled else '비활성 상태입니다.'))
        except (OSError, subprocess.SubprocessError) as exc:
            results.append(self._step('event-log-query', False, 'PrintService 채널 조회', str(exc)))
            enabled = False
        if self.auto_enable and not enabled:
            if not self.is_admin():
                requested = self._run_elevated_wevtutil()
                results.append(self._step(
                    'event-log-enable', requested,
                    'PrintService 관리자 복구 요청',
                    'UAC 승인 대기' if requested else 'UAC 승격 요청 실패 또는 취소',
                ))
            else:
                try:
                    command = self._run(['wevtutil', 'sl', PRINT_SERVICE_CHANNEL, '/e:true'])
                    results.append(self._step('event-log-enable', command.returncode == 0,
                                              'PrintService 활성화', command.stderr.strip() or '활성화 명령 완료'))
                except (OSError, subprocess.SubprocessError) as exc:
                    results.append(self._step('event-log-enable', False, 'PrintService 활성화', str(exc)))
        try:
            import win32print
            printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 2)
            results.append(self._step('spooler-check', True, 'Windows 스풀러 확인', f'{len(printers)}개 프린터 발견'))
        except (ImportError, OSError) as exc:
            results.append(self._step('spooler-check', False, 'Windows 스풀러 확인', str(exc)))
        logger.info('Print monitor diagnostics and repair completed: %s', results)
        return results

    @staticmethod
    def _step(name, success, message, detail):
        result = {'step': name, 'success': bool(success), 'message': message, 'detail': detail}
        logger.info('Diagnostic step=%s success=%s message=%s detail=%s', name, success, message, detail)
        return result


class PrintVerificationPipeline:
    """Run print confirmation in explicit, auditable stages."""
    def __init__(self, devmode_reader=None, counter_reader=None):
        self.devmode_reader = devmode_reader
        self.counter_reader = counter_reader

    def verify(self, request, counter_before=None):
        configure_print_logging()
        result = {'request': request.as_dict(), 'stage': VerificationStage.DETECTED.value,
                  'counter_before': counter_before, 'counter_after': None, 'actual_pages': 0}
        logger.info('Pipeline stage=%s job_id=%s', result['stage'], request.job_id)
        if request.job_id is None:
            return self._fail(result, 'missing job id')
        result['stage'] = VerificationStage.JOB_CONFIRMED.value
        logger.info('Pipeline stage=%s job_id=%s', result['stage'], request.job_id)

        if self.devmode_reader:
            devmode = self.devmode_reader(request.printer_name, request.job_id)
            if not devmode:
                return self._fail(result, 'DEVMODE unavailable')
            result['devmode'] = devmode
        result['stage'] = VerificationStage.DEVMODE_CONFIRMED.value
        logger.info('Pipeline stage=%s job_id=%s', result['stage'], request.job_id)

        if request.status == 'CANCELLED':
            return self._fail(result, 'print job cancelled')
        if request.status not in ('STARTED', 'SUCCESS', 'SPOOLER'):
            return self._fail(result, f'unsupported print status: {request.status}')
        if request.status == 'SUCCESS':
            result['stage'] = VerificationStage.PRINT_COMPLETED.value
            logger.info('Pipeline stage=%s job_id=%s', result['stage'], request.job_id)

        if self.counter_reader:
            after = self.counter_reader()
            result['counter_after'] = after
            if counter_before is not None and after is not None:
                result['actual_pages'] = max(0, int(after) - int(counter_before))
            result['stage'] = VerificationStage.SNMP_CONFIRMED.value
            logger.info('Pipeline stage=%s job_id=%s actual_pages=%s', result['stage'], request.job_id, result['actual_pages'])
        return result

    @staticmethod
    def _fail(result, reason):
        result['stage'] = VerificationStage.FAILED.value
        result['reason'] = reason
        logger.error('Pipeline stage=FAILED job_id=%s reason=%s', result['request'].get('job_id'), reason)
        return result


def _event_data(root):
    values = {}
    unnamed_index = 1
    for item in root.iter():
        local_name = item.tag.rsplit('}', 1)[-1]
        # PrintService uses both EventData/Data and UserData leaf elements
        # such as Param1, Param5, JobId, and DocumentName.
        if local_name == 'Data':
            pass
        elif list(item):
            continue
        else:
            name = local_name
        name = item.attrib.get('Name', '').strip() or name
        if not name:
            name = f'Param{unnamed_index}'
            unnamed_index += 1
        value = item.text or ''
        values[name] = value
        values.setdefault(name.casefold(), value)
    return values


def parse_printservice_xml(xml_text):
    """Convert one RenderedXml PrintService event into :class:`PrintRequest`."""
    root = ET.fromstring(xml_text)
    system = root.find('./{*}System')
    event_id = int((system.findtext('./{*}EventID') if system is not None else '0') or 0)
    data = _event_data(root)
    timestamp = ''
    if system is not None:
        stamp = system.find('./{*}TimeCreated')
        timestamp = stamp.attrib.get('SystemTime', '') if stamp is not None else ''
    def value(*names, default=''):
        for name in names:
            result = data.get(name, data.get(str(name).casefold(), ''))
            if result not in (None, ''):
                return result
        return default

    def integer(*names, default=0):
        for name in names:
            try: return int(value(name))
            except (TypeError, ValueError): pass
        return default
    document_name = value('DocumentName', 'Document', 'Param2')
    output_path = value('OutputFile', 'FileName', 'Param6')
    if output_path and ('.' in output_path or '\\' in output_path or '/' in output_path):
        # Keep the full path separately, but use only its basename for
        # matching against the filename shown in the open LinkBox transfer
        # tabs. Virtual printers commonly report a full PDF output path.
        document_name = os.path.basename(str(output_path))
    request = PrintRequest(
        event_id=event_id, job_id=integer('JobId', 'Param1', default=None),
        printer_name=value('PrinterName', 'Printer', 'Param5'),
        document_name=document_name,
        output_path=output_path,
        user_name=value('UserName', 'User', 'Param3'),
        # Param7 is not stable across PrintService event schemas; for Event
        # 307 it can contain a byte count rather than a page count.
        requested_pages=integer('Pages', 'TotalPages'),
        copies=max(1, integer('Copies', 'Param8', default=1)),
        color_type=value('Color', 'ColorType', default='UNKNOWN').upper(),
        paper_size=value('PaperSize', 'PageSize', default='UNKNOWN').upper(),
        timestamp=timestamp,
        status='STARTED' if event_id == 805 else 'SUCCESS' if event_id == 307 else 'CANCELLED' if event_id == 310 else 'UNKNOWN',
        print_tag='임의로 출력',
    )
    matched_file = resolve_transfer_file(request.document_name or request.output_path)
    if matched_file:
        request.source_path = matched_file['source_path']
        request.print_tag = 'LinkBox 파일 출력'
        request.source_metadata = matched_file
    configure_print_logging()
    logger.info('PrintService event detected: %s', request.as_dict())
    return request


class WindowsPrintServiceMonitor:
    """Poll PrintService events without blocking the Qt GUI thread."""
    def __init__(self, event_ids=None, max_events=32, monitored_printers=None, on_request=None):
        self.event_ids = set(event_ids or DEFAULT_EVENT_IDS)
        self.max_events = int(max_events)
        self._seen_signatures = set()
        self._active_spooler_signatures = {}
        self._event_cursor = load_print_event_cursor()
        self.on_request = on_request
        self.printer_tree = {}
        self.set_monitored_printers(monitored_printers or [])
        self._ensure_event_log_enabled()

    @staticmethod
    def _ensure_event_log_enabled():
        """Enable the PrintService Operational channel when permissions allow."""
        configure_print_logging()
        command = ['wevtutil', 'sl', PRINT_SERVICE_CHANNEL, '/e:true']
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    encoding=CONFIG_ENCODING, errors='replace', timeout=5, check=False)
            if result.returncode == 0:
                logger.info('PrintService Operational channel is enabled')
            else:
                logger.warning('Could not enable PrintService channel: returncode=%s stderr=%s; run as administrator if needed',
                                result.returncode, (result.stderr or '').strip())
        except (OSError, subprocess.SubprocessError):
            logger.exception('PrintService channel enable command failed')

    @staticmethod
    def _key(value):
        return str(value or '').strip().casefold()

    def set_monitored_printers(self, printers):
        """Replace printer parents while retaining the child job tree."""
        configure_print_logging()
        previous = self.printer_tree
        self.printer_tree = {}
        for printer in printers:
            if not printer.get('enabled', True):
                logger.info('Printer monitor registration skipped: disabled printer=%s', printer.get('name'))
                continue
            name = str(printer.get('name') or '').strip()
            host = str(printer.get('host') or '').strip()
            if name:
                self.printer_tree[self._key(name)] = {
                    'printer': printer, 'jobs': previous.get(self._key(name), {}).get('jobs', []),
                }
                logger.info('Printer monitor registration success: name=%s host=%s', name, host)
            else:
                logger.error('Printer monitor registration failed: printer name is empty, data=%s', printer)
            # Keep one monitored parent per configured printer.  The host or
            # port is metadata, not another printer.  Registering it as a
            # second tree node caused duplicate spooler queries (for example
            # PORTPROMPT: was polled twice for Microsoft Print to PDF).
        configure_print_logging()
        logger.info('Monitored printer tree refreshed: %d target(s): %s', len(self.printer_tree), list(self.printer_tree))

    def _register_under_printer(self, request):
        """Attach a request as a child of its matching configured printer."""
        parent_key = self._key(request.printer_name)
        parent = self.printer_tree.get(parent_key)
        if parent is None:
            return False
        child = request.as_dict()
        document_key = self._key(
            request.source_path or request.output_path or request.document_name
        )
        # Group repeated prints of the same document below one tree item while
        # retaining every individual job record in its children list.
        if document_key:
            for existing in reversed(parent['jobs']):
                existing_key = self._key(
                    existing.get('source_path')
                    or existing.get('output_path')
                    or existing.get('document_name')
                )
                if existing_key == document_key:
                    existing.setdefault('children', []).append(child)
                    existing['print_count'] = len(existing['children']) + 1
                    logger.info(
                        'Repeated print grouped under document=%s count=%s job_id=%s',
                        document_key, existing['print_count'], request.job_id,
                    )
                    return True
        child['children'] = []
        child['print_count'] = 1
        parent['jobs'].append(child)
        # Keep the in-memory tree bounded for long-running shop terminals.
        del parent['jobs'][:-500]
        logger.info(
            'Tree item added: printer=%s document=%s source_path=%s output_path=%s job_id=%s status=%s tag=%s',
            request.printer_name, document_key or request.document_name,
            request.source_path or '<unavailable>', request.output_path or '<unavailable>',
            request.job_id, request.status, request.print_tag or '<none>',
        )
        if not request.source_path:
            logger.warning(
                'Original source filename unavailable; printer supplied output filename only: '
                'job_id=%s output_path=%s', request.job_id, request.output_path or request.document_name
            )
        return True

    def get_printer_tree(self):
        """Return printer parents with their matched print-job children."""
        return self.printer_tree

    def add_virtual_sample(self, filename, source_path, printer_name=None):
        """Add one explicit, non-printing sample item for tree verification."""
        target = printer_name or next(iter(self.printer_tree.values()), {}).get('printer', {}).get('name', '')
        if not target:
            return False
        request = PrintRequest(
            event_id=-1,
            job_id=-1,
            printer_name=target,
            document_name=os.path.basename(os.fspath(filename)),
            user_name='sample',
            output_path=os.path.abspath(os.fspath(source_path)),
            source_path=os.path.abspath(os.fspath(source_path)),
            requested_pages=0,
            status='SAMPLE',
            print_tag='LinkBox 파일 출력 (샘플)',
        )
        return self._register_under_printer(request)

    def poll(self):
        configure_print_logging()
        logger.debug('Print monitor poll started: targets=%d event_ids=%s', len(self.printer_tree), sorted(self.event_ids))
        if not self.printer_tree:
            logger.warning('Print monitor skipped: no enabled monitored printers configured')
            return []
        query = ' or '.join(f'EventID={event_id}' for event_id in sorted(self.event_ids))
        # Restrict polling to events newer than the persisted environment
        # cursor. This prevents replaying old events after restart.
        time_filter = f"TimeCreated[@SystemTime > '{self._event_cursor}']"
        command = ['wevtutil', 'qe', PRINT_SERVICE_CHANNEL,
                   f'/q:*[System[({query}) and {time_filter}]]',
                   '/f:RenderedXml', f'/c:{self.max_events}']
        try:
            logger.debug('Executing PrintService query: %s', command)
            result = subprocess.run(command, capture_output=True, text=True,
                                    encoding=CONFIG_ENCODING, errors='replace', timeout=5,
                                    check=False)
        except (OSError, subprocess.SubprocessError):
            configure_print_logging()
            logger.exception('Unable to query Windows PrintService event log')
            logger.info('Falling back to Windows spooler job enumeration')
            return self._poll_spooler_jobs()
        logger.debug('PrintService result: returncode=%s stdout_chars=%d stderr=%s', result.returncode, len(result.stdout or ''), (result.stderr or '').strip())
        if result.returncode != 0 or not result.stdout.strip():
            configure_print_logging()
            logger.debug(
                'No new PrintService event data: returncode=%s stderr=%s',
                result.returncode,
                (result.stderr or '').strip(),
            )
            if result.returncode == 0:
                now_cursor = _datetime.datetime.now(_datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                self._event_cursor = save_print_event_cursor(now_cursor) or self._event_cursor
            return self._poll_spooler_jobs()
        events = []
        for chunk in result.stdout.split('</Event>'):
            if '<Event' not in chunk: continue
            try:
                event = parse_printservice_xml(chunk + '</Event>')
            except (ET.ParseError, ValueError):
                logger.exception('PrintService XML parse failed: xml_prefix=%r', chunk[:300])
                continue
            signature = (event.event_id, event.job_id, event.timestamp)
            if signature in self._seen_signatures:
                continue
            self._seen_signatures.add(signature)
            if len(self._seen_signatures) > self.max_events * 8:
                self._seen_signatures = set(list(self._seen_signatures)[-self.max_events * 4:])
            if not event.printer_name:
                logger.debug(
                    'PrintService event has no printer field; waiting for completion event: event_id=%s job_id=%s',
                    event.event_id, event.job_id,
                )
                continue
            if self._register_under_printer(event):
                events.append(event)
                # Play only after the event passes deduplication and printer
                # registration.  parse_printservice_xml() is also used for
                # polling historical events, so playing there caused the
                # same event to beep on every poll.
                play_notification_sound(sound_type='tree')
                configure_print_logging()
                logger.info('Print request registered under printer=%s job_id=%s', event.printer_name, event.job_id)
            else:
                configure_print_logging()
                logger.warning('Print request ignored; printer is not monitored: printer=%s job_id=%s', event.printer_name, event.job_id)
        if events:
            configure_print_logging()
            logger.info('PrintService poll completed: %d new event(s)', len(events))
        # Advance only after the query has been processed. Use the current
        # UTC time as a safe boundary when no event was returned.
        cursor_candidates = [event.timestamp for event in events if event.timestamp]
        cursor_candidates.append(_datetime.datetime.now(_datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'))
        self._event_cursor = save_print_event_cursor(max(cursor_candidates)) or self._event_cursor
        spooler_events = self._poll_spooler_jobs()
        new_requests = list(reversed(events)) + spooler_events
        if self.on_request:
            for request in new_requests:
                self.on_request(request)
        return new_requests

    def _poll_spooler_jobs(self):
        """Fallback for virtual printers such as Microsoft Print to PDF.

        Some virtual printer jobs do not produce Event 307 until the output
        filename dialog is completed. EnumJobs can still observe the job while
        it is queued/rendering, which provides the monitor signal immediately.
        """
        requests = []
        for parent in self.printer_tree.values():
            printer = parent['printer']
            name = str(printer.get('name', ''))
            spooler_jobs = enumerate_spooler_jobs(name)
            wmi_jobs = enumerate_wmi_jobs(name)
            logger.debug(
                'Print job sources queried: printer=%s spooler_jobs=%d wmi_jobs=%d',
                name, len(spooler_jobs), len(wmi_jobs),
            )
            # Always combine both sources. Prefer the richer Spooler record
            # when both sources describe the same printer/job pair.
            jobs_by_key = {}
            for job in wmi_jobs:
                jobs_by_key[(name.casefold(), str(job.get('job_id', '')))] = job
            for job in spooler_jobs:
                jobs_by_key[(name.casefold(), str(job.get('job_id', '')))] = job
            jobs = list(jobs_by_key.values())
            logger.debug(
                'Print job sources merged: printer=%s merged_jobs=%d', name, len(jobs)
            )
            current_signatures = set()
            for job in jobs:
                job_id = int(job.get('job_id', 0))
                signature = (name.casefold(), job_id, job.get('status', ''), job.get('document_name', ''))
                current_signatures.add(signature)
                previous_signatures = self._active_spooler_signatures.get(name.casefold(), set())
                if signature in previous_signatures:
                    continue
                request = PrintRequest(
                    event_id=0, job_id=job_id, printer_name=name,
                    document_name=str(job.get('document_name') or ''),
                    user_name=str(job.get('user_name') or ''),
                    requested_pages=int(job.get('total_pages') or 0),
                    copies=int(job.get('size') or 1), status='SPOOLER',
                    print_tag='임의로 출력',
                )
                logger.info(
                    'Print file information collected: method=%s printer=%s job_id=%s '
                    'document=%s user=%s pages=%s size=%s status=%s tag=%s',
                    job.get('source_method', 'unknown'), name, job_id,
                    request.document_name, request.user_name,
                    request.requested_pages, job.get('size', 0), job.get('status', request.status),
                    request.print_tag,
                )
                parent['jobs'].append(request.as_dict())
                del parent['jobs'][:-500]
                requests.append(request)
                play_notification_sound(sound_type='detection')
                configure_print_logging()
                logger.info('Spooler job detected: printer=%s job_id=%s document=%s', name, job_id, request.document_name)
            self._active_spooler_signatures[name.casefold()] = current_signatures
        return requests


class WindowsPrintServiceSubscription:
    """Event-driven PrintService monitor using the Windows EvtSubscribe API."""
    def __init__(self, monitored_printers=None, on_request=None, pipeline=None):
        self.monitor = WindowsPrintServiceMonitor(monitored_printers=monitored_printers)
        self.on_request = on_request
        self.pipeline = pipeline or PrintVerificationPipeline()
        self._subscription = None
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        configure_print_logging()
        if self._thread and self._thread.is_alive():
            logger.info('PrintService subscription start skipped: already running')
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._subscribe, name='PrintServiceSubscription', daemon=True)
        self._thread.start()
        logger.info('PrintService subscription thread started')
        return True

    def stop(self):
        configure_print_logging()
        self._stop.set()
        if self._subscription is not None:
            try:
                close = getattr(self._subscription, 'Close', None)
                if close:
                    close()
            except (OSError, AttributeError):
                pass
            self._subscription = None
        logger.info('PrintService subscription stopped')

    def _subscribe(self):
        configure_print_logging()
        try:
            import win32evtlog
            flags = getattr(win32evtlog, 'EvtSubscribeToFutureEvents', 1)
            query = '*[System[(EventID=805 or EventID=307 or EventID=310)]]'
            self._subscription = win32evtlog.EvtSubscribe(
                PRINT_SERVICE_CHANNEL, flags, Query=query, Callback=self._callback,
            )
            logger.info('PrintService EvtSubscribe started')
            while not self._stop.wait(0.5):
                pass
        except ImportError:
            logger.exception('EvtSubscribe unavailable: pywin32 is not installed')
        except Exception:
            logger.exception('PrintService EvtSubscribe failed; polling fallback remains available')
        finally:
            self._subscription = None

    def _callback(self, action, context, event_handle):
        try:
            import win32evtlog
            logger.info('PrintService subscription callback received: action=%s', action)
            xml_text = win32evtlog.EvtRender(event_handle, win32evtlog.EvtRenderEventXml)
            logger.debug('PrintService event XML received: chars=%d', len(xml_text or ''))
            request = parse_printservice_xml(xml_text)
            signature = (request.event_id, request.job_id, request.timestamp)
            if signature in self.monitor._seen_signatures:
                logger.debug('Subscribed event ignored as duplicate: %s', signature)
                return
            self.monitor._seen_signatures.add(signature)
            if not self.monitor._register_under_printer(request):
                logger.warning('Subscribed event ignored; printer is not monitored: %s', request.printer_name)
                return
            play_notification_sound(sound_type='detection')
            verification = self.pipeline.verify(request)
            logger.info('Print request verification finished: job_id=%s stage=%s result=%s',
                        request.job_id, verification['stage'], verification)
            logger.info('Subscribed print event registered: printer=%s job_id=%s', request.printer_name, request.job_id)
            if self.on_request:
                self.on_request(request)
        except Exception:
            logger.exception('PrintService subscription callback failed')


def read_dev_mode(printer_name, job_id):
    """Read color, paper size, pages and copies from the Windows DEVMODE.

    Returns ``None`` when pywin32 is unavailable or the spooler job no longer
    exists. The caller should treat this as metadata enrichment, not failure.
    """
    try:
        import win32print
    except ImportError:
        configure_print_logging()
        logger.warning('DEVMODE unavailable: pywin32 is not installed')
        return None
    handle = win32print.OpenPrinter(printer_name)
    try:
        job = win32print.GetJob(handle, int(job_id), 2)
        mode = job.get('pDevMode')
        if mode is None: return None
        # Win32 DEVMODE.dmColor: DMCOLOR_COLOR=2, DMCOLOR_MONOCHROME=1.
        color = 'COLOR' if getattr(mode, 'Color', 1) == 2 else 'MONO'
        result = {'color_type': color, 'paper_size': getattr(mode, 'PaperSize', None),
                  'copies': getattr(mode, 'Copies', 1), 'requested_pages': job.get('TotalPages', 0)}
        configure_print_logging()
        logger.info('DEVMODE read: printer=%s job_id=%s metadata=%s', printer_name, job_id, result)
        return result
    except (OSError, TypeError, ValueError):
        configure_print_logging()
        logger.exception('DEVMODE read failed: printer=%s job_id=%s', printer_name, job_id)
        return None
    finally:
        win32print.ClosePrinter(handle)
