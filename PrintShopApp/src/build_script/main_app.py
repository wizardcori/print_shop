"""
PrintShopApp 빌드 CLI 진입점 (main_app.py)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from Common.log import set_file_tag
from build_script.build import BuildApp, FILE_TAG_BUILD, parse_targets
from build_script.build_archive_manager import MODE_DEVELOPMENT, MODE_PRODUCTION
from build_script.build_targets import BuildTargets
from build_script.target_config_io import (
    INSTALLER_FIELD_ONLY,
    INSTALLER_FIELD_SKIP,
    INSTALLER_FIELD_TARGETS,
    VALID_BUMP_UNITS,
    add_build_config_arguments,
    extract_cli_config_overrides,
)
from build_script.target_records import ensure_default_targets_injected

set_file_tag(FILE_TAG_BUILD)

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

for p in (str(PROJECT_ROOT), str(SRC_DIR), str(CURRENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

ensure_default_targets_injected()

CLI_DESCRIPTION: str = "PrintShopApp 통합 빌드 스크립트"
BUMP_CHOICES: tuple[str, ...] = tuple(sorted(VALID_BUMP_UNITS))
MODE_CHOICES: tuple[str, ...] = (MODE_PRODUCTION, MODE_DEVELOPMENT)

EXIT_CODE_SUCCESS: int = 0
EXIT_CODE_FAILURE: int = 1

__all__ = [
    "BUMP_CHOICES",
    "CLI_DESCRIPTION",
    "EXIT_CODE_FAILURE",
    "EXIT_CODE_SUCCESS",
    "MODE_CHOICES",
    "build_arg_parser",
    "main",
]


def build_arg_parser() -> argparse.ArgumentParser:
    ensure_default_targets_injected()
    allowed_keys = ", ".join(BuildTargets.ALL_TARGETS.keys())
    allowed_names = ", ".join(BuildTargets.ALL_TARGETS.values())

    parser = argparse.ArgumentParser(description=CLI_DESCRIPTION)
    parser.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help=f"빌드 대상 번호({allowed_keys}) 또는 이름({allowed_names})",
    )
    parser.add_argument(
        "--bump",
        choices=BUMP_CHOICES,
        default=None,
        help="버전 증가 단위 (실패 시 자동 롤백)",
    )
    parser.add_argument(
        "--mode",
        choices=MODE_CHOICES,
        default=MODE_PRODUCTION,
        help="빌드 배포 모드",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="빌드 전 작업/배포/ZIP/릴리스/인스톨러 디렉터리 정리",
    )
    parser.add_argument("--clean-work", action="store_true", help="대상별 work_out 정리")
    parser.add_argument("--clean-dist", action="store_true", help="대상별 dist_out 정리")
    parser.add_argument("--clean-spec", action="store_true", help="대상별 .spec 파일 정리 후 필요 시 재생성")

    add_build_config_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cli_cfg = extract_cli_config_overrides(args)
    cli_installer = cli_cfg.get("cli_installer_overrides") or {}

    targets = parse_targets(args.targets) if args.targets is not None else None
    app = BuildApp(
        project_root=str(PROJECT_ROOT),
        targets=targets,
        bump_unit=args.bump,
        mode=args.mode,
        skip_installer=bool(cli_installer.get(INSTALLER_FIELD_SKIP, False)),
        installer_only=bool(cli_installer.get(INSTALLER_FIELD_ONLY, False)),
        installer_targets=cli_installer.get(INSTALLER_FIELD_TARGETS),
        clean_build=args.clean,
        clean_work_out=args.clean_work,
        clean_dist_out=args.clean_dist,
        clean_spec=args.clean_spec,
        dir_config_json=cli_cfg["dir_config_json"],
        app_config_json=cli_cfg["app_config_json"],
        cli_dir_overrides=cli_cfg["cli_dir_overrides"],
        cli_app_overrides=cli_cfg["cli_app_overrides"],
        cli_installer_overrides=cli_installer,
    )
    ok = app.run()
    return EXIT_CODE_SUCCESS if ok else EXIT_CODE_FAILURE


if __name__ == "__main__":
    sys.exit(main())