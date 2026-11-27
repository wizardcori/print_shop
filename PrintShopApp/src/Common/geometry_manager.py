from typing import Dict, Any, List, Optional
from Common.path_mgr import PathMgr
from Common.config import FileConfigManager, ConfigType
from Common.log import logd, loge

from Common.log import set_file_tag

set_file_tag("GEO")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QDialog,
        QSplitter,
        QApplication,
        QMainWindow,
    )
    from PySide6.QtCore import QRect
except ImportError:
    QWidget = QDialog = QSplitter = QApplication = QMainWindow = QRect = None


class GeometryConfig(FileConfigManager):
    file_dir: str = PathMgr.CONFIG_DIR
    file_name: str = "geometry.ini"
    config_encoding: str = "utf-8"
    section: str = "General"

    def _ensure_schema_key(self, key: str, data_type: Any, default_value: Any):
        if key not in self.schema:
            self.schema[key] = {"type": data_type, "default": default_value}
            if not self.config.has_option(self.section, key):
                self.config.set(self.section, key, str(default_value))
            logd(f"[{self.section}] Added new schema key '{key}' with default: {default_value}")


#################################################################################
# 1. GeometryManager (오직 창 위치 및 크기만 관리)
#################################################################################
class GeometryManager:
    def __init__(self, section_name: Optional[str] = None):
        self._section_name = section_name or self.__class__.__name__

        class DynamicGeometryConfig(GeometryConfig):
            section = self._section_name

        self.geometry_config = DynamicGeometryConfig()

    def save_window_geometry(self, window: QWidget):
        if window is None:
            loge(
                f"[{self.geometry_config.section}] Cannot save window geometry: Provided window is None."
            )
            return

        geom = window.geometry()
        val = [geom.x(), geom.y(), geom.width(), geom.height()]
        key = "window_geometry"
        self.geometry_config._ensure_schema_key(key, ConfigType.LIST, val)
        self.geometry_config.set(key, val)
        logd(
            f"[{self.geometry_config.section}] Saved window geometry: x={geom.x()}, y={geom.y()}, w={geom.width()}, h={geom.height()}"
        )

    def load_window_geometry(self, window: QWidget, default_geometry: Optional[List[int]] = None):
        if window is None:
            loge(
                f"[{self.geometry_config.section}] Cannot load window geometry: Provided window is None."
            )
            return

        key = "window_geometry"
        if key not in self.geometry_config.schema:
            if default_geometry and len(default_geometry) == 4:
                self.geometry_config._ensure_schema_key(
                    key, ConfigType.LIST, list(default_geometry)
                )
            else:
                logd(
                    f"[{self.geometry_config.section}] '{key}' not found in schema. Skipping geometry load."
                )
                return

        val = self.geometry_config.get(key)
        # 튜플 반환 대비 안전한 list 캐스팅 추가
        if isinstance(val, tuple):
            val = list(val)

        if not isinstance(val, list) or len(val) != 4:
            loge(f"[{self.geometry_config.section}] Invalid geometry format in config: {val}.")
            return

        x, y, w, h = val

        # 1. 기존 화면 가시성 검증
        if not self._is_window_visible_on_screen(x, y, w, h):
            default_val = default_geometry or self.geometry_config.schema[key].get(
                "default", [100, 100, 1200, 800]
            )
            if isinstance(default_val, tuple):
                default_val = list(default_val)
            if isinstance(default_val, list) and len(default_val) == 4:
                logd(
                    f"[{self.geometry_config.section}] Window position off-screen. Fallback to default: {default_val}"
                )
                x, y, w, h = default_val
                self.geometry_config.set(key, [x, y, w, h])

        # 2. 타이틀바가 화면 위쪽 밖으로 나간 경우 강제 보정
        if QApplication is not None:
            target_rect = QRect(x, y, w, h)
            current_screen = (
                QApplication.screenAt(target_rect.center()) or QApplication.primaryScreen()
            )
            if current_screen:
                screen_geom = current_screen.availableGeometry()

                if y < screen_geom.top():
                    y = screen_geom.top()

                if y > screen_geom.bottom() - 40:
                    y = screen_geom.bottom() - 40

                if x + w < screen_geom.left() + 50:
                    x = screen_geom.left()
                elif x > screen_geom.right() - 50:
                    x = screen_geom.right() - w

        # 3. 활성화된 모든 스크린 통합 가용 영역 검증
        if QApplication is not None:
            desktop_rect = QRect()
            for screen in QApplication.screens():
                desktop_rect = desktop_rect.united(screen.availableGeometry())

            if not desktop_rect.contains(x, y + 20):
                logd(
                    f"[{self.geometry_config.section}] Saved geometry [{x}, {y}, {w}, {h}] is out of active screen bounds. Resetting to default."
                )
                default_val = default_geometry or [100, 100, 640, 480]
                if isinstance(default_val, tuple):
                    default_val = list(default_val)
                if isinstance(default_val, list) and len(default_val) == 4:
                    x, y, w, h = default_val
                    self.geometry_config.set(key, [x, y, w, h])

        window.setGeometry(x, y, w, h)
        logd(
            f"[{self.geometry_config.section}] Applied window geometry: x={x}, y={y}, w={w}, h={h}"
        )

    def _is_window_visible_on_screen(self, x: int, y: int, w: int, h: int) -> bool:
        if QApplication is None:
            return True

        target_rect = QRect(x, y, w, h)
        target_area = target_rect.width() * target_rect.height()
        if target_area <= 0:
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

        return (max_visible_area / target_area) >= 0.2


