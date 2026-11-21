from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_targets import BuildDirConfig, BuildTargets


class BuildArchiveManager:
    """각 앱의 빌드 산출물을 버전별로 아카이빙하고 이력·복원을 관리하는 클래스."""

    ARCHIVE_ROOT_DIR_NAME: str = "build_archive"
    DIST_DIR_NAME: str = "dist"
    INDEX_FILE_NAME: str = "index.json"
    MANIFEST_FILE_NAME: str = "build_manifest.json"
    TIMINGS_FILE_NAME: str = "build_step_timings.json"

    VERSION_PREFIX: str = "v"
    BUILD_PREFIX: str = "b"
    BUILD_ID_SEPARATOR: str = "_"
    BUILD_TIMESTAMP_FORMAT: str = "%Y%m%d_%H%M%S"
    ISO_TIME_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"
    UNKNOWN_VALUE: str = "unknown"

    MODE_PRODUCTION: str = "production"
    MODE_DEVELOPMENT: str = "development"
    MODE_TAG_MAP: dict[str, str] = {
        MODE_PRODUCTION: "prod",
        MODE_DEVELOPMENT: "dev",
    }

    DEFAULT_KEEP_VERSIONS: int = 15
    DEFAULT_KEEP_BUILDS_PER_VERSION: int = 5
    HASH_CHUNK_SIZE: int = 1024 * 1024
    JSON_INDENT: int = 2
    JSON_ENCODING: str = "utf-8"

    KEY_APP_KEY: str = "app_key"
    KEY_APP_NAME: str = "app_name"
    KEY_VERSION: str = "version"
    KEY_BUMP_UNIT: str = "bump_unit"
    KEY_MODE: str = "mode"
    KEY_BUILT_AT_UTC: str = "built_at_utc"
    KEY_BUILT_BY: str = "built_by"
    KEY_GIT_COMMIT: str = "git_commit"
    KEY_CLEAN_BUILD: str = "clean_build"
    KEY_EXE: str = "exe"

    KEY_FILENAME: str = "filename"
    KEY_SOURCE_PATH: str = "source_path"
    KEY_ARCHIVE_PATH: str = "archive_path"
    KEY_RELATIVE_ARCHIVE_PATH: str = "relative_archive_path"
    KEY_SIZE_BYTES: str = "size_bytes"
    KEY_SHA256: str = "sha256"

    KEY_UPDATED_AT_UTC: str = "updated_at_utc"
    KEY_LATEST_VERSION: str = "latest_version"
    KEY_LATEST_BUILD_ID: str = "latest_build_id"
    KEY_BUILDS: str = "builds"
    KEY_BUILD_ID: str = "build_id"
    KEY_VERSION_DIR: str = "version_dir"
    KEY_BUILD_DIR: str = "build_dir"

    def __init__(
        self,
        project_root: str | Path,
        keep_versions: int = DEFAULT_KEEP_VERSIONS,
        keep_builds_per_version: int = DEFAULT_KEEP_BUILDS_PER_VERSION,
        dir_config: BuildDirConfig | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.dir_config = dir_config
        archive_name = (
            dir_config.release_dir_name
            if dir_config and dir_config.release_dir_name
            else self.ARCHIVE_ROOT_DIR_NAME
        )
        dist_name = (
            dir_config.dist_dir_name
            if dir_config and dir_config.dist_dir_name
            else self.DIST_DIR_NAME
        )
        self.archive_root = self.project_root / archive_name
        self.dist_root = self.project_root / dist_name
        self.keep_versions = max(1, int(keep_versions))
        self.keep_builds_per_version = max(1, int(keep_builds_per_version))
        self.archive_root.mkdir(parents=True, exist_ok=True)[cite: 7]

    @classmethod
    def normalize_version_tag(cls, version: str) -> str:
        clean = str(version or "").strip()
        if not clean:
            return f"{cls.VERSION_PREFIX}0.0.0"
        if clean.startswith(cls.VERSION_PREFIX):
            return clean
        return f"{cls.VERSION_PREFIX}{clean}"

    @classmethod
    def strip_version_tag(cls, version_or_dir: str) -> str:
        s = str(version_or_dir or "").strip()
        if s.startswith(cls.VERSION_PREFIX):
            return s[len(cls.VERSION_PREFIX):]
        return s

    @classmethod
    def build_mode_tag(cls, mode: str) -> str:
        normalized = str(mode or cls.MODE_PRODUCTION).strip().lower()
        if normalized in cls.MODE_TAG_MAP:
            return cls.MODE_TAG_MAP[normalized]
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", normalized)
        return sanitized or cls.UNKNOWN_VALUE

    @classmethod
    def make_build_id(cls, mode: str, now_local: datetime | None = None) -> str:
        dt = now_local or datetime.now()
        ts = dt.strftime(cls.BUILD_TIMESTAMP_FORMAT)
        mode_tag = cls.build_mode_tag(mode)
        return f"{cls.BUILD_PREFIX}{ts}{cls.BUILD_ID_SEPARATOR}{mode_tag}"

    @classmethod
    def compute_sha256(cls, file_path: Path) -> str:
        h = hashlib.sha256()
        with file_path.open("rb") as f:
            while True:
                chunk = f.read(cls.HASH_CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def get_app_archive_dir(self, app_name: str) -> Path:
        return self.archive_root / app_name

    def get_app_index_path(self, app_name: str) -> Path:
        return self.get_app_archive_dir(app_name) / self.INDEX_FILE_NAME

    def get_version_dir(self, app_name: str, version: str) -> Path:
        return self.get_app_archive_dir(app_name) / self.normalize_version_tag(version)

    def get_build_dir(self, app_name: str, version: str, build_id: str) -> Path:
        return self.get_version_dir(app_name, version) / build_id

    def load_index(self, app_name: str) -> dict[str, Any]:
        index_path = self.get_app_index_path(app_name)
        default_index: dict[str, Any] = {
            self.KEY_APP_NAME: app_name,
            self.KEY_UPDATED_AT_UTC: "",
            self.KEY_LATEST_VERSION: "",
            self.KEY_LATEST_BUILD_ID: "",
            self.KEY_BUILDS: [],
        }
        if not index_path.is_file():
            return default_index

        try:
            data = json.loads(index_path.read_text(encoding=self.JSON_ENCODING))
            if isinstance(data, dict):
                default_index.update(data)
                if not isinstance(default_index.get(self.KEY_BUILDS), list):
                    default_index[self.KEY_BUILDS] = []
        except Exception:
            pass
        return default_index

    def save_index(self, app_name: str, index_data: dict[str, Any]) -> Path:
        app_dir = self.get_app_archive_dir(app_name)
        app_dir.mkdir(parents=True, exist_ok=True)
        index_data[self.KEY_APP_NAME] = app_name
        index_data[self.KEY_UPDATED_AT_UTC] = datetime.now(timezone.utc).strftime(self.ISO_TIME_FORMAT)
        index_path = self.get_app_index_path(app_name)
        index_path.write_text(
            json.dumps(index_data, ensure_ascii=False, indent=self.JSON_INDENT),
            encoding=self.JSON_ENCODING,
        )
        return index_path

    def archive_exe_build(
        self,
        *,
        app_key: str,
        app_name: str,
        version: str,
        exe_path: str | Path,
        mode: str = MODE_PRODUCTION,
        bump_unit: str | None = None,
        built_by: str | None = None,
        git_commit: str | None = None,
        clean_build: bool = False,
        step_timings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        src_exe = Path(exe_path).resolve()
        if not src_exe.is_file():
            raise FileNotFoundError(f"아카이빙할 EXE 파일을 찾을 수 없습니다: {src_exe}")

        ver_tag = self.normalize_version_tag(version)
        clean_ver = self.strip_version_tag(ver_tag)
        build_id = self.make_build_id(mode=mode)
        build_dir = self.get_build_dir(app_name, ver_tag, build_id)
        build_dir.mkdir(parents=True, exist_ok=True)

        archived_exe = build_dir / src_exe.name
        shutil.copy2(src_exe, archived_exe)

        built_at_utc = datetime.now(timezone.utc).strftime(self.ISO_TIME_FORMAT)
        user_name = built_by or os.environ.get("USERNAME") or os.environ.get("USER") or self.UNKNOWN_VALUE
        commit_str = git_commit or self.UNKNOWN_VALUE
        sha256_hex = self.compute_sha256(archived_exe)
        size_bytes = archived_exe.stat().st_size

        if step_timings is not None:
            timings_path = build_dir / self.TIMINGS_FILE_NAME
            timings_path.write_text(
                json.dumps(step_timings, ensure_ascii=False, indent=self.JSON_INDENT),
                encoding=self.JSON_ENCODING,
            )

        rel_exe_path = archived_exe.relative_to(self.project_root).as_posix()
        manifest: dict[str, Any] = {
            self.KEY_APP_KEY: str(app_key),
            self.KEY_APP_NAME: app_name,
            self.KEY_VERSION: clean_ver,
            self.KEY_BUMP_UNIT: bump_unit or "",
            self.KEY_MODE: mode,
            self.KEY_BUILT_AT_UTC: built_at_utc,
            self.KEY_BUILT_BY: user_name,
            self.KEY_GIT_COMMIT: commit_str,
            self.KEY_CLEAN_BUILD: bool(clean_build),
            self.KEY_EXE: {
                self.KEY_FILENAME: archived_exe.name,
                self.KEY_SOURCE_PATH: str(src_exe),
                self.KEY_ARCHIVE_PATH: str(archived_exe),
                self.KEY_RELATIVE_ARCHIVE_PATH: rel_exe_path,
                self.KEY_SIZE_BYTES: int(size_bytes),
                self.KEY_SHA256: sha256_hex,
            },
        }

        manifest_path = build_dir / self.MANIFEST_FILE_NAME
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=self.JSON_INDENT),
            encoding=self.JSON_ENCODING,
        )

        index_data = self.load_index(app_name)
        entry: dict[str, Any] = {
            self.KEY_VERSION: clean_ver,
            self.KEY_VERSION_DIR: ver_tag,
            self.KEY_BUILD_ID: build_id,
            self.KEY_BUILD_DIR: build_dir.relative_to(self.project_root).as_posix(),
            self.KEY_MODE: mode,
            self.KEY_BUILT_AT_UTC: built_at_utc,
            self.KEY_BUILT_BY: user_name,
            self.KEY_SHA256: sha256_hex,
            self.KEY_SIZE_BYTES: int(size_bytes),
            self.KEY_RELATIVE_ARCHIVE_PATH: rel_exe_path,
        }
        builds_list: list[dict[str, Any]] = index_data.get(self.KEY_BUILDS, [])
        builds_list.insert(0, entry)
        index_data[self.KEY_BUILDS] = builds_list
        index_data[self.KEY_LATEST_VERSION] = clean_ver
        index_data[self.KEY_LATEST_BUILD_ID] = build_id
        self.save_index(app_name, index_data)

        self.cleanup_app_archive(app_name)
        return manifest

    def cleanup_app_archive(self, app_name: str) -> None:
        app_dir = self.get_app_archive_dir(app_name)
        if not app_dir.is_dir():
            return

        version_dirs = sorted(
            [p for p in app_dir.iterdir() if p.is_dir() and p.name.startswith(self.VERSION_PREFIX)],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_ver_dir in version_dirs[self.keep_versions:]:
            shutil.rmtree(old_ver_dir, ignore_errors=True)

        for ver_dir in version_dirs[:self.keep_versions]:
            if not ver_dir.is_dir():
                continue
            build_dirs = sorted(
                [p for p in ver_dir.iterdir() if p.is_dir() and p.name.startswith(self.BUILD_PREFIX)],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old_build_dir in build_dirs[self.keep_builds_per_version:]:
                shutil.rmtree(old_build_dir, ignore_errors=True)

    def restore_build_to_dist(self, app_name: str, version: str, build_id: str | None = None) -> Path:
        ver_dir = self.get_version_dir(app_name, version)
        if not ver_dir.is_dir():
            raise FileNotFoundError(f"버전 아카이브 폴더가 없습니다: {ver_dir}")

        if build_id:
            target_build_dir = ver_dir / build_id
        else:
            candidates = sorted(
                [p for p in ver_dir.iterdir() if p.is_dir()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not candidates:
                raise FileNotFoundError(f"복원할 빌드가 없습니다: {ver_dir}")
            target_build_dir = candidates[0]

        manifest_path = target_build_dir / self.MANIFEST_FILE_NAME
        if not manifest_path.is_file():
            raise FileNotFoundError(f"매니페스트 파일이 없습니다: {manifest_path}")

        manifest = json.loads(manifest_path.read_text(encoding=self.JSON_ENCODING))
        exe_info = manifest.get(self.KEY_EXE, {})
        exe_filename = exe_info.get(self.KEY_FILENAME) or f"{app_name}.exe"
        archived_exe = target_build_dir / exe_filename
        if not archived_exe.is_file():
            raise FileNotFoundError(f"아카이브 EXE가 없습니다: {archived_exe}")

        expected_sha = exe_info.get(self.KEY_SHA256)
        if expected_sha and self.compute_sha256(archived_exe) != expected_sha:
            raise ValueError(f"아카이브 EXE 무결성(SHA-256) 검증 실패: {archived_exe}")

        app_key = manifest.get(self.KEY_APP_KEY)
        if app_key and self.dir_config is not None:
            dist_app_dir = Path(BuildTargets.get_dist_dir(str(app_key), str(self.project_root), create=True))
        else:
            dist_app_dir = self.dist_root / app_name
            dist_app_dir.mkdir(parents=True, exist_ok=True)

        restored_exe = dist_app_dir / exe_filename
        shutil.copy2(archived_exe, restored_exe)
        return restored_exe