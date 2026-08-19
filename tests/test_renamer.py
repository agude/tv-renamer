"""Tests for rename planning and execution."""

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest

from tv_renamer.renamer import _safe_name, execute_renames, plan_renames, show_dir_name, write_nfo
from tv_renamer.tmdb import Episode


def _make_episodes(season: int, count: int) -> list[Episode]:
    return [Episode(season=season, episode=i + 1, name=f"Episode {i + 1}") for i in range(count)]


def test_plan_renames_standard_format(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "[S01.E01] Show - Pilot.mp4").touch()
    (src / "[S01.E02] Show - Second.mp4").touch()

    episodes = _make_episodes(1, 2)
    ops = plan_renames(src, show_name="Test Show", year="2020", tmdb_id=99999, episodes=episodes)

    assert len(ops) == 2
    show_dir = "Test Show (2020) [tmdbid-99999]"
    assert ops[0].dest == tmp_path / show_dir / "Season 1" / "Test Show - S01E01 - Episode 1.mp4"
    assert ops[1].dest == tmp_path / show_dir / "Season 1" / "Test Show - S01E02 - Episode 2.mp4"


def test_plan_renames_bare_numbers(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "01title.ts").touch()
    (src / "02title.ts").touch()

    episodes = _make_episodes(1, 2)
    ops = plan_renames(
        src,
        show_name="Show",
        year="2000",
        tmdb_id=99999,
        episodes=episodes,
        season_override=1,
    )

    assert len(ops) == 2
    assert "S01E01" in ops[0].dest.name
    assert "S01E02" in ops[1].dest.name


def test_plan_renames_unsafe_characters(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "S01E01.mp4").touch()

    episodes = [Episode(season=1, episode=1, name='What: The "Movie"?')]
    ops = plan_renames(src, show_name="Show: Test", year="2020", tmdb_id=99999, episodes=episodes)

    assert ":" not in ops[0].dest.name
    assert '"' not in ops[0].dest.name


def test_plan_renames_missing_episode_title(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "S01E99.mp4").touch()

    episodes = _make_episodes(1, 2)
    ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

    assert len(ops) == 1
    assert ops[0].dest.name == "Show - S01E99.mp4"


def test_plan_renames_custom_output(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    out = tmp_path / "output"
    (src / "S01E01.mkv").touch()

    episodes = _make_episodes(1, 1)
    ops = plan_renames(
        src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes, output=out
    )

    assert str(ops[0].dest).startswith(str(out))


def test_execute_renames(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    f1 = src / "S01E01.mkv"
    f1.write_text("data")

    episodes = _make_episodes(1, 1)
    ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)
    count = execute_renames(ops, show_name="Show", tmdb_id=99999)

    assert count == 1
    assert ops[0].dest.exists()
    assert not f1.exists()
    nfo = ops[0].dest.parent.parent / "tvshow.nfo"
    assert nfo.exists()
    assert "<tmdbid>99999</tmdbid>" in nfo.read_text()


def test_execute_renames_with_log(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "S01E01.mkv").write_text("data")

    log = tmp_path / "changes.log"
    episodes = _make_episodes(1, 1)
    ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)
    execute_renames(ops, log_path=log)

    assert log.exists()
    assert "S01E01" in log.read_text()


