"""Run external tools (ffmpeg, ffprobe) without blocking the event loop."""

from __future__ import annotations

import asyncio


async def run(args: list[str]) -> tuple[int, bytes, bytes]:
    """Run a command; returns (exit code, stdout, stderr).

    If the calling task is cancelled (download cancelled, shutdown), the
    process is killed rather than left running.
    """
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await proc.communicate()
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    return proc.returncode or 0, out, err
