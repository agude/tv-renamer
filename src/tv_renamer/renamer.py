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


_REPLACE_WITH_DASH = re.compile(r"[/:]")
_DELETE = re.compile(r'[<>"\\|?*]')
_MULTI_SPACE = re.compile(r" {2,}")

_NFO_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<tvshow>
  <title>{title}</title>
  <tmdbid>{tmdb_id}</tmdbid>
</tvshow>
"""

_MOVIE_NFO_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>{title}</title>
  <tmdbid>{tmdb_id}</tmdbid>
</movie>
"""

_MAX_FILENAME_BYTES = 255


def _safe_name(name: str) -> str:
    name = _REPLACE_WITH_DASH.sub(" - ", name)
    name = _DELETE.sub("", name)
    name = _MULTI_SPACE.sub(" ", name)
    return name.strip().rstrip(". ")


def _truncate_filename(filename: str) -> str:
    """Truncate a filename to fit within 255 UTF-8 bytes, preserving the extension."""
    encoded = filename.encode("utf-8")
    if len(encoded) <= _MAX_FILENAME_BYTES:
        return filename

    stem, _, ext = filename.rpartition(".")
    if not stem:
        stem = ext
        ext = ""
    else:
        ext = "." + ext

    ext_bytes = len(ext.encode("utf-8"))
    budget = _MAX_FILENAME_BYTES - ext_bytes

    truncated = stem.encode("utf-8")[:budget].decode("utf-8", errors="ignore").rstrip()
    return truncated + ext


def show_dir_name(show_name: str, year: str, tmdb_id: int) -> str:
    safe_show = _safe_name(show_name)
    return f"{safe_show} ({year}) [tmdbid-{tmdb_id}]"


def movie_dir_name(movie_name: str, year: str, tmdb_id: int) -> str:
    safe_name = _safe_name(movie_name)
    return f"{safe_name} ({year}) [tmdbid-{tmdb_id}]"


def build_movie_path(
    *,
    out_root: Path,
    movie_name: str,
    year: str,
    tmdb_id: int,
    extension: str,
) -> Path:
    dir_name = movie_dir_name(movie_name, year, tmdb_id)
    filename = _truncate_filename(f"{dir_name}{extension}")
    return out_root / dir_name / filename


def write_movie_nfo(movie_dir: Path, movie_name: str, tmdb_id: int) -> Path:
    if not isinstance(tmdb_id, int):
        raise TypeError(f"tmdb_id must be int, got {type(tmdb_id).__name__}")
    nfo_path = movie_dir / "movie.nfo"
    nfo_path.write_text(_MOVIE_NFO_TEMPLATE.format(title=escape(movie_name), tmdb_id=tmdb_id))
    return nfo_path


def plan_movie_rename(
    file: Path,
    *,
    movie_name: str,
    year: str,
    tmdb_id: int,
    output: Path | None = None,
) -> RenameOp:
    if not file.exists():
        raise FileNotFoundError(f"Source file does not exist: {file}")
    out_root = output or file.parent
    dest = build_movie_path(
        out_root=out_root,
        movie_name=movie_name,
        year=year,
        tmdb_id=tmdb_id,
        extension=file.suffix,
    )
    return RenameOp(source=file, dest=dest)


def build_episode_path(
    *,
    out_root: Path,
    show_name: str,
    year: str,
    tmdb_id: int,
    season: int,
    episode: int,
    ep_title: str | None = None,
    extension: str,
    part: int | None = None,
) -> Path:
    """Build the Jellyfin-standard destination path for a single episode."""
    safe_show = _safe_name(show_name)
    dir_name = show_dir_name(show_name, year, tmdb_id)

    ep_tag = f"S{season:02d}E{episode:02d}"
    if ep_title:
        title = _safe_name(ep_title)
        if part is not None:
            title = f"{title} (Part {part})"
        new_name = _truncate_filename(f"{safe_show} - {ep_tag} - {title}{extension}")
    else:
        if part is not None:
            new_name = f"{safe_show} - {ep_tag} (Part {part}){extension}"
        else:
            new_name = f"{safe_show} - {ep_tag}{extension}"

    return out_root / dir_name / f"Season {season}" / new_name


