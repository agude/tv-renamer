"""Tests for episode number extraction from filenames."""

from pathlib import Path

import pytest

from tv_renamer.matcher import FileMatch, extract_episode, match_files


@pytest.mark.parametrize(
    "filename, expected",
    [
        # S01E01 format
        ("Show - S01E01 - Pilot.mp4", (1, 1, None)),
        ("S02E13.mkv", (2, 13, None)),
        ("show.s03e005.title.ts", (3, 5, None)),
        # [S01.E01] bracket format
        ("[S01.E01] Avatar The Last Airbender - The Boy in the Iceberg.mp4", (1, 1, None)),
        ("[S03.E21] Show Name - Title.mkv", (3, 21, None)),
        # 1x01 format
        ("Show 1x01 Pilot.mp4", (1, 1, None)),
        ("2x13 - Title.mkv", (2, 13, None)),
        # Bare leading number
        ("01 - Title.mp4", (None, 1, None)),
        ("001Title.ts", (None, 1, None)),
        ("10神奇宝贝乡的妙蛙种子.mp4", (None, 10, None)),
        ("死神粤语01.ts", (None, 1, None)),
        # No match
        ("Movie Title (2020).mkv", (None, None, None)),
        ("README.txt", (None, None, None)),
        # Zero is not a valid episode
        ("00 intro.mp4", (None, None, None)),
    ],
)
def test_extract_episode(filename: str, expected: tuple[int | None, int | None, int | None]):
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
        ("Show 1920x1080 BluRay.mkv", (None, None, None)),
        ("Show 1280x720 BluRay.mkv", (None, None, None)),
        ("Show 720x480 BluRay.mkv", (None, None, None)),
        ("Show 1x01 Pilot.mp4", (1, 1, None)),
        ("2x13 - Title.mkv", (2, 13, None)),
        ("1x100 - Title.mp4", (1, 100, None)),
    ],
)
def test_extract_episode_resolution_not_matched(
    filename: str, expected: tuple[int | None, int | None, int | None]
):
    assert extract_episode(filename) == expected


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("ep12345.mkv", (None, None, None)),
        # Known false positive until commit 12 bounds bare numbers by episode count
        ("Show.name.2020.mkv", (None, 2020, None)),
    ],
)
def test_extract_episode_trailing_anchored(
    filename: str, expected: tuple[int | None, int | None, int | None]
):
    assert extract_episode(filename) == expected


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Show - S01E01-E02.mkv", (1, 1, 2)),
        ("S01E01-02.mkv", (1, 1, 2)),
        ("S01E01E02.mkv", (1, 1, 2)),
        ("Show - S02E05-E06 - Double Feature.mp4", (2, 5, 6)),
        # Single episode is not affected
        ("S01E01.mkv", (1, 1, None)),
    ],
)
def test_extract_episode_multi_episode(
    filename: str, expected: tuple[int | None, int | None, int | None]
):
    assert extract_episode(filename) == expected


@pytest.mark.parametrize(
    "filename, expected",
    [
        # Multi-digit episode numbers (anime)
        ("S01E100.mkv", (1, 100, None)),
        ("S01E0100.mkv", (1, 100, None)),
        ("S01E1000.mkv", (1, 1000, None)),
        # Double-digit seasons
        ("S10E01.mkv", (10, 1, None)),
        ("S99E99.mkv", (99, 99, None)),
        # 1x format with large episodes
        ("1x100 - Title.mp4", (1, 100, None)),
        # Large bare numbers
        ("100 Title.mp4", (None, 100, None)),
        ("1000 Title.mp4", (None, 1000, None)),
    ],
)
def test_extract_episode_multi_digit(
    filename: str, expected: tuple[int | None, int | None, int | None]
):
    assert extract_episode(filename) == expected
