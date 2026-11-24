"""
빌드 설정 입출력 모듈 (target_config_io.py)
- CLI 인자 파싱, JSON 파일 읽기/쓰기, 환경변수 반영 및 우선순위 병합 담당
- 우선순위: 1. CLI -> 2. 환경변수 -> 3. JSON -> 4. 코드 기본값
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WORK_DIR_NAME: str = "build"
DIST_DIR_NAME: str = "dist"
RELEASE_DIR_NAME: str = "release"
INSTALL_DIR_NAME: str = "Installer"

DEFAULT_CONFIG_FILENAME: str = "build_dirs.json"
ENV_APP_OVERRIDES_KEY: str = "BUILD_APP_OVERRIDES_JSON"
ENV_INSTALLER_CONFIG_KEY: str = "BUILD_INSTALLER_JSON"
ENV_INSTALLER_TARGETS_KEY: str = "BUILD_INSTALLER_TARGETS"
ENV_INSTALLER_ONLY_KEY: str = "BUILD_INSTALLER_ONLY"
ENV_SKIP_INSTALLER_KEY: str = "BUILD_SKIP_INSTALLER"

ENV_DIR_KEYS: dict[str, str] = {
    "work_dir_name": "BUILD_WORK_DIR_NAME",
    "dist_dir_name": "BUILD_DIST_DIR_NAME",
    "release_dir_name": "BUILD_RELEASE_DIR_NAME",
    "install_dir_name": "BUILD_INSTALL_DIR_NAME",
}

APP_OVERRIDE_FIELDS: tuple[str, ...] = (
    "label",
    "exe_name",
    "spec_hints",
    "dir_hints",
    "entry_file",
    "entry_hints",
    "version_file",
    "version_rel_paths",
    "console",
    "copy_to_test",
    "copy_to_archive",
    "include_in_installer",
    "standalone_installer",
    "is_installer",
    "hidden_imports",
    "extra_pathex",
    "pyinstaller",
    "pyinstaller_onefile",
    "pyinstaller_uac_admin",
    "pyinstaller_icon_path",
    "pyinstaller_hidden_imports",
    "pyinstaller_excludes",
    "pyinstaller_datas",
    "pyinstaller_binaries",
    "pyinstaller_extra_pathex",
    "inno",
    "inno_install_subdir",
    "inno_excludes",
    "inno_flags",
    "inno_components",
    "inno_tasks",
    "extra",
    "bump_unit",
    "mode",
    "clean_work",
    "clean_dist",
    "clean_spec",
)

JSON_SECTION_DIRS: str = "dirs"
JSON_SECTION_APPS: str = "apps"
JSON_SECTION_INSTALLER: str = "installer"

INSTALLER_FIELD_TARGETS: str = "targets"
INSTALLER_FIELD_ONLY: str = "installer_only"
INSTALLER_FIELD_SKIP: str = "skip_installer"
INSTALLER_FIELD_NAME: str = "name"
INSTALLER_FIELD_VERSION_SOURCE: str = "version_source_id"
INSTALLER_FIELD_EXTRA: str = "extra"

INSTALLER_KNOWN_FIELDS: frozenset[str] = frozenset(
    {
        INSTALLER_FIELD_TARGETS,
        INSTALLER_FIELD_ONLY,
        INSTALLER_FIELD_SKIP,
        INSTALLER_FIELD_NAME,
        INSTALLER_FIELD_VERSION_SOURCE,
    }
)

NONE_BUMP_TOKENS: frozenset[str] = frozenset({"none", "null", "false", "0", "변경 없음"})
VALID_BUMP_UNITS: frozenset[str] = frozenset({"patch", "minor", "major"})

TRUTHY_TOKENS: frozenset[str] = frozenset({"true", "1", "yes", "y", "on"})
FALSY_TOKENS: frozenset[str] = frozenset({"false", "0", "no", "n", "off"})
NULL_TOKENS: frozenset[str] = frozenset({"null", "none", ""})

DEFAULT_JSON_INDENT: int = 2
DEFAULT_TEXT_ENCODING: str = "utf-8"
BOM_TEXT_ENCODING: str = "utf-8-sig"

__all__ = [
    "APP_OVERRIDE_FIELDS",
    "BOM_TEXT_ENCODING",
    "BuildDirConfig",
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_JSON_INDENT",
    "DEFAULT_TEXT_ENCODING",
    "DIST_DIR_NAME",
    "ENV_APP_OVERRIDES_KEY",
    "ENV_DIR_KEYS",
    "ENV_INSTALLER_CONFIG_KEY",
    "ENV_INSTALLER_ONLY_KEY",
    "ENV_INSTALLER_TARGETS_KEY",
    "ENV_SKIP_INSTALLER_KEY",
    "FALSY_TOKENS",
    "INSTALLER_FIELD_EXTRA",
    "INSTALLER_FIELD_NAME",
    "INSTALLER_FIELD_ONLY",
    "INSTALLER_FIELD_SKIP",
    "INSTALLER_FIELD_TARGETS",
    "INSTALLER_FIELD_VERSION_SOURCE",
    "INSTALLER_KNOWN_FIELDS",
    "INSTALL_DIR_NAME",
    "InstallerBuildConfig",
    "JSON_SECTION_APPS",
    "JSON_SECTION_DIRS",
    "JSON_SECTION_INSTALLER",
    "NONE_BUMP_TOKENS",
    "NULL_TOKENS",
    "RELEASE_DIR_NAME",
    "TRUTHY_TOKENS",
    "VALID_BUMP_UNITS",
    "WORK_DIR_NAME",
    "add_build_config_arguments",
    "extract_apps_from_env",
    "extract_apps_from_json",
    "extract_cli_config_overrides",
    "extract_installer_from_env",
    "extract_installer_from_json",
    "load_json_dict",
    "merge_app_override_dicts",
    "normalize_bump_unit",
    "normalize_str_tuple",
    "normalize_target_id_list",
    "parse_bool_env",
    "parse_cli_app_override_tokens",
    "parse_scalar_value",
    "resolve_app_overrides",
    "resolve_default_json_path",
    "write_build_config_json",
]


def normalize_bump_unit(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s or s in NONE_BUMP_TOKENS:
        return None
    if s in VALID_BUMP_UNITS:
        return s
    return None


def normalize_str_tuple(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        items = [x.strip() for x in value.split(",") if x.strip()]
        return tuple(items)
    if isinstance(value, (list, tuple, set)):
        items = [str(x).strip() for x in value if str(x).strip()]
        return tuple(items)
    return None


def normalize_target_id_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        return [x.strip() for x in stripped.split(",") if x.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return None


def parse_scalar_value(raw: str) -> Any:
    text = raw.strip()
    low = text.lower()
    if low in TRUTHY_TOKENS:
        return True
    if low in FALSY_TOKENS:
        return False
    if low in NULL_TOKENS:
        return None
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    if "|" in text:
        return [part.strip() for part in text.split("|") if part.strip()]
    return text


def parse_bool_env(env_name: str) -> bool | None:
    raw = os.environ.get(env_name)
    if raw is None or not str(raw).strip():
        return None
    val = parse_scalar_value(str(raw))
    return val if isinstance(val, bool) else None


def parse_cli_app_override_tokens(tokens: list[str] | None) -> dict[str, dict[str, Any]]:
    """
    CLI 토큰 파싱:
      - `<AppKey>.<field>=<value>` (예: `UpdateService.console=false`, `PrintShopApp.bump_unit=patch`)
      - `<AppKey>:<field>=<value>`
      - JSON 문자열 전체(`{"UpdateService": {"console": false}}`)
    """
    result: dict[str, dict[str, Any]] = {}
    if not tokens:
        return result

    for raw_tok in tokens:
        if not raw_tok or not str(raw_tok).strip():
            continue
        tok = str(raw_tok).strip()

        if tok.startswith("{"):
            parsed = json.loads(tok)
            if isinstance(parsed, dict):
                for app_key, cfg in parsed.items():
                    if isinstance(cfg, dict):
                        bucket = result.setdefault(str(app_key).strip(), {})
                        for k, v in cfg.items():
                            if k in APP_OVERRIDE_FIELDS:
                                bucket[k] = normalize_bump_unit(v) if k == "bump_unit" else v
            continue

        if "=" not in tok:
            raise ValueError(f"잘못된 --app-set 형식입니다: '{tok}' (예: UpdateService.console=false)")

        lhs, rhs = tok.split("=", 1)
        sep = ":" if ":" in lhs and "." not in lhs else "."
        if sep not in lhs:
            raise ValueError(f"잘못된 --app-set 대상/필드 형식입니다: '{tok}' (예: UpdateService.console=false)")

        app_key, field_name = lhs.split(sep, 1)
        app_key = app_key.strip()
        field_name = field_name.strip()
        if field_name not in APP_OVERRIDE_FIELDS:
            raise ValueError(
                f"지원하지 않는 앱 설정 필드입니다: '{field_name}' (허용: {list(APP_OVERRIDE_FIELDS)})"
            )

        bucket = result.setdefault(app_key, {})
        parsed_val = parse_scalar_value(rhs)
        bucket[field_name] = normalize_bump_unit(parsed_val) if field_name == "bump_unit" else parsed_val

    return result


def merge_app_override_dicts(
    base: dict[str, dict[str, Any]] | None,
    incoming: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {
        str(k): dict(v) for k, v in (base or {}).items() if isinstance(v, dict)
    }
    if not incoming:
        return merged

    for raw_key, patch in incoming.items():
        if not isinstance(patch, dict):
            continue
        app_key = str(raw_key).strip()
        bucket = merged.setdefault(app_key, {})
        for field_name, val in patch.items():
            if field_name not in APP_OVERRIDE_FIELDS:
                continue
            normalized_val = normalize_bump_unit(val) if field_name == "bump_unit" else val
            if normalized_val is None:
                bucket.pop(field_name, None)
            else:
                bucket[field_name] = normalized_val
        if not bucket:
            merged.pop(app_key, None)

    return merged


def load_json_dict(json_path: str | Path) -> dict[str, Any]:
    p = Path(json_path)
    if not p.is_file():
        raise FileNotFoundError(f"빌드 설정 JSON 파일을 찾을 수 없습니다: {p}")
    with open(p, "r", encoding=BOM_TEXT_ENCODING) as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON 설정 최상위는 객체(dict)여야 합니다: {p}")
    return loaded


def resolve_default_json_path(
    project_root: str | Path | None = None,
    json_path: str | Path | None = None,
) -> Path | None:
    if json_path:
        return Path(json_path)
    if project_root:
        auto_json = Path(project_root) / DEFAULT_CONFIG_FILENAME
        if auto_json.is_file():
            return auto_json
    return None


def extract_apps_from_json(json_path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not json_path:
        return {}
    loaded = load_json_dict(json_path)
    apps_section = loaded.get(JSON_SECTION_APPS)
    if not isinstance(apps_section, dict):
        return {}
    return {str(k): dict(v) for k, v in apps_section.items() if isinstance(v, dict)}


def extract_apps_from_env() -> dict[str, dict[str, Any]]:
    raw_env = os.environ.get(ENV_APP_OVERRIDES_KEY)
    if not raw_env or not raw_env.strip():
        return {}
    parsed = json.loads(raw_env.strip())
    if not isinstance(parsed, dict):
        raise ValueError(f"{ENV_APP_OVERRIDES_KEY} 환경변수는 JSON 객체(dict)여야 합니다.")
    return {str(k): dict(v) for k, v in parsed.items() if isinstance(v, dict)}


def extract_installer_from_json(json_path: str | Path | None) -> dict[str, Any]:
    if not json_path:
        return {}
    loaded = load_json_dict(json_path)
    section = loaded.get(JSON_SECTION_INSTALLER)
    return dict(section) if isinstance(section, dict) else {}


def extract_installer_from_env() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    raw_json_env = os.environ.get(ENV_INSTALLER_CONFIG_KEY)
    if raw_json_env and raw_json_env.strip():
        parsed = json.loads(raw_json_env.strip())
        if not isinstance(parsed, dict):
            raise ValueError(f"{ENV_INSTALLER_CONFIG_KEY} 환경변수는 JSON 객체(dict)여야 합니다.")
        merged.update(parsed)

    raw_targets = os.environ.get(ENV_INSTALLER_TARGETS_KEY)
    if raw_targets is not None and str(raw_targets).strip() != "":
        merged[INSTALLER_FIELD_TARGETS] = normalize_target_id_list(raw_targets)

    installer_only_env = parse_bool_env(ENV_INSTALLER_ONLY_KEY)
    if installer_only_env is not None:
        merged[INSTALLER_FIELD_ONLY] = installer_only_env

    skip_installer_env = parse_bool_env(ENV_SKIP_INSTALLER_KEY)
    if skip_installer_env is not None:
        merged[INSTALLER_FIELD_SKIP] = skip_installer_env

    return merged


@dataclass
class BuildDirConfig:
    work_dir_name: str = WORK_DIR_NAME
    dist_dir_name: str = DIST_DIR_NAME
    release_dir_name: str = RELEASE_DIR_NAME
    install_dir_name: str = INSTALL_DIR_NAME

    def apply_dict(self, data: dict[str, Any] | None) -> "BuildDirConfig":
        if not data:
            return self
        for field_name in ENV_DIR_KEYS:
            val = data.get(field_name)
            if isinstance(val, str) and val.strip():
                setattr(self, field_name, val.strip())
        return self

    def apply_json_file(self, json_path: str | Path | None) -> "BuildDirConfig":
        if not json_path:
            return self
        loaded = load_json_dict(json_path)
        section = loaded.get(JSON_SECTION_DIRS) if isinstance(loaded.get(JSON_SECTION_DIRS), dict) else loaded
        return self.apply_dict(section)

    def apply_env(self) -> "BuildDirConfig":
        for field_name, env_name in ENV_DIR_KEYS.items():
            env_val = os.environ.get(env_name)
            if env_val and env_val.strip():
                setattr(self, field_name, env_val.strip())
        return self

    @classmethod
    def resolve(
        cls,
        *,
        project_root: str | Path | None = None,
        json_path: str | Path | None = None,
        cli_overrides: dict[str, Any] | None = None,
        code_overrides: dict[str, Any] | None = None,
    ) -> "BuildDirConfig":
        """
        우선순위:
          1. CLI 인자 (cli_overrides)
          2. 환경변수 (BUILD_*_DIR_NAME)
          3. JSON 설정 파일 (명시 경로 또는 <project_root>/build_dirs.json)
          4. 코드 인자/기본값 (code_overrides -> 상수)
        """
        cfg = cls()
        cfg.apply_dict(code_overrides)

        resolved_json = resolve_default_json_path(project_root=project_root, json_path=json_path)
        if resolved_json is not None:
            cfg.apply_json_file(resolved_json)

        cfg.apply_env()
        cfg.apply_dict(cli_overrides)
        return cfg


@dataclass
class InstallerBuildConfig:
    """인스톨러 조합 및 실행 제어 설정."""

    targets: list[str] | None = None
    installer_only: bool = False
    skip_installer: bool = False
    name: str | None = None
    version_source_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def apply_dict(self, data: dict[str, Any] | None) -> "InstallerBuildConfig":
        if not data:
            return self

        if INSTALLER_FIELD_TARGETS in data:
            raw_t = data.get(INSTALLER_FIELD_TARGETS)
            if raw_t is None:
                self.targets = None
            else:
                normalized = normalize_target_id_list(raw_t)
                self.targets = normalized if normalized is not None else []

        if INSTALLER_FIELD_ONLY in data and isinstance(data.get(INSTALLER_FIELD_ONLY), bool):
            self.installer_only = bool(data[INSTALLER_FIELD_ONLY])

        if INSTALLER_FIELD_SKIP in data and isinstance(data.get(INSTALLER_FIELD_SKIP), bool):
            self.skip_installer = bool(data[INSTALLER_FIELD_SKIP])

        if INSTALLER_FIELD_NAME in data:
            self.name = str(data[INSTALLER_FIELD_NAME]).strip() if data[INSTALLER_FIELD_NAME] else None

        if INSTALLER_FIELD_VERSION_SOURCE in data:
            self.version_source_id = (
                str(data[INSTALLER_FIELD_VERSION_SOURCE]).strip()
                if data[INSTALLER_FIELD_VERSION_SOURCE]
                else None
            )

        for k, v in data.items():
            if k not in INSTALLER_KNOWN_FIELDS:
                if v is None:
                    self.extra.pop(k, None)
                else:
                    self.extra[k] = v

        return self

    @classmethod
    def resolve(
        cls,
        *,
        project_root: str | Path | None = None,
        json_path: str | Path | None = None,
        installer_config_json: str | Path | None = None,
        code_overrides: dict[str, Any] | None = None,
        cli_overrides: dict[str, Any] | None = None,
    ) -> "InstallerBuildConfig":
        """
        인스톨러 설정 우선순위:
          1. CLI 인자 (cli_overrides)
          2. 환경변수 (BUILD_INSTALLER_*)
          3. JSON 설정 파일 (명시 경로 또는 <project_root>/build_dirs.json -> 'installer' 섹션)
          4. 코드 인자/기본값 (code_overrides -> 기본값)
        """
        cfg = cls()
        cfg.apply_dict(code_overrides)

        resolved_json = resolve_default_json_path(project_root=project_root, json_path=json_path)
        if resolved_json is not None:
            cfg.apply_dict(extract_installer_from_json(resolved_json))

        if installer_config_json:
            cfg.apply_dict(extract_installer_from_json(installer_config_json))

        cfg.apply_dict(extract_installer_from_env())
        cfg.apply_dict(cli_overrides)
        return cfg

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            INSTALLER_FIELD_TARGETS: list(self.targets) if self.targets is not None else None,
            INSTALLER_FIELD_ONLY: self.installer_only,
            INSTALLER_FIELD_SKIP: self.skip_installer,
        }
        if self.name is not None:
            payload[INSTALLER_FIELD_NAME] = self.name
        if self.version_source_id is not None:
            payload[INSTALLER_FIELD_VERSION_SOURCE] = self.version_source_id
        if self.extra:
            payload[INSTALLER_FIELD_EXTRA] = dict(self.extra)
        return payload


def resolve_app_overrides(
    *,
    project_root: str | Path | None = None,
    json_path: str | Path | None = None,
    app_config_json: str | Path | None = None,
    code_app_overrides: dict[str, dict[str, Any]] | None = None,
    cli_app_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """앱별 설정 우선순위(4. 코드 -> 3. JSON -> 2. 환경변수 -> 1. CLI)로 병합합니다."""
    merged: dict[str, dict[str, Any]] = {}
    merged = merge_app_override_dicts(merged, code_app_overrides)

    resolved_json = resolve_default_json_path(project_root=project_root, json_path=json_path)
    if resolved_json is not None:
        merged = merge_app_override_dicts(merged, extract_apps_from_json(resolved_json))

    if app_config_json:
        merged = merge_app_override_dicts(merged, extract_apps_from_json(app_config_json))

    merged = merge_app_override_dicts(merged, extract_apps_from_env())
    merged = merge_app_override_dicts(merged, cli_app_overrides)
    return merged


def write_build_config_json(
    json_path: str | Path,
    *,
    dir_config: BuildDirConfig,
    app_overrides: dict[str, dict[str, Any]],
    installer_config: InstallerBuildConfig | None = None,
) -> Path:
    target_path = Path(json_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        JSON_SECTION_DIRS: {
            "work_dir_name": dir_config.work_dir_name,
            "dist_dir_name": dir_config.dist_dir_name,
            "release_dir_name": dir_config.release_dir_name,
            "install_dir_name": dir_config.install_dir_name,
        },
        JSON_SECTION_APPS: app_overrides,
    }
    if installer_config is not None:
        payload[JSON_SECTION_INSTALLER] = installer_config.to_dict()
    with open(target_path, "w", encoding=DEFAULT_TEXT_ENCODING) as f:
        json.dump(payload, f, ensure_ascii=False, indent=DEFAULT_JSON_INDENT)
    return target_path


def add_build_config_arguments(parser: Any) -> None:
    """빌드 디렉터리, 앱별 세부설정 및 인스톨러 조합 CLI 옵션을 ArgumentParser에 등록합니다."""
    parser.add_argument(
        "--dir-config",
        default=None,
        help=f"디렉터리/앱/인스톨러 설정 JSON 파일 경로 (기본: {DEFAULT_CONFIG_FILENAME})",
    )
    parser.add_argument("--work-dir-name", default=None, help=f"작업 폴더명 (기본: {WORK_DIR_NAME})")
    parser.add_argument("--dist-dir-name", default=None, help=f"배포 산출물 폴더명 (기본: {DIST_DIR_NAME})")
    parser.add_argument("--release-dir-name", default=None, help=f"릴리스 폴더명 (기본: {RELEASE_DIR_NAME})")
    parser.add_argument("--install-dir-name", default=None, help=f"인스톨러 폴더명 (기본: {INSTALL_DIR_NAME})")

    parser.add_argument(
        "--app-config",
        default=None,
        help=f"앱별 세부설정 JSON 파일 경로 (최상위 또는 '{JSON_SECTION_APPS}' 객체 지원)",
    )
    parser.add_argument(
        "--app-set",
        nargs="+",
        default=None,
        help="앱별 세부설정 직접 지정 (예: UpdateService.console=false PrintShopApp.bump_unit=patch)",
    )

    parser.add_argument(
        "--installer-targets",
        default=None,
        help="인스톨러에 포함할 대상 ID/이름 목록 (예: 1,3,5 또는 1,2 또는 1)",
    )
    parser.add_argument(
        "--installer-only",
        action="store_true",
        default=None,
        help="기존 빌드를 재사용하고 인스톨러만 생성",
    )
    parser.add_argument(
        "--skip-installer",
        action="store_true",
        default=None,
        help="인스톨러 생성 단계 건너뜀",
    )


def extract_cli_config_overrides(args: Any) -> dict[str, Any]:
    """파싱된 argparse Namespace에서 디렉터리/앱/인스톨러 오버라이드 및 JSON 경로를 추출합니다."""
    cli_dir_overrides = {
        "work_dir_name": getattr(args, "work_dir_name", None),
        "dist_dir_name": getattr(args, "dist_dir_name", None),
        "release_dir_name": getattr(args, "release_dir_name", None),
        "install_dir_name": getattr(args, "install_dir_name", None),
    }
    cli_app_overrides = parse_cli_app_override_tokens(getattr(args, "app_set", None))

    cli_installer_overrides: dict[str, Any] = {}
    raw_inst_targets = getattr(args, "installer_targets", None)
    if raw_inst_targets is not None:
        cli_installer_overrides[INSTALLER_FIELD_TARGETS] = normalize_target_id_list(raw_inst_targets)
    if getattr(args, "installer_only", None) is not None:
        cli_installer_overrides[INSTALLER_FIELD_ONLY] = bool(getattr(args, "installer_only"))
    if getattr(args, "skip_installer", None) is not None:
        cli_installer_overrides[INSTALLER_FIELD_SKIP] = bool(getattr(args, "skip_installer"))

    return {
        "dir_config_json": getattr(args, "dir_config", None),
        "app_config_json": getattr(args, "app_config", None),
        "cli_dir_overrides": cli_dir_overrides,
        "cli_app_overrides": cli_app_overrides,
        "cli_installer_overrides": cli_installer_overrides,
    }