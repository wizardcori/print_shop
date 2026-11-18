import sys
import time
import threading
from queue import PriorityQueue
from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, 
    QTextEdit, QLabel, QProgressBar, QWidget, QHBoxLayout, 
    QListWidget, QSplitter, QComboBox
)

# ==========================================
# 1. 작업별 우선순위 상수 클래스
# ==========================================
class TaskPriority:
    HIGH = 1     # 긴급 작업 (숫자가 낮을수록 최우선)
    NORMAL = 5   # 일반 작업
    LOW = 10     # 후순위 작업


# ==========================================
# 2. 우선순위 및 취소 관리가 포함된 백그라운드 워커
# ==========================================
class PriorityWorkerThread(QThread):
    task_progress = Signal(str, str, int, str)  # (owner_id, task_name, 퍼센트, 메시지)
    task_finished = Signal(str, str, tuple)     # (owner_id, task_name, (상태, 결과))
    queue_updated = Signal(list)                # 전체 대기열 목록 전달
    current_task_changed = Signal(str, str)     # (owner_id, task_name) 현재 실행 중인 작업

    def __init__(self):
        super().__init__()
        self.task_queue = PriorityQueue()
        self._counter = 0  # 동일 우선순위 간 입력 순서 보장용 (Tie-breaker)
        
        self._is_running = True
        self.current_task_key = None
        self.cancel_flags = {}      # task_key -> threading.Event
        self.active_tasks_info = [] # [(priority, counter, task_key, task_name), ...]

    def add_task(self, priority, task_key, owner_id, task_name, func, args, kwargs):
        cancel_event = threading.Event()
        self.cancel_flags[task_key] = cancel_event
        
        self._counter += 1
        item = (priority, self._counter, (task_key, owner_id, task_name, func, args, kwargs))
        
        self.task_queue.put(item)
        self.active_tasks_info.append((priority, self._counter, task_key, task_name))
        
        # 우선순위 순서대로 정렬 후 큐 상태 갱신
        self.active_tasks_info.sort(key=lambda x: (x[0], x[1]))
        self.emit_queue_status()

    def cancel_task(self, task_key):
        if task_key in self.cancel_flags:
            self.cancel_flags[task_key].set()  # 취소 플래그 ON

        # 대기열 목록에서 제거
        self.active_tasks_info = [t for t in self.active_tasks_info if t[2] != task_key]
        self.emit_queue_status()

    def emit_queue_status(self):
        task_names = [f"[{self.get_priority_name(t[0])}] {t[3]}" for t in self.active_tasks_info]
        self.queue_updated.emit(task_names)

    def get_priority_name(self, p):
        if p == TaskPriority.HIGH: return "긴급"
        elif p == TaskPriority.LOW: return "후순위"
        return "일반"

    def run(self):
        while self._is_running:
            try:
                priority, counter, task_data = self.task_queue.get(timeout=0.5)
                task_key, owner_id, task_name, func, args, kwargs = task_data
            except Exception:
                continue

            self.current_task_key = task_key
            self.current_task_changed.emit(owner_id, task_name)
            
            # 대기열 목록에서 현재 실행 중인 작업 제거 후 갱신
            self.active_tasks_info = [t for t in self.active_tasks_info if t[2] != task_key]
            self.emit_queue_status()

            cancel_event = self.cancel_flags.get(task_key)

            # 진행률 보고 콜백 (취소 여부 실시간 감지 포함)
            def progress_callback(percent, message):
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("작업이 취소되었습니다.")
                self.task_progress.emit(owner_id, task_name, percent, message)

            try:
                kwargs['progress_cb'] = progress_callback
                kwargs['cancel_event'] = cancel_event
                
                # 함수 실행
                result = func(*args, **kwargs)
                
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("작업이 취소되었습니다.")

                self.task_finished.emit(owner_id, task_name, ("SUCCESS", result))
            except InterruptedError as ie:
                self.task_finished.emit(owner_id, task_name, ("CANCELLED", str(ie)))
            except Exception as e:
                self.task_finished.emit(owner_id, task_name, ("ERROR", str(e)))
            finally:
                self.current_task_key = None
                self.current_task_changed.emit("", "없음")
                self.task_queue.task_done()

    def stop(self):
        self._is_running = False
        self.wait()


