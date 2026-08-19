"""Tests for episode number extraction from filenames."""

from pathlib import Path

import pytest

from tv_renamer.matcher import FileMatch, extract_episode, match_files


@pytest.mark.parametrize(
    "filename, expected",
    [
        # S01E01 format
        ("Show - S01E01 - Pilot.mp4", (1, 1)),
        ("S02E13.mkv", (2, 13)),
        ("show.s03e005.title.ts", (3, 5)),
        # [S01.E01] bracket format
        ("[S01.E01] Avatar The Last Airbender - The Boy in the Iceberg.mp4", (1, 1)),
        ("[S03.E21] Show Name - Title.mkv", (3, 21)),
        # 1x01 format
        ("Show 1x01 Pilot.mp4", (1, 1)),
        ("2x13 - Title.mkv", (2, 13)),
        # Bare leading number
        ("01 - Title.mp4", (None, 1)),
        ("001Title.ts", (None, 1)),
        ("10神奇宝贝乡的妙蛙种子.mp4", (None, 10)),
        ("死神粤语01.ts", (None, 1)),
        # No match
        ("Movie Title (2020).mkv", (None, None)),
        ("README.txt", (None, None)),
        # Zero is not a valid episode
        ("00 intro.mp4", (None, None)),
    ],
)
def test_extract_episode(filename: str, expected: tuple[int | None, int | None]):
    assert extract_episode(filename) == expected


def test_match_files(tmp_path: Path):
    (tmp_path / "S01E01 - Pilot.mkv").touch()
    (tmp_path / "S01E02 - Second.mkv").touch()
    (tmp_path / "cover.jpg").touch()
    (tmp_path / "notes.txt").touch()

    results = match_files(tmp_path)
    assert len(results) == 2
    assert all(isinstance(r, FileMatch) for r in results)
    assert results[0].episode == 1
    assert results[1].episode == 2


def test_match_files_chinese_names(tmp_path: Path):
    (tmp_path / "死神粤语01.ts").touch()
    (tmp_path / "死神粤语02.ts").touch()
    (tmp_path / "死神粤语03.ts").touch()

    results = match_files(tmp_path)
    assert len(results) == 3
    assert results[0].episode == 1
    assert results[1].episode == 2
    assert results[2].episode == 3
    assert all(r.season is None for r in results)


def test_match_files_excludes_non_media(tmp_path: Path):
    (tmp_path / "S01E01 - Pilot.mkv").touch()
    (tmp_path / "cover.jpg").touch()
    (tmp_path / "notes.txt").touch()
    (tmp_path / "subtitles.srt").touch()

    results = match_files(tmp_path)
    assert len(results) == 1


def test_match_files_unmatched_returns_false(tmp_path: Path):
    (tmp_path / "random_movie.mkv").touch()

    results = match_files(tmp_path)
    assert len(results) == 1
    assert not results[0].matched
    assert results[0].episode is None
    assert results[0].season is None


@pytest.mark.parametrize(
    "filename, expected",
    [
        # Multi-digit episode numbers (anime)
        ("S01E100.mkv", (1, 100)),
        ("S01E0100.mkv", (1, 100)),
        ("S01E1000.mkv", (1, 1000)),
        # Double-digit seasons
        ("S10E01.mkv", (10, 1)),
        ("S99E99.mkv", (99, 99)),
        # 1x format with large episodes
        ("1x100 - Title.mp4", (1, 100)),
        # Large bare numbers
        ("100 Title.mp4", (None, 100)),
        ("1000 Title.mp4", (None, 1000)),
    ],
)
def test_extract_episode_multi_digit(filename: str, expected: tuple[int | None, int | None]):
    assert extract_episode(filename) == expected
