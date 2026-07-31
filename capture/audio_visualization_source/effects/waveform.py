import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, hsv_color, polyline


class WaveformEffect(AudioEffect):
    effect_id = "waveform"
    label = "丝带波形"
    description = "双层发光丝带跟随原始波形展开，适合人声和旋律。"
    default_enabled = False
    order = 10
    parameters = (
        ParameterSpec("amplitude", "振幅", 0.25, 1.5, 0.82, 0.05, 2),
        ParameterSpec("thickness", "线宽", 1, 6, 2, 1, 0),
        ParameterSpec("smoothing", "平滑", 0.0, 0.95, 0.58, 0.05, 2),
        ParameterSpec("glow", "辉光", 0.0, 1.5, 0.85, 0.05, 2),
        ParameterSpec("hue_speed", "流光速度", 0.0, 1.5, 0.28, 0.05, 2),
    )

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        source = frame.waveform
        if source.size < 2:
            return
        indexes = np.linspace(0, source.size - 1, width).astype(np.int32)
        wave = self.smooth("wave", source[indexes], self.values["smoothing"])
        wave = np.clip(wave * self.values["amplitude"], -1.0, 1.0)
        x = np.arange(width, dtype=np.int32)
        center = height // 2
        scale = height * 0.34
        upper = np.column_stack((x, center + wave * scale)).astype(np.int32)
        lower = np.column_stack((x, center - wave * scale * 0.55)).astype(np.int32)
        hue = frame.time * self.values["hue_speed"] * 40.0
        glow = np.zeros_like(canvas)
        thickness = int(self.values["thickness"])
        polyline(glow, upper, hsv_color(hue + 92), thickness + 2)
        polyline(glow, lower, hsv_color(hue + 145), max(1, thickness))
        add_glow(canvas, glow, 5.5, self.values["glow"])
        polyline(canvas, upper, (230, 255, 255), 1)
        cv2.line(canvas, (0, center), (width - 1, center), (45, 25, 55), 1, cv2.LINE_AA)
