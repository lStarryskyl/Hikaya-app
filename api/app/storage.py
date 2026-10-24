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


def partial_key(key: str) -> str:
    """Where a file is written before it replaces `key`: `a/b.mp3` -> `a/b-part.mp3`."""
    stem, dot, extension = key.rpartition(".")
    return f"{stem}-part.{extension}" if dot and "/" not in extension else f"{key}-part"


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

    def prepare(self, key: str) -> Path:
        """The path for a tool (such as FFmpeg) to write `key` to, with its folder made."""
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_bytes(self, key: str, data: bytes) -> None:
        """Write `key` whole: readers see the old file or the new one, never a partial one."""
        partial = self.prepare(partial_key(key))
        partial.write_bytes(data)
        partial.replace(self.path(key))

    def copy(self, source: str, target: str) -> None:
        partial = self.prepare(partial_key(target))
        shutil.copyfile(self.path(source), partial)
        partial.replace(self.path(target))

    def move(self, source: str, target: str) -> None:
        self.prepare(target)
        self.path(source).replace(self.path(target))

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
