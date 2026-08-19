"""Tests for directory scanning and classification."""

from pathlib import Path

from tv_renamer.scanner import scan_directory


def test_scan_empty(tmp_path: Path):
    result = scan_directory(tmp_path)
    assert result.shows == []
    assert result.loose_files == []


def test_scan_loose_files(tmp_path: Path):
    (tmp_path / "Movie Title.mkv").touch()
    (tmp_path / "Another Movie.mp4").touch()
    (tmp_path / "readme.txt").touch()

    result = scan_directory(tmp_path)
    assert len(result.loose_files) == 2
    assert result.shows == []


def test_scan_show_directory(tmp_path: Path):
    show_dir = tmp_path / "Breaking Bad"
    show_dir.mkdir()
    (show_dir / "S01E01 - Pilot.mkv").touch()
    (show_dir / "S01E02 - Cats in the Bag.mkv").touch()

    result = scan_directory(tmp_path)
    assert len(result.shows) == 1
    assert result.shows[0].name == "Breaking Bad"
    assert result.shows[0].episode_count == 2
    assert not result.shows[0].has_season_folders


def test_scan_with_season_folders(tmp_path: Path):
    show_dir = tmp_path / "Avatar"
    s1 = show_dir / "Season 1"
    s1.mkdir(parents=True)
    (s1 / "S01E01.mp4").touch()
    (s1 / "S01E02.mp4").touch()

    result = scan_directory(tmp_path)
    assert result.shows[0].has_season_folders
    assert result.shows[0].episode_count == 2


def test_scan_mixed(tmp_path: Path):
    (tmp_path / "Loose Movie.mkv").touch()
    show = tmp_path / "Some Show"
    show.mkdir()
    (show / "ep01.mp4").touch()

    result = scan_directory(tmp_path)
    assert len(result.loose_files) == 1
    assert len(result.shows) == 1
