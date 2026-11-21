from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

for p in (str(PROJECT_ROOT), str(SRC_DIR), str(CURRENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import Common.log as common_log  # noqa: E402
from Common.log import WindowLogColorHandlerBase, logd, loge, set_file_tag  # noqa: E402

set_file_tag("BUILD_MGR")

from build_script.build import BuildApp, PrintShopBuildStepTimer, parse_targets  # noqa: E402
from build_script.build_targets import BuildTargets, DEFAULT_CONFIG_FILENAME  # noqa: E402
from build_script.target_config_io import InstallerBuildConfig  # noqa: E402
from build_target_config_tab import BuildTargetConfigTab  # noqa: E402
from BuildManagerApp.settings_window import SettingsWindow  # noqa: E402
from Common.prio_worker_queue import CancelToken, TaskListenerBase, TaskManager, TaskPriority  # noqa: E402

MANAGER_STATE_FILENAME: str = "build_manager_state.json"


class SingleLineFitCheckBox(QCheckBox):
    """한 줄에 모두 표시하되 가용 폭을 넘으면 글꼴 크기를 자동으로 축소하는 체크박스."""

    def __init__(
        self,
        text: str = "",
        base_pt: float = 10.0,
        min_pt: float = 7.5,
        indicator_reserve_px: int = 22,
        h_pad: int = 8,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._full_text = text
        self._base_pt = base_pt
        self._min_pt = min_pt
        self._indicator_reserve_px = indicator_reserve_px
        self._h_pad = h_pad
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def fullText(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text or ""
        super().setToolTip(self._full_text)
        self._refit_font()
        self.updateGeometry()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refit_font()

    def _calc_fitted_font_and_width(self, available_width: int) -> tuple[Any, int]:
        font = self.font()
        clean_text = self._full_text or ""
        if not clean_text:
            font.setPointSizeF(self._base_pt)
            return font, self._indicator_reserve_px + self._h_pad

        text_budget = max(12, available_width - self._indicator_reserve_px - self._h_pad)
        chosen_pt = self._min_pt
        pt = self._base_pt
        while pt >= self._min_pt:
            font.setPointSizeF(pt)
            fm = QFontMetrics(font)
            if fm.horizontalAdvance(clean_text) <= text_budget:
                chosen_pt = pt
                break
            pt = round(pt - 0.5, 2)

        font.setPointSizeF(chosen_pt)
        fm = QFontMetrics(font)
        desired_w = fm.horizontalAdvance(clean_text) + self._indicator_reserve_px + self._h_pad
        return font, desired_w

    def _refit_font(self) -> None:
        avail = self.width() if self.width() > 0 else self.maximumWidth()
        if avail <= 0:
            avail = 10_000
        font, _ = self._calc_fitted_font_and_width(avail)
        self.setFont(font)
        super().setText(self._full_text)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        _, desired_w = self._calc_fitted_font_and_width(10_000)
        hint.setWidth(desired_w)
        return hint

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        font = self.font()
        font.setPointSizeF(self._min_pt)
        fm = QFontMetrics(font)
        min_text_w = fm.horizontalAdvance(self._full_text or "")
        hint.setWidth(min_text_w + self._indicator_reserve_px + self._h_pad)
        return hint


BUILD_APP_ACCEPTED_KEYS: set[str] = {
    "project_root",
    "targets",
    "bump_unit",
    "bump_units",
    "mode",
    "skip_installer",
    "installer_only",
    "installer_targets",
    "clean_build",
    "clean_work_out",
    "clean_dist_out",
    "clean_spec",
    "progress_callback",
    "timer",
    "dir_config_json",
    "app_config_json",
    "installer_config_json",
    "dir_overrides",
    "cli_dir_overrides",
    "app_overrides",
    "cli_app_overrides",
    "installer_overrides",
    "cli_installer_overrides",
}


def run_build_job(
    build_kwargs: dict[str, Any],
    progress_cb: Any = None,
    cancel_event: threading.Event | None = None,
    cancel_token: CancelToken | None = None,
) -> dict[str, Any]:
    """
    PriorityWorkerThread에서 실행되는 작업 래퍼 함수.
    - job_type == "clean": BuildTargets 단일 기준 빌드 출력 디렉터리 정리 전용 작업 수행
    - job_type == "app" / "installer": BuildApp 파이프라인 실행
    """
    active_event = cancel_token.event if cancel_token is not None else cancel_event
    if active_event and active_event.is_set():
        raise InterruptedError("빌드 시작 전 취소되었습니다.")

    job_type = str(build_kwargs.get("job_type") or "app")
    target_app = build_kwargs.get("target_app")
    project_root = str(build_kwargs.get("project_root") or PROJECT_ROOT)

    if job_type == "clean":
        if callable(progress_cb):
            progress_cb(10, "빌드 출력 디렉터리 정리 중...")

        BuildTargets.configure(
            project_root=project_root,
            json_path=build_kwargs.get("dir_config_json"),
            code_overrides=build_kwargs.get("dir_overrides"),
            app_overrides=build_kwargs.get("app_overrides"),
        )
        if active_event and active_event.is_set():
            raise InterruptedError("디렉터리 정리 중 취소되었습니다.")

        removed_dirs = BuildTargets.clean_output_dirs(project_root, include_test=True)
        for removed in removed_dirs:
            logd(f"[CleanJob] 디렉터리 정리 완료: {removed}")

        if callable(progress_cb):
            progress_cb(100, "빌드 출력 디렉터리 정리 완료")

        return {
            "ok": True,
            "job_type": "clean",
            "target_app": None,
            "removed_dirs": removed_dirs,
            "message": f"빌드 출력 디렉터리 정리 완료 ({len(removed_dirs)}개 폴더)",
        }

    timer = PrintShopBuildStepTimer()
    kwargs = {k: v for k, v in build_kwargs.items() if k in BUILD_APP_ACCEPTED_KEYS}
    kwargs["timer"] = timer

    def _on_build_progress(payload: dict[str, Any]) -> None:
        if active_event and active_event.is_set():
            raise InterruptedError("빌드 진행 중 취소되었습니다.")
        if callable(progress_cb):
            pct = payload.get("percent")
            safe_pct = max(0, min(100, int(pct))) if isinstance(pct, (int, float)) else 0
            detail = str(payload.get("detail") or payload.get("step_key") or "빌드 진행 중...")
            progress_cb(safe_pct, detail)

    kwargs["progress_callback"] = _on_build_progress

    logd(
        f"[BuildJob] BuildApp 실행 준비 (job_type={job_type}, target_app={target_app}, "
        f"targets={kwargs.get('targets')}, bump_unit={kwargs.get('bump_unit')}, "
        f"installer_only={kwargs.get('installer_only')}, mode={kwargs.get('mode')})"
    )
    try:
        app = BuildApp(**kwargs, cancel_event=active_event, cancel_token=cancel_token)
    except TypeError:
        try:
            app = BuildApp(**kwargs, cancel_event=active_event)
        except TypeError:
            app = BuildApp(**kwargs)

    if active_event and active_event.is_set():
        raise InterruptedError("빌드 초기화 직후 취소되었습니다.")

    ok = bool(app.run())
    if active_event and active_event.is_set():
        raise InterruptedError("사용자에 의해 빌드가 취소되었습니다.")

    if not ok:
        raise RuntimeError(f"빌드 파이프라인이 실패했습니다. (job_type={job_type}, target_app={target_app})")

    label = str(target_app) if target_app else ("installer" if job_type == "installer" else job_type)
    return {
        "ok": True,
        "job_type": job_type,
        "target_app": target_app,
        "message": f"[{label}] 작업이 성공적으로 완료되었습니다.",
        "timer": timer,
    }


class BuildTaskListener(TaskListenerBase):
    """
    BuildManagerWindow 전용 작업 이벤트 리스너.
    - QMainWindow 다중 상속 대신 위임/리스너 패턴을 사용합니다.
    - owner_widget=window로 weakref 생존 여부를 추적합니다.
    """

    def __init__(self, window: "BuildManagerWindow") -> None:
        super().__init__(owner_widget=window)
        self._window = window

    def on_task_progress(self, task_key: str, task_name: str, percent: int, message: str) -> None:
        if task_key not in self._window._active_build_keys:
            return
        self._window.progress_bar.setValue(max(0, min(100, int(percent))))
        self._window.lbl_progress_detail.setText(f"[{task_name}] {message}")

    def on_task_finished(self, task_key: str, task_name: str, status: str, data: Any) -> None:
        timing = TaskManager().get_timing(task_key)
        if timing is not None:
            logd(f"[BuildManager] 작업 시점 요약 ({task_name}) -> {timing.format_summary()}")

        was_tracked = task_key in self._window._active_build_keys
        self._window._active_build_keys.discard(task_key)

        ok = status == "SUCCESS"
        if isinstance(data, dict):
            msg = str(data.get("message") or status)
        else:
            msg = str(data) if data is not None else status

        if timing is not None and timing.run_sec is not None:
            msg = f"{msg} (실행 {timing.run_sec:.2f}s / 총 {timing.total_sec:.2f}s)"

        if status == "CANCELLED":
            logd(f"[BuildManager] [{task_name}] {msg}", level="info")
        elif status == "ERROR":
            loge(f"[BuildManager] [{task_name}] {msg}")

        if not was_tracked:
            return

        remaining = len(self._window._active_build_keys)
        total = max(1, self._window._total_build_count)
        done = total - remaining

        if remaining > 0:
            self._window.lbl_progress_detail.setText(
                f"[{task_name}] {msg} ({done}/{total} 완료, 남은 작업 {remaining}개)"
            )
            if self._window.statusBar():
                self._window.statusBar().showMessage(f"빌드 진행 중 ({done}/{total} 완료)", 4000)
            return

        self._window._total_build_count = 0
        self._window._on_build_finished(ok, msg)


def load_manager_ui_state(state_path: Path) -> dict[str, Any]:
    if not state_path.is_file():
        return {}
    try:
        with open(state_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_manager_ui_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


class BuildManagerWindow(QMainWindow):
    """PrintShopApp 빌드 관리 메인 윈도우."""

    def __init__(
        self,
        project_root: str | Path = PROJECT_ROOT,
        config_path: str | Path | None = None,
        state_path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_root = Path(project_root).resolve()
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else (self.project_root / DEFAULT_CONFIG_FILENAME)
        )
        self.state_path = (
            Path(state_path).resolve()
            if state_path
            else (self.project_root / MANAGER_STATE_FILENAME)
        )

        self._target_checks: dict[str, SingleLineFitCheckBox] = {}
        self._dir_overrides: dict[str, Any] = {}
        self._app_overrides: dict[str, dict[str, Any]] = {}
        self._installer_overrides: dict[str, Any] = {}
        self._active_build_keys: set[str] = set()
        self._total_build_count: int = 0
        self._build_listener = BuildTaskListener(self)
        self._log_handler: WindowLogColorHandlerBase | None = None
        self._settings_window: SettingsWindow | None = None
        self._build_target_window: BuildTargetConfigTab | None = None
        self._is_closing: bool = False

        # C++ 객체 소멸 시 안전망 (위젯 메서드 접근 없이 큐 정리 및 로그 핸들러 분리)
        self.destroyed.connect(self._on_destroyed_cleanup)

        self.setWindowTitle(f"PrintShop Build Manager - {self.project_root.name}")
        self.resize(920, 720)

        self._init_ui()
        self._setup_logging()
        self._refresh_target_checkboxes()
        self._load_saved_state()
        self._init_settings_window()
        self._init_build_target_window()

    def _on_destroyed_cleanup(self, *_args: Any) -> None:
        TaskManager().on_window_closing(self._build_listener)
        self._dispose_build_target_window()
        self._teardown_logging()

    def _setup_logging(self) -> None:
        self._teardown_logging()

        try:
            handler = WindowLogColorHandlerBase(
                owner_window=self,
                log_widget=self.log_viewer,
                level=logging.DEBUG,
                require_top_level=True,
            )
            targets: list[logging.Logger] = [logging.getLogger()]
            shared = getattr(common_log, "_shared_logger", None)
            if shared is not None and getattr(shared, "logger", None) is not None:
                targets.append(shared.logger)

            handler.attach_to_loggers(targets)
            self._log_handler = handler
        except Exception as exc:
            loge(f"[BuildManager] UI 로그 핸들러 초기화 실패: {exc}")

    def _teardown_logging(self) -> None:
        handler = self._log_handler
        self._log_handler = None
        if handler is not None:
            handler.detach()

    def _on_clear_log(self) -> None:
        self.log_viewer.clear()

    def _init_ui(self) -> None:
        self.build_page = self._create_build_page()
        self.setCentralWidget(self.build_page)

        if self.statusBar():
            self.statusBar().showMessage("준비됨")

    def _create_build_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        top_bar = QHBoxLayout()
        self.lbl_project_info = QLabel(f"프로젝트: {self.project_root}")
        self.lbl_project_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top_bar.addWidget(self.lbl_project_info, stretch=1)

        self.btn_open_build_target = QPushButton("BuildTarget")
        self.btn_open_build_target.clicked.connect(self._on_open_build_target)
        top_bar.addWidget(self.btn_open_build_target)

        self.btn_open_settings = QPushButton("설정")
        self.btn_open_settings.clicked.connect(self._on_open_settings)
        top_bar.addWidget(self.btn_open_settings)
        layout.addLayout(top_bar)

        targets_group = QGroupBox("빌드 대상 선택")
        targets_hbox = QHBoxLayout(targets_group)
        targets_hbox.setContentsMargins(8, 6, 8, 6)
        targets_hbox.setSpacing(6)

        self.chk_all_targets = SingleLineFitCheckBox("All", base_pt=10.0, min_pt=7.5)
        self.chk_all_targets.setTristate(True)
        self.chk_all_targets.clicked.connect(self._on_all_targets_clicked)
        targets_hbox.addWidget(self.chk_all_targets, stretch=0)

        self.targets_row_layout = QHBoxLayout()
        self.targets_row_layout.setContentsMargins(0, 0, 0, 0)
        self.targets_row_layout.setSpacing(6)
        targets_hbox.addLayout(self.targets_row_layout, stretch=1)

        self.chk_installer_target = SingleLineFitCheckBox("인스톨러", base_pt=10.0, min_pt=7.5)
        self.chk_installer_target.stateChanged.connect(self._on_installer_target_changed)
        targets_hbox.addWidget(self.chk_installer_target, stretch=0)

        layout.addWidget(targets_group)

        opts_group = QGroupBox("빌드 옵션")
        opts_layout = QGridLayout(opts_group)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["production", "development"])

        self.combo_bump = QComboBox()
        self.combo_bump.addItem("변경 없음 (none)", userData=None)
        self.combo_bump.addItem("patch", userData="patch")
        self.combo_bump.addItem("minor", userData="minor")
        self.combo_bump.addItem("major", userData="major")

        self.chk_skip_installer = QCheckBox("인스톨러 건너뜀 (--skip-installer)")
        self.chk_skip_installer.stateChanged.connect(self._on_skip_installer_changed)
        self.chk_installer_only = QCheckBox("인스톨러만 생성 (--installer-only)")
        self.chk_clean_build = QCheckBox("전체 빌드 폴더 정리 (--clean)")
        self.chk_clean_work = QCheckBox("work 폴더 정리 (--clean-work)")
        self.chk_clean_dist = QCheckBox("dist 폴더 정리 (--clean-dist)")
        self.chk_clean_spec = QCheckBox(".spec 파일 정리 (--clean-spec)")

        opts_layout.addWidget(QLabel("배포 모드"), 0, 0)
        opts_layout.addWidget(self.combo_mode, 0, 1)
        opts_layout.addWidget(QLabel("버전 증가"), 0, 2)
        opts_layout.addWidget(self.combo_bump, 0, 3)

        opts_layout.addWidget(self.chk_skip_installer, 1, 0, 1, 2)
        opts_layout.addWidget(self.chk_installer_only, 1, 2, 1, 2)
        opts_layout.addWidget(self.chk_clean_build, 2, 0)
        opts_layout.addWidget(self.chk_clean_work, 2, 1)
        opts_layout.addWidget(self.chk_clean_dist, 2, 2)
        opts_layout.addWidget(self.chk_clean_spec, 2, 3)

        layout.addWidget(opts_group)

        run_row = QHBoxLayout()
        self.btn_start_build = QPushButton("빌드 실행")
        self.btn_start_build.clicked.connect(self._on_start_build)

        self.btn_cancel_build = QPushButton("빌드 취소")
        self.btn_cancel_build.setEnabled(False)
        self.btn_cancel_build.clicked.connect(self._on_cancel_build)

        self.btn_clear_log = QPushButton("로그 지우기")
        self.btn_clear_log.clicked.connect(self._on_clear_log)

        self.lbl_progress_detail = QLabel("대기 중")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        run_row.addWidget(self.btn_start_build)
        run_row.addWidget(self.btn_cancel_build)
        run_row.addWidget(self.btn_clear_log)
        run_row.addWidget(self.lbl_progress_detail, stretch=1)
        run_row.addWidget(self.progress_bar)
        layout.addLayout(run_row)

        log_group = QGroupBox("빌드 로그")
        log_vbox = QVBoxLayout(log_group)
        self.log_viewer = QPlainTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMaximumBlockCount(5000)

        log_font = QFont("Consolas", 9)
        log_font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_viewer.setFont(log_font)

        log_vbox.addWidget(self.log_viewer)
        layout.addWidget(log_group, stretch=1)

        return page

    def _init_build_target_window(self) -> None:
        self._build_target_window = BuildTargetConfigTab(
            project_root=self.project_root,
            config_path=self.config_path,
            parent=None,
            as_window=True,
        )
        self._build_target_window.hide()
        self._build_target_window.config_changed.connect(self._on_build_target_config_changed)

    def _on_build_target_config_changed(self, _payload: dict[str, Any]) -> None:
        self._sync_overrides_from_targets()
        self._refresh_target_checkboxes()

    def _on_open_build_target(self) -> None:
        if self._build_target_window is None:
            self._init_build_target_window()
        if self._build_target_window is None:
            return
        self._build_target_window.set_paths(self.project_root, self.config_path)
        self._build_target_window.load_from_json(self.config_path, show_error=False)
        self._build_target_window.show()
        self._build_target_window.raise_()
        self._build_target_window.activateWindow()

    def _dispose_build_target_window(self) -> None:
        win = self._build_target_window
        self._build_target_window = None
        if win is not None:
            try:
                win.force_close_window()
                win.deleteLater()
            except Exception:
                pass

    def _init_settings_window(self) -> None:
        self._settings_window = SettingsWindow(
            project_root=self.project_root,
            config_path=self.config_path,
            parent=self,
        )
        self._settings_window.hide()
        self._settings_window.settings_applied.connect(self._apply_settings_from_window)
        self._settings_window.accepted.connect(self._apply_settings_from_window)

    def _sync_settings_window_paths(self) -> None:
        if self._settings_window is None:
            return
        target_tab = getattr(self._settings_window, "build_target_config_tab", None)
        if target_tab is not None:
            target_tab.set_paths(self.project_root, self.config_path)
            target_tab.load_from_json(self.config_path, show_error=False)
        cfg_tab = getattr(self._settings_window, "config_tab", None)
        if cfg_tab is not None and hasattr(cfg_tab, "load_from_manager"):
            cfg_tab.load_from_manager(show_error=False)

    def _apply_settings_from_window(self) -> None:
        if self._settings_window is None:
            return
        target_tab = getattr(self._settings_window, "build_target_config_tab", None)
        if target_tab is not None:
            self.project_root = Path(target_tab.project_root).resolve()
            self.config_path = Path(target_tab.config_path).resolve()
            self.state_path = self.project_root / MANAGER_STATE_FILENAME

        self._update_project_header()
        self._sync_overrides_from_targets()
        self._refresh_target_checkboxes()
        save_manager_ui_state(self.state_path, self._collect_ui_state())
        if self.statusBar():
            self.statusBar().showMessage("세팅 윈도우 설정이 반영되었습니다.", 4000)

    def _on_open_settings(self) -> None:
        if self._settings_window is None:
            self._init_settings_window()
        if self._settings_window is None:
            return
        self._sync_settings_window_paths()
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _dispose_settings_window(self) -> None:
        win = self._settings_window
        self._settings_window = None
        if win is not None:
            try:
                win.hide()
                win.close()
                win.deleteLater()
            except Exception:
                pass

    def _update_project_header(self) -> None:
        if hasattr(self, "lbl_project_info"):
            self.lbl_project_info.setText(
                f"프로젝트: {self.project_root}  |  설정 JSON: {self.config_path}"
            )
        self.setWindowTitle(f"PrintShop Build Manager - {self.project_root.name}")

    def _sync_overrides_from_targets(self) -> None:
        dcfg = BuildTargets.get_dir_config(self.project_root)
        self._dir_overrides = {
            "work_dir_name": dcfg.work_dir_name,
            "dist_dir_name": dcfg.dist_dir_name,
            "release_dir_name": dcfg.release_dir_name,
            "install_dir_name": dcfg.install_dir_name,
        }
        self._app_overrides = {
            k: dict(v) for k, v in BuildTargets.get_app_overrides().items()
        }
        json_arg = str(self.config_path) if self.config_path.is_file() else None
        resolved_inst = InstallerBuildConfig.resolve(
            project_root=self.project_root,
            json_path=json_arg,
        )
        self._installer_overrides = {
            k: v
            for k, v in resolved_inst.to_dict().items()
            if k not in ("installer_only", "skip_installer")
        }

    def _resolve_target_version(self, key: str, spec: Any) -> str:
        """대상 앱의 버전 문자열(예: 1.2.3)을 조회합니다."""
        candidates: list[Path] = []
        ov = self._app_overrides.get(key, {}) if hasattr(self, "_app_overrides") else {}

        for raw in (
            ov.get("version_file"),
            getattr(spec, "version_file", None) if spec else None,
        ):
            if raw:
                p = Path(str(raw))
                candidates.append(p if p.is_absolute() else (self.project_root / p))

        rel_paths = (
            ov.get("version_rel_paths")
            or (getattr(spec, "version_rel_paths", None) if spec else None)
            or ()
        )
        for rel in rel_paths:
            if rel:
                p = Path(str(rel))
                candidates.append(p if p.is_absolute() else (self.project_root / p))

        dir_hints = (
            ov.get("dir_hints")
            or (getattr(spec, "dir_hints", None) if spec else None)
            or ()
        )
        for d in dir_hints:
            if d:
                candidates.append(self.project_root / "src" / str(d) / "version.txt")
                candidates.append(self.project_root / str(d) / "version.txt")

        for path in candidates:
            try:
                if path.is_file():
                    lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
                    if lines and lines[0].strip():
                        return lines[0].strip()
            except Exception:
                continue

        for attr in ("version", "default_version"):
            val = getattr(spec, attr, None) if spec else None
            if val:
                return str(val).strip()

        return ""

    def _format_target_label(self, key: str, spec: Any) -> str:
        ver = self._resolve_target_version(key, spec)
        return f"{key}({ver})" if ver else key

    def _layout_single_line_targets(self) -> None:
        """한 줄 폭 안에 All, 대상 체크박스들, 인스톨러가 모두 들어가도록 폭과 글꼴을 배분합니다."""
        if not hasattr(self, "targets_row_layout"):
            return

        container = self.targets_row_layout.parentWidget()
        total_w = container.width() if container and container.width() > 0 else self.width() - 40
        if total_w <= 0:
            return

        all_w = self.chk_all_targets.sizeHint().width()
        inst_w = self.chk_installer_target.sizeHint().width()
        fixed_gaps = self.targets_row_layout.spacing() * 2 + 12
        avail_for_targets = max(60, total_w - all_w - inst_w - fixed_gaps)

        target_list = list(self._target_checks.values())
        count = len(target_list)
        if count == 0:
            return

        inner_spacing = self.targets_row_layout.spacing() * max(0, count - 1)
        per_slot = max(24, (avail_for_targets - inner_spacing) // count)

        for chk in target_list:
            chk.setMaximumWidth(per_slot)
            chk.setMinimumWidth(0)
            chk._refit_font()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_single_line_targets()

    def _on_all_targets_clicked(self) -> None:
        if self.chk_all_targets.checkState() == Qt.CheckState.PartiallyChecked:
            self.chk_all_targets.blockSignals(True)
            self.chk_all_targets.setCheckState(Qt.CheckState.Checked)
            self.chk_all_targets.blockSignals(False)
            checked = True
        else:
            checked = self.chk_all_targets.checkState() == Qt.CheckState.Checked

        self._set_all_targets_checked(checked)

    def _on_installer_target_changed(self, _state: int) -> None:
        is_checked = self.chk_installer_target.isChecked()
        self.chk_skip_installer.blockSignals(True)
        self.chk_skip_installer.setChecked(not is_checked)
        self.chk_skip_installer.blockSignals(False)
        self._sync_all_target_checkbox_state()

    def _on_skip_installer_changed(self, _state: int) -> None:
        if hasattr(self, "chk_installer_target"):
            self.chk_installer_target.blockSignals(True)
            self.chk_installer_target.setChecked(not self.chk_skip_installer.isChecked())
            self.chk_installer_target.blockSignals(False)
        self._sync_all_target_checkbox_state()

    def _sync_all_target_checkbox_state(self) -> None:
        if not hasattr(self, "chk_all_targets"):
            return

        boxes: list[QCheckBox] = list(self._target_checks.values())
        if hasattr(self, "chk_installer_target"):
            boxes.append(self.chk_installer_target)

        total = len(boxes)
        self.chk_all_targets.blockSignals(True)
        if total == 0:
            self.chk_all_targets.setCheckState(Qt.CheckState.Unchecked)
        else:
            checked_count = sum(1 for chk in boxes if chk.isChecked())
            if checked_count == 0:
                self.chk_all_targets.setCheckState(Qt.CheckState.Unchecked)
            elif checked_count == total:
                self.chk_all_targets.setCheckState(Qt.CheckState.Checked)
            else:
                self.chk_all_targets.setCheckState(Qt.CheckState.PartiallyChecked)
        self.chk_all_targets.blockSignals(False)

    def _refresh_target_checkboxes(self) -> None:
        previously_checked = {
            key for key, chk in self._target_checks.items() if chk.isChecked()
        }
        has_previous = len(self._target_checks) > 0

        while self.targets_row_layout.count():
            item = self.targets_row_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._target_checks.clear()

        keys = BuildTargets.ordered_keys()
        for key in keys:
            spec = BuildTargets.get_spec(key)
            label = self._format_target_label(key, spec)
            chk = SingleLineFitCheckBox(label, base_pt=10.0, min_pt=7.5)
            if has_previous:
                chk.setChecked(key in previously_checked or not previously_checked)
            else:
                chk.setChecked(True)
            chk.stateChanged.connect(lambda _state: self._sync_all_target_checkbox_state())
            self._target_checks[key] = chk
            self.targets_row_layout.addWidget(chk, stretch=1)

        if hasattr(self, "chk_installer_target"):
            self.chk_installer_target.blockSignals(True)
            self.chk_installer_target.setChecked(not self.chk_skip_installer.isChecked())
            self.chk_installer_target.blockSignals(False)

        self._sync_all_target_checkbox_state()
        self._layout_single_line_targets()

    def _set_all_targets_checked(self, checked: bool) -> None:
        for chk in self._target_checks.values():
            chk.blockSignals(True)
            chk.setChecked(checked)
            chk.blockSignals(False)

        if hasattr(self, "chk_installer_target"):
            self.chk_installer_target.blockSignals(True)
            self.chk_installer_target.setChecked(checked)
            self.chk_installer_target.blockSignals(False)

        self.chk_skip_installer.blockSignals(True)
        self.chk_skip_installer.setChecked(not checked)
        self.chk_skip_installer.blockSignals(False)

        self._sync_all_target_checkbox_state()

    def _get_selected_targets(self) -> list[str]:
        selected = [key for key, chk in self._target_checks.items() if chk.isChecked()]
        return selected or BuildTargets.ordered_keys()

    def _get_selected_bump(self) -> str | None:
        data = self.combo_bump.currentData()
        return str(data) if data else None

    def _get_selected_mode(self) -> str:
        return self.combo_mode.currentText().strip() or "production"

    def _collect_ui_state(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "config_path": str(self.config_path),
            "selected_targets": [key for key, chk in self._target_checks.items() if chk.isChecked()],
            "mode": self._get_selected_mode(),
            "bump_unit": self._get_selected_bump(),
            "skip_installer": bool(self.chk_skip_installer.isChecked()),
            "installer_only": bool(self.chk_installer_only.isChecked()),
            "clean_build": bool(self.chk_clean_build.isChecked()),
            "clean_work_out": bool(self.chk_clean_work.isChecked()),
            "clean_dist_out": bool(self.chk_clean_dist.isChecked()),
            "clean_spec": bool(self.chk_clean_spec.isChecked()),
        }

    def _apply_ui_state(self, state: dict[str, Any]) -> None:
        proj_dir = state.get("project_root")
        if isinstance(proj_dir, str) and proj_dir.strip():
            self.project_root = Path(proj_dir).resolve()
            self.state_path = self.project_root / MANAGER_STATE_FILENAME

        cfg_file = state.get("config_path")
        if isinstance(cfg_file, str) and cfg_file.strip():
            self.config_path = Path(cfg_file).resolve()

        self._update_project_header()

        saved_targets = state.get("selected_targets")
        if isinstance(saved_targets, list) and self._target_checks:
            target_set = {str(t) for t in saved_targets}
            for key, chk in self._target_checks.items():
                chk.blockSignals(True)
                chk.setChecked(key in target_set)
                chk.blockSignals(False)

        mode = state.get("mode")
        if isinstance(mode, str):
            idx = self.combo_mode.findText(mode)
            if idx >= 0:
                self.combo_mode.setCurrentIndex(idx)

        bump = state.get("bump_unit")
        bump_idx = self.combo_bump.findData(bump)
        if bump_idx >= 0:
            self.combo_bump.setCurrentIndex(bump_idx)

        skip_inst = bool(state.get("skip_installer", False))
        self.chk_skip_installer.blockSignals(True)
        self.chk_skip_installer.setChecked(skip_inst)
        self.chk_skip_installer.blockSignals(False)

        if hasattr(self, "chk_installer_target"):
            self.chk_installer_target.blockSignals(True)
            self.chk_installer_target.setChecked(not skip_inst)
            self.chk_installer_target.blockSignals(False)

        self.chk_installer_only.setChecked(bool(state.get("installer_only", False)))
        self.chk_clean_build.setChecked(bool(state.get("clean_build", False)))
        self.chk_clean_work.setChecked(bool(state.get("clean_work_out", False)))
        self.chk_clean_dist.setChecked(bool(state.get("clean_dist_out", False)))
        self.chk_clean_spec.setChecked(bool(state.get("clean_spec", False)))

        self._sync_all_target_checkbox_state()
        self._layout_single_line_targets()

    def _load_saved_state(self) -> None:
        state = load_manager_ui_state(self.state_path)
        if state and isinstance(state.get("config_path"), str) and state["config_path"].strip():
            self.config_path = Path(state["config_path"]).resolve()

        if self.config_path.is_file():
            BuildTargets.configure(project_root=self.project_root, json_path=self.config_path)
        else:
            BuildTargets.configure(project_root=self.project_root)

        self._sync_overrides_from_targets()
        self._refresh_target_checkboxes()
        if state:
            self._apply_ui_state(state)
        self._update_project_header()

    def _save_all_state(self) -> None:
        save_manager_ui_state(self.state_path, self._collect_ui_state())

    def _resolve_app_bump_unit(self, target_key: str, default_bump: str | None) -> str | None:
        """개별 앱 설정(_app_overrides[target_key]['bump_unit'])에서 버전 증가 단위를 읽습니다."""
        ov = self._app_overrides.get(target_key, {}) if isinstance(self._app_overrides, dict) else {}
        if "bump_unit" in ov and ov["bump_unit"] is not None:
            s = str(ov["bump_unit"]).strip().lower()
            if not s or s in ("none", "null", "false", "0", "변경 없음"):
                return None
            if s in ("patch", "minor", "major"):
                return s
        return default_bump

    def _on_start_build(self) -> None:
        if self._active_build_keys:
            QMessageBox.information(self, "빌드 진행 중", "이미 빌드가 실행 중이거나 대기열에 있습니다.")
            return

        checked_apps = [key for key, chk in self._target_checks.items() if chk.isChecked()]
        app_keys = checked_apps or list(BuildTargets.ordered_keys())

        clean_build_opt = bool(self.chk_clean_build.isChecked())
        skip_installer_opt = bool(self.chk_skip_installer.isChecked())
        installer_only_opt = bool(self.chk_installer_only.isChecked())
        include_installer = bool(self.chk_installer_target.isChecked()) and (
            not skip_installer_opt or installer_only_opt
        )

        # 작업 순서: 1) clean(선택 시) -> 2) 개별 app -> 3) installer(대상 활성 시)
        job_specs: list[tuple[str, str]] = []
        if clean_build_opt:
            job_specs.append(("clean", "clean"))
        if not installer_only_opt:
            for key in app_keys:
                job_specs.append(("app", key))
        if include_installer:
            job_specs.append(("installer", "installer"))

        if not job_specs:
            QMessageBox.warning(self, "대상 오류", "실행할 빌드 작업이 없습니다.")
            return

        parsed_apps: dict[str, list[str]] = {}
        try:
            for kind, key in job_specs:
                if kind == "app":
                    parsed_apps[key] = parse_targets([key])
        except Exception as exc:
            QMessageBox.warning(self, "대상 오류", f"빌드 대상 확인 중 오류가 발생했습니다:\n{exc}")
            return

        cfg_file_str = str(self.config_path) if self.config_path.is_file() else None
        mode = self._get_selected_mode()
        fallback_bump = self._get_selected_bump()

        self.progress_bar.setValue(0)
        self.lbl_progress_detail.setText(f"빌드 대기열 등록 중... (총 {len(job_specs)}개 작업)")
        self.btn_start_build.setEnabled(False)
        self.btn_cancel_build.setEnabled(True)

        submitted_keys: list[str] = []
        base_ts = int(time.time() * 1000)

        try:
            for idx, (kind, job_key) in enumerate(job_specs):
                is_clean_job = kind == "clean"
                is_installer_job = kind == "installer"

                if is_clean_job:
                    job_targets: list[str] = []
                    job_bump: str | None = None
                elif is_installer_job:
                    job_targets = list(app_keys)
                    job_bump = None
                else:
                    job_targets = parsed_apps[job_key]
                    job_bump = self._resolve_app_bump_unit(job_key, fallback_bump)

                build_kwargs: dict[str, Any] = {
                    "project_root": str(self.project_root),
                    "job_type": kind,
                    "target_app": job_key if kind == "app" else None,
                    "targets": job_targets,
                    "bump_unit": job_bump,
                    "mode": mode,
                    "skip_installer": True if is_clean_job else (not is_installer_job),
                    "installer_only": is_installer_job,
                    "clean_build": is_clean_job,
                    "clean_work_out": False if is_clean_job else bool(self.chk_clean_work.isChecked()),
                    "clean_dist_out": False if is_clean_job else bool(self.chk_clean_dist.isChecked()),
                    "clean_spec": False if is_clean_job else bool(self.chk_clean_spec.isChecked()),
                    "progress_callback": None,
                    "timer": None,
                    "dir_config_json": cfg_file_str,
                    "dir_overrides": dict(self._dir_overrides),
                    "app_overrides": {k: dict(v) for k, v in self._app_overrides.items()},
                    "installer_targets": list(app_keys) if is_installer_job else None,
                    "installer_overrides": dict(self._installer_overrides),
                }

                task_key = f"BUILD_MGR_{base_ts}_{idx}_{job_key}"
                task_name = f"Build({mode}:{job_key})"

                logd(
                    f"[BuildManager] 작업 제출 (task_key={task_key}, job_type={kind}, "
                    f"target_app={build_kwargs['target_app']}, targets={job_targets}, "
                    f"bump_unit={job_bump})"
                )
                TaskManager().submit(
                    self._build_listener,
                    TaskPriority.NORMAL,
                    task_key,
                    task_name,
                    run_build_job,
                    build_kwargs,
                    cancel_on_close=True,
                )
                submitted_keys.append(task_key)
                self._active_build_keys.add(task_key)

            self._total_build_count = len(submitted_keys)

        except Exception as exc:
            for k in submitted_keys:
                TaskManager().cancel(k)
                self._active_build_keys.discard(k)
            self._total_build_count = 0
            loge(f"[BuildManager] 빌드 작업 제출 실패: {exc}")
            self.btn_start_build.setEnabled(True)
            self.btn_cancel_build.setEnabled(False)
            QMessageBox.warning(self, "등록 오류", str(exc))

    def _on_cancel_build(self) -> None:
        if not self._active_build_keys:
            return
        keys_to_cancel = list(self._active_build_keys)
        logd(f"[BuildManager] 빌드 취소 요청 (task_keys={keys_to_cancel})")
        self.btn_cancel_build.setEnabled(False)
        self.lbl_progress_detail.setText("빌드 취소 요청 중...")
        for k in keys_to_cancel:
            TaskManager().cancel(k)
        logd("[BuildManager] 빌드 취소 요청이 전달되었습니다. 현재 작업 종료를 기다리는 중입니다.", level="info")
        if self.statusBar():
            self.statusBar().showMessage("빌드 취소 요청 중...", 4000)

    def _on_build_finished(self, ok: bool, message: str) -> None:
        self._active_build_keys.clear()
        self._total_build_count = 0
        self.btn_start_build.setEnabled(True)
        self.btn_cancel_build.setEnabled(False)
        if ok:
            self.progress_bar.setValue(100)
        self.lbl_progress_detail.setText(message)
        if self.statusBar():
            self.statusBar().showMessage(message, 6000)

    def closeEvent(self, event: Any) -> None:
        if self._active_build_keys:
            reply = QMessageBox.question(
                self,
                "종료 확인",
                "현재 빌드가 진행 중입니다. 작업을 취소하고 종료하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        logd("[BuildManager] closeEvent 처리 시작")
        self._is_closing = True
        TaskManager().on_window_closing(
            self._build_listener,
            reason="빌드 매니저 종료로 빌드가 취소되었습니다.",
        )
        self._active_build_keys.clear()
        self._total_build_count = 0
        self._save_all_state()
        self._dispose_build_target_window()
        self._dispose_settings_window()
        self._teardown_logging()
        super().closeEvent(event)