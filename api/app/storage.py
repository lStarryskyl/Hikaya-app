"""Where stored files live. Today: a folder on local disk.

Callers only use keys (like `stories/<id>/<file>`), never paths they build themselves,
so a different backend can replace this one without touching them.
"""

import os
import re
from functools import lru_cache
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)*(\.[A-Za-z0-9]+)?$")


class TooLarge(Exception):
    pass


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def path(self, key: str) -> Path:
        if not _SAFE_KEY.match(key):
            raise ValueError(f"unsafe storage key: {key!r}")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"storage key escapes the root: {key!r}")
        return path

    async def save_upload(self, key: str, upload: UploadFile, max_bytes: int) -> int:
        """Streams an upload to disk. Raises TooLarge (leaving nothing behind) past max_bytes."""
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            with open(path, "wb") as out:
                while chunk := await upload.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise TooLarge
                    out.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return written

    def size(self, key: str) -> int:
        return self.path(key).stat().st_size

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


@lru_cache
def _storage_for(root: str) -> LocalStorage:
    return LocalStorage(root)


def get_storage() -> LocalStorage:
    root = get_settings().media_dir
    os.makedirs(root, exist_ok=True)
    return _storage_for(root)
