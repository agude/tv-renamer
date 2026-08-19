"""Rename orchestration: match files to TMDB episodes and rename."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tv_renamer.matcher import match_files
from tv_renamer.tmdb import Episode


@dataclass(frozen=True)
class RenameOp:
    source: Path
    dest: Path


# Characters illegal in filenames on most filesystems.
_UNSAFE = re.compile(r'[<>:"/\\|?*]')


def _safe_name(name: str) -> str:
    return _UNSAFE.sub("", name).strip()


def plan_renames(
    directory: Path,
    show_name: str,
    year: str,
    episodes: list[Episode],
    output: Path | None = None,
    season_override: int | None = None,
) -> list[RenameOp]:
    """Build a list of rename operations without executing them.

    Args:
        directory: Source directory containing media files.
        show_name: Canonical show name from TMDB.
        year: First air date year.
        episodes: Episode list from TMDB for the relevant season(s).
        output: Output root directory. Defaults to the source directory's parent.
        season_override: Force all files into this season number.
    """
    out_root = output or directory.parent
    safe_show = _safe_name(show_name)
    show_dir_name = f"{safe_show} ({year})"

    ep_by_num: dict[tuple[int, int], Episode] = {}
    for e in episodes:
        ep_by_num[(e.season, e.episode)] = e

    matches = match_files(directory)
    ops: list[RenameOp] = []

    for fm in matches:
        if not fm.matched:
            continue
        assert fm.episode is not None

        season = season_override if season_override is not None else (fm.season or 1)
        key = (season, fm.episode)

        ep = ep_by_num.get(key)
        if ep is not None:
            ep_title = _safe_name(ep.name)
            new_name = f"{safe_show} - S{season:02d}E{fm.episode:02d} - {ep_title}{fm.path.suffix}"
        else:
            new_name = f"{safe_show} - S{season:02d}E{fm.episode:02d}{fm.path.suffix}"

        dest = out_root / show_dir_name / f"Season {season}" / new_name
        ops.append(RenameOp(source=fm.path, dest=dest))

    return ops


def execute_renames(ops: list[RenameOp], *, log_path: Path | None = None) -> int:
    """Execute rename operations. Returns count of files renamed."""
    count = 0
    log_lines: list[str] = []

    for op in ops:
        op.dest.parent.mkdir(parents=True, exist_ok=True)
        op.source.rename(op.dest)
        log_lines.append(f"{op.source} -> {op.dest}\n")
        count += 1

    if log_path and log_lines:
        with log_path.open("a") as f:
            f.writelines(log_lines)

    return count
