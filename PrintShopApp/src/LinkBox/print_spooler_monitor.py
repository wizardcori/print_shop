"""PyWin32 print spooler EnumJobs reader."""
import logging

logger = logging.getLogger('printshop.print_monitor')


def enumerate_print_jobs(printer_name):
    """Return EnumJobs level-2 records as normalized dictionaries."""
    try:
        import win32print
    except ImportError:
        logger.debug('Spooler monitor unavailable: pywin32 is not installed')
        return []
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(handle, 0, 999, 2)
        finally:
            win32print.ClosePrinter(handle)
        return [{
            'source_method': 'PyWin32 EnumJobs',
            'printer_name': printer_name,
            'job_id': int(job.get('JobId', 0)),
            'document_name': str(job.get('pDocument') or ''),
            'user_name': str(job.get('pUserName') or ''),
            'total_pages': int(job.get('TotalPages') or 0),
            'size': int(job.get('Size') or 0),
            'status': str(job.get('Status') or ''),
            'submitted': str(job.get('Submitted') or ''),
        } for job in jobs]
    except (OSError, TypeError, ValueError):
        logger.exception('Print spooler EnumJobs query failed: printer=%s', printer_name)
        return []
