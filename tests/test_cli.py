"""Tests for CLI argument parsing and wiring."""

import pytest

from tv_renamer.cli import main


def test_no_args_exits():
    with pytest.raises(SystemExit):
        main([])


def test_scan_missing_dir():
    with pytest.raises(SystemExit):
        main(["scan"])


def test_rename_requires_id():
    with pytest.raises(SystemExit):
        main(["rename", "/tmp/fake"])