#################################################################################
# 2. SplitterManager (오직 내부 스플릿터 크기만 관리 + 직계 자식 필터링)
#################################################################################
class SplitterManager:
    def __init__(self, section_name: Optional[str] = None):
        self._section_name = section_name or self.__class__.__name__

        class DynamicSplitterConfig(GeometryConfig):
            section = self._section_name

        self.geometry_config = DynamicSplitterConfig()

    def clean_unused_splitters(self, parent_widget: QWidget, suffix: str = "_sizes"):
        if parent_widget is None:
            return

        splitters = [
            c for c in parent_widget.findChildren(QSplitter) if c.parent() == parent_widget
        ]
        valid_names = {s.objectName() for s in splitters if s.objectName()}

        cfg = self.geometry_config
        section = cfg.section
        if not cfg.config.has_section(section):
            return

        for option in list(cfg.config.options(section)):
            if option.endswith(suffix):
                base_name = option[: -len(suffix)]
                if base_name not in valid_names:
                    if option in cfg.schema:
                        del cfg.schema[option]
                    cfg.config.remove_option(section, option)
                    cfg.save()

    def save_splitters_by_name(self, parent_widget: QWidget):
        if parent_widget is None:
            return

        splitters = [
            c for c in parent_widget.findChildren(QSplitter) if c.parent() == parent_widget
        ]

        for splitter in splitters:
            name = splitter.objectName()
            if not name:
                continue

            sizes = splitter.sizes()
            if not sizes or any(s <= 0 for s in sizes):
                logd(
                    f"[{self.geometry_config.section}] Skipping save for splitter '{name}' due to invalid sizes: {sizes}"
                )
                continue

            key = f"{name}_sizes"
            self.geometry_config._ensure_schema_key(key, ConfigType.LIST, sizes)
            self.geometry_config.set(key, sizes)
            logd(f"[{self.geometry_config.section}] Saved named splitter '{name}': {sizes}")

    def load_splitters_by_name(self, parent_widget: QWidget):
        if parent_widget is None:
            return

        self.clean_unused_splitters(parent_widget)

        splitters = [
            c for c in parent_widget.findChildren(QSplitter) if c.parent() == parent_widget
        ]

        for splitter in splitters:
            name = splitter.objectName()
            if not name:
                continue

            key = f"{name}_sizes"
            if key in self.geometry_config.schema:
                sizes = self.geometry_config.get(key)
                # 튜플 반환 대비 안전한 list 캐스팅 추가
                if isinstance(sizes, tuple):
                    sizes = list(sizes)

                if isinstance(sizes, list) and len(sizes) > 0 and all(s > 0 for s in sizes):
                    splitter.setSizes(sizes)
                    logd(
                        f"[{self.geometry_config.section}] Loaded named splitter '{name}': {sizes}"
                    )
                else:
                    loge(
                        f"[{self.geometry_config.section}] Ignored zero-sized or invalid splitter data for '{key}': {sizes}"
                    )


