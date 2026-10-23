"""Shared interfaces used by the PrintShop service modules.

The integrated application owns one context and injects it into LinkBox and
LinkShare services.  Services must use this context instead of importing
state from ``main_app``; this keeps the future route extraction one-way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Any, Callable


@dataclass
class TransferState:
    """Thread-safe state shared by the file-transfer routes and UI."""

    records_by_client: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    change_versions: dict[str, int] = field(default_factory=dict)
    ack_versions: dict[str, int] = field(default_factory=dict)
    processed_uploads: dict[str, Any] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    changed: threading.Condition = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.changed = threading.Condition(self.lock)


@dataclass
class ServiceContext:
    """Dependency boundary between the shell and feature services."""

    database: Any = None
    settings: dict[str, Any] = field(default_factory=dict)
    signals: Any = None
    transfer: TransferState = field(default_factory=TransferState)
    transfer_callback: Callable[..., Any] | None = None

    def update_settings(self, **values: Any) -> None:
        self.settings.update(values)

