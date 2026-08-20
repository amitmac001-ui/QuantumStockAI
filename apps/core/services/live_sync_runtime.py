from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings


class LiveSyncAlreadyRunning(RuntimeError):
    pass


@contextmanager
def live_sync_lock(stale_after_seconds: int = 1800):
    """Small cross-process lock; no scanner or provider state is held inside it."""

    path = Path(settings.BASE_DIR) / "data" / "technical_scanner_publish.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = None
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        if time.time() - path.stat().st_mtime <= stale_after_seconds:
            raise LiveSyncAlreadyRunning(
                "Technical Scanner publish already running."
            ) from exc
        path.unlink(missing_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
            path.unlink(missing_ok=True)
