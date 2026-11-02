"""Printer-independent print dispatch, counter reconciliation, and billing."""

from dataclasses import dataclass
from datetime import datetime, timezone


VALID_STATUSES = {'SUCCESS', 'CANCELLED', 'JAMMED', 'FAILED'}


@dataclass
class PrintJob:
    client_info: str
    color_type: str
    paper_size: str
    requested_pages: int
    operator_info: str = ''
    printer_name: str = ''
    spooler_job_id: int | None = None


class PrintWorkflow:
    """Coordinate a confirmed print job without assuming a physical printer API."""

    def __init__(self, database, counter_reader=None):
        self.database = database
        self.counter_reader = counter_reader

    def begin(self, job):
        before = self._read_counter()
        return {'job': job, 'counter_before': before}

    def complete(self, state, status='SUCCESS', error_message=None):
        status = str(status).upper()
        if status not in VALID_STATUSES:
            raise ValueError(f'Unsupported print status: {status}')
        job = state['job']
        before = state.get('counter_before')
        after = self._read_counter()
        if status == 'SUCCESS' and before is not None and after is not None:
            actual = max(0, after - before)
        elif status == 'SUCCESS':
            actual = int(job.requested_pages)
        else:
            actual = 0
        color = str(job.color_type).upper()
        paper = str(job.paper_size).upper()
        unit_price = self.database.get_print_price(color, paper) or 0
        record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'client_info': job.client_info,
            'operator_info': job.operator_info,
            'printer_name': job.printer_name,
            'color_type': color,
            'paper_size': paper,
            'requested_pages': int(job.requested_pages),
            'actual_pages': actual,
            'unit_price': unit_price,
            'total_price': actual * unit_price if status == 'SUCCESS' else 0,
            'status': status,
            'spooler_job_id': job.spooler_job_id,
            'counter_before': before,
            'counter_after': after,
            'error_message': error_message,
        }
        record['id'] = self.database.save_print_log(record)
        return record

    def _read_counter(self):
        if self.counter_reader is None:
            return None
        try:
            value = self.counter_reader()
            return None if value is None else int(value)
        except (OSError, ValueError, TypeError):
            return None
