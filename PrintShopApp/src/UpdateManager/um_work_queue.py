import queue
from PySide6.QtCore import QThread, Signal
from um_work_handler import UpdateManagerWorkHandler  # TaskHandler 임포트 활성화

from Common.log import logd, loge

class UpdateManagerWorkQueue(QThread):
    """업로드 및 다운로드 작업을 큐(Queue) 기반으로 순차 관리하고 실행하는 비동기 워커"""
    finished_signal = Signal(str, object)            # task_type, result
    error_signal = Signal(str, str)                # version/task_type, err_msg
    progress_signal = Signal(str, int, str, str)   # version, percent, status, message
    total_progress_signal = Signal(int, str)       # percent, message

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.task_queue = queue.Queue()
        self.cancelled_items = set()
        self.cancel_all_flag = False
        logd("UpdateManagerWorkQueue 인스턴스 초기화됨")

    def add_task(self, task_type: str, item_data: dict):
        self.task_queue.put((task_type, item_data))
        logd(f"워커 큐 작업 등록: [{task_type}] 데이터={item_data.get('version', item_data)}")

    def cancel_item(self, version_str: str):
        self.cancelled_items.add(version_str)
        logd(f"워커 개별 작업 취소 요청 등록됨: v{version_str}")

    def cancel_all(self):
        self.cancel_all_flag = True
        logd("워커 전체 작업 취소 플래그 활성화됨")

    def run(self):
        total_tasks = self.task_queue.qsize()
        completed_count = 0
        current_idx = 0
        is_transfer_batch = False
        logd(f"UpdateManagerWorkQueue 스레드 실행 시작 (대기 작업 수: {total_tasks}건)")

        while not self.task_queue.empty() and not self.cancel_all_flag:
            try:
                task_type, item = self.task_queue.get_nowait()
            except queue.Empty:
                break

            logd(f"큐에서 작업 인출: [{task_type}]")

            # 1. 단독 제어 작업 처리 (CHECK_SYNC, FETCH 등)
            if task_type in ["CHECK_SYNC", "FETCH_REMOTE_JSON", "FORCE_UPDATE_REMOTE_JSON", "AUTO_SYNC_JSON"]:
                try:
                    if task_type == "CHECK_SYNC":
                        t_type, result = UpdateManagerWorkHandler.handle_check_sync(self.manager, item)
                    elif task_type == "FETCH_REMOTE_JSON":
                        t_type, result = UpdateManagerWorkHandler.handle_fetch_remote_json(self.manager)
                    elif task_type == "FORCE_UPDATE_REMOTE_JSON":
                        t_type, result = UpdateManagerWorkHandler.handle_force_update_remote_json(self.manager, item)
                    elif task_type == "AUTO_SYNC_JSON":
                        t_type, result = UpdateManagerWorkHandler.handle_auto_sync_json(self.manager)
                        
                    self.finished_signal.emit(t_type, result)
                except Exception as e:
                    loge(f"{task_type} 작업 중 예외 발생: {e}")
                    self.error_signal.emit(task_type, str(e))
                
                self.task_queue.task_done()
                continue

            # 2. 업로드 및 다운로드 큐 작업 처리
            is_transfer_batch = True
            ver = item.get("version")
            if ver in self.cancelled_items:
                logd(f"취소 목록에 포함된 버전 건너뜀: v{ver}")
                self.task_queue.task_done()
                continue

            current_idx += 1

            try:
                def cb(pct, msg):
                    self.progress_signal.emit(ver, pct, "진행 중", msg)
                    overall = int(((current_idx - 1) * 100 + pct) / total_tasks)
                    self.total_progress_signal.emit(overall, msg)

                def check_cancel():
                    return self.cancel_all_flag or (ver in self.cancelled_items)

                success, err_msg = False, ""
                if task_type == "UPLOAD":
                    self.progress_signal.emit(ver, 0, "업로드 중", f"[{current_idx}/{total_tasks}] 버전 v{ver} 업로드 시작...")
                    success, err_msg = UpdateManagerWorkHandler.handle_upload(self.manager, item, current_idx, total_tasks, cb, check_cancel)
                elif task_type == "DOWNLOAD":
                    self.progress_signal.emit(ver, 0, "다운로드 중", f"[{current_idx}/{total_tasks}] 버전 v{ver} 다운로드 시작...")
                    success, err_msg = UpdateManagerWorkHandler.handle_download(self.manager, item, current_idx, total_tasks, cb, check_cancel)

                if success:
                    completed_count += 1
                    logd(f"{task_type} 성공 처리: v{ver}")
                    self.progress_signal.emit(ver, 100, "완료", f"✅ 버전 v{ver} {task_type} 완료!")
                else:
                    loge(f"{task_type} 실패 처리: v{ver} - {err_msg}")
                    self.error_signal.emit(ver, err_msg)

            except Exception as e:
                loge(f"워커 작업 처리 중 예기치 않은 예외 발생 (v{ver}): {e}")
                self.error_signal.emit(ver if ver else "GENERAL", str(e))

            self.task_queue.task_done()

        if self.cancel_all_flag:
            logd("전체 취소 플래그로 인해 워커 루프가 조기 종료되었습니다.")
            self.total_progress_signal.emit(0, "⚠️ 사용자에 의해 모든 작업이 취소되었습니다.")
            
        if is_transfer_batch:
            logd(f"배치 전송 큐 작업 종료 (최종 성공: {completed_count}건)")
            self.finished_signal.emit("QUEUE_FINISHED", completed_count)
