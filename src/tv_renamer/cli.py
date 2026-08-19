"""Argparse entry point for all subcommands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from tv_renamer.copier import copy_to_dest
from tv_renamer.renamer import execute_renames, plan_renames
from tv_renamer.scanner import scan_directory
from tv_renamer.tmdb import get_episodes, get_show, search_movie, search_tv


def _cmd_scan(args: argparse.Namespace) -> None:
    result = scan_directory(Path(args.directory))

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
    query = args.query
    media_type: str = args.type

    if media_type in ("tv", "both"):
        results = search_tv(query)
        if results:
            print("\n  TV Shows:")
            for r in results[:10]:
                print(f"    [{r.tmdb_id}] {r.name} ({r.year})")
                if r.overview:
                    print(f"      {r.overview[:120]}")

    if media_type in ("movie", "both"):
        results = search_movie(query)
        if results:
            print("\n  Movies:")
            for r in results[:10]:
                print(f"    [{r.tmdb_id}] {r.name} ({r.year})")
                if r.overview:
                    print(f"      {r.overview[:120]}")


def _cmd_episodes(args: argparse.Namespace) -> None:
    tmdb_id: int = args.id
    show = get_show(tmdb_id)
    print(f"\n  {show.name} ({show.year})")

    if args.season is not None:
        seasons_to_show = [args.season]
    else:
        seasons_to_show = [s.season_number for s in show.seasons]

    for sn in seasons_to_show:
        episodes = get_episodes(tmdb_id, sn)
        print(f"\n  Season {sn} ({len(episodes)} episodes):")
        for ep in episodes:
            print(f"    S{ep.season:02d}E{ep.episode:02d} - {ep.name}")


def _cmd_rename(args: argparse.Namespace) -> None:
    tmdb_id: int = args.id
    directory = Path(args.directory)
    dry_run: bool = args.dry_run
    season_override: int | None = args.season
    log_path = Path(args.log) if args.log else None
    output = Path(args.output) if args.output else None

    show = get_show(tmdb_id)
    print(f"\n  Show: {show.name} ({show.year})")

    if season_override is not None:
        all_episodes = get_episodes(tmdb_id, season_override)
    else:
        all_episodes = []
        for s in show.seasons:
            all_episodes.extend(get_episodes(tmdb_id, s.season_number))

    ops = plan_renames(
        directory,
        show_name=show.name,
        year=show.year,
        episodes=all_episodes,
        output=output,
        season_override=season_override,
    )

    if not ops:
        print("  No files matched.")
        return

    for op in ops:
        label = "[DRY RUN] " if dry_run else ""
        print(f"  {label}{op.source.name}")
        print(f"    -> {op.dest}")

    if dry_run:
        print(f"\n  {len(ops)} files would be renamed.")
    else:
        count = execute_renames(ops, log_path=log_path)
        print(f"\n  {count} files renamed.")


def _cmd_copy(args: argparse.Namespace) -> None:
    source = Path(args.source)
    dest = Path(args.dest)
    dry_run: bool = args.dry_run

    label = "[DRY RUN] " if dry_run else ""
    print(f"  {label}Copying {source} -> {dest}")
    copy_to_dest(source, dest, dry_run=dry_run)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="tv-renamer",
        description="Rename and organize TV media files for Jellyfin.",
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
    p_search.set_defaults(func=_cmd_search)

    # episodes
    p_ep = sub.add_parser("episodes", help="List episodes for a TMDB show")
    p_ep.add_argument("id", type=int, help="TMDB show ID")
    p_ep.add_argument("--season", type=int, default=None, help="Season number")
    p_ep.set_defaults(func=_cmd_episodes)

    # rename
    p_rename = sub.add_parser("rename", help="Rename episodes to Jellyfin format")
    p_rename.add_argument("directory", help="Directory containing episodes")
    p_rename.add_argument("--id", type=int, required=True, help="TMDB show ID")
    p_rename.add_argument("--season", type=int, default=None, help="Force season number")
    p_rename.add_argument("--output", default=None, help="Output root directory")
    p_rename.add_argument("--dry-run", action="store_true", help="Preview without renaming")
    p_rename.add_argument("--log", default=None, help="Log file path")
    p_rename.set_defaults(func=_cmd_rename)

    # copy
    p_copy = sub.add_parser("copy", help="Copy organized files to NAS")
    p_copy.add_argument("source", help="Source directory")
    p_copy.add_argument("--dest", required=True, help="Destination directory")
    p_copy.add_argument("--dry-run", action="store_true", help="Preview without copying")
    p_copy.set_defaults(func=_cmd_copy)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
