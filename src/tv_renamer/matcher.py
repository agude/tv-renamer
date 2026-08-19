"""Extract episode numbers from filenames with varied naming conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tv_renamer.constants import MEDIA_EXTENSIONS


@dataclass(frozen=True)
class FileMatch:
    path: Path
    season: int | None
    episode: int | None
    episode_end: int | None = None
    pattern: str | None = None

    @property
    def matched(self) -> bool:
        return self.episode is not None


_MULTI_EP = re.compile(r"S(\d{1,2})E(\d{1,4})(?:-E?|E)(\d{1,4})", re.IGNORECASE)

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # S01E01 or S01E001
    ("sXXeXX", re.compile(r"S(\d{1,2})E(\d{1,4})", re.IGNORECASE)),
    # [S01.E01]
    ("bracket", re.compile(r"\[S(\d{1,2})\.E(\d{1,4})\]", re.IGNORECASE)),
    # 1x01
    ("XxXX", re.compile(r"(?<!\d)(\d{1,2})x(\d{2,4})(?!\d)", re.IGNORECASE)),
]

_RESOLUTION_HEIGHTS = frozenset({480, 576, 720, 1080, 1440, 2160})

# Bare number: leading ("01 - title.mp4") or trailing after non-digit chars ("死神粤语01.ts")
_BARE_LEADING = re.compile(r"^(\d{1,4})")
_BARE_TRAILING = re.compile(r"(?<!\d)(\d{1,4})$")


def extract_episode(
    filename: str,
) -> tuple[int | None, int | None, int | None, str | None]:
    """Return (season, episode, episode_end, pattern) parsed from a filename.

    episode_end is set for multi-episode files (e.g. S01E01-E02).
    pattern identifies which regex matched (bare_leading, bare_trailing, etc.).
    Returns (None, None, None, None) if no pattern matches.
    """
    m = _MULTI_EP.search(filename)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3)), "multi"

    for name, pat in _PATTERNS:
        m = pat.search(filename)
        if m:
            season_num, ep_num = int(m.group(1)), int(m.group(2))
            if name == "XxXX" and ep_num in _RESOLUTION_HEIGHTS:
                continue
            return season_num, ep_num, None, name

    m = _BARE_LEADING.match(filename)
    if m:
        num = int(m.group(1))
        if num > 0:
            return None, num, None, "bare_leading"

    stem = Path(filename).stem
    m = _BARE_TRAILING.search(stem)
    if m:
        candidate = int(m.group(1))
        if candidate > 0:
            return None, candidate, None, "bare_trailing"

    return None, None, None, None


def match_files(directory: Path) -> list[FileMatch]:
    """Match all media files in a directory to episode numbers."""
    results: list[FileMatch] = []
    for f in sorted(directory.iterdir()):
        if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS:
            season, episode, episode_end, pattern = extract_episode(f.name)
            results.append(
                FileMatch(
                    path=f,
                    season=season,
                    episode=episode,
                    episode_end=episode_end,
                    pattern=pattern,
                )
            )
    return results
