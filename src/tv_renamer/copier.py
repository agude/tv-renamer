"""Rsync wrapper for transfer to the NAS."""

from __future__ import annotations

import subprocess
from pathlib import Path


def copy_to_dest(
    source: Path,
    dest: Path,
    *,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Rsync source directory to destination.

    A real transfer streams rsync output to the terminal so --progress
    is visible. A dry run captures stdout and returns it for the caller
    to print. Raises subprocess.CalledProcessError on non-zero exit.
    """
    cmd: list[str] = [
        "rsync",
        "-av",
        "--checksum",
        "--progress",
    ]
    if dry_run:
        cmd.append("--dry-run")

    src_str = str(source).rstrip("/") + "/"
    cmd.extend([src_str, str(dest)])

    return subprocess.run(cmd, check=True, text=True, capture_output=dry_run)
