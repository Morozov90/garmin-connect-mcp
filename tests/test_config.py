"""Credential tests use synthetic keys and temporary directories only."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from garmin_training_mcp.config import Settings, credential_lock, read_key, save_key


def test_save_is_private_and_env_takes_precedence(tmp_path, monkeypatch):
    settings = Settings(tmp_path / "config")
    save_key(settings, "synthetic-key")
    assert read_key(settings) == "synthetic-key"
    assert settings.key_file.stat().st_mode & 0o777 == 0o600
    assert settings.directory.stat().st_mode & 0o777 == 0o700
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "override")
    assert read_key(settings) == "override"
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", " ")
    with pytest.raises(ValueError, match="empty"):
        read_key(settings)


def test_rejects_insecure_or_symlinked_credentials(tmp_path):
    settings = Settings(tmp_path / "config")
    save_key(settings, "synthetic-key")
    settings.key_file.chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        read_key(settings)
    settings.key_file.unlink()
    target = tmp_path / "target"
    target.write_text("other")
    settings.key_file.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        save_key(settings, "replacement")
    assert target.read_text() == "other"


def test_settings_validate_zone_and_absolute_directory(monkeypatch):
    monkeypatch.setenv("GARMIN_MCP_CONFIG_DIR", "relative")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("GARMIN_MCP_CONFIG_DIR", "/tmp/synthetic-garmin-config")
    monkeypatch.setenv("GARMIN_MCP_TIMEZONE", "Bad/Zone")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_lock_bounds_wait_and_serializes_threads(tmp_path):
    settings = Settings(tmp_path / "config")
    with credential_lock(settings), ThreadPoolExecutor(1) as pool:

        def attempt():
            with credential_lock(settings, timeout=0.03):
                return True

        with pytest.raises(TimeoutError):
            pool.submit(attempt).result()
    with credential_lock(settings, timeout=0.03):
        assert settings.lock_file.exists()


def test_missing_and_blank_keys_are_actionable(tmp_path):
    settings = Settings(tmp_path / "config")
    with pytest.raises(ValueError, match="setup"):
        read_key(settings)
    with pytest.raises(ValueError):
        save_key(settings, " ")


def test_default_macos_directory(monkeypatch):
    monkeypatch.delenv("GARMIN_MCP_CONFIG_DIR", raising=False)
    assert (
        Settings.from_env().directory
        == Path.home() / "Library/Application Support/garmin-training-mcp"
    )


def test_setup_never_falls_back_to_echoed_input(tmp_path, monkeypatch):
    import getpass
    import sys
    import warnings

    from garmin_training_mcp.__main__ import setup

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def no_terminal(prompt):
        warnings.warn("Cannot control terminal echo", getpass.GetPassWarning, stacklevel=1)
        pytest.fail("getpass reached its echoing fallback")

    monkeypatch.setattr(getpass, "getpass", no_terminal)
    with pytest.raises(ValueError, match="hidden"):
        setup(Settings(tmp_path / "config"))
    assert not (tmp_path / "config/personal-api-key").exists()


def test_lock_coordinates_separate_client_processes(tmp_path):
    import subprocess
    import sys

    settings = Settings(tmp_path / "config")
    script = """
import sys
from pathlib import Path
from garmin_training_mcp.config import Settings, credential_lock
try:
    with credential_lock(Settings(Path(sys.argv[1])), timeout=0.03):
        sys.exit(2)
except TimeoutError:
    sys.exit(0)
"""
    with credential_lock(settings):
        result = subprocess.run([sys.executable, "-c", script, str(settings.directory)], timeout=5)
    assert result.returncode == 0
