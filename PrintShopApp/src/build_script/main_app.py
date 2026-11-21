"""
PrintShopApp 빌드 CLI 진입점 (main_app.py)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from Common.log import set_file_tag

set_file_tag("BUILD")

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

for p in (str(PROJECT_ROOT), str(SRC_DIR), str(CURRENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from build import BuildApp, parse_targets  # noqa: E402
from build_targets import ALL_TARGETS  # noqa: E402
from target_config_io import (  # noqa: E402
    add_build_config_arguments,
    extract_cli_config_overrides,
)


def build_arg_parser() -> argparse.ArgumentParser:
    allowed_keys = ", ".join(ALL_TARGETS.keys())
    allowed_names = ", ".join(ALL_TARGETS.values())
    parser = argparse.ArgumentParser(description="PrintShopApp 통합 빌드 스크립트")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help=f"빌드 대상 번호({allowed_keys}) 또는 이름({allowed_names})",
    )
    parser.add_argument(
        "--bump",
        choices=["major", "minor", "patch"],
        default=None,
        help="버전 증가 단위 (실패 시 자동 롤백)",
    )
    parser.add_argument(
        "--mode",
        choices=["production", "development"],
        default="production",
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
        skip_installer=bool(cli_installer.get("skip_installer", False)),
        installer_only=bool(cli_installer.get("installer_only", False)),
        installer_targets=cli_installer.get("targets"),
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
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())