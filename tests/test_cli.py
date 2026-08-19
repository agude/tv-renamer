"""Tests for CLI argument parsing and subcommand wiring."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tv_renamer.cli import main
from tv_renamer.tmdb import Episode, SearchResult, SeasonSummary, ShowInfo


def test_no_args_exits():
    with pytest.raises(SystemExit):
        main([])


def test_scan_missing_dir():
    with pytest.raises(SystemExit):
        main(["scan"])


def test_rename_requires_id():
    with pytest.raises(SystemExit):
        main(["rename", "/tmp/fake"])


class TestScanCommand:
    @patch("tv_renamer.cli.scan_directory")
    def test_scan_calls_scanner(self, mock_scan, tmp_path: Path, capsys):
        from tv_renamer.scanner import ScanResult

        mock_scan.return_value = ScanResult(root=tmp_path)
        main(["scan", str(tmp_path)])

        mock_scan.assert_called_once_with(tmp_path)

    @patch("tv_renamer.cli.scan_directory")
    def test_scan_prints_loose_files(self, mock_scan, tmp_path: Path, capsys):
        from tv_renamer.scanner import LooseFile, ScanResult

        mock_scan.return_value = ScanResult(
            root=tmp_path,
            loose_files=[LooseFile(path=tmp_path / "movie.mkv", name="movie.mkv")],
        )
        main(["scan", str(tmp_path)])
        out = capsys.readouterr().out
        assert "Loose files" in out
        assert "movie.mkv" in out

    @patch("tv_renamer.cli.scan_directory")
    def test_scan_prints_shows(self, mock_scan, tmp_path: Path, capsys):
        from tv_renamer.scanner import ScanResult, ShowEntry

        mock_scan.return_value = ScanResult(
            root=tmp_path,
            shows=[
                ShowEntry(
                    path=tmp_path / "Breaking Bad",
                    name="Breaking Bad",
                    episode_count=5,
                    has_season_folders=True,
                    sample_files=["S01E01.mkv"],
                )
            ],
        )
        main(["scan", str(tmp_path)])
        out = capsys.readouterr().out
        assert "Breaking Bad" in out
        assert "5 episodes" in out
        assert "season folders" in out


class TestSearchCommand:
    @patch("tv_renamer.cli.search_tv")
    @patch("tv_renamer.cli.search_movie")
    def test_search_both_by_default(self, mock_movie, mock_tv, capsys):
        mock_tv.return_value = [
            SearchResult(
                tmdb_id=1, name="Test", first_air_date="2020-01-01", overview="", media_type="tv"
            ),
        ]
        mock_movie.return_value = []
        main(["search", "test"])

        mock_tv.assert_called_once_with("test")
        mock_movie.assert_called_once_with("test")

    @patch("tv_renamer.cli.search_tv")
    @patch("tv_renamer.cli.search_movie")
    def test_search_tv_only(self, mock_movie, mock_tv, capsys):
        mock_tv.return_value = []
        main(["search", "test", "--type", "tv"])

        mock_tv.assert_called_once()
        mock_movie.assert_not_called()

    @patch("tv_renamer.cli.search_tv")
    @patch("tv_renamer.cli.search_movie")
    def test_search_movie_only(self, mock_movie, mock_tv, capsys):
        mock_movie.return_value = []
        main(["search", "test", "--type", "movie"])

        mock_tv.assert_not_called()
        mock_movie.assert_called_once()

    @patch("tv_renamer.cli.search_tv")
    @patch("tv_renamer.cli.search_movie")
    def test_search_prints_results(self, mock_movie, mock_tv, capsys):
        mock_tv.return_value = [
            SearchResult(
                tmdb_id=246,
                name="Avatar",
                first_air_date="2005-02-21",
                overview="An animated series about the Avatar.",
                media_type="tv",
            ),
        ]
        mock_movie.return_value = []
        main(["search", "avatar"])

        out = capsys.readouterr().out
        assert "[246]" in out
        assert "Avatar" in out
        assert "2005" in out


class TestEpisodesCommand:
    @patch("tv_renamer.cli.get_episodes")
    @patch("tv_renamer.cli.get_show")
    def test_episodes_all_seasons(self, mock_show, mock_eps, capsys):
        mock_show.return_value = ShowInfo(
            tmdb_id=246,
            name="Avatar",
            first_air_date="2005-02-21",
            seasons=[
                SeasonSummary(season_number=1, episode_count=2, name="Book One"),
                SeasonSummary(season_number=2, episode_count=1, name="Book Two"),
            ],
        )
        mock_eps.side_effect = [
            [
                Episode(season=1, episode=1, name="Pilot"),
                Episode(season=1, episode=2, name="Second"),
            ],
            [Episode(season=2, episode=1, name="Premiere")],
        ]

        main(["episodes", "246"])

        assert mock_eps.call_count == 2
        out = capsys.readouterr().out
        assert "Season 1" in out
        assert "Season 2" in out

    @patch("tv_renamer.cli.get_episodes")
    @patch("tv_renamer.cli.get_show")
    def test_episodes_single_season(self, mock_show, mock_eps, capsys):
        mock_show.return_value = ShowInfo(
            tmdb_id=1,
            name="Test",
            first_air_date="2020-01-01",
            seasons=[SeasonSummary(season_number=1, episode_count=1, name="S1")],
        )
        mock_eps.return_value = [Episode(season=1, episode=1, name="Pilot")]

        main(["episodes", "1", "--season", "1"])

        mock_eps.assert_called_once_with(1, 1)


class TestRenameCommand:
    @patch("tv_renamer.cli.get_episodes")
    @patch("tv_renamer.cli.get_show")
    def test_rename_dry_run(self, mock_show, mock_eps, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01 - Pilot.mp4").write_text("data")

        mock_show.return_value = ShowInfo(
            tmdb_id=99999,
            name="Test Show",
            first_air_date="2020-01-01",
            seasons=[],
        )
        mock_eps.return_value = [Episode(season=1, episode=1, name="Pilot")]

        main(["rename", str(src), "--id", "99999", "--season", "1", "--dry-run"])

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "would be renamed" in out
        assert (src / "S01E01 - Pilot.mp4").exists()

    @patch("tv_renamer.cli.get_episodes")
    @patch("tv_renamer.cli.get_show")
    def test_rename_executes(self, mock_show, mock_eps, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mp4").write_text("data")

        mock_show.return_value = ShowInfo(
            tmdb_id=99999,
            name="Test Show",
            first_air_date="2020-01-01",
            seasons=[],
        )
        mock_eps.return_value = [Episode(season=1, episode=1, name="Pilot")]

        main(["rename", str(src), "--id", "99999", "--season", "1"])

        out = capsys.readouterr().out
        assert "1 files renamed" in out
        assert not (src / "S01E01.mp4").exists()

    @patch("tv_renamer.cli.get_episodes")
    @patch("tv_renamer.cli.get_show")
    def test_rename_no_matches(self, mock_show, mock_eps, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "random.mkv").touch()

        mock_show.return_value = ShowInfo(
            tmdb_id=1,
            name="Show",
            first_air_date="2020-01-01",
            seasons=[],
        )
        mock_eps.return_value = [Episode(season=1, episode=1, name="Pilot")]

        main(["rename", str(src), "--id", "1", "--season", "1"])

        out = capsys.readouterr().out
        assert "No files matched" in out

    @patch("tv_renamer.cli.get_episodes")
    @patch("tv_renamer.cli.get_show")
    def test_rename_collisions_exit_nonzero(self, mock_show, mock_eps, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mkv").touch()
        (src / "01 - other rip.mkv").touch()

        mock_show.return_value = ShowInfo(
            tmdb_id=99999,
            name="Test Show",
            first_air_date="2020-01-01",
            seasons=[],
        )
        mock_eps.return_value = [Episode(season=1, episode=1, name="Pilot")]

        with pytest.raises(SystemExit, match="1"):
            main(["rename", str(src), "--id", "99999", "--season", "1"])

        out = capsys.readouterr().out
        assert "Collisions" in out
        assert (src / "S01E01.mkv").exists()
        assert (src / "01 - other rip.mkv").exists()

    @patch("tv_renamer.cli.get_episodes")
    @patch("tv_renamer.cli.get_show")
    def test_rename_collisions_dry_run_exit_nonzero(
        self, mock_show, mock_eps, tmp_path: Path, capsys
    ):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mkv").touch()
        (src / "01 - other rip.mkv").touch()

        mock_show.return_value = ShowInfo(
            tmdb_id=99999,
            name="Test Show",
            first_air_date="2020-01-01",
            seasons=[],
        )
        mock_eps.return_value = [Episode(season=1, episode=1, name="Pilot")]

        with pytest.raises(SystemExit, match="1"):
            main(["rename", str(src), "--id", "99999", "--season", "1", "--dry-run"])

        out = capsys.readouterr().out
        assert "Collisions" in out


class TestCopyCommand:
    @patch("tv_renamer.cli.copy_to_dest")
    def test_copy_calls_copier(self, mock_copy, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"

        main(["copy", str(src), "--dest", str(dest)])

        mock_copy.assert_called_once_with(src, dest, dry_run=False)

    @patch("tv_renamer.cli.copy_to_dest")
    def test_copy_dry_run(self, mock_copy, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"

        main(["copy", str(src), "--dest", str(dest), "--dry-run"])

        mock_copy.assert_called_once_with(src, dest, dry_run=True)
        out = capsys.readouterr().out
        assert "DRY RUN" in out
