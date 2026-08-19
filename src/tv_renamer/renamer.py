"""Rename orchestration: match files to TMDB episodes and rename."""

from __future__ import annotations

import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from tv_renamer.matcher import match_files
from tv_renamer.tmdb import Episode


@dataclass(frozen=True)
class RenameOp:
    source: Path
    dest: Path


@dataclass(frozen=True)
class RenamePlan:
    ops: list[RenameOp]
    unmatched: list[Path]
    collisions: dict[Path, list[Path]] = field(default_factory=dict)
    missing_episodes: list[tuple[int, int]] = field(default_factory=list)


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
) -> RenamePlan:
    """Build a rename plan with operations and unmatched files.

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
    unmatched: list[Path] = []

    for fm in matches:
        if not fm.matched:
            unmatched.append(fm.path)
            continue
        if fm.episode is None:
            unmatched.append(fm.path)
            continue

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

    dest_sources: dict[Path, list[Path]] = defaultdict(list)
    for op in ops:
        dest_sources[op.dest].append(op.source)
    collisions = {dest: srcs for dest, srcs in dest_sources.items() if len(srcs) > 1}

    matched_keys = set()
    for fm in matches:
        if fm.episode is not None:
            season = (
                season_override
                if season_override is not None
                else (fm.season if fm.season is not None else 1)
            )
            matched_keys.add((season, fm.episode))
    missing_episodes = sorted(k for k in ep_by_num if k not in matched_keys)

    return RenamePlan(
        ops=ops,
        unmatched=unmatched,
        collisions=collisions,
        missing_episodes=missing_episodes,
    )


def write_nfo(show_dir: Path, show_name: str, tmdb_id: int) -> Path:
    """Write a tvshow.nfo file into the show directory."""
    if not isinstance(tmdb_id, int):
        raise TypeError(f"tmdb_id must be int, got {type(tmdb_id).__name__}")
    nfo_path = show_dir / "tvshow.nfo"
    nfo_path.write_text(_NFO_TEMPLATE.format(title=escape(show_name), tmdb_id=tmdb_id))
    return nfo_path


def _flush_log(log_path: Path | None, lines: list[str]) -> None:
    if log_path and lines:
        with log_path.open("a") as f:
            f.writelines(lines)


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
        if op.dest.exists():
            _flush_log(log_path, log_lines)
            raise FileExistsError(
                f"Destination already exists: {op.source} -> {op.dest}; "
                f"{count} of {len(ops)} files already moved"
            )
        op.dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(op.source), str(op.dest))
        except OSError:
            _flush_log(log_path, log_lines)
            raise OSError(
                f"Failed to move {op.source} -> {op.dest}; "
                f"{count} of {len(ops)} files already moved"
            ) from None
        log_lines.append(f"{op.source} -> {op.dest}\n")
        count += 1
        show_dirs.add(op.dest.parent.parent)

    if show_name is not None and tmdb_id is not None:
        for sd in show_dirs:
            nfo = write_nfo(sd, show_name, tmdb_id)
            log_lines.append(f"wrote {nfo}\n")

    _flush_log(log_path, log_lines)

    return count
