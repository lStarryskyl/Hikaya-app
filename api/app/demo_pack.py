"""Export and import the provider result cache as a "demo pack".

    python -m app.demo_pack export [path]   # default demo-pack/hikaya-demo-pack.tar.gz
    python -m app.demo_pack import [path]

Run the demo stories once with live AI on, export, and import on the demo laptop: with live
AI off, every step is then answered from the cache and nothing is paid for on stage.

The archive holds `cache.json` (one row per cached result) and `files/<key>` for results
that point at a stored file. Import accepts nothing else, so an archive cannot write outside
the media store.
"""

import asyncio
import io
import json
import sys
import tarfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import dispose_engine, get_sessionmaker
from app.models import ProviderCacheEntry
from app.storage import get_storage

DEFAULT_PATH = Path("demo-pack/hikaya-demo-pack.tar.gz")
MAX_MEMBER_BYTES = 200 * 1024 * 1024


class BadPack(Exception):
    pass


async def export_pack(sessionmaker: async_sessionmaker[AsyncSession], path: Path) -> int:
    storage = get_storage()
    async with sessionmaker() as session:
        rows = (await session.execute(select(ProviderCacheEntry))).scalars().all()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(
        [
            {
                "key": r.key,
                "operation": r.operation,
                "provider": r.provider,
                "result": r.result,
                "file_key": r.file_key,
            }
            for r in rows
        ],
        ensure_ascii=False,
    ).encode()
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("cache.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        for r in rows:
            if r.file_key and storage.exists(r.file_key):
                tar.add(storage.path(r.file_key), arcname=f"files/{r.file_key}", recursive=False)
    return len(rows)


async def import_pack(sessionmaker: async_sessionmaker[AsyncSession], path: Path) -> int:
    """Adds results not already cached. Returns how many were added."""
    storage = get_storage()
    with tarfile.open(path, "r:gz") as tar:
        members = tar.getmembers()
        for m in members:
            ok = (
                m.isfile()
                and m.size <= MAX_MEMBER_BYTES
                and (m.name == "cache.json" or m.name.startswith("files/"))
            )
            if ok and m.name.startswith("files/"):
                try:
                    storage.path(m.name.removeprefix("files/"))  # rejects unsafe keys
                except ValueError:
                    ok = False
            if not ok:
                raise BadPack(f"unexpected entry in demo pack: {m.name!r}")
        cache = tar.extractfile("cache.json")
        if cache is None:
            raise BadPack("demo pack has no cache.json")
        rows = json.loads(cache.read())
        for m in members:
            if m.name.startswith("files/"):
                target = storage.path(m.name.removeprefix("files/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(m).read())

    added = 0
    async with sessionmaker() as session:
        for row in rows:
            result = await session.execute(
                pg_insert(ProviderCacheEntry)
                .values(
                    key=row["key"],
                    operation=row["operation"],
                    provider=row["provider"],
                    result=row["result"],
                    file_key=row.get("file_key"),
                )
                .on_conflict_do_nothing(index_elements=["key"])
            )
            added += result.rowcount or 0
        await session.commit()
    return added


async def _main(command: str, path: Path) -> None:
    maker = get_sessionmaker()
    try:
        if command == "export":
            print(f"Exported {await export_pack(maker, path)} cached results to {path}")
        elif command == "import":
            print(f"Imported {await import_pack(maker, path)} new cached results from {path}")
        else:
            raise SystemExit("usage: python -m app.demo_pack export|import [path]")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: python -m app.demo_pack export|import [path]")
    asyncio.run(_main(args[0], Path(args[1]) if len(args) > 1 else DEFAULT_PATH))
