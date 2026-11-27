"""LinkShare Wi-Fi Pass Manager Tab & Runtime Implementation."""

import os
import json
import datetime
import threading
from io import BytesIO

try:
    import qrcode
except ImportError:
    qrcode = None

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QGroupBox,
    QSplitter,
    QTabWidget,
    QPushButton,
    QComboBox,
    QLineEdit,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QFile
from PySide6.QtGui import QFontMetrics, QPixmap, QImage
from PySide6.QtUiTools import QUiLoader

from Common.log import logd, loge
from Common.network_utils import escape_wifi_qr_field
from LinkShare.core.customer_request_approval_controller import ApprovalController
from .tabs.internet_share_connected_tab import InternetConnectionTab
from .tabs.internet_share_request_tab import InternetRequestTab
from .tabs.internet_share_approval_tab import InternetApprovalTab
from .tabs.internet_share_history_tab import InternetHistoryTab
from LinkShare.core.usage_history_controller import update_usage_history_tables
from Session import SessionManager

from LinkShare.web.internet_portal import link_share_start
from Common.config import FileConfigManager
from LinkShare.setting.linkshare_settings import LinkshareConfig
from LinkShare.setting.hotspot_settings_tab import HotspotNetworkConfig
from LinkShare.linkshare_signals import LinkShareServerSignals
from .internet_share_filter import InternetShareFilter

from LinkShare.ui.internet_share_approval_dialog import get_approval_dialog
from Common.geometry_manager import AutoSplitterWidget
from .tabs.internet_share_tab_signal_manager import ist_signal_manager


class CollapsibleStatusLabel(QLabel):
    def __init__(self, text="", parent=None):
        if isinstance(text, QWidget):
            parent = text
            text = ""
        super().__init__(text or "", parent)
        self._full_text = str(text or "")
        self._expanded = False
        self.setCursor(Qt.PointingHandCursor)
        self.setWordWrap(True)

        if text:
            self.setText(text)

    def setText(self, text):
        self._full_text = str(text or "")
        self._refresh_display()

    def _refresh_display(self):
        super().setText(self._full_text if self._expanded else self._full_text.split(" | ", 1)[0])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self._refresh_display()
        super().mousePressEvent(event)


class AutoFitTextLabel(QLabel):
    def __init__(self, text="", point_size=11, parent=None):
        if isinstance(text, QWidget):
            parent = text
            text = ""
        super().__init__(text or "", parent)
        self._base_point_size = point_size
        self.setWordWrap(False)

    def resizeEvent(self, event):
        self._fit_font()
        super().resizeEvent(event)

    def _fit_font(self):
        font = self.font()
        font.setBold(True)
        font.setPointSize(self._base_point_size)
        metrics = QFontMetrics(font)
        while font.pointSize() > 7 and metrics.horizontalAdvance(self.text()) > max(
            60, self.width() - 8
        ):
            font.setPointSize(font.pointSize() - 1)
        self.setFont(font)


from .ui.linkshare_layout_ui import Ui_LinkShareLayout


