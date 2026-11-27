import os
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTreeView,
    QPushButton,
    QLabel,
    QMessageBox,
    QLineEdit,
    QInputDialog,
    QHeaderView,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QDir

# 안전한 QFileSystemModel 임포트 처리
try:
    from PySide6.QtGui import QFileSystemModel
except ImportError:
    try:
        from PySide6.QtCore import QFileSystemModel
    except ImportError:
        try:
            from PySide6.QtWidgets import QFileSystemModel
        except ImportError:
            QFileSystemModel = None


class FolderExplorerDialog(QDialog):
    """좌측 폴더 트리 + 우측 파일/폴더 목록 + 경로 바를 갖춘 탐색기형 폴더 선택 대화상자"""

    def __init__(self, current_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("폴더 선택 - 탐색기")

        self.setMinimumSize(700, 460)
        self.resize(900, 580)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        if QFileSystemModel is None:
            QMessageBox.critical(
                self,
                "오류",
                "현재 사용 중인 PySide6 환경에서 QFileSystemModel을 지원하지 않습니다.",
            )
            self.reject()
            return

        self.selected_path = ""
        self._syncing = False

        root_path = QDir.rootPath()

        # 좌측 모델: 폴더 트리 전용
        self.dir_model = QFileSystemModel(self)
        self.dir_model.setRootPath(root_path)
        self.dir_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)

        # 우측 모델: 폴더 + 파일 상세 목록
        self.content_model = QFileSystemModel(self)
        self.content_model.setRootPath(root_path)
        self.content_model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)

        self._init_ui()
        self._connect_signals()

        initial_dir = self._resolve_initial_dir(current_path)
        self.navigate_to(initial_dir)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. 상단 안내 및 빠른 이동 버튼(상위 폴더, 홈, 새 폴더)
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>대상 폴더를 탐색하고 선택하세요:</b>"))
        top_bar.addStretch()

        self.up_btn = QPushButton("↑ 상위")
        self.up_btn.setToolTip("상위 폴더로 이동")
        self.up_btn.setStyleSheet("padding: 4px 10px;")

        self.home_btn = QPushButton("홈")
        self.home_btn.setToolTip("사용자 홈 폴더로 이동")
        self.home_btn.setStyleSheet("padding: 4px 10px;")

        self.new_folder_btn = QPushButton("+ 새 폴더")
        self.new_folder_btn.setToolTip("현재 폴더 아래에 새 폴더 생성")
        self.new_folder_btn.setStyleSheet("padding: 4px 10px;")

        top_bar.addWidget(self.up_btn)
        top_bar.addWidget(self.home_btn)
        top_bar.addWidget(self.new_folder_btn)
        main_layout.addLayout(top_bar)

        # 2. 주소 표시줄
        path_bar = QHBoxLayout()
        path_bar.addWidget(QLabel("경로:"))

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("경로를 직접 입력하거나 붙여넣고 Enter를 누르세요...")
        self.path_edit.setStyleSheet("padding: 5px 8px;")

        self.go_btn = QPushButton("이동")
        self.go_btn.setStyleSheet("padding: 5px 12px;")

        path_bar.addWidget(self.path_edit, stretch=1)
        path_bar.addWidget(self.go_btn)
        main_layout.addLayout(path_bar)

        # 3. 중앙 스플리터 (좌측 폴더 트리 / 우측 파일·폴더 뷰)
        splitter = QSplitter(Qt.Horizontal)

        self.folder_tree = QTreeView()
        self.folder_tree.setModel(self.dir_model)
        self.folder_tree.setRootIndex(self.dir_model.index(QDir.rootPath()))
        self.folder_tree.setHeaderHidden(False)
        self.folder_tree.setUniformRowHeights(True)
        self.folder_tree.setAnimated(True)
        # 폴더 트리에서는 이름 컬럼만 깔끔하게 노출
        for col in range(1, self.dir_model.columnCount()):
            self.folder_tree.hideColumn(col)

        self.content_view = QTreeView()
        self.content_view.setModel(self.content_model)
        self.content_view.setRootIndex(self.content_model.index(QDir.rootPath()))
        self.content_view.setRootIsDecorated(False)
        self.content_view.setItemsExpandable(False)
        self.content_view.setSortingEnabled(True)
        self.content_view.setUniformRowHeights(True)
        self.content_view.setSelectionMode(QAbstractItemView.SingleSelection)

        header = self.content_view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, self.content_model.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        splitter.addWidget(self.folder_tree)
        splitter.addWidget(self.content_view)
        splitter.setSizes([270, 610])
        main_layout.addWidget(splitter, stretch=1)

        # 4. 선택 경로 미리보기 및 하단 확인/취소 버튼
        self.selected_label = QLabel("선택된 폴더: ")
        self.selected_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.selected_label.setStyleSheet("color: #37474f; padding: 2px 0;")
        main_layout.addWidget(self.selected_label)

        btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("이 폴더 선택")
        self.select_btn.setDefault(True)
        self.select_btn.setStyleSheet(
            "background-color: #0277bd; color: white; font-weight: bold; padding: 6px 14px;"
        )

        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setStyleSheet("padding: 6px 14px;")

        btn_layout.addStretch()
        btn_layout.addWidget(self.select_btn)
        btn_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(btn_layout)

    def _connect_signals(self):
        self.up_btn.clicked.connect(self._go_up)
        self.home_btn.clicked.connect(lambda: self.navigate_to(QDir.homePath()))
        self.new_folder_btn.clicked.connect(self._create_new_folder)
        self.path_edit.returnPressed.connect(self._on_path_entered)
        self.go_btn.clicked.connect(self._on_path_entered)

        self.folder_tree.clicked.connect(self._on_folder_tree_clicked)
        self.content_view.doubleClicked.connect(self._on_content_double_clicked)
        self.content_view.clicked.connect(self._on_content_clicked)

        self.select_btn.clicked.connect(self.on_select_clicked)
        self.cancel_btn.clicked.connect(self.reject)

    def _resolve_initial_dir(self, current_path):
        if current_path:
            norm = os.path.abspath(current_path)
            if os.path.isdir(norm):
                return norm
            if os.path.isfile(norm):
                return os.path.dirname(norm)
        return QDir.homePath()

    def _expand_ancestors(self, target_path):
        """목표 경로까지 좌측 트리의 상위 노드들을 펼칩니다."""
        path = os.path.abspath(target_path)
        ancestors = []
        while True:
            idx = self.dir_model.index(path)
            if idx.isValid():
                ancestors.append(idx)
            parent = os.path.dirname(path)
            if not parent or parent == path:
                break
            path = parent

        for idx in reversed(ancestors):
            self.folder_tree.expand(idx)

    def navigate_to(self, folder_path):
        """지정한 폴더로 좌측 트리와 우측 목록, 주소창을 동기화합니다."""
        if not folder_path or not os.path.isdir(folder_path):
            return

        abs_dir = os.path.abspath(folder_path)
        self._syncing = True
        try:
            self.path_edit.setText(abs_dir)

            # 우측 뷰의 루트를 해당 폴더로 전환
            content_root = self.content_model.index(abs_dir)
            if content_root.isValid():
                self.content_view.setRootIndex(content_root)

            # 좌측 트리에서 해당 폴더 확장 및 선택
            dir_idx = self.dir_model.index(abs_dir)
            if dir_idx.isValid():
                self._expand_ancestors(abs_dir)
                self.folder_tree.setCurrentIndex(dir_idx)
                self.folder_tree.scrollTo(dir_idx)

            self._update_selected_preview(abs_dir)
        finally:
            self._syncing = False

    def _update_selected_preview(self, folder_path):
        self.selected_label.setText(f"선택된 폴더: <b>{folder_path}</b>")

    def _get_current_working_dir(self):
        text_path = self.path_edit.text().strip()
        if text_path and os.path.isdir(text_path):
            return os.path.abspath(text_path)

        idx = self.folder_tree.currentIndex()
        if idx.isValid():
            p = self.dir_model.filePath(idx)
            if os.path.isdir(p):
                return os.path.abspath(p)

        return os.path.abspath(QDir.homePath())

    def _on_folder_tree_clicked(self, index):
        if self._syncing or not index.isValid():
            return
        folder_path = self.dir_model.filePath(index)
        if os.path.isdir(folder_path):
            self.navigate_to(folder_path)

    def _on_content_clicked(self, index):
        if not index.isValid():
            return
        info = self.content_model.fileInfo(index)
        file_path = info.absoluteFilePath()
        if info.isDir():
            self._update_selected_preview(file_path)
        else:
            # 파일을 클릭하더라도 저장/선택 대상은 해당 파일이 속한 폴더로 표시
            self._update_selected_preview(os.path.dirname(file_path))

    def _on_content_double_clicked(self, index):
        if not index.isValid():
            return
        info = self.content_model.fileInfo(index)
        if info.isDir():
            self.navigate_to(info.absoluteFilePath())

    def _on_path_entered(self):
        raw = self.path_edit.text().strip().strip('"')
        if not raw:
            return
        target = os.path.abspath(raw)
        if os.path.isfile(target):
            target = os.path.dirname(target)

        if os.path.isdir(target):
            self.navigate_to(target)
        else:
            QMessageBox.warning(self, "경로 오류", f"존재하지 않는 폴더입니다:\n{raw}")

    def _go_up(self):
        current = self._get_current_working_dir()
        parent = os.path.dirname(current)
        if parent and parent != current and os.path.isdir(parent):
            self.navigate_to(parent)

    def _create_new_folder(self):
        base_dir = self._get_current_working_dir()
        folder_name, ok = QInputDialog.getText(self, "새 폴더", f"생성할 폴더 이름 ({base_dir}):")
        if not ok or not folder_name.strip():
            return

        new_path = os.path.join(base_dir, folder_name.strip())
        try:
            os.makedirs(new_path, exist_ok=False)
            self.navigate_to(new_path)
        except FileExistsError:
            QMessageBox.warning(self, "알림", "이미 같은 이름의 폴더가 있습니다.")
        except OSError as e:
            QMessageBox.critical(self, "생성 실패", f"폴더를 만들 수 없습니다:\n{e}")

    def on_select_clicked(self):
        # 1. 우측 목록에서 현재 선택된 항목 우선 확인
        content_idx = self.content_view.currentIndex()
        if content_idx.isValid():
            info = self.content_model.fileInfo(content_idx)
            path = info.absoluteFilePath()
            if os.path.isdir(path):
                self.selected_path = os.path.abspath(path)
                self.accept()
                return
            if os.path.isfile(path):
                self.selected_path = os.path.abspath(os.path.dirname(path))
                self.accept()
                return

        # 2. 우측 선택이 없으면 좌측 트리 또는 주소창의 현재 폴더 선택
        current_dir = self._get_current_working_dir()
        if os.path.isdir(current_dir):
            self.selected_path = current_dir
            self.accept()
            return

        QMessageBox.warning(self, "선택 오류", "선택된 폴더가 없습니다.")
