import win32serviceutil
import win32service
import win32event
import servicemanager
import time
import os

class PythonService(win32serviceutil.ServiceFramework):
    # 윈도우 서비스 이름, 표시 이름, 설명 설정
    _svc_name_ = "PythonTestService"
    _svc_display_name_ = "Python Test Service"
    _svc_description_ = "파이썬으로 만든 샘플 윈도우 서비스입니다."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        # 서비스 중지 신호를 받기 위한 이벤트 생성
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = True

    def SvcStop(self):
        """서비스가 중지될 때 호출되는 메서드"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_running = False

    def SvcDoRun(self):
        """서비스가 시작될 때 메인으로 실행되는 메서드"""
        servicemanager.LogInfoMsg("PythonTestService가 시작되었습니다.")
        self.main()

    def main(self):
        """실제 백그라운드에서 동작할 작업 로직"""
        # 로그 파일 저장 경로 (C:\temp 폴더가 미리 생성되어 있어야 함)
        log_path = r"C:\temp\service_log.txt"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        while self.is_running:
            # 작업 내용 (예: 10초마다 로그 기록)
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"서비스 실행 중... 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            except Exception as e:
                pass

            # 10초 동안 대기하면서 중지 신호(SvcStop)가 들어오는지 모니터링
            rc = win32event.WaitForSingleObject(self.hWaitStop, 10000)
            if rc == win32event.WAIT_OBJECT_0:
                break


if __name__ == '__main__':
    # 명령줄 인자(install, start, stop 등) 처리
    win32serviceutil.HandleCommandLine(PythonService)