class LinkShareManager(AutoSplitterWidget):
    """LinkShare Wi-Fi Pass Manager QWidget 클래스"""

    title = "🌐 Wi-Fi Pass Manager (LinkShare)"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.client_identity_map = {}
        self.client_metadata_map = {}

        # 원본 QR 픽스맵 저장용 변수 초기화
        self._raw_net_pixmap = QPixmap()
        self._raw_cap_pixmap = QPixmap()

        # --- Qt 시그널 인스턴스 생성 및 슬롯 연결 ---
        self.share_signals = LinkShareServerSignals()
        self.approval_controller = ApprovalController(self)
        self.session_identity_lock = threading.Lock()

        self.tab_objects = []
        self.tab_signals = []

        # Configuration 인스턴스 생성
        self.linkshare_config = LinkshareConfig()
        self.hotspot_config = HotspotNetworkConfig()

        # --- 1. InternetShareFilter 인스턴스 생성 (config 연동으로 영구 저장/복원) ---
        self.share_filter = InternetShareFilter(manager=self, config=self.linkshare_config)

        # --- UI 파일 로드 및 초기화 ---
        self._init_ui()
        self._bind_widgets()
        self._init_events_and_data()
        self.update_qr_codes()

        link_share_start()

    def _init_ui(self):
        """UI 파일 로드 및 메인 레이아웃 구성"""
        loader = QUiLoader()
        loader.registerCustomWidget(CollapsibleStatusLabel)
        loader.registerCustomWidget(AutoFitTextLabel)

        # ==========================================
        # 1. 변환된 파이썬 UI 모듈을 self에 직접 적용
        # ==========================================
        try:
            ui_instance = Ui_LinkShareLayout()
            ui_instance.setupUi(self)
            logd("UI_LOAD (Python Module 성공) : Ui_LinkShareLayout setupUi 완료")
        except Exception as e:
            loge(f"[오류] UI setupUi 실행 중 예외 발생: {e}")
            # 폴백: UI 로드 실패 시 기본 레이아웃 생성
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_tabs = QTabWidget(self)
            main_layout.addWidget(self.main_tabs)

        # self가 곧 UI가 생성된 윈도우/위젯이므로 self.ui를 자기 자신으로 지정
        self.ui = self

    def _bind_widgets(self):
        """UI 컴포넌트 변수 바인딩"""
        self.linkshare_splitter = self.ui.findChild(QSplitter, "linkshare_splitter")

        # QR 코드 관련 위젯 및 그룹박스 바인딩
        self.qr_group_box = self.ui.findChild(QGroupBox, "qr_group_box")

        if self.qr_group_box:
            self.qr_group_box.setTitle("Wi-Fi Portal QR Codes")
            self.qr_group_box.setCheckable(True)
            self.qr_group_box.setChecked(True)
            self.qr_group_box.toggled.connect(self._on_wifi_group_toggled)

        # QR 코드 관련 위젯
        self.hotspot_network_qr_label = self.ui.findChild(QLabel, "hotspot_network_qr_label")
        self.hotspot_network_info_label = self.ui.findChild(QLabel, "hotspot_network_info_label")
        self.network_print_btn = self.ui.findChild(QPushButton, "network_print_btn")

        self.hotspot_qr_label = self.ui.findChild(QLabel, "hotspot_qr_label")
        self.hotspot_qr_caption = self.ui.findChild(QLabel, "hotspot_qr_caption")
        self.hotspot_url_label = self.ui.findChild(QLabel, "hotspot_url_label")
        self.captive_print_btn = self.ui.findChild(QPushButton, "captive_print_btn")

        for qr_lbl in (self.hotspot_network_qr_label, self.hotspot_qr_label):
            if qr_lbl:
                qr_lbl.setMinimumSize(140, 140)
                qr_lbl.setAlignment(Qt.AlignCenter)
                qr_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                qr_lbl.setScaledContents(False)

        # 상태 레이아웃 비율 설정
        status_layout = self.ui.findChild(QHBoxLayout, "status_layout")
        if status_layout:
            status_layout.setStretch(0, 1)
            status_layout.setStretch(1, 0)
            status_layout.setStretch(2, 2)

        # 상태 및 필터 관련 위젯
        self.status_group = self.ui.findChild(QGroupBox, "status_group")
        self.status_title_label = self.ui.findChild(AutoFitTextLabel, "status_title_label")
        self.status_label = self.ui.findChild(AutoFitTextLabel, "status_label")
        self.windows_hotspot_clients_label = self.ui.findChild(
            AutoFitTextLabel, "windows_hotspot_clients_label"
        )

        self.internet_share_tabs = self.ui.findChild(QTabWidget, "internet_share_tabs")
        self.internet_share_filter = self.ui.findChild(QComboBox, "internet_share_filter")
        self.internet_share_start = self.ui.findChild(QLineEdit, "internet_share_start")
        self.internet_share_end = self.ui.findChild(QLineEdit, "internet_share_end")
        self.internet_share_total_label = self.ui.findChild(QLabel, "internet_share_total_label")
        self.show_approval_btn = self.ui.findChild(QPushButton, "show_approval_btn")

    def _init_events_and_data(self):
        """데이터 로드, 시그널/슬롯 연결 및 initial view 설정"""
        window = self.window()

        # 스플릿바 조절 시 실시간 QR 이미지 업데이트 시그널 연결
        if self.linkshare_splitter:
            self._user_custom_splitter_sizes = None
            self.linkshare_splitter.splitterMoved.connect(self._on_splitter_manually_moved)

        # 스플릿바 스타일 및 두께 설정 적용
        self._setup_splitter_style()

        if self.network_print_btn and hasattr(window, "show_network_qr_print_dialog"):
            self.network_print_btn.clicked.connect(window.show_network_qr_print_dialog)
        if self.captive_print_btn and hasattr(window, "show_captive_qr_print_dialog"):
            self.captive_print_btn.clicked.connect(window.show_captive_qr_print_dialog)

        # 1. 탭 생성 및 구조화 (share_filter 주입)
        if self.internet_share_tabs:
            while self.internet_share_tabs.count() > 0:
                self.internet_share_tabs.removeTab(0)

            conn_tab = InternetConnectionTab(window=window, share_filter=self.share_filter)
            requ_tab = InternetRequestTab(window=window, share_filter=self.share_filter)
            appr_tab = InternetApprovalTab(window=window, share_filter=self.share_filter)
            hist_tab = InternetHistoryTab(window=window, share_filter=self.share_filter)

            self.internet_share_tabs.addTab(conn_tab, conn_tab.getTitle())
            self.internet_share_tabs.addTab(requ_tab, requ_tab.getTitle())
            self.internet_share_tabs.addTab(appr_tab, appr_tab.getTitle())
            self.internet_share_tabs.addTab(hist_tab, hist_tab.getTitle())

            self.tab_objects = [conn_tab, requ_tab, appr_tab, hist_tab]

            self.tab_signals = [
                ist_signal_manager.connected_load_filtered_signal,
                ist_signal_manager.request_load_filtered_signal,
                ist_signal_manager.approval_load_filtered_signal,
                ist_signal_manager.history_load_filtered_signal,
            ]

            self.tab_index_to_title = {
                idx: tab.getTitle() for idx, tab in enumerate(self.tab_objects)
            }
            self.tab_title_to_index = {
                tab.getTitle(): idx for idx, tab in enumerate(self.tab_objects)
            }
            self.tab_title_to_object = {tab.getTitle(): tab for tab in self.tab_objects}

            # 2. 탭 상태 초기화 및 등록
            self.share_filter.init_tab_states(list(self.tab_title_to_index.keys()))

            if self.internet_share_filter:
                self.internet_share_filter.clear()
                self.internet_share_filter.addItems(self.share_filter.FILTER_ITEMS)

        # 3. 시그널 바인딩
        if self.internet_share_filter:
            self.internet_share_filter.currentIndexChanged.connect(self.on_filter_combo_changed)
        if self.internet_share_start:
            self.internet_share_start.textChanged.connect(self.on_date_field_changed)
        if self.internet_share_end:
            self.internet_share_end.textChanged.connect(self.on_date_field_changed)
        if self.internet_share_tabs:
            self.internet_share_tabs.currentChanged.connect(self.internet_share_tab_changed)

        for signal, tab in zip(self.tab_signals, self.tab_objects):
            if signal and hasattr(tab, "load_filtered"):
                signal.connect(tab.load_filtered)

        if self.show_approval_btn:
            self.show_approval_btn.clicked.connect(self.open_internet_share_approval_dialog)

        # 4. 저장된 마지막 활성 탭 및 필터 설정 반영 후 로드
        if self.internet_share_tabs:
            saved_tab_index = self.linkshare_config.get("active_tab_index")
            target_idx = (
                saved_tab_index
                if (
                    saved_tab_index is not None
                    and 0 <= saved_tab_index < self.internet_share_tabs.count()
                )
                else 0
            )

            self.internet_share_tab_changed(target_idx)

            self.internet_share_tabs.setCurrentIndex(target_idx)

        # 프로그램 시작 시 미승인 요청 확인 후 자동 팝업
        QTimer.singleShot(200, self.check_pending_requests_on_startup)

    def trigger_table_update(self, current_tab_index=None):
        """현재 선택된 탭의 테이블 데이터를 필터 조건에 맞게 갱신"""
        if current_tab_index is None:
            current_tab_index = self.internet_share_tabs.currentIndex()

        current_tab_name = self.tab_index_to_title.get(current_tab_index, "")
        target_tab_obj = self.tab_title_to_object.get(current_tab_name)

        if not target_tab_obj:
            return

        state = self.share_filter.get_state(current_tab_name)
        filter_name = self.share_filter.get_filter_name(current_tab_name)

    def on_filter_combo_changed(self, combo_index):
        """필터 콤보박스 변경 슬롯"""

        current_tab_idx = self.internet_share_tabs.currentIndex()
        current_tab_name = self.internet_share_tabs.tabText(current_tab_idx)
        combo_text = self.internet_share_filter.currentText()
        logd(f"on_filter_combo_changed tab:{current_tab_idx},{current_tab_name},{combo_text}")

        def set_date_ui(start_str, end_str):
            if self.internet_share_start:
                self.internet_share_start.setText(start_str)
            if self.internet_share_end:
                self.internet_share_end.setText(end_str)

        self.share_filter.handle_filter_combo_changed(
            current_tab_name=current_tab_name,
            current_tab_index=current_tab_idx,
            combo_index=combo_index,
            combo_text=combo_text,
            set_date_callback=set_date_ui,
        )

    def on_date_field_changed(self):
        """날짜 입력 텍스트 변경 슬롯"""
        current_tab_idx = self.internet_share_tabs.currentIndex()
        current_tab_name = self.internet_share_tabs.tabText(current_tab_idx)

        start_val = self.internet_share_start.text() if self.internet_share_start else ""
        end_val = self.internet_share_end.text() if self.internet_share_end else ""

        def set_custom_combo_ui(custom_idx):
            if self.internet_share_filter:
                self.internet_share_filter.setCurrentIndex(custom_idx)

        self.share_filter.handle_date_field_changed(
            current_tab_name=current_tab_name,
            current_tab_index=current_tab_idx,
            start_val=start_val,
            end_val=end_val,
            set_custom_combo_callback=set_custom_combo_ui,
        )

    def internet_share_tab_changed(self, current_tab_idx):
        """탭 전환 슬롯"""
        self.linkshare_config.set("active_tab_index", current_tab_idx)
        current_tab_name = self.internet_share_tabs.tabText(current_tab_idx)

        logd(f"internet_share_tab_changed tab:{current_tab_idx}:{current_tab_name}")

        def sync_ui_widgets(*args):
            if len(args) == 1 and isinstance(args[0], (tuple, list)):
                combo_index, start_str, end_str = args[0]
            elif len(args) == 3:
                combo_index, start_str, end_str = args
            else:
                return

            if self.internet_share_filter:
                self.internet_share_filter.setCurrentIndex(int(combo_index))
            if self.internet_share_start:
                self.internet_share_start.setText(str(start_str))
            if self.internet_share_end:
                self.internet_share_end.setText(str(end_str))

        self.share_filter.handle_tab_changed(
            new_tab_name=current_tab_name,
            new_tab_idx=current_tab_idx,
            sync_ui_callback=sync_ui_widgets,
        )

    def _build_qr_pixmap(self, payload: str) -> QPixmap:
        """텍스트나 불필요한 외곽 여백을 최소화한 순수 QR 코드 QPixmap 생성"""
        if qrcode is None or not payload:
            return QPixmap()

        qr = qrcode.QRCode(version=1, box_size=12, border=1)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qimage = QImage.fromData(buffer.getvalue())
        return QPixmap.fromImage(qimage)

    def _load_qr_pixmap_fallback(
        self, dir_key: str, fallback_dir: str, filename: str, label_tag: str
    ) -> QPixmap:
        """qrcode 모듈 미사용 시 기존 저장된 QR 이미지 파일을 불러오는 폴백"""
        raw_dir = self.hotspot_config.get(dir_key)
        target_dir = str(raw_dir).strip() if raw_dir else fallback_dir
        if not os.path.isabs(target_dir):
            target_dir = os.path.abspath(target_dir)

        file_path = os.path.join(target_dir, filename)
        if not os.path.isfile(file_path):
            logd(f"[LinkShare] {label_tag} QR 파일 없음: {file_path}")
            return QPixmap()

        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            loge(f"[LinkShare] {label_tag} QR 이미지 디코딩 실패: {file_path}")
            return QPixmap()

        return pixmap

    def update_qr_codes(self):
        """현재 핫스팟/포털 설정 기준으로 순수 QR 코드 픽스맵 생성 및 표시"""
        wifi_ssid = self.hotspot_config.get("hotspot_ssid") or "hbwifi"
        wifi_password = self.hotspot_config.get("hotspot_password") or ""
        gateway = self.hotspot_config.get("hotspot_gateway_ip") or "192.168.137.1"
        portal_url = f"http://{gateway}:5000/scan"

        wifi_type = "WPA" if wifi_password else "nopass"
        wifi_payload = (
            f"WIFI:T:{wifi_type};S:{escape_wifi_qr_field(wifi_ssid)};"
            f"P:{escape_wifi_qr_field(wifi_password)};H:false;;"
        )

        net_pixmap = self._build_qr_pixmap(wifi_payload)
        if net_pixmap.isNull():
            net_pixmap = self._load_qr_pixmap_fallback(
                dir_key="network_qr_output_dir",
                fallback_dir="network_qr_codes",
                filename="network_connection_qr_1x.jpg",
                label_tag="네트워크",
            )
        self._raw_net_pixmap = net_pixmap

        cap_pixmap = self._build_qr_pixmap(portal_url)
        if cap_pixmap.isNull():
            cap_pixmap = self._load_qr_pixmap_fallback(
                dir_key="captive_qr_output_dir",
                fallback_dir="captive_qr_codes",
                filename="captive_portal_qr_1x.jpg",
                label_tag="캡티브",
            )
        self._raw_cap_pixmap = cap_pixmap

        self._update_scaled_qr_images()

        displayed_pwd = wifi_password if wifi_password else "(not available)"
        if hasattr(self, "hotspot_network_info_label") and self.hotspot_network_info_label:
            self.hotspot_network_info_label.setText(
                f"SSID: {wifi_ssid}   Password: {displayed_pwd}"
            )

        if hasattr(self, "hotspot_url_label") and self.hotspot_url_label:
            self.hotspot_url_label.setText(portal_url)

    def _update_scaled_qr_images(self):
        """원본 QR 픽스맵을 라벨 가용 영역에 맞춰 정사각형 비율로 스케일링"""
        if (
            hasattr(self, "_raw_net_pixmap")
            and not self._raw_net_pixmap.isNull()
            and hasattr(self, "hotspot_network_qr_label")
            and self.hotspot_network_qr_label
        ):
            self._set_fitted_pixmap(self.hotspot_network_qr_label, self._raw_net_pixmap)

        if (
            hasattr(self, "_raw_cap_pixmap")
            and not self._raw_cap_pixmap.isNull()
            and hasattr(self, "hotspot_qr_label")
            and self.hotspot_qr_label
        ):
            self._set_fitted_pixmap(self.hotspot_qr_label, self._raw_cap_pixmap)

    def _set_fitted_pixmap(self, label, pixmap):
        if pixmap.isNull() or label is None:
            return
        avail_w = max(1, label.width() - 4)
        avail_h = max(1, label.height() - 4)
        target_side = min(avail_w, avail_h)
        if target_side < 20:
            return
        scaled = pixmap.scaled(
            target_side, target_side, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        label.setPixmap(scaled)

    def _on_wifi_group_toggled(self, checked):
        widgets_to_toggle = [
            getattr(self, "hotspot_network_qr_label", None),
            getattr(self, "hotspot_network_info_label", None),
            getattr(self, "network_print_btn", None),
            getattr(self, "hotspot_qr_label", None),
            getattr(self, "hotspot_qr_caption", None),
            getattr(self, "hotspot_url_label", None),
            getattr(self, "captive_print_btn", None),
        ]

        for widget in widgets_to_toggle:
            if widget:
                widget.setVisible(checked)

        if checked:
            self.qr_group_box.setMaximumHeight(16777215)
            if (
                hasattr(self, "_prev_linkshare_splitter_sizes")
                and self._prev_linkshare_splitter_sizes
            ):
                self.linkshare_splitter.setSizes(self._prev_linkshare_splitter_sizes)
        else:
            self._prev_linkshare_splitter_sizes = self.linkshare_splitter.sizes()
            total = sum(self._prev_linkshare_splitter_sizes)
            self.qr_group_box.setMaximumHeight(35)
            self.linkshare_splitter.setSizes([35, max(0, total - 35)])

    def _setup_splitter_style(self):
        if hasattr(self, "linkshare_splitter") and self.linkshare_splitter:
            splitter_style = """
                QSplitter::handle {
                    background-color: #3498db;
                    margin: 6px;
                    border-radius: 8px;
                }
                QSplitter::handle:hover {
                    background-color: #2ecc71;
                }
            """
            self.linkshare_splitter.setHandleWidth(8)
            self.linkshare_splitter.setChildrenCollapsible(False)
            self.linkshare_splitter.setStyleSheet(splitter_style)

    def _on_splitter_manually_moved(self, pos, index):
        if hasattr(self, "linkshare_splitter") and self.linkshare_splitter:
            if not hasattr(self, "_is_collapsed") or not self._is_collapsed:
                self._user_custom_splitter_sizes = self.linkshare_splitter.sizes()
        QTimer.singleShot(0, self._update_scaled_qr_images)

    def open_internet_share_approval_dialog(self):
        approval_dialog = get_approval_dialog()
        approval_dialog.show_unique_dialog(parent=self, session_data=None)

    def check_pending_requests_on_startup(self):
        try:
            from LinkShare.db.internet_share_db import internet_share_db

            records = internet_share_db.load(view_type="REQUEST")
            pending_records = [
                r
                for r in records
                if r.get("overall_status") == "PENDING" or r.get("approval_status") == "PENDING"
            ]
            if pending_records:
                logd(
                    f"[LinkShare] 프로그램 시작 시 미승인 사용 요청 {len(pending_records)}건 감지 -> 승인 다이얼로그 자동 팝업"
                )
                approval_dialog = get_approval_dialog()
                approval_dialog.show_unique_dialog(parent=self, session_data=None)
        except Exception as e:
            loge(f"[LinkShare] 미승인 요청 확인 중 오류 발생: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._update_scaled_qr_images)
        QTimer.singleShot(100, self._update_scaled_qr_images)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_scaled_qr_images)

        if hasattr(self, "linkshare_splitter") and self.linkshare_splitter:
            if hasattr(self, "_user_custom_splitter_sizes") and self._user_custom_splitter_sizes:
                if not hasattr(self, "_is_collapsed") or not self._is_collapsed:
                    self.linkshare_splitter.setSizes(self._user_custom_splitter_sizes)