#################################################################################
# 3. TableColumnManager (테이블 컬럼 너비, 숨김, 순서 및 메타데이터 관리)
#################################################################################
class TableColumnManager:
    def __init__(self, section_name: Optional[str] = None):
        self._section_name = section_name or self.__class__.__name__

        class DynamicTableConfig(GeometryConfig):
            section = self._section_name

        self.geometry_config = DynamicTableConfig()
        self._table_defaults: Dict[str, Dict[str, Any]] = {}

    def set_table_default_from_info(self, table_name: str, header_info_def: dict):
        if not hasattr(self, "_table_defaults") or self._table_defaults is None:
            self._table_defaults = {}

        keys = list(header_info_def.keys())
        visible_cols = []
        widths = []

        for idx, key in enumerate(keys):
            info = header_info_def[key]
            if info.get("default", True):
                visible_cols.append(idx)
            widths.append(info.get("width", 100))

        self._table_defaults[table_name] = {
            "visible": visible_cols,
            "order": list(range(len(keys))),
            "widths": widths,
        }

        if hasattr(self, "findChildren"):
            tables = [c for c in self.findChildren(QWidget) if hasattr(c, "horizontalHeader")]
            for table in tables:
                if table.objectName() == table_name and hasattr(
                    table, "set_header_info_definition"
                ):
                    table.set_header_info_definition(header_info_def)

    def save_table_columns_by_name(self, parent_widget: QWidget):
        if parent_widget is None:
            return

        tables = [
            c
            for c in parent_widget.findChildren(QWidget)
            if hasattr(c, "horizontalHeader")
            and c.parent() == parent_widget
            and c.objectName().strip()
        ]

        for table in tables:
            name = table.objectName()
            header = table.horizontalHeader()
            col_count = table.columnCount()
            if col_count <= 0:
                continue

            widths = [header.sectionSize(i) for i in range(col_count)]
            width_key = f"{name}_column_widths"
            self.geometry_config._ensure_schema_key(width_key, ConfigType.LIST, widths)
            self.geometry_config.set(width_key, widths)

            hidden_cols = [i for i in range(col_count) if table.isColumnHidden(i)]
            hidden_key = f"{name}_column_hidden"
            self.geometry_config._ensure_schema_key(hidden_key, ConfigType.LIST, hidden_cols)
            self.geometry_config.set(hidden_key, hidden_cols)

            visual_order = [header.logicalIndex(v) for v in range(col_count)]
            order_key = f"{name}_column_order"
            self.geometry_config._ensure_schema_key(order_key, ConfigType.LIST, visual_order)
            self.geometry_config.set(order_key, visual_order)

    def load_table_columns_by_name(self, parent_widget: QWidget):
        if parent_widget is None:
            return

        tables = [
            c
            for c in parent_widget.findChildren(QWidget)
            if hasattr(c, "horizontalHeader")
            and c.parent() == parent_widget
            and c.objectName().strip()
        ]

        for table in tables:
            name = table.objectName()
            header = table.horizontalHeader()
            col_count = table.columnCount()
            if col_count <= 0:
                continue

            defaults = self._table_defaults.get(name, {})

            # 튜플 반환 대비 안전한 list 캐스팅 추가
            order_key = f"{name}_column_order"
            if order_key in self.geometry_config.schema:
                visual_order = self.geometry_config.get(order_key)
                if isinstance(visual_order, (tuple, list)):
                    visual_order = list(visual_order)
            else:
                visual_order = defaults.get("order")
                if isinstance(visual_order, (tuple, list)):
                    visual_order = list(visual_order)

            if isinstance(visual_order, list) and len(visual_order) == col_count:
                for visual_idx, logical_idx in enumerate(visual_order):
                    current_visual = header.visualIndex(logical_idx)
                    if current_visual != visual_idx:
                        header.moveSection(current_visual, visual_idx)

            hidden_key = f"{name}_column_hidden"
            if hidden_key in self.geometry_config.schema:
                hidden_cols = self.geometry_config.get(hidden_key)
                if isinstance(hidden_cols, tuple):
                    hidden_cols = list(hidden_cols)
                if isinstance(hidden_cols, list):
                    for i in range(col_count):
                        table.setColumnHidden(i, i in hidden_cols)
            else:
                visible_defaults = defaults.get("visible")
                if visible_defaults is not None:
                    for i in range(col_count):
                        table.setColumnHidden(i, i not in visible_defaults)

            width_key = f"{name}_column_widths"
            if width_key in self.geometry_config.schema:
                widths = self.geometry_config.get(width_key)
                if isinstance(widths, tuple):
                    widths = list(widths)
            else:
                widths = defaults.get("widths")

            if isinstance(widths, list) and len(widths) == col_count:
                for i, w in enumerate(widths):
                    if w > 0:
                        table.setColumnWidth(i, w)

            if hasattr(table, "update_visible_columns"):
                table.update_visible_columns()


#################################################################################
# 4. GeometrySplitterManager 및 공통 위젯/다이얼로그 베이스 클래스들
#################################################################################
class GeometrySplitterManager(GeometryManager, SplitterManager):
    def __init__(self, section_name: Optional[str] = None):
        GeometryManager.__init__(self, section_name)


class AutoGeometryWidget(QWidget, GeometryManager):
    title = "DefaultWindow"

    def __init__(self, parent=None):
        super().__init__(parent)
        if not hasattr(self, "title"):
            self.title = "DefaultWindow"
        GeometryManager.__init__(self, self.__class__.__name__)

    def getTitle(self):
        return self.title

    def showEvent(self, event):
        super().showEvent(event)
        self.load_window_geometry(self)

    def hideEvent(self, event):
        self.save_window_geometry(self)
        super().hideEvent(event)

    def closeEvent(self, event):
        self.save_window_geometry(self)
        super().closeEvent(event)


