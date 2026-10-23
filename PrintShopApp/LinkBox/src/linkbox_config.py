"""LinkBox-specific settings normalization."""

import os


def apply_saved_defaults(app_settings, current_upload_folder, current_zones, current_save_tabs):
    """Return persisted LinkBox folder/zone/tab defaults."""
    upload_folder = app_settings.get('upload_folder') or current_upload_folder
    zones = app_settings.get('zones') or current_zones
    save_tabs = app_settings.get('save_tabs') or current_save_tabs
    os.makedirs(upload_folder, exist_ok=True)
    return upload_folder, list(zones), list(save_tabs)
