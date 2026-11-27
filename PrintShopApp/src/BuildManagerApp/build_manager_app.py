from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import time
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
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

LOG_FILE_TAG: str = "BUILD_MGR"
set_file_tag(LOG_FILE_TAG)

from BuildManagerApp.build_app_tabs_group import (
    BuildAppTabGroupBox,
    INSTALLER_TAB_KEY,
)  # noqa: E402
from BuildManagerApp.build_manager_config import (  # noqa: E402
    BUILD_MANAGER_INI_NAME,
    BuildManagerIniStore,
    DEFAULT_BUILD_MODE,
    DEFAULT_INSTALL_DIR_NAME,
    DEFAULT_RELEASE_DIR_NAME,
)
from BuildManagerApp.build_target_config_tab import BuildTargetConfigTab  # noqa: E402
from BuildManagerApp.prev_version_resolver import (  # noqa: E402
    _build_snapshot_sig,
    _collect_zip_candidates,
    _get_app_folder_names,
    _resolve_bucket_dir_names,
    clear_prev_version_cache,
    resolve_prev_version_meta,
    resolve_zip_prev_version_meta,
)
from BuildManagerApp.settings_window import SettingsWindow  # noqa: E402
from build_script.build import (  # noqa: E402
    BuildApp,
    PrintShopBuildStepTimer,
    STEP_APP_TEST,
    STEP_BUILD,
    STEP_ENV,
    STEP_EOF_CRYPTO,
    STEP_INSTALLER,
    STEP_PUBKEY,
    STEP_RELEASE,
    STEP_TEST_SYNC,
    STEP_UI,
    STEP_VERSION,
    parse_targets,
)
from build_script.target_config import TargetConfig, get_build_target_helpers  # noqa: E402
from build_script.version_service import VersionService  # noqa: E402
from Common.prio_worker_queue import (  # noqa: E402
    CancelToken,
    TaskListenerBase,
    TaskManager,
    TaskPriority,
)

try:
    from Common.sound import play_task_completion_sound as _external_play_task_completion_sound
except Exception:  # noqa: E402
    _external_play_task_completion_sound = None

if sys.platform == "win32":
    import winsound

PLATFORM_WIN32: str = "win32"

MAIN_WINDOW_DEFAULT_WIDTH: int = 1120
MAIN_WINDOW_DEFAULT_HEIGHT: int = 740
MAIN_WINDOW_TITLE_PREFIX: str = "PrintShop Build Manager"

LOG_FONT_FAMILY: str = "Consolas"
LOG_FONT_SIZE: int = 9
LOG_MAX_BLOCK_COUNT: int = 5000
LOG_LEVEL_INFO: str = "info"

DEFAULT_VERSION_FALLBACK: str = "1.0.0"
DEFAULT_BUMP_UNIT: str = "patch"
DEFAULT_PROGRESS_MIN: int = 0
DEFAULT_PROGRESS_MAX: int = 100
DEFAULT_CLEAN_PROGRESS_START: int = 10
DEFAULT_ZIP_PROGRESS_STEP: int = 20
DEFAULT_MS_PER_SEC: int = 1000

DEFAULT_AUTO_INSTALL_LIBS: bool = True
DEFAULT_LIB_VENV_DIR_NAME: str = ".venv"
DEFAULT_LIB_CONFIRM: bool = False

STATUS_SUCCESS: str = "SUCCESS"
STATUS_ERROR: str = "ERROR"
STATUS_CANCELLED: str = "CANCELLED"

JOB_TYPE_CLEAN: str = "clean"
JOB_TYPE_STEP: str = "step"
JOB_TYPE_APP: str = "app"
JOB_TYPE_INSTALLER: str = "installer"
JOB_TYPE_PREV_ZIP_INSPECT: str = "prev_zip_inspect"

STEP_LIB_INSTALL: str = "step2_1_lib_install"

SHARED_PRE_STEPS: tuple[str, ...] = (
    STEP_UI,
    STEP_ENV,
    STEP_LIB_INSTALL,
    STEP_PUBKEY,
)

APP_PIPELINE_STEPS: tuple[str, ...] = (
    STEP_VERSION,
    STEP_BUILD,
    STEP_EOF_CRYPTO,
    STEP_TEST_SYNC,
    STEP_APP_TEST,
    STEP_RELEASE,
)

TASK_PREFIX_PREV_ZIP: str = "PREV_ZIP_"
TASK_PREFIX_BUILD_MGR: str = "BUILD_MGR_"

SRC_SUBDIR_NAME: str = "src"
VERSION_FILENAME: str = "version.txt"
VERSION_FILE_ENCODING: str = "utf-8-sig"

KEY_RUN_TEST: str = "run_test"
KEY_CLEAN_WORK: str = "clean_work"
KEY_CLEAN_DIST: str = "clean_dist"
KEY_CLEAN_SPEC: str = "clean_spec"
KEY_BUMP_UNIT: str = "bump_unit"
KEY_MODE: str = "mode"

MSG_READY: str = "준비됨"
MSG_WAITING: str = "대기 중"
MSG_CANCEL_REQUESTING: str = "빌드 취소 요청 중..."
MSG_CANCEL_DISPATCHED: str = (
    "[BuildManager] 빌드 취소 요청이 전달되었습니다. 현재 작업 종료를 기다리는 중입니다."
)
MSG_CLOSE_CANCEL_REASON: str = "빌드 매니저 종료로 빌드가 취소되었습니다."

STATUS_BAR_SHORT_MS: int = 4000
STATUS_BAR_LONG_MS: int = 6000
SEPARATOR_WIDTH_PX: int = 1
SEPARATOR_MIN_HEIGHT_PX: int = 16
ACTION_BTN_MIN_HEIGHT_PX: int = 24
BUILD_BTN_MIN_HEIGHT_PX: int = 26
DETAIL_LABEL_MIN_WIDTH_PX: int = 100
PROGRESS_BAR_MIN_WIDTH_PX: int = 240
PROGRESS_BAR_HEIGHT_PX: int = 22

MODE_CHOICES: tuple[str, ...] = (DEFAULT_BUILD_MODE, "development")
BUMP_CHOICES: tuple[tuple[str, str | None], ...] = (
    ("변경 없음 (none)", None),
    ("patch", "patch"),
    ("minor", "minor"),
    ("major", "major"),
)
VALID_BUMP_UNITS: frozenset[str] = frozenset({"patch", "minor", "major"})
NONE_BUMP_TOKENS: frozenset[str] = frozenset({"none", "null", "false", "0", "변경 없음"})

DEFAULT_INSTALLER_TARGET_ALIASES: tuple[str, ...] = (
    "PrintShopApp",
    "PrintShopUpdateService",
    "UpdateService",
)

APP_VERSION_PATHS: dict[str, list[str]] = {
    "PrintShopApp": [
        "src/PrintShopApp/version.txt",
    ],
    "PrintShopUpdateService": [
        "src/PrintShopUpdateService/version.txt",
        "src/PrintShopApp/version.txt",
    ],
    "PrintShopUpdateManager": [
        "src/PrintShopUpdateManager/version.txt",
        "src/PrintShopApp/version.txt",
    ],
    "PrintShopVersionViewer": [
        "src/PrintShopVersionViewer/version.txt",
        "src/PrintShopApp/version.txt",
    ],
    "PrintShopBuildManagerApp": [
        "src/BuildManagerApp/version.txt",
        "src/PrintShopApp/version.txt",
    ],
}

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
    "auto_install_libs",
    "lib_venv_root",
    "lib_venv_dir_name",
    "lib_confirm",
}


def _clamp_percent(val: Any) -> int:
    if isinstance(val, (int, float)):
        return max(DEFAULT_PROGRESS_MIN, min(DEFAULT_PROGRESS_MAX, int(val)))
    return DEFAULT_PROGRESS_MIN


def _calc_overall_percent(
    completed_steps: int,
    total_steps: int,
    step_percent: int,
) -> int:
    if total_steps <= 0:
        return DEFAULT_PROGRESS_MIN
    clamped_step = _clamp_percent(step_percent)
    overall = ((max(0, completed_steps) + (clamped_step / DEFAULT_PROGRESS_MAX)) / total_steps) * (
        DEFAULT_PROGRESS_MAX
    )
    return _clamp_percent(round(overall))


def _resolve_default_installer_targets() -> list[str]:
    ordered = list(TargetConfig.ordered_keys())
    resolved: list[str] = []
    for alias in DEFAULT_INSTALLER_TARGET_ALIASES:
        if alias in ordered and alias not in resolved:
            resolved.append(alias)
        else:
            for key in ordered:
                if alias.lower() in key.lower() and key not in resolved:
                    resolved.append(key)
                    break
    return resolved or ordered[:2]


def _get_low_task_priority() -> TaskPriority:
    return getattr(TaskPriority, "LOW", TaskPriority.NORMAL)


def _has_valid_prev_version(prev_meta: dict[str, Any] | None) -> bool:
    if not isinstance(prev_meta, dict) or not prev_meta:
        return False
    if prev_meta.get("error"):
        return False
    exe_path = str(prev_meta.get("_exe_path") or "").strip()
    source_label = str(prev_meta.get("_source_label") or "").strip().lower()
    items = prev_meta.get("items") if isinstance(prev_meta.get("items"), dict) else {}
    ver = str(items.get("version") or "").strip()
    has_artifact_source = source_label.startswith("zip(") or source_label.startswith("exe(")
    return bool(exe_path and has_artifact_source and ver and ver not in ("-", "없음"))


