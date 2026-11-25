"""
릴리스 아카이브 및 Windows 인스톨러 패키징 서비스 (packaging_service.py)
"""

from __future__ import annotations

import os
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Any, Callable

from Common.Version.exe_version_crypto import sign_exe_authenticode
from Common.log import logd
from build_script.artifact_signing import write_sha256_file
from build_script.target_config import (
    AppTargetSpec,
    BuildDirConfig,
    EXE_EXTENSION,
    INSTALLER_TARGET_KEY,
    TargetConfig,
    UNKNOWN_ORDER_SORT_KEY,
)
from build_script.target_config_io import InstallerBuildConfig
from build_script.version_service import VersionService

MODE_PRODUCTION: str = "production"
ARCHIVE_EXTENSION: str = ".zip"
SHA256_EXTENSION: str = ".sha256"
ISS_EXTENSION: str = ".iss"
NONE_COMBO_TAG: str = "none"

EXPLICIT_ISS_FILENAMES: tuple[str, ...] = (
    "installer.iss",
    "PrintShopApp_Setup.iss",
)

ISCC_EXECUTABLE_NAMES: tuple[str, ...] = (
    "ISCC.exe",
    "ISCC",
    "iscc.exe",
    "iscc",
)

ISCC_RELATIVE_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("Programs", "Inno Setup 6", "ISCC.exe"),
    ("Inno Setup 6", "ISCC.exe"),
    ("Inno Setup 5", "ISCC.exe"),
)

__all__ = [
    "ARCHIVE_EXTENSION",
    "EXPLICIT_ISS_FILENAMES",
    "ISCC_EXECUTABLE_NAMES",
    "ISCC_RELATIVE_CANDIDATES",
    "ISS_EXTENSION",
    "MODE_PRODUCTION",
    "NONE_COMBO_TAG",
    "PackagingService",
    "SHA256_EXTENSION",
]


