import ctypes
import os
import subprocess
from typing import List, Set, Tuple
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from Common.log import logd, setup_global_log
from Common.log_settings_tab import LogSettingsTab
from config_tab import ConfigTab
from exe_file_record import ExeFileRecord
from memory_zip_extractor import MemoryZipExtractor
from settings_window import SettingsWindow
from viewer_config import viewer_config_instance


def _get_system_memory_stats_mb() -> tuple[float, float]:
    """(누적/프로세스 메모리 사용량 MB, 시스템 메모리 여유량 MB) 반환"""
    process_mb = 0.0
    available_mb = 0.0

    try:
        import psutil  # type: ignore

        proc = psutil.Process(os.getpid())
        process_mb = proc.memory_info().rss / (1024 * 1024)
        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        return process_mb, available_mb
    except ImportError:
        pass

    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            available_mb = stat.ullAvailPhys / (1024 * 1024)

        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        h_proc = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(h_proc, ctypes.byref(pmc), pmc.cb):
            process_mb = pmc.WorkingSetSize / (1024 * 1024)

    return process_mb, available_mb


class ColumnVisibilityDialog(QDialog):
    """컬럼 숨기기/보이기 일괄 관리 다이얼로그"""

    def __init__(self, columns: List[str], hidden_set: Set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("컬럼 숨기기 / 표시 설정")
        self.resize(360, 480)
        self._checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        vbox = QVBoxLayout(container)

        for col_name in columns:
            chk = QCheckBox(col_name)
            chk.setChecked(col_name not in hidden_set)
            # No 컬럼은 최소 1개 표시 유지 위해 비활성화하지 않고 안내만 제공
            vbox.addWidget(chk)
            self._checkboxes[col_name] = chk

        vbox.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_all_show = QPushButton("모두 표시")
        btn_all_show.clicked.connect(self._check_all)
        btn_row.addWidget(btn_all_show)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _check_all(self):
        for chk in self._checkboxes.values():
            chk.setChecked(True)

    def get_hidden_columns(self) -> List[str]:
        hidden = [name for name, chk in self._checkboxes.items() if not chk.isChecked()]
        # 모든 컬럼이 숨겨지는 것 방지
        if len(hidden) >= len(self._checkboxes) and self._checkboxes:
            first_name = next(iter(self._checkboxes.keys()))
            hidden = [h for h in hidden if h != first_name]
        return hidden


class VersionViewerWindow(QMainWindow):
    MIN_SUBFOLDER_DEPTH = 0
    MAX_SUBFOLDER_DEPTH = 10

    def __init__(self):
        super().__init__()
        setup_global_log(module_name="VersionViewer")
        logd("VersionViewerWindow initialized successfully.")

        self.config = viewer_config_instance
        self.zip_extractor = MemoryZipExtractor()
        self.records: List[ExeFileRecord] = []
        self.seen_folder_files: Set[Tuple[str, str]] = set()
        self.cumulative_zip_bytes: int = 0
        self._restoring_columns: bool = False

        self.setWindowTitle("PrintShopApp - 버전 뷰어 및 하위 검색기")

        w = int(self.config.get("window_width") or 1350)
        h = int(self.config.get("window_height") or 600)
        self.resize(w, h)

        self.init_ui()
        self._restore_column_state_from_config()
        self._init_memory_timer()

        saved_files = self._load_saved_file_list()
        if saved_files:
            self.path_label.setText(f"저장된 파일리스트 로드 ({len(saved_files)}개)")
            logd(f"Restoring {len(saved_files)} file path(s) from config file_list.")
            self._ingest_file_paths(saved_files, persist_config=False)
        else:
            last_path = self.config.get("last_path")
            if last_path and os.path.exists(last_path):
                abs_last = os.path.abspath(last_path)
                self.path_label.setText(f"선택된 경로: {abs_last}")
                logd(f"Restoring last path from config: {abs_last}")
                self.scan_and_extract(abs_last, is_dir=os.path.isdir(abs_last))
            else:
                self.refresh_memory_stats()

    def get_dir_depth(self) -> int:
        raw_depth = self.config.get("dir_depth")
        try:
            depth = int(raw_depth)
        except (TypeError, ValueError):
            depth = 3
        return max(self.MIN_SUBFOLDER_DEPTH, min(self.MAX_SUBFOLDER_DEPTH, depth))

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        top_layout = QHBoxLayout()

        self.path_label = QLabel("선택된 경로: 없음")
        self.path_label.setStyleSheet("font-weight: bold; color: #FFFFFF;")

        self.mem_group = QGroupBox("메모리 현황")
        self.mem_group.setStyleSheet(
            "QGroupBox { color: #FFFF00; border: 1px solid #FFFF00; font-weight: bold; margin-top: 6px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        mem_layout = QHBoxLayout(self.mem_group)
        mem_layout.setContentsMargins(8, 2, 8, 2)
        mem_layout.setSpacing(12)

        self.lbl_cum_mem = QLabel("누적 메모리 사용량: 0.0 MB")
        self.lbl_cum_mem.setStyleSheet("font-weight: bold; color: #82B1FF;")

        self.lbl_sys_avail_mem = QLabel("시스템 메모리 여유량: 0.0 MB")
        self.lbl_sys_avail_mem.setStyleSheet("font-weight: bold; color: #69F0AE;")

        mem_layout.addWidget(self.lbl_cum_mem)
        mem_layout.addWidget(self.lbl_sys_avail_mem)

        btn_select_dir = QPushButton("📁 폴더 선택")
        btn_select_dir.clicked.connect(self.select_directory)

        btn_select_file = QPushButton("📄 파일 선택")
        btn_select_file.clicked.connect(self.select_file)

        btn_settings = QPushButton("⚙️ 세팅")
        btn_settings.clicked.connect(self.open_settings_window)

        top_layout.addWidget(self.path_label, 1)
        top_layout.addWidget(self.mem_group)
        top_layout.addWidget(btn_select_dir)
        top_layout.addWidget(btn_select_file)
        top_layout.addWidget(btn_settings)
        layout.addLayout(top_layout)

        remove_layout = QHBoxLayout()
        self.lbl_list_summary = QLabel("파일리스트: 0건 (체크 시 일괄 제거 가능)")
        self.lbl_list_summary.setStyleSheet("color: #E0E0E0; font-weight: bold;")

        btn_columns = QPushButton("👁️ 컬럼 관리")
        btn_columns.setToolTip("컬럼 숨기기/표시 설정")
        btn_columns.clicked.connect(self.open_column_visibility_dialog)

        btn_remove_selected = QPushButton("🗑️ 선택(개별) 제거")
        btn_remove_selected.clicked.connect(self.remove_selected_record)

        btn_remove_checked = QPushButton("☑️ 체크 일괄 제거")
        btn_remove_checked.clicked.connect(self.remove_checked_records)

        btn_remove_all = QPushButton("🧹 전체 제거")
        btn_remove_all.clicked.connect(self.remove_all_records)

        remove_layout.addWidget(self.lbl_list_summary, 1)
        remove_layout.addWidget(btn_columns)
        remove_layout.addWidget(btn_remove_selected)
        remove_layout.addWidget(btn_remove_checked)
        remove_layout.addWidget(btn_remove_all)
        layout.addLayout(remove_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(len(ExeFileRecord.COLUMNS))
        self.table.setHorizontalHeaderLabels(ExeFileRecord.COLUMNS)

        self.table.setStyleSheet(
            "QTableWidget {"
            "   background-color: #000000;"
            "   color: #FFFFFF;"
            "   gridline-color: #666666;"
            "}"
            "QTableWidget::item:selected {"
            "   background-color: #1A237E;"
            "   color: #FFFF00;"
            "   border: 2px solid #00E5FF;"
            "}"
        )

        header = self.table.horizontalHeader()
        for col in range(len(ExeFileRecord.COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        header.setSectionsClickable(True)
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.sectionClicked.connect(self.select_column)
        header.sectionMoved.connect(self._on_column_moved)
        header.sectionResized.connect(self._on_column_resized)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

        default_widths = [
            65, 80, 260, 180, 95, 110, 160,
            110, 110, 130, 150, 200, 150, 130, 130, 160, 150, 110, 110,
            95, 145, 320,
        ]
        for col, width in enumerate(default_widths):
            if col < self.table.columnCount():
                self.table.setColumnWidth(col, width)

        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)

        layout.addWidget(self.table)

    def _restore_column_state_from_config(self):
        """Config에서 컬럼 위치(순서), 크기, 숨김 상태 로드"""
        self._restoring_columns = True
        try:
            header = self.table.horizontalHeader()
            col_count = len(ExeFileRecord.COLUMNS)

            # 1) 컬럼 사이즈 복원 (논리 인덱스 기준)
            saved_widths = self.config.get("column_widths")
            if isinstance(saved_widths, list):
                for logical_idx in range(min(col_count, len(saved_widths))):
                    try:
                        w = int(saved_widths[logical_idx])
                        if w >= 20:
                            self.table.setColumnWidth(logical_idx, w)
                    except (TypeError, ValueError):
                        continue

            # 2) 컬럼 위치(순서) 복원 (컬럼명 리스트 기준)
            saved_order = self.config.get("column_order")
            if isinstance(saved_order, list) and len(saved_order) == col_count:
                name_to_logical = {name: idx for idx, name in enumerate(ExeFileRecord.COLUMNS)}
                desired_logicals: List[int] = []
                for col_name in saved_order:
                    if isinstance(col_name, str) and col_name in name_to_logical:
                        idx = name_to_logical[col_name]
                        if idx not in desired_logicals:
                            desired_logicals.append(idx)
                for idx in range(col_count):
                    if idx not in desired_logicals:
                        desired_logicals.append(idx)

                for target_visual_idx, logical_idx in enumerate(desired_logicals):
                    current_visual_idx = header.visualIndex(logical_idx)
                    if current_visual_idx != target_visual_idx:
                        header.moveSection(current_visual_idx, target_visual_idx)

            # 3) 컬럼 숨김(show/hide) 상태 복원
            saved_hidden = self.config.get("hidden_columns")
            hidden_set = set(saved_hidden) if isinstance(saved_hidden, list) else set()
            for logical_idx, col_name in enumerate(ExeFileRecord.COLUMNS):
                self.table.setColumnHidden(logical_idx, col_name in hidden_set)
        finally:
            self._restoring_columns = False

    def save_column_state_to_config(self):
        """현재 컬럼 위치(순서), 크기, 숨김 상태를 Config에 저장"""
        if self._restoring_columns:
            return

        header = self.table.horizontalHeader()
        col_count = len(ExeFileRecord.COLUMNS)

        ordered_names: List[str] = []
        for visual_idx in range(col_count):
            logical_idx = header.logicalIndex(visual_idx)
            if 0 <= logical_idx < col_count:
                ordered_names.append(ExeFileRecord.COLUMNS[logical_idx])

        widths: List[int] = [self.table.columnWidth(idx) for idx in range(col_count)]
        hidden_cols: List[str] = [
            col_name for idx, col_name in enumerate(ExeFileRecord.COLUMNS) if self.table.isColumnHidden(idx)
        ]

        self.config.set("column_order", ordered_names)
        self.config.set("column_widths", widths)
        self.config.set("hidden_columns", hidden_cols)
        if hasattr(self.config, "save"):
            self.config.save()

    def _on_column_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int):
        if self._restoring_columns:
            return
        logd(f"Column moved: logical={logical_index}, visual {old_visual_index} -> {new_visual_index}")
        self.save_column_state_to_config()

    def _on_column_resized(self, logical_index: int, old_size: int, new_size: int):
        if self._restoring_columns:
            return
        self.save_column_state_to_config()

    def _move_logical_column_by_visual_delta(self, logical_idx: int, delta: int):
        header = self.table.horizontalHeader()
        current_visual = header.visualIndex(logical_idx)
        target_visual = max(0, min(self.table.columnCount() - 1, current_visual + delta))
        if current_visual != target_visual:
            header.moveSection(current_visual, target_visual)
            self.save_column_state_to_config()

    def _on_header_context_menu(self, pos):
        header = self.table.horizontalHeader()
        logical_idx = header.logicalIndexAt(pos)
        if logical_idx < 0:
            return

        col_name = ExeFileRecord.COLUMNS[logical_idx]
        menu = QMenu(self)

        act_move_left = menu.addAction("⬅️ 왼쪽으로 이동")
        act_move_right = menu.addAction("➡️ 오른쪽으로 이동")
        menu.addSeparator()

        if self.table.isColumnHidden(logical_idx):
            act_toggle_hide = menu.addAction(f"👁️ '{col_name}' 컬럼 보이기")
        else:
            act_toggle_hide = menu.addAction(f"🙈 '{col_name}' 컬럼 숨기기")

        act_manage_cols = menu.addAction("📋 전체 컬럼 표시/숨기기 창...")
        act_show_all = menu.addAction("✨ 모든 컬럼 표시")

        chosen = menu.exec(header.mapToGlobal(pos))
        if chosen is None:
            return

        if chosen == act_move_left:
            self._move_logical_column_by_visual_delta(logical_idx, -1)
        elif chosen == act_move_right:
            self._move_logical_column_by_visual_delta(logical_idx, 1)
        elif chosen == act_toggle_hide:
            currently_hidden = self.table.isColumnHidden(logical_idx)
            if not currently_hidden:
                visible_count = sum(
                    1 for i in range(self.table.columnCount()) if not self.table.isColumnHidden(i)
                )
                if visible_count <= 1:
                    QMessageBox.information(self, "안내", "최소 1개 이상의 컬럼은 표시되어야 합니다.")
                    return
            self.table.setColumnHidden(logical_idx, not currently_hidden)
            self.save_column_state_to_config()
        elif chosen == act_manage_cols:
            self.open_column_visibility_dialog()
        elif chosen == act_show_all:
            for i in range(self.table.columnCount()):
                self.table.setColumnHidden(i, False)
            self.save_column_state_to_config()

    def open_column_visibility_dialog(self):
        hidden_set = {
            col_name for idx, col_name in enumerate(ExeFileRecord.COLUMNS) if self.table.isColumnHidden(idx)
        }
        dlg = ColumnVisibilityDialog(ExeFileRecord.COLUMNS, hidden_set, parent=self)
        if dlg.exec() == QDialog.Accepted:
            new_hidden = set(dlg.get_hidden_columns())
            for idx, col_name in enumerate(ExeFileRecord.COLUMNS):
                self.table.setColumnHidden(idx, col_name in new_hidden)
            self.save_column_state_to_config()

    def _load_saved_file_list(self) -> List[str]:
        raw_list = self.config.get("file_list")
        if not isinstance(raw_list, list):
            return []
        abs_paths: List[str] = []
        seen: Set[str] = set()
        for p in raw_list:
            if not isinstance(p, str) or not p.strip():
                continue
            abs_p = os.path.abspath(p.strip())
            norm_key = os.path.normcase(abs_p)
            if norm_key not in seen and os.path.exists(abs_p):
                seen.add(norm_key)
                abs_paths.append(abs_p)
        return abs_paths

    def _save_file_list_to_config(self):
        abs_paths: List[str] = []
        seen: Set[str] = set()
        for rec in self.records:
            src_abs = os.path.abspath(rec.source_abs_path)
            norm_key = os.path.normcase(src_abs)
            if norm_key not in seen:
                seen.add(norm_key)
                abs_paths.append(src_abs)

        self.config.set("file_list", abs_paths)
        if hasattr(self.config, "save"):
            self.config.save()

    def _update_summary_label(self):
        checked_cnt = 0
        for r in range(self.table.rowCount()):
            chk_item = self.table.item(r, 0)
            if chk_item and chk_item.checkState() == Qt.Checked:
                checked_cnt += 1
        self.lbl_list_summary.setText(
            f"파일리스트: {len(self.records)}건 | 체크됨: {checked_cnt}건 | 서치 깊이: {self.get_dir_depth()}"
        )

    def _rebuild_table(self):
        self.records.sort(key=lambda r: r.sort_key)
        self.table.setRowCount(len(self.records))
        for row_idx, record in enumerate(self.records):
            record.index = row_idx + 1
            for col_idx, item in enumerate(record.create_table_items()):
                self.table.setItem(row_idx, col_idx, item)
        self._update_summary_label()

    def remove_selected_record(self):
        target_row = self.table.currentRow()
        if target_row < 0:
            selected_indexes = self.table.selectedIndexes()
            if selected_indexes:
                target_row = selected_indexes[0].row()

        if not (0 <= target_row < len(self.records)):
            QMessageBox.information(self, "안내", "제거할 항목을 먼저 선택해 주세요.")
            return

        removed = self.records.pop(target_row)
        self.seen_folder_files = {r.folder_and_file_key for r in self.records}
        logd(f"Removed single record: {removed.file_path}")
        self._rebuild_table()
        self._save_file_list_to_config()

    def remove_checked_records(self):
        checked_rows: Set[int] = set()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                checked_rows.add(r)

        if not checked_rows:
            QMessageBox.information(self, "안내", "일괄 제거할 항목의 체크박스를 선택해 주세요.")
            return

        self.records = [rec for idx, rec in enumerate(self.records) if idx not in checked_rows]
        self.seen_folder_files = {r.folder_and_file_key for r in self.records}
        logd(f"Batch removed {len(checked_rows)} checked record(s).")
        self._rebuild_table()
        self._save_file_list_to_config()

    def remove_all_records(self):
        if not self.records and self.table.rowCount() == 0:
            return

        self.records.clear()
        self.seen_folder_files.clear()
        self.cumulative_zip_bytes = 0
        self.table.setRowCount(0)
        self._update_summary_label()
        self._save_file_list_to_config()
        self.refresh_memory_stats()
        logd("Removed all file list records and cleared config file_list.")

    def select_column(self, col_index: int):
        row_count = self.table.rowCount()
        col_count = self.table.columnCount()
        if row_count <= 0 or not (0 <= col_index < col_count):
            return

        self.table.clearSelection()
        for r in range(row_count):
            item = self.table.item(r, col_index)
            if item is not None:
                item.setSelected(True)

    def _init_memory_timer(self):
        self.mem_timer = QTimer(self)
        self.mem_timer.setInterval(1500)
        self.mem_timer.timeout.connect(self.refresh_memory_stats)
        self.mem_timer.start()

    def refresh_memory_stats(self):
        proc_mb, avail_mb = _get_system_memory_stats_mb()
        cum_zip_mb = self.cumulative_zip_bytes / (1024 * 1024)
        total_tracked_mb = proc_mb + cum_zip_mb
        self.lbl_cum_mem.setText(
            f"누적 메모리 사용량: {total_tracked_mb:.1f} MB (ZIP해제누적: {cum_zip_mb:.1f} MB)"
        )
        self.lbl_sys_avail_mem.setText(f"시스템 메모리 여유량: {avail_mb:.1f} MB")

    def open_settings_window(self):
        settings_win = SettingsWindow(title="환경 설정", parent=self)
        config_tab = ConfigTab(config=self.config, parent=settings_win)
        log_tab = LogSettingsTab(settings_win)

        settings_win.add_tab(config_tab, "일반 설정 (Config)", scrollable=True)
        settings_win.add_tab(log_tab, "로그 설정 (Log)", scrollable=True)
        settings_win.exec()

        self.resize(int(self.config.get("window_width")), int(self.config.get("window_height")))
        self._restore_column_state_from_config()
        self._update_summary_label()

    def select_directory(self):
        depth = self.get_dir_depth()
        dir_path = QFileDialog.getExistingDirectory(self, f"검색할 폴더 선택 (서치 깊이: {depth})")
        if dir_path:
            abs_dir = os.path.abspath(dir_path)
            self.path_label.setText(f"선택된 경로: {abs_dir}")
            self.config.set("last_path", abs_dir)
            logd(f"Directory selected (dir_depth={depth}): {abs_dir}")
            self.scan_and_extract(abs_dir, is_dir=True)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "확인할 실행 또는 압축 파일 선택",
            "",
            "Executable & Zip Files (*.exe *.zip);;Executable Files (*.exe);;Zip Archives (*.zip)",
        )
        if file_path:
            abs_file = os.path.abspath(file_path)
            self.path_label.setText(f"선택된 경로: {abs_file}")
            self.config.set("last_path", abs_file)
            logd(f"File selected: {abs_file}")
            self.scan_and_extract(abs_file, is_dir=False)

    def _collect_targets_within_depth(self, root_dir: str, max_depth: int) -> List[str]:
        found_files: List[str] = []
        root_abs = os.path.abspath(root_dir)
        clamped_depth = max(self.MIN_SUBFOLDER_DEPTH, min(self.MAX_SUBFOLDER_DEPTH, int(max_depth)))

        for current_root, dirs, files in os.walk(root_abs):
            rel_path = os.path.relpath(current_root, root_abs)
            depth = 0 if rel_path == "." else len(rel_path.split(os.sep))

            if depth >= clamped_depth:
                dirs[:] = []

            for fname in sorted(files):
                lower = fname.lower()
                if lower.endswith(".exe") or lower.endswith(".zip"):
                    found_files.append(os.path.abspath(os.path.join(current_root, fname)))

        return found_files

    def _try_register_record(self, record: ExeFileRecord) -> bool:
        key = record.folder_and_file_key
        if not key[1]:
            return False
        if key in self.seen_folder_files:
            logd(f"Skipping identical folder+file record: {key[0]} | {key[1]}")
            return False
        self.seen_folder_files.add(key)
        self.records.append(record)
        return True

    def _ingest_file_paths(self, target_paths: List[str], persist_config: bool = True):
        skipped_count = 0

        for target in target_paths:
            abs_target = os.path.abspath(target)
            if not os.path.exists(abs_target):
                continue

            lower = abs_target.lower()
            if lower.endswith(".exe"):
                record = ExeFileRecord(
                    index=0,
                    file_path=abs_target,
                    source_type="EXE",
                )
                if not self._try_register_record(record):
                    skipped_count += 1

            elif lower.endswith(".zip"):
                entries = self.zip_extractor.extract_exe_entries_from_file(abs_target)
                for entry in entries:
                    record = ExeFileRecord(
                        index=0,
                        file_path=abs_target,
                        exe_bytes=entry.data,
                        source_type="ZIP",
                        zip_path=os.path.abspath(entry.zip_path),
                        inner_path=entry.inner_path,
                        uncompressed_size=entry.uncompressed_size,
                    )
                    if not self._try_register_record(record):
                        skipped_count += 1
                        continue
                    self.cumulative_zip_bytes += entry.uncompressed_size

        if not self.records:
            self.table.setRowCount(0)
            self._update_summary_label()
            if persist_config:
                self._save_file_list_to_config()
            self.refresh_memory_stats()
            return

        self._rebuild_table()

        if persist_config:
            self._save_file_list_to_config()

        if skipped_count > 0:
            logd(f"Skipped {skipped_count} identical folder+file record(s).")

        self.refresh_memory_stats()

    def scan_and_extract(self, path: str, is_dir: bool):
        self.records.clear()
        self.seen_folder_files.clear()
        self.table.setRowCount(0)

        target_paths: List[str] = []
        if is_dir:
            target_paths = self._collect_targets_within_depth(path, self.get_dir_depth())
        else:
            abs_p = os.path.abspath(path)
            if abs_p.lower().endswith((".exe", ".zip")):
                target_paths = [abs_p]

        if not target_paths:
            QMessageBox.information(self, "안내", "탐색된 실행(.exe) 또는 압축(.zip) 파일이 없습니다.")
            logd("No executable or zip files found during scan.")
            self._update_summary_label()
            self._save_file_list_to_config()
            self.refresh_memory_stats()
            return

        self._ingest_file_paths(target_paths, persist_config=True)

    def on_item_double_clicked(self, item):
        row = item.row()
        if 0 <= row < len(self.records):
            rec = self.records[row]
            open_target = rec.zip_path if rec.is_from_zip else rec.file_path
            if open_target and os.path.exists(open_target):
                logd(f"Opening explorer for: {open_target}")
                subprocess.run(["explorer.exe", "/select,", os.path.abspath(open_target)])
            else:
                QMessageBox.warning(self, "경고", f"파일을 찾을 수 없습니다:\n{open_target}")

    def closeEvent(self, event):
        self.config.set("window_width", self.width())
        self.config.set("window_height", self.height())
        self.save_column_state_to_config()
        self._save_file_list_to_config()
        logd("VersionViewer window size, column state, and file list saved.")
        super().closeEvent(event)