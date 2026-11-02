"""WMI Win32_PrintJob reader used by the LinkBox printer monitor.

WMI is useful as a diagnostic/fallback source for queued jobs. It exposes
printer name, job id, document, owner, size, pages and submitted time.
"""
import logging

logger = logging.getLogger('printshop.print_monitor')


def enumerate_print_jobs(printer_name=None):
    """Return Win32_PrintJob records as plain dictionaries.

    Returns an empty list when the optional ``wmi`` package is unavailable or
    WMI cannot be queried.
    """
    try:
        import wmi
    except ImportError:
        logger.debug('WMI monitor unavailable: wmi package is not installed')
        return []
    try:
        connection = wmi.WMI(namespace='root\\CIMV2')
        jobs = connection.Win32_PrintJob()
        result = []
        for job in jobs:
            name = str(getattr(job, 'Name', '') or '')
            printer, _, job_id = name.rpartition(',')
            if printer_name and printer.casefold() != str(printer_name).casefold():
                continue
            result.append({
                'source_method': 'WMI Win32_PrintJob',
                'printer_name': printer,
                'job_id': int(job_id) if job_id.isdigit() else job_id,
                'document_name': str(getattr(job, 'Document', '') or ''),
                'user_name': str(getattr(job, 'Owner', '') or ''),
                'total_pages': int(getattr(job, 'TotalPages', 0) or 0),
                'size': int(getattr(job, 'Size', 0) or 0),
                'status': str(getattr(job, 'Status', '') or ''),
                'submitted': str(getattr(job, 'TimeSubmitted', '') or ''),
            })
        return result
    except Exception:
        logger.exception('WMI Win32_PrintJob query failed: printer=%s', printer_name)
        return []
