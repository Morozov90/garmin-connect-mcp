"""Local credential storage. No secret is accepted through an MCP argument."""

from __future__ import annotations

import fcntl
import os
import stat
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Settings:
    directory: Path
    timezone: str = "America/Vancouver"

    def __post_init__(self):
        if not self.directory.is_absolute():
            raise ValueError("GARMIN_MCP_CONFIG_DIR must be an absolute path.")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as from_error:
            raise ValueError("GARMIN_MCP_TIMEZONE must name an IANA timezone.") from from_error

    @classmethod
    def from_env(cls) -> Settings:
        default = Path.home() / "Library/Application Support/garmin-training-mcp"
        return cls(
            Path(os.environ.get("GARMIN_MCP_CONFIG_DIR", str(default))).expanduser(),
            os.environ.get("GARMIN_MCP_TIMEZONE", "America/Vancouver"),
        )

    @property
    def key_file(self) -> Path:
        return self.directory / "personal-api-key"

    @property
    def cache_file(self) -> Path:
        return self.directory / "bearer-token.json"

    @property
    def lock_file(self) -> Path:
        return self.directory / "credentials.lock"


def private_directory(settings: Settings) -> None:
    directory = settings.directory
    if directory.is_symlink():
        raise ValueError("Credential directory must not be a symlink.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_uid != os.getuid():
        raise ValueError("Credential directory must belong to the current user.")
    directory.chmod(0o700)


def check_private(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("Credential files must not be symlinks.")
    try:
        info = path.stat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("Credential files must be regular files owned by the current user.")
    if info.st_mode & 0o077:
        raise ValueError("Credential file permissions must be 600; run chmod 600 locally.")


@contextmanager
def credential_lock(settings: Settings, timeout: float = 5):
    private_directory(settings)
    check_private(settings.lock_file)
    fd = os.open(settings.lock_file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Credential storage is busy; retry shortly.") from None
                time.sleep(0.01)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read_key(settings: Settings) -> str:
    if "GARMIN_PERSONAL_API_KEY" in os.environ:
        key = os.environ["GARMIN_PERSONAL_API_KEY"].strip()
        if not key:
            raise ValueError("GARMIN_PERSONAL_API_KEY is empty; unset it or provide a valid key.")
        return key
    check_private(settings.key_file)
    try:
        key = settings.key_file.read_text().strip()
    except FileNotFoundError:
        raise ValueError("No Personal API Key. Run garmin-mcp setup in a terminal.") from None
    if not key:
        raise ValueError("Key file is empty; run garmin-mcp setup.")
    return key


def save_key(settings: Settings, key: str) -> None:
    key = key.strip()
    if not key:
        raise ValueError("Personal API Key must not be empty.")
    with credential_lock(settings):
        check_private(settings.key_file)
        fd, name = tempfile.mkstemp(prefix=".key-", dir=settings.directory)
        try:
            with os.fdopen(fd, "w") as file:
                file.write(key + "\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, settings.key_file)
        finally:
            Path(name).unlink(missing_ok=True)
