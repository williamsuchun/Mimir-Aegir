"""Deterministic synthetic media bundle for clone-to-success validation."""

from __future__ import annotations

import math
import wave
from pathlib import Path

import cv2
import numpy as np


class DemoError(RuntimeError):
    pass


def create_demo_bundle(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    video_path = root / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 180)
    )
    if not writer.isOpened():
        raise DemoError("OpenCV could not create the deterministic demo video")
    for frame_index in range(60):
        frame = np.full((180, 320, 3), 28, dtype=np.uint8)
        if 32 <= frame_index <= 48:
            left = 20 + (frame_index - 32) * 14
            frame[55:120, left : left + 45] = (220, 220, 220)
        writer.write(frame)
    writer.release()

    sample_rate = 8000
    duration = 6
    samples = np.zeros(sample_rate * duration, dtype=np.float64)
    for index in range(sample_rate * 3, sample_rate * 5):
        samples[index] = 0.55 * math.sin(2 * math.pi * 440 * index / sample_rate)
    pcm = np.clip(samples * 32767, -32768, 32767).astype("<i2")
    with wave.open(str(video_path.with_suffix(".wav")), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())

    video_path.with_suffix(".vtt").write_text(
        "WEBVTT\n\n"
        "00:00:00.500 --> 00:00:01.400\n"
        "Earlier commentary discussed an offside call.\n\n"
        "00:00:03.100 --> 00:00:04.800\n"
        "A jump, impact, and loud cheer mark the finish.\n",
        encoding="utf-8",
    )
    return video_path