def play_task_completion_sound(
    status: str,
    wav_map: dict[str, str | Path] | None = None,
) -> None:
    """단일 작업 종료 시 비동기로 알림음을 재생합니다."""
    if _external_play_task_completion_sound is not None:
        try:
            _external_play_task_completion_sound(status, wav_map)
            return
        except Exception as exc:
            logd(f"[BuildManager] 외부 사운드 모듈 재생 실패 (status={status}): {exc}")

    if sys.platform != PLATFORM_WIN32:
        return

    try:
        custom_path = wav_map.get(status) if wav_map else None
        if custom_path:
            wav_file = Path(custom_path)
            if wav_file.is_file():
                winsound.PlaySound(
                    str(wav_file),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
                return

        beep_type = {
            STATUS_SUCCESS: winsound.MB_OK,
            STATUS_ERROR: winsound.MB_ICONHAND,
            STATUS_CANCELLED: winsound.MB_ICONEXCLAMATION,
        }.get(status, winsound.MB_OK)
        winsound.MessageBeep(beep_type)
    except Exception as exc:
        logd(f"[BuildManager] 작업 완료 사운드 재생 실패 (status={status}): {exc}")


def _create_v_separator(parent: QWidget | None = None) -> QFrame:
    """위젯 간 경계를 구분하기 위한 세로줄(QFrame.VLine)을 생성합니다."""
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setFixedWidth(SEPARATOR_WIDTH_PX)
    line.setMinimumHeight(SEPARATOR_MIN_HEIGHT_PX)
    line.setStyleSheet("color: #666666; background-color: #666666;")
    line.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    return line


def _apply_button_emphasis(
    btn: QPushButton,
    *,
    variant: str = "secondary",
    min_height: int = ACTION_BTN_MIN_HEIGHT_PX,
) -> None:
    """버튼 역할(primary / danger / secondary)에 따라 시각 강조 스타일을 적용합니다."""
    btn.setMinimumHeight(min_height)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)

    if variant == "primary":
        btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 3px 12px;
                border: 2px solid #4da3ff;
                border-radius: 4px;
                background-color: #1f4e78;
                color: #ffffff;
            }
            QPushButton:hover:enabled {
                background-color: #2b6cb0;
                border-color: #80bdff;
            }
            QPushButton:pressed:enabled {
                background-color: #153654;
            }
            QPushButton:disabled {
                font-weight: normal;
                border: 1px solid #555555;
                background-color: #262626;
                color: #888888;
            }
            """)
    elif variant == "danger":
        btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 3px 10px;
                border: 1px solid #d9534f;
                border-radius: 4px;
                background-color: #3a1d1d;
                color: #ffb3b3;
            }
            QPushButton:hover:enabled {
                background-color: #6e2624;
                border-color: #ff7b77;
                color: #ffffff;
            }
            QPushButton:pressed:enabled {
                background-color: #4a1817;
            }
            QPushButton:disabled {
                font-weight: normal;
                border: 1px solid #444444;
                background-color: transparent;
                color: #777777;
            }
            """)
    else:
        btn.setStyleSheet("""
            QPushButton {
                padding: 2px 9px;
                border: 1px solid #6b6b6b;
                border-radius: 4px;
                background-color: #252525;
                color: #f2f2f2;
            }
            QPushButton:hover:enabled {
                border-color: #b0b0b0;
                background-color: #363636;
            }
            QPushButton:pressed:enabled {
                background-color: #181818;
            }
            QPushButton:disabled {
                border: 1px solid #444444;
                background-color: transparent;
                color: #777777;
            }
            """)


def run_prev_zip_inspect_job(
    payload: dict[str, Any],
    progress_cb: Any = None,
    cancel_event: threading.Event | None = None,
    cancel_token: CancelToken | None = None,
) -> dict[str, Any]:
    """각 앱의 release ZIP을 메모리에서 해제해 이전버전 메타데이터를 추출합니다."""
    active_event = cancel_token.event if cancel_token is not None else cancel_event
    if active_event and active_event.is_set():
        raise InterruptedError("이전버전 ZIP 확인이 취소되었습니다.")

    app_key = str(payload["target_key"])
    if callable(progress_cb):
        progress_cb(DEFAULT_ZIP_PROGRESS_STEP, f"[{app_key}] release ZIP 메모리 확인 중...")

    meta = resolve_zip_prev_version_meta(
        project_root=payload["project_root"],
        target_key=app_key,
        config_path=payload.get("config_path"),
        app_override=payload.get("app_override"),
        app_version_paths=payload.get("app_version_paths"),
    )

    if active_event and active_event.is_set():
        raise InterruptedError("이전버전 ZIP 확인이 취소되었습니다.")

    if callable(progress_cb):
        progress_cb(DEFAULT_PROGRESS_MAX, f"[{app_key}] release ZIP 확인 완료")

    return {
        "ok": True,
        "job_type": JOB_TYPE_PREV_ZIP_INSPECT,
        "target_app": app_key,
        "prev_meta": meta,
        "_zip_sig": payload.get("_zip_sig"),
    }


