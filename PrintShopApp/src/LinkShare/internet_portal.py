import os
import qrcode
import io
import base64
import threading
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

# 1. NiceGUI와 충돌하지 않는 독립된 FastAPI 앱 생성
app = FastAPI(title="Internet Sharing & Pass Portal")

QR_SAVE_FOLDER = os.path.abspath("qr_codes")
os.makedirs(QR_SAVE_FOLDER, exist_ok=True)

INTERNET_PORTAL_SERVICE_IP = '0.0.0.0'
INTERNET_PORTAL_SERVICE_PORT = 8081

# 세션 및 상태 관리 변수
session_state = {
    "status": "None",          # None, Pending, Approved, Rejected, Expired
    "start_time": "-",
    "end_time": "-",
    "remaining_seconds": 0,
    "total_used_seconds": 0,
    "internet_status": "확인 대기"
}

# 2. 메인 페이지 요청 시 동일 폴더에 있는 internet_portal.html 파일을 읽어서 반환
@app.get("/", response_class=HTMLResponse)
async def internet_portal_home():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "internet_portal.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h3>internet_portal.html 파일을 찾을 수 없습니다.</h3>", status_code=404)

# 3. API 엔드포인트 정의 (portal.html의 JS 요청 처리)
@app.get("/request")
async def api_request(min: int = 30):
    session_state["status"] = "Pending"
    session_state["remaining_seconds"] = min * 60
    session_state["start_time"] = "방금전"
    session_state["end_time"] = f"{min}분 후"
    return {"status": "success", "msg": f"{min}분 인터넷 사용요청이 접수되었습니다.", "session": session_state}

@app.get("/status")
async def api_status(wait: int = 0):
    return session_state

@app.get("/internet-status")
async def api_internet_status(request: Request):
    return {"status": "success"}

# 4. 백그라운드 스레드 실행 함수 (uvicorn)
def start_internet_portal_background(host=INTERNET_PORTAL_SERVICE_IP, port=INTERNET_PORTAL_SERVICE_PORT):
    """internet_portal.html을 인클루드하여 서빙하는 독립된 FastAPI 서버를 백그라운드 스레드로 실행합니다[cite: 5]."""
    def run_server():
        uvicorn.run(app, host=host, port=port, log_level="warning")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print(f"[Server] 인터넷 공유 및 패스 포털 서버가 백그라운드(http://{host}:{port})에서 구동되었습니다[cite: 5].")

if __name__ in {"__main__", "__mp_main__"}:
    uvicorn.run(app, host=INTERNET_PORTAL_SERVICE_IP, port=INTERNET_PORTAL_SERVICE_PORT, log_level="info")