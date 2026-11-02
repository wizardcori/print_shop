"""Route registration for the integrated LinkBox file-share service."""

from collections.abc import Callable
from typing import Any


def register_file_share_routes(app: Any, handlers: dict[str, Callable[..., Any]]) -> None:
    app.add_url_rule('/file_share', 'file_share_page', handlers['file_share_page'])
    app.add_url_rule('/upload', 'file_share_upload', handlers['file_share_upload'], methods=['POST'])
    app.add_url_rule('/transfer_status', 'transfer_status', handlers['transfer_status'])
    app.add_url_rule('/transfer_ack', 'transfer_ack', handlers['transfer_ack'], methods=['POST'])
    app.add_url_rule('/transfer_update', 'transfer_update', handlers['transfer_update'], methods=['POST'])