"""Where stored files live. Today: a folder on local disk.

Callers only use keys (like `stories/<id>/<file>`), never paths they build themselves,
so a different backend can replace this one without touching them.
"""

import asyncio
import os
import re
import shutil
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
        # Disk writes happen in a thread so a large upload never blocks the event loop.
        out = await asyncio.to_thread(open, path, "wb")
        try:
            while chunk := await upload.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise TooLarge
                await asyncio.to_thread(out.write, chunk)
        except BaseException:
            out.close()
            path.unlink(missing_ok=True)
            raise
        out.close()
        return written

    def size(self, key: str) -> int:
        return self.path(key).stat().st_size

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def delete_tree(self, prefix: str) -> None:
        """Remove a whole folder of stored files, such as everything for one story."""
        path = self.path(prefix)
        if path.is_dir():
            shutil.rmtree(path)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.path(key).unlink(missing_ok=True)


@lru_cache
def _storage_for(root: str) -> LocalStorage:
    return LocalStorage(root)


def get_storage() -> LocalStorage:
    root = get_settings().media_dir
    os.makedirs(root, exist_ok=True)
    return _storage_for(root)
