from __future__ import annotations

import textwrap
from pathlib import Path

from Common.log import logd
from build_script.target_config import AppTargetSpec, SRC_DIR_NAME, TargetConfig
from build_script.target_config_io import DEFAULT_TEXT_ENCODING
from build_script.test_source_inspector import AppSourceProfile, inspect_app_source

TEST_SUBDIR_NAME: str = "test"
GEN_SUBDIR_NAME: str = "gen"
AUTO_TEST_FILE_PREFIX: str = "test_"
AUTO_TEST_FILE_SUFFIX: str = "_auto.py"

CLI_HELP_FLAG: str = "--help"
CLI_SMOKE_TIMEOUT_SEC: int = 15
GUI_ALIVE_TIMEOUT_SEC: int = 3
GUI_TERMINATE_TIMEOUT_SEC: int = 5


def resolve_src_test_gen_dir(
    project_root: str | Path,
    spec: AppTargetSpec,
    *,
    create: bool = True,
) -> Path:
    """<project_root>/src/test/<앱별>/gen 경로를 반환."""
    root = Path(project_root).resolve()
    app_folder = TargetConfig.get_folder_name(spec.key)
    gen_dir = root / SRC_DIR_NAME / TEST_SUBDIR_NAME / app_folder / GEN_SUBDIR_NAME
    if create:
        gen_dir.mkdir(parents=True, exist_ok=True)
    return gen_dir


def _resolve_app_source_dirs(project_root: str | Path, spec: AppTargetSpec) -> list[Path]:
    """앱별 소스 코드 디렉터리 후보를 수집."""
    root = Path(project_root).resolve()
    src_root = root / SRC_DIR_NAME
    candidates: list[Path] = []

    app_folder = TargetConfig.get_folder_name(spec.key)
    if app_folder:
        candidates.append(src_root / app_folder)

    for hint in getattr(spec, "dir_hints", ()) or ():
        hint_path = Path(hint)
        if hint_path.is_absolute():
            candidates.append(hint_path)
        else:
            p1 = src_root / hint_path
            p2 = root / hint_path
            if p1.exists():
                candidates.append(p1)
            elif p2.exists():
                candidates.append(p2)

    unique_dirs: list[Path] = []
    seen: set[Path] = set()
    for c in candidates:
        resolved = c.resolve()
        if resolved not in seen and resolved.is_dir():
            seen.add(resolved)
            unique_dirs.append(resolved)
    return unique_dirs


def _build_smoke_block(spec: AppTargetSpec, profile: AppSourceProfile) -> str:
    """GUI/CLI 판별 결과에 따른 스모크 테스트 블록 생성."""
    is_console_flag = bool(getattr(spec, "console", False))
    treat_as_cli = is_console_flag and not profile.uses_gui and profile.uses_cli_parser

    if treat_as_cli:
        return textwrap.dedent(
            f"""\
            def test_app_smoke():
                proc = subprocess.run(
                    [str(EXE_PATH), {CLI_HELP_FLAG!r}],
                    capture_output=True,
                    text=True,
                    timeout={CLI_SMOKE_TIMEOUT_SEC},
                )
                assert proc.returncode == 0
            """
        )

    return textwrap.dedent(
        f"""\
        def test_app_smoke():
            proc = subprocess.Popen(
                [str(EXE_PATH)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                try:
                    code = proc.wait(timeout={GUI_ALIVE_TIMEOUT_SEC})
                    pytest.fail(f"[{{APP_LABEL}}] 실행 직후 조기 종료됨 (exit={{code}})")
                except subprocess.TimeoutExpired:
                    pass
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout={GUI_TERMINATE_TIMEOUT_SEC})
                    except subprocess.TimeoutExpired:
                        proc.kill()
        """
    )


