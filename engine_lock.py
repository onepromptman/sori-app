"""
engine_lock.py: one Sori engine per state folder.

The browser app, the desktop window and the headless sweep each start an
engine that queues new episodes. Two engines on one shows.json queue every
episode twice, so whichever starts first takes `engine.lock` in the state
folder and the others stand down.

The lock is an operating-system file lock, not a "this file exists" marker:
the system drops it when the process ends, however it ends, so a crash never
leaves Sori locked out. The file itself stays behind and is reused.
"""

from __future__ import annotations

import os
from pathlib import Path

LOCK_NAME = "engine.lock"


class EngineLock:
    """Holds the engine lock for a state folder until released or the process ends."""

    def __init__(self, home: Path) -> None:
        self.path = Path(home) / LOCK_NAME
        self._fd: int | None = None

    def acquire(self) -> bool:
        """Take the lock. False when another engine already holds it."""
        if self._fd is not None:
            return True
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
        try:
            _lock(fd)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            _unlock(fd)
        except OSError:
            pass
        os.close(fd)

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


if os.name == "nt":
    import msvcrt

    def _lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