class PackagingService:
    def __init__(
        self,
        project_root: str,
        dir_config: BuildDirConfig,
        version_service: VersionService,
        mode: str = MODE_PRODUCTION,
        cancel_event: threading.Event | None = None,
        cancel_token: Any | None = None,
    ):
        self.project_root = os.path.abspath(project_root)
        self.dir_config = dir_config
        self.version_service = version_service
        self.mode = mode
        self.cancel_token = cancel_token
        self.cancel_event: threading.Event | None = (
            getattr(cancel_token, "event", None) if cancel_token is not None else cancel_event
        )

    def _check_cancelled(self, reason: str = "사용자에 의해 패키징이 취소되었습니다.") -> None:
        token_set = bool(self.cancel_token is not None and getattr(self.cancel_token, "is_set", False))
        event_set = bool(self.cancel_event is not None and self.cancel_event.is_set())
        if token_set or event_set:
            raise InterruptedError(reason)

    @staticmethod
    def compute_full_combo_tag() -> str:
        all_includable = sorted(
            [
                spec
                for spec in TargetConfig.TARGET_SPECS
                if not spec.is_installer and spec.include_in_installer
            ],
            key=lambda s: (int(s.order) if str(s.order).isdigit() else UNKNOWN_ORDER_SORT_KEY, s.key),
        )
        if not all_includable:
            return NONE_COMBO_TAG
        return "_".join(str(spec.order) for spec in all_includable)

    def _build_artifact_base_name(
        self,
        main_label: str,
        main_app_version: str,
        combo_tag: str | None = None,
        artifact_name: str | None = None,
        full_combo_tag: str | None = None,
    ) -> str:
        resolved_full_tag = full_combo_tag or self.compute_full_combo_tag()
        if artifact_name and artifact_name.strip():
            base = artifact_name.strip()
        elif combo_tag and combo_tag != NONE_COMBO_TAG and combo_tag != resolved_full_tag:
            base = f"{main_label}_{combo_tag}_v{main_app_version}_Setup"
        else:
            base = f"{main_label}_v{main_app_version}_Setup"

        if self.mode != MODE_PRODUCTION and f"_{self.mode}" not in base:
            return f"{base}_{self.mode}"
        return base

    def _collect_inno_spec_defines(self, ordered_specs: list[AppTargetSpec]) -> list[str]:
        """각 AppTargetSpec.inno 세부 설정을 ISCC /D 매크로 인자 목록으로 변환."""
        defines: list[str] = []
        all_components: list[str] = []
        all_tasks: list[str] = []

        for spec in ordered_specs:
            inno = getattr(spec, "inno", None)
            if inno is None:
                continue

            prefix = f"App_{spec.key}"
            if inno.install_subdir:
                defines.append(f"/D{prefix}_InstallSubdir={inno.install_subdir}")
            if inno.excludes:
                defines.append(f"/D{prefix}_Excludes={inno.excludes}")
            if inno.flags:
                defines.append(f"/D{prefix}_Flags={','.join(inno.flags)}")
            if inno.components:
                defines.append(f"/D{prefix}_Components={','.join(inno.components)}")
                for comp in inno.components:
                    if comp not in all_components:
                        all_components.append(comp)
            if inno.tasks:
                defines.append(f"/D{prefix}_Tasks={','.join(inno.tasks)}")
                for task in inno.tasks:
                    if task not in all_tasks:
                        all_tasks.append(task)
            for k, v in (inno.extra_defines or {}).items():
                clean_k = str(k).strip()
                if clean_k and v is not None:
                    defines.append(f"/D{clean_k}={v}")

        if all_components:
            defines.append(f"/DInstallerComponents={','.join(all_components)}")
        if all_tasks:
            defines.append(f"/DInstallerTasks={','.join(all_tasks)}")
        return defines

    def create_release_archives(
        self,
        specs: list[AppTargetSpec],
        target_versions: dict[str, str],
    ) -> list[str]:
        self._check_cancelled("릴리스 패키지 생성 시작 전 취소되었습니다.")
        dist_root = TargetConfig.get_dist_root(self.project_root)
        if not os.path.isdir(dist_root):
            return []

        created_releases: list[str] = []
        for spec in specs:
            self._check_cancelled(f"[{spec.label}] 릴리스 패키지 생성 중 취소되었습니다.")
            app_dist_dir = TargetConfig.get_dist_dir(spec.key, self.project_root)
            TargetConfig.validate_app_artifact_layout(
                self.project_root,
                self.dir_config.dist_dir_name,
                spec.key,
                app_dist_dir,
            )

            if not os.path.isdir(app_dist_dir):
                logd(
                    f"  • [{spec.label}] {self.dir_config.dist_dir_name}/"
                    f"{TargetConfig.get_folder_name(spec.key)} 폴더가 없어 릴리스 생성을 건너뜀"
                )
                continue

            app_release_dir = TargetConfig.get_release_dir(spec.key, self.project_root, create=True)
            TargetConfig.validate_app_artifact_layout(
                self.project_root,
                self.dir_config.release_dir_name,
                spec.key,
                app_release_dir,
            )

            app_ver = self.version_service.get_target_version(spec.key, target_versions)
            archive_name = (
                f"{spec.label}_{self.mode}_v{app_ver}{ARCHIVE_EXTENSION}"
                if self.mode != MODE_PRODUCTION
                else f"{spec.label}_v{app_ver}{ARCHIVE_EXTENSION}"
            )
            release_zip_path = os.path.join(app_release_dir, archive_name)
            TargetConfig.validate_app_artifact_layout(
                self.project_root,
                self.dir_config.release_dir_name,
                spec.key,
                release_zip_path,
            )

            file_count = 0
            with zipfile.ZipFile(release_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(app_dist_dir):
                    for fn in files:
                        if fn.endswith(SHA256_EXTENSION):
                            continue
                        full_p = os.path.join(root, fn)
                        rel_p = os.path.relpath(full_p, app_dist_dir)
                        zf.write(full_p, rel_p)
                        file_count += 1

            sha_hex = write_sha256_file(release_zip_path)
            created_releases.append(release_zip_path)

            archive_flag = getattr(spec, "copy_to_archive", True)
            logd(
                f"  • [{spec.label}] 릴리스 패키지 생성 완료: {release_zip_path} "
                f"(files={file_count}, copy_to_archive={archive_flag}, "
                f"sha256={sha_hex[:12] if sha_hex else 'none'})"
            )

        return created_releases

    def create_update_zips(
        self,
        specs: list[AppTargetSpec],
        target_versions: dict[str, str],
    ) -> list[str]:
        """기존 호출부 호환용 래퍼."""
        return self.create_release_archives(specs=specs, target_versions=target_versions)

    @staticmethod
    def find_iscc_executable() -> str | None:
        for name in ISCC_EXECUTABLE_NAMES:
            found = shutil.which(name)
            if found and os.path.isfile(found):
                return found

        base_roots: list[str] = []
        for env_key in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"):
            val = os.environ.get(env_key)
            if val and val.strip():
                base_roots.append(val.strip())
        local_fallback = os.path.expanduser(r"~\AppData\Local")
        if local_fallback and local_fallback not in base_roots:
            base_roots.append(local_fallback)

        for root_dir in base_roots:
            for rel_parts in ISCC_RELATIVE_CANDIDATES:
                candidate = os.path.join(root_dir, *rel_parts)
                if os.path.isfile(candidate):
                    return candidate
        return None

    def find_iss_script(self, installer_dir: str) -> str | None:
        install_root = TargetConfig.get_install_root(self.project_root)
        release_root = TargetConfig.get_release_root(self.project_root)
        search_dirs: list[str] = []
        for d in (self.project_root, installer_dir, install_root, release_root):
            if d and d not in search_dirs:
                search_dirs.append(d)

        for d in search_dirs:
            for fn in EXPLICIT_ISS_FILENAMES:
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    return p

        iss_files: list[str] = []
        for search_root in search_dirs:
            if os.path.isdir(search_root):
                for fn in os.listdir(search_root):
                    if fn.lower().endswith(ISS_EXTENSION):
                        full_p = os.path.join(search_root, fn)
                        if os.path.isfile(full_p):
                            iss_files.append(full_p)

        return max(iss_files, key=os.path.getmtime) if iss_files else None

    def _sync_installer_to_dist_and_release(
        self,
        installer_key: str,
        installer_exe_path: str,
    ) -> tuple[str, str]:
        """인스톨러 EXE 및 SHA-256 파일을 인스톨러 저장 경로(install_dir)와 dist 인스톨러 폴더 양쪽에 저장."""
        install_root_name = TargetConfig.get_install_root_name(self.project_root)
        release_dir = TargetConfig.get_install_dir(installer_key, self.project_root, create=True)
        dist_dir = TargetConfig.get_installer_dist_dir(installer_key, self.project_root, create=True)

        TargetConfig.validate_app_artifact_layout(
            self.project_root,
            install_root_name,
            installer_key,
            release_dir,
        )
        TargetConfig.validate_app_artifact_layout(
            self.project_root,
            self.dir_config.dist_dir_name,
            installer_key,
            dist_dir,
        )

        src_exe = Path(installer_exe_path).resolve()
        release_exe = Path(release_dir) / src_exe.name
        if src_exe != release_exe:
            shutil.copy2(src_exe, release_exe)

        sign_exe_authenticode(str(release_exe), cwd=self.project_root)
        release_sha = write_sha256_file(str(release_exe))

        dist_exe = Path(dist_dir) / src_exe.name
        shutil.copy2(release_exe, dist_exe)

        if release_sha and os.path.isfile(release_sha):
            shutil.copy2(release_sha, Path(dist_dir) / Path(release_sha).name)
        else:
            write_sha256_file(str(dist_exe))

        logd(f"  • 인스톨러 release/install 저장 완료: {release_exe}")
        logd(f"  • 인스톨러 dist 저장 완료: {dist_exe}")
        return str(release_exe), str(dist_exe)

    def create_windows_installer(
        self,
        main_app_version: str,
        run_cmd_fn: Callable[..., Any],
        installer_specs: list[AppTargetSpec] | None = None,
        combo_tag: str | None = None,
        artifact_name: str | None = None,
        installer_config: InstallerBuildConfig | None = None,
        full_combo_tag: str | None = None,
    ) -> tuple[str | None, str]:
        self._check_cancelled("인스톨러 생성 시작 전 취소되었습니다.")
        main_key = self.version_service.resolve_main_target_key()
        main_label = TargetConfig.get_label(main_key)
        main_dist_dir = TargetConfig.get_dist_dir(main_key, self.project_root)

        installer_key = INSTALLER_TARGET_KEY if INSTALLER_TARGET_KEY in TargetConfig.BY_KEY else main_key
        install_root_name = TargetConfig.get_install_root_name(self.project_root)
        installer_dir = TargetConfig.get_install_dir(installer_key, self.project_root, create=True)
        installer_folder_name = TargetConfig.get_folder_name(installer_key)

        TargetConfig.validate_app_artifact_layout(
            self.project_root,
            self.dir_config.dist_dir_name,
            main_key,
            main_dist_dir,
        )
        TargetConfig.validate_app_artifact_layout(
            self.project_root,
            install_root_name,
            installer_key,
            installer_dir,
        )

        ordered_specs = list(installer_specs) if installer_specs is not None else []
        effective_combo = combo_tag or (
            "_".join(str(s.order) for s in ordered_specs) if ordered_specs else NONE_COMBO_TAG
        )
        target_labels_str = ",".join(s.label for s in ordered_specs)
        target_keys_str = ",".join(s.key for s in ordered_specs)
        out_base_name = self._build_artifact_base_name(
            main_label=main_label,
            main_app_version=main_app_version,
            combo_tag=effective_combo,
            artifact_name=artifact_name,
            full_combo_tag=full_combo_tag,
        )

        iss_path = self.find_iss_script(installer_dir)
        iscc = self.find_iscc_executable()

        if iss_path and iscc:
            logd(f"  • ISS 스크립트 검출: {iss_path}")
            logd(f"  • ISCC 컴파일러 검출: {iscc}")
            logd(
                f"  • 인스톨러 조합 정보: combo={effective_combo}, "
                f"targets={target_keys_str or 'default'}, out={out_base_name}, dir={installer_dir}"
            )
            inno_spec_defines = self._collect_inno_spec_defines(ordered_specs)
            extra_cfg_defines: list[str] = []
            if installer_config and getattr(installer_config, "extra", None):
                for ek, ev in installer_config.extra.items():
                    if str(ek).strip() and ev is not None:
                        extra_cfg_defines.append(f"/D{str(ek).strip()}={ev}")

            cmd = [
                iscc,
                f"/DSourceDir={self.project_root}",
                f"/DAppDistDir={main_dist_dir}",
                f"/DDistRoot={TargetConfig.get_dist_root(self.project_root)}",
                f"/DAppVersion={main_app_version}",
                f"/DOutputDir={installer_dir}",
                f"/DOutputBaseFilename={out_base_name}",
                f"/DInstallerCombo={effective_combo}",
                f"/DInstallerTargets={target_keys_str}",
                f"/DInstallerLabels={target_labels_str}",
                *inno_spec_defines,
                *extra_cfg_defines,
                iss_path,
            ]
            run_cmd_fn(cmd, cwd=self.project_root)
        else:
            reasons = []
            if not iss_path:
                reasons.append(f"{ISS_EXTENSION} 스크립트 미검출")
            if not iscc:
                reasons.append(f"{ISCC_EXECUTABLE_NAMES[0]} 미검출")
            logd(f"  • Inno Setup 컴파일 생략 ({', '.join(reasons)}): 기존 인스톨러 산출물 확인으로 진행")

        self._check_cancelled("인스톨러 서명 및 해시 생성 전 취소되었습니다.")
        created_installers = [
            os.path.join(installer_dir, f)
            for f in os.listdir(installer_dir)
            if f.lower().endswith(EXE_EXTENSION)
        ]
        latest_installer = max(created_installers, key=os.path.getmtime) if created_installers else None
        if latest_installer:
            TargetConfig.validate_app_artifact_layout(
                self.project_root,
                install_root_name,
                installer_key,
                latest_installer,
            )
            release_exe_path, dist_exe_path = self._sync_installer_to_dist_and_release(
                installer_key=installer_key,
                installer_exe_path=latest_installer,
            )
            return (
                release_exe_path,
                f"Installer ready in {install_root_name} & dist: {os.path.basename(release_exe_path)} "
                f"(v{main_app_version}, combo={effective_combo}, dist={os.path.dirname(dist_exe_path)})",
            )

        return None, (
            f"Installer step completed (no {EXE_EXTENSION} artifact in "
            f"{install_root_name}/{installer_folder_name}/)"
        )