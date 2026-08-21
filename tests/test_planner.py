"""Tests for YAML plan generation, serialization, and execution."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from tv_renamer.planner import (
    MoviePlanData,
    MoviePlanEntry,
    PlanData,
    PlanEntry,
    generate_movie_plan,
    generate_plan,
    movie_plan_to_renames,
    plan_to_renames,
    read_movie_plan,
    read_plan,
    write_movie_plan,
    write_plan,
)
from tv_renamer.renamer import build_episode_path
from tv_renamer.tmdb import Episode, MovieInfo


def _make_episodes(season: int, count: int) -> list[Episode]:
    return [Episode(season=season, episode=i + 1, name=f"Episode {i + 1}") for i in range(count)]


class TestBuildEpisodePath:
    def test_basic_path(self, tmp_path: Path):
        result = build_episode_path(
            out_root=tmp_path,
            show_name="Test Show",
            year="2020",
            tmdb_id=99999,
            season=1,
            episode=1,
            ep_title="Pilot",
            extension=".mp4",
        )
        assert (
            result
            == tmp_path
            / "Test Show (2020) [tmdbid-99999]"
            / "Season 1"
            / "Test Show - S01E01 - Pilot.mp4"
        )

    def test_no_title(self, tmp_path: Path):
        result = build_episode_path(
            out_root=tmp_path,
            show_name="Show",
            year="2020",
            tmdb_id=1,
            season=2,
            episode=5,
            extension=".mkv",
        )
        assert result.name == "Show - S02E05.mkv"

    def test_with_part(self, tmp_path: Path):
        result = build_episode_path(
            out_root=tmp_path,
            show_name="Show",
            year="2020",
            tmdb_id=1,
            season=1,
            episode=1,
            ep_title="Pilot",
            extension=".mp4",
            part=2,
        )
        assert "Pilot (Part 2)" in result.name
        assert "S01E01" in result.name

    def test_part_without_title(self, tmp_path: Path):
        result = build_episode_path(
            out_root=tmp_path,
            show_name="Show",
            year="2020",
            tmdb_id=1,
            season=1,
            episode=1,
            extension=".mp4",
            part=1,
        )
        assert result.name == "Show - S01E01 (Part 1).mp4"

    def test_unsafe_chars_sanitized(self, tmp_path: Path):
        result = build_episode_path(
            out_root=tmp_path,
            show_name="Show: Test",
            year="2020",
            tmdb_id=1,
            season=1,
            episode=1,
            ep_title='What "Happened"?',
            extension=".mp4",
        )
        assert ":" not in result.name
        assert '"' not in result.name
        assert "?" not in result.name

    def test_season_zero(self, tmp_path: Path):
        result = build_episode_path(
            out_root=tmp_path,
            show_name="Show",
            year="2020",
            tmdb_id=1,
            season=0,
            episode=3,
            ep_title="Special",
            extension=".mkv",
        )
        assert "Season 0" in str(result)
        assert "S00E03" in result.name


class TestGeneratePlan:
    def test_all_matched(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01 - Pilot.mp4").touch()
        (src / "S01E02 - Second.mp4").touch()

        episodes = _make_episodes(1, 2)
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=42, episodes=episodes)

        assert plan.show == "Show"
        assert plan.tmdb_id == 42
        assert plan.year == "2020"
        assert plan.directory == str(src)
        assert len(plan.files) == 2
        assert plan.files[0].season == 1
        assert plan.files[0].episode == 1
        assert plan.files[0].title == "Episode 1"
        assert plan.files[1].episode == 2

    def test_unmatched_files_included(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mp4").touch()
        (src / "random_movie.mkv").touch()

        episodes = _make_episodes(1, 1)
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=42, episodes=episodes)

        assert len(plan.files) == 2
        matched = [e for e in plan.files if e.episode is not None]
        unmatched = [e for e in plan.files if e.episode is None]
        assert len(matched) == 1
        assert len(unmatched) == 1
        assert unmatched[0].file == "random_movie.mkv"

    def test_season_override(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "01.mp4").touch()

        episodes = [Episode(season=3, episode=1, name="First")]
        plan = generate_plan(
            src,
            show_name="Show",
            year="2020",
            tmdb_id=42,
            episodes=episodes,
            season_override=3,
        )

        assert plan.files[0].season == 3
        assert plan.files[0].episode == 1
        assert plan.files[0].title == "First"

    def test_episode_beyond_tmdb_has_no_title(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E99.mp4").touch()

        episodes = _make_episodes(1, 3)
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=42, episodes=episodes)

        assert plan.files[0].episode == 99
        assert plan.files[0].title is None

    def test_empty_directory(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()

        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=42, episodes=[])

        assert len(plan.files) == 0

    def test_ep_prefix_matched(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "[粵語] Show_EP01 Title.mp4").touch()
        (src / "[粵語] Show_EP02 Title.mp4").touch()

        episodes = _make_episodes(1, 2)
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=42, episodes=episodes)

        assert len(plan.files) == 2
        assert plan.files[0].episode == 1
        assert plan.files[0].title == "Episode 1"
        assert plan.files[1].episode == 2

    def test_multi_season_absolute_numbering(self, tmp_path: Path):
        """Sequential numbering across seasons: EP01-03=S1, EP04-05=S2."""
        src = tmp_path / "source"
        src.mkdir()
        for i in range(1, 6):
            (src / f"Show_EP{i:02d}.mp4").touch()

        episodes = [
            Episode(season=1, episode=1, name="S1E1"),
            Episode(season=1, episode=2, name="S1E2"),
            Episode(season=1, episode=3, name="S1E3"),
            Episode(season=2, episode=1, name="S2E1"),
            Episode(season=2, episode=2, name="S2E2"),
        ]
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=42, episodes=episodes)

        assert len(plan.files) == 5
        assert plan.files[0].season == 1
        assert plan.files[0].episode == 1
        assert plan.files[0].title == "S1E1"
        assert plan.files[2].season == 1
        assert plan.files[2].episode == 3
        assert plan.files[2].title == "S1E3"
        assert plan.files[3].season == 2
        assert plan.files[3].episode == 1
        assert plan.files[3].title == "S2E1"
        assert plan.files[4].season == 2
        assert plan.files[4].episode == 2
        assert plan.files[4].title == "S2E2"

    def test_multi_season_with_season_override_ignores_split(self, tmp_path: Path):
        """Season override forces all into one season, no auto-split."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "Show_EP01.mp4").touch()
        (src / "Show_EP02.mp4").touch()

        episodes = [
            Episode(season=1, episode=1, name="S1E1"),
            Episode(season=2, episode=1, name="S2E1"),
        ]
        plan = generate_plan(
            src,
            show_name="Show",
            year="2020",
            tmdb_id=42,
            episodes=episodes,
            season_override=1,
        )

        assert plan.files[0].season == 1
        assert plan.files[0].episode == 1
        assert plan.files[1].season == 1
        assert plan.files[1].episode == 2

    def test_multi_season_sxxexx_uses_file_season(self, tmp_path: Path):
        """Files with explicit season info use it, not absolute mapping."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "S02E01.mp4").touch()

        episodes = [
            Episode(season=1, episode=1, name="S1E1"),
            Episode(season=2, episode=1, name="S2E1"),
        ]
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=42, episodes=episodes)

        assert plan.files[0].season == 2
        assert plan.files[0].episode == 1
        assert plan.files[0].title == "S2E1"

    def test_multi_season_beyond_total_has_no_title(self, tmp_path: Path):
        """Absolute number beyond total episode count gets no title."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "Show_EP99.mp4").touch()

        episodes = [*_make_episodes(1, 3), Episode(season=2, episode=1, name="S2E1")]
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=42, episodes=episodes)

        assert plan.files[0].episode == 99
        assert plan.files[0].season == 1
        assert plan.files[0].title is None


