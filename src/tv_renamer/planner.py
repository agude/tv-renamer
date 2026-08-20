"""YAML plan generation and execution for manual episode/movie assignment."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tv_renamer.constants import MEDIA_EXTENSIONS
from tv_renamer.matcher import match_files
from tv_renamer.renamer import RenameOp, RenamePlan, build_episode_path, build_movie_path
from tv_renamer.tmdb import Episode, TMDBClient


@dataclass
class PlanEntry:
    file: str
    season: int | None = None
    episode: int | None = None
    title: str | None = None
    part: int | None = None


@dataclass
class PlanData:
    show: str
    tmdb_id: int
    year: str
    directory: str
    files: list[PlanEntry] = field(default_factory=list)
    output: str | None = None


def _build_absolute_map(
    episodes: list[Episode],
) -> dict[int, tuple[int, int, str]]:
    """Map absolute episode numbers to (season, episode, title).

    When episodes span multiple seasons, builds cumulative offsets so that
    absolute number 1 maps to S01E01, and numbering continues across season
    boundaries. Returns empty dict if episodes is empty.
    """
    seasons: dict[int, list[Episode]] = {}
    for e in episodes:
        seasons.setdefault(e.season, []).append(e)

    result: dict[int, tuple[int, int, str]] = {}
    offset = 0
    for sn in sorted(seasons):
        season_eps = sorted(seasons[sn], key=lambda e: e.episode)
        for ep in season_eps:
            abs_num = offset + ep.episode
            result[abs_num] = (ep.season, ep.episode, ep.name)
        offset += len(season_eps)
    return result


def generate_plan(
    directory: Path,
    *,
    show_name: str,
    year: str,
    tmdb_id: int,
    episodes: list[Episode],
    season_override: int | None = None,
) -> PlanData:
    """Auto-detect episode assignments and build a plan.

    Runs the filename matcher, looks up TMDB titles, and produces a PlanData
    that can be written to YAML, edited, and later executed.

    When files have no season info (bare numbers, EP prefix) and episodes span
    multiple seasons, treats the file number as an absolute index across all
    seasons and maps it to the correct season/episode.
    """
    ep_by_num: dict[tuple[int, int], Episode] = {}
    for e in episodes:
        ep_by_num[(e.season, e.episode)] = e

    distinct_seasons = {e.season for e in episodes}
    multi_season = len(distinct_seasons) > 1 and season_override is None
    abs_map = _build_absolute_map(episodes) if multi_season else {}

    matches = match_files(directory)
    entries: list[PlanEntry] = []

    for fm in matches:
        if not fm.matched or fm.episode is None:
            entries.append(PlanEntry(file=fm.path.name))
            continue

        if season_override is not None:
            season = season_override
            ep_num = fm.episode
        elif fm.season is not None:
            season = fm.season
            ep_num = fm.episode
        elif multi_season and fm.episode in abs_map:
            season, ep_num, _ = abs_map[fm.episode]
        else:
            season = 1
            ep_num = fm.episode

        ep = ep_by_num.get((season, ep_num))
        entries.append(
            PlanEntry(
                file=fm.path.name,
                season=season,
                episode=ep_num,
                title=ep.name if ep else None,
            )
        )

    return PlanData(
        show=show_name,
        tmdb_id=tmdb_id,
        year=year,
        directory=str(directory),
        files=entries,
    )


def _yaml_str(s: str) -> str:
    """Quote a string for YAML output, handling special characters."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_plan(plan: PlanData, path: Path) -> None:
    """Write a plan to a YAML file with human-readable formatting."""
    lines: list[str] = []
    lines.append("# tv-renamer plan")
    lines.append("# Edit assignments below, then run:")
    lines.append(f"#   tv-renamer rename --plan {path.name} --dry-run")
    lines.append("")
    lines.append(f"show: {_yaml_str(plan.show)}")
    lines.append(f"tmdb_id: {plan.tmdb_id}")
    lines.append(f"year: {_yaml_str(plan.year)}")
    lines.append(f"directory: {_yaml_str(plan.directory)}")
    if plan.output:
        lines.append(f"output: {_yaml_str(plan.output)}")
    lines.append("")
    lines.append("files:")

    for entry in plan.files:
        lines.append(f"  - file: {_yaml_str(entry.file)}")
        if entry.season is not None:
            lines.append(f"    season: {entry.season}")
        else:
            lines.append("    season:")
        if entry.episode is not None:
            lines.append(f"    episode: {entry.episode}")
        else:
            lines.append("    episode:")
        if entry.title is not None:
            lines.append(f"    title: {_yaml_str(entry.title)}")
        if entry.part is not None:
            lines.append(f"    part: {entry.part}")

        if entry.season is None or entry.episode is None:
            lines.append("    # unmatched — set season/episode to include, or remove to skip")
        elif entry.title is None:
            lines.append(f"    # no TMDB match for S{entry.season:02d}E{entry.episode:02d}")

        lines.append("")

    path.write_text("\n".join(lines))


