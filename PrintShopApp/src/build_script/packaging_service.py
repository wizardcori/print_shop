# src/build_script/packaging_service.py
from __future__ import annotations

import os
import shutil
import threading
import zipfile
from typing import Any, Callable

from artifact_signing import write_sha256_file
from build_targets import AppTargetSpec, BuildDirConfig, BuildTargets
from Common.log import logd
from Common.Version.exe_version_crypto import sign_exe_authenticode
from target_config_io import InstallerBuildConfig
from version_service import VersionService


class PackagingService:
    def __init__(
        self,
        project_root: str,
        dir_config: BuildDirConfig,
        version_service: VersionService,
        mode: str = "production",
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

    def _build_artifact_base_name(
        self,
        main_label: str,
        main_app_version: str,
        combo_tag: str | None = None,
        artifact_name: str | None = None,
    ) -> str:
        if artifact_name and artifact_name.strip():
            base = artifact_name.strip()
        elif combo_tag and combo_tag != "none" and combo_tag != "1_2_3_4_5":
            base = f"{main_label}_{combo_tag}_v{main_app_version}_Setup"
        else:
            base = f"{main_label}_v{main_app_version}_Setup"

        if self.mode != "production" and f"_{self.mode}" not in base:
            return f"{base}_{self.mode}"
        return base

    def create_release_archives(
        self,
        specs: list[AppTargetSpec],
        target_versions: dict[str, str],
    ) -> list[str]:
        self._check_cancelled("릴리스 패키지 생성 시작 전 취소되었습니다.")
        dist_root = BuildTargets.get_dist_root(self.project_root)
        if not os.path.isdir(dist_root):
            return []

        created_releases: list[str] = []
        for spec in specs:
            self._check_cancelled(f"[{spec.label}] 릴리스 패키지 생성 중 취소되었습니다.")
            app_dist_dir = BuildTargets.get_dist_dir(spec.key, self.project_root)
            BuildTargets.validate_app_artifact_layout(
                self.project_root,
                self.dir_config.dist_dir_name,
                spec.key,
                app_dist_dir,
            )

            if not os.path.isdir(app_dist_dir):
                logd(
                    f"  • [{spec.label}] {self.dir_config.dist_dir_name}/"
                    f"{BuildTargets.get_folder_name(spec.key)} 폴더가 없어 릴리스 생성을 건너뜀"
                )
                continue

            app_release_dir = BuildTargets.get_release_dir(spec.key, self.project_root, create=True)
            BuildTargets.validate_app_artifact_layout(
                self.project_root,
                self.dir_config.release_dir_name,
                spec.key,
                app_release_dir,
            )

            app_ver = self.version_service.get_target_version(spec.key, target_versions)
            archive_name = (
                f"{spec.label}_{self.mode}_v{app_ver}.zip"
                if self.mode != "production"
                else f"{spec.label}_v{app_ver}.zip"
            )
            release_zip_path = os.path.join(app_release_dir, archive_name)
            BuildTargets.validate_app_artifact_layout(
                self.project_root,
                self.dir_config.release_dir_name,
                spec.key,
                release_zip_path,
            )

            file_count = 0
            with zipfile.ZipFile(release_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(app_dist_dir):
                    for fn in files:
                        if fn.endswith(".sha256"):
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
        for name in ("ISCC.exe", "ISCC", "iscc.exe", "iscc"):
            found = shutil.which(name)
            if found and os.path.isfile(found):
                return found

        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        candidate_paths = [
            os.path.join(local_app_data, "Programs", "Inno Setup 6", "ISCC.exe"),
            r"C:\Users\hwlee\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
            r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
            r"C:\Program Files\Inno Setup 5\ISCC.exe",
        ]
        for path in candidate_paths:
            if path and os.path.isfile(path):
                return path
        return None

    def find_iss_script(self, installer_dir: str) -> str | None:
        install_root = BuildTargets.get_install_root(self.project_root)
        search_dirs: list[str] = [self.project_root, installer_dir]
        if install_root not in search_dirs:
            search_dirs.append(install_root)

        explicit_candidates: list[str] = []
        for d in search_dirs:
            explicit_candidates.extend(
                [
                    os.path.join(d, "installer.iss"),
                    os.path.join(d, "PrintShopApp_Setup.iss"),
                ]
            )
        for p in explicit_candidates:
            if os.path.isfile(p):
                return p

        iss_files: list[str] = []
        for search_root in search_dirs:
            if os.path.isdir(search_root):
                for fn in os.listdir(search_root):
                    if fn.lower().endswith(".iss"):
                        full_p = os.path.join(search_root, fn)
                        if os.path.isfile(full_p):
                            iss_files.append(full_p)

        return max(iss_files, key=os.path.getmtime) if iss_files else None

    def create_windows_installer(
        self,
        main_app_version: str,
        run_cmd_fn: Callable[..., Any],
        installer_specs: list[AppTargetSpec] | None = None,
        combo_tag: str | None = None,
        artifact_name: str | None = None,
        installer_config: InstallerBuildConfig | None = None,
    ) -> tuple[str | None, str]:
        self._check_cancelled("인스톨러 생성 시작 전 취소되었습니다.")
        main_key = self.version_service.resolve_main_target_key()
        main_label = BuildTargets.get_label(main_key)
        main_dist_dir = BuildTargets.get_dist_dir(main_key, self.project_root)
        installer_dir = BuildTargets.get_install_dir(main_key, self.project_root, create=True)

        BuildTargets.validate_app_artifact_layout(
            self.project_root,
            self.dir_config.dist_dir_name,
            main_key,
            main_dist_dir,
        )
        BuildTargets.validate_app_artifact_layout(
            self.project_root,
            self.dir_config.install_dir_name,
            main_key,
            installer_dir,
        )

        ordered_specs = list(installer_specs) if installer_specs is not None else []
        effective_combo = combo_tag or (
            "_".join(str(s.order) for s in ordered_specs) if ordered_specs else "none"
        )
        target_labels_str = ",".join(s.label for s in ordered_specs)
        target_keys_str = ",".join(s.key for s in ordered_specs)
        out_base_name = self._build_artifact_base_name(
            main_label=main_label,
            main_app_version=main_app_version,
            combo_tag=effective_combo,
            artifact_name=artifact_name,
        )

        iss_path = self.find_iss_script(installer_dir)
        iscc = self.find_iscc_executable()

        if iss_path and iscc:
            logd(f"  • ISS 스크립트 검출: {iss_path}")
            logd(f"  • ISCC 컴파일러 검출: {iscc}")
            logd(
                f"  • 인스톨러 조합 정보: combo={effective_combo}, "
                f"targets={target_keys_str or 'default'}, out={out_base_name}"
            )
            cmd = [
                iscc,
                f"/DSourceDir={self.project_root}",
                f"/DAppDistDir={main_dist_dir}",
                f"/DDistRoot={BuildTargets.get_dist_root(self.project_root)}",
                f"/DAppVersion={main_app_version}",
                f"/DOutputDir={installer_dir}",
                f"/DOutputBaseFilename={out_base_name}",
                f"/DInstallerCombo={effective_combo}",
                f"/DInstallerTargets={target_keys_str}",
                f"/DInstallerLabels={target_labels_str}",
                iss_path,
            ]
            run_cmd_fn(cmd, cwd=self.project_root)
        else:
            reasons = []
            if not iss_path:
                reasons.append(".iss 스크립트 미검출")
            if not iscc:
                reasons.append("ISCC.exe 미검출")
            logd(f"  • Inno Setup 컴파일 생략 ({', '.join(reasons)}): 기존 인스톨러 산출물 확인으로 진행")

        self._check_cancelled("인스톨러 서명 및 해시 생성 전 취소되었습니다.")
        created_installers = [
            os.path.join(installer_dir, f)
            for f in os.listdir(installer_dir)
            if f.lower().endswith(".exe")
        ]
        latest_installer = max(created_installers, key=os.path.getmtime) if created_installers else None
        if latest_installer:
            BuildTargets.validate_app_artifact_layout(
                self.project_root,
                self.dir_config.install_dir_name,
                main_key,
                latest_installer,
            )
            sign_exe_authenticode(latest_installer, cwd=self.project_root)
            write_sha256_file(latest_installer)
            if installer_config and getattr(installer_config, "extra", None):
                logd(f"  • installer extra 옵션: {installer_config.extra}")
            return (
                latest_installer,
                f"Installer ready: {os.path.basename(latest_installer)} "
                f"(v{main_app_version}, combo={effective_combo})",
            )

        return None, (
            f"Installer step completed (no .exe artifact in "
            f"{self.dir_config.install_dir_name}/{main_label}/)"
        )