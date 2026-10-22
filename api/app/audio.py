"""Audio checks and conversion with FFmpeg. Not an AI step, so it may run in a request."""

import asyncio
from pathlib import Path

# Accepted upload types: file extension to store it under, and the FFmpeg demuxer to read it
# with. Naming the demuxer means FFmpeg never guesses from the content, so a playlist dressed
# up as audio can never make it open other files or URLs.
UPLOAD_FORMATS: dict[str, tuple[str, str]] = {
    "audio/wav": (".wav", "wav"),
    "audio/x-wav": (".wav", "wav"),
    "audio/wave": (".wav", "wav"),
    "audio/webm": (".webm", "matroska"),
    "video/webm": (".webm", "matroska"),
    "audio/ogg": (".ogg", "ogg"),
    "audio/mpeg": (".mp3", "mp3"),
    "audio/mp3": (".mp3", "mp3"),
    "audio/mp4": (".m4a", "mov"),
    "audio/x-m4a": (".m4a", "mov"),
    "audio/aac": (".aac", "aac"),
    "audio/flac": (".flac", "flac"),
}

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


def upload_format(content_type: str | None) -> tuple[str, str] | None:
    """(extension, demuxer) for an accepted upload type such as `audio/webm;codecs=opus`."""
    base = (content_type or "").split(";")[0].strip().lower()
    return UPLOAD_FORMATS.get(base)


async def normalise(source: Path, target: Path, demuxer: str) -> None:
    """Constant-bitrate mono MP3: every browser plays it (open-source Chromium has no AAC),
    every speech provider accepts it, and constant bitrate keeps seeking exact."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        await _run(
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-protocol_whitelist", "file", "-f", demuxer, "-i", str(source),
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
