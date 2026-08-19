"""Tests for rename planning and execution."""

from pathlib import Path

from tv_renamer.renamer import execute_renames, plan_renames
from tv_renamer.tmdb import Episode


def _make_episodes(season: int, count: int) -> list[Episode]:
    return [Episode(season=season, episode=i + 1, name=f"Episode {i + 1}") for i in range(count)]


def test_plan_renames_standard_format(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "[S01.E01] Show - Pilot.mp4").touch()
    (src / "[S01.E02] Show - Second.mp4").touch()

    episodes = _make_episodes(1, 2)
    ops = plan_renames(src, show_name="Test Show", year="2020", episodes=episodes)

    assert len(ops) == 2
    assert (
        ops[0].dest
        == tmp_path / "Test Show (2020)" / "Season 1" / "Test Show - S01E01 - Episode 1.mp4"
    )
    assert (
        ops[1].dest
        == tmp_path / "Test Show (2020)" / "Season 1" / "Test Show - S01E02 - Episode 2.mp4"
    )


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
    ops = plan_renames(src, show_name="Show: Test", year="2020", episodes=episodes)

    assert ":" not in ops[0].dest.name
    assert '"' not in ops[0].dest.name


def test_plan_renames_missing_episode_title(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "S01E99.mp4").touch()

    episodes = _make_episodes(1, 2)
    ops = plan_renames(src, show_name="Show", year="2020", episodes=episodes)

    assert len(ops) == 1
    assert ops[0].dest.name == "Show - S01E99.mp4"


def test_plan_renames_custom_output(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    out = tmp_path / "output"
    (src / "S01E01.mkv").touch()

    episodes = _make_episodes(1, 1)
    ops = plan_renames(src, show_name="Show", year="2020", episodes=episodes, output=out)

    assert str(ops[0].dest).startswith(str(out))


def test_execute_renames(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    f1 = src / "S01E01.mkv"
    f1.write_text("data")

    episodes = _make_episodes(1, 1)
    ops = plan_renames(src, show_name="Show", year="2020", episodes=episodes)
    count = execute_renames(ops)

    assert count == 1
    assert ops[0].dest.exists()
    assert not f1.exists()


def test_execute_renames_with_log(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "S01E01.mkv").write_text("data")

    log = tmp_path / "changes.log"
    episodes = _make_episodes(1, 1)
    ops = plan_renames(src, show_name="Show", year="2020", episodes=episodes)
    execute_renames(ops, log_path=log)

    assert log.exists()
    assert "S01E01" in log.read_text()


def test_no_match_files_skipped(tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "random_movie.mkv").touch()

    episodes = _make_episodes(1, 5)
    ops = plan_renames(src, show_name="Show", year="2020", episodes=episodes)

    assert len(ops) == 0
