"""Audio checks and conversion with FFmpeg. Not an AI step, so it may run in a request."""

import asyncio
from pathlib import Path

NORMALISED_CONTENT_TYPE = "audio/mpeg"
NORMALISED_EXTENSION = ".mp3"
_TIMEOUT_SECONDS = 300


class NotAudio(Exception):
    pass


async def _run(*args: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), _TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise NotAudio("timed out reading the audio") from None
    if process.returncode != 0:
        raise NotAudio("FFmpeg could not read the file")
    return stdout


async def normalise(source: Path, target: Path) -> None:
    """Constant-bitrate mono MP3: every browser plays it (open-source Chromium has no AAC),
    every speech provider accepts it, and constant bitrate keeps seeking exact."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        await _run(
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
            "-vn", "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "96k",
            str(target),
        )  # fmt: skip
    except NotAudio:
        target.unlink(missing_ok=True)
        raise


async def duration_ms(path: Path) -> int:
    out = await _run(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    )  # fmt: skip
    try:
        seconds = float(out.decode().strip())
    except ValueError:
        raise NotAudio("no duration") from None
    if seconds <= 0:
        raise NotAudio("empty audio")
    return round(seconds * 1000)
