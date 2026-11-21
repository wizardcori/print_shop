from Common.config import FileConfigManager, ConfigType
from Common.path_mgr import PathMgr


class VersionViewerConfig(FileConfigManager):
    """VersionViewer 전용 설정 매니저"""
    file_dir: str = PathMgr.CONFIG_DIR
    file_name: str = "version_viewer_config.ini"
    section: str = "VersionViewer"
    schema = {
        "last_path": {"type": ConfigType.STRING, "default": ""},
        "file_list": {"type": ConfigType.LIST, "default": []},
        "dir_depth": {"type": ConfigType.INTEGER, "default": 3, "min": 0, "max": 10},
        "window_width": {"type": ConfigType.INTEGER, "default": 1350},
        "window_height": {"type": ConfigType.INTEGER, "default": 600},
        "column_order": {"type": ConfigType.LIST, "default": []},
        "column_widths": {"type": ConfigType.LIST, "default": []},
        "hidden_columns": {"type": ConfigType.LIST, "default": []},
    }


viewer_config_instance = VersionViewerConfig()