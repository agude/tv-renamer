"""Tests for directory scanning and classification."""

from pathlib import Path

from tv_renamer.scanner import scan_directory


def test_scan_empty(tmp_path: Path):
    result = scan_directory(tmp_path)
    assert result.shows == []
    assert result.loose_files == []
    assert result.movies == []


def test_scan_loose_files(tmp_path: Path):
    (tmp_path / "Movie Title.mkv").touch()
    (tmp_path / "Another Movie.mp4").touch()
    (tmp_path / "readme.txt").touch()

    result = scan_directory(tmp_path)
    assert len(result.movies) == 2
    assert result.loose_files == []
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
    assert len(result.movies) == 1
    assert len(result.shows) == 1


class TestSeasonFolderDetection:
    def test_subs_not_season_folder(self, tmp_path: Path):
        show = tmp_path / "Show"
        subs = show / "Subs"
        subs.mkdir(parents=True)
        (subs / "eng.srt").touch()
        (show / "S01E01.mkv").touch()

        result = scan_directory(tmp_path)
        assert not result.shows[0].has_season_folders

    def test_sample_not_season_folder(self, tmp_path: Path):
        show = tmp_path / "Show"
        sample = show / "Sample"
        sample.mkdir(parents=True)
        (show / "S01E01.mkv").touch()

        result = scan_directory(tmp_path)
        assert not result.shows[0].has_season_folders

    def test_screenshots_not_season_folder(self, tmp_path: Path):
        show = tmp_path / "Show"
        ss = show / "Screenshots"
        ss.mkdir(parents=True)
        (show / "S01E01.mkv").touch()

        result = scan_directory(tmp_path)
        assert not result.shows[0].has_season_folders

    def test_season_1_recognized(self, tmp_path: Path):
        show = tmp_path / "Show"
        (show / "Season 1").mkdir(parents=True)

        result = scan_directory(tmp_path)
        assert result.shows[0].has_season_folders

    def test_lowercase_season_recognized(self, tmp_path: Path):
        show = tmp_path / "Show"
        (show / "season 1").mkdir(parents=True)

        result = scan_directory(tmp_path)
        assert result.shows[0].has_season_folders

    def test_s01_recognized(self, tmp_path: Path):
        show = tmp_path / "Show"
        (show / "S01").mkdir(parents=True)

        result = scan_directory(tmp_path)
        assert result.shows[0].has_season_folders

    def test_specials_recognized(self, tmp_path: Path):
        show = tmp_path / "Show"
        (show / "Specials").mkdir(parents=True)

        result = scan_directory(tmp_path)
        assert result.shows[0].has_season_folders


class TestDeepRecursion:
    def test_nested_media_counted(self, tmp_path: Path):
        show = tmp_path / "Show"
        deep = show / "Season 1" / "extras" / "behind_the_scenes"
        deep.mkdir(parents=True)
        (deep / "ep01.mkv").touch()
        (show / "Season 1" / "S01E01.mkv").touch()

        result = scan_directory(tmp_path)
        assert result.shows[0].episode_count == 2

    def test_dotdir_skipped_in_show(self, tmp_path: Path):
        show = tmp_path / "Show"
        dotdir = show / ".hidden"
        dotdir.mkdir(parents=True)
        (dotdir / "secret.mkv").touch()
        (show / "S01E01.mkv").touch()

        result = scan_directory(tmp_path)
        assert result.shows[0].episode_count == 1


class TestMovieClassification:
    def test_movie_file_classified(self, tmp_path: Path):
        (tmp_path / "Movie Title (2020).mkv").touch()

        result = scan_directory(tmp_path)
        assert len(result.movies) == 1
        assert result.movies[0].name == "Movie Title (2020).mkv"
        assert len(result.loose_files) == 0

    def test_episode_file_classified_as_loose(self, tmp_path: Path):
        (tmp_path / "S01E01 - Pilot.mkv").touch()

        result = scan_directory(tmp_path)
        assert len(result.loose_files) == 1
        assert result.loose_files[0].name == "S01E01 - Pilot.mkv"
        assert len(result.movies) == 0

    def test_mixed_movies_and_episodes(self, tmp_path: Path):
        (tmp_path / "Movie Title (2020).mkv").touch()
        (tmp_path / "S01E01 - Pilot.mkv").touch()

        result = scan_directory(tmp_path)
        assert len(result.movies) == 1
        assert len(result.loose_files) == 1