class TestWritePlan:
    def test_produces_valid_yaml(self, tmp_path: Path):
        plan = PlanData(
            show="Test Show",
            tmdb_id=42,
            year="2020",
            directory="/some/path",
            files=[
                PlanEntry(file="ep01.mp4", season=1, episode=1, title="Pilot"),
                PlanEntry(file="ep02.mp4", season=1, episode=2, title="Second"),
            ],
        )
        out = tmp_path / "plan.yaml"
        write_plan(plan, out)

        raw = yaml.safe_load(out.read_text())
        assert raw["show"] == "Test Show"
        assert raw["tmdb_id"] == 42
        assert len(raw["files"]) == 2

    def test_unmatched_entry_has_null_fields(self, tmp_path: Path):
        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory="/path",
            files=[PlanEntry(file="unknown.mkv")],
        )
        out = tmp_path / "plan.yaml"
        write_plan(plan, out)

        raw = yaml.safe_load(out.read_text())
        entry = raw["files"][0]
        assert entry["season"] is None
        assert entry["episode"] is None

    def test_part_included_when_set(self, tmp_path: Path):
        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory="/path",
            files=[PlanEntry(file="ep.mp4", season=1, episode=1, title="Pilot", part=2)],
        )
        out = tmp_path / "plan.yaml"
        write_plan(plan, out)

        raw = yaml.safe_load(out.read_text())
        assert raw["files"][0]["part"] == 2

    def test_part_omitted_when_none(self, tmp_path: Path):
        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory="/path",
            files=[PlanEntry(file="ep.mp4", season=1, episode=1, title="Pilot")],
        )
        out = tmp_path / "plan.yaml"
        write_plan(plan, out)

        raw = yaml.safe_load(out.read_text())
        assert "part" not in raw["files"][0]

    def test_output_field_written(self, tmp_path: Path):
        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory="/source",
            files=[],
            output="/output",
        )
        out = tmp_path / "plan.yaml"
        write_plan(plan, out)

        raw = yaml.safe_load(out.read_text())
        assert raw["output"] == "/output"

    def test_special_chars_in_title_escaped(self, tmp_path: Path):
        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory="/path",
            files=[
                PlanEntry(file="ep.mp4", season=1, episode=1, title='Woo-oo!: The "Pilot"'),
            ],
        )
        out = tmp_path / "plan.yaml"
        write_plan(plan, out)

        raw = yaml.safe_load(out.read_text())
        assert raw["files"][0]["title"] == 'Woo-oo!: The "Pilot"'

    def test_includes_header_comments(self, tmp_path: Path):
        plan = PlanData(show="Show", tmdb_id=1, year="2020", directory="/path", files=[])
        out = tmp_path / "plan.yaml"
        write_plan(plan, out)

        text = out.read_text()
        assert "tv-renamer plan" in text
        assert "tv-renamer rename --plan" in text


