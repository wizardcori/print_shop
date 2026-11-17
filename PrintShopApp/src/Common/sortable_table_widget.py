import re
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QCheckBox, QWidget, QHBoxLayout, QHeaderView, QMenu
from PySide6.QtCore import Qt


def get_natural_sort_key(text: str):
    if text is None:
        return []
    text = str(text).strip()
    try:
        return [float(text), ""]
    except ValueError:
        pass

    tokens = re.split(r'(\d+(?:\.\d+)?)', text)
    key = []
    for token in tokens:
        if not token:
            continue
        try:
            key.append(float(token))
        except ValueError:
            key.append(token.lower())
    return key


class NaturalSortTableItem(QTableWidgetItem):
    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
        return get_natural_sort_key(self.text()) < get_natural_sort_key(other.text())


class SortableTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self._apply_default_styles_and_settings()

    def _apply_default_styles_and_settings(self):
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setStyleSheet(
            "QTableWidget { background-color: #ffffff; color: #263238; gridline-color: #b0bec5; }"
            " QHeaderView::section { background-color: #1565c0; color: white; font-weight: bold; padding: 4px; }"
        )

    def on_header_clicked(self, logical_index: int):
        if self.current_sort_column == logical_index:
            self.sort_order = (
                Qt.SortOrder.DescendingOrder
                if self.sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self.current_sort_column = logical_index
            self.sort_order = Qt.SortOrder.AscendingOrder
        self.sort_by_column(logical_index, self.sort_order)

    def sort_by_column(self, col: int, order: Qt.SortOrder):
        row_count = self.rowCount()
        col_count = self.columnCount()
        if row_count <= 1:
            return

        rows_data = []
        for r in range(row_count):
            row_items = []
            active_checked = True
            for c in range(col_count):
                item = self.item(r, c)
                if not item:
                    item = NaturalSortTableItem("")
                row_items.append(item.clone())

                widget = self.cellWidget(r, c)
                if widget:
                    chk = widget.findChild(QCheckBox)
                    if chk:
                        active_checked = chk.isChecked()

            sort_text = row_items[col].text() if col < len(row_items) else ""
            sort_key = get_natural_sort_key(sort_text)
            rows_data.append({
                "sort_key": sort_key,
                "items": row_items,
                "active_checked": active_checked,
            })

        is_reverse = (order == Qt.SortOrder.DescendingOrder)
        rows_data.sort(key=lambda x: x["sort_key"], reverse=is_reverse)

        self.setRowCount(0)
        for r_idx, r_data in enumerate(rows_data):
            self.insertRow(r_idx)
            for c_idx, item in enumerate(r_data["items"]):
                self.setItem(r_idx, c_idx, item)
                if c_idx == 1:
                    cell_widget = QWidget()
                    cell_layout = QHBoxLayout(cell_widget)
                    chk = QCheckBox()
                    chk.setChecked(r_data["active_checked"])
                    cell_layout.addWidget(chk)
                    cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell_layout.setContentsMargins(0, 0, 0, 0)
                    self.setCellWidget(r_idx, c_idx, cell_widget)

        self.horizontalHeader().setSortIndicator(col, order)


class ColumnManageableTableWidget(SortableTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visible_columns = []
        self.header_info_def = None
        
        header = self.horizontalHeader()
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_header_context_menu)
        header.sectionMoved.connect(lambda: self.update_visible_columns())
        
        self.update_visible_columns()

    def set_header_info_definition(self, header_info_def: dict):
        self.header_info_def = header_info_def

    def update_visible_columns(self):
        header = self.horizontalHeader()
        visible_cols = []
        for visual_idx in range(self.columnCount()):
            logical_idx = header.logicalIndex(visual_idx)
            if not self.isColumnHidden(logical_idx):
                visible_cols.append(logical_idx)
        self.visible_columns = visible_cols

    def show_header_context_menu(self, pos):
        header = self.horizontalHeader()
        logical_index = header.logicalIndexAt(pos)
        
        menu = QMenu(self)
        if logical_index >= 0:
            header_item = self.horizontalHeaderItem(logical_index)
            col_name = header_item.text() if header_item else f"컬럼 {logical_index}"
            hide_action = menu.addAction(f"'{col_name}' 컬럼 숨기기")
            hide_action.triggered.connect(lambda: self.hide_column_and_update(logical_index))
            menu.addSeparator()

        show_menu = menu.addMenu("컬럼 표시 설정")
        for c in range(self.columnCount()):
            header_item = self.horizontalHeaderItem(c)
            col_name = header_item.text() if header_item else f"컬럼 {c}"
            action = show_menu.addAction(col_name)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(c))
            action.triggered.connect(lambda checked, col=c: self.toggle_column_visibility(col, checked))
            
        if self.header_info_def:
            menu.addSeparator()
            reset_action = menu.addAction("기본값으로 복원")
            reset_action.triggered.connect(self.reset_to_default_columns)
            
        menu.exec(header.mapToGlobal(pos))

    def reset_to_default_columns(self):
        if not self.header_info_def:
            return
        keys = list(self.header_info_def.keys())
        header = self.horizontalHeader()
        
        for visual_idx, logical_idx in enumerate(range(len(keys))):
            current_visual = header.visualIndex(logical_idx)
            if current_visual != visual_idx:
                header.moveSection(current_visual, visual_idx)

        for idx, key in enumerate(keys):
            info = self.header_info_def[key]
            should_be_visible = info.get("default", True)
            width = info.get("width", 100)
            self.setColumnHidden(idx, not should_be_visible)
            if width > 0:
                self.setColumnWidth(idx, width)
                
        self.update_visible_columns()
        
        parent_widget = self.parent()
        while parent_widget:
            if hasattr(parent_widget, 'save_table_columns_by_name'):
                parent_widget.save_table_columns_by_name(parent_widget)
                break
            parent_widget = parent_widget.parent()

    def hide_column_and_update(self, col: int):
        self.setColumnHidden(col, True)
        self.update_visible_columns()

    def toggle_column_visibility(self, col: int, visible: bool):
        self.setColumnHidden(col, not visible)
        self.update_visible_columns()

    def setModel(self, model):
        super().setModel(model)
        self.update_visible_columns()

