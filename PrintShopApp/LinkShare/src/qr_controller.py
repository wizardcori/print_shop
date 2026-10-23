"""LinkShare QR generation and background export workflow."""
import filecmp
import os
import threading
import urllib.parse
from io import BytesIO

import qrcode
from Common.network_utils import escape_wifi_qr_field
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter, QPixmap
def update_qr_code(window, run_hotspot_diagnostics):
    current_nic_index = window.nic_combo.currentIndex()
    ip = window.nic_combo.itemData(current_nic_index, Qt.UserRole) or "192.168.137.1"
    hotspot_status = run_hotspot_diagnostics(
        window.hotspot_nic, window.hotspot_network, window.hotspot_gateway
    )
    if hotspot_status['active']:
        ip = window.hotspot_gateway
    zone = window.zone_input.text().strip() or "Default"
    # The file-transfer QR must open the upload page directly.  The root
    # route is the LinkShare portal and redirects to /scan, so using it
    # here makes the QR appear to work while never showing file upload.
    target_url = f"http://{ip}:5000/file_share?{urllib.parse.urlencode({'zone': zone})}"
    window.url_label.setText(f"Generated URL: {target_url}")
    if hasattr(window, 'hotspot_url_label'):
        window.hotspot_url_label.setText(f"Generated URL: {target_url}")

    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qimage = QImage.fromData(buffer.getvalue())
        pixmap = QPixmap.fromImage(qimage)
        window.qr_pixmap = pixmap
        window.qr_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        queue_qr_background_export(window, 
            'network', pixmap,
            f"SSID: {window.hotspot_ssid}\nPassword: {window.hotspot_password or '(not available)'}"
        )
        if hasattr(window, 'hotspot_qr_label'):
            update_hotspot_qr_code(window)
    except Exception as e:
        print(f"QR Gen Error: {e}")

def update_hotspot_qr_code(window):
    """Generate a QR code that opens the captive portal immediately."""
    portal_url = f"http://{window.hotspot_gateway}:5000/scan"
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(portal_url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        window.hotspot_qr_pixmap = QPixmap.fromImage(QImage.fromData(buffer.getvalue()))
        qr_size = min(220, window.hotspot_qr_label.maximumWidth() or 220)
        window.hotspot_qr_label.setPixmap(
            window.hotspot_qr_pixmap.scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        window.hotspot_qr_caption.setText("This QR code is for Internet access requests.")
        window.hotspot_url_label.setText(f"Access Request URL: {portal_url}")

        wifi_ssid = window.hotspot_ssid or 'hbwifi'
        wifi_password = window.hotspot_password or ''
        wifi_type = 'WPA' if wifi_password else 'nopass'
        wifi_payload = (
            f"WIFI:T:{wifi_type};S:{escape_wifi_qr_field(wifi_ssid)};"
            f"P:{escape_wifi_qr_field(wifi_password)};H:false;;"
        )
        wifi_qr = qrcode.QRCode(version=1, box_size=10, border=4)
        wifi_qr.add_data(wifi_payload)
        wifi_qr.make(fit=True)
        wifi_image = wifi_qr.make_image(fill_color="black", back_color="white")
        wifi_buffer = BytesIO()
        wifi_image.save(wifi_buffer, format="PNG")
        network_pixmap = QPixmap.fromImage(QImage.fromData(wifi_buffer.getvalue()))
        window.hotspot_network_pixmap = network_pixmap
        if hasattr(window, 'hotspot_network_qr_label'):
            window.hotspot_network_qr_label.setPixmap(
                network_pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        if hasattr(window, 'hotspot_network_info_label'):
            displayed_password = wifi_password or '(not available)'
            window.hotspot_network_info_label.setText(
                f"SSID: {wifi_ssid}\nPassword: {displayed_password}"
            )
        queue_qr_background_export(window, 
            'captive', window.hotspot_qr_pixmap,
            f"Internet access request\n{portal_url}"
        )
    except Exception as exc:
        window.hotspot_qr_pixmap = QPixmap()
        window.hotspot_qr_label.setText(f"Internet QR generation failed: {exc}")

def queue_qr_background_export(window, qr_type, pixmap, guide_text):
    """Export a changed QR as JPG in a worker without blocking the GUI."""
    if pixmap.isNull():
        return
    image = pixmap.toImage().convertToFormat(QImage.Format_RGB32)
    default_output_dir = os.path.join(os.getcwd(), 'data', 'qr_output')
    output_dir = window.qr_output_dirs.get(qr_type, default_output_dir) or default_output_dir
    if not os.path.isdir(output_dir):
        output_dir = default_output_dir
    os.makedirs(output_dir, exist_ok=True)
    safe_name = 'network_connection_qr' if qr_type == 'network' else 'captive_portal_qr'
    threading.Thread(
        target=_export_qr_jpg_worker,
        args=(window, qr_type, image, guide_text, output_dir, safe_name),
        daemon=True,
    ).start()

def _export_qr_jpg_worker(window, qr_type, qr_image, guide_text, output_dir, safe_name):
    try:
        output_results = []
        changed = False
        for scale in (1, 2, 3, 4):
            qr_size = max(240, 240 * scale)
            scaled_qr = qr_image.scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.FastTransformation)
            margin = max(12, 12 * scale)
            text_font = QFont('Arial', max(12, 12 * scale))
            metrics = QFontMetrics(text_font)
            lines = guide_text.splitlines() or [qr_type]
            line_height = metrics.lineSpacing()
            canvas = QImage(
                qr_size + margin * 2,
                qr_size + line_height * len(lines) + margin * 2,
                QImage.Format_RGB32,
            )
            canvas.fill(Qt.white)
            painter = QPainter(canvas)
            painter.setPen(Qt.black)
            painter.setFont(text_font)
            painter.drawImage(margin, margin, scaled_qr)
            text_y = margin + qr_size + max(2, scale)
            for line in lines:
                painter.drawText(margin, text_y, qr_size, line_height, Qt.AlignHCenter, line)
                text_y += line_height
            painter.end()
            output_path = os.path.join(output_dir, f'{safe_name}_{scale}x.jpg')
            temp_path = f'{output_path}.tmp-{threading.get_ident()}'
            if not canvas.save(temp_path, 'JPG'):
                raise OSError(f'{output_path} 저장에 실패했습니다.')
            if os.path.exists(output_path) and filecmp.cmp(temp_path, output_path, shallow=False):
                os.remove(temp_path)
                output_results.append(f'{scale}x: 변경 없음')
            else:
                os.replace(temp_path, output_path)
                changed = True
                output_results.append(f'{scale}x: 갱신됨 ({output_path})')
        if changed:
            window.qr_export_completed.emit(qr_type, True, '\n'.join(output_results))
    except Exception as exc:
        window.qr_export_completed.emit(qr_type, False, str(exc))