def read_plan(path: Path) -> PlanData:
    """Read a plan from a YAML file."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Plan file must be a YAML mapping, got {type(raw).__name__}")

    for key in ("show", "tmdb_id", "year", "directory", "files"):
        if key not in raw:
            raise ValueError(f"Plan file missing required key: {key}")

    if not isinstance(raw["files"], list):
        raise ValueError("Plan 'files' must be a list")

    entries: list[PlanEntry] = []
    for i, item in enumerate(raw["files"]):
        if not isinstance(item, dict):
            raise ValueError(f"Plan entry {i} must be a mapping")
        if "file" not in item:
            raise ValueError(f"Plan entry {i} missing 'file' key")
        entries.append(
            PlanEntry(
                file=item["file"],
                season=item.get("season"),
                episode=item.get("episode"),
                title=item.get("title"),
                part=item.get("part"),
            )
        )

    return PlanData(
        show=raw["show"],
        tmdb_id=int(raw["tmdb_id"]),
        year=str(raw["year"]),
        directory=raw["directory"],
        files=entries,
        output=raw.get("output"),
    )


def plan_to_renames(plan: PlanData, *, output_override: Path | None = None) -> RenamePlan:
    """Convert a plan into rename operations.

    Entries with null season/episode are skipped. Collisions (multiple files
    resolving to the same destination) are detected and reported.
    """
    directory = Path(plan.directory)
    out_root = output_override or (Path(plan.output) if plan.output else directory.parent)

    ops: list[RenameOp] = []
    skipped: list[Path] = []

    for entry in plan.files:
        source = directory / entry.file
        if entry.season is None or entry.episode is None:
            skipped.append(source)
            continue

        dest = build_episode_path(
            out_root=out_root,
            show_name=plan.show,
            year=plan.year,
            tmdb_id=plan.tmdb_id,
            season=entry.season,
            episode=entry.episode,
            ep_title=entry.title,
            extension=Path(entry.file).suffix,
            part=entry.part,
        )
        ops.append(RenameOp(source=source, dest=dest))

    dest_sources: dict[Path, list[Path]] = defaultdict(list)
    for op in ops:
        dest_sources[op.dest].append(op.source)
    collisions = {dest: srcs for dest, srcs in dest_sources.items() if len(srcs) > 1}

    return RenamePlan(ops=ops, unmatched=skipped, collisions=collisions)


@dataclass
class MoviePlanEntry:
    file: str
    tmdb_id: int | None = None
    name: str | None = None
    year: str | None = None


@dataclass
class MoviePlanData:
    directory: str
    files: list[MoviePlanEntry] = field(default_factory=list)
    output: str | None = None


def generate_movie_plan(directory: Path) -> MoviePlanData:
    entries: list[MoviePlanEntry] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix.lower() in MEDIA_EXTENSIONS:
            entries.append(MoviePlanEntry(file=entry.name))
    return MoviePlanData(directory=str(directory), files=entries)


def write_movie_plan(plan: MoviePlanData, path: Path) -> None:
    lines: list[str] = []
    lines.append("# tv-renamer movie plan")
    lines.append("# Fill in tmdb_id for each movie, then run:")
    lines.append(f"#   tv-renamer movie-rename --plan {path.name} --dry-run")
    lines.append("")
    lines.append(f"directory: {_yaml_str(plan.directory)}")
    if plan.output:
        lines.append(f"output: {_yaml_str(plan.output)}")
    lines.append("")
    lines.append("files:")

    for entry in plan.files:
        lines.append(f"  - file: {_yaml_str(entry.file)}")
        if entry.tmdb_id is not None:
            lines.append(f"    tmdb_id: {entry.tmdb_id}")
        else:
            lines.append("    tmdb_id:")
        if entry.name is not None:
            lines.append(f"    name: {_yaml_str(entry.name)}")
        if entry.year is not None:
            lines.append(f"    year: {_yaml_str(entry.year)}")

        if entry.tmdb_id is None:
            lines.append("    # set tmdb_id to include, or remove entry to skip")

        lines.append("")

    path.write_text("\n".join(lines))


def read_movie_plan(path: Path) -> MoviePlanData:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Plan file must be a YAML mapping, got {type(raw).__name__}")

    for key in ("directory", "files"):
        if key not in raw:
            raise ValueError(f"Plan file missing required key: {key}")

    if not isinstance(raw["files"], list):
        raise ValueError("Plan 'files' must be a list")

    entries: list[MoviePlanEntry] = []
    for i, item in enumerate(raw["files"]):
        if not isinstance(item, dict):
            raise ValueError(f"Plan entry {i} must be a mapping")
        if "file" not in item:
            raise ValueError(f"Plan entry {i} missing 'file' key")
        tmdb_id = item.get("tmdb_id")
        entries.append(
            MoviePlanEntry(
                file=item["file"],
                tmdb_id=int(tmdb_id) if tmdb_id is not None else None,
                name=item.get("name"),
                year=str(item["year"]) if item.get("year") is not None else None,
            )
        )

    return MoviePlanData(
        directory=raw["directory"],
        files=entries,
        output=raw.get("output"),
    )


def movie_plan_to_renames(plan: MoviePlanData, client: TMDBClient | None = None) -> RenamePlan:
    directory = Path(plan.directory)
    out_root = Path(plan.output) if plan.output else directory.parent

    ops: list[RenameOp] = []
    skipped: list[Path] = []

    for entry in plan.files:
        source = directory / entry.file
        if entry.tmdb_id is None:
            skipped.append(source)
            continue

        if entry.name is not None and entry.year is not None:
            name = entry.name
            year = entry.year
        else:
            if client is None:
                raise RuntimeError(f"Entry {entry.file} needs TMDB lookup but no client provided")
            movie = client.get_movie(entry.tmdb_id)
            name = entry.name or movie.name
            year = entry.year or movie.year

        dest = build_movie_path(
            out_root=out_root,
            movie_name=name,
            year=year,
            tmdb_id=entry.tmdb_id,
            extension=Path(entry.file).suffix,
        )
        ops.append(RenameOp(source=source, dest=dest))

    dest_sources: dict[Path, list[Path]] = defaultdict(list)
    for op in ops:
        dest_sources[op.dest].append(op.source)
    collisions = {dest: srcs for dest, srcs in dest_sources.items() if len(srcs) > 1}

    return RenamePlan(ops=ops, unmatched=skipped, collisions=collisions)
