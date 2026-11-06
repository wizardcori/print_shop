from typing import Dict, Any, List, Optional
from Common.config import FileConfigManager, ConfigType, CONFIG_DIR
from Common.log import logd, loge

try:
    from PyQt6.QtWidgets import QWidget, QSplitter, QApplication, QMainWindow
    from PyQt6.QtCore import QRect
except ImportError:
    try:
        from PySide6.QtWidgets import QWidget, QSplitter, QApplication, QMainWindow
        from PySide6.QtCore import QRect
    except ImportError:
        QWidget = QSplitter = QApplication = QMainWindow = QRect = None


class GeometryConfig(FileConfigManager):
    file_dir: str = CONFIG_DIR
    file_name: str = "geometry.ini"
    config_encoding: str = "utf-8"
    section: str = "General"

    def _ensure_schema_key(self, key: str, data_type: Any, default_value: Any):
        if key not in self.schema:
            self.schema[key] = {
                "type": data_type,
                "default": default_value
            }
            if not self.config.has_option(self.section, key):
                self.config.set(self.section, key, str(default_value))
            logd(f"[{self.section}] Added new schema key '{key}' with default: {default_value}")


#############################################################################################################
class GeometryManager:
    """
    self.config 충돌을 방지하기 위해 내부에 geometry_config 인스턴스를 소유하는 컴포지션 구조
    """
    def __init__(self, section_name: Optional[str] = None):
        self._section_name = section_name or self.__class__.__name__
        
        # 동적으로 섹션명이 할당되는 지오메트리 전용 Config 생성
        class DynamicGeometryConfig(GeometryConfig):
            section = self._section_name
            
        self.geometry_config = DynamicGeometryConfig()

    def save_window_geometry(self, window: QWidget):
        if window is None:
            loge(f"[{self.geometry_config.section}] Cannot save window geometry: Provided window is None.")
            return

        geom = window.geometry()
        val = [geom.x(), geom.y(), geom.width(), geom.height()]
        key = "window_geometry"
        self.geometry_config._ensure_schema_key(key, ConfigType.LIST, val)
        self.geometry_config.set(key, val)
        logd(f"[{self.geometry_config.section}] Saved window geometry: x={geom.x()}, y={geom.y()}, w={geom.width()}, h={geom.height()}")

    def load_window_geometry(self, window: QWidget, default_geometry: Optional[List[int]] = None):
        if window is None:
            loge(f"[{self.geometry_config.section}] Cannot load window geometry: Provided window is None.")
            return

        key = "window_geometry"
        if key not in self.geometry_config.schema:
            logd(f"[{self.geometry_config.section}] '{key}' not found in schema. Skipping geometry load.")
            return

        val = self.geometry_config.get(key)
        if not isinstance(val, list) or len(val) != 4:
            loge(f"[{self.geometry_config.section}] Invalid geometry format in config: {val}. Expected a list of 4 integers.")
            return

        x, y, w, h = val

        if not self._is_window_visible_on_screen(x, y, w, h):
            default_val = default_geometry or self.geometry_config.schema[key].get("default", [100, 100, 1200, 800])
            if isinstance(default_val, list) and len(default_val) == 4:
                logd(f"[{self.geometry_config.section}] Window position ({x}, {y}, {w}, {h}) is off-screen or insufficiently visible. Fallback to default: {default_val}")
                x, y, w, h = default_val
                self.geometry_config.set(key, [x, y, w, h])
            else:
                loge(f"[{self.geometry_config.section}] Invalid default geometry format: {default_val}")

        window.setGeometry(x, y, w, h)
        logd(f"[{self.geometry_config.section}] Applied window geometry: x={x}, y={y}, w={w}, h={h}")

    def _is_window_visible_on_screen(self, x: int, y: int, w: int, h: int) -> bool:
        if QApplication is None:
            logd(f"[{self.geometry_config.section}] QApplication instance not available. Skipping screen visibility check.")
            return True

        target_rect = QRect(x, y, w, h)
        target_area = target_rect.width() * target_rect.height()
        if target_area <= 0:
            loge(f"[{self.geometry_config.section}] Invalid window dimensions: width={w}, height={h}.")
            return False

        screens = QApplication.screens()
        max_visible_area = 0

        for screen in screens:
            screen_rect = screen.availableGeometry()
            intersection = target_rect.intersected(screen_rect)
            if not intersection.isEmpty():
                intersected_area = intersection.width() * intersection.height()
                if intersected_area > max_visible_area:
                    max_visible_area = intersected_area

        visible_ratio = max_visible_area / target_area
        is_visible = visible_ratio >= 0.2

        if not is_visible:
            logd(f"[{self.geometry_config.section}] Window visibility ratio ({visible_ratio:.2%}) is below threshold (20%).")

        return is_visible

    def clean_unused_splitters(self, parent_widget: QWidget, suffix: str = "_sizes"):
        if parent_widget is None:
            loge(f"[{self.geometry_config.section}] Cannot clean splitters: Parent widget is None.")
            return

        splitters = parent_widget.findChildren(QSplitter)
        valid_names = {splitter.objectName() for splitter in splitters if splitter.objectName()}
        
        cfg = self.geometry_config
        section = cfg.section
        
        if not cfg.config.has_section(section):
            return
            
        existing_options = cfg.config.options(section)
        removed_keys = []
        
        for option in existing_options:
            if option.endswith(suffix):
                base_name = option[:-len(suffix)]
                if base_name not in valid_names:
                    if option in cfg.schema:
                        del cfg.schema[option]
                    cfg.config.remove_option(section, option)
                    removed_keys.append(option)
        
        if removed_keys:
            cfg.save()
            logd(f"[{section}] Cleaned unused splitter configurations: {removed_keys}")

    def save_multiple_splitters(self, *splitters: QSplitter, prefix: str = "splitter"):
        for index, splitter in enumerate(splitters):
            if splitter is None:
                continue
            sizes = splitter.sizes()
            key = f"{prefix}_{index}_sizes"
            self.geometry_config._ensure_schema_key(key, ConfigType.LIST, sizes)
            self.geometry_config.set(key, sizes)
            logd(f"[{self.geometry_config.section}] Saved splitter sizes for '{key}': {sizes}")

    def load_multiple_splitters(self, *splitters: QSplitter, prefix: str = "splitter"):
        for index, splitter in enumerate(splitters):
            if splitter is None:
                continue
            key = f"{prefix}_{index}_sizes"
            if key in self.geometry_config.schema:
                sizes = self.geometry_config.get(key)
                if isinstance(sizes, list) and len(sizes) > 0:
                    splitter.setSizes(sizes)
                    logd(f"[{self.geometry_config.section}] Loaded splitter sizes for '{key}': {sizes}")
                else:
                    loge(f"[{self.geometry_config.section}] Invalid or empty sizes data for '{key}': {sizes}")

    def auto_load_splitters(self, parent_widget: QWidget, prefix: str = "splitter"):
        if parent_widget is None:
            loge(f"[{self.geometry_config.section}] Cannot auto load splitters: Parent widget is None.")
            return
        splitters = parent_widget.findChildren(QSplitter)
        if splitters:
            self.load_multiple_splitters(*splitters, prefix=prefix)

    def auto_save_splitters(self, parent_widget: QWidget, prefix: str = "splitter"):
        if parent_widget is None:
            loge(f"[{self.geometry_config.section}] Cannot auto save splitters: Parent widget is None.")
            return
        splitters = parent_widget.findChildren(QSplitter)
        if splitters:
            self.save_multiple_splitters(*splitters, prefix=prefix)

    def save_splitters_by_name(self, parent_widget: QWidget):
        if parent_widget is None:
            loge(f"[{self.geometry_config.section}] Cannot save splitters by name: Parent widget is None.")
            return

        splitters = parent_widget.findChildren(QSplitter)
        for splitter in splitters:
            name = splitter.objectName()
            if not name:
                logd(f"[{self.geometry_config.section}] Skipping unnamed splitter instance.")
                continue
                
            sizes = splitter.sizes()
            key = f"{name}_sizes"
            
            self.geometry_config._ensure_schema_key(key, ConfigType.LIST, sizes)
            self.geometry_config.set(key, sizes)
            logd(f"[{self.geometry_config.section}] Saved named splitter '{name}': {sizes}")

    def load_splitters_by_name(self, parent_widget: QWidget):
        if parent_widget is None:
            loge(f"[{self.geometry_config.section}] Cannot load splitters by name: Parent widget is None.")
            return

        self.clean_unused_splitters(parent_widget)        

        splitters = parent_widget.findChildren(QSplitter)
        for splitter in splitters:
            name = splitter.objectName()
            if not name:
                continue
                
            key = f"{name}_sizes"
            if key in self.geometry_config.schema:
                sizes = self.geometry_config.get(key)
                if isinstance(sizes, list) and len(sizes) > 0:
                    splitter.setSizes(sizes)
                    logd(f"[{self.geometry_config.section}] Loaded named splitter '{name}': {sizes}")
                else:
                    loge(f"[{self.geometry_config.section}] Invalid or empty sizes data for named splitter '{key}': {sizes}")


#############################################################################################################
class AutoGeometryWidget(QWidget, GeometryManager):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        GeometryManager.__init__(self, self.__class__.__name__)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_window_geometry(self)
        self.load_splitters_by_name(self)

    def hideEvent(self, event):
        self.save_window_geometry(self)
        self.save_splitters_by_name(self)
        super().hideEvent(event)

    def closeEvent(self, event):
        self.save_window_geometry(self)
        self.save_splitters_by_name(self)
        super().closeEvent(event)                    


#############################################################################################################
class AutoGeometryMainWindow(QMainWindow, GeometryManager):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)
        GeometryManager.__init__(self, self.__class__.__name__)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_window_geometry(self)
        self.load_splitters_by_name(self)

    def hideEvent(self, event):
        self.save_window_geometry(self)
        self.save_splitters_by_name(self)
        super().hideEvent(event)

    def closeEvent(self, event):
        self.save_window_geometry(self)
        self.save_splitters_by_name(self)
        super().closeEvent(event)