# ==========================================
# 3. 전역 큐 매니저 (Singleton)
# ==========================================
class TaskManager:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
            cls._instance.worker = PriorityWorkerThread()
            cls._instance.worker.start()
        return cls._instance

    def enqueue(self, priority, task_key, owner_id, task_name, func, *args, **kwargs):
        self.worker.add_task(priority, task_key, owner_id, task_name, func, args, kwargs)

    def cancel(self, task_key):
        self.worker.cancel_task(task_key)

    def get_worker(self):
        return self.worker


# ==========================================
# 4. 공통 베이스 윈도우 (윈도우별 소유자 라우팅 대행)
# ==========================================
class QueueBaseWindow:
    def __init__(self, window_id):
        super().__init__()
        self.window_id = window_id
        
        worker = TaskManager().get_worker()
        worker.task_progress.connect(self._handle_global_progress)
        worker.task_finished.connect(self._handle_global_finished)
        worker.queue_updated.connect(self._handle_global_queue)
        worker.current_task_changed.connect(self._handle_global_current)

    @Slot(str, str, int, str)
    def _handle_global_progress(self, owner_id, task_name, percent, message):
        if owner_id == self.window_id: self.on_task_progress(task_name, percent, message)

    @Slot(str, str, tuple)
    def _handle_global_finished(self, owner_id, task_name, response):
        if owner_id == self.window_id:
            status, data = response
            self.on_task_finished(task_name, status, data)

    @Slot(list)
    def _handle_global_queue(self, task_names): self.on_queue_updated(task_names)

    @Slot(str, str)
    def _handle_global_current(self, owner_id, task_name):
        if owner_id == self.window_id or owner_id == "": 
            self.on_current_task_changed(owner_id, task_name)

    def on_task_progress(self, task_name, percent, message): pass
    def on_task_finished(self, task_name, status, data): pass
    def on_queue_updated(self, task_names): pass
    def on_current_task_changed(self, owner_id, task_name): pass


# ==========================================
# 5. 백그라운드에서 실행될 테스트용 함수
# ==========================================
def sample_background_task(total_steps=8, progress_cb=None, cancel_event=None):
    for step in range(1, total_steps + 1):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("작업 도중 사용자에 의해 취소되었습니다.")
        time.sleep(0.5)
        percent = int((step / total_steps) * 100)
        if progress_cb:
            progress_cb(percent, f"세부 단계 {step}/{total_steps} 실행 중...")
    return "성공적으로 처리가 완료되었습니다!"


# ==========================================
# 6. 메인 윈도우 구현
# ==========================================
# class MainWindow(BaseWindow):
#     def __init__(self):
#         super().__init__(window_id="MAIN_WIN")
#         self.setWindowTitle("PySide 안전한 백그라운드 큐 - 메인 윈도우")
#         self.resize(750, 500)

#         main_layout = QHBoxLayout()
        
#         # 좌측 패널 (제어 및 모니터링)
#         left_widget = QWidget()
#         left_layout = QVBoxLayout(left_widget)

#         self.status_label = QLabel("상태: 대기 중")
#         left_layout.addWidget(self.status_label)

#         self.current_task_label = QLabel("실행 중인 작업: 없음")
#         left_layout.addWidget(self.current_task_label)

#         self.progress_bar = QProgressBar()
#         self.progress_bar.setValue(0)
#         left_layout.addWidget(self.progress_bar)

#         self.text_edit = QTextEdit()
#         self.text_edit.setReadOnly(True)
#         left_layout.addWidget(self.text_edit)

#         # 우선순위 선택 콤보박스
#         priority_layout = QHBoxLayout()
#         priority_layout.addWidget(QLabel("우선순위:"))
#         self.combo_priority = QComboBox()
#         self.combo_priority.addItem("긴급 (HIGH)", TaskPriority.HIGH)
#         self.combo_priority.addItem("일반 (NORMAL)", TaskPriority.NORMAL)
#         self.combo_priority.addItem("후순위 (LOW)", TaskPriority.LOW)
#         self.combo_priority.setCurrentIndex(1)
#         priority_layout.addWidget(self.combo_priority)
#         left_layout.addLayout(priority_layout)

#         btn_layout = QHBoxLayout()
#         self.btn_run = QPushButton("작업 등록하기")
#         self.btn_run.clicked.connect(self.request_task)
#         btn_layout.addWidget(self.btn_run)

#         self.btn_cancel = QPushButton("현재 작업 취소")
#         self.btn_cancel.setStyleSheet("background-color: #ffcccc;")
#         self.btn_cancel.clicked.connect(lambda: self.my_task_key and TaskManager().cancel(self.my_task_key))
#         btn_layout.addWidget(self.btn_cancel)

