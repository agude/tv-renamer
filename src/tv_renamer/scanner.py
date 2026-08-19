"""Directory inventory and file classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tv_renamer.tmdb import MEDIA_EXTENSIONS


@dataclass
class ShowEntry:
    path: Path
    name: str
    episode_count: int = 0
    has_season_folders: bool = False
    sample_files: list[str] = field(default_factory=list)


@dataclass
class LooseFile:
    path: Path
    name: str


@dataclass
class ScanResult:
    root: Path
    shows: list[ShowEntry] = field(default_factory=list)
    loose_files: list[LooseFile] = field(default_factory=list)


def scan_directory(root: Path) -> ScanResult:
    """Inventory a directory of media files.

    Directories become show entries; files at the top level become loose files
    (likely movies or misplaced episodes).
    """
    result = ScanResult(root=root)

    for entry in sorted(root.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            show = _scan_show(entry)
            result.shows.append(show)
        elif entry.is_file() and entry.suffix.lower() in MEDIA_EXTENSIONS:
            result.loose_files.append(LooseFile(path=entry, name=entry.name))

    return result


def _scan_show(show_dir: Path) -> ShowEntry:
    """Scan a single show directory."""
    media_files: list[str] = []
    has_season_folders = False

    for entry in sorted(show_dir.iterdir()):
        if entry.is_dir():
            subdir_name = entry.name.lower()
            if subdir_name.startswith("s") or subdir_name.startswith("season"):
                has_season_folders = True
            for f in entry.iterdir():
                if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS:
                    media_files.append(f.name)
        elif entry.is_file() and entry.suffix.lower() in MEDIA_EXTENSIONS:
            media_files.append(entry.name)

    return ShowEntry(
        path=show_dir,
        name=show_dir.name,
        episode_count=len(media_files),
        has_season_folders=has_season_folders,
        sample_files=media_files[:3],
    )
