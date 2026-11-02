"""Integrated LinkBox printer monitoring service.

This service is hosted by PrintShopApp. It does not create or show a LinkBox
window; it only owns printer monitoring and its Qt timer.
"""
import datetime
import logging
import os

from PySide6.QtCore import QObject, QTimer

from .linkbox_setting import load_monitored_printers
from .print_log_writer import load_log_settings
from Common.paths import LOG_DIR
from .print_request_monitor import (
    PrintMonitorDiagnostics,
    WindowsPrintServiceMonitor,
    close_print_logging,
    configure_print_logging,
)


class IntegratedPrinterMonitor(QObject):
    """Run the LinkBox printer monitor inside the integrated main window."""

    def __init__(self, parent=None, data_dir=None, interval_ms=10000, on_request=None):
        super().__init__(parent)
        self.logger = logging.getLogger('printshop.print_monitor')
        log_dir = data_dir and os.path.join(data_dir, 'log') or LOG_DIR
        log_path = os.path.join(log_dir, datetime.datetime.now().strftime('%Y%m%d_print.log'))
        configure_print_logging(log_path)
        # Validate and repair the Windows PrintService channel from the
        # integrated app. If elevation is needed, Windows shows the UAC prompt
        # without launching a separate LinkBox process.
        PrintMonitorDiagnostics(auto_enable=True).run()
        log_settings = load_log_settings()
        self.log_settings = log_settings
        self.monitor = WindowsPrintServiceMonitor(
            monitored_printers=load_monitored_printers(), on_request=on_request
        )
        self.timer = QTimer(self)
        self.timer.setInterval(int(interval_ms))
        self.timer.timeout.connect(self.poll)

    def start(self):
        self.timer.start()
        self.poll()

    def stop(self):
        self.timer.stop()
        close_print_logging()

    def poll(self):
        try:
            return self.monitor.poll()
        except Exception:
            self.logger.exception('Integrated printer monitor poll failed')
