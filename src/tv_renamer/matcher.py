"""Extract episode numbers from filenames with varied naming conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tv_renamer.tmdb import MEDIA_EXTENSIONS


@dataclass(frozen=True)
class FileMatch:
    path: Path
    season: int | None
    episode: int | None

    @property
    def matched(self) -> bool:
        return self.episode is not None


_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # S01E01 or S01E001
    ("sXXeXX", re.compile(r"S(\d{1,2})E(\d{1,4})", re.IGNORECASE)),
    # [S01.E01]
    ("bracket", re.compile(r"\[S(\d{1,2})\.E(\d{1,4})\]", re.IGNORECASE)),
    # 1x01
    ("XxXX", re.compile(r"(\d{1,2})x(\d{2,4})", re.IGNORECASE)),
]

# Bare number: leading ("01 - title.mp4") or trailing after non-digit chars ("死神粤语01.ts")
_BARE_LEADING = re.compile(r"^(\d{1,4})")
_BARE_TRAILING = re.compile(r"(?<!\d)(\d{1,4})$")


def extract_episode(filename: str) -> tuple[int | None, int | None]:
    """Return (season, episode) parsed from a filename.

    Returns (None, None) if no pattern matches.
    """
    for _name, pattern in _PATTERNS:
        m = pattern.search(filename)
        if m:
            return int(m.group(1)), int(m.group(2))

    m = _BARE_LEADING.match(filename)
    if m:
        num = int(m.group(1))
        if num > 0:
            return None, num

    stem = Path(filename).stem
    m = _BARE_TRAILING.search(stem)
    if m:
        candidate = int(m.group(1))
        if candidate > 0:
            return None, candidate

    return None, None


def match_files(directory: Path) -> list[FileMatch]:
    """Match all media files in a directory to episode numbers."""
    results: list[FileMatch] = []
    for f in sorted(directory.iterdir()):
        if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS:
            season, episode = extract_episode(f.name)
            results.append(FileMatch(path=f, season=season, episode=episode))
    return results