class TestReadPlan:
    def test_round_trip(self, tmp_path: Path):
        original = PlanData(
            show="DuckTales",
            tmdb_id=72350,
            year="2017",
            directory="/media/drive/Duck Tales",
            files=[
                PlanEntry(file="E01.mp4", season=1, episode=1, title="Woo-oo!"),
                PlanEntry(file="E02.mp4", season=1, episode=1, title="Woo-oo!", part=2),
                PlanEntry(file="E03.mp4", season=1, episode=2, title="Daytrip of Doom!"),
                PlanEntry(file="bonus.mkv"),
            ],
        )
        path = tmp_path / "plan.yaml"
        write_plan(original, path)
        loaded = read_plan(path)

        assert loaded.show == original.show
        assert loaded.tmdb_id == original.tmdb_id
        assert loaded.year == original.year
        assert loaded.directory == original.directory
        assert len(loaded.files) == 4
        assert loaded.files[0].title == "Woo-oo!"
        assert loaded.files[1].part == 2
        assert loaded.files[3].season is None
        assert loaded.files[3].episode is None

    def test_missing_required_key_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("show: Test\n")

        with pytest.raises(ValueError, match="missing required key"):
            read_plan(path)

    def test_not_a_mapping_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("- item1\n- item2\n")

        with pytest.raises(ValueError, match="must be a YAML mapping"):
            read_plan(path)

    def test_files_not_a_list_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("show: S\ntmdb_id: 1\nyear: '2020'\ndirectory: /p\nfiles: not-a-list\n")

        with pytest.raises(ValueError, match="must be a list"):
            read_plan(path)

    def test_entry_missing_file_key_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text(
            "show: S\ntmdb_id: 1\nyear: '2020'\ndirectory: /p\n"
            "files:\n  - season: 1\n    episode: 1\n"
        )

        with pytest.raises(ValueError, match="missing 'file' key"):
            read_plan(path)

    def test_entry_not_a_mapping_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text(
            "show: S\ntmdb_id: 1\nyear: '2020'\ndirectory: /p\nfiles:\n  - just a string\n"
        )

        with pytest.raises(ValueError, match="must be a mapping"):
            read_plan(path)

    def test_output_field_read(self, tmp_path: Path):
        path = tmp_path / "plan.yaml"
        path.write_text(
            "show: S\ntmdb_id: 1\nyear: '2020'\ndirectory: /p\noutput: /out\nfiles: []\n"
        )
        plan = read_plan(path)
        assert plan.output == "/out"

    def test_year_coerced_to_string(self, tmp_path: Path):
        path = tmp_path / "plan.yaml"
        path.write_text("show: S\ntmdb_id: 1\nyear: 2020\ndirectory: /p\nfiles: []\n")
        plan = read_plan(path)
        assert plan.year == "2020"
        assert isinstance(plan.year, str)


