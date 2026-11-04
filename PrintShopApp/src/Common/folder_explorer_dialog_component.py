import os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTreeView, QPushButton, QLabel, QMessageBox
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
    """윈도우 탐색기처럼 파일과 폴더를 모두 보여주며 크기 조절이 가능한 커스텀 대화상자"""
    def __init__(self, current_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("폴더 선택 (탐색기)")
        
        # 크기 조절 가능하도록 최소 크기 및 기본 크기, 창 플래그 설정
        self.setMinimumSize(450, 350)
        self.resize(600, 500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        
        if QFileSystemModel is None:
            QMessageBox.critical(self, "오류", "현재 사용 중인 PySide6 환경에서 QFileSystemModel을 지원하지 않습니다.")
            self.reject()
            return

        self.selected_path = ""
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>폴더와 파일을 확인하고 저장할 폴더를 선택하세요:</b>"))
        
        self.model = QFileSystemModel()
        self.model.setRootPath(QDir.rootPath())
        self.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        
        if current_path and os.path.exists(current_path):
            index = self.model.index(current_path)
            self.tree_view.setRootIndex(self.model.index(QDir.rootPath()))
            self.tree_view.setCurrentIndex(index)
            self.tree_view.scrollTo(index)
        
        layout.addWidget(self.tree_view)
        
        btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("이 폴더 선택")
        self.select_btn.setStyleSheet("background-color: #0277bd; color: white; font-weight: bold; padding: 6px 12px;")
        self.select_btn.clicked.connect(self.on_select_clicked)
        
        cancel_btn = QPushButton("취소")
        cancel_btn.setStyleSheet("padding: 6px 12px;")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.select_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def on_select_clicked(self):
        index = self.tree_view.currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "선택 오류", "선택된 폴더나 파일이 없습니다.")
            return
            
        file_path = self.model.fileInfo(index).absoluteFilePath()
        if os.path.isfile(file_path):
            folder_path = os.path.dirname(file_path)
        else:
            folder_path = file_path
            
        self.selected_path = folder_path
        self.accept()