class AutoSplitterWidget(QWidget, SplitterManager):
    title = "DefaultComponent"

    def __init__(self, parent=None):
        super().__init__(parent)
        if not hasattr(self, "title"):
            self.title = "DefaultComponent"
        SplitterManager.__init__(self, self.__class__.__name__)

    def getTitle(self):
        return self.title

    def showEvent(self, event):
        super().showEvent(event)
        self.load_splitters_by_name(self)

    def hideEvent(self, event):
        self.save_splitters_by_name(self)
        super().hideEvent(event)

    def closeEvent(self, event):
        self.save_splitters_by_name(self)
        super().closeEvent(event)


class AutoGeometrySplitterWidget(QWidget, GeometrySplitterManager):
    title = "DefaultWindow"

    def __init__(self, parent=None):
        super().__init__(parent)
        if not hasattr(self, "title"):
            self.title = "DefaultWindow"
        GeometrySplitterManager.__init__(self, self.__class__.__name__)

    def getTitle(self):
        return self.title

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


class GeometrySplitterTableManager(GeometryManager, SplitterManager, TableColumnManager):
    def __init__(self, section_name: Optional[str] = None):
        GeometryManager.__init__(self, section_name)


class AutoGeometrySplitterTableWidget(QWidget, GeometrySplitterTableManager):
    title = "DefaultWindow"

    def __init__(self, parent=None):
        super().__init__(parent)
        if not hasattr(self, "title"):
            self.title = "DefaultWindow"
        GeometrySplitterTableManager.__init__(self, self.__class__.__name__)

    def getTitle(self):
        return self.title

    def showEvent(self, event):
        super().showEvent(event)
        self.load_window_geometry(self)
        self.load_splitters_by_name(self)
        self.load_table_columns_by_name(self)

    def hideEvent(self, event):
        self.save_window_geometry(self)
        self.save_splitters_by_name(self)
        self.save_table_columns_by_name(self)
        super().hideEvent(event)

    def closeEvent(self, event):
        self.save_window_geometry(self)
        self.save_splitters_by_name(self)
        self.save_table_columns_by_name(self)
        super().closeEvent(event)


class AutoGeometryDialog(QDialog, GeometryManager):
    title = "DefaultDialog"
    default_geometry: List[int] = [100, 100, 640, 480]

    def __init__(self, parent=None, default_geometry: Optional[List[int]] = None):
        QDialog.__init__(self, parent)
        if not hasattr(self, "title"):
            self.title = "DefaultDialog"
        GeometryManager.__init__(self, self.__class__.__name__)
        self._default_geometry = default_geometry or list(self.default_geometry)
        self.geometry_config._ensure_schema_key(
            "window_geometry", ConfigType.LIST, list(self._default_geometry)
        )

    def getTitle(self):
        return self.title

    def showEvent(self, event):
        super().showEvent(event)
        self.load_window_geometry(self, default_geometry=self._default_geometry)

    def hideEvent(self, event):
        self.save_window_geometry(self)
        super().hideEvent(event)

    def closeEvent(self, event):
        self.save_window_geometry(self)
        super().closeEvent(event)


import inspect


class SingletonAutoGeometryDialog(AutoGeometryDialog):
    _instances = {}

    def __init__(self, parent=None, default_geometry: Optional[List[int]] = None):
        if getattr(self, "_initialized", False):
            return
        if default_geometry is not None:
            super().__init__(parent, default_geometry=default_geometry)
        else:
            super().__init__(parent)
        self._initialized = True

    @classmethod
    def get_instance(cls, parent=None, default_geometry: Optional[List[int]] = None):
        if cls not in cls._instances or cls._instances[cls] is None:
            if default_geometry is not None:
                cls._instances[cls] = cls(parent, default_geometry=default_geometry)
            else:
                cls._instances[cls] = cls(parent)

            app = QApplication.instance()
            if app:
                try:
                    app.aboutToQuit.connect(cls.cleanup_instance)
                except Exception:
                    pass
        return cls._instances[cls]

    @classmethod
    def cleanup_instance(cls):
        dialog = cls._instances.get(cls)
        if dialog is not None:
            try:
                logd(f"[{cls.__name__}] Cleaning up singleton instance on app quit.")
                dialog.deleteLater()
            except RuntimeError:
                pass
            finally:
                cls._instances[cls] = None

    @classmethod
    def show_unique_dialog(
        cls, parent=None, session_data=None, default_geometry: Optional[List[int]] = None
    ):
        dialog = cls.get_instance(parent, default_geometry=default_geometry)
        if hasattr(dialog, "slot_load_request"):
            dialog.slot_load_request(session_data)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def closeEvent(self, event):
        self.save_window_geometry(self)
        event.ignore()
        self.hide()
