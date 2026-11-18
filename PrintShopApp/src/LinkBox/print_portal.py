import os
import qrcode
import io
import base64
import threading  # 백그라운드 스레드 실행용
from fastapi import BackgroundTasks, UploadFile, File
from nicegui import ui, app

from Common.path_mgr import PathMgr

os.makedirs(paths.QRCODE_DIR, exist_ok=True)

# 외부 모바일 접속을 원활하게 하려면 '0.0.0.0'으로 설정하는 것이 좋습니다.
PRINT_PORTAL_SERVICE_IP = '0.0.0.0'
PRINT_PORTAL_SERVICE_PORT = 8080

PRINT_SERVICE_COOKIE = 'print_service_client_token'


state = {
    "zone": "Counter",
    "files": [
        {
            "id": "file_1",
            "name": "Report_Document.pdf",
            "size": "2.4 MB",
            "pages": [
                {"page_num": i, "enabled": True, "color": "Color", "copies": 1, 
                 "preview": f"https://via.placeholder.com/150x200?text=Page+{i}"}
                for i in range(1, 5)
            ]
        }
    ]
}

url = f"http://{PRINT_PORTAL_SERVICE_IP}:{PRINT_PORTAL_SERVICE_PORT}"
qr = qrcode.QRCode(version=1, box_size=10, border=2)
qr.add_data(url)
qr.make(fit=True)
qr_img = qr.make_image(fill_color="black", back_color="white")

qr_path = os.path.join(paths.QRCODE_DIR, "service_qr.png")
qr_img.save(qr_path)

buf = io.BytesIO()
qr_img.save(buf, format="PNG")
qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

def play_completion_sound():
    logd("[알림] 전송 완료 사운드 재생 트리거됨")

@app.post("/api/upload")
async def api_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    file_id = f"file_{os.urandom(4).hex()}"
    saved_path = os.path.join(paths.QRCODE_DIR, file.filename)
    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)
    background_tasks.add_task(play_completion_sound)
    return {"status": "success", "file_id": file_id, "filename": file.filename}