class TestPlanToRenames:
    def test_basic_renames(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "ep01.mp4").touch()
        (src / "ep02.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=99999,
            year="2020",
            directory=str(src),
            files=[
                PlanEntry(file="ep01.mp4", season=1, episode=1, title="Pilot"),
                PlanEntry(file="ep02.mp4", season=1, episode=2, title="Second"),
            ],
        )
        result = plan_to_renames(plan)

        assert len(result.ops) == 2
        assert "S01E01 - Pilot" in result.ops[0].dest.name
        assert "S01E02 - Second" in result.ops[1].dest.name

    def test_null_entries_skipped(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "ep01.mp4").touch()
        (src / "bonus.mkv").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[
                PlanEntry(file="ep01.mp4", season=1, episode=1, title="Pilot"),
                PlanEntry(file="bonus.mkv"),
            ],
        )
        result = plan_to_renames(plan)

        assert len(result.ops) == 1
        assert len(result.unmatched) == 1
        assert result.unmatched[0].name == "bonus.mkv"

    def test_part_in_filename(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "ep01a.mp4").touch()
        (src / "ep01b.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[
                PlanEntry(file="ep01a.mp4", season=1, episode=1, title="Pilot", part=1),
                PlanEntry(file="ep01b.mp4", season=1, episode=1, title="Pilot", part=2),
            ],
        )
        result = plan_to_renames(plan)

        assert len(result.ops) == 2
        assert "Part 1" in result.ops[0].dest.name
        assert "Part 2" in result.ops[1].dest.name
        assert len(result.collisions) == 0

    def test_collision_detected(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "ep01a.mp4").touch()
        (src / "ep01b.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[
                PlanEntry(file="ep01a.mp4", season=1, episode=1, title="Pilot"),
                PlanEntry(file="ep01b.mp4", season=1, episode=1, title="Pilot"),
            ],
        )
        result = plan_to_renames(plan)

        assert len(result.collisions) == 1

    def test_no_collision_with_different_parts(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.mp4").touch()
        (src / "b.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[
                PlanEntry(file="a.mp4", season=1, episode=1, title="Pilot", part=1),
                PlanEntry(file="b.mp4", season=1, episode=1, title="Pilot", part=2),
            ],
        )
        result = plan_to_renames(plan)
        assert len(result.collisions) == 0

    def test_output_override(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        out = tmp_path / "output"
        (src / "ep.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[PlanEntry(file="ep.mp4", season=1, episode=1, title="Pilot")],
        )
        result = plan_to_renames(plan, output_override=out)

        assert str(result.ops[0].dest).startswith(str(out))

    def test_output_from_plan(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        out = tmp_path / "plan_output"
        (src / "ep.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[PlanEntry(file="ep.mp4", season=1, episode=1, title="Pilot")],
            output=str(out),
        )
        result = plan_to_renames(plan)

        assert str(result.ops[0].dest).startswith(str(out))

    def test_default_output_is_parent(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "ep.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[PlanEntry(file="ep.mp4", season=1, episode=1, title="Pilot")],
        )
        result = plan_to_renames(plan)

        assert str(result.ops[0].dest).startswith(str(tmp_path))

    def test_no_title_no_part(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "ep.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[PlanEntry(file="ep.mp4", season=1, episode=5)],
        )
        result = plan_to_renames(plan)

        assert result.ops[0].dest.name == "Show - S01E05.mp4"

    def test_all_null_entries(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.mkv").touch()
        (src / "b.mkv").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[
                PlanEntry(file="a.mkv"),
                PlanEntry(file="b.mkv"),
            ],
        )
        result = plan_to_renames(plan)

        assert len(result.ops) == 0
        assert len(result.unmatched) == 2

    def test_mixed_seasons(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.mp4").touch()
        (src / "b.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[
                PlanEntry(file="a.mp4", season=1, episode=23, title="Finale"),
                PlanEntry(file="b.mp4", season=2, episode=1, title="Premiere"),
            ],
        )
        result = plan_to_renames(plan)

        assert len(result.ops) == 2
        assert "Season 1" in str(result.ops[0].dest)
        assert "Season 2" in str(result.ops[1].dest)

    def test_missing_source_file_raises(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[PlanEntry(file="nonexistent.mp4", season=1, episode=1, title="Pilot")],
        )
        with pytest.raises(FileNotFoundError, match="does not exist"):
            plan_to_renames(plan)

    def test_missing_directory_raises(self, tmp_path: Path):
        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(tmp_path / "nonexistent"),
            files=[PlanEntry(file="ep.mp4", season=1, episode=1, title="Pilot")],
        )
        with pytest.raises(FileNotFoundError, match="directory does not exist"):
            plan_to_renames(plan)

    def test_skipped_entries_not_checked_for_existence(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "ep.mp4").touch()

        plan = PlanData(
            show="Show",
            tmdb_id=1,
            year="2020",
            directory=str(src),
            files=[
                PlanEntry(file="ep.mp4", season=1, episode=1, title="Pilot"),
                PlanEntry(file="ghost.mkv"),
            ],
        )
        result = plan_to_renames(plan)

        assert len(result.ops) == 1
        assert len(result.unmatched) == 1


class TestEndToEnd:
    """Full round-trip: generate -> write -> read -> execute."""

    def test_generate_write_read_execute(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01 - Pilot.mp4").write_text("data1")
        (src / "S01E02 - Second.mp4").write_text("data2")

        episodes = _make_episodes(1, 2)
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

        plan_file = tmp_path / "plan.yaml"
        write_plan(plan, plan_file)

        loaded = read_plan(plan_file)
        rename_plan = plan_to_renames(loaded)

        assert len(rename_plan.ops) == 2
        assert "S01E01 - Episode 1" in rename_plan.ops[0].dest.name
        assert "S01E02 - Episode 2" in rename_plan.ops[1].dest.name

    def test_edit_plan_then_execute(self, tmp_path: Path):
        """Simulate operator editing: shift episode numbers by 1."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mp4").write_text("actually ep2")
        (src / "S01E02.mp4").write_text("actually ep3")

        episodes = _make_episodes(1, 3)
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

        # Operator corrects: E01 is really ep2, E02 is really ep3
        plan.files[0].episode = 2
        plan.files[0].title = "Episode 2"
        plan.files[1].episode = 3
        plan.files[1].title = "Episode 3"

        plan_file = tmp_path / "plan.yaml"
        write_plan(plan, plan_file)

        loaded = read_plan(plan_file)
        rename_plan = plan_to_renames(loaded)

        assert "S01E02 - Episode 2" in rename_plan.ops[0].dest.name
        assert "S01E03 - Episode 3" in rename_plan.ops[1].dest.name

    def test_split_episode_workflow(self, tmp_path: Path):
        """Simulate: premiere was split into two files, operator assigns parts."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "E01.mp4").write_text("part1")
        (src / "E02.mp4").write_text("part2")
        (src / "E03.mp4").write_text("ep2")

        episodes = _make_episodes(1, 2)
        plan = generate_plan(
            src,
            show_name="Show",
            year="2020",
            tmdb_id=99999,
            episodes=episodes,
            season_override=1,
        )

        # Operator corrects: E01+E02 are both episode 1 (split premiere)
        plan.files[0].episode = 1
        plan.files[0].title = "Episode 1"
        plan.files[0].part = 1
        plan.files[1].episode = 1
        plan.files[1].title = "Episode 1"
        plan.files[1].part = 2
        plan.files[2].episode = 2
        plan.files[2].title = "Episode 2"

        plan_file = tmp_path / "plan.yaml"
        write_plan(plan, plan_file)
        loaded = read_plan(plan_file)
        rename_plan = plan_to_renames(loaded)

        assert len(rename_plan.ops) == 3
        assert len(rename_plan.collisions) == 0
        assert "Episode 1 (Part 1)" in rename_plan.ops[0].dest.name
        assert "Episode 1 (Part 2)" in rename_plan.ops[1].dest.name
        assert "S01E02 - Episode 2" in rename_plan.ops[2].dest.name

    def test_skip_files_by_removing_from_plan(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "S01E01.mp4").touch()
        (src / "S01E02.mp4").touch()
        (src / "bonus.mkv").touch()

        episodes = _make_episodes(1, 2)
        plan = generate_plan(src, show_name="Show", year="2020", tmdb_id=99999, episodes=episodes)

        # Operator removes the unmatched entry
        plan.files = [e for e in plan.files if e.episode is not None]

        rename_plan = plan_to_renames(plan)
        assert len(rename_plan.ops) == 2
        assert len(rename_plan.unmatched) == 0


class TestGenerateMoviePlan:
    def test_lists_media_files(self, tmp_path: Path):
        (tmp_path / "movie1.mkv").touch()
        (tmp_path / "movie2.mp4").touch()
        (tmp_path / "readme.txt").touch()

        plan = generate_movie_plan(tmp_path)

        assert len(plan.files) == 2
        assert plan.directory == str(tmp_path)
        names = {e.file for e in plan.files}
        assert "movie1.mkv" in names
        assert "movie2.mp4" in names

    def test_excludes_non_media(self, tmp_path: Path):
        (tmp_path / "notes.txt").touch()
        (tmp_path / "cover.jpg").touch()

        plan = generate_movie_plan(tmp_path)
        assert len(plan.files) == 0

    def test_all_tmdb_fields_null(self, tmp_path: Path):
        (tmp_path / "movie.mkv").touch()

        plan = generate_movie_plan(tmp_path)
        entry = plan.files[0]
        assert entry.tmdb_id is None
        assert entry.name is None
        assert entry.year is None


class TestWriteMoviePlan:
    def test_produces_valid_yaml(self, tmp_path: Path):
        plan = MoviePlanData(
            directory="/movies",
            files=[
                MoviePlanEntry(file="movie.mkv", tmdb_id=550, name="Fight Club", year="1999"),
            ],
        )
        out = tmp_path / "plan.yaml"
        write_movie_plan(plan, out)

        raw = yaml.safe_load(out.read_text())
        assert raw["directory"] == "/movies"
        assert len(raw["files"]) == 1
        assert raw["files"][0]["tmdb_id"] == 550

    def test_null_tmdb_id_in_yaml(self, tmp_path: Path):
        plan = MoviePlanData(
            directory="/movies",
            files=[MoviePlanEntry(file="unknown.mkv")],
        )
        out = tmp_path / "plan.yaml"
        write_movie_plan(plan, out)

        raw = yaml.safe_load(out.read_text())
        assert raw["files"][0]["tmdb_id"] is None

    def test_includes_header_comments(self, tmp_path: Path):
        plan = MoviePlanData(directory="/movies", files=[])
        out = tmp_path / "plan.yaml"
        write_movie_plan(plan, out)

        text = out.read_text()
        assert "movie plan" in text
        assert "movie-rename --plan" in text


class TestReadMoviePlan:
    def test_round_trip(self, tmp_path: Path):
        original = MoviePlanData(
            directory="/movies",
            files=[
                MoviePlanEntry(file="fc.mkv", tmdb_id=550, name="Fight Club", year="1999"),
                MoviePlanEntry(file="unknown.mkv"),
            ],
        )
        path = tmp_path / "plan.yaml"
        write_movie_plan(original, path)
        loaded = read_movie_plan(path)

        assert loaded.directory == original.directory
        assert len(loaded.files) == 2
        assert loaded.files[0].tmdb_id == 550
        assert loaded.files[0].name == "Fight Club"
        assert loaded.files[1].tmdb_id is None

    def test_missing_required_key_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("directory: /movies\n")

        with pytest.raises(ValueError, match="missing required key"):
            read_movie_plan(path)

    def test_not_a_mapping_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("- item\n")

        with pytest.raises(ValueError, match="must be a YAML mapping"):
            read_movie_plan(path)

    def test_entry_missing_file_raises(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("directory: /movies\nfiles:\n  - tmdb_id: 1\n")

        with pytest.raises(ValueError, match="missing 'file' key"):
            read_movie_plan(path)


class TestMoviePlanToRenames:
    def test_basic_renames(self, tmp_path: Path):
        (tmp_path / "fc.mkv").touch()

        plan = MoviePlanData(
            directory=str(tmp_path),
            files=[MoviePlanEntry(file="fc.mkv", tmdb_id=550, name="Fight Club", year="1999")],
        )
        result = movie_plan_to_renames(plan)

        assert len(result.ops) == 1
        assert "Fight Club (1999) [tmdbid-550]" in str(result.ops[0].dest)

    def test_null_tmdb_id_skipped(self, tmp_path: Path):
        (tmp_path / "unknown.mkv").touch()

        plan = MoviePlanData(
            directory=str(tmp_path),
            files=[MoviePlanEntry(file="unknown.mkv")],
        )
        result = movie_plan_to_renames(plan)

        assert len(result.ops) == 0
        assert len(result.unmatched) == 1

    def test_name_year_from_entry_skips_tmdb_lookup(self, tmp_path: Path):
        (tmp_path / "movie.mkv").touch()

        plan = MoviePlanData(
            directory=str(tmp_path),
            files=[MoviePlanEntry(file="movie.mkv", tmdb_id=550, name="Fight Club", year="1999")],
        )
        result = movie_plan_to_renames(plan, client=None)

        assert len(result.ops) == 1

    def test_missing_name_triggers_tmdb_lookup(self, tmp_path: Path):
        (tmp_path / "movie.mkv").touch()

        mock_client = MagicMock()
        mock_client.get_movie.return_value = MovieInfo(
            tmdb_id=550, name="Fight Club", release_date="1999-10-15", overview="", runtime=139
        )

        plan = MoviePlanData(
            directory=str(tmp_path),
            files=[MoviePlanEntry(file="movie.mkv", tmdb_id=550)],
        )
        result = movie_plan_to_renames(plan, client=mock_client)

        assert len(result.ops) == 1
        mock_client.get_movie.assert_called_once_with(550)
        assert "Fight Club" in str(result.ops[0].dest)

    def test_tmdb_lookup_writes_back_to_entry(self, tmp_path: Path):
        (tmp_path / "movie.mkv").touch()

        mock_client = MagicMock()
        mock_client.get_movie.return_value = MovieInfo(
            tmdb_id=550, name="Fight Club", release_date="1999-10-15", overview="", runtime=139
        )

        entry = MoviePlanEntry(file="movie.mkv", tmdb_id=550)
        plan = MoviePlanData(directory=str(tmp_path), files=[entry])
        movie_plan_to_renames(plan, client=mock_client)

        assert entry.name == "Fight Club"
        assert entry.year == "1999"

    def test_collision_detected(self, tmp_path: Path):
        (tmp_path / "a.mkv").touch()
        (tmp_path / "b.mkv").touch()

        plan = MoviePlanData(
            directory=str(tmp_path),
            files=[
                MoviePlanEntry(file="a.mkv", tmdb_id=550, name="Fight Club", year="1999"),
                MoviePlanEntry(file="b.mkv", tmdb_id=550, name="Fight Club", year="1999"),
            ],
        )
        result = movie_plan_to_renames(plan)

        assert len(result.collisions) == 1

    def test_missing_source_file_raises(self, tmp_path: Path):
        plan = MoviePlanData(
            directory=str(tmp_path),
            files=[
                MoviePlanEntry(file="nonexistent.mkv", tmdb_id=550, name="Fight Club", year="1999"),
            ],
        )
        with pytest.raises(FileNotFoundError, match="does not exist"):
            movie_plan_to_renames(plan)

    def test_missing_directory_raises(self, tmp_path: Path):
        plan = MoviePlanData(
            directory=str(tmp_path / "nonexistent"),
            files=[
                MoviePlanEntry(file="fc.mkv", tmdb_id=550, name="Fight Club", year="1999"),
            ],
        )
        with pytest.raises(FileNotFoundError, match="directory does not exist"):
            movie_plan_to_renames(plan)

    def test_skipped_entries_not_checked_for_existence(self, tmp_path: Path):
        (tmp_path / "real.mkv").touch()

        plan = MoviePlanData(
            directory=str(tmp_path),
            files=[
                MoviePlanEntry(file="real.mkv", tmdb_id=550, name="Fight Club", year="1999"),
                MoviePlanEntry(file="ghost.mkv"),
            ],
        )
        result = movie_plan_to_renames(plan)

        assert len(result.ops) == 1
        assert len(result.unmatched) == 1
