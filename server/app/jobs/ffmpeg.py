"""ffmpeg command lines."""

from __future__ import annotations

from ..audible_api.content import DownloadInfo


def decrypt_args(info: DownloadInfo, src: str, out: str, fmt: str, chapters_file: str = "") -> list[str]:
    """Decrypt an AAX/AAXC file into out.

    m4b copies the audio stream; mp3 re-encodes with LAME (VBR ~190 kbps).
    When chapters_file (FFMETADATA1) is given, its chapters replace the ones
    in the Audible file and the source's other tags are kept.
    """
    args = ["ffmpeg", "-y"]
    # Decryption options apply to the next input, so they go before the source.
    if info.format == "aaxc":
        args += ["-audible_key", info.key, "-audible_iv", info.iv]
    else:
        args += ["-activation_bytes", info.activation_bytes]
    args += ["-i", src]
    if chapters_file:
        args += ["-i", chapters_file, "-map", "0:a", "-map_metadata", "0", "-map_chapters", "1"]
    args.append("-vn")
    if fmt == "mp3":
        args += ["-c:a", "libmp3lame", "-q:a", "2"]
    else:
        args += ["-c:a", "copy"]
    args.append(out)
    return args


def chapter_args(src: str, out: str, start_sec: float, end_sec: float) -> list[str]:
    """Cut one chapter out of a decrypted file (stream copy)."""
    return ["ffmpeg", "-y", "-ss", f"{start_sec:f}", "-to", f"{end_sec:f}", "-i", src, "-c", "copy", out]
