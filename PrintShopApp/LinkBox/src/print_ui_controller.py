"""LinkBox printer-log UI callbacks hosted by the integrated window."""

import os
import subprocess


def update_print_log_outputs(window, set_print_logging_enabled):
    """Apply the development-only print-log checkbox state."""
    window.log_print_enabled = (
        getattr(window, 'log_print_checkbox', None) is None
        or window.log_print_checkbox.isChecked()
    )
    window.print_detect_enabled = (
        getattr(window, 'print_detect_checkbox', None) is None
        or window.print_detect_checkbox.isChecked()
    )
    set_print_logging_enabled(
        log_print=window.log_print_enabled,
        print_detect=window.print_detect_enabled,
    )
    window.persist_settings()


def open_print_log_viewer(window, log_type, development_mode, print_monitor_logger, load_log_viewer_path):
    """Open a configured LinkBox print log in the selected viewer."""
    if not development_mode:
        return
    log_path = getattr(
        print_monitor_logger,
        '_print_detect_log_path' if log_type == 'print_detect' else '_print_log_path',
        '',
    )
    viewer = load_log_viewer_path()
    if not log_path or not os.path.exists(log_path):
        return
    if viewer and os.path.exists(viewer):
        subprocess.Popen([viewer, log_path])
    elif hasattr(os, 'startfile'):
        os.startfile(log_path)