def test_execute_renames_partial_failure(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    files = []
    for i in range(1, 6):
        f = src / f"S01E{i:02d}.mkv"
        f.write_text(f"data{i}")
        files.append(f)

    episodes = _make_episodes(1, 5)
    ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)
    log = tmp_path / "changes.log"

    call_count = 0
    original_move = __import__("shutil").move

    def failing_move(s: str, d: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise OSError("cross-device link")
        original_move(s, d)

    with (
        patch("tv_renamer.renamer.shutil.move", side_effect=failing_move),
        pytest.raises(OSError, match="S01E03"),
    ):
        execute_renames(ops, log_path=log)

    log_text = log.read_text()
    assert log_text.count(" -> ") == 2


def test_execute_renames_refuses_overwrite(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "S01E01.mkv").write_text("original")

    episodes = _make_episodes(1, 1)
    ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

    ops[0].dest.parent.mkdir(parents=True, exist_ok=True)
    ops[0].dest.write_text("existing")

    with pytest.raises(FileExistsError, match="Destination already exists"):
        execute_renames(ops)

    assert (src / "S01E01.mkv").exists()
    assert ops[0].dest.read_text() == "existing"


def test_execute_renames_overwrite_aborts_whole_batch(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "S01E01.mkv").write_text("data1")
    (src / "S01E02.mkv").write_text("data2")

    episodes = _make_episodes(1, 2)
    ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

    ops[0].dest.parent.mkdir(parents=True, exist_ok=True)
    ops[0].dest.write_text("blocker")

    with pytest.raises(FileExistsError):
        execute_renames(ops)

    assert (src / "S01E01.mkv").exists()
    assert (src / "S01E02.mkv").exists()


def test_no_match_files_skipped(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "random_movie.mkv").touch()

    episodes = _make_episodes(1, 5)
    ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

    assert len(ops) == 0


def test_write_nfo(tmp_path: Path):
    nfo = write_nfo(tmp_path, "Avatar: The Last Airbender", 246)
    assert nfo.name == "tvshow.nfo"
    content = nfo.read_text()
    assert "<tmdbid>246</tmdbid>" in content
    assert "<title>Avatar: The Last Airbender</title>" in content


class TestWriteNfoXmlEscape:
    @pytest.mark.parametrize(
        "title",
        [
            "Tom & Jerry <Classic>",
            "Show with <angle brackets>",
            'Show with "double quotes"',
            "Show with 'single quotes'",
            "A & B & C",
        ],
    )
    def test_xml_special_chars_produce_valid_xml(self, tmp_path: Path, title: str):
        nfo = write_nfo(tmp_path, title, 42)
        tree = ET.parse(nfo)
        root = tree.getroot()
        assert root.find("title") is not None
        assert root.findtext("title") == title
        assert root.findtext("tmdbid") == "42"


class TestSafeName:
    def test_removes_colon(self):
        assert _safe_name("Show: Test") == "Show Test"

    def test_removes_quotes(self):
        assert _safe_name('The "Best" Show') == "The Best Show"

    def test_removes_question_mark(self):
        assert _safe_name("Who?") == "Who"

    def test_removes_multiple_unsafe(self):
        assert _safe_name('A:B<C>D"E') == "ABCDE"

    def test_strips_whitespace(self):
        assert _safe_name("  Show  ") == "Show"

    def test_passthrough_safe_name(self):
        assert _safe_name("Perfectly Normal Name") == "Perfectly Normal Name"

    def test_empty_after_stripping(self):
        assert _safe_name(':::"""') == ""

    def test_unicode_preserved(self):
        assert _safe_name("死神粤语") == "死神粤语"


class TestPlanRenamesSpecials:
    def test_season_zero_stays_in_season_zero(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "Show.S00E03.mkv").touch()

        episodes = [Episode(season=0, episode=3, name="Special Three")]
        ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

        assert len(ops) == 1
        assert "Season 0" in str(ops[0].dest)
        assert "S00E03" in ops[0].dest.name

    def test_season_override_zero_honored(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "01.mp4").touch()

        episodes = [Episode(season=0, episode=1, name="Pilot Special")]
        ops = plan_renames(
            src,
            show_name="Show",
            year="2020",
            tmdb_id=99999,
            episodes=episodes,
            season_override=0,
        )

        assert len(ops) == 1
        assert "Season 0" in str(ops[0].dest)
        assert "S00E01" in ops[0].dest.name

    def test_no_season_defaults_to_one(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "01title.ts").touch()

        episodes = _make_episodes(1, 1)
        ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

        assert len(ops) == 1
        assert "Season 1" in str(ops[0].dest)
        assert "S01E01" in ops[0].dest.name


class TestShowDirName:
    def test_standard_format(self):
        assert show_dir_name("Test Show", "2020", 99999) == "Test Show (2020) [tmdbid-99999]"

    def test_unsafe_chars_stripped(self):
        result = show_dir_name("Show: Test", "2020", 1)
        assert ":" not in result
        assert "[tmdbid-1]" in result


class TestPlanRenamesMultiSeason:
    def test_multi_season_routing(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01 - Pilot.mp4").touch()
        (src / "S02E01 - Premiere.mp4").touch()
        (src / "S02E02 - Second.mp4").touch()

        episodes = [
            Episode(season=1, episode=1, name="Pilot"),
            Episode(season=2, episode=1, name="Premiere"),
            Episode(season=2, episode=2, name="Second"),
        ]
        ops = plan_renames(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

        assert len(ops) == 3
        s1_ops = [op for op in ops if "Season 1" in str(op.dest)]
        s2_ops = [op for op in ops if "Season 2" in str(op.dest)]
        assert len(s1_ops) == 1
        assert len(s2_ops) == 2

    def test_season_override_forces_all_to_one_season(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "01.mp4").touch()
        (src / "02.mp4").touch()

        episodes = [
            Episode(season=3, episode=1, name="First"),
            Episode(season=3, episode=2, name="Second"),
        ]
        ops = plan_renames(
            src,
            show_name="Show",
            year="2020",
            tmdb_id=99999,
            episodes=episodes,
            season_override=3,
        )

        assert len(ops) == 2
        assert all("Season 3" in str(op.dest) for op in ops)
        assert all("S03E" in op.dest.name for op in ops)
