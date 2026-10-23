"""LinkShare QR print and export workflow."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QRadioButton, QVBoxLayout,
)
from PySide6.QtGui import QPageSize
def show_network_qr_print_dialog(window):
    if not hasattr(window, 'hotspot_network_pixmap') or window.hotspot_network_pixmap.isNull():
        QMessageBox.warning(window, "Print QR Code", "The network QR code is not ready yet.")
        return
    show_qr_print_dialog(window, 
        "Network Connection QR",
        window.hotspot_network_pixmap,
        f"SSID: {window.hotspot_ssid}\nPassword: {window.hotspot_password or '(not available)'}",
    )

def show_captive_qr_print_dialog(window):
    if not hasattr(window, 'hotspot_qr_pixmap') or window.hotspot_qr_pixmap.isNull():
        QMessageBox.warning(window, "Print QR Code", "The captive portal QR code is not ready yet.")
        return
    show_qr_print_dialog(window, 
        "Captive Portal QR",
        window.hotspot_qr_pixmap,
        f"Internet access request\nhttp://{window.hotspot_gateway}:5000/scan",
    )

def show_qr_print_dialog(window, title, pixmap, guide_text):
    dialog = QDialog(window)
    dialog.setWindowTitle(title)
    dialog.setMinimumSize(380, 460)
    layout = QVBoxLayout(dialog)
    qr_type = 'network' if 'Network' in title else 'captive'
    saved_format = window.qr_output_formats.get(qr_type, 'PDF')
    saved_scale = int(window.qr_output_scales.get(qr_type, 1))

    preview = QLabel()
    preview.setAlignment(Qt.AlignCenter)
    preview.setPixmap(pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    layout.addWidget(preview)

    guide = QLabel(guide_text)
    guide.setAlignment(Qt.AlignCenter)
    guide.setWordWrap(True)
    guide.setStyleSheet("font-size: 11px; color: #263238; padding: 6px;")
    layout.addWidget(guide)

    format_layout = QHBoxLayout()
    format_layout.addWidget(QLabel("출력 형식:"))
    format_group = QButtonGroup(dialog)
    format_buttons = {}
    for file_format in ("JPG", "BMP", "PDF"):
        radio = QRadioButton(file_format)
        radio.setChecked(file_format == saved_format)
        format_group.addButton(radio)
        format_buttons[file_format] = radio
        format_layout.addWidget(radio)
    format_layout.addStretch()
    layout.addLayout(format_layout)

    scale_layout = QHBoxLayout()
    for scale in (1, 2, 3, 4):
        button = QPushButton(f"{scale}x")
        button.setMinimumHeight(32)
        if scale == saved_scale:
            button.setStyleSheet("font-weight: bold; border: 2px solid #1565c0;")
        button.clicked.connect(
            lambda checked=False, value=scale: export_qr_with_text(window, 
                pixmap, title, guide_text, value,
                next((name for name, radio in format_buttons.items() if radio.isChecked()), "PDF"),
                dialog, qr_type
            )
        )
        scale_layout.addWidget(button)
    layout.addLayout(scale_layout)
    dialog.exec()

def export_qr_with_text(window, pixmap, title, guide_text, scale, file_format, preview_dialog=None, qr_type=None):
    """Save a compact, readable QR+text output with a fixed filename."""
    qr_type = qr_type or ('network' if 'Network' in title else 'captive')
    output_dir = window.qr_output_dirs.get(qr_type, os.path.join(os.getcwd(), 'data', 'qr_output'))
    if not output_dir or not os.path.isdir(output_dir):
        output_dir = QFileDialog.getExistingDirectory(window, "출력 폴더 선택", output_dir or os.getcwd())
        if not output_dir:
            return False
        window.qr_output_dirs[qr_type] = output_dir
        window.persist_settings()

    safe_name = "network_connection_qr" if "Network" in title else "captive_portal_qr"
    extension = file_format.lower()
    output_path = os.path.join(output_dir, f"{safe_name}_{scale}x.{extension}")
    window.qr_output_formats[qr_type] = file_format
    window.qr_output_scales[qr_type] = scale
    window.persist_settings()
    qr_size = max(240, 240 * scale)
    qr_image = pixmap.toImage().scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.FastTransformation)
    margin = max(12, 12 * scale)
    text_font = QFont("Arial", max(12, 12 * scale))
    text_metrics = QFontMetrics(text_font)
    text_lines = guide_text.splitlines() or [title]
    text_height = text_metrics.lineSpacing() * len(text_lines)
    canvas = QImage(qr_size + margin * 2, qr_size + text_height + margin * 2, QImage.Format_RGB32)
    canvas.fill(Qt.white)
    painter = QPainter(canvas)
    painter.setPen(Qt.black)
    painter.setFont(text_font)
    painter.drawImage(margin, margin, qr_image)
    text_y = margin + qr_size + max(2, scale)
    for line in text_lines:
        painter.drawText(margin, text_y, qr_size, text_metrics.lineSpacing(), Qt.AlignHCenter, line)
        text_y += text_metrics.lineSpacing()
    painter.end()

    try:
        if file_format in ("JPG", "BMP"):
            if not canvas.save(output_path, file_format):
                raise OSError("이미지 파일 저장에 실패했습니다.")
        else:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(output_path)
            printer.setPageSize(QPageSize(QPageSize.A4))
            painter = QPainter(printer)
            page_rect = printer.pageLayout().paintRectPixels(printer.resolution())
            fitted = canvas.scaled(page_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = page_rect.left() + (page_rect.width() - fitted.width()) // 2
            y = page_rect.top() + (page_rect.height() - fitted.height()) // 2
            painter.drawImage(x, y, fitted)
            painter.end()
    except (OSError, RuntimeError) as exc:
        QMessageBox.warning(window, "출력 실패", str(exc))
        return False

    QMessageBox.information(window, "출력 완료", f"파일이 저장되었습니다.\n{output_path}")
    if preview_dialog is not None:
        preview_dialog.accept()
    return True

def print_qr_pixmap(window, pixmap, title, scale, preview_dialog=None):
    printer = QPrinter(QPrinter.HighResolution)
    print_dialog = QPrintDialog(printer, window)
    if print_dialog.exec() != QDialog.Accepted:
        return False

    painter = QPainter(printer)
    try:
        page_rect = printer.pageLayout().paintRectPixels(printer.resolution())
        qr_size = int(printer.resolution() * 40 * scale / 25.4)
        qr_size = min(qr_size, page_rect.width(), page_rect.height())
        x = page_rect.left() + (page_rect.width() - qr_size) // 2
        y = page_rect.top() + (page_rect.height() - qr_size) // 2
        print_pixmap = pixmap.scaled(
            qr_size, qr_size, Qt.KeepAspectRatio, Qt.FastTransformation
        )
        painter.drawPixmap(x, y, print_pixmap)
    finally:
        painter.end()
    if preview_dialog is not None:
        preview_dialog.accept()
    return True

def print_network_qr_code(window):
    window.show_network_qr_print_dialog()

def show_qr_print_sizes(window):
    window.show_captive_qr_print_dialog()

def print_qr_code(window, scale):
    if not hasattr(window, 'hotspot_qr_pixmap') or window.hotspot_qr_pixmap.isNull():
        QMessageBox.warning(window, "Print QR Code", "The QR code is not ready yet.")
        return
    print_qr_pixmap(window, window.hotspot_qr_pixmap, "Captive Portal QR", scale)

