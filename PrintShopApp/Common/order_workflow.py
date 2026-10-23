"""Order state machine, validation, and printer routing primitives."""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class OrderState(str, Enum):
    UPLOADED = "UPLOADED"
    CONFIGURED = "CONFIGURED"
    USER_CONFIRMED = "USER_CONFIRMED"
    WORKER_REVIEW = "WORKER_REVIEW"
    PRINT_QUEUED = "PRINT_QUEUED"
    PRINTING = "PRINTING"
    COMPLETED = "COMPLETED"
    PAID_HANDOVER = "PAID_HANDOVER"


TRANSITIONS = {
    OrderState.UPLOADED: {OrderState.CONFIGURED},
    OrderState.CONFIGURED: {OrderState.USER_CONFIRMED, OrderState.UPLOADED},
    OrderState.USER_CONFIRMED: {OrderState.WORKER_REVIEW},
    OrderState.WORKER_REVIEW: {OrderState.PRINT_QUEUED, OrderState.CONFIGURED, OrderState.UPLOADED},
    OrderState.PRINT_QUEUED: {OrderState.PRINTING, OrderState.WORKER_REVIEW},
    OrderState.PRINTING: {OrderState.COMPLETED, OrderState.WORKER_REVIEW, OrderState.PRINT_QUEUED},
    OrderState.COMPLETED: {OrderState.PAID_HANDOVER, OrderState.PRINT_QUEUED},
    OrderState.PAID_HANDOVER: set(),
}


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "WARNING"
    file_id: str | None = None


def validate_file(path, *, paper_size="A4", copies=1, max_bytes=250 * 1024 * 1024):
    """Return actionable issues without modifying the uploaded file."""
    file_path = Path(path)
    issues = []
    if not file_path.is_file():
        return [ValidationIssue("FILE_MISSING", "파일을 찾을 수 없습니다.", "ERROR")]
    if file_path.stat().st_size > max_bytes:
        issues.append(ValidationIssue("FILE_TOO_LARGE", "파일 크기가 허용 한도를 초과했습니다.", "ERROR"))
    if copies < 1:
        issues.append(ValidationIssue("INVALID_COPIES", "부수는 1 이상이어야 합니다.", "ERROR"))
    if str(paper_size).upper() not in {"A4", "A3", "B4", "LETTER"}:
        issues.append(ValidationIssue("UNSUPPORTED_PAPER", "지원하지 않는 용지 규격입니다.", "ERROR"))
    if file_path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        issues.append(ValidationIssue("UNSUPPORTED_FORMAT", "인쇄 가능한 파일 형식이 아닙니다."))
    return issues


@dataclass
class PrinterCandidate:
    name: str
    status: str = "AVAILABLE"
    paper_sizes: set[str] = field(default_factory=set)
    color: bool = True
    queue_pages: int = 0
    ppm: float = 20.0


def choose_printer(printers, *, paper_size="A4", color=False):
    """Choose the shortest eligible queue, preferring a mono-only device for mono jobs."""
    eligible = [p for p in printers if str(p.status).upper() == "AVAILABLE"
                and str(paper_size).upper() in {s.upper() for s in p.paper_sizes}
                and (color is False or p.color)]
    if not eligible:
        return None
    return min(eligible, key=lambda p: (0 if (not color and not p.color) else 1, p.queue_pages))


def estimate_completion_seconds(queue_pages, pages, ppm, finishing_seconds=0):
    if ppm <= 0:
        raise ValueError("ppm must be positive")
    return max(0, int((queue_pages + pages) * 60 / ppm + finishing_seconds))
