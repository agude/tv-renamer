"""Rsync wrapper for transfer to the NAS."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CopyResult:
    dry_run_output: str | None = None
    verified: bool = False


def copy_to_dest(
    source: Path,
    dest: Path,
    *,
    dry_run: bool = False,
) -> CopyResult:
    """Rsync source directory to destination.

    A real transfer streams rsync output to the terminal so --progress
    is visible, then runs a post-copy checksum verification pass.
    A dry run captures and returns stdout. Raises on non-zero exit.
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

    result = subprocess.run(cmd, check=True, text=True, capture_output=dry_run)

    if dry_run:
        return CopyResult(dry_run_output=result.stdout)

    verify_cmd = [
        "rsync",
        "-n",
        "--checksum",
        "--itemize-changes",
        src_str,
        str(dest),
    ]
    verify = subprocess.run(verify_cmd, check=True, text=True, capture_output=True)
    verified = not verify.stdout.strip()

    return CopyResult(verified=verified)
