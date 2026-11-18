"""LinkBox Python source package."""
"""
Settings package initialization.
Imports all feature-owned config/UI modules so that register_settings_tab 
registers them automatically.
"""

from . import update_service_protocol
__all__ = [
    "update_service_protocol",
]