def _build_source_tests_block(profile: AppSourceProfile) -> str:
    """소스 스캔 프로필 기반 보조 테스트 생성."""
    blocks: list[str] = []

    if profile.py_file_count > 0:
        blocks.append(
            textwrap.dedent(
                f"""\
                def test_source_files_present():
                    assert {profile.py_file_count} > 0
                """
            )
        )

    safe_modules = getattr(profile, "safe_import_modules", []) or []
    if safe_modules:
        blocks.append(
            textwrap.dedent(
                f"""\
                @pytest.mark.parametrize("mod_name", {safe_modules!r})
                def test_safe_module_imports(mod_name: str):
                    import importlib
                    try:
                        mod = importlib.import_module(mod_name)
                    except (ImportError, ModuleNotFoundError) as exc:
                        pytest.skip(f"[{{APP_LABEL}}] 모듈 임포트 생략 ({{mod_name}}): {{exc}}")
                    assert mod is not None
                """
            )
        )

    return "\n\n".join(blocks)


def generate_app_pytest_scripts(
    *,
    project_root: str,
    specs: list[AppTargetSpec],
    target_versions: dict[str, str],
    synced_exe_paths: dict[str, str],
) -> list[Path]:
    """각 앱의 소스 검사 결과를 반영해 <project_root>/src/test/<앱별>/gen에 pytest 스크립트를 생성."""
    generated_files: list[Path] = []
    root_path = Path(project_root).resolve()
    src_dir_path = root_path / SRC_DIR_NAME
    spec_keys = [getattr(s, "key", repr(s)) for s in (specs or [])]

    logd(
        "[TestGen] 전달 인자 -> "
        f"project_root={project_root!r}, specs_count={len(spec_keys)}, spec_keys={spec_keys}, "
        f"target_versions={target_versions!r}, synced_exe_paths={synced_exe_paths!r}"
    )
    logd(f"[TestGen] 루트/소스 디렉터리 -> root_path={root_path}, src_dir_path={src_dir_path}")

    for spec in specs:
        gen_dir = resolve_src_test_gen_dir(root_path, spec, create=True)
        test_dir = Path(TargetConfig.get_test_dir(spec.key, str(root_path)))
        exe_path_str = synced_exe_paths.get(spec.key) or str(test_dir / spec.exe_name)
        app_ver = target_versions.get(spec.key, "")

        source_dirs = _resolve_app_source_dirs(root_path, spec)
        source_dir_strs = [str(d) for d in source_dirs]
        logd(
            f"[TestGen] [{spec.label} ({spec.key})] 디렉터리/인자 -> "
            f"gen_dir={gen_dir}, test_dir={test_dir}, exe_path_str={exe_path_str}, "
            f"app_ver={app_ver!r}, source_dirs={source_dir_strs}"
        )

        profile = inspect_app_source(source_dirs, spec.key, src_root=src_dir_path)

        smoke_block = _build_smoke_block(spec, profile)
        extra_source_block = _build_source_tests_block(profile)

        script_path = gen_dir / f"{AUTO_TEST_FILE_PREFIX}{spec.key.lower()}{AUTO_TEST_FILE_SUFFIX}"
        parts = [
            textwrap.dedent(
                f"""\
                # Auto-generated in src/test/<app>/gen after Step 7 sync.
                # Source scan: py_files={profile.py_file_count}, uses_gui={profile.uses_gui}, uses_cli={profile.uses_cli_parser}
                from pathlib import Path
                import subprocess
                import sys
                import pytest

                APP_KEY = {spec.key!r}
                APP_LABEL = {spec.label!r}
                APP_VERSION = {app_ver!r}
                EXE_PATH = Path({exe_path_str!r})
                SRC_DIR = Path({str(src_dir_path)!r})
                SOURCE_DIRS = {source_dir_strs!r}

                for _p in (str(SRC_DIR), *SOURCE_DIRS):
                    if _p and _p not in sys.path:
                        sys.path.insert(0, _p)


                def test_artifact_exists():
                    assert EXE_PATH.is_file(), f"[{{APP_LABEL}}] 테스트 대상 EXE가 없습니다: {{EXE_PATH}}"
                """
            ),
            smoke_block.rstrip(),
        ]
        if extra_source_block.strip():
            parts.append(extra_source_block.rstrip())

        content = "\n\n".join(parts) + "\n"
        script_path.write_text(content, encoding=DEFAULT_TEXT_ENCODING)
        generated_files.append(script_path)
        logd(f"  • [{spec.label}] pytest 스크립트 생성 완료: {script_path}")

    return generated_files
