"""
Enhanced Sortable QTableWidget with Natural Sorting Support.
Fixes alphabetical sorting issues (e.g., '10 MINS' < '120 MINS' < '30 MINS')
and supports precise numeric/float/text sort keys.
"""

import re
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QCheckBox, QWidget, QHBoxLayout
from PySide6.QtCore import Qt


def get_natural_sort_key(text: str):
    """
    문자열 내의 숫자와 텍스트 부분을 분리하여 수치 기준으로 정렬할 수 있는 Key(튜플)를 생성합니다.
    예:
    '10 MINS'  -> [10.0, ' MINS']
    '120 MINS' -> [120.0, ' MINS']
    '30 MINS'  -> [30.0, ' MINS']
    '5.5'      -> [5.5, '']
    """
    if text is None:
        return []
    
    text = str(text).strip()
    
    # 1. 완전한 정수/실수인 경우 바로 float 반환
    try:
        return [float(text), ""]
    except ValueError:
        pass

    # 2. 문자열 내 숫자와 비숫자 부분을 분리 (정수 및 소수점 지원)
    # 예: '120 MINS' -> ['120', ' MINS']
    tokens = re.split(r'(\d+(?:\.\d+)?)', text)
    
    key = []
    for token in tokens:
        if not token:
            continue
        try:
            # 숫자 부분은 float으로 변환하여 수치 비교
            key.append(float(token))
        except ValueError:
            # 문자 부분은 대소문자 구분을 없앤 소문자 텍스트로 비교
            key.append(token.lower())
            
    return key


class NaturalSortTableItem(QTableWidgetItem):
    """
    개선된 NaturalSortTableItem:
    QTableWidget 자체 정렬(self.sortItems 등) 사용 시에도 정확한 수치/문자 결합 정렬을 지원합니다.
    """
    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)

        key_self = get_natural_sort_key(self.text())
        key_other = get_natural_sort_key(other.text())

        return key_self < key_other


class SortableTableWidget(QTableWidget):
    """
    QTableWidget 상속 위젯.
    헤더 클릭 정렬 시 CellWidget(체크박스 등)의 상태를 보존하며
    개선된 Natural Sort 키를 이용하여 오름차순/내림차순 정렬을 수행합니다.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.horizontalHeader().sectionClicked.connect(self.on_header_clicked)

    def on_header_clicked(self, logical_index: int):
        """헤더 클릭 시 정렬 순서 토글 및 실행"""
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
        """행 데이터 및 CheckBox 셀 위젯 상태를 안전하게 보존하며 정렬"""
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

                # CheckBox 위젯 체크 상태 보존
                widget = self.cellWidget(r, c)
                if widget:
                    chk = widget.findChild(QCheckBox)
                    if chk:
                        active_checked = chk.isChecked()

            # 정렬 대상 컬럼 값의 Natural Key 생성
            sort_text = row_items[col].text() if col < len(row_items) else ""
            sort_key = get_natural_sort_key(sort_text)

            rows_data.append({
                "sort_key": sort_key,
                "items": row_items,
                "active_checked": active_checked,
            })

        # 보강된 natural sort key 기준 정렬
        is_reverse = (order == Qt.SortOrder.DescendingOrder)
        rows_data.sort(key=lambda x: x["sort_key"], reverse=is_reverse)

        # 테이블에 정렬 결과 재배치
        self.setRowCount(0)
        for r_idx, r_data in enumerate(rows_data):
            self.insertRow(r_idx)
            for c_idx, item in enumerate(r_data["items"]):
                self.setItem(r_idx, c_idx, item)

                # Active(index 1) CheckBox Widget 복원
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