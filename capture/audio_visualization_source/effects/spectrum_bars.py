import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, frequency_bands, hsv_color


class SpectrumBarsEffect(AudioEffect):
    effect_id = "spectrum_bars"
    label = "玻璃频谱"
    description = "带峰值游标的悬浮玻璃柱，低频到高频采用连续流光配色。"
    default_enabled = True
    order = 20
    parameters = (
        ParameterSpec("bars", "柱数", 16, 64, 32, 4, 0),
        ParameterSpec("height", "高度", 0.25, 0.92, 0.72, 0.05, 2),
        ParameterSpec("smoothing", "回落平滑", 0.0, 0.96, 0.76, 0.04, 2),
        ParameterSpec("gap", "间距", 0, 5, 2, 1, 0),
        ParameterSpec("glow", "辉光", 0.0, 1.5, 0.72, 0.05, 2),
    )

    def __init__(self) -> None:
        super().__init__()
        self.peaks = np.zeros(0, dtype=np.float32)

    def reset(self) -> None:
        super().reset()
        self.peaks = np.zeros(0, dtype=np.float32)

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = int(self.values["bars"])
        bands = self.smooth("bars", frequency_bands(frame, count), self.values["smoothing"])
        if self.peaks.size != count:
            self.peaks = np.zeros(count, dtype=np.float32)
        self.peaks = np.maximum(bands, self.peaks - max(0.008, dt * 0.55))
        slot = width / count
        gap = int(self.values["gap"])
        max_height = height * self.values["height"]
        baseline = height - max(4, int(height * 0.035))
        layer = np.zeros_like(canvas)
        for index, value in enumerate(bands):
            x1 = int(index * slot + gap / 2)
            x2 = max(x1, int((index + 1) * slot - 1 - gap / 2))
            y = baseline - max(1, int(value * max_height))
            color = hsv_color(92 + index * 78 / max(1, count - 1))
            cv2.rectangle(layer, (x1, y), (x2, baseline), color, -1)
            peak_y = baseline - int(self.peaks[index] * max_height)
            cv2.line(canvas, (x1, peak_y), (x2, peak_y), (245, 255, 255), 1, cv2.LINE_AA)
        add_glow(canvas, layer, 4.5, self.values["glow"])
