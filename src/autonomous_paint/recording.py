"""Numbered frame capture and FFmpeg recording."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil
import subprocess

import pygame
from PIL import Image


def save_frame(surface: pygame.Surface, directory: Path, index: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"frame_{index:06d}.png"
    save_png(surface, path)
    return path


def save_png(surface: pygame.Surface, path: Path) -> Path:
    """Encode fully in memory, write once, and verify the retained PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = pygame.image.tobytes(surface, "RGB")
    image = Image.frombytes("RGB", surface.get_size(), raw)
    encoded = BytesIO()
    image.save(encoded, format="PNG")
    path.write_bytes(encoded.getvalue())
    with Image.open(path) as verification:
        verification.load()
    return path


def encode_recordings(
    frame_directory: Path,
    gif_path: Path,
    mp4_path: Path,
    fps: int = 3,
) -> tuple[Path, Path]:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("FFmpeg is required to encode recordings")
    if fps < 1:
        raise ValueError("fps must be at least one")
    pattern = str(frame_directory / "frame_%06d.png")
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    palette_filter = (
        "[0:v]split[source][palette_input];"
        "[palette_input]palettegen=max_colors=128[palette];"
        "[source][palette]paletteuse=dither=bayer:bayer_scale=3"
    )
    commands = [
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            pattern,
            "-filter_complex",
            palette_filter,
            "-loop",
            "0",
            str(gif_path),
        ],
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            pattern,
            "-c:v",
            "libx264",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(mp4_path),
        ],
    ]
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "unknown FFmpeg error"
            raise RuntimeError(f"recording failed: {detail}")
    return gif_path, mp4_path
