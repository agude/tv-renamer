"""Tests for rsync wrapper."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from tv_renamer.copier import copy_to_dest


def _completed(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=stderr)


@patch("tv_renamer.copier.subprocess.run")
def test_copy_basic_flags(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    copy_to_dest(src, dest)

    transfer_call = mock_run.call_args_list[0]
    cmd = transfer_call[0][0]
    assert cmd[0] == "rsync"
    assert "-av" in cmd
    assert "--checksum" in cmd
    assert "--progress" in cmd
    assert "--dry-run" not in cmd


@patch("tv_renamer.copier.subprocess.run")
def test_copy_dry_run_flag(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed(stdout="file list\n")

    result = copy_to_dest(src, dest, dry_run=True)

    cmd = mock_run.call_args[0][0]
    assert "--dry-run" in cmd
    assert result.dry_run_output == "file list\n"


@patch("tv_renamer.copier.subprocess.run")
def test_copy_source_trailing_slash(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    copy_to_dest(src, dest)

    cmd = mock_run.call_args_list[0][0][0]
    src_arg = cmd[-2]
    assert src_arg.endswith("/")
    assert not src_arg.endswith("//")


@patch("tv_renamer.copier.subprocess.run")
def test_copy_dest_is_string(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    copy_to_dest(src, dest)

    cmd = mock_run.call_args_list[0][0][0]
    assert cmd[-1] == str(dest)


@patch("tv_renamer.copier.subprocess.run")
def test_copy_check_true(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    copy_to_dest(src, dest)

    assert mock_run.call_args_list[0][1]["check"] is True


@patch("tv_renamer.copier.subprocess.run")
def test_real_copy_streams_output(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    copy_to_dest(src, dest)

    transfer_kwargs = mock_run.call_args_list[0][1]
    assert transfer_kwargs["capture_output"] is False


@patch("tv_renamer.copier.subprocess.run")
def test_dry_run_captures_output(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    copy_to_dest(src, dest, dry_run=True)

    assert mock_run.call_args[1]["capture_output"] is True


@patch("tv_renamer.copier.subprocess.run")
def test_verify_pass_runs_after_real_copy(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    copy_to_dest(src, dest)

    assert mock_run.call_count == 2
    verify_cmd = mock_run.call_args_list[1][0][0]
    assert "-n" in verify_cmd
    assert "--checksum" in verify_cmd
    assert "--itemize-changes" in verify_cmd


@patch("tv_renamer.copier.subprocess.run")
def test_verify_pass_not_run_on_dry_run(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    copy_to_dest(src, dest, dry_run=True)

    assert mock_run.call_count == 1


@patch("tv_renamer.copier.subprocess.run")
def test_verify_pass_clean_returns_verified(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.return_value = _completed()

    result = copy_to_dest(src, dest)

    assert result.verified is True


@patch("tv_renamer.copier.subprocess.run")
def test_verify_pass_differences_returns_unverified(mock_run: MagicMock, tmp_path: Path):
    src = tmp_path / "source"
    src.mkdir()
    dest = tmp_path / "dest"
    mock_run.side_effect = [
        _completed(),
        _completed(stdout=">f..T...... file.mkv\n"),
    ]

    result = copy_to_dest(src, dest)

    assert result.verified is False
