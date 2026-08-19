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

_NFO_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<tvshow>
  <title>{title}</title>
  <tmdbid>{tmdb_id}</tmdbid>
</tvshow>
"""


def _safe_name(name: str) -> str:
    return _UNSAFE.sub("", name).strip()


def show_dir_name(show_name: str, year: str, tmdb_id: int) -> str:
    safe_show = _safe_name(show_name)
    return f"{safe_show} ({year}) [tmdbid-{tmdb_id}]"


def plan_renames(
    directory: Path,
    show_name: str,
    year: str,
    tmdb_id: int,
    episodes: list[Episode],
    output: Path | None = None,
    season_override: int | None = None,
) -> list[RenameOp]:
    """Build a list of rename operations without executing them.

    Args:
        directory: Source directory containing media files.
        show_name: Canonical show name from TMDB.
        year: First air date year.
        tmdb_id: TMDB show ID (embedded in folder name for Jellyfin matching).
        episodes: Episode list from TMDB for the relevant season(s).
        output: Output root directory. Defaults to the source directory's parent.
        season_override: Force all files into this season number.
    """
    out_root = output or directory.parent
    safe_show = _safe_name(show_name)
    dir_name = show_dir_name(show_name, year, tmdb_id)

    ep_by_num: dict[tuple[int, int], Episode] = {}
    for e in episodes:
        ep_by_num[(e.season, e.episode)] = e

    matches = match_files(directory)
    ops: list[RenameOp] = []

    for fm in matches:
        if not fm.matched:
            continue
        assert fm.episode is not None

        season = (
            season_override
            if season_override is not None
            else (fm.season if fm.season is not None else 1)
        )
        key = (season, fm.episode)

        ep = ep_by_num.get(key)
        if ep is not None:
            ep_title = _safe_name(ep.name)
            new_name = f"{safe_show} - S{season:02d}E{fm.episode:02d} - {ep_title}{fm.path.suffix}"
        else:
            new_name = f"{safe_show} - S{season:02d}E{fm.episode:02d}{fm.path.suffix}"

        dest = out_root / dir_name / f"Season {season}" / new_name
        ops.append(RenameOp(source=fm.path, dest=dest))

    return ops


def write_nfo(show_dir: Path, show_name: str, tmdb_id: int) -> Path:
    """Write a tvshow.nfo file into the show directory."""
    nfo_path = show_dir / "tvshow.nfo"
    nfo_path.write_text(_NFO_TEMPLATE.format(title=show_name, tmdb_id=tmdb_id))
    return nfo_path


def execute_renames(
    ops: list[RenameOp],
    *,
    log_path: Path | None = None,
    show_name: str | None = None,
    tmdb_id: int | None = None,
) -> int:
    """Execute rename operations. Returns count of files renamed.

    If show_name and tmdb_id are provided, writes a tvshow.nfo in the show directory.
    """
    count = 0
    log_lines: list[str] = []
    show_dirs: set[Path] = set()

    for op in ops:
        op.dest.parent.mkdir(parents=True, exist_ok=True)
        op.source.rename(op.dest)
        log_lines.append(f"{op.source} -> {op.dest}\n")
        count += 1
        # Track show-level directories (parent of Season N)
        show_dirs.add(op.dest.parent.parent)

    if show_name is not None and tmdb_id is not None:
        for sd in show_dirs:
            nfo = write_nfo(sd, show_name, tmdb_id)
            log_lines.append(f"wrote {nfo}\n")

    if log_path and log_lines:
        with log_path.open("a") as f:
            f.writelines(log_lines)

    return count
