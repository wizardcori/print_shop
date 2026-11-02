"""
Settings package initialization.
Imports all feature-owned config/UI modules so that register_settings_tab 
registers them automatically.
"""

from . import general_settings
from . import env_settings
from . import operator_settings
