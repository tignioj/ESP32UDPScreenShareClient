from __future__ import annotations

import cv2
import numpy as np

from .base import AudioFrame


def frequency_bands(frame: AudioFrame, count: int, low_hz: float = 45.0,
                    high_hz: float = 16000.0) -> np.ndarray:
    """Convert an FFT into perceptual log-spaced bands in the 0..1 range."""
    spectrum = np.asarray(frame.spectrum, dtype=np.float32)
    if spectrum.size < 3 or not np.any(spectrum > 0):
        return np.zeros(count, dtype=np.float32)

    hz_per_bin = frame.sample_rate / frame.block_size
    low_bin = max(1, int(low_hz / hz_per_bin))
    high_bin = min(spectrum.size - 1, max(low_bin + 2, int(high_hz / hz_per_bin)))
    edges = np.geomspace(low_bin, high_bin, count + 1)
    bands = np.zeros(count, dtype=np.float32)
    for index in range(count):
        start = max(1, int(edges[index]))
        end = min(spectrum.size, max(start + 1, int(edges[index + 1])))
        bands[index] = float(np.sqrt(np.mean(np.square(spectrum[start:end]))))

    bands = np.log1p(bands * 4.0)
    reference = float(np.percentile(bands, 94))
    if reference > 1e-6:
        bands = np.clip(bands / reference, 0.0, 1.15)
    return bands


def hsv_color(hue: float, saturation: int = 235, value: int = 255) -> tuple[int, int, int]:
    pixel = np.uint8([[[int(hue) % 180, saturation, value]]])
    bgr = cv2.cvtColor(pixel, cv2.COLOR_HSV2BGR)[0, 0]
    return tuple(int(channel) for channel in bgr)


def add_glow(canvas: np.ndarray, layer: np.ndarray, radius: float = 6.0,
             strength: float = 0.7) -> None:
    if not np.any(layer):
        return
    blurred = cv2.GaussianBlur(layer, (0, 0), sigmaX=max(0.5, radius), sigmaY=max(0.5, radius))
    cv2.addWeighted(canvas, 1.0, blurred, strength, 0, dst=canvas)
    cv2.add(canvas, layer, dst=canvas)


def polyline(canvas: np.ndarray, points: np.ndarray, color: tuple[int, int, int],
             thickness: int = 1, closed: bool = False) -> None:
    if len(points) > 1:
        cv2.polylines(canvas, [np.asarray(points, dtype=np.int32)], closed, color,
                      thickness, cv2.LINE_AA)


def gradient_background(width: int, height: int) -> np.ndarray:
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    x = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
    vignette = np.clip(1.0 - 0.42 * (x * x + (y - 0.45) ** 2), 0.45, 1.0)
    result = np.empty((height, width, 3), dtype=np.float32)
    result[:, :, 0] = (13 + 13 * y) * vignette
    result[:, :, 1] = (5 + 7 * y) * vignette
    result[:, :, 2] = (12 + 8 * (1.0 - y)) * vignette
    return np.clip(result, 0, 255).astype(np.uint8)
