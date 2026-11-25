from __future__ import annotations

import os
from typing import Any

from build_script.target_config import TargetConfig, MAIN_APP_OVERRIDE_NAME, get_target_spec
from Common.log import logd, loge
from Common.Version.exe_version_crypto import generate_win_version_info


class VersionService:
    def __init__(self, project_root: str, target_helpers: dict[str, Any] | None = None):
        self.project_root = os.path.abspath(project_root)
        self.target_helpers = target_helpers or {}

    def get_version_files(self, target_key: str) -> list[str]:
        fn = self.target_helpers.get("get_version_files")
        if callable(fn):
            return list(fn(target_key))
        return TargetConfig.get_version_files(target_key, project_root=self.project_root)

    @staticmethod
    def read_version(ver_file: str) -> str:
        if ver_file and os.path.isfile(ver_file):
            with open(ver_file, "r", encoding="utf-8-sig") as f:
                val = f.read().strip()
                if val:
                    return val
        return "1.0.0"

    @staticmethod
    def write_version(ver_file: str, version_str: str) -> str:
        ver_clean = version_str.strip()
        os.makedirs(os.path.dirname(ver_file), exist_ok=True)
        with open(ver_file, "w", encoding="utf-8") as f:
            f.write(f"{ver_clean}\n")
        return ver_clean

    @staticmethod
    def bump_version_str(current_version: str, unit: str = "patch") -> str:
        parts = [int(x) for x in current_version.split(".") if x.isdigit()]
        while len(parts) < 3:
            parts.append(0)
        major, minor, patch = parts[0], parts[1], parts[2]
        if unit == "major":
            return f"{major + 1}.0.0"
        if unit == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"

    def get_target_version(self, target_key: str, target_versions: dict[str, str] | None = None) -> str:
        if target_versions and target_key in target_versions and target_versions[target_key]:
            return target_versions[target_key]
        ver_files = self.get_version_files(target_key)
        if ver_files:
            return self.read_version(ver_files[0])
        return "1.0.0"

    @staticmethod
    def resolve_main_target_key() -> str:
        ordered = TargetConfig.ordered_keys()
        for candidate in (MAIN_APP_OVERRIDE_NAME, "PrintShopApp", "App", "main_app"):
            if candidate in ordered:
                return candidate
        return ordered[0] if ordered else MAIN_APP_OVERRIDE_NAME

    def get_main_app_version(self, target_versions: dict[str, str] | None = None) -> str:
        main_key = self.resolve_main_target_key()
        for candidate_key in (main_key, MAIN_APP_OVERRIDE_NAME, "PrintShopApp", "App", "main_app"):
            if target_versions and candidate_key in target_versions and target_versions[candidate_key]:
                return target_versions[candidate_key]
            ver_files = self.get_version_files(candidate_key)
            if ver_files:
                return self.read_version(ver_files[0])
        if target_versions:
            return next(iter(target_versions.values()), "1.0.0")
        return "1.0.0"

    def sync_targets(self, targets: list[str], bump_unit: str | None) -> tuple[dict[str, str], dict[str, str]]:
        target_versions: dict[str, str] = {}
        previous_versions: dict[str, str] = {}

        for target_key in targets:
            spec = get_target_spec(target_key)
            label = spec.label if spec else target_key
            ver_files = self.get_version_files(target_key)
            if not ver_files:
                raise FileNotFoundError(f"[{label}] version_rel_paths가 정의되지 않았습니다.")

            primary_file = ver_files[0]
            cur_ver = self.read_version(primary_file)

            if bump_unit:
                previous_versions[primary_file] = cur_ver
                next_ver = self.bump_version_str(cur_ver, bump_unit)
                for vf in ver_files:
                    self.write_version(vf, next_ver)
                target_versions[target_key] = next_ver
                logd(f"  • [{label}] 버전 증가 ({bump_unit}): v{cur_ver} -> v{next_ver} ({primary_file})")
            else:
                for vf in ver_files:
                    self.write_version(vf, cur_ver)
                target_versions[target_key] = cur_ver
                logd(f"  • [{label}] 현재 버전 유지: v{cur_ver} ({primary_file})")

            rc_file = os.path.join(os.path.dirname(primary_file), "version_info.txt")
            generate_win_version_info(target_versions[target_key], output_path=rc_file, app_name=label)
            logd(f"  • [{label}] 리소스 파일 생성 완료: {rc_file}")

        return target_versions, previous_versions

    def rollback(self, previous_versions: dict[str, str]) -> None:
        for ver_file, prev_ver in previous_versions.items():
            try:
                self.write_version(ver_file, prev_ver)
                logd(f"  ↩️ 버전 롤백 완료 ({ver_file}): v{prev_ver}")
            except Exception as rb_err:
                loge(f"  ⚠️ 버전 롤백 중 오류 발생 ({ver_file}): {rb_err}")
# ```

# `packaging_service.py`도 함께 올려주시면 `copy_to_archive` 정책과 ID 오름차순 인스톨러 조합(`installer_specs`, `combo_tag`, `artifact_name`) 생성 부분까지 연결해 드릴 수 있습니다.