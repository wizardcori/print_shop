import datetime as dt
import configparser
import json
import os
import socket
import sqlite3
import sys
import urllib.request
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout,
)


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def format_size(size):
    size = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


class ManualCheck(QDialog):
    def __init__(self, title, instructions, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<h2>{title}</h2>"))
        text = QLabel(instructions)
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addWidget(QLabel("Notes (optional):"))
        self.notes = QLineEdit()
        layout.addWidget(self.notes)
        buttons = QDialogButtonBox()
        self.pass_button = buttons.addButton("Pass", QDialogButtonBox.AcceptRole)
        self.fail_button = buttons.addButton("Fail", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result(self):
        return {"result": "PASS" if self.exec() == QDialog.Accepted else "FAIL",
                "note": self.notes.text().strip()}


def check_http(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, "HTTP endpoint is reachable"
    except Exception as exc:
        return None, str(exc)


def run_automatic_checks(hostname="192.168.137.1", port=5000):
    """Run checks that do not require a person or a physical phone."""
    checks = []
    try:
        with socket.create_connection((hostname, port), timeout=3):
            checks.append({"step": "Hotspot endpoint",
                           "note": f"{hostname}:{port} reachable",
                           "result": "PASS"})
    except OSError as exc:
        checks.append({"step": "Hotspot endpoint", "note": str(exc), "result": "FAIL"})
    status, detail = check_http(f"http://{hostname}:{port}/scan")
    checks.append({"step": "QR web endpoint", "note": detail,
                   "result": "PASS" if status == 200 else "FAIL"})
    checks.append(check_hotspot_config(hostname))
    checks.append(check_database())
    checks.append(check_transfer_files())
    checks.append(check_sync_endpoint(hostname, port))
    checks.append(check_admin_records())
    return add_expected_actual(checks)


def add_expected_actual(items):
    expected_by_step = {
        "Hotspot endpoint": "TCP port is reachable",
        "QR web endpoint": "HTTP 200",
        "Hotspot SSID and IP": "SSID is configured and IP is valid",
        "DB storage": "Required SQLite tables exist",
        "File existence and size": "All persisted files exist with matching sizes",
        "User synchronization data": "Transfer status endpoint responds",
        "Administrator record": "At least one transfer_log record exists",
    }
    for item in items:
        item["expected"] = expected_by_step.get(item["step"], "PASS")
        item["actual"] = item["result"]
    return items


def check_hotspot_config(hostname):
    settings_path = Path(os.environ.get(
        "PRINTSHOP_SETTINGS_FILE",
        str(ROOT.parent / "PrintShopApp" / "data" / "wifi_approval_settings.ini"),
    ))
    configured_ssid = ""
    if settings_path.exists():
        parser = configparser.ConfigParser()
        parser.read(settings_path, encoding="utf-8")
        configured_ssid = parser.get("Hotspot", "ssid", fallback="").strip()
    ip_ok = bool(hostname and socket.inet_aton(hostname))
    note = f"SSID={configured_ssid or 'not configured'}, IP={hostname}"
    return {"step": "Hotspot SSID and IP", "note": note,
            "result": "PASS" if ip_ok and configured_ssid else "FAIL"}


def _database_path():
    return Path(os.environ.get(
        "PRINTSHOP_DATABASE",
        str(ROOT.parent / "PrintShopApp" / "data" / "db" / "wifi_approval.db"),
    ))


def check_database():
    path = _database_path()
    if not path.exists():
        return {"step": "DB storage", "note": f"Missing: {path}", "result": "FAIL"}
    try:
        with sqlite3.connect(path) as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"sessions", "usage_events", "file_transfers", "transfer_log"}
        missing = required - tables
        return {"step": "DB storage", "note": f"SQLite tables={len(tables)}",
                "result": "PASS" if not missing else "FAIL"}
    except sqlite3.Error as exc:
        return {"step": "DB storage", "note": str(exc), "result": "FAIL"}


def check_transfer_files():
    path = _database_path()
    if not path.exists():
        return {"step": "File existence and size", "note": "DB is unavailable", "result": "FAIL"}
    checked = 0
    invalid = []
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute("SELECT target_folder, data_json FROM transfer_log")
            for folder, data_json in rows:
                record = json.loads(data_json)
                filename = str(record.get("filename", ""))
                if not filename or filename.startswith("summary_") or filename == "transfer_summary.txt":
                    continue
                checked += 1
                file_path = Path(folder) / filename
                if not file_path.is_file():
                    invalid.append(f"missing:{filename}")
                    continue
                stored = str(record.get("size", "")).strip()
                if stored and stored != format_size(file_path.stat().st_size):
                    invalid.append(f"size:{filename}")
        note = f"checked={checked}, invalid={len(invalid)}"
        return {"step": "File existence and size", "note": note,
                "result": "PASS" if checked and not invalid else "FAIL"}
    except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        return {"step": "File existence and size", "note": str(exc), "result": "FAIL"}


def check_sync_endpoint(hostname, port):
    status, detail = check_http(f"http://{hostname}:{port}/transfer_status")
    return {"step": "User synchronization data", "note": detail,
            "result": "PASS" if status in {200, 204, 400} else "FAIL"}


def check_admin_records():
    path = _database_path()
    if not path.exists():
        return {"step": "Administrator record", "note": "DB is unavailable", "result": "FAIL"}
    try:
        with sqlite3.connect(path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM transfer_log").fetchone()[0]
        return {"step": "Administrator record", "note": f"transfer_log rows={count}",
                "result": "PASS" if count > 0 else "FAIL"}
    except sqlite3.Error as exc:
        return {"step": "Administrator record", "note": str(exc), "result": "FAIL"}


def run():
    app = QApplication(sys.argv)
    started = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    results.extend(run_automatic_checks())

    for title, instructions in [
        ("Wi-Fi Connection", "Connect a real phone to the PrintShop hotspot, then select Pass or Fail."),
        ("QR Camera Scan", "Scan the QR code with the phone camera and confirm the URL opens."),
        ("Mobile Screen", "Confirm the upload page is displayed correctly on the phone."),
        ("File Selection and Upload", "Select a file on the phone, upload it, and confirm completion."),
        ("Administrator Screen", "Confirm the uploaded record appears in the administrator screen."),
        ("Filename and Size", "Compare the filename and displayed size with the selected file."),
        ("Color and Copies", "Confirm the color option and copy count are correct."),
        ("Completion Status", "Confirm the record completion status is displayed correctly."),
    ]:
        manual_result = ManualCheck(title, instructions).result()
        results.append({"step": title, "note": manual_result["note"],
                        "result": manual_result["result"],
                        "expected": "PASS",
                        "actual": manual_result["result"]})

    RESULTS.mkdir(exist_ok=True)
    output = RESULTS / f"{started}.json"
    output.write_text(json.dumps({"started": started, "results": results},
                                 indent=2, ensure_ascii=False), encoding="utf-8")
    failed = [item for item in results if item["result"] == "FAIL"]
    QMessageBox.information(None, "Test Complete",
                            f"Test finished: {'FAIL' if failed else 'PASS'}\n{output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run())
