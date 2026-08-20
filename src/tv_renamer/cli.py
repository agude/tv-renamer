"""Argparse entry point for all subcommands."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from requests import HTTPError

from tv_renamer.copier import copy_to_dest
from tv_renamer.planner import (
    generate_movie_plan,
    generate_plan,
    movie_plan_to_renames,
    plan_to_renames,
    read_movie_plan,
    read_plan,
    write_movie_plan,
    write_plan,
)
from tv_renamer.renamer import (
    execute_renames,
    parse_log,
    plan_movie_rename,
    plan_renames,
    undo_renames,
    write_movie_nfo,
)
from tv_renamer.scanner import scan_directory
from tv_renamer.tmdb import TMDBClient


def _cmd_scan(args: argparse.Namespace) -> None:
    result = scan_directory(Path(args.directory))

    if result.movies:
        print(f"\n  Movies ({len(result.movies)}):")
        for f in result.movies:
            print(f"    {f.name}")

    if result.loose_files:
        print(f"\n  Loose files ({len(result.loose_files)}):")
        for f in result.loose_files:
            print(f"    {f.name}")

    if result.shows:
        print(f"\n  Shows ({len(result.shows)}):")
        for show in result.shows:
            seasons = " [has season folders]" if show.has_season_folders else ""
            print(f"    {show.name}  ({show.episode_count} episodes){seasons}")
            for sample in show.sample_files:
                print(f"      {sample}")


def _cmd_search(args: argparse.Namespace) -> None:
    client: TMDBClient = args.client
    query = args.query
    media_type: str = args.type

    if media_type in ("tv", "both"):
        results = client.search_tv(query)
        if results:
            print("\n  TV Shows:")
            for r in results[:10]:
                print(f"    [{r.tmdb_id}] {r.name} ({r.year})")
                if r.overview:
                    print(f"      {r.overview[:120]}")

    if media_type in ("movie", "both"):
        results = client.search_movie(query)
        if results:
            print("\n  Movies:")
            for r in results[:10]:
                print(f"    [{r.tmdb_id}] {r.name} ({r.year})")
                if r.overview:
                    print(f"      {r.overview[:120]}")


def _cmd_episodes(args: argparse.Namespace) -> None:
    client: TMDBClient = args.client
    tmdb_id: int = args.id
    show = client.get_show(tmdb_id)
    print(f"\n  {show.name} ({show.year})")

    if args.season is not None:
        seasons_to_show = [args.season]
    else:
        seasons_to_show = [s.season_number for s in show.seasons]

    for sn in seasons_to_show:
        episodes = client.get_episodes(tmdb_id, sn)
        print(f"\n  Season {sn} ({len(episodes)} episodes):")
        for ep in episodes:
            print(f"    S{ep.season:02d}E{ep.episode:02d} - {ep.name}")


def _cmd_plan(args: argparse.Namespace) -> None:
    client: TMDBClient = args.client
    tmdb_id: int = args.id
    directory = Path(args.directory)
    season_override: int | None = args.season
    out_file = Path(args.out) if args.out else None

    show = client.get_show(tmdb_id)

    if season_override is not None:
        all_episodes = client.get_episodes(tmdb_id, season_override)
    else:
        all_episodes = []
        for s in show.seasons:
            all_episodes.extend(client.get_episodes(tmdb_id, s.season_number))

    plan_data = generate_plan(
        directory,
        show_name=show.name,
        year=show.year,
        tmdb_id=tmdb_id,
        episodes=all_episodes,
        season_override=season_override,
    )

    if out_file:
        write_plan(plan_data, out_file)
        matched = sum(1 for e in plan_data.files if e.episode is not None)
        unmatched = len(plan_data.files) - matched
        print(f"  Plan written to {out_file}")
        print(f"  {matched} matched, {unmatched} unmatched, {len(plan_data.files)} total")
    else:
        write_plan(plan_data, Path("/dev/stdout"))


def _cmd_rename(args: argparse.Namespace) -> None:
    dry_run: bool = args.dry_run
    log_path = Path(args.log) if args.log else None

    if args.plan:
        plan_data = read_plan(Path(args.plan))
        output = Path(args.output) if args.output else None
        rename_plan = plan_to_renames(plan_data, output_override=output)
        show_name = plan_data.show
        tmdb_id = plan_data.tmdb_id
        print(f"\n  Show: {show_name} ({plan_data.year})")
        print(f"  Plan: {args.plan}")
    else:
        if not args.directory or args.id is None:
            print("error: provide either --plan or both directory and --id", file=sys.stderr)
            sys.exit(1)
        client: TMDBClient = args.client
        tmdb_id = args.id
        directory = Path(args.directory)
        season_override: int | None = args.season
        output = Path(args.output) if args.output else None

        show = client.get_show(tmdb_id)
        show_name = show.name
        print(f"\n  Show: {show.name} ({show.year})")

        if season_override is not None:
            all_episodes = client.get_episodes(tmdb_id, season_override)
        else:
            all_episodes = []
            for s in show.seasons:
                all_episodes.extend(client.get_episodes(tmdb_id, s.season_number))

        rename_plan = plan_renames(
            directory,
            show_name=show.name,
            year=show.year,
            tmdb_id=tmdb_id,
            episodes=all_episodes,
            output=output,
            season_override=season_override,
        )

    plan = rename_plan

    if not plan.ops:
        print("  No files matched.")
        if plan.unmatched:
            print(f"\n  Unmatched ({len(plan.unmatched)}):")
            for p in plan.unmatched:
                print(f"    {p.name}")
        return

    if plan.collisions:
        print("  Collisions detected — multiple files resolve to the same destination:\n")
        for dest, srcs in plan.collisions.items():
            print(f"    {dest.name}")
            for src_path in srcs:
                print(f"      <- {src_path.name}")
        print(f"\n  {len(plan.collisions)} collision(s). No files renamed.")
        sys.exit(1)

    for op in plan.ops:
        label = "[DRY RUN] " if dry_run else ""
        print(f"  {label}{op.source.name}")
        print(f"    -> {op.dest}")

    if plan.unmatched:
        print(f"\n  Unmatched ({len(plan.unmatched)}):")
        for p in plan.unmatched:
            print(f"    {p.name}")

    if plan.missing_episodes:
        ep_list = ", ".join(f"S{s:02d}E{e:02d}" for s, e in plan.missing_episodes)
        total = len(plan.ops) + len(plan.missing_episodes)
        print(f"\n  Matched {len(plan.ops)}/{total} episodes; missing {ep_list}")

    if dry_run:
        print(f"\n  {len(plan.ops)} files would be renamed.")
    else:
        count = execute_renames(
            plan.ops,
            log_path=log_path,
            show_name=show_name,
            tmdb_id=tmdb_id,
        )
        print(f"\n  {count} files renamed.")


def _cmd_undo(args: argparse.Namespace) -> None:
    log_path = Path(args.log)
    dry_run: bool = args.dry_run

    plan = parse_log(log_path)

    if not plan.moves:
        print("  Log contains no moves to undo.")
        return

    for op in plan.moves:
        label = "[DRY RUN] " if dry_run else ""
        print(f"  {label}{op.source.name}")
        print(f"    -> {op.dest}")

    for nfo in plan.nfo_removals:
        label = "[DRY RUN] " if dry_run else ""
        print(f"  {label}remove {nfo}")

    count = undo_renames(plan, dry_run=dry_run)

    if dry_run:
        print(f"\n  {count} files would be restored.")
    else:
        print(f"\n  {count} files restored.")


def _cmd_copy(args: argparse.Namespace) -> None:
    source = Path(args.source)
    dest = Path(args.dest)
    dry_run: bool = args.dry_run

    label = "[DRY RUN] " if dry_run else ""
    print(f"  {label}Copying {source} -> {dest}")
    result = copy_to_dest(source, dest, dry_run=dry_run)
    if dry_run:
        if result.dry_run_output:
            print(result.dry_run_output)
    elif result.verified:
        print("  Verify: OK")
    else:
        print("  Verify: FAILED — differences detected after copy", file=sys.stderr)
        sys.exit(1)


def _cmd_movie(args: argparse.Namespace) -> None:
    client: TMDBClient = args.client
    movie = client.get_movie(args.id)
    runtime = f"{movie.runtime} min" if movie.runtime else "unknown"
    print(f"\n  {movie.name} ({movie.year})")
    print(f"  Runtime: {runtime}")
    if movie.overview:
        print(f"  {movie.overview[:200]}")


def _cmd_movie_plan(args: argparse.Namespace) -> None:
    directory = Path(args.directory)
    out_file = Path(args.out) if args.out else None

    plan_data = generate_movie_plan(directory)

    if out_file:
        write_movie_plan(plan_data, out_file)
        print(f"  Plan written to {out_file}")
        print(f"  {len(plan_data.files)} files listed")
    else:
        write_movie_plan(plan_data, Path("/dev/stdout"))


def _flush_movie_log(log_path: Path | None, lines: list[str]) -> None:
    if log_path and lines:
        with log_path.open("a") as f:
            f.writelines(lines)


def _execute_movie_ops(
    ops: list[tuple[str, str, int, str]],
    *,
    dry_run: bool,
    log_path: Path | None,
) -> None:
    """Execute or preview movie rename ops.

    Each op is (source, dest, tmdb_id, movie_name) from the rename plan.
    """
    import shutil

    log_lines: list[str] = []
    count = 0
    for source_str, dest_str, tmdb_id, movie_name in ops:
        source = Path(source_str)
        dest = Path(dest_str)
        label = "[DRY RUN] " if dry_run else ""
        print(f"  {label}{source.name}")
        print(f"    -> {dest}")

        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                _flush_movie_log(log_path, log_lines)
                raise FileExistsError(
                    f"Destination already exists: {source} -> {dest}; "
                    f"{count} of {len(ops)} files already moved"
                )
            try:
                shutil.move(str(source), str(dest))
            except OSError:
                _flush_movie_log(log_path, log_lines)
                raise OSError(
                    f"Failed to move {source} -> {dest}; {count} of {len(ops)} files already moved"
                ) from None
            nfo = write_movie_nfo(dest.parent, movie_name, tmdb_id)
            log_lines.append(f"{source} -> {dest}\n")
            log_lines.append(f"wrote {nfo}\n")
            count += 1

    _flush_movie_log(log_path, log_lines)

    if dry_run:
        print(f"\n  {len(ops)} file(s) would be renamed.")
    else:
        print(f"\n  {count} file(s) renamed.")


def _cmd_movie_rename(args: argparse.Namespace) -> None:
    dry_run: bool = args.dry_run
    log_path = Path(args.log) if args.log else None
    output = Path(args.output) if args.output else None

    if args.plan:
        plan_data = read_movie_plan(Path(args.plan))
        if output:
            plan_data.output = str(output)
        client: TMDBClient | None = None
        needs_lookup = any(
            e.tmdb_id is not None and (e.name is None or e.year is None) for e in plan_data.files
        )
        if needs_lookup:
            client = TMDBClient()
        rename_plan = movie_plan_to_renames(plan_data, client=client)
        print(f"\n  Plan: {args.plan}")

        if rename_plan.collisions:
            print("  Collisions detected:\n")
            for dest, srcs in rename_plan.collisions.items():
                print(f"    {dest.name}")
                for src_path in srcs:
                    print(f"      <- {src_path.name}")
            print(f"\n  {len(rename_plan.collisions)} collision(s). No files renamed.")
            sys.exit(1)

        active_entries = [e for e in plan_data.files if e.tmdb_id is not None]
        ops_with_meta: list[tuple[str, str, int, str]] = []
        for op, entry in zip(rename_plan.ops, active_entries, strict=True):
            ops_with_meta.append(
                (str(op.source), str(op.dest), entry.tmdb_id, entry.name or "")  # type: ignore[arg-type]
            )

        if rename_plan.unmatched:
            print(f"\n  Skipped ({len(rename_plan.unmatched)}):")
            for p in rename_plan.unmatched:
                print(f"    {p.name}")

        _execute_movie_ops(ops_with_meta, dry_run=dry_run, log_path=log_path)
    else:
        if not args.file or args.id is None:
            print("error: provide either --plan or both file and --id", file=sys.stderr)
            sys.exit(1)
        client_single: TMDBClient = args.client
        movie = client_single.get_movie(args.id)
        file = Path(args.file)
        print(f"\n  Movie: {movie.name} ({movie.year})")

        op = plan_movie_rename(
            file,
            movie_name=movie.name,
            year=movie.year,
            tmdb_id=movie.tmdb_id,
            output=output,
        )

        _execute_movie_ops(
            [(str(op.source), str(op.dest), movie.tmdb_id, movie.name)],
            dry_run=dry_run,
            log_path=log_path,
        )


def _http_message(exc: HTTPError) -> str:
    if exc.response is not None:
        if exc.response.status_code == 401:
            return "TMDB_API_KEY is invalid or expired"
        if exc.response.status_code == 404:
            return "no such TMDB id"
    return str(exc)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="tv-renamer",
        description="Rename and organize TV and movie media files for Jellyfin.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = sub.add_parser("scan", help="Inventory a directory of media files")
    p_scan.add_argument("directory", help="Directory to scan")
    p_scan.set_defaults(func=_cmd_scan)

    # search
    p_search = sub.add_parser("search", help="Search TMDB for a show or movie")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument(
        "--type",
        choices=["tv", "movie", "both"],
        default="both",
        help="Search type (default: both)",
    )
    p_search.set_defaults(func=_cmd_search, needs_client=True)

    # episodes
    p_ep = sub.add_parser("episodes", help="List episodes for a TMDB show")
    p_ep.add_argument("id", type=int, help="TMDB show ID")
    p_ep.add_argument("--season", type=int, default=None, help="Season number")
    p_ep.set_defaults(func=_cmd_episodes, needs_client=True)

    # plan
    p_plan = sub.add_parser("plan", help="Generate a YAML rename plan for editing")
    p_plan.add_argument("directory", help="Directory containing episodes")
    p_plan.add_argument("--id", type=int, required=True, help="TMDB show ID")
    p_plan.add_argument("--season", type=int, default=None, help="Force season number")
    p_plan.add_argument("-o", "--out", default=None, help="Output YAML file (default: stdout)")
    p_plan.set_defaults(func=_cmd_plan, needs_client=True)

    # rename
    p_rename = sub.add_parser("rename", help="Rename episodes to Jellyfin format")
    p_rename.add_argument(
        "directory", nargs="?", default=None, help="Directory containing episodes"
    )
    p_rename.add_argument("--id", type=int, default=None, help="TMDB show ID")
    p_rename.add_argument("--season", type=int, default=None, help="Force season number")
    p_rename.add_argument("--output", default=None, help="Output root directory")
    p_rename.add_argument("--dry-run", action="store_true", help="Preview without renaming")
    p_rename.add_argument("--log", default=None, help="Log file path")
    p_rename.add_argument("--plan", default=None, help="YAML plan file (replaces directory/--id)")
    p_rename.set_defaults(func=_cmd_rename)

    # movie
    p_movie = sub.add_parser("movie", help="Show details for a TMDB movie")
    p_movie.add_argument("id", type=int, help="TMDB movie ID")
    p_movie.set_defaults(func=_cmd_movie, needs_client=True)

    # movie-plan
    p_mplan = sub.add_parser("movie-plan", help="Generate a YAML movie plan for editing")
    p_mplan.add_argument("directory", help="Directory containing movie files")
    p_mplan.add_argument("-o", "--out", default=None, help="Output YAML file (default: stdout)")
    p_mplan.set_defaults(func=_cmd_movie_plan)

    # movie-rename
    p_mren = sub.add_parser("movie-rename", help="Rename movie file(s) to Jellyfin format")
    p_mren.add_argument("file", nargs="?", default=None, help="Movie file to rename")
    p_mren.add_argument("--id", type=int, default=None, help="TMDB movie ID")
    p_mren.add_argument("--plan", default=None, help="YAML plan file (replaces file/--id)")
    p_mren.add_argument("--output", default=None, help="Output root directory")
    p_mren.add_argument("--dry-run", action="store_true", help="Preview without renaming")
    p_mren.add_argument("--log", default=None, help="Log file path")
    p_mren.set_defaults(func=_cmd_movie_rename)

    # undo
    p_undo = sub.add_parser("undo", help="Reverse a logged rename batch")
    p_undo.add_argument("--log", required=True, help="Log file from a rename run")
    p_undo.add_argument("--dry-run", action="store_true", help="Preview without undoing")
    p_undo.set_defaults(func=_cmd_undo)

    # copy
    p_copy = sub.add_parser("copy", help="Copy organized files to NAS")
    p_copy.add_argument("source", help="Source directory")
    p_copy.add_argument("--dest", required=True, help="Destination directory")
    p_copy.add_argument("--dry-run", action="store_true", help="Preview without copying")
    p_copy.set_defaults(func=_cmd_copy)

    args = parser.parse_args(argv)

    try:
        needs_client = getattr(args, "needs_client", False)
        if args.command == "rename" and not args.plan:
            needs_client = True
        if args.command == "movie-rename" and not getattr(args, "plan", None):
            needs_client = True
        if needs_client:
            args.client = TMDBClient()
        args.func(args)
    except HTTPError as exc:
        print(f"error: {_http_message(exc)}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        msg = exc.stderr.strip() if exc.stderr else f"rsync exited with status {exc.returncode}"
        print(f"error: {msg}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
