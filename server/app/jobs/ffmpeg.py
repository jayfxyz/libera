"""ffmpeg command lines."""

from __future__ import annotations

from ..audible_api.content import DownloadInfo


def decrypt_args(info: DownloadInfo, src: str, out: str, fmt: str, chapters_file: str = "",
                 cover_file: str = "") -> list[str]:
    """Decrypt an AAX/AAXC file into out.

    m4b copies the audio stream; mp3 re-encodes with LAME (VBR ~190 kbps).
    When chapters_file (FFMETADATA1) is given, its chapters replace the ones
    in the Audible file; the source's other tags are kept either way.
    When cover_file (JPEG) is given, it's embedded as the cover artwork.
    """
    args = ["ffmpeg", "-y"]
    # Decryption options apply to the next input, so they go before the source.
    if info.format == "aaxc":
        args += ["-audible_key", info.key, "-audible_iv", info.iv]
    else:
        args += ["-activation_bytes", info.activation_bytes]
    args += ["-i", src]
    inputs = 1
    if chapters_file:
        args += ["-i", chapters_file]
        chapters_input, inputs = inputs, inputs + 1
    if cover_file:
        args += ["-i", cover_file]
        cover_input, inputs = inputs, inputs + 1

    args += ["-map", "0:a", "-map_metadata", "0"]
    if chapters_file:
        args += ["-map_chapters", str(chapters_input)]
    if cover_file:
        args += ["-map", f"{cover_input}:v", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
    else:
        args.append("-vn")

    if fmt == "mp3":
        args += ["-c:a", "libmp3lame", "-q:a", "2"]
        if cover_file:
            args += ["-id3v2_version", "3"]  # the ID3 version most players read artwork from
    else:
        args += ["-c:a", "copy"]
    args.append(out)
    return args


def chapter_args(src: str, out: str, start_sec: float, end_sec: float) -> list[str]:
    """Cut one chapter out of a decrypted file (stream copy)."""
    return ["ffmpeg", "-y", "-ss", f"{start_sec:f}", "-to", f"{end_sec:f}", "-i", src, "-c", "copy", out]
