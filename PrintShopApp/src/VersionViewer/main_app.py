import sys
from PySide6.QtWidgets import QApplication
from version_window import VersionViewerWindow


def main():
    app = QApplication(sys.argv)
    window = VersionViewerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()