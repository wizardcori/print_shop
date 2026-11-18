import os
import sys

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget, QMainWindow

class UiHelper:
    """UI 모듈 로드 및 파일 경로 유틸리티 클래스"""

    @staticmethod
    def load_ui_smart(loader: QUiLoader, ui_path: str = None, ui_name: str = "main", caller_file: str = None):
        """
        오직 변환된 파이썬 UI 모듈(ui_*.py)만 임포트하여 로드합니다.
        """
        from Common.log import logd, loge

        caller_frame = sys._getframe(1)
        target_widget = caller_frame.f_locals.get('self', None)

        if target_widget is None:
            loge("[오류] load_ui_smart: 클래스 내부의 'self'를 감지할 수 없습니다.")
            return None

        if not caller_file:
            caller_file = caller_frame.f_globals.get('__file__', None)

        if caller_file:
            caller_dir = os.path.dirname(os.path.abspath(caller_file))
            if ui_path:
                ui_path = os.path.abspath(os.path.join(caller_dir, ui_path))
            else:
                ui_path = caller_dir

        if ui_path and os.path.isfile(ui_path):
            ui_path = os.path.dirname(ui_path)

        if ui_name:
            ui_name = os.path.splitext(ui_name)[0]

        module_name = f"ui_{ui_name}"

        if ui_path and ui_path not in sys.path:
            sys.path.insert(0, os.path.abspath(ui_path))

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            if sys._MEIPASS not in sys.path:
                sys.path.insert(0, sys._MEIPASS)

        try:
            logd(f"[DEBUG] UI 모듈 임포트 시도: '{module_name}' (경로: {ui_path})")
            ui_module = __import__(module_name, fromlist=[f"ui_{ui_name.capitalize()}"])
            
            ui_class_name = next((attr for attr in dir(ui_module) if attr.startswith("Ui_")), None)
            
            if ui_class_name:
                ui_class = getattr(ui_module, ui_class_name)
                
                if "MainWindow" in ui_class_name or ui_name.lower() in ["main", "print_shop_app"]:
                    loaded_ui = QMainWindow(target_widget)
                else:
                    loaded_ui = QWidget(target_widget)
                    
                ui_instance = ui_class()
                ui_instance.setupUi(loaded_ui)
                
                target_widget.ui = loaded_ui
                logd(f"UI_LOAD (Python Module 성공) : 모듈명={module_name}, 클래스명={ui_class_name}")
                return loaded_ui
            else:
                loge(f"[오류] 모듈({module_name}) 내에 'Ui_'로 시작하는 클래스가 없습니다.")
                return None
                
        except Exception as e:
            loge(f"[오류] 파이썬 UI 모듈({module_name}) 로드 중 예외 발생: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def get_ui_file_path(file_path, sub_folder, filename):
        """__file__, 서브 폴더명, 파일명을 인자로 받아 UI 파일의 절대 경로를 반환합니다."""
        current_dir = os.path.dirname(os.path.abspath(file_path))
        ui_path = os.path.join(current_dir, sub_folder, filename)
        if not os.path.exists(ui_path):
            ui_path = os.path.join(current_dir, filename)
        return ui_path
