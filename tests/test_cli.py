"""Tests for CLI argument parsing and subcommand wiring."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from requests import HTTPError, Response

from tv_renamer.cli import main
from tv_renamer.tmdb import Episode, MovieInfo, SearchResult, SeasonSummary, ShowInfo


def test_no_args_exits():
    with pytest.raises(SystemExit):
        main([])


def test_scan_missing_dir():
    with pytest.raises(SystemExit):
        main(["scan"])


def test_rename_requires_id():
    with pytest.raises(SystemExit):
        main(["rename", "/tmp/fake"])


def _mock_client(**overrides: object) -> MagicMock:
    client = MagicMock()
    client.search_tv.return_value = overrides.get("search_tv", [])
    client.search_movie.return_value = overrides.get("search_movie", [])
    client.get_show.return_value = overrides.get(
        "get_show",
        ShowInfo(tmdb_id=1, name="Show", first_air_date="2020-01-01", seasons=[]),
    )
    client.get_episodes.return_value = overrides.get("get_episodes", [])
    client.get_movie.return_value = overrides.get(
        "get_movie",
        MovieInfo(tmdb_id=1, name="Movie", release_date="2020-01-01", overview="", runtime=120),
    )
    return client


class TestScanCommand:
    @patch("tv_renamer.cli.scan_directory")
    def test_scan_calls_scanner(self, mock_scan: MagicMock, tmp_path: Path, capsys: object):
        from tv_renamer.scanner import ScanResult

        mock_scan.return_value = ScanResult(root=tmp_path)
        main(["scan", str(tmp_path)])

        mock_scan.assert_called_once_with(tmp_path)

    @patch("tv_renamer.cli.scan_directory")
    def test_scan_prints_loose_files(self, mock_scan: MagicMock, tmp_path: Path, capsys):
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
    def test_scan_prints_movies(self, mock_scan: MagicMock, tmp_path: Path, capsys):
        from tv_renamer.scanner import LooseFile, ScanResult

        mock_scan.return_value = ScanResult(
            root=tmp_path,
            movies=[LooseFile(path=tmp_path / "Movie.mkv", name="Movie.mkv")],
        )
        main(["scan", str(tmp_path)])
        out = capsys.readouterr().out
        assert "Movies" in out
        assert "Movie.mkv" in out

    @patch("tv_renamer.cli.scan_directory")
    def test_scan_prints_shows(self, mock_scan: MagicMock, tmp_path: Path, capsys):
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

    def test_scan_works_without_api_key(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        with patch.dict("os.environ", {}, clear=True):
            main(["scan", str(src)])


class TestSearchCommand:
    @patch("tv_renamer.cli.TMDBClient")
    def test_search_both_by_default(self, MockClient: MagicMock, capsys):
        client = _mock_client(
            search_tv=[
                SearchResult(
                    tmdb_id=1,
                    name="Test",
                    first_air_date="2020-01-01",
                    overview="",
                    media_type="tv",
                ),
            ]
        )
        MockClient.return_value = client
        main(["search", "test"])

        client.search_tv.assert_called_once_with("test")
        client.search_movie.assert_called_once_with("test")

    @patch("tv_renamer.cli.TMDBClient")
    def test_search_tv_only(self, MockClient: MagicMock, capsys):
        client = _mock_client()
        MockClient.return_value = client
        main(["search", "test", "--type", "tv"])

        client.search_tv.assert_called_once()
        client.search_movie.assert_not_called()

    @patch("tv_renamer.cli.TMDBClient")
    def test_search_movie_only(self, MockClient: MagicMock, capsys):
        client = _mock_client()
        MockClient.return_value = client
        main(["search", "test", "--type", "movie"])

        client.search_tv.assert_not_called()
        client.search_movie.assert_called_once()

    @patch("tv_renamer.cli.TMDBClient")
    def test_search_prints_results(self, MockClient: MagicMock, capsys):
        client = _mock_client(
            search_tv=[
                SearchResult(
                    tmdb_id=246,
                    name="Avatar",
                    first_air_date="2005-02-21",
                    overview="An animated series about the Avatar.",
                    media_type="tv",
                ),
            ]
        )
        MockClient.return_value = client
        main(["search", "avatar"])

        out = capsys.readouterr().out
        assert "[246]" in out
        assert "Avatar" in out
        assert "2005" in out


class TestEpisodesCommand:
    @patch("tv_renamer.cli.TMDBClient")
    def test_episodes_all_seasons(self, MockClient: MagicMock, capsys):
        client = _mock_client(
            get_show=ShowInfo(
                tmdb_id=246,
                name="Avatar",
                first_air_date="2005-02-21",
                seasons=[
                    SeasonSummary(season_number=1, episode_count=2, name="Book One"),
                    SeasonSummary(season_number=2, episode_count=1, name="Book Two"),
                ],
            ),
        )
        client.get_episodes.side_effect = [
            [
                Episode(season=1, episode=1, name="Pilot"),
                Episode(season=1, episode=2, name="Second"),
            ],
            [Episode(season=2, episode=1, name="Premiere")],
        ]
        MockClient.return_value = client
        main(["episodes", "246"])

        assert client.get_episodes.call_count == 2
        out = capsys.readouterr().out
        assert "Season 1" in out
        assert "Season 2" in out

    @patch("tv_renamer.cli.TMDBClient")
    def test_episodes_single_season(self, MockClient: MagicMock, capsys):
        client = _mock_client(
            get_show=ShowInfo(
                tmdb_id=1,
                name="Test",
                first_air_date="2020-01-01",
                seasons=[SeasonSummary(season_number=1, episode_count=1, name="S1")],
            ),
        )
        client.get_episodes.return_value = [Episode(season=1, episode=1, name="Pilot")]
        MockClient.return_value = client
        main(["episodes", "1", "--season", "1"])

        client.get_episodes.assert_called_once_with(1, 1)


class TestRenameCommand:
    @patch("tv_renamer.cli.TMDBClient")
    def test_rename_dry_run(self, MockClient: MagicMock, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01 - Pilot.mp4").write_text("data")

        client = _mock_client(
            get_show=ShowInfo(
                tmdb_id=99999, name="Test Show", first_air_date="2020-01-01", seasons=[]
            ),
            get_episodes=[Episode(season=1, episode=1, name="Pilot")],
        )
        MockClient.return_value = client
        main(["rename", str(src), "--id", "99999", "--season", "1", "--dry-run"])

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "would be renamed" in out
        assert (src / "S01E01 - Pilot.mp4").exists()

    @patch("tv_renamer.cli.TMDBClient")
    def test_rename_executes(self, MockClient: MagicMock, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mp4").write_text("data")

        client = _mock_client(
            get_show=ShowInfo(
                tmdb_id=99999, name="Test Show", first_air_date="2020-01-01", seasons=[]
            ),
            get_episodes=[Episode(season=1, episode=1, name="Pilot")],
        )
        MockClient.return_value = client
        main(["rename", str(src), "--id", "99999", "--season", "1"])

        out = capsys.readouterr().out
        assert "1 files renamed" in out
        assert not (src / "S01E01.mp4").exists()

    @patch("tv_renamer.cli.TMDBClient")
    def test_rename_no_matches(self, MockClient: MagicMock, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "random.mkv").touch()

        client = _mock_client(
            get_show=ShowInfo(tmdb_id=1, name="Show", first_air_date="2020-01-01", seasons=[]),
            get_episodes=[Episode(season=1, episode=1, name="Pilot")],
        )
        MockClient.return_value = client
        main(["rename", str(src), "--id", "1", "--season", "1"])

        out = capsys.readouterr().out
        assert "No files matched" in out

    @patch("tv_renamer.cli.TMDBClient")
    def test_rename_collisions_exit_nonzero(self, MockClient: MagicMock, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mkv").touch()
        (src / "01 - other rip.mkv").touch()

        client = _mock_client(
            get_show=ShowInfo(
                tmdb_id=99999, name="Test Show", first_air_date="2020-01-01", seasons=[]
            ),
            get_episodes=[Episode(season=1, episode=1, name="Pilot")],
        )
        MockClient.return_value = client
        with pytest.raises(SystemExit, match="1"):
            main(["rename", str(src), "--id", "99999", "--season", "1"])

        out = capsys.readouterr().out
        assert "Collisions" in out
        assert (src / "S01E01.mkv").exists()
        assert (src / "01 - other rip.mkv").exists()

    @patch("tv_renamer.cli.TMDBClient")
    def test_rename_collisions_dry_run_exit_nonzero(
        self, MockClient: MagicMock, tmp_path: Path, capsys
    ):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mkv").touch()
        (src / "01 - other rip.mkv").touch()

        client = _mock_client(
            get_show=ShowInfo(
                tmdb_id=99999, name="Test Show", first_air_date="2020-01-01", seasons=[]
            ),
            get_episodes=[Episode(season=1, episode=1, name="Pilot")],
        )
        MockClient.return_value = client
        with pytest.raises(SystemExit, match="1"):
            main(["rename", str(src), "--id", "99999", "--season", "1", "--dry-run"])

        out = capsys.readouterr().out
        assert "Collisions" in out


class TestCopyCommand:
    @patch("tv_renamer.cli.copy_to_dest")
    def test_copy_calls_copier(self, mock_copy: MagicMock, tmp_path: Path, capsys):
        from tv_renamer.copier import CopyResult

        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        mock_copy.return_value = CopyResult(verified=True)

        main(["copy", str(src), "--dest", str(dest)])

        mock_copy.assert_called_once_with(src, dest, dry_run=False)
        out = capsys.readouterr().out
        assert "Verify: OK" in out

    @patch("tv_renamer.cli.copy_to_dest")
    def test_copy_dry_run(self, mock_copy: MagicMock, tmp_path: Path, capsys):
        from tv_renamer.copier import CopyResult

        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        mock_copy.return_value = CopyResult(dry_run_output="would transfer\n")

        main(["copy", str(src), "--dest", str(dest), "--dry-run"])

        mock_copy.assert_called_once_with(src, dest, dry_run=True)
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "would transfer" in out

    @patch("tv_renamer.cli.copy_to_dest")
    def test_copy_verify_failure_exits_nonzero(self, mock_copy: MagicMock, tmp_path: Path, capsys):
        from tv_renamer.copier import CopyResult

        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        mock_copy.return_value = CopyResult(verified=False)

        with pytest.raises(SystemExit, match="1"):
            main(["copy", str(src), "--dest", str(dest)])

        err = capsys.readouterr().err
        assert "FAILED" in err


class TestErrorBoundary:
    def test_scan_nonexistent_dir_exits_1(self, capsys):
        ret = main(["scan", "/nonexistent/path"])
        assert ret == 1
        err = capsys.readouterr().err
        assert "error:" in err

    def test_successful_command_returns_0(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        ret = main(["scan", str(src)])
        assert ret == 0

    @patch("tv_renamer.cli.TMDBClient")
    def test_missing_api_key_exits_1(self, MockClient: MagicMock, capsys):
        MockClient.side_effect = RuntimeError("TMDB_API_KEY environment variable is not set")
        ret = main(["search", "test"])
        assert ret == 1
        err = capsys.readouterr().err
        assert "TMDB_API_KEY" in err

    @patch("tv_renamer.cli.TMDBClient")
    def test_http_401_names_env_var(self, MockClient: MagicMock, capsys):
        resp = Response()
        resp.status_code = 401
        client = _mock_client()
        client.search_tv.side_effect = HTTPError(response=resp)
        MockClient.return_value = client
        ret = main(["search", "test"])
        assert ret == 1
        err = capsys.readouterr().err
        assert "TMDB_API_KEY is invalid or expired" in err

    @patch("tv_renamer.cli.TMDBClient")
    def test_http_404_says_no_such_id(self, MockClient: MagicMock, capsys):
        resp = Response()
        resp.status_code = 404
        client = _mock_client()
        client.get_show.side_effect = HTTPError(response=resp)
        MockClient.return_value = client
        ret = main(["episodes", "999999"])
        assert ret == 1
        err = capsys.readouterr().err
        assert "no such TMDB id" in err

    @patch("tv_renamer.cli.copy_to_dest")
    def test_rsync_failure_exits_1(self, mock_copy: MagicMock, tmp_path: Path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        mock_copy.side_effect = subprocess.CalledProcessError(
            23, "rsync", stderr="rsync: some error\n"
        )
        ret = main(["copy", str(src), "--dest", str(dest)])
        assert ret == 1
        err = capsys.readouterr().err
        assert "rsync: some error" in err


class TestMovieCommand:
    @patch("tv_renamer.cli.TMDBClient")
    def test_movie_prints_details(self, MockClient: MagicMock, capsys):
        client = _mock_client(
            get_movie=MovieInfo(
                tmdb_id=550,
                name="Fight Club",
                release_date="1999-10-15",
                overview="An insomniac office worker...",
                runtime=139,
            ),
        )
        MockClient.return_value = client
        main(["movie", "550"])

        out = capsys.readouterr().out
        assert "Fight Club" in out
        assert "1999" in out
        assert "139 min" in out

    @patch("tv_renamer.cli.TMDBClient")
    def test_movie_unknown_runtime(self, MockClient: MagicMock, capsys):
        client = _mock_client(
            get_movie=MovieInfo(
                tmdb_id=1, name="Test", release_date="2020-01-01", overview="", runtime=None
            ),
        )
        MockClient.return_value = client
        main(["movie", "1"])

        out = capsys.readouterr().out
        assert "unknown" in out


class TestMovieRenameCommand:
    @patch("tv_renamer.cli.TMDBClient")
    def test_movie_rename_dry_run(self, MockClient: MagicMock, tmp_path: Path, capsys):
        movie_file = tmp_path / "fight_club.mkv"
        movie_file.write_text("data")

        client = _mock_client(
            get_movie=MovieInfo(
                tmdb_id=550,
                name="Fight Club",
                release_date="1999-10-15",
                overview="",
                runtime=139,
            ),
        )
        MockClient.return_value = client
        main(["movie-rename", str(movie_file), "--id", "550", "--dry-run"])

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "would be renamed" in out
        assert movie_file.exists()

    @patch("tv_renamer.cli.TMDBClient")
    def test_movie_rename_executes(self, MockClient: MagicMock, tmp_path: Path, capsys):
        movie_file = tmp_path / "fight_club.mkv"
        movie_file.write_text("data")

        client = _mock_client(
            get_movie=MovieInfo(
                tmdb_id=550,
                name="Fight Club",
                release_date="1999-10-15",
                overview="",
                runtime=139,
            ),
        )
        MockClient.return_value = client
        main(["movie-rename", str(movie_file), "--id", "550"])

        out = capsys.readouterr().out
        assert "file(s) renamed" in out
        assert not movie_file.exists()

        movie_dir = tmp_path / "Fight Club (1999) [tmdbid-550]"
        assert movie_dir.exists()
        assert (movie_dir / "movie.nfo").exists()
        assert (movie_dir / "Fight Club (1999) [tmdbid-550].mkv").exists()

    @patch("tv_renamer.cli.TMDBClient")
    def test_movie_rename_with_log(self, MockClient: MagicMock, tmp_path: Path, capsys):
        movie_file = tmp_path / "movie.mkv"
        movie_file.write_text("data")
        log = tmp_path / "changes.log"

        client = _mock_client(
            get_movie=MovieInfo(
                tmdb_id=1, name="Test", release_date="2020-01-01", overview="", runtime=90
            ),
        )
        MockClient.return_value = client
        main(["movie-rename", str(movie_file), "--id", "1", "--log", str(log)])

        assert log.exists()
        log_text = log.read_text()
        assert " -> " in log_text
        assert "wrote " in log_text
        assert "movie.nfo" in log_text

    @patch("tv_renamer.cli.TMDBClient")
    def test_movie_rename_custom_output(self, MockClient: MagicMock, tmp_path: Path, capsys):
        movie_file = tmp_path / "movie.mkv"
        movie_file.write_text("data")
        out_dir = tmp_path / "output"

        client = _mock_client(
            get_movie=MovieInfo(
                tmdb_id=1, name="Test", release_date="2020-01-01", overview="", runtime=90
            ),
        )
        MockClient.return_value = client
        main(["movie-rename", str(movie_file), "--id", "1", "--output", str(out_dir)])

        out = capsys.readouterr().out
        assert "file(s) renamed" in out
        assert (out_dir / "Test (2020) [tmdbid-1]" / "Test (2020) [tmdbid-1].mkv").exists()


class TestMoviePlanCommand:
    def test_movie_plan_writes_file(self, tmp_path: Path, capsys):
        movies_dir = tmp_path / "movies"
        movies_dir.mkdir()
        (movies_dir / "movie1.mkv").touch()
        (movies_dir / "movie2.mp4").touch()
        plan_file = tmp_path / "plan.yaml"

        main(["movie-plan", str(movies_dir), "-o", str(plan_file)])

        out = capsys.readouterr().out
        assert "Plan written to" in out
        assert "2 files listed" in out
        assert plan_file.exists()

    def test_movie_plan_stdout_no_crash(self, tmp_path: Path):
        movies_dir = tmp_path / "movies"
        movies_dir.mkdir()
        (movies_dir / "movie.mkv").touch()

        ret = main(["movie-plan", str(movies_dir)])
        assert ret == 0


class TestMovieRenamePlanMode:
    def test_plan_mode_dry_run(self, tmp_path: Path, capsys):
        movies_dir = tmp_path / "movies"
        movies_dir.mkdir()
        (movies_dir / "fc.mkv").write_text("data")

        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(
            f'directory: "{movies_dir}"\n'
            "files:\n"
            '  - file: "fc.mkv"\n'
            "    tmdb_id: 550\n"
            '    name: "Fight Club"\n'
            '    year: "1999"\n'
        )

        main(["movie-rename", "--plan", str(plan_file), "--dry-run"])

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "would be renamed" in out
        assert (movies_dir / "fc.mkv").exists()

    @patch("tv_renamer.cli.TMDBClient")
    def test_plan_mode_tmdb_lookup(self, MockClient: MagicMock, tmp_path: Path, capsys):
        movies_dir = tmp_path / "movies"
        movies_dir.mkdir()
        (movies_dir / "fc.mkv").write_text("data")

        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(
            f'directory: "{movies_dir}"\nfiles:\n  - file: "fc.mkv"\n    tmdb_id: 550\n'
        )

        client = _mock_client(
            get_movie=MovieInfo(
                tmdb_id=550,
                name="Fight Club",
                release_date="1999-10-15",
                overview="",
                runtime=139,
            ),
        )
        MockClient.return_value = client
        main(["movie-rename", "--plan", str(plan_file)])

        out = capsys.readouterr().out
        assert "file(s) renamed" in out
        assert not (movies_dir / "fc.mkv").exists()

        movie_dir = movies_dir.parent / "Fight Club (1999) [tmdbid-550]"
        assert movie_dir.exists()
        nfo = movie_dir / "movie.nfo"
        assert nfo.exists()
        assert "Fight Club" in nfo.read_text()

    def test_plan_mode_executes(self, tmp_path: Path, capsys):
        movies_dir = tmp_path / "movies"
        movies_dir.mkdir()
        (movies_dir / "fc.mkv").write_text("data")

        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(
            f'directory: "{movies_dir}"\n'
            "files:\n"
            '  - file: "fc.mkv"\n'
            "    tmdb_id: 550\n"
            '    name: "Fight Club"\n'
            '    year: "1999"\n'
        )

        main(["movie-rename", "--plan", str(plan_file)])

        out = capsys.readouterr().out
        assert "file(s) renamed" in out
        assert not (movies_dir / "fc.mkv").exists()

        parent = movies_dir.parent
        movie_dir = parent / "Fight Club (1999) [tmdbid-550]"
        assert movie_dir.exists()
        assert (movie_dir / "movie.nfo").exists()
