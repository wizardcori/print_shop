"""Application service connecting uploads and printer events to order state."""
from datetime import datetime, timezone
from typing import Any
import uuid

from .order_workflow import OrderState, ValidationIssue, validate_file


class OrderService:
    """Coordinate the single-PC order lifecycle through the SQLite repository."""

    def __init__(self, database: Any) -> None:
        self.database = database

    def create_from_upload(self, transfer_id: str, files: list[dict[str, Any]]) -> str:
        """Create an order and persist uploaded files and validation notices."""
        now = datetime.now(timezone.utc).isoformat()
        order_id = str(transfer_id)
        self.database.create_order(order_id, state=OrderState.UPLOADED.value, created_at=now)
        for item in files:
            issues = validate_file(item['path'], paper_size=item.get('paper_size', 'A4'),
                                   copies=int(item.get('copies', 1)))
            issue_data = [issue.__dict__ for issue in issues]
            self.database.add_order_file(
                str(uuid.uuid4()), order_id, item['filename'], item, issue_data)
            for issue in issues:
                self.database.add_notification(
                    order_id, issue.code, issue.message, issue.severity,
                    created_at=now)
        if files:
            self.database.transition_order(order_id, OrderState.CONFIGURED.value,
                                           changed_by='upload', reason='upload options saved',
                                           timestamp=now)
        return order_id

    def mark_print_event(self, filename: str, status: str, changed_by: str = 'printer-monitor') -> str | None:
        """Advance the matching order for a detected or completed print event."""
        order_ids = self.database.find_order_ids_for_filename(filename)
        if not order_ids:
            return None
        order_id = order_ids[-1]
        now = datetime.now(timezone.utc).isoformat()
        current = self.database.get_order_state(order_id)
        if str(status).upper() == 'PRINT_COMPLETED':
            for target in (OrderState.USER_CONFIRMED, OrderState.WORKER_REVIEW,
                           OrderState.PRINT_QUEUED, OrderState.PRINTING,
                           OrderState.COMPLETED):
                current = self._advance_if_possible(order_id, current, target, changed_by, now)
        elif current == OrderState.CONFIGURED.value:
            for target in (OrderState.USER_CONFIRMED, OrderState.WORKER_REVIEW,
                           OrderState.PRINT_QUEUED, OrderState.PRINTING):
                current = self._advance_if_possible(order_id, current, target, changed_by, now)
        return order_id

    def _advance_if_possible(self, order_id: str, current: str, target: OrderState,
                             changed_by: str, timestamp: str) -> str:
        if current == target.value:
            return current
        try:
            return self.database.transition_order(order_id, target.value, changed_by,
                                                  'printer event', timestamp)
        except ValueError:
            return current
