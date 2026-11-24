"""
PrintShopApp 빌드 파이프라인 코어 모듈 (build.py)
- BuildApp 파이프라인 실행, 단계 타이머, 공개키/암호화 모듈 리로드 및 대상 파싱 담당
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from Common.log import set_file_tag

FILE_TAG_BUILD: str = "BUILD"
set_file_tag(FILE_TAG_BUILD)

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

for p in (str(PROJECT_ROOT), str(SRC_DIR), str(CURRENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from Common.log import logd, loge  # noqa: E402
from Common.step_timer import BuildStepTimer  # noqa: E402
from build_script.artifact_signing import inject_and_verify_exe  # noqa: E402
from build_script.build_targets import (  # noqa: E402
    AppTargetSpec,
    BuildDirConfig,
    BuildTargets,
    MAIN_APP_OVERRIDE_NAME,
    SRC_DIR_NAME,
    TEST_DIR_NAME,
    UNKNOWN_ORDER_SORT_KEY,
    get_build_target_helpers,
    get_target_spec,
)
from build_script.env_ui_helper import (  # noqa: E402
    convert_ui_files,
    resolve_built_exe_path,
    resolve_python_executable,
)
from build_script.packaging_service import (  # noqa: E402
    FULL_COMBO_TAG,
    MODE_PRODUCTION,
    NONE_COMBO_TAG,
    PackagingService,
)
from build_script.spec_builder import SpecAndPyInstallerBuilder  # noqa: E402
from build_script.target_config_io import (  # noqa: E402
    DEFAULT_TEXT_ENCODING,
    INSTALLER_FIELD_ONLY,
    INSTALLER_FIELD_SKIP,
    INSTALLER_FIELD_TARGETS,
    InstallerBuildConfig,
    normalize_bump_unit,
)
from build_script.target_records import ensure_default_targets_injected  # noqa: E402
from build_script.version_service import VersionService  # noqa: E402

from build_script.test.test_source_gen import generate_app_pytest_scripts  # noqa: E402

ensure_default_targets_injected()

try:
    from Common.prio_worker_queue import CancelToken, kill_process_tree  # noqa: E402
except Exception:
    try:
        from prio_worker_queue import CancelToken, kill_process_tree  # type: ignore  # noqa: E402
    except Exception:
        CancelToken = Any  # type: ignore

        def kill_process_tree(proc: subprocess.Popen[Any]) -> None:  # type: ignore[misc]
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass


STEP_UI: str = "step1_ui"
STEP_ENV: str = "step2_env"
STEP_PUBKEY: str = "step3_pubkey"
STEP_VERSION: str = "step4_version"
STEP_BUILD: str = "step5_build"
STEP_EOF_CRYPTO: str = "step6_eof_crypto"
STEP_TEST_SYNC: str = "step7_test_sync"
STEP_APP_TEST: str = "step7_1_app_pytest"
STEP_RELEASE: str = "step8_release"
STEP_INSTALLER: str = "step9_installer"

PIPELINE_STEP_WEIGHTS: tuple[tuple[str, float], ...] = (
    (STEP_UI, 0.05),
    (STEP_ENV, 0.04),
    (STEP_PUBKEY, 0.03),
    (STEP_VERSION, 0.08),
    (STEP_BUILD, 0.35),
    (STEP_EOF_CRYPTO, 0.10),
    (STEP_TEST_SYNC, 0.05),
    (STEP_APP_TEST, 0.06),
    (STEP_RELEASE, 0.08),
    (STEP_INSTALLER, 0.16),
)

STATUS_SUCCESS: str = "SUCCESS"
STATUS_FAILED: str = "FAILED"
STATUS_SKIPPED: str = "SKIPPED"

ENV_BUILD_MODE: str = "BUILD_MODE"
ENV_PYTHONUNBUFFERED: str = "PYTHONUNBUFFERED"
DEFAULT_CMD_TIMEOUT_SEC: int = 600
PUBKEY_REVERIFY_ATTEMPTS: int = 2
SETUP_SUFFIX: str = "Setup"

PUBKEY_MODULE_CANDIDATES: tuple[str, ...] = (
    "Common.Version.exe_version_public_key",
    "exe_version_public_key",
)
CRYPTO_MODULE_CANDIDATES: tuple[str, ...] = (
    "Common.Version.exe_version_crypto",
    "exe_version_crypto",
)
PUBKEY_GEN_SCRIPT_REL_PARTS: tuple[str, ...] = (
    SRC_DIR_NAME,
    "Common",
    "Version",
    "generate_public_key_module.py",
)

__all__ = [
    "BuildApp",
    "CRYPTO_MODULE_CANDIDATES",
    "DEFAULT_CMD_TIMEOUT_SEC",
    "ENV_BUILD_MODE",
    "ENV_PYTHONUNBUFFERED",
    "FILE_TAG_BUILD",
    "PIPELINE_STEP_WEIGHTS",
    "PUBKEY_GEN_SCRIPT_REL_PARTS",
    "PUBKEY_MODULE_CANDIDATES",
    "PUBKEY_REVERIFY_ATTEMPTS",
    "PrintShopBuildStepTimer",
    "SETUP_SUFFIX",
    "STATUS_FAILED",
    "STATUS_SKIPPED",
    "STATUS_SUCCESS",
    "STEP_BUILD",
    "STEP_ENV",
    "STEP_EOF_CRYPTO",
    "STEP_INSTALLER",
    "STEP_PUBKEY",
    "STEP_RELEASE",
    "STEP_TEST_SYNC",
    "STEP_APP_TEST",
    "STEP_UI",
    "STEP_VERSION",
    "parse_targets",
    "reload_pubkey_and_crypto_modules",
]


class PrintShopBuildStepTimer(BuildStepTimer):
    """PrintShopApp 빌드 파이프라인 단계를 등록하는 BuildStepTimer 하위 클래스."""

    def __init__(self):
        super().__init__()
        self.register_steps(list(PIPELINE_STEP_WEIGHTS))


def reload_pubkey_and_crypto_modules() -> dict[str, list[str]]:
    """갱신된 exe_version_public_key 및 crypto 모듈을 안전하게 리로드합니다."""
    reloaded: dict[str, list[str]] = {"pubkey": [], "crypto": []}

    for mod_name in PUBKEY_MODULE_CANDIDATES:
        mod = sys.modules.get(mod_name)
        if mod is not None:
            importlib.reload(mod)
            reloaded["pubkey"].append(mod_name)

    for mod_name in CRYPTO_MODULE_CANDIDATES:
        mod = sys.modules.get(mod_name)
        if mod is not None:
            importlib.reload(mod)
            reloaded["crypto"].append(mod_name)

    return reloaded


def parse_targets(raw_targets: list[str] | str | None) -> list[str]:
    """번호 또는 대상 이름을 정규화된 target 목록으로 변환."""
    ensure_default_targets_injected()
    return BuildTargets.parse_targets(raw_targets)


class BuildApp:
    def __init__(
        self,
        project_root: str = str(PROJECT_ROOT),
        targets: list[str] | None = None,
        bump_unit: str | None = None,
        bump_units: dict[str, str | None] | None = None,
        mode: str = MODE_PRODUCTION,
        skip_installer: bool = False,
        installer_only: bool = False,
        installer_targets: list[str] | str | None = None,
        clean_build: bool = False,
        clean_work_out: bool = False,
        clean_dist_out: bool = False,
        clean_spec: bool = False,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        timer: BuildStepTimer | None = None,
        dir_config_json: str | None = None,
        app_config_json: str | None = None,
        installer_config_json: str | None = None,
        dir_overrides: dict[str, Any] | None = None,
        cli_dir_overrides: dict[str, Any] | None = None,
        app_overrides: dict[str, dict[str, Any]] | None = None,
        cli_app_overrides: dict[str, dict[str, Any]] | None = None,
        installer_overrides: dict[str, Any] | None = None,
        cli_installer_overrides: dict[str, Any] | None = None,
        cancel_event: threading.Event | None = None,
        cancel_token: Any | None = None,
        run_tests: bool = True,
        pytest_args: list[str] | None = None,
        test_fail_build: bool = True,        
    ):
        self.project_root = os.path.abspath(project_root)
        self.src_dir = os.path.join(self.project_root, SRC_DIR_NAME)
        self.cancel_token = cancel_token
        self.cancel_event: threading.Event | None = (
            getattr(cancel_token, "event", None) if cancel_token is not None else cancel_event
        )

        self.run_tests: bool = bool(run_tests)
        self.pytest_args: list[str] = list(pytest_args) if pytest_args else ["-v"]
        self.test_fail_build: bool = bool(test_fail_build)

        ensure_default_targets_injected()

        self.dir_config: BuildDirConfig = BuildTargets.configure(
            project_root=self.project_root,
            json_path=dir_config_json,
            app_config_json=app_config_json,
            cli_overrides=cli_dir_overrides,
            code_overrides=dir_overrides,
            app_overrides=app_overrides,
            cli_app_overrides=cli_app_overrides,
        )
        self.target_helpers: dict[str, Any] = get_build_target_helpers(self.project_root)

        merged_cli_installer: dict[str, Any] = dict(cli_installer_overrides or {})
        if installer_targets is not None and INSTALLER_FIELD_TARGETS not in merged_cli_installer:
            merged_cli_installer[INSTALLER_FIELD_TARGETS] = installer_targets
        if installer_only and INSTALLER_FIELD_ONLY not in merged_cli_installer:
            merged_cli_installer[INSTALLER_FIELD_ONLY] = True
        if skip_installer and INSTALLER_FIELD_SKIP not in merged_cli_installer:
            merged_cli_installer[INSTALLER_FIELD_SKIP] = True

        self.installer_config: InstallerBuildConfig = InstallerBuildConfig.resolve(
            project_root=self.project_root,
            json_path=dir_config_json,
            installer_config_json=installer_config_json,
            code_overrides=installer_overrides,
            cli_overrides=merged_cli_installer,
        )

        self.targets = targets or BuildTargets.ordered_keys(include_installer=False)
        self.bump_unit = normalize_bump_unit(bump_unit)
        self.bump_units: dict[str, str | None] = self._init_bump_units(bump_units)
        self.mode = mode or MODE_PRODUCTION
        self.skip_installer = bool(self.installer_config.skip_installer or skip_installer)
        self.installer_only = bool(self.installer_config.installer_only or installer_only)
        self.clean_build = clean_build
        self.clean_work_out = clean_work_out
        self.clean_dist_out = clean_dist_out
        self.clean_spec = clean_spec
        self.progress_callback = progress_callback
        self.timer: BuildStepTimer = timer or PrintShopBuildStepTimer()
        self.results: list[dict[str, Any]] = []
        self.public_key_status: dict[str, Any] = {}

        self.version_service = VersionService(
            project_root=self.project_root,
            target_helpers=self.target_helpers,
        )
        self.spec_builder = SpecAndPyInstallerBuilder(
            project_root=self.project_root,
            src_dir=self.src_dir,
            dir_config=self.dir_config,
            version_service=self.version_service,
            clean_work_out=self.clean_work_out,
            clean_dist_out=self.clean_dist_out,
            clean_spec=self.clean_spec,
            cancel_event=self.cancel_event,
            cancel_token=self.cancel_token,
        )
        self.packaging_service = PackagingService(
            project_root=self.project_root,
            dir_config=self.dir_config,
            version_service=self.version_service,
            mode=self.mode,
            cancel_event=self.cancel_event,
            cancel_token=self.cancel_token,
        )

    def _init_bump_units(self, explicit_bump_units: dict[str, str | None] | None) -> dict[str, str | None]:
        resolved: dict[str, str | None] = {}
        app_overrides_map = BuildTargets.get_app_overrides()
        for app_key, ov in app_overrides_map.items():
            if isinstance(ov, dict) and "bump_unit" in ov:
                resolved[app_key] = normalize_bump_unit(ov.get("bump_unit"))
        if explicit_bump_units:
            for app_key, unit in explicit_bump_units.items():
                resolved[str(app_key)] = normalize_bump_unit(unit)
        return resolved

    def _resolve_target_bump_unit(self, target_key: str) -> str | None:
        if target_key in self.bump_units:
            return normalize_bump_unit(self.bump_units[target_key])
        return self.bump_unit

    def _is_cancelled(self) -> bool:
        if self.cancel_token is not None and getattr(self.cancel_token, "is_set", False):
            return True
        if self.cancel_event is not None and self.cancel_event.is_set():
            return True
        return False

    def _check_cancelled(self, reason: str = "사용자에 의해 빌드가 취소되었습니다.") -> None:
        if self._is_cancelled():
            raise InterruptedError(reason)

    def _emit_progress(self, payload: dict[str, Any]) -> None:
        if self._is_cancelled():
            return
        if callable(self.progress_callback):
            try:
                self.progress_callback(payload)
            except Exception:
                pass

    def _begin_step(self, step_key: str, detail: str = "") -> float:
        self._check_cancelled()
        rec = self.timer.start_step(step_key)
        payload = self.timer.build_progress_payload(
            step_key=step_key,
            phase="start",
            detail=detail or step_key,
            phase_ratio=0.15,
            is_final=False,
        )
        self._emit_progress(payload)
        return float(rec.get("start_ts") or 0.0)

    def _end_step(
        self,
        step_key: str,
        detail: str = "",
        is_final: bool = False,
        force_percent: int | None = None,
    ) -> float:
        rec = self.timer.end_step(step_key)
        payload = self.timer.build_progress_payload(
            step_key=step_key,
            phase="end",
            detail=detail or f"{step_key} 완료",
            phase_ratio=1.0,
            is_final=is_final,
            force_percent=force_percent,
        )
        self._emit_progress(payload)
        return float(rec.get("elapsed") or 0.0)

    def _record_result(self, step: str, status: str, detail: str, step_key: str | None = None) -> None:
        timing = self.timer.get_step_timing(step_key) if step_key else {}
        self.results.append(
            {
                "step": step,
                "status": status,
                "detail": detail,
                "start_time": timing.get("start_str", "-"),
                "end_time": timing.get("end_str", "-"),
                "elapsed": timing.get("elapsed", 0.0),
            }
        )

    def _run_cmd(
        self,
        cmd: list[str],
        cwd: str | None = None,
        check: bool = True,
        timeout: int | None = DEFAULT_CMD_TIMEOUT_SEC,
    ) -> subprocess.CompletedProcess[str]:
        self._check_cancelled("명령 실행 전 빌드가 취소되었습니다.")
        work_dir = cwd or self.project_root
        logd(f"  $ {' '.join(cmd)} (cwd={work_dir})")

        env = os.environ.copy()
        env[ENV_PYTHONUNBUFFERED] = "1"

        proc = subprocess.Popen(
            cmd,
            cwd=work_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=DEFAULT_TEXT_ENCODING,
            errors="replace",
            bufsize=1,
        )

        if self.cancel_token is not None and hasattr(self.cancel_token, "on_cancel"):
            self.cancel_token.on_cancel(lambda p=proc: kill_process_tree(p))

        captured_lines: list[str] = []
        try:
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                if self._is_cancelled():
                    kill_process_tree(proc)
                    raise InterruptedError("외부 명령 실행 중 빌드가 취소되었습니다.")
                stripped = line.rstrip("\r\n")
                if stripped:
                    captured_lines.append(stripped)
                    logd(f"    {stripped}")

            returncode = proc.wait(timeout=timeout)
            if self._is_cancelled():
                kill_process_tree(proc)
                raise InterruptedError("외부 명령 종료 중 빌드가 취소되었습니다.")
        except subprocess.TimeoutExpired:
            kill_process_tree(proc)
            proc.wait()
            raise RuntimeError(f"명령 시간 초과({timeout}s): {' '.join(cmd)}")
        finally:
            if self.cancel_token is not None and hasattr(self.cancel_token, "clear_callbacks"):
                self.cancel_token.clear_callbacks()
            if proc.poll() is None:
                kill_process_tree(proc)
            if proc.stdout:
                proc.stdout.close()

        joined_out = "\n".join(captured_lines)
        if check and returncode != 0:
            raise RuntimeError(f"명령 실패(exit={returncode}): {' '.join(cmd)}")

        return subprocess.CompletedProcess(cmd, returncode, stdout=joined_out, stderr="")

    def _iter_selected_specs(self) -> list[AppTargetSpec]:
        """선택된 대상 순서대로 일반 앱 AppTargetSpec 목록을 반환."""
        spec_by_key = {spec.key: spec for spec in BuildTargets.TARGET_SPECS}
        ordered: list[AppTargetSpec] = []
        for target_key in self.targets:
            spec = spec_by_key.get(target_key) or get_target_spec(target_key)
            if spec and not spec.is_installer and spec not in ordered:
                ordered.append(spec)
        return ordered

    def get_installer_specs_sorted(self) -> list[AppTargetSpec]:
        """인스톨러 포함 대상 목록을 ID(order) 오름차순으로 정렬하여 반환."""
        raw_targets = self.installer_config.targets
        if raw_targets is None:
            keys = list(self.targets)
        elif len(raw_targets) == 0:
            return []
        else:
            keys = BuildTargets.parse_targets(raw_targets)

        spec_by_key = {spec.key: spec for spec in BuildTargets.TARGET_SPECS}
        matched: list[AppTargetSpec] = []
        seen_keys: set[str] = set()
        for key in keys:
            spec = spec_by_key.get(key) or get_target_spec(key)
            if (
                spec
                and not spec.is_installer
                and spec.include_in_installer
                and spec.key not in seen_keys
            ):
                seen_keys.add(spec.key)
                matched.append(spec)

        return sorted(
            matched,
            key=lambda s: (int(s.order) if str(s.order).isdigit() else UNKNOWN_ORDER_SORT_KEY, s.key),
        )

    def get_installer_combo_tag(self, specs: list[AppTargetSpec] | None = None) -> str:
        """ID 낮은 순 정렬 기준 조합 식별자 생성."""
        ordered_specs = specs if specs is not None else self.get_installer_specs_sorted()
        if not ordered_specs:
            return NONE_COMBO_TAG
        return "_".join(str(spec.order) for spec in ordered_specs)

    def get_installer_artifact_name(
        self,
        main_app_version: str,
        specs: list[AppTargetSpec] | None = None,
    ) -> str:
        """조합 식별자 및 버전을 반영한 인스톨러 파일명(확장자 제외) 반환."""
        ordered_specs = specs if specs is not None else self.get_installer_specs_sorted()
        combo_tag = self.get_installer_combo_tag(ordered_specs)
        base_name = self.installer_config.name or f"{BuildTargets.PREFIX}{SETUP_SUFFIX}"
        if combo_tag == FULL_COMBO_TAG:
            return f"{base_name}_v{main_app_version}"
        return f"{base_name}_{combo_tag}_v{main_app_version}"

    def _sync_single_target_to_test(self, spec: AppTargetSpec) -> Path | None:
        """단일 앱 산출물을 <project_root>/test/<대상폴더>로 동기화."""
        resolved_exe = resolve_built_exe_path(
            project_root=self.project_root,
            target_key=spec.key,
            default_exe_name=spec.exe_name,
        )
        if not resolved_exe or not os.path.isfile(resolved_exe):
            logd(f"  • [{spec.label}] test 동기화 대상 EXE 미존재 (건너뜀): {spec.exe_name}")
            return None

        test_app_dir = Path(BuildTargets.get_test_dir(spec.key, self.project_root, create=True))
        BuildTargets.validate_app_artifact_layout(
            self.project_root,
            TEST_DIR_NAME,
            spec.key,
            test_app_dir,
        )
        dest_exe = test_app_dir / Path(resolved_exe).name
        shutil.copy2(resolved_exe, dest_exe)
        logd(f"  • [{spec.label}] test 동기화 완료: {dest_exe}")
        return dest_exe

    def step1_convert_ui_files(self, py_exe: str | None = None) -> None:
        """[Step 1] Qt Designer .ui 파일을 .py로 변환."""
        step_key = STEP_UI
        step_name = "Step 1: UI Conversion"
        self._begin_step(step_key, detail="UI 변환 확인")
        logd(f"[{step_name}] .ui 파일 변환 확인 중...")
        try:
            self._check_cancelled()
            resolved_py = py_exe or resolve_python_executable(self.project_root)
            converted, total_ui = convert_ui_files(
                project_root=self.project_root,
                src_dir=self.src_dir,
                py_exe=resolved_py,
                run_cmd_fn=self._run_cmd,
            )
            msg = f"UI check complete (converted={converted}, total_ui={total_ui})"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step2_setup_environment_and_config(self) -> tuple[str, str]:
        """[Step 2] 빌드 환경, 앱별 디렉터리 및 모드 확인."""
        step_key = STEP_ENV
        step_name = "Step 2: Environment & Mode"
        self._begin_step(step_key, detail="환경 및 모드 설정")
        logd(f"[{step_name}] 빌드 환경 및 모드 설정...")
        try:
            self._check_cancelled()
            py_exe = resolve_python_executable(self.project_root)
            os.environ[ENV_BUILD_MODE] = self.mode

            if self.clean_build:
                removed = BuildTargets.clean_output_dirs(self.project_root, include_test=True)
                for target_dir in removed:
                    logd(f"  • 기존 디렉터리 정리: {target_dir}")

            BuildTargets.ensure_all_app_dirs(self.project_root, targets=self.targets)
            msg = (
                f"mode={self.mode}, python={py_exe}, "
                f"dirs=(work={self.dir_config.work_dir_name}, dist={self.dir_config.dist_dir_name}, "
                f"release={self.dir_config.release_dir_name}, test={TEST_DIR_NAME})"
            )
            logd(f"  • {msg}")
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
            return py_exe, self.mode
        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step3_prepare_public_key_module(self) -> dict[str, Any]:
        """[Step 3] generate_public_key_module에 생성/로딩/샘플재검증을 위임하여 실행."""
        step_key = STEP_PUBKEY
        step_name = "Step 3: Public Key Module"
        self._begin_step(step_key, detail="공개키 모듈 생성 및 샘플 재검증")
        logd(f"[{step_name}] 공개키 모듈 생성, 변수 로딩 및 샘플 재검증 시작...")

        gen_script = os.path.join(self.project_root, *PUBKEY_GEN_SCRIPT_REL_PARTS)
        if not os.path.isfile(gen_script):
            gen_script = os.path.join(CURRENT_DIR, PUBKEY_GEN_SCRIPT_REL_PARTS[-1])

        try:
            self._check_cancelled()
            if not os.path.isfile(gen_script):
                raise FileNotFoundError(f"공개키 생성 스크립트를 찾을 수 없습니다: {gen_script}")

            gen_dir = str(Path(gen_script).resolve().parent)
            if gen_dir not in sys.path:
                sys.path.insert(0, gen_dir)

            import Common.Version.generate_public_key_module as pub_gen_mod  # type: ignore
            pub_gen_mod = importlib.reload(pub_gen_mod)
            info = pub_gen_mod.generate_and_verify_public_key_module(
                project_root=self.project_root,
                reverify_attempts=PUBKEY_REVERIFY_ATTEMPTS,
            )
            self.public_key_status = info

            logd(
                f"  • [step3] 생성={info['generated']} | 파일존재={info['file_exists']} | "
                f"변수({info['var_name']})로딩={info['loaded_to_var']} | path={info['py_path']}"
            )
            for item in info.get("attempts", []):
                logd(
                    f"  • [step3] 샘플 재검증 #{item['attempt']}: "
                    f"{'성공' if item['ok'] else '실패'} ({item['reason']})"
                )

            if info.get("error") or not info.get("sample_verified"):
                raise RuntimeError(info.get("error") or info.get("last_reason") or "공개키 모듈 검증 실패")

            self._check_cancelled()
            reloaded_mods = reload_pubkey_and_crypto_modules()
            logd(f"  • [step3] 모듈 리로드 완료: {reloaded_mods}")

            msg = f"Public key module verified ({Path(info['py_path']).name})"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
            return info

        except Exception as exc:
            loge(f"  ❌ [step3] 실패: {exc}")
            msg = f"실패: {exc}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step4_sync_version_and_resources(self) -> tuple[dict[str, str], dict[str, str]]:
        """[Step 4] 선택된 앱별 개별 version.txt 조회/증가 및 앱별 version_info.txt 생성."""
        step_key = STEP_VERSION
        step_name = "Step 4: Version & Resources"
        self._begin_step(step_key, detail="앱별 버전 및 리소스 생성")
        logd(f"[{step_name}] 앱별 개별 version.txt 확인/증가 및 리소스 생성...")
        try:
            self._check_cancelled()
            per_target_units = {t: self._resolve_target_bump_unit(t) for t in self.targets}
            distinct_units = {u for u in per_target_units.values() if u is not None}

            if len(distinct_units) <= 1:
                uniform_unit = next(iter(distinct_units)) if distinct_units else None
                target_versions, previous_versions = self.version_service.sync_targets(
                    targets=self.targets,
                    bump_unit=uniform_unit,
                )
            else:
                target_versions = {}
                previous_versions = {}
                for target_key in self.targets:
                    self._check_cancelled(f"대상({target_key}) 버전 동기화 중 취소되었습니다.")
                    t_ver, p_ver = self.version_service.sync_targets(
                        targets=[target_key],
                        bump_unit=per_target_units.get(target_key),
                    )
                    target_versions.update(t_ver)
                    previous_versions.update(p_ver)

            summary_str = ", ".join(
                f"{k}=v{v}(bump={per_target_units.get(k) or 'none'})"
                for k, v in target_versions.items()
            )
            msg = f"Per-app versions ready ({summary_str})"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
            return target_versions, previous_versions
        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step5_build_targets(self, py_exe: str, target_versions: dict[str, str]) -> None:
        """[Step 5] 메인 앱 및 서브 앱 구분 없이 동일한 PyInstaller 빌드 실행."""
        step_key = STEP_BUILD
        step_name = "Step 5: Build Targets"
        self._begin_step(step_key, detail="PyInstaller 빌드")
        logd(f"[{step_name}] 대상 빌드 실행: {self.targets}")
        try:
            selected_specs = self._iter_selected_specs()
            built: list[str] = []
            total_targets = max(1, len(selected_specs))

            for idx, spec_obj in enumerate(selected_specs):
                self._check_cancelled(f"대상({spec_obj.label}) 빌드 전 취소되었습니다.")
                sub_ratio = (idx + 0.2) / total_targets
                self._emit_progress(
                    self.timer.build_progress_payload(
                        step_key=step_key,
                        phase="running",
                        detail=f"빌드 중: {spec_obj.label}",
                        phase_ratio=sub_ratio,
                        is_final=False,
                    )
                )
                if self.spec_builder.build_target(spec_obj.key, py_exe, self._run_cmd):
                    built.append(spec_obj.key)

            self._check_cancelled()
            ver_summary = ", ".join(
                f"{k}=v{self.version_service.get_target_version(k, target_versions)}" for k in built
            )
            msg = f"Built targets={built} ({ver_summary})"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step6_inject_eof_encryption(self, target_versions: dict[str, str], mode: str) -> None:
        """[Step 6] 메인 앱 및 서브 앱 동일하게 EXE 메타데이터 서명/검증 + Authenticode + SHA-256 생성."""
        step_key = STEP_EOF_CRYPTO
        step_name = "Step 6: EOF Sign, Authenticode & Verify"
        self._begin_step(step_key, detail="메타데이터 서명/Authenticode/검증")
        logd(f"[{step_name}] EXE 메타데이터 전자서명, Authenticode 서명 및 검증...")
        try:
            selected_specs = self._iter_selected_specs()
            injected_count = 0

            for spec_obj in selected_specs:
                self._check_cancelled()
                app_ver = self.version_service.get_target_version(spec_obj.key, target_versions)
                resolved_exe = resolve_built_exe_path(
                    project_root=self.project_root,
                    target_key=spec_obj.key,
                    default_exe_name=spec_obj.exe_name,
                )
                if resolved_exe and os.path.isfile(resolved_exe):
                    BuildTargets.validate_app_artifact_layout(
                        self.project_root,
                        self.dir_config.dist_dir_name,
                        spec_obj.key,
                        resolved_exe,
                    )
                    inject_and_verify_exe(
                        exe_path=resolved_exe,
                        app_label=spec_obj.label,
                        app_version=app_ver,
                        mode=mode,
                        cwd=self.project_root,
                        reload_fn=reload_pubkey_and_crypto_modules,
                    )
                    injected_count += 1
                else:
                    expected_fallback = os.path.join(
                        BuildTargets.get_dist_dir(spec_obj.key, self.project_root),
                        spec_obj.exe_name,
                    )
                    logd(f"  • [{spec_obj.label}] EXE 미존재 (건너뜀): {expected_fallback}")

            msg = f"EOF signed, Authenticode & verified ({injected_count} target(s))"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step7_sync_to_test_folder(self) -> list[str]:
        """[Step 7] copy_to_test 정책이 활성화된 앱 산출물을 test 폴더로 동기화."""
        step_key = STEP_TEST_SYNC
        step_name = "Step 7: Sync to Test Folder"
        self._begin_step(step_key, detail="테스트 폴더 동기화")
        logd(f"[{step_name}] copy_to_test 정책 기준 테스트 폴더 동기화...")
        try:
            synced: list[str] = []
            for spec_obj in self._iter_selected_specs():
                self._check_cancelled()
                if not spec_obj.copy_to_test:
                    logd(f"  • [{spec_obj.label}] copy_to_test=False (건너뜀)")
                    continue
                copied = self._sync_single_target_to_test(spec_obj)
                if copied is not None:
                    synced.append(str(copied))

            msg = f"Synced {len(synced)} target(s) to {TEST_DIR_NAME}/"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
            return synced
        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step7_1_generate_and_run_app_tests(
        self,
        py_exe: str,
        target_versions: dict[str, str],
    ) -> str | None:
        """[Step 7-1] 현재 대상 앱의 pytest 스크립트 생성 및 실행."""
        step_key = STEP_APP_TEST
        step_name = "Step 7-1: App Pytest Generate & Run"
        self._begin_step(step_key, detail="앱별 pytest 스크립트 생성 및 실행")
        logd(f"[{step_name}] 앱별 pytest 스크립트 생성 및 테스트 실행...")

        try:
            self._check_cancelled()

            current_target_key = self.targets[0] if getattr(self, "targets", None) else None
            target_spec = get_target_spec(current_target_key) if current_target_key else None

            if (
                target_spec is None
                or target_spec.is_installer
                or not target_spec.copy_to_test
                or not getattr(target_spec, "run_test", True)
            ):
                msg = "현재 대상 앱이 테스트 실행 대상이 아니므로 건너뜀"
                logd(f"  • [{step_name}] {msg}")
                self._end_step(step_key, detail=msg)
                self._record_result(step_name, STATUS_SKIPPED, msg, step_key=step_key)
                return None

            synced_exe_map: dict[str, str] = {}
            test_dir = Path(BuildTargets.get_test_dir(target_spec.key, self.project_root))
            candidate_exe = test_dir / target_spec.exe_name
            if candidate_exe.is_file():
                synced_exe_map[target_spec.key] = str(candidate_exe)

            generated_files = generate_app_pytest_scripts(
                project_root=self.project_root,
                specs=[target_spec],
                target_versions=target_versions,
                synced_exe_paths=synced_exe_map,
            )

            if not generated_files:
                msg = f"[{target_spec.label}] 생성된 pytest 스크립트가 없어 건너뜀"
                logd(f"  • [{step_name}] {msg}")
                self._end_step(step_key, detail=msg)
                self._record_result(step_name, STATUS_SKIPPED, msg, step_key=step_key)
                return None

            generated_script = str(generated_files[0])

            if not getattr(self, "run_tests", False):
                msg = f"[{target_spec.label}] pytest 스크립트 생성 완료 (run_tests=False 로 실행 생략)"
                logd(f"  • [{step_name}] {msg}")
                self._end_step(step_key, detail=msg)
                self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
                return generated_script

            extra_args = list(getattr(self, "pytest_args", None) or ["-v"])
            cmd = [py_exe, "-m", "pytest", generated_script, *extra_args]

            self._check_cancelled()
            proc_res = self._run_cmd(cmd, cwd=self.project_root, check=False)
            self._check_cancelled()

            if proc_res.returncode != 0:
                tail_lines = [ln for ln in (proc_res.stdout or "").splitlines() if ln.strip()][-5:]
                tail_summary = " | ".join(tail_lines)
                fail_msg = (
                        f"[{target_spec.label}] pytest 실패 또는 미실행 (exit={proc_res.returncode})"
                        + (f" - {tail_summary}" if tail_summary else "")
                    )                
                loge(f"  ❌ [{step_name}] {fail_msg}")
                if getattr(self, "test_fail_build", True):
                    raise RuntimeError(fail_msg)
                self._end_step(step_key, detail=fail_msg)
                self._record_result(step_name, STATUS_FAILED, fail_msg, step_key=step_key)
                return generated_script

            msg = f"[{target_spec.label}] pytest 생성 및 통과 완료"

            logd(f"  • [{step_name}] {msg}")
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
            return generated_script

        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step8_create_release_artifacts(self, target_versions: dict[str, str]) -> list[str]:
        """[Step 8] 메인 앱 및 서브 앱 동일하게 개별 버전 기준 릴리스 아카이브 및 SHA-256 생성."""
        step_key = STEP_RELEASE
        step_name = "Step 8: Release Package"
        self._begin_step(step_key, detail="앱별 릴리스 패키지 생성")
        logd(f"[{step_name}] 앱별 개별 버전 릴리스 패키지 생성...")
        try:
            self._check_cancelled()
            dist_root = BuildTargets.get_dist_root(self.project_root)
            if not os.path.isdir(dist_root):
                msg = f"{self.dir_config.dist_dir_name} 디렉터리가 없어 릴리스 생성을 건너뜀"
                logd(f"  • {msg}")
                self._end_step(step_key, detail=msg)
                self._record_result(step_name, STATUS_SKIPPED, msg, step_key=step_key)
                return []

            created_releases = self.packaging_service.create_update_zips(
                specs=self._iter_selected_specs(),
                target_versions=target_versions,
            )
            if not created_releases:
                msg = "생성된 앱별 릴리스 파일이 없음"
                self._end_step(step_key, detail=msg)
                self._record_result(step_name, STATUS_SKIPPED, msg, step_key=step_key)
                return []

            names = ", ".join(os.path.basename(p) for p in created_releases)
            msg = f"Created {len(created_releases)} release artifact(s): {names}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_SUCCESS, msg, step_key=step_key)
            return created_releases
        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def step9_create_windows_installer(
        self,
        py_exe: str,
        main_app_version: str,
        is_final: bool = True,
    ) -> str | None:
        """[Step 9] 선택된 인스톨러 조합(ID 오름차순) 기준 Windows 인스톨러 생성 및 서명/검증."""
        step_key = STEP_INSTALLER
        step_name = "Step 9: Windows Installer"
        if self.skip_installer:
            msg = "skip_installer=True 로 인스톨러 생성 건너뜀"
            logd(f"[{step_name}] {msg}")
            self._begin_step(step_key, detail=msg)
            self._end_step(step_key, detail=msg, is_final=is_final)
            self._record_result(step_name, STATUS_SKIPPED, msg, step_key=step_key)
            return None

        installer_specs = self.get_installer_specs_sorted()
        combo_tag = self.get_installer_combo_tag(installer_specs)
        artifact_name = self.get_installer_artifact_name(main_app_version, installer_specs)
        ordered_labels = [s.label for s in installer_specs]

        self._begin_step(step_key, detail=f"Windows 인스톨러 생성 ({combo_tag})")
        logd(
            f"\n[{step_name}] Windows 인스톨러 생성 "
            f"(combo={combo_tag}, targets={ordered_labels}, artifact={artifact_name}, v{main_app_version})..."
        )
        try:
            self._check_cancelled()
            create_fn = getattr(self.packaging_service, "create_windows_installer")
            try:
                latest_installer, msg = create_fn(
                    main_app_version=main_app_version,
                    run_cmd_fn=self._run_cmd,
                    installer_specs=installer_specs,
                    combo_tag=combo_tag,
                    artifact_name=artifact_name,
                    installer_config=self.installer_config,
                )
            except TypeError:
                latest_installer, msg = create_fn(
                    main_app_version=main_app_version,
                    run_cmd_fn=self._run_cmd,
                )

            self._check_cancelled()
            full_msg = f"{msg} [combo={combo_tag}, name={artifact_name}]"
            self._end_step(step_key, detail=full_msg, is_final=is_final)
            self._record_result(step_name, STATUS_SUCCESS, full_msg, step_key=step_key)
            return latest_installer
        except Exception as e:
            msg = f"실패: {e}"
            self._end_step(step_key, detail=msg, is_final=is_final)
            self._record_result(step_name, STATUS_FAILED, msg, step_key=step_key)
            raise

    def run(self) -> bool:
        previous_versions: dict[str, str] = {}
        self.timer.reset()

        try:
            self._check_cancelled("빌드 시작 전 취소되었습니다.")

            if self.installer_only:
                logd("=== [--installer-only] 인스톨러 단독 생성 모드 시작 ===")
                py_exe = resolve_python_executable(self.project_root)
                installer_specs = self.get_installer_specs_sorted()
                fallback_specs = [s for s in BuildTargets.TARGET_SPECS if not s.is_installer]
                version_source_key = (
                    self.installer_config.version_source_id
                    or (
                        installer_specs[0].key
                        if installer_specs
                        else (fallback_specs[0].key if fallback_specs else MAIN_APP_OVERRIDE_NAME)
                    )
                )
                version_map = self.version_service.sync_targets(
                    targets=[s.key for s in installer_specs] or self.targets,
                    bump_unit=None,
                )[0]
                main_app_version = (
                    version_map.get(version_source_key)
                    or self.version_service.get_main_app_version(version_map)
                )
                self.step9_create_windows_installer(py_exe, main_app_version, is_final=True)
                self._check_cancelled()
                return True

            self.step1_convert_ui_files()
            py_exe, mode = self.step2_setup_environment_and_config()
            self.step3_prepare_public_key_module()
            target_versions, previous_versions = self.step4_sync_version_and_resources()
            main_app_version = self.version_service.get_main_app_version(target_versions)

            self.step5_build_targets(py_exe, target_versions)
            self.step6_inject_eof_encryption(target_versions, mode)
            self.step7_sync_to_test_folder()

            self.step7_1_generate_and_run_app_tests(py_exe, target_versions)

            self.step8_create_release_artifacts(target_versions)
            self.step9_create_windows_installer(py_exe, main_app_version, is_final=True)

            self._check_cancelled()
            logd("\n=== 전체 빌드 파이프라인 성공 완료 ===")
            return True
        except InterruptedError as ie:
            logd(f"[CANCELLED] 빌드 프로세스 취소됨: {ie}")
            if previous_versions:
                self.version_service.rollback(previous_versions)
            return False
        except Exception as e:
            if self._is_cancelled():
                logd(f"[CANCELLED] 취소 처리 중 예외 발생: {e}")
                if previous_versions:
                    self.version_service.rollback(previous_versions)
                return False
            loge(f"\n[FAILED] 빌드 프로세스 중 예외 발생: {e}")
            if previous_versions:
                self.version_service.rollback(previous_versions)
            return False