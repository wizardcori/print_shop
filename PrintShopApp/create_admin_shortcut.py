"""Create/update a desktop shortcut that always requests administrator rights.

The shortcut is created through Windows Shell.Application and then the standard
LNK ``SLDF_RUNAS_USER`` flag is set in the link header.  This keeps the feature
dependency-free (no pywin32 required).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# Keep the filename ASCII so legacy Windows PowerShell code pages cannot
# convert the path to '?' before WScript.Shell saves the link.
SHORTCUT_NAME = "PrintShopApp_Admin.lnk"
SLDF_RUNAS_USER = 0x2000
LNK_HEADER_SIZE = 76
LINK_FLAGS_OFFSET = 0x14


def _powershell_literal(value: str) -> str:
    """Return a single-quoted PowerShell string literal."""
    return "'" + value.replace("'", "''") + "'"


def _patch_run_as_flag(shortcut_path: Path) -> None:
    data = bytearray(shortcut_path.read_bytes())
    if len(data) < LNK_HEADER_SIZE:
        raise ValueError(f"Invalid shortcut header: {shortcut_path}")
    flags = int.from_bytes(
        data[LINK_FLAGS_OFFSET : LINK_FLAGS_OFFSET + 4], "little"
    )
    data[LINK_FLAGS_OFFSET : LINK_FLAGS_OFFSET + 4] = (
        flags | SLDF_RUNAS_USER
    ).to_bytes(4, "little")
    shortcut_path.write_bytes(data)


def create_admin_shortcut(project_dir: Path, shortcut_path: Path | None = None) -> Path:
    project_dir = project_dir.resolve()
    if shortcut_path is None:
        desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        shortcut_path = desktop / SHORTCUT_NAME
    else:
        shortcut_path = shortcut_path.resolve()
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)

    executable = project_dir / "main_app.exe"
    if executable.exists():
        target = executable
        arguments = ""
    else:
        target = Path(os.environ.get("ComSpec", "cmd.exe"))
        arguments = f'/c "{project_dir / "run.bat"}"'

    icon_path = executable if executable.exists() else target
    script = "\n".join(
        [
            "$ws = New-Object -ComObject WScript.Shell",
            f"$sc = $ws.CreateShortcut({_powershell_literal(str(shortcut_path))})",
            f"$sc.TargetPath = {_powershell_literal(str(target))}",
            f"$sc.Arguments = {_powershell_literal(arguments)}",
            f"$sc.WorkingDirectory = {_powershell_literal(str(project_dir))}",
            f"$sc.IconLocation = {_powershell_literal(str(icon_path))}",
            "$sc.Description = 'PrintShopApp 관리자 권한 실행'",
            "$sc.Save()",
        ]
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell shortcut creation failed")

    _patch_run_as_flag(shortcut_path)
    return shortcut_path


def set_startup_registration(project_dir: Path, enabled: bool) -> Path | None:
    """Register or remove the current-user startup shortcut."""
    startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
    shortcut_path = startup_dir / SHORTCUT_NAME
    if enabled:
        return create_admin_shortcut(project_dir, shortcut_path)
    if shortcut_path.exists():
        shortcut_path.unlink()
    return None


if __name__ == "__main__":
    try:
        path = create_admin_shortcut(Path(__file__).parent)
        print(f"[INFO] Administrator shortcut ready: {path}")
    except Exception as exc:  # pragma: no cover - startup helper diagnostics
        print(f"[WARN] Could not create administrator shortcut: {exc}", file=sys.stderr)
        sys.exit(1)