def plan_renames(
    directory: Path,
    *,
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

    max_ep_per_season: dict[int, int] = {}
    for s, ep_num in ep_by_num:
        max_ep_per_season[s] = max(max_ep_per_season.get(s, 0), ep_num)

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

        if (
            fm.pattern is not None
            and fm.pattern in ("bare_leading", "bare_trailing", "ep_prefix")
            and fm.episode > max_ep_per_season.get(season, 0)
        ):
            unmatched.append(fm.path)
            continue

        if fm.episode_end is not None:
            ep_range = list(range(fm.episode, fm.episode_end + 1))
            eps = [ep_by_num.get((season, e)) for e in ep_range]
            if any(ep is None for ep in eps):
                unmatched.append(fm.path)
                continue
            titles = " & ".join(_safe_name(ep.name) for ep in eps if ep is not None)
            ep_tag = f"S{season:02d}E{fm.episode:02d}-E{fm.episode_end:02d}"
            new_name = _truncate_filename(f"{safe_show} - {ep_tag} - {titles}{fm.path.suffix}")
        else:
            key = (season, fm.episode)
            ep = ep_by_num.get(key)
            if ep is not None:
                ep_title = _safe_name(ep.name)
                new_name = _truncate_filename(
                    f"{safe_show} - S{season:02d}E{fm.episode:02d} - {ep_title}{fm.path.suffix}"
                )
            else:
                new_name = f"{safe_show} - S{season:02d}E{fm.episode:02d}{fm.path.suffix}"

        dest = out_root / dir_name / f"Season {season}" / new_name
        ops.append(RenameOp(source=fm.path, dest=dest))

    dest_sources: dict[Path, list[Path]] = defaultdict(list)
    for op in ops:
        dest_sources[op.dest].append(op.source)
    collisions = {dest: srcs for dest, srcs in dest_sources.items() if len(srcs) > 1}

    matched_keys: set[tuple[int, int]] = set()
    for fm in matches:
        if fm.episode is not None:
            season = (
                season_override
                if season_override is not None
                else (fm.season if fm.season is not None else 1)
            )
            if fm.episode_end is not None:
                for ep_num in range(fm.episode, fm.episode_end + 1):
                    matched_keys.add((season, ep_num))
            else:
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


@dataclass(frozen=True)
class UndoPlan:
    moves: list[RenameOp]
    nfo_removals: list[Path]


def parse_log(log_path: Path) -> UndoPlan:
    """Parse a changes.log into an undo plan (reversed order)."""
    moves: list[RenameOp] = []
    nfo_removals: list[Path] = []

    for line in log_path.read_text().splitlines():
        if line.startswith("wrote "):
            nfo_removals.append(Path(line.removeprefix("wrote ")))
        elif " -> " in line:
            src_str, dest_str = line.split(" -> ", 1)
            moves.append(RenameOp(source=Path(dest_str), dest=Path(src_str)))

    moves.reverse()
    return UndoPlan(moves=moves, nfo_removals=nfo_removals)


def undo_renames(plan: UndoPlan, *, dry_run: bool = False) -> int:
    """Reverse a logged rename batch. Returns count of files restored."""
    for op in plan.moves:
        if not op.source.exists():
            raise FileNotFoundError(f"Source no longer exists: {op.source}")
        if op.dest.exists():
            raise FileExistsError(f"Original location already occupied: {op.dest}")

    if dry_run:
        return len(plan.moves)

    for nfo in plan.nfo_removals:
        if nfo.exists():
            nfo.unlink()

    count = 0
    for op in plan.moves:
        op.dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(op.source), str(op.dest))
        count += 1

    dirs_to_prune: list[Path] = []
    for op in plan.moves:
        dirs_to_prune.append(op.source.parent)
        dirs_to_prune.append(op.source.parent.parent)

    for d in sorted(set(dirs_to_prune), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    return count