def _run_single_build_step(
    app: BuildApp,
    step_key: str,
    py_exe: str,
    mode: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    """BuildApp 인스턴스에서 지정된 단일 빌드 단계만 실행하고 공유 상태를 갱신합니다."""
    target_versions: dict[str, str] = dict(state.get("target_versions") or {})
    previous_versions: dict[str, str] = dict(state.get("previous_versions") or {})

    if step_key == STEP_UI:
        app.step1_convert_ui_files(py_exe=py_exe)
    elif step_key == STEP_ENV:
        resolved_py, resolved_mode = app.step2_setup_environment_and_config()
        state["py_exe"] = resolved_py
        state["mode"] = resolved_mode
    elif step_key == STEP_LIB_INSTALL:
        install_fn = getattr(app, "install_python_libraries", None)
        if not callable(install_fn):
            raise AttributeError(
                "BuildApp에 install_python_libraries() 메서드가 정의되어 있지 않습니다."
            )
        install_fn()
    elif step_key == STEP_PUBKEY:
        app.step3_prepare_public_key_module()
    elif step_key == STEP_VERSION:
        t_vers, p_vers = app.step4_sync_version_and_resources()
        target_versions.update(t_vers)
        previous_versions.update(p_vers)
        state["target_versions"] = target_versions
        state["previous_versions"] = previous_versions
    elif step_key == STEP_BUILD:
        app.step5_build_targets(py_exe, target_versions)
    elif step_key == STEP_EOF_CRYPTO:
        app.step6_inject_eof_encryption(target_versions, mode)
    elif step_key == STEP_TEST_SYNC:
        app.step7_sync_to_test_folder()
    elif step_key == STEP_APP_TEST:
        app.step7_1_generate_and_run_app_tests(py_exe, target_versions)
    elif step_key == STEP_RELEASE:
        app.step8_create_release_artifacts(target_versions)
    elif step_key == STEP_INSTALLER:
        main_ver = app.version_service.get_main_app_version(target_versions)
        app.step9_create_windows_installer(py_exe, main_ver, is_final=True)
    else:
        raise ValueError(f"지원하지 않는 빌드 단계입니다: {step_key}")

    return {
        "target_versions": dict(state.get("target_versions") or {}),
        "previous_versions": dict(state.get("previous_versions") or {}),
        "py_exe": state.get("py_exe") or py_exe,
        "mode": state.get("mode") or mode,
    }


def run_build_job(
    build_kwargs: dict[str, Any],
    progress_cb: Any = None,
    cancel_event: threading.Event | None = None,
    cancel_token: CancelToken | None = None,
) -> dict[str, Any]:
    """
    PriorityWorkerThread에서 실행되는 작업 래퍼 함수.
    - job_type == "clean": TargetConfig 단일 기준 빌드 출력 디렉터리 정리 전용 작업 수행
    - job_type == "step": 지정된 단일 파이프라인 단계 실행
    - job_type == "app" / "installer": BuildApp 전체 파이프라인 실행
    """
    active_event = cancel_token.event if cancel_token is not None else cancel_event
    if active_event and active_event.is_set():
        raise InterruptedError("빌드 시작 전 취소되었습니다.")

    job_type = str(build_kwargs.get("job_type") or JOB_TYPE_APP)
    target_app = build_kwargs.get("target_app")
    project_root = str(build_kwargs.get("project_root") or PROJECT_ROOT)

    if job_type == JOB_TYPE_CLEAN:
        if callable(progress_cb):
            progress_cb(DEFAULT_CLEAN_PROGRESS_START, "빌드 출력 디렉터리 정리 중...")

        TargetConfig.configure(
            project_root=project_root,
            json_path=build_kwargs.get("dir_config_json"),
            code_overrides=build_kwargs.get("dir_overrides"),
            app_overrides=build_kwargs.get("app_overrides"),
        )
        if active_event and active_event.is_set():
            raise InterruptedError("디렉터리 정리 중 취소되었습니다.")

        removed_dirs = TargetConfig.clean_output_dirs(project_root, include_test=True)
        for removed in removed_dirs:
            logd(f"[CleanJob] 디렉터리 정리 완료: {removed}")

        if callable(progress_cb):
            progress_cb(DEFAULT_PROGRESS_MAX, "빌드 출력 디렉터리 정리 완료")

        return {
            "ok": True,
            "job_type": JOB_TYPE_CLEAN,
            "target_app": None,
            "removed_dirs": removed_dirs,
            "message": f"빌드 출력 디렉터리 정리 완료 ({len(removed_dirs)}개 폴더)",
        }

    timer = PrintShopBuildStepTimer()
    kwargs = {k: v for k, v in build_kwargs.items() if k in BUILD_APP_ACCEPTED_KEYS}
    kwargs["timer"] = timer

    step_key = str(build_kwargs.get("step_key") or "")
    if job_type == JOB_TYPE_STEP and step_key != STEP_VERSION:
        kwargs["bump_unit"] = None
        kwargs["bump_units"] = {}

    def _on_build_progress(payload: dict[str, Any]) -> None:
        if active_event and active_event.is_set():
            raise InterruptedError("빌드 진행 중 취소되었습니다.")
        if callable(progress_cb):
            safe_pct = _clamp_percent(payload.get("percent"))
            detail = str(payload.get("detail") or payload.get("step_key") or "빌드 진행 중...")
            progress_cb(safe_pct, detail)

    kwargs["progress_callback"] = _on_build_progress

    logd(
        f"[BuildJob] BuildApp 실행 준비 (job_type={job_type}, step_key={step_key or '-'}, "
        f"target_app={target_app}, targets={kwargs.get('targets')}, "
        f"bump_unit={kwargs.get('bump_unit')}, installer_only={kwargs.get('installer_only')}, "
        f"mode={kwargs.get('mode')}, auto_install_libs={kwargs.get('auto_install_libs')})"
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

    if job_type == JOB_TYPE_STEP:
        step_state = dict(build_kwargs.get("pipeline_state") or {})
        py_exe = str(step_state.get("py_exe") or sys.executable)
        step_mode = str(step_state.get("mode") or kwargs.get("mode") or "")
        updated_state = _run_single_build_step(app, step_key, py_exe, step_mode, step_state)

        if active_event and active_event.is_set():
            raise InterruptedError("사용자에 의해 단계가 취소되었습니다.")

        label = f"{target_app}:{step_key}" if target_app else step_key
        return {
            "ok": True,
            "job_type": JOB_TYPE_STEP,
            "step_key": step_key,
            "target_app": target_app,
            "pipeline_state": updated_state,
            "message": f"[{label}] 단계가 완료되었습니다.",
            "timer": timer,
        }

    ok = bool(app.run())
    if active_event and active_event.is_set():
        raise InterruptedError("사용자에 의해 빌드가 취소되었습니다.")

    if not ok:
        raise RuntimeError(
            f"빌드 파이프라인이 실패했습니다. (job_type={job_type}, target_app={target_app})"
        )

    label = (
        str(target_app)
        if target_app
        else (INSTALLER_TAB_KEY if job_type == JOB_TYPE_INSTALLER else job_type)
    )
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

    def on_task_started(self, task_key: str, task_name: str, message: str = "") -> None:
        if task_key not in self._window._active_build_keys:
            return
        app_key = self._window._task_to_app_key.get(task_key)
        if app_key and hasattr(self._window, "build_app_tabs_group"):
            self._window.build_app_tabs_group.notify_target_started(
                app_key, detail=message or "빌드 시작"
            )

    def on_task_progress(self, task_key: str, task_name: str, percent: int, message: str) -> None:
        if task_key not in self._window._active_build_keys:
            return
        safe_pct = _clamp_percent(percent)
        total_steps = self._window._total_build_count
        if total_steps > 0:
            overall_pct = _calc_overall_percent(
                self._window._completed_step_count,
                total_steps,
                safe_pct,
            )
            step_no = min(total_steps, self._window._completed_step_count + 1)
            self._window.progress_bar.setValue(overall_pct)
            self._window.lbl_progress_detail.setText(
                f"[{step_no}/{total_steps}] [{task_name}] {message}"
            )
        else:
            self._window.progress_bar.setValue(safe_pct)
            self._window.lbl_progress_detail.setText(f"[{task_name}] {message}")

        app_key = self._window._task_to_app_key.get(task_key)
        if app_key and hasattr(self._window, "build_app_tabs_group"):
            self._window.build_app_tabs_group.notify_target_progress(app_key, safe_pct, message)

    def on_task_finished(self, task_key: str, task_name: str, status: str, data: Any) -> None:
        deferred_app_key = self._window._deferred_zip_tasks.pop(task_key, None)
        if deferred_app_key is not None:
            if status == STATUS_SUCCESS and isinstance(data, dict):
                zip_sig = data.get("_zip_sig")
                if isinstance(zip_sig, tuple):
                    self._window._completed_zip_sigs[deferred_app_key] = zip_sig
                prev_meta = data.get("prev_meta")
                if isinstance(prev_meta, dict) and hasattr(self._window, "build_app_tabs_group"):
                    self._window._apply_deferred_prev_meta(deferred_app_key, prev_meta)
            return

        timing = TaskManager().get_timing(task_key)
        if timing is not None:
            logd(f"[BuildManager] 작업 시점 요약 ({task_name}) ->" f" {timing.format_summary()}")

        was_tracked = task_key in self._window._active_build_keys
        self._window._active_build_keys.discard(task_key)
        app_key = self._window._task_to_app_key.pop(task_key, None)

        ok = status == STATUS_SUCCESS
        if isinstance(data, dict):
            msg = str(data.get("message") or status)
            updated_state = data.get("pipeline_state")
            if isinstance(updated_state, dict):
                self._window._pipeline_state.update(updated_state)
        else:
            msg = str(data) if data is not None else status

        if timing is not None and timing.run_sec is not None:
            msg = f"{msg} (실행 {timing.run_sec:.2f}s / 총 {timing.total_sec:.2f}s)"

        if status == STATUS_CANCELLED:
            logd(f"[BuildManager] [{task_name}] {msg}", level=LOG_LEVEL_INFO)
        elif status == STATUS_ERROR:
            loge(f"[BuildManager] [{task_name}] {msg}")

        if not was_tracked:
            return

        if ok:
            self._window._completed_step_count += 1

        has_more_steps = (
            ok
            and not self._window._cancel_requested
            and not self._window._is_closing
            and bool(self._window._pending_step_specs)
        )

        if app_key and hasattr(self._window, "build_app_tabs_group"):
            is_last_for_card = not has_more_steps or (
                self._window._pending_step_specs[0].get("ui_key") != app_key
            )
            if not ok or is_last_for_card:
                self._window.build_app_tabs_group.notify_target_finished(
                    app_key,
                    success=ok,
                    percent=(DEFAULT_PROGRESS_MAX if ok else self._window.progress_bar.value()),
                )

        if has_more_steps:
            total = max(1, self._window._total_build_count)
            done = self._window._completed_step_count
            overall_pct = _calc_overall_percent(done, total, 0)
            self._window.progress_bar.setValue(overall_pct)
            self._window.lbl_progress_detail.setText(
                f"[{task_name}] {msg} ({done}/{total} 단계 완료, 다음 단계 준비 중)"
            )
            if self._window.statusBar():
                self._window.statusBar().showMessage(
                    f"빌드 진행 중 ({done}/{total} 단계 완료)",
                    STATUS_BAR_SHORT_MS,
                )
            self._window._submit_next_build_step()
            return

        self._window._pending_step_specs.clear()
        if not ok:
            self._window._rollback_versions_if_needed()

        play_task_completion_sound(status, getattr(self._window, "_sound_wav_map", None))
        self._window._total_build_count = 0
        self._window._completed_step_count = 0
        self._window._on_build_finished(ok, msg)


def _normalize_project_root(raw_root: str | Path) -> Path:
    resolved = Path(raw_root).resolve()
    if resolved.name.lower() == SRC_SUBDIR_NAME and (
        (resolved / "Common").is_dir()
        or (resolved / "build_script").is_dir()
        or (resolved.parent / SRC_SUBDIR_NAME).is_dir()
    ):
        return resolved.parent
    return resolved


class BuildManagerWindow(QMainWindow):
    """PrintShopApp 빌드 관리 메인 윈도우."""

    def __init__(
        self,
        project_root: str | Path = PROJECT_ROOT,
        config_path: str | Path | None = None,
        app_version_paths: dict[str, list[str | Path]] | None = None,
        auto_install_libs: bool = DEFAULT_AUTO_INSTALL_LIBS,
        lib_venv_root: str | Path | None = None,
        lib_venv_dir_name: str = DEFAULT_LIB_VENV_DIR_NAME,
        lib_confirm: bool = DEFAULT_LIB_CONFIRM,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_root = _normalize_project_root(project_root)
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else (self.project_root / BUILD_MANAGER_INI_NAME)
        )
        self.ini_store = BuildManagerIniStore(self.config_path.parent)
        self.app_version_paths: dict[str, list[str | Path]] = {
            k: list(v) for k, v in (app_version_paths or APP_VERSION_PATHS).items()
        }

        self.auto_install_libs: bool = bool(auto_install_libs)
        self.lib_venv_root: str | None = (
            str(Path(lib_venv_root).resolve()) if lib_venv_root is not None else None
        )
        self.lib_venv_dir_name: str = (
            str(lib_venv_dir_name or DEFAULT_LIB_VENV_DIR_NAME).strip() or DEFAULT_LIB_VENV_DIR_NAME
        )
        self.lib_confirm: bool = bool(lib_confirm)

        self._target_checks: dict[str, QCheckBox] = {}
        self._dir_overrides: dict[str, Any] = {}
        self._installer_overrides: dict[str, Any] = {}
        self._installer_user_configured: bool = False
        self._auto_scroll_log: bool = True
        self._active_build_keys: set[str] = set()
        self._task_to_app_key: dict[str, str] = {}
        self._deferred_zip_tasks: dict[str, str] = {}
        self._completed_zip_sigs: dict[str, tuple[tuple[str, int, int], ...]] = {}
        self._pending_step_specs: list[dict[str, Any]] = []
        self._pipeline_state: dict[str, Any] = {}
        self._cancel_requested: bool = False
        self._total_build_count: int = 0
        self._completed_step_count: int = 0
        self._build_listener = BuildTaskListener(self)
        self._log_handler: WindowLogColorHandlerBase | None = None
        self._settings_window: SettingsWindow | None = None
        self._build_target_window: BuildTargetConfigTab | None = None
        self._sound_wav_map: dict[str, str | Path] = {}
        self._is_closing: bool = False

        self.destroyed.connect(self._on_destroyed_cleanup)

        self.setWindowTitle(f"{MAIN_WINDOW_TITLE_PREFIX} - {self.project_root.name}")
        self.resize(MAIN_WINDOW_DEFAULT_WIDTH, MAIN_WINDOW_DEFAULT_HEIGHT)

        self._init_ui()
        self._setup_logging()
        self._init_build_target_window()
        self._load_saved_state()
        self._init_settings_window()
        self._ensure_default_installer_targets()
        self._sync_build_app_tabs()

    def _get_app_overrides(self) -> dict[str, dict[str, Any]]:
        """_app_overrides의 단일 원본인 BuildTargetConfigTab 또는 TargetConfig에서 조회합니다."""
        win = getattr(self, "_build_target_window", None)
        if win is not None and isinstance(getattr(win, "_app_overrides", None), dict):
            return win._app_overrides
        return TargetConfig.get_app_overrides()

    def _on_destroyed_cleanup(self, *_args: Any) -> None:
        TaskManager().on_window_closing(self._build_listener)
        self._dispose_build_target_window()
        self._dispose_settings_window()
        self._teardown_logging()

    def _scroll_log_to_bottom(self) -> None:
        if not getattr(self, "_auto_scroll_log", True):
            return
        if not hasattr(self, "log_viewer"):
            return
        cursor = self.log_viewer.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_viewer.setTextCursor(cursor)
        self.log_viewer.ensureCursorVisible()

    def _apply_auto_scroll_policy(self, enabled: bool) -> None:
        self._auto_scroll_log = bool(enabled)
        if self._auto_scroll_log:
            self._scroll_log_to_bottom()

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
            self.statusBar().showMessage(MSG_READY)

    def _create_build_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)
        self.lbl_project_info = QLabel(f"프로젝트: {self.project_root}")
        self.lbl_project_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top_bar.addWidget(self.lbl_project_info, stretch=1)

        self.btn_open_build_target = QPushButton("BuildTarget")
        _apply_button_emphasis(
            self.btn_open_build_target,
            variant="secondary",
            min_height=ACTION_BTN_MIN_HEIGHT_PX,
        )
        self.btn_open_build_target.clicked.connect(self._on_open_build_target)
        top_bar.addWidget(self.btn_open_build_target)

        top_bar.addWidget(_create_v_separator(page))

        self.btn_open_settings = QPushButton("설정")
        _apply_button_emphasis(
            self.btn_open_settings,
            variant="secondary",
            min_height=ACTION_BTN_MIN_HEIGHT_PX,
        )
        self.btn_open_settings.clicked.connect(self._on_open_settings)
        top_bar.addWidget(self.btn_open_settings)
        layout.addLayout(top_bar)

        self.targets_group = QGroupBox("빌드 대상 선택")
        targets_group_layout = QHBoxLayout(self.targets_group)
        targets_group_layout.setContentsMargins(8, 4, 8, 4)
        targets_group_layout.setSpacing(6)

        self.chk_all_targets = QCheckBox("All")
        self.chk_all_targets.setToolTip("전체 빌드 대상 선택 / 해제")
        self.chk_all_targets.setTristate(True)
        self.chk_all_targets.clicked.connect(self._on_all_targets_clicked)
        targets_group_layout.addWidget(self.chk_all_targets, stretch=0)

        targets_group_layout.addWidget(_create_v_separator(self.targets_group))

        self.targets_row_layout = QHBoxLayout()
        self.targets_row_layout.setContentsMargins(0, 0, 0, 0)
        self.targets_row_layout.setSpacing(6)
        targets_group_layout.addLayout(self.targets_row_layout, stretch=1)

        targets_group_layout.addWidget(_create_v_separator(self.targets_group))

        self.chk_installer_target = QCheckBox("인스톨러")
        self.chk_installer_target.setToolTip("인스톨러 빌드 포함 여부")
        self.chk_installer_target.stateChanged.connect(self._on_installer_target_changed)
        targets_group_layout.addWidget(self.chk_installer_target, stretch=0)

        layout.addWidget(self.targets_group)

        opts_row = QHBoxLayout()
        opts_row.setContentsMargins(0, 0, 0, 0)
        opts_row.setSpacing(6)

        group1 = QGroupBox("배포 / 버전")
        g1_layout = QHBoxLayout(group1)
        g1_layout.setContentsMargins(8, 4, 8, 4)
        g1_layout.setSpacing(5)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(list(MODE_CHOICES))
        self.combo_mode.setToolTip(f"배포 모드 ({' / '.join(MODE_CHOICES)})")
        self.combo_mode.currentIndexChanged.connect(self._on_main_mode_changed)

        self.combo_bump = QComboBox()
        for label_text, unit_val in BUMP_CHOICES:
            self.combo_bump.addItem(label_text, userData=unit_val)
        self.combo_bump.setToolTip("버전 증가 단위 (none / patch / minor / major)")
        self.combo_bump.currentIndexChanged.connect(self._on_main_bump_changed)

        g1_layout.addWidget(QLabel("배포 모드"))
        g1_layout.addWidget(self.combo_mode)
        g1_layout.addWidget(_create_v_separator(group1))
        g1_layout.addWidget(QLabel("버전 증가"))
        g1_layout.addWidget(self.combo_bump)

        group2 = QGroupBox("인스톨러 옵션")
        g2_layout = QHBoxLayout(group2)
        g2_layout.setContentsMargins(8, 4, 8, 4)
        g2_layout.setSpacing(6)

        self.chk_skip_installer = QCheckBox("skip")
        self.chk_skip_installer.setToolTip("인스톨러 건너뜀 (--skip-installer)")
        self.chk_skip_installer.stateChanged.connect(self._on_skip_installer_changed)

        self.chk_installer_only = QCheckBox("create")
        self.chk_installer_only.setToolTip("인스톨러만 생성 (--installer-only)")

        g2_layout.addWidget(self.chk_skip_installer)
        g2_layout.addWidget(_create_v_separator(group2))
        g2_layout.addWidget(self.chk_installer_only)

        group3 = QGroupBox("정리 옵션")
        g3_layout = QHBoxLayout(group3)
        g3_layout.setContentsMargins(8, 4, 8, 4)
        g3_layout.setSpacing(6)

        self.chk_clean_build = QCheckBox("all")
        self.chk_clean_build.setToolTip("전체 빌드 폴더 정리 (--clean)")

        self.chk_clean_work = QCheckBox("work")
        self.chk_clean_work.setToolTip("work 폴더 정리 (--clean-work)")

        self.chk_clean_dist = QCheckBox("dist")
        self.chk_clean_dist.setToolTip("dist 폴더 정리 (--clean-dist)")

        self.chk_clean_spec = QCheckBox("spec")
        self.chk_clean_spec.setToolTip(".spec 파일 정리 (--clean-spec)")

        self._bind_clean_option_signals()

        g3_layout.addWidget(self.chk_clean_build)
        g3_layout.addWidget(_create_v_separator(group3))
        g3_layout.addWidget(self.chk_clean_work)
        g3_layout.addWidget(_create_v_separator(group3))
        g3_layout.addWidget(self.chk_clean_dist)
        g3_layout.addWidget(_create_v_separator(group3))
        g3_layout.addWidget(self.chk_clean_spec)

        opts_row.addWidget(group1, stretch=0)
        opts_row.addWidget(group2, stretch=0)
        opts_row.addWidget(group3, stretch=1)
        layout.addLayout(opts_row)

        progress_group = QGroupBox("빌드 실행 및 진행 상태")
        run_row = QHBoxLayout(progress_group)
        run_row.setContentsMargins(8, 4, 8, 4)
        run_row.setSpacing(6)

        self.btn_start_build = QPushButton("빌드 실행")
        _apply_button_emphasis(
            self.btn_start_build,
            variant="primary",
            min_height=BUILD_BTN_MIN_HEIGHT_PX,
        )
        self.btn_start_build.clicked.connect(self._on_start_build)

        self.btn_cancel_build = QPushButton("빌드 취소")
        _apply_button_emphasis(
            self.btn_cancel_build,
            variant="danger",
            min_height=BUILD_BTN_MIN_HEIGHT_PX,
        )
        self.btn_cancel_build.setEnabled(False)
        self.btn_cancel_build.clicked.connect(self._on_cancel_build)

        self.btn_clear_log = QPushButton("로그 지우기")
        _apply_button_emphasis(
            self.btn_clear_log,
            variant="secondary",
            min_height=BUILD_BTN_MIN_HEIGHT_PX,
        )
        self.btn_clear_log.clicked.connect(self._on_clear_log)

        self.lbl_progress_detail = QLabel(MSG_WAITING)
        self.lbl_progress_detail.setMinimumWidth(DETAIL_LABEL_MIN_WIDTH_PX)
        self.lbl_progress_detail.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(DEFAULT_PROGRESS_MIN, DEFAULT_PROGRESS_MAX)
        self.progress_bar.setValue(DEFAULT_PROGRESS_MIN)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setMinimumWidth(PROGRESS_BAR_MIN_WIDTH_PX)
        self.progress_bar.setMinimumHeight(PROGRESS_BAR_HEIGHT_PX)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        run_row.addWidget(self.btn_start_build)
        run_row.addWidget(self.btn_cancel_build)
        run_row.addWidget(self.btn_clear_log)
        run_row.addWidget(_create_v_separator(progress_group))
        run_row.addWidget(self.lbl_progress_detail, stretch=1)
        run_row.addWidget(_create_v_separator(progress_group))
        run_row.addWidget(self.progress_bar, stretch=2)
        layout.addWidget(progress_group)

        self.build_app_tabs_group = BuildAppTabGroupBox("BuildApp")
        self.build_app_tabs_group.target_selection_changed.connect(
            self._on_tab_card_selection_changed
        )

        self.build_app_tabs_group.target_bump_changed.connect(self._on_tab_card_bump_changed)

        self.build_app_tabs_group.prev_log_emitted.connect(lambda _key, msg: logd(msg))

        layout.addWidget(self.build_app_tabs_group, stretch=0)

        log_group = QGroupBox("빌드 로그")
        log_vbox = QVBoxLayout(log_group)
        log_vbox.setContentsMargins(6, 6, 6, 6)
        log_vbox.setSpacing(4)
        self.log_viewer = QPlainTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMaximumBlockCount(LOG_MAX_BLOCK_COUNT)
        self.log_viewer.textChanged.connect(self._scroll_log_to_bottom)

        log_font = QFont(LOG_FONT_FAMILY, LOG_FONT_SIZE)
        log_font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_viewer.setFont(log_font)

        log_vbox.addWidget(self.log_viewer)
        layout.addWidget(log_group, stretch=1)

        return page

    def _should_show_installer_tab(self) -> bool:
        if not hasattr(self, "chk_installer_target"):
            return False
        return bool(self.chk_installer_target.isChecked()) and not bool(
            self.chk_skip_installer.isChecked()
        )

    def _resolve_release_app_dir(self, key: str, spec: Any, ov: dict[str, Any]) -> Path:
        _, release_dir_name = _resolve_bucket_dir_names(self.project_root, ov, self.config_path)
        release_root = (self.project_root / release_dir_name).resolve()
        folder_names = _get_app_folder_names(key, spec, ov)

        for folder_name in folder_names:
            candidate = (release_root / folder_name).resolve()
            if candidate.is_dir():
                return candidate

        if folder_names:
            return (release_root / folder_names[0]).resolve()
        return release_root

    def _build_target_tab_meta(self, key: str) -> dict[str, Any]:
        if key == INSTALLER_TAB_KEY:
            inst_targets = self._ensure_default_installer_targets()
            targets_text = ", ".join(inst_targets) if inst_targets else "기본값"
            install_dir = self.project_root / str(
                self._dir_overrides.get("install_dir_name") or DEFAULT_INSTALL_DIR_NAME
            )
            return {
                "target_name": INSTALLER_TAB_KEY,
                "label_text": f"{INSTALLER_TAB_KEY} ({targets_text})",
                "display_name": INSTALLER_TAB_KEY,
                "location_path": (install_dir if install_dir.exists() else self.project_root),
                "bump_checked": False,
                "prev_meta": None,
            }

        spec = TargetConfig.get_spec(key)
        app_overrides = self._get_app_overrides()
        ov = app_overrides.get(key, {}) if isinstance(app_overrides, dict) else {}
        display_name = str(ov.get("display_name") or getattr(spec, "display_name", None) or key)

        loc_path: Path | None = None
        dir_hints = (
            ov.get("dir_hints") or (getattr(spec, "dir_hints", None) if spec else None) or ()
        )
        for d in dir_hints:
            cand = self.project_root / SRC_SUBDIR_NAME / str(d)
            if cand.exists():
                loc_path = cand
                break

        bump_unit = self._resolve_app_bump_unit(key, self._get_selected_bump())
        prev_meta = resolve_prev_version_meta(
            project_root=self.project_root,
            target_key=key,
            config_path=self.config_path,
            app_override=ov,
            app_version_paths=self.app_version_paths,
            defer_zip=True,
        )
        has_prev = _has_valid_prev_version(prev_meta)
        base_label = self._format_target_label(key, spec)
        label_text = base_label if has_prev else key

        release_app_dir = self._resolve_release_app_dir(key, spec, ov)
        resolved_loc_path = release_app_dir if not has_prev else (loc_path or release_app_dir)

        return {
            "target_name": key,
            "label_text": label_text,
            "display_name": display_name,
            "location_path": resolved_loc_path,
            "bump_checked": bool(bump_unit),
            "prev_meta": prev_meta,
        }

    def _apply_deferred_prev_meta(self, app_key: str, prev_meta: dict[str, Any]) -> None:
        if not hasattr(self, "build_app_tabs_group"):
            return
        cards_by_key = getattr(self.build_app_tabs_group, "_cards_by_key", None)
        if isinstance(cards_by_key, dict):
            card = cards_by_key.get(app_key)
            if card is not None and hasattr(card, "set_prev_meta"):
                card.set_prev_meta(prev_meta)
                if hasattr(card, "btn_open_prev_dir"):
                    spec = TargetConfig.get_spec(app_key)
                    app_overrides = self._get_app_overrides()
                    ov = app_overrides.get(app_key, {}) if isinstance(app_overrides, dict) else {}
                    has_prev = _has_valid_prev_version(prev_meta)
                    base_label = self._format_target_label(app_key, spec)
                    card.btn_open_prev_dir.setText(base_label if has_prev else app_key)
                    if not has_prev:
                        release_app_dir = self._resolve_release_app_dir(app_key, spec, ov)
                        card.set_location_tooltip(str(release_app_dir))
                        card.setProperty("_location_path", str(release_app_dir))

    def _get_app_zip_sig(self, key: str) -> tuple[tuple[str, int, int], ...]:
        """해당 앱의 release .zip 파일 목록과 (경로, 크기, 수정시각_ns) 스냅샷을 반환합니다."""
        app_overrides = self._get_app_overrides()
        ov = app_overrides.get(key, {}) if isinstance(app_overrides, dict) else {}
        spec = TargetConfig.get_spec(key)
        try:
            dcfg = TargetConfig.get_dir_config(self.project_root)
            release_dir_name = str(
                ov.get("release_dir_name") or dcfg.release_dir_name or DEFAULT_RELEASE_DIR_NAME
            )
        except Exception:
            release_dir_name = DEFAULT_RELEASE_DIR_NAME

        zip_paths = _collect_zip_candidates(
            root=self.project_root,
            target_key=key,
            spec=spec,
            ov=ov,
            release_dir_name=release_dir_name,
        )
        if not zip_paths:
            return ()
        return _build_snapshot_sig(zip_paths)

    def _schedule_deferred_zip_inspections(self, app_keys: list[str]) -> None:
        """ZIP 후보가 있고 이전과 변경된 앱만 TaskQueue에 등록합니다."""
        low_prio = _get_low_task_priority()
        active_apps = set(self._deferred_zip_tasks.values())
        app_overrides = self._get_app_overrides()

        for key in app_keys:
            if key in active_apps:
                continue

            zip_sig = self._get_app_zip_sig(key)
            if not zip_sig:
                continue

            if self._completed_zip_sigs.get(key) == zip_sig:
                continue

            task_key = f"{TASK_PREFIX_PREV_ZIP}{key}"
            ov = app_overrides.get(key, {}) if isinstance(app_overrides, dict) else {}
            payload = {
                "project_root": str(self.project_root),
                "target_key": key,
                "config_path": (str(self.config_path) if self.config_path.is_file() else None),
                "app_override": dict(ov),
                "app_version_paths": self.app_version_paths,
                "_zip_sig": zip_sig,
            }
            self._deferred_zip_tasks[task_key] = key
            active_apps.add(key)
            TaskManager().submit(
                self._build_listener,
                low_prio,
                task_key,
                f"PrevZip({key})",
                run_prev_zip_inspect_job,
                payload,
                cancel_on_close=True,
            )

    def _sync_build_app_tabs(self) -> None:
        if not hasattr(self, "build_app_tabs_group"):
            return
        selected_keys = [
            key
            for key in TargetConfig.ordered_keys()
            if key in self._target_checks and self._target_checks[key].isChecked()
        ]
        include_inst = self._should_show_installer_tab()
        if include_inst:
            self._ensure_default_installer_targets()

        self.build_app_tabs_group.sync_selected_targets(
            selected_keys,
            meta_provider=self._build_target_tab_meta,
            include_installer_tab=include_inst,
        )
        self._schedule_deferred_zip_inspections(selected_keys)

    def _on_tab_card_selection_changed(self, target_key: str, checked: bool) -> None:
        if target_key == INSTALLER_TAB_KEY:
            if (
                hasattr(self, "chk_installer_target")
                and self.chk_installer_target.isChecked() != checked
            ):
                self.chk_installer_target.setChecked(checked)
            return
        chk = self._target_checks.get(target_key)
        if chk is not None and chk.isChecked() != checked:
            chk.setChecked(checked)

    def _on_tab_card_bump_changed(self, target_key: str, checked: bool) -> None:
        default_unit = self._get_selected_bump() or DEFAULT_BUMP_UNIT
        new_unit = default_unit if checked else None
        app_ov = self._get_app_overrides()
        bucket = dict(app_ov.get(target_key, {}))
        if new_unit is None:
            bucket.pop(KEY_BUMP_UNIT, None)
        else:
            bucket[KEY_BUMP_UNIT] = new_unit
        app_ov[target_key] = bucket
        self._save_build_config_ini_now()

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
        self._sync_installer_overrides_from_target_window()
        self._sync_overrides_from_targets()
        self._ensure_default_installer_targets()
        self._refresh_target_checkboxes()

    def _on_open_build_target(self) -> None:
        if self._build_target_window is None:
            self._init_build_target_window()
        if self._build_target_window is None:
            return
        self._build_target_window.set_paths(self.project_root, self.config_path)
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
            ini_store=self.ini_store,
            parent=self,
        )
        self._settings_window.hide()
        self._settings_window.settings_applied.connect(self._apply_settings_from_window)
        self._settings_window.accepted.connect(self._apply_settings_from_window)

    def _sync_settings_window_paths(self) -> None:
        if self._settings_window is None:
            return
        self._settings_window.project_root = self.project_root
        self._settings_window.config_path = self.config_path
        self._settings_window.ini_store = self.ini_store
        if hasattr(self._settings_window, "general_tab"):
            self._settings_window.general_tab.set_paths(self.project_root, self.config_path)
            sections = self.ini_store.load_target_sections()
            self._settings_window.general_tab.set_dir_values(sections["dirs"])
        if hasattr(self._settings_window, "config_tab"):
            self._settings_window.config_tab.set_config_manager(self.ini_store.manager_cfg)

    def _apply_settings_from_window(self) -> None:
        if self._settings_window is None:
            return
        self.project_root = _normalize_project_root(self._settings_window.project_root)
        if self._settings_window.config_path is not None:
            self.config_path = Path(self._settings_window.config_path).resolve()
        self.ini_store.reload_all(self.config_path.parent)

        self._update_project_header()
        self._reload_targets_from_ini()
        self._ensure_default_installer_targets()
        self._refresh_target_checkboxes()
        self._save_all_state()
        if self.statusBar():
            self.statusBar().showMessage("세팅 윈도우 설정이 반영되었습니다.", STATUS_BAR_SHORT_MS)

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
                f"프로젝트: {self.project_root}  |  설정 INI: {self.config_path}"
            )
        self.setWindowTitle(f"{MAIN_WINDOW_TITLE_PREFIX} - {self.project_root.name}")

    def _sync_overrides_from_targets(self) -> None:
        dcfg = TargetConfig.get_dir_config(self.project_root)
        self._dir_overrides = {
            "work_dir_name": dcfg.work_dir_name,
            "dist_dir_name": dcfg.dist_dir_name,
            "release_dir_name": dcfg.release_dir_name,
            "install_dir_name": dcfg.install_dir_name,
        }

        raw_targets = self._installer_overrides.get("targets")
        resolved_targets = (
            [str(x).strip() for x in raw_targets if str(x).strip()]
            if isinstance(raw_targets, (list, tuple))
            else _resolve_default_installer_targets()
        )
        self._installer_overrides = {
            "targets": resolved_targets,
            "name": str(self._installer_overrides.get("name") or "").strip() or None,
            "version_source_id": str(
                self._installer_overrides.get("version_source_id") or ""
            ).strip()
            or None,
            "extra": dict(self._installer_overrides.get("extra") or {}),
        }

    def _resolve_target_version(self, key: str, spec: Any) -> str:
        """대상 앱의 버전 문자열(예: 1.2.3)을 조회합니다."""
        candidates: list[Path] = []
        app_overrides = self._get_app_overrides()
        ov = app_overrides.get(key, {}) if isinstance(app_overrides, dict) else {}

        for raw in (
            ov.get("version_file"),
            getattr(spec, "version_file", None) if spec else None,
        ):
            if raw:
                p = Path(str(raw))
                candidates.append(p if p.is_absolute() else (self.project_root / p))

        rel_paths = (
            self.app_version_paths.get(key)
            or ov.get("version_rel_paths")
            or (getattr(spec, "version_rel_paths", None) if spec else None)
            or ()
        )
        for rel in rel_paths:
            if rel:
                p = Path(str(rel))
                candidates.append(p if p.is_absolute() else (self.project_root / p))

        dir_hints = (
            ov.get("dir_hints") or (getattr(spec, "dir_hints", None) if spec else None) or ()
        )
        for d in dir_hints:
            if d:
                candidates.append(self.project_root / SRC_SUBDIR_NAME / str(d) / VERSION_FILENAME)
                candidates.append(self.project_root / str(d) / VERSION_FILENAME)

        for path in candidates:
            try:
                if path.is_file():
                    lines = path.read_text(encoding=VERSION_FILE_ENCODING).strip().splitlines()
                    if lines and lines[0].strip():
                        return lines[0].strip().split()[0]
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

    def _on_all_targets_clicked(self) -> None:
        if self.chk_all_targets.checkState() == Qt.CheckState.PartiallyChecked:
            self.chk_all_targets.blockSignals(True)
            self.chk_all_targets.setCheckState(Qt.CheckState.Checked)
            self.chk_all_targets.blockSignals(False)
            checked = True
        else:
            checked = self.chk_all_targets.checkState() == Qt.CheckState.Checked

        if checked:
            self._ensure_default_installer_targets()
        self._set_all_targets_checked(checked)

    def _on_installer_target_changed(self, _state: int) -> None:
        is_checked = self.chk_installer_target.isChecked()
        self.chk_skip_installer.blockSignals(True)
        self.chk_skip_installer.setChecked(not is_checked)
        self.chk_skip_installer.blockSignals(False)
        if is_checked:
            self._ensure_default_installer_targets()
        self._sync_all_target_checkbox_state()
        self._sync_build_app_tabs()

    def _on_skip_installer_changed(self, _state: int) -> None:
        if hasattr(self, "chk_installer_target"):
            self.chk_installer_target.blockSignals(True)
            self.chk_installer_target.setChecked(not self.chk_skip_installer.isChecked())
            self.chk_installer_target.blockSignals(False)
        if not self.chk_skip_installer.isChecked():
            self._ensure_default_installer_targets()
        self._sync_all_target_checkbox_state()
        self._sync_build_app_tabs()

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
        previously_checked = {key for key, chk in self._target_checks.items() if chk.isChecked()}
        has_previous = len(self._target_checks) > 0

        while self.targets_row_layout.count():
            item = self.targets_row_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._target_checks.clear()

        keys = TargetConfig.ordered_keys()
        for idx, key in enumerate(keys):
            if idx > 0:
                self.targets_row_layout.addWidget(_create_v_separator(self.targets_group))
            spec = TargetConfig.get_spec(key)
            label = self._format_target_label(key, spec)
            chk = QCheckBox(label)
            chk.setToolTip(label)
            if has_previous:
                chk.setChecked(key in previously_checked or not previously_checked)
            else:
                chk.setChecked(True)
            chk.stateChanged.connect(self._on_target_checkbox_changed)
            self._target_checks[key] = chk
            self.targets_row_layout.addWidget(chk)

        if hasattr(self, "chk_installer_target"):
            self.chk_installer_target.blockSignals(True)
            self.chk_installer_target.setChecked(not self.chk_skip_installer.isChecked())
            self.chk_installer_target.blockSignals(False)

        self._sync_all_target_checkbox_state()
        self._sync_build_app_tabs()

    def _on_target_checkbox_changed(self, _state: int) -> None:
        self._sync_all_target_checkbox_state()
        self._sync_build_app_tabs()

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

        if checked:
            self._ensure_default_installer_targets()

        self._sync_all_target_checkbox_state()
        self._sync_build_app_tabs()

    def _get_selected_targets(self) -> list[str]:
        selected = [key for key, chk in self._target_checks.items() if chk.isChecked()]
        return selected or TargetConfig.ordered_keys()

    def _get_selected_bump(self) -> str | None:
        data = self.combo_bump.currentData()
        return str(data) if data else None

    def _get_selected_mode(self) -> str:
        return self.combo_mode.currentText().strip() or DEFAULT_BUILD_MODE

    def _collect_ui_state(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "selected_targets": [
                key for key, chk in self._target_checks.items() if chk.isChecked()
            ],
            KEY_MODE: self._get_selected_mode(),
            KEY_BUMP_UNIT: self._get_selected_bump(),
            "skip_installer": bool(self.chk_skip_installer.isChecked()),
            "installer_only": bool(self.chk_installer_only.isChecked()),
            "clean_build": bool(self.chk_clean_build.isChecked()),
            "clean_work_out": bool(self.chk_clean_work.isChecked()),
            "clean_dist_out": bool(self.chk_clean_dist.isChecked()),
            "clean_spec": bool(self.chk_clean_spec.isChecked()),
            "auto_scroll_log": bool(self._auto_scroll_log),
            "auto_install_libs": bool(self.auto_install_libs),
            "lib_venv_root": self.lib_venv_root,
            "lib_venv_dir_name": self.lib_venv_dir_name,
            "lib_confirm": bool(self.lib_confirm),
        }

    def _apply_ui_state(self, state: dict[str, Any]) -> None:
        saved_targets = state.get("selected_targets")
        if isinstance(saved_targets, list) and self._target_checks:
            target_set = {str(t) for t in saved_targets}
            for key, chk in self._target_checks.items():
                chk.blockSignals(True)
                chk.setChecked(key in target_set)
                chk.blockSignals(False)

        mode = state.get(KEY_MODE)
        if isinstance(mode, str):
            idx = self.combo_mode.findText(mode)
            if idx >= 0:
                self.combo_mode.blockSignals(True)
                self.combo_mode.setCurrentIndex(idx)
                self.combo_mode.blockSignals(False)

        bump = state.get(KEY_BUMP_UNIT)
        bump_idx = self.combo_bump.findData(bump)
        if bump_idx >= 0:
            self.combo_bump.blockSignals(True)
            self.combo_bump.setCurrentIndex(bump_idx)
            self.combo_bump.blockSignals(False)

        skip_inst = bool(state.get("skip_installer", False))
        self.chk_skip_installer.blockSignals(True)
        self.chk_skip_installer.setChecked(skip_inst)
        self.chk_skip_installer.blockSignals(False)

        if hasattr(self, "chk_installer_target"):
            self.chk_installer_target.blockSignals(True)
            self.chk_installer_target.setChecked(not skip_inst)
            self.chk_installer_target.blockSignals(False)

        self.chk_installer_only.setChecked(bool(state.get("installer_only", False)))

        clean_boxes = (
            self.chk_clean_build,
            self.chk_clean_work,
            self.chk_clean_dist,
            self.chk_clean_spec,
        )
        for box in clean_boxes:
            box.blockSignals(True)
        self.chk_clean_build.setChecked(bool(state.get("clean_build", False)))
        self.chk_clean_work.setChecked(bool(state.get("clean_work_out", False)))
        self.chk_clean_dist.setChecked(bool(state.get("clean_dist_out", False)))
        self.chk_clean_spec.setChecked(bool(state.get("clean_spec", False)))
        for box in clean_boxes:
            box.blockSignals(False)

        auto_scroll = bool(state.get("auto_scroll_log", True))
        self._apply_auto_scroll_policy(auto_scroll)

        if "auto_install_libs" in state:
            self.auto_install_libs = bool(state.get("auto_install_libs"))
        if "lib_venv_root" in state:
            raw_venv_root = state.get("lib_venv_root")
            self.lib_venv_root = (
                str(Path(str(raw_venv_root)).resolve())
                if isinstance(raw_venv_root, str) and raw_venv_root.strip()
                else None
            )
        if "lib_venv_dir_name" in state and state.get("lib_venv_dir_name"):
            self.lib_venv_dir_name = str(state.get("lib_venv_dir_name")).strip()
        if "lib_confirm" in state:
            self.lib_confirm = bool(state.get("lib_confirm"))

        self._sync_all_target_checkbox_state()
        self._sync_build_app_tabs()

    def _reload_targets_from_ini(self) -> None:
        sections = self.ini_store.load_target_sections()
        dir_ov = {k: v for k, v in sections["dirs"].items() if v}
        app_ov = sections["app_overrides"]
        inst_dict = sections["installer"]

        TargetConfig.configure(
            project_root=self.project_root,
            code_overrides=dir_ov or None,
            app_overrides=app_ov or None,
        )

        if self._build_target_window is not None:
            self._build_target_window.set_paths(self.project_root, self.config_path)
            self._build_target_window.load_from_ini(self.config_path, show_error=False)

        dcfg = TargetConfig.get_dir_config(self.project_root)
        self._dir_overrides = {
            "work_dir_name": dcfg.work_dir_name,
            "dist_dir_name": dcfg.dist_dir_name,
            "release_dir_name": dcfg.release_dir_name,
            "install_dir_name": dcfg.install_dir_name,
        }

        raw_targets = inst_dict.get("targets")
        has_other_inst_cfg = bool(
            str(inst_dict.get("name") or "").strip()
            or str(inst_dict.get("version_source_id") or "").strip()
            or (isinstance(inst_dict.get("extra"), dict) and bool(inst_dict.get("extra")))
        )
        if isinstance(raw_targets, (list, tuple)):
            resolved_targets = [str(x).strip() for x in raw_targets if str(x).strip()]
        elif has_other_inst_cfg:
            resolved_targets = []
        else:
            resolved_targets = _resolve_default_installer_targets()

        self._installer_overrides = {
            "targets": resolved_targets,
            "name": str(inst_dict.get("name") or "").strip() or None,
            "version_source_id": str(inst_dict.get("version_source_id") or "").strip() or None,
            "extra": dict(inst_dict.get("extra") or {}),
        }

    def _load_saved_state(self) -> None:
        self.ini_store.reload_all(self.config_path.parent)
        state = self.ini_store.load_ui_state()

        proj_dir = state.get("project_root")
        if isinstance(proj_dir, str) and proj_dir.strip():
            candidate_root = _normalize_project_root(proj_dir)
            if candidate_root.is_dir():
                self.project_root = candidate_root
                self.config_path = self.project_root / BUILD_MANAGER_INI_NAME
                self.ini_store.reload_all(self.config_path.parent)
                state = self.ini_store.load_ui_state()

        self._reload_targets_from_ini()
        self._refresh_target_checkboxes()
        if state:
            self._apply_ui_state(state)
        self._update_project_header()
        self._sync_build_app_tabs()

    def _save_all_state(self) -> None:
        self.ini_store.save_ui_state(self._collect_ui_state())
        self._save_build_config_ini_now()

    def _save_build_config_ini_now(self) -> None:
        win = self._build_target_window
        if win is not None and hasattr(win, "_stage_all_tabs_state"):
            win._stage_all_tabs_state()

        app_ov = {k: dict(v) for k, v in self._get_app_overrides().items()}
        dcfg = TargetConfig.get_dir_config(self.project_root)
        dir_dict = {
            "work_dir_name": dcfg.work_dir_name,
            "dist_dir_name": dcfg.dist_dir_name,
            "release_dir_name": dcfg.release_dir_name,
            "install_dir_name": dcfg.install_dir_name,
        }
        inst_payload = {
            "targets": self._installer_overrides.get("targets") or [],
            "name": self._installer_overrides.get("name") or "",
            "version_source_id": self._installer_overrides.get("version_source_id") or "",
            "installer_only": bool(self.chk_installer_only.isChecked()),
            "skip_installer": bool(self.chk_skip_installer.isChecked()),
            "extra": dict(self._installer_overrides.get("extra") or {}),
        }
        self.ini_store.save_target_sections(
            dir_values=dir_dict,
            app_overrides=app_ov,
            installer_values=inst_payload,
        )

    def _get_checked_app_keys(self) -> list[str]:
        return [key for key, chk in self._target_checks.items() if chk.isChecked()]

    def _bind_clean_option_signals(self) -> None:
        self.chk_clean_build.stateChanged.connect(self._on_main_clean_options_changed)
        self.chk_clean_work.stateChanged.connect(self._on_main_clean_options_changed)
        self.chk_clean_dist.stateChanged.connect(self._on_main_clean_options_changed)
        self.chk_clean_spec.stateChanged.connect(self._on_main_clean_options_changed)

    def _on_main_clean_options_changed(self, _state: int) -> None:
        selected_apps = self._get_checked_app_keys()
        if not selected_apps:
            return

        clean_all = bool(self.chk_clean_build.isChecked())
        clean_patch = {
            KEY_CLEAN_WORK: clean_all or bool(self.chk_clean_work.isChecked()),
            KEY_CLEAN_DIST: clean_all or bool(self.chk_clean_dist.isChecked()),
            KEY_CLEAN_SPEC: clean_all or bool(self.chk_clean_spec.isChecked()),
        }

        app_ov = self._get_app_overrides()
        for key in selected_apps:
            bucket = dict(app_ov.get(key, {}))
            bucket.update(clean_patch)
            app_ov[key] = bucket

        TargetConfig.configure(
            project_root=self.project_root,
            code_overrides=self._dir_overrides or None,
            app_overrides=app_ov,
        )

        if self._build_target_window is not None and hasattr(
            self._build_target_window, "apply_clean_options_to_targets"
        ):
            self._build_target_window.set_paths(self.project_root, self.config_path)
            self._build_target_window.apply_clean_options_to_targets(
                selected_apps,
                clean_patch,
                persist_ini=True,
                emit_signal=True,
            )
        else:
            self._save_build_config_ini_now()

    def _resolve_app_clean_flag(self, target_key: str, field_name: str, fallback: bool) -> bool:
        app_overrides = self._get_app_overrides()
        ov = app_overrides.get(target_key, {}) if isinstance(app_overrides, dict) else {}
        if field_name in ov and isinstance(ov[field_name], bool):
            return bool(ov[field_name])
        return bool(fallback)

    def _resolve_app_bump_unit(self, target_key: str, default_bump: str | None) -> str | None:
        app_overrides = self._get_app_overrides()
        ov = app_overrides.get(target_key, {}) if isinstance(app_overrides, dict) else {}
        if KEY_BUMP_UNIT in ov and ov[KEY_BUMP_UNIT] is not None:
            s = str(ov[KEY_BUMP_UNIT]).strip().lower()
            if not s or s in NONE_BUMP_TOKENS:
                return None
            if s in VALID_BUMP_UNITS:
                return s
        return default_bump

    def _resolve_app_mode(self, target_key: str, default_mode: str) -> str:
        app_overrides = self._get_app_overrides()
        ov = app_overrides.get(target_key, {}) if isinstance(app_overrides, dict) else {}
        raw_mode = ov.get(KEY_MODE)
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
        return default_mode

    def _resolve_app_run_test(self, target_key: str) -> bool:
        app_overrides = self._get_app_overrides()
        ov = app_overrides.get(target_key, {}) if isinstance(app_overrides, dict) else {}
        if KEY_RUN_TEST in ov:
            return bool(ov[KEY_RUN_TEST])
        spec = TargetConfig.get_spec(target_key)
        return bool(getattr(spec, KEY_RUN_TEST, False)) if spec else False

    def _apply_patch_to_selected_apps(self, patch: dict[str, Any]) -> None:
        selected_apps = self._get_checked_app_keys()
        if not selected_apps or not patch:
            return

        app_ov = self._get_app_overrides()
        for key in selected_apps:
            bucket = dict(app_ov.get(key, {}))
            for k, v in patch.items():
                if v is None:
                    bucket.pop(k, None)
                else:
                    bucket[k] = v
            app_ov[key] = bucket

        TargetConfig.configure(
            project_root=self.project_root,
            code_overrides=self._dir_overrides or None,
            app_overrides=app_ov,
        )

        if self._build_target_window is not None and hasattr(
            self._build_target_window, "apply_app_fields_to_targets"
        ):
            self._build_target_window.set_paths(self.project_root, self.config_path)
            self._build_target_window.apply_app_fields_to_targets(
                selected_apps,
                patch,
                persist_ini=True,
                emit_signal=True,
            )
        else:
            self._save_build_config_ini_now()

    def _on_main_mode_changed(self, _index: int) -> None:
        mode = self._get_selected_mode()
        self._apply_patch_to_selected_apps({KEY_MODE: mode})

    def _on_main_bump_changed(self, _index: int) -> None:
        bump = self._get_selected_bump()
        self._apply_patch_to_selected_apps({KEY_BUMP_UNIT: bump})
        self._sync_build_app_tabs()

    def _build_step_plan_specs(
        self,
        *,
        app_keys: list[str],
        parsed_apps: dict[str, list[str]],
        clean_build_opt: bool,
        installer_only_opt: bool,
        include_installer: bool,
        installer_targets: list[str],
        mode: str,
        fallback_bump: str | None,
    ) -> list[dict[str, Any]]:
        """선행 공용 단계와 앱별 파이프라인 단계, 인스톨러 단계를 순서대로 구성합니다."""
        specs: list[dict[str, Any]] = []

        if clean_build_opt:
            specs.append(
                {
                    "kind": JOB_TYPE_CLEAN,
                    "step_key": JOB_TYPE_CLEAN,
                    "job_key": JOB_TYPE_CLEAN,
                    "target_app": None,
                    "ui_key": None,
                    "targets": [],
                    "bump_unit": None,
                    "mode": mode,
                    "clean_build": True,
                    "skip_installer": True,
                    "installer_only": False,
                }
            )

        if not installer_only_opt:
            all_selected_targets = [t for k in app_keys for t in parsed_apps.get(k, [k])]
            first_app_key = app_keys[0] if app_keys else None

            for shared_step in SHARED_PRE_STEPS:
                specs.append(
                    {
                        "kind": JOB_TYPE_STEP,
                        "step_key": shared_step,
                        "job_key": shared_step,
                        "target_app": None,
                        "ui_key": first_app_key,
                        "targets": all_selected_targets,
                        "bump_unit": None,
                        "mode": mode,
                        "clean_build": False,
                        "skip_installer": True,
                        "installer_only": False,
                    }
                )

            for key in app_keys:
                job_targets = parsed_apps[key]
                job_bump = self._resolve_app_bump_unit(key, fallback_bump)
                job_mode = self._resolve_app_mode(key, mode)
                for app_step in APP_PIPELINE_STEPS:
                    specs.append(
                        {
                            "kind": JOB_TYPE_STEP,
                            "step_key": app_step,
                            "job_key": f"{key}_{app_step}",
                            "target_app": key,
                            "ui_key": key,
                            "targets": job_targets,
                            "bump_unit": job_bump if app_step == STEP_VERSION else None,
                            "mode": job_mode,
                            "clean_build": False,
                            "skip_installer": True,
                            "installer_only": False,
                        }
                    )

        if include_installer:
            specs.append(
                {
                    "kind": JOB_TYPE_STEP,
                    "step_key": STEP_INSTALLER,
                    "job_key": INSTALLER_TAB_KEY,
                    "target_app": None,
                    "ui_key": INSTALLER_TAB_KEY,
                    "targets": list(installer_targets),
                    "bump_unit": None,
                    "mode": mode,
                    "clean_build": False,
                    "skip_installer": False,
                    "installer_only": installer_only_opt,
                }
            )

        return specs

    def _submit_next_build_step(self) -> bool:
        """대기 중인 다음 빌드 단계 1건을 TaskManager에 제출합니다."""
        if self._cancel_requested or self._is_closing:
            self._pending_step_specs.clear()
            return False
        if not self._pending_step_specs:
            return False

        spec = self._pending_step_specs.pop(0)
        kind = str(spec["kind"])
        step_key = str(spec["step_key"])
        job_key = str(spec["job_key"])
        target_app = spec.get("target_app")
        ui_key = spec.get("ui_key")
        job_mode = str(spec.get("mode") or self._get_selected_mode())
        job_bump = spec.get("bump_unit")
        job_targets = list(spec.get("targets") or [])

        is_clean = kind == JOB_TYPE_CLEAN
        is_installer = step_key == STEP_INSTALLER
        is_app_target = isinstance(target_app, str) and bool(target_app)

        app_run_test = self._resolve_app_run_test(target_app) if is_app_target else False

        app_clean_work = (
            False
            if is_clean
            else (
                self._resolve_app_clean_flag(
                    target_app, KEY_CLEAN_WORK, bool(self.chk_clean_work.isChecked())
                )
                if is_app_target
                else bool(self.chk_clean_work.isChecked())
            )
        )
        app_clean_dist = (
            False
            if is_clean
            else (
                self._resolve_app_clean_flag(
                    target_app, KEY_CLEAN_DIST, bool(self.chk_clean_dist.isChecked())
                )
                if is_app_target
                else bool(self.chk_clean_dist.isChecked())
            )
        )
        app_clean_spec = (
            False
            if is_clean
            else (
                self._resolve_app_clean_flag(
                    target_app, KEY_CLEAN_SPEC, bool(self.chk_clean_spec.isChecked())
                )
                if is_app_target
                else bool(self.chk_clean_spec.isChecked())
            )
        )

        app_ov_copy = {k: dict(v) for k, v in self._get_app_overrides().items()}

        build_kwargs: dict[str, Any] = {
            "project_root": str(self.project_root),
            "job_type": kind,
            "step_key": step_key,
            "target_app": target_app if is_app_target else None,
            "targets": job_targets,
            KEY_BUMP_UNIT: job_bump,
            KEY_MODE: job_mode,
            KEY_RUN_TEST: app_run_test,
            "skip_installer": bool(spec["skip_installer"]),
            "installer_only": bool(spec["installer_only"]),
            "clean_build": bool(spec["clean_build"]),
            "clean_work_out": app_clean_work,
            "clean_dist_out": app_clean_dist,
            "clean_spec": app_clean_spec,
            "progress_callback": None,
            "timer": None,
            "dir_config_json": None,
            "dir_overrides": dict(self._dir_overrides),
            "app_overrides": app_ov_copy,
            "installer_targets": list(job_targets) if is_installer else None,
            "installer_overrides": dict(self._installer_overrides),
            "pipeline_state": dict(self._pipeline_state),
            "auto_install_libs": bool(self.auto_install_libs),
            "lib_venv_root": self.lib_venv_root,
            "lib_venv_dir_name": self.lib_venv_dir_name,
            "lib_confirm": bool(self.lib_confirm),
        }

        ts_ms = int(time.time() * DEFAULT_MS_PER_SEC)
        step_idx = self._completed_step_count
        task_key = f"{TASK_PREFIX_BUILD_MGR}{ts_ms}_{step_idx}_{job_key}"
        task_name = f"Step({job_mode}:{job_key})"

        if ui_key and hasattr(self, "build_app_tabs_group"):
            self.build_app_tabs_group.focus_tab(str(ui_key))

        self._active_build_keys.clear()
        self._task_to_app_key.clear()
        self._active_build_keys.add(task_key)
        if ui_key:
            self._task_to_app_key[task_key] = str(ui_key)

        logd(
            f"[BuildManager] 단계 작업 제출 (task_key={task_key}, job_type={kind}, "
            f"step_key={step_key}, target_app={build_kwargs['target_app']}, "
            f"targets={job_targets}, bump_unit={job_bump}, mode={job_mode})"
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
        return True

    def _rollback_versions_if_needed(self) -> None:
        prev_versions = self._pipeline_state.get("previous_versions")
        if not isinstance(prev_versions, dict) or not prev_versions:
            return
        try:
            helpers = get_build_target_helpers(str(self.project_root))
            svc = VersionService(
                project_root=str(self.project_root),
                target_helpers=helpers,
            )
            svc.rollback(dict(prev_versions))
            logd(f"[BuildManager] 단계 실패/취소로 버전 롤백 완료: {prev_versions}")
        except Exception as exc:
            loge(f"[BuildManager] 버전 롤백 중 오류 발생: {exc}")

    def _on_start_build(self) -> None:
        if self._active_build_keys or self._pending_step_specs:
            QMessageBox.information(
                self, "빌드 진행 중", "이미 빌드가 실행 중이거나 대기열에 있습니다."
            )
            return

        checked_apps = [key for key, chk in self._target_checks.items() if chk.isChecked()]
        app_keys = checked_apps or list(TargetConfig.ordered_keys())

        clean_build_opt = bool(self.chk_clean_build.isChecked())
        skip_installer_opt = bool(self.chk_skip_installer.isChecked())
        installer_only_opt = bool(self.chk_installer_only.isChecked())
        include_installer = bool(self.chk_installer_target.isChecked()) and (
            not skip_installer_opt or installer_only_opt
        )

        installer_targets = self._ensure_default_installer_targets() if include_installer else []

        parsed_apps: dict[str, list[str]] = {}
        try:
            for key in app_keys:
                parsed_apps[key] = parse_targets([key])
            if include_installer and installer_targets:
                _ = parse_targets(installer_targets)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "대상 오류",
                f"빌드 대상 확인 중 오류가 발생했습니다:\n{exc}",
            )
            return

        mode = self._get_selected_mode()
        fallback_bump = self._get_selected_bump()

        step_specs = self._build_step_plan_specs(
            app_keys=app_keys,
            parsed_apps=parsed_apps,
            clean_build_opt=clean_build_opt,
            installer_only_opt=installer_only_opt,
            include_installer=include_installer,
            installer_targets=installer_targets,
            mode=mode,
            fallback_bump=fallback_bump,
        )

        if not step_specs:
            QMessageBox.warning(self, "대상 오류", "실행할 빌드 작업이 없습니다.")
            return

        self._cancel_requested = False
        self._pipeline_state = {"mode": mode}
        self._pending_step_specs = list(step_specs)
        self._total_build_count = len(step_specs)
        self._completed_step_count = 0

        self.progress_bar.setValue(DEFAULT_PROGRESS_MIN)
        self.lbl_progress_detail.setText(
            f"단계별 빌드 대기열 등록 중... (총 {len(step_specs)}개 단계)"
        )
        self.btn_start_build.setEnabled(False)
        self.btn_cancel_build.setEnabled(True)

        tab_keys: list[str] = [] if installer_only_opt else list(app_keys)
        if include_installer and INSTALLER_TAB_KEY not in tab_keys:
            tab_keys.append(INSTALLER_TAB_KEY)

        if hasattr(self, "build_app_tabs_group"):
            self.build_app_tabs_group.reset_all_progress(tab_keys)
            first_tab_key = next(
                (str(s["ui_key"]) for s in step_specs if s.get("ui_key")),
                tab_keys[0] if tab_keys else None,
            )
            if first_tab_key:
                self.build_app_tabs_group.focus_tab(first_tab_key)

        try:
            submitted = self._submit_next_build_step()
            if not submitted:
                raise RuntimeError("첫 번째 빌드 단계를 제출할 수 없습니다.")
        except Exception as exc:
            self._pending_step_specs.clear()
            self._active_build_keys.clear()
            self._task_to_app_key.clear()
            self._total_build_count = 0
            self._completed_step_count = 0
            loge(f"[BuildManager] 빌드 단계 제출 실패: {exc}")
            self.btn_start_build.setEnabled(True)
            self.btn_cancel_build.setEnabled(False)
            QMessageBox.warning(self, "등록 오류", str(exc))

    def _on_cancel_build(self) -> None:
        if not self._active_build_keys and not self._pending_step_specs:
            return
        self._cancel_requested = True
        self._pending_step_specs.clear()
        keys_to_cancel = list(self._active_build_keys)
        logd(f"[BuildManager] 빌드 취소 요청 (task_keys={keys_to_cancel})")
        self.btn_cancel_build.setEnabled(False)
        self.lbl_progress_detail.setText(MSG_CANCEL_REQUESTING)
        for k in keys_to_cancel:
            TaskManager().cancel(k)
        logd(MSG_CANCEL_DISPATCHED, level=LOG_LEVEL_INFO)
        if self.statusBar():
            self.statusBar().showMessage(MSG_CANCEL_REQUESTING, STATUS_BAR_SHORT_MS)

    def _on_build_finished(self, ok: bool, message: str) -> None:
        self._active_build_keys.clear()
        self._task_to_app_key.clear()
        self._pending_step_specs.clear()
        self._pipeline_state.clear()
        self._cancel_requested = False
        self._total_build_count = 0
        self._completed_step_count = 0
        self.btn_start_build.setEnabled(True)
        self.btn_cancel_build.setEnabled(False)
        if ok:
            self.progress_bar.setValue(DEFAULT_PROGRESS_MAX)
        self.lbl_progress_detail.setText(message)
        if self.statusBar():
            self.statusBar().showMessage(message, STATUS_BAR_LONG_MS)
        clear_prev_version_cache()
        self._completed_zip_sigs.clear()
        self._sync_build_app_tabs()

    def closeEvent(self, event: Any) -> None:
        if self._active_build_keys or self._pending_step_specs:
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
        self._cancel_requested = True
        self._pending_step_specs.clear()
        self._deferred_zip_tasks.clear()
        TaskManager().on_window_closing(
            self._build_listener,
            reason=MSG_CLOSE_CANCEL_REASON,
        )
        self._active_build_keys.clear()
        self._task_to_app_key.clear()
        self._total_build_count = 0
        self._completed_step_count = 0
        self._save_all_state()
        self._dispose_build_target_window()
        self._dispose_settings_window()
        self._teardown_logging()
        super().closeEvent(event)

    def _has_custom_installer_config(self) -> bool:
        inst = self._installer_overrides or {}
        if inst.get("targets") is not None:
            return True
        if str(inst.get("name") or "").strip():
            return True
        if str(inst.get("version_source_id") or "").strip():
            return True
        if isinstance(inst.get("extra"), dict) and bool(inst.get("extra")):
            return True
        return False

    def _mark_installer_configured(self) -> None:
        self._installer_user_configured = True
        if self._build_target_window is not None and hasattr(
            self._build_target_window, "mark_installer_configured"
        ):
            self._build_target_window.mark_installer_configured()

    def _ensure_default_installer_targets(self) -> list[str]:
        current_targets = self._installer_overrides.get("targets")
        if isinstance(current_targets, (list, tuple)):
            return [str(x).strip() for x in current_targets if str(x).strip()]

        if (
            getattr(self, "_installer_user_configured", False)
            or self._has_custom_installer_config()
        ):
            return []

        defaults = _resolve_default_installer_targets()
        self._installer_overrides["targets"] = list(defaults)
        if self._build_target_window is not None:
            self._build_target_window._rebuild_installer_target_checkboxes(defaults)
            self._build_target_window._installer_config = (
                self._build_target_window._collect_installer_config()
            )
        return list(defaults)

    def _sync_installer_overrides_from_target_window(self) -> None:
        win = self._build_target_window
        if win is None:
            return
        inst_cfg: dict[str, Any] | None = None
        if hasattr(win, "get_installer_overrides_dict"):
            try:
                inst_cfg = win.get_installer_overrides_dict()
            except Exception:
                inst_cfg = None
        if not isinstance(inst_cfg, dict) and hasattr(win, "_collect_installer_config"):
            try:
                collected = win._collect_installer_config()
                inst_cfg = collected.to_dict() if hasattr(collected, "to_dict") else None
            except Exception:
                inst_cfg = None
        if isinstance(inst_cfg, dict):
            raw_targets = inst_cfg.get("targets")
            targets = (
                [str(x).strip() for x in raw_targets if str(x).strip()]
                if isinstance(raw_targets, (list, tuple))
                else list(self._installer_overrides.get("targets") or [])
            )
            self._installer_overrides = {
                "targets": targets,
                "name": str(inst_cfg.get("name") or "").strip() or None,
                "version_source_id": str(inst_cfg.get("version_source_id") or "").strip() or None,
                "extra": dict(inst_cfg.get("extra") or {}),
            }
            self._installer_user_configured = True
