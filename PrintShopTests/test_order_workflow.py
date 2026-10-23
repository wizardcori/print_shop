"""Unit tests for the single-PC order lifecycle."""
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'PrintShopApp'))

from Common.db import AppDatabase  # noqa: E402
from Common.order_service import OrderService  # noqa: E402
from Common.order_workflow import (  # noqa: E402
    OrderState, PrinterCandidate, choose_printer, estimate_completion_seconds,
    validate_file,
)


class TestOrderWorkflow(unittest.TestCase):
    def test_upload_and_print_completion_are_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.pdf'
            path.write_bytes(b'%PDF-test')
            database = AppDatabase(str(Path(folder) / 'orders.db'))
            service = OrderService(database)
            service.create_from_upload('order-1', [{'path': str(path), 'filename': path.name}])
            self.assertEqual(database.get_order_state('order-1'), OrderState.CONFIGURED.value)
            self.assertEqual(service.mark_print_event(path.name, 'PRINT_COMPLETED'), 'order-1')
            self.assertEqual(database.get_order_state('order-1'), OrderState.COMPLETED.value)

    def test_invalid_file_is_recorded_as_notification(self):
        with tempfile.TemporaryDirectory() as folder:
            database = AppDatabase(str(Path(folder) / 'orders.db'))
            OrderService(database).create_from_upload(
                'order-2', [{'path': str(Path(folder) / 'missing.docx'), 'filename': 'missing.docx'}])
            with database._connect() as connection:
                row = connection.execute('SELECT code FROM notification_logs WHERE order_id = ?',
                                         ('order-2',)).fetchone()
            self.assertEqual(row['code'], 'FILE_MISSING')

    def test_router_and_eta(self):
        printers = [
            PrinterCandidate('color', paper_sizes={'A4'}, color=True, queue_pages=20),
            PrinterCandidate('mono', paper_sizes={'A4'}, color=False, queue_pages=4),
        ]
        self.assertEqual(choose_printer(printers, paper_size='A4', color=False).name, 'mono')
        self.assertEqual(estimate_completion_seconds(10, 10, 20), 60)

    def test_validation_rejects_unsupported_format(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.docx'
            path.write_bytes(b'test')
            self.assertEqual(validate_file(path)[0].code, 'UNSUPPORTED_FORMAT')


if __name__ == '__main__':
    unittest.main(verbosity=2)
