"""Rsync wrapper for verified transfer to the NAS."""

from __future__ import annotations

import subprocess
from pathlib import Path


def copy_to_dest(
    source: Path,
    dest: Path,
    *,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Rsync source directory to destination with verification.

    Args:
        source: Source directory to copy.
        dest: Destination directory on the NAS.
        dry_run: If True, pass --dry-run to rsync.
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

    return subprocess.run(cmd, check=True, text=True, capture_output=not dry_run)
