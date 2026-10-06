"""Merge a silent video file and a WAV audio file into a single MP4.

Uses the FFmpeg binary bundled with `imageio-ffmpeg` — no external install
needed on the user's machine.
"""

import os
import subprocess
import tempfile
from typing import Optional

import imageio_ffmpeg


def mux_audio_video(
    video_path: str,
    audio_path: str,
    output_path: str,
) -> Optional[str]:
    """Combine `video_path` + `audio_path` into `output_path`.

    Returns None on success, or an error message string on failure.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # -c:v copy  : pas de ré-encodage vidéo (rapide, sans perte)
    # -c:a aac   : encode l'audio en AAC (compatible MP4 partout)
    # -shortest  : s'arrête sur le flux le plus court (évite les décalages)
    cmd = [
        ffmpeg,
        "-y",                    # overwrite output
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            # Hide the console window that would otherwise flash on Windows
            creationflags=subprocess.CREATE_NO_WINDOW
            if os.name == "nt"
            else 0,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace").strip().splitlines()
            return err[-1] if err else f"ffmpeg exited with {result.returncode}"
    except Exception as exc:  # noqa: BLE001
        return str(exc)

    return None


def make_temp_path(suffix: str) -> str:
    """Return a temporary file path with the given suffix."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path