"""Shared LinkBox file-transfer formatting and path helpers."""

import re


def format_size(size_bytes):
    """Format a received file size for the LinkBox transfer table."""
    if size_bytes < 1024:
        return f"{size_bytes} Bytes"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def safe_folder_part(value, fallback='Unknown'):
    """Make a user-controlled value safe and readable in a Windows path."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or '').strip())
    cleaned = cleaned.rstrip('. ')
    return cleaned[:80] or fallback
