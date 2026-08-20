"""Tests for episode number extraction from filenames."""

from pathlib import Path

import pytest

from tv_renamer.matcher import FileMatch, extract_episode, match_files


@pytest.mark.parametrize(
    "filename, expected",
    [
        # S01E01 format
        ("Show - S01E01 - Pilot.mp4", (1, 1, None, "sXXeXX")),
        ("S02E13.mkv", (2, 13, None, "sXXeXX")),
        ("show.s03e005.title.ts", (3, 5, None, "sXXeXX")),
        # [S01.E01] bracket format
        (
            "[S01.E01] Avatar The Last Airbender - The Boy in the Iceberg.mp4",
            (1, 1, None, "bracket"),
        ),
        ("[S03.E21] Show Name - Title.mkv", (3, 21, None, "bracket")),
        # 1x01 format
        ("Show 1x01 Pilot.mp4", (1, 1, None, "XxXX")),
        ("2x13 - Title.mkv", (2, 13, None, "XxXX")),
        # Bare leading number
        ("01 - Title.mp4", (None, 1, None, "bare_leading")),
        ("001Title.ts", (None, 1, None, "bare_leading")),
        ("10神奇宝贝乡的妙蛙种子.mp4", (None, 10, None, "bare_leading")),
        ("死神粤语01.ts", (None, 1, None, "bare_trailing")),
        # EP prefix (common in CJK rips)
        ("美少女戰士Crystal_EP01 阿兔 Sailor Moon.mp4", (None, 1, None, "ep_prefix")),
        ("Show_EP100.mp4", (None, 100, None, "ep_prefix")),
        ("[粵語] Show_EP42 Title.mp4", (None, 42, None, "ep_prefix")),
        # No match
        ("Movie Title (2020).mkv", (None, None, None, None)),
        ("README.txt", (None, None, None, None)),
        # Zero is not a valid episode
        ("00 intro.mp4", (None, None, None, None)),
    ],
)
def test_extract_episode(
    filename: str, expected: tuple[int | None, int | None, int | None, str | None]
):
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
        ("Show 1920x1080 BluRay.mkv", (None, None, None, None)),
        ("Show 1280x720 BluRay.mkv", (None, None, None, None)),
        ("Show 720x480 BluRay.mkv", (None, None, None, None)),
        ("Show 1x01 Pilot.mp4", (1, 1, None, "XxXX")),
        ("2x13 - Title.mkv", (2, 13, None, "XxXX")),
        ("1x100 - Title.mp4", (1, 100, None, "XxXX")),
    ],
)
def test_extract_episode_resolution_not_matched(
    filename: str, expected: tuple[int | None, int | None, int | None, str | None]
):
    assert extract_episode(filename) == expected


@pytest.mark.parametrize(
    "filename, expected",
    [
        # EP prefix does not match inside words
        ("SETUP01.mkv", (None, 1, None, "bare_trailing")),
        ("SEP01.mkv", (None, 1, None, "bare_trailing")),
        # EP prefix with too many digits falls through
        ("ep12345.mkv", (None, None, None, None)),
        # EP prefix with dot separator
        ("Show_EP.03.mp4", (None, 3, None, "ep_prefix")),
        # EP prefix zero is not valid
        ("EP00.mp4", (None, None, None, None)),
    ],
)
def test_extract_episode_ep_prefix_edge_cases(
    filename: str, expected: tuple[int | None, int | None, int | None, str | None]
):
    assert extract_episode(filename) == expected


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Show.name.2020.mkv", (None, 2020, None, "bare_trailing")),
    ],
)
def test_extract_episode_trailing_anchored(
    filename: str, expected: tuple[int | None, int | None, int | None, str | None]
):
    assert extract_episode(filename) == expected


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Show - S01E01-E02.mkv", (1, 1, 2, "multi")),
        ("S01E01-02.mkv", (1, 1, 2, "multi")),
        ("S01E01E02.mkv", (1, 1, 2, "multi")),
        ("Show - S02E05-E06 - Double Feature.mp4", (2, 5, 6, "multi")),
        # Single episode is not affected
        ("S01E01.mkv", (1, 1, None, "sXXeXX")),
    ],
)
def test_extract_episode_multi_episode(
    filename: str, expected: tuple[int | None, int | None, int | None, str | None]
):
    assert extract_episode(filename) == expected


@pytest.mark.parametrize(
    "filename, expected",
    [
        # Multi-digit episode numbers (anime)
        ("S01E100.mkv", (1, 100, None, "sXXeXX")),
        ("S01E0100.mkv", (1, 100, None, "sXXeXX")),
        ("S01E1000.mkv", (1, 1000, None, "sXXeXX")),
        # Double-digit seasons
        ("S10E01.mkv", (10, 1, None, "sXXeXX")),
        ("S99E99.mkv", (99, 99, None, "sXXeXX")),
        # 1x format with large episodes
        ("1x100 - Title.mp4", (1, 100, None, "XxXX")),
        # Large bare numbers
        ("100 Title.mp4", (None, 100, None, "bare_leading")),
        ("1000 Title.mp4", (None, 1000, None, "bare_leading")),
    ],
)
def test_extract_episode_multi_digit(
    filename: str, expected: tuple[int | None, int | None, int | None, str | None]
):
    assert extract_episode(filename) == expected
