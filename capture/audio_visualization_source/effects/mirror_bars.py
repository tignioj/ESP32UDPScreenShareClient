import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, frequency_bands, hsv_color


class MirrorBarsEffect(AudioEffect):
    effect_id = "mirror_bars"
    label = "镜像城市"
    description = "从中央地平线向上下生长的霓虹天际线，配有独立峰值游标。"
    default_enabled = False
    order = 60
    parameters = (
        ParameterSpec("bars", "柱数", 16, 56, 36, 4, 0),
        ParameterSpec("height", "展开高度", 0.15, 0.48, 0.39, 0.03, 2),
        ParameterSpec("smoothing", "回落平滑", 0.0, 0.96, 0.79, 0.04, 2),
        ParameterSpec("glow", "辉光", 0.0, 1.5, 0.9, 0.05, 2),
        ParameterSpec("hue", "主色相", 0, 179, 140, 5, 0),
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
        bands = self.smooth("mirror", frequency_bands(frame, count), self.values["smoothing"])
        if self.peaks.size != count:
            self.peaks = np.zeros(count, dtype=np.float32)
        self.peaks = np.maximum(bands, self.peaks - max(0.007, dt * 0.48))
        center_y = height // 2
        max_height = height * self.values["height"]
        slot = width / count
        layer = np.zeros_like(canvas)
        for index, value in enumerate(bands):
            x1 = int(index * slot + 1)
            x2 = max(x1, int((index + 1) * slot - 2))
            amount = max(1, int(value * max_height))
            color = hsv_color(self.values["hue"] + index * 42 / max(1, count - 1))
            cv2.rectangle(layer, (x1, center_y - amount), (x2, center_y + amount), color, -1)
            peak = int(self.peaks[index] * max_height)
            cv2.line(canvas, (x1, center_y - peak), (x2, center_y - peak), (255, 255, 255), 1)
            cv2.line(canvas, (x1, center_y + peak), (x2, center_y + peak), (255, 255, 255), 1)
        add_glow(canvas, layer, 5.0, self.values["glow"])
        cv2.line(canvas, (0, center_y), (width - 1, center_y), hsv_color(self.values["hue"]), 1, cv2.LINE_AA)