# 메인 페이지 함수 내부에 전체 UI 구조를 포함시켜 전역 스코프 충돌을 해결합니다.
@ui.page('/')
def print_main_page():
    ui.dark_mode().enable()
    
    with ui.column().classes('w-full max-w-[700px] mx-auto p-4 gap-4 min-h-screen bg-gray-950 text-white'):
        
        with ui.card().classes('w-full bg-gray-900 border border-gray-800 p-5 rounded-xl shadow-lg gap-3'):
            ui.label('🖨️ 스마트 프린트 파일 전송 & 프리뷰').classes('text-2xl font-bold text-blue-400')
            
            with ui.row().classes('items-center gap-2 text-sm text-gray-300'):
                ui.label('현재 구역:')
                ui.badge(state["zone"]).classes('bg-blue-600 text-white font-bold')
                ui.label(f'| 서비스 IP: {PRINT_PORTAL_SERVICE_IP}').classes('text-xs text-gray-400')

            user_name_input = ui.input(label='사용자명 (선택)', placeholder='예: 홍길동').classes('w-full')

            with ui.row().classes('items-center justify-between w-full pt-2 gap-2'):
                file_upload = ui.upload(
                    label='파일 선택', 
                    multiple=True, 
                    auto_upload=False
                ).classes('max-w-[220px]')
                
                transfer_button = ui.button('파일 전송 및 렌더링', on_click=lambda: handle_upload()).classes('bg-blue-600 font-bold flex-1')
                transfer_button.disable()

            selection_count = ui.label('선택 파일 0개').classes('text-xs text-gray-400')

        file_list_container = ui.column().classes('w-full gap-3')

        def on_files_changed():
            count = len(file_upload.files)
            selection_count.text = f'선택 파일 {count}개'
            transfer_button.enabled = count > 0

        file_upload.on('value-change', on_files_changed)

        def handle_upload():
            if not file_upload.files:
                return
            ui.notify('파일이 성공적으로 전송되었으며 미리보기가 생성됩니다!', type='positive')
            play_completion_sound()
            file_upload.clear()
            selection_count.text = '선택 파일 0개'
            transfer_button.disable()
            refresh_file_list()

        with ui.dialog() as detail_dialog, ui.card().classes('w-[92vw] max-w-[1050px] h-[85vh] bg-gray-900 border border-gray-700 flex flex-col p-4 gap-4 shadow-2xl'):
            
            with ui.row().classes('w-full items-center justify-between border-b border-gray-800 pb-3'):
                modal_title = ui.label('🔍 페이지별 상세 프리뷰 및 인쇄 옵션').classes('text-lg font-bold text-white')
                
                with ui.row().classes('items-center gap-3'):
                    ui.label('확대/축소:').classes('text-xs text-gray-400')
                    zoom_slider = ui.slider(min=80, max=220, value=120, step=10).classes('w-32')
                    ui.button('닫기', on_click=detail_dialog.close).classes('bg-red-600 text-white font-bold text-xs px-3 py-1')

            scroll_area = ui.scroll_area().classes('w-full flex-1 p-2')
            modal_grid = ui.grid(columns=2).classes('w-full gap-4')

        def open_detail_modal(file_item):
            modal_title.text = f"🔍 {file_item['name']} - 페이지별 상세 설정"
            modal_grid.clear()
            
            with modal_grid:
                for page in file_item['pages']:
                    with ui.card().classes('bg-gray-800 p-3 gap-3 border border-gray-700 flex flex-row items-center justify-between'):
                        
                        img = ui.image(page['preview']).classes('object-contain rounded border border-gray-600 bg-black/40')
                        zoom_slider.on('value-change', lambda e, im=img: im.style(f'width: {e.args}px; height: auto;'))
                        img.style('width: 120px; height: auto;')
                        
                        with ui.column().classes('flex-1 gap-2 pl-2'):
                            with ui.row().classes('w-full justify-between items-center'):
                                ui.label(f'P.{page["page_num"]}').classes('text-white font-bold text-sm')
                                ui.checkbox('출력', value=page['enabled']).bind_value(page, 'enabled').classes('text-xs text-gray-300')
                            
                            ui.select(['Color', 'Black & White'], value=page['color']).bind_value(page, 'color').classes('w-full bg-gray-700 text-white text-xs')
                            
                            with ui.row().classes('items-center justify-between w-full pt-1'):
                                ui.label('수량:').classes('text-xs text-gray-400')
                                with ui.row().classes('items-center gap-1'):
                                    copies_lbl = ui.label(str(page['copies'])).classes('text-white font-bold text-xs px-2')
                                    
                                    def dec(p=page, lbl=copies_lbl):
                                        p['copies'] = max(1, p['copies'] - 1)
                                        lbl.text = str(p['copies'])
                                    def inc(p=page, lbl=copies_lbl):
                                        p['copies'] = min(99, p['copies'] + 1)
                                        lbl.text = str(p['copies'])
                                        
                                    ui.button('−', on_click=dec).classes('w-6 h-6 bg-gray-700 text-white text-xs p-0')
                                    ui.button('+', on_click=inc).classes('w-6 h-6 bg-blue-600 text-white text-xs p-0')

            detail_dialog.open()

        def refresh_file_list():
            file_list_container.clear()
            with file_list_container:
                for file_item in state["files"]:
                    with ui.card().classes('w-full bg-gray-900 border border-gray-800 p-4 flex flex-row items-center justify-between'):
                        with ui.column().classes('gap-1'):
                            ui.label(file_item['name']).classes('text-white font-bold text-sm')
                            ui.label(f"용량: {file_item['size']} | 총 {len(file_item['pages'])}페이지").classes('text-xs text-gray-400')
                        
                        ui.button('출력 자세히보기', icon='visibility', on_click=lambda fi=file_item: open_detail_modal(fi)).classes('bg-blue-600 text-white font-bold text-xs')

        refresh_file_list()

        with ui.expansion('모바일 접속 QR 코드 보기', icon='qr_code').classes('w-full bg-gray-900 border border-gray-800 rounded-lg'):
            with ui.column().classes('items-center w-full p-4 gap-2'):
                ui.label(f'저장 경로: {paths.QRCODE_DIR}/service_qr.png').classes('text-xs text-gray-400')
                ui.image(f'data:image/png;base64,{qr_base64}').classes('w-36 h-36')

# 데스크톱 앱(PySide6) 등에서 호출하여 백그라운드 스레드로 서버를 띄울 수 있는 함수
def start_print_portal_background(host=PRINT_PORTAL_SERVICE_IP, port=PRINT_PORTAL_SERVICE_PORT):
    """NiceGUI 웹 서버를 백그라운드 스레드로 실행합니다."""
    def run_server():
        ui.run(host=host, port=port, title='스마트 프린트 클라이언트', reload=False, dark=True, show=False)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    logd(f"[Server] 스마트 프린트 웹 서버가 백그라운드(http://{host}:{port})에서 구동되었습니다.")

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(host=PRINT_PORTAL_SERVICE_IP, port=PRINT_PORTAL_SERVICE_PORT, title='스마트 프린트 클라이언트', reload=False, dark=True)