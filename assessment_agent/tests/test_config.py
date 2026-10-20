import os

import pytest

import assessment_agent.config as cfg
from assessment_agent.main import create_assessment_app


def test_ensure_data_dir_creates_missing_directories(tmp_path, monkeypatch):
    target = tmp_path / "a" / "b"
    monkeypatch.setattr(cfg, "DATA_DIR", str(target))
    cfg.ensure_data_dir()
    assert target.is_dir()


def test_ensure_data_dir_rejects_a_path_that_is_a_file(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(cfg, "DATA_DIR", str(blocker))
    with pytest.raises(RuntimeError, match="Cannot create DATA_DIR"):
        cfg.ensure_data_dir()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_ensure_data_dir_rejects_an_unwritable_directory(tmp_path, monkeypatch):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    monkeypatch.setattr(cfg, "DATA_DIR", str(locked))
    try:
        with pytest.raises(RuntimeError, match="not writable"):
            cfg.ensure_data_dir()
    finally:
        locked.chmod(0o700)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_app_refuses_to_start_when_data_dir_is_unwritable(tmp_path, monkeypatch):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    monkeypatch.setattr(cfg, "DATA_DIR", str(locked))
    try:
        with pytest.raises(RuntimeError, match="not writable"):
            create_assessment_app()
    finally:
        locked.chmod(0o700)
