"""Integrated LinkBox file upload and transfer-status service."""

from __future__ import annotations

from dataclasses import dataclass
import datetime
import json
import os
import re
import threading
from typing import Any, Callable
from flask import Flask, make_response, render_template, request


@dataclass
class FileShareDependencies:
    upload_folder: str
    default_colors: list[str]
    runtime_settings: dict[str, Any]
    database: Any
    get_client_identity: Callable[..., Any]
    format_size: Callable[[int], str]
    safe_folder_part: Callable[[str, str], str]
    client_metadata_map: dict[str, Any]
    transfer_records: dict[str, list[dict[str, Any]]]
    transfer_versions: dict[str, int]
    transfer_acks: dict[str, int]
    transfer_condition: threading.Condition
    processed_uploads: dict[str, Any]
    transfer_callback: Callable[..., Any] | None = None
    update_signal: Any = None
    order_service: Any = None
    client_cookie_name: str = 'printshop_client_token'


class FileShareService:
    """Own LinkBox HTTP behavior while receiving app dependencies explicitly."""

    def __init__(self, dependencies: FileShareDependencies) -> None:
        self.d = dependencies

    def register(self, app: Flask) -> None:
        """Register all LinkBox file-share endpoints on the integrated Flask app."""
        app.add_url_rule('/file_share', 'file_share_page', self.page)
        app.add_url_rule('/upload', 'file_share_upload', self.upload, methods=['POST'])
        app.add_url_rule('/transfer_status', 'transfer_status', self.status)
        app.add_url_rule('/transfer_ack', 'transfer_ack', self.ack, methods=['POST'])
        app.add_url_rule('/transfer_update', 'transfer_update', self.update, methods=['POST'])

    def page(self):
        """Render the customer upload page."""
        zone = request.args.get('zone', 'Default')
        color_options = self.d.runtime_settings.get('color_options', self.d.default_colors)
        return render_template('file_share.html', zone=zone, color_options=color_options)

    def upload(self):
        """Persist uploaded files and create the corresponding order."""
        zone = request.args.get('zone', 'Default')
        files = [item for item in request.files.getlist('file') if item and item.filename]
        if not files:
            return {'error': 'No files selected'}, 400

        copies = self._json_list('copies')
        colors = self._json_list('colors')
        token, token_id, client_ip, device_name = self.d.get_client_identity()
        upload_id = (request.headers.get('X-Upload-Id') or '').strip()[:100]

        if upload_id and (token_id, upload_id) in self.d.processed_uploads:
            previous = self.d.processed_uploads[(token_id, upload_id)]
            response = make_response(previous['payload'], previous['status'])
            return self._cookie(response, token)

        metadata = self.d.client_metadata_map.get(token_id, {})
        user_name = metadata.get('user_name', '').strip() or device_name or 'Guest'
        safe_identity = re.sub(r'[^A-Za-z0-9_.-]', '_', token_id or client_ip)
        transfer_id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')

        folder_name = (
            f"{self.d.safe_folder_part(zone, 'Default')}_"
            f"{self.d.safe_folder_part(user_name, 'Guest')}_"
            f"{self.d.safe_folder_part(client_ip, 'UnknownIP')}_"
            f"{transfer_id}"
        )
        folder = os.path.join(self.d.upload_folder, folder_name)
        os.makedirs(folder, exist_ok=True)

        records = []
        received = []
        failed = 0
        allowed_colors = self.d.runtime_settings.get('color_options', self.d.default_colors)

        for index, uploaded in enumerate(files):
            try:
                copy_count = max(0, min(999, int(copies[index])))
            except (IndexError, TypeError, ValueError):
                copy_count = 1

            if index < len(colors):
                color = str(colors[index]).strip()
            else:
                color = allowed_colors[0]
            if color not in allowed_colors:
                color = allowed_colors[0]

            filename = os.path.basename(uploaded.filename)
            path = os.path.join(folder, filename)
            try:
                uploaded.save(path)
                size = self.d.format_size(os.path.getsize(path))
            except OSError:
                failed += 1
                continue

            received.append((
                user_name,
                '',
                token_id[:12],
                zone,
                filename,
                copy_count,
                size,
                datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),
                'Completed (100%)',
                color,
            ))
            records.append({
                'folder': folder,
                'filename': filename,
                'copies': copy_count,
                'user_name': user_name,
                'user_info': 'Unknown',
                'cookie': token_id[:12],
                'zone': zone,
                'size': size,
                'received_time': datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),
                'status': 'Completed (100%)',
                'color': color,
                'task_completed': False,
            })

        if records and self.d.order_service:
            self.d.order_service.create_from_upload(
                transfer_id,
                [dict(item, path=os.path.join(folder, item['filename'])) for item in records],
            )

        with self.d.transfer_condition:
            self.d.transfer_records.setdefault(token_id, []).extend(records)
            self.d.transfer_versions[token_id] = self.d.transfer_versions.get(token_id, 0) + 1
            self.d.transfer_condition.notify_all()

        if self.d.transfer_callback:
            self.d.transfer_callback(received, folder, safe_identity)

        payload = {
            'ok': bool(records),
            'count': len(records),
            'failed_count': failed,
            'folder': folder,
            'records': records,
            'error': '' if records else 'All files failed to upload',
        }
        status = 200 if records else 500

        if upload_id:
            self.d.processed_uploads[(token_id, upload_id)] = {'payload': payload, 'status': status}

        return self._cookie(make_response(payload, status), token)

    def status(self):
        """Return the current user-scoped transfer records."""
        token, token_id, _client_ip, _device = self.d.get_client_identity()
        try:
            since = int(request.args.get('since', 0))
        except (TypeError, ValueError):
            since = 0

        with self.d.transfer_condition:
            version = self.d.transfer_versions.get(token_id, 0)
            if version <= since:
                self.d.transfer_condition.wait(timeout=25)
            version = self.d.transfer_versions.get(token_id, 0)
            records = [
                dict(item) for item in self.d.transfer_records.get(token_id, [])
                if os.path.isfile(os.path.join(item.get('folder', ''), item.get('filename', '')))
            ]

        return self._cookie(make_response({
            'version': version,
            'changed': version != since,
            'records': records,
        }), token)

    def ack(self):
        """Acknowledge a transfer version for the current client."""
        _token, token_id, _ip, _device = self.d.get_client_identity()
        payload = request.get_json(silent=True) or {}
        try:
            version = max(0, int(payload.get('version', 0)))
        except (TypeError, ValueError):
            version = 0

        self.d.transfer_acks[token_id] = version
        return {'ok': True, 'version': version}

    def update(self):
        """Update copy/color options for one uploaded file."""
        _token, token_id, _ip, _device = self.d.get_client_identity()
        payload = request.get_json(silent=True) or {}
        filename = str(payload.get('filename', '')).strip()
        folder = str(payload.get('folder', '')).strip()

        try:
            copies = max(0, min(999, int(payload.get('copies', 1))))
        except (TypeError, ValueError):
            copies = 1

        color = str(payload.get('color', '')).strip()
        allowed_colors = self.d.runtime_settings.get('color_options', self.d.default_colors)
        if color not in allowed_colors:
            color = self.d.default_colors[0]

        updated = False
        with self.d.transfer_condition:
            for record in self.d.transfer_records.get(token_id, []):
                if record.get('folder') == folder and record.get('filename') == filename:
                    record.update(copies=copies, color=color)
                    updated = True

            if updated:
                if self.d.database:
                    self.d.database.update_transfer_log(folder, filename, copies=copies, color=color)
                self.d.transfer_versions[token_id] = self.d.transfer_versions.get(token_id, 0) + 1
                self.d.transfer_condition.notify_all()

        if updated and self.d.update_signal:
            self.d.update_signal.emit(folder, filename, copies, color)

        return {'ok': updated}

    @staticmethod
    def _json_list(name: str) -> list[Any]:
        try:
            value = json.loads(request.form.get(name, '[]'))
            return value if isinstance(value, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def _cookie(self, response, token: str):
        response.set_cookie(
            self.d.client_cookie_name,
            token,
            max_age=2592000,
            httponly=True,
            samesite='Lax',
        )
        return response
