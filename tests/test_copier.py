"""Tests for rsync wrapper."""

from pathlib import Path
from unittest.mock import patch

from tv_renamer.copier import copy_to_dest


@patch("tv_renamer.copier.subprocess.run")
def test_copy_basic_flags(mock_run, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"

    copy_to_dest(src, dest)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "rsync"
    assert "-av" in cmd
    assert "--checksum" in cmd
    assert "--progress" in cmd
    assert "--dry-run" not in cmd


@patch("tv_renamer.copier.subprocess.run")
def test_copy_dry_run_flag(mock_run, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"

    copy_to_dest(src, dest, dry_run=True)

    cmd = mock_run.call_args[0][0]
    assert "--dry-run" in cmd


@patch("tv_renamer.copier.subprocess.run")
def test_copy_source_trailing_slash(mock_run, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"

    copy_to_dest(src, dest)

    cmd = mock_run.call_args[0][0]
    src_arg = cmd[-2]
    assert src_arg.endswith("/")
    assert not src_arg.endswith("//")


@patch("tv_renamer.copier.subprocess.run")
def test_copy_dest_is_string(mock_run, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"

    copy_to_dest(src, dest)

    cmd = mock_run.call_args[0][0]
    assert cmd[-1] == str(dest)


@patch("tv_renamer.copier.subprocess.run")
def test_copy_check_true(mock_run, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"

    copy_to_dest(src, dest)

    assert mock_run.call_args[1]["check"] is True


@patch("tv_renamer.copier.subprocess.run")
def test_real_copy_streams_output(mock_run, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"

    copy_to_dest(src, dest)

    assert mock_run.call_args[1]["capture_output"] is False


@patch("tv_renamer.copier.subprocess.run")
def test_dry_run_captures_output(mock_run, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"

    copy_to_dest(src, dest, dry_run=True)

    assert mock_run.call_args[1]["capture_output"] is True