#         self.btn_sub = QPushButton("서브 윈도우 열기")
#         self.btn_sub.clicked.connect(lambda: SubWindow().show())
#         btn_layout.addWidget(self.btn_sub)

#         left_layout.addLayout(btn_layout)

#         # 우측 패널 (대기열 목록 뷰어)
#         right_widget = QWidget()
#         right_layout = QVBoxLayout(right_widget)
#         right_layout.addWidget(QLabel("📋 우선순위 대기열 (Queue List)"))
        
#         self.queue_list_widget = QListWidget()
#         right_layout.addWidget(self.queue_list_widget)

#         splitter = QSplitter()
#         splitter.addWidget(left_widget)
#         splitter.addWidget(right_widget)
#         splitter.setSizes([450, 300])

#         container = QWidget()
#         root_layout = QVBoxLayout(container)
#         root_layout.addWidget(splitter)
#         self.setCentralWidget(container)

#         self.my_task_key = None

#     def request_task(self):
#         priority = self.combo_priority.currentData()
#         p_name = self.combo_priority.currentText()
        
#         task_name = f"MainTask_{int(time.time() % 1000)}"
#         task_key = f"{self.window_id}_{task_name}"
#         self.my_task_key = task_key

#         self.progress_bar.setValue(0)
        
#         # 큐에 등록
#         TaskManager().enqueue(
#             priority, task_key, self.window_id, task_name, 
#             sample_background_task, total_steps=10
#         )
#         self.text_edit.append(f"[등록] '{task_name}' ({p_name}) 작업이 큐에 적재되었습니다.")

#     def on_task_progress(self, task_name, percent, message):
#         self.progress_bar.setValue(percent)
#         self.status_label.setText(f"<b>[{task_name}]</b> {message} ({percent}%)")

#     def on_task_finished(self, task_name, status, data):
#         if status == "SUCCESS": self.text_edit.append(f"[성공] {data}")
#         elif status == "CANCELLED": self.text_edit.append(f"[취소] {data}")
#         else: self.text_edit.append(f"[에러] {data}")
#         self.progress_bar.setValue(0)
#         self.my_task_key = None

#     def on_queue_updated(self, task_names):
#         self.queue_list_widget.clear()
#         for name in task_names:
#             self.queue_list_widget.addItem(name)

#     def on_current_task_changed(self, owner_id, task_name):
#         if owner_id == self.window_id:
#             self.current_task_label.setText(f"실행 중인 작업: <font color='blue'>{task_name}</font>")
#         elif owner_id == "":
#             self.current_task_label.setText("실행 중인 작업: 없음")

#     def closeEvent(self, event):
#         TaskManager().get_worker().stop()
#         event.accept()


# # ==========================================
# # 7. 서브 윈도우 구현 (동일 큐 공유 예시)
# # ==========================================
# class SubWindow(BaseWindow):
#     def __init__(self):
#         super().__init__(window_id=f"SUB_WIN_{id(self)}")
#         self.setWindowTitle("서브 윈도우")
#         self.resize(350, 250)

#         layout = QVBoxLayout()
#         self.label = QLabel("상태: 대기 중...")
#         layout.addWidget(self.label)

#         self.btn_run = QPushButton("서브창 작업 등록 (긴급)")
#         self.btn_run.clicked.connect(self.request_sub_task)
#         layout.addWidget(self.btn_run)

#         container = QWidget()
#         container.setLayout(layout)
#         self.setCentralWidget(container)
#         self.my_task_key = None

#     def request_sub_task(self):
#         task_name = f"SubTask_{int(time.time() % 1000)}"
#         task_key = f"{self.window_id}_{task_name}"
#         self.my_task_key = task_key

#         # 서브창에서는 긴급(HIGH) 우선순위로 테스트해보기
#         TaskManager().enqueue(
#             TaskPriority.HIGH, task_key, self.window_id, task_name, 
#             sample_background_task, total_steps=6
#         )
#         self.label.setText("서브창 긴급 작업 요청됨")

#     def on_task_progress(self, task_name, percent, message):
#         self.label.setText(f"진행: {percent}% ({message})")

#     def on_task_finished(self, task_name, status, data):
#         if status == "SUCCESS": self.label.setText(f"완료: {data}")
#         else: self.label.setText(f"종료: {status}")


# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     main_win = MainWindow()
#     main_win.show()
#     sys.exit(app.exec())
 