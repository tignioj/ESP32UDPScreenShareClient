import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, frequency_bands, hsv_color, polyline


class AuroraEffect(AudioEffect):
    effect_id = "aurora"
    label = "极光丝幕"
    description = "多层半透明频谱丝幕缓慢漂移，适合氛围音乐和纯音乐。"
    default_enabled = False
    order = 70
    parameters = (
        ParameterSpec("layers", "丝幕层数", 2, 6, 4, 1, 0),
        ParameterSpec("height", "起伏高度", 0.18, 0.75, 0.48, 0.03, 2),
        ParameterSpec("flow", "漂移速度", 0.0, 1.5, 0.32, 0.05, 2),
        ParameterSpec("smoothing", "平滑", 0.0, 0.97, 0.86, 0.03, 2),
        ParameterSpec("glow", "雾化辉光", 0.0, 1.5, 0.82, 0.05, 2),
    )

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = 72
        bands = self.smooth("aurora", frequency_bands(frame, count), self.values["smoothing"])
        bands = cv2.GaussianBlur(bands.reshape(1, -1), (11, 1), 0).ravel()
        x = np.linspace(0, width - 1, count).astype(np.int32)
        baseline = int(height * 0.84)
        layer = np.zeros_like(canvas)
        layers = int(self.values["layers"])
        for index in range(layers):
            shift = int(frame.time * self.values["flow"] * (4 + index * 2)) + index * 9
            values = np.roll(bands, shift % count)
            scale = height * self.values["height"] * (0.62 + 0.38 * index / max(1, layers - 1))
            ridge_y = baseline - index * 7 - (values * scale).astype(np.int32)
            ridge = np.column_stack((x, ridge_y))
            color = hsv_color(76 + index * 17 + frame.time * 2, 205, 230)
            fill = np.vstack((ridge, (width - 1, baseline), (0, baseline))).astype(np.int32)
            veil = np.zeros_like(canvas)
            cv2.fillPoly(veil, [fill], color)
            cv2.addWeighted(layer, 1.0, veil, 0.10 + index * 0.025, 0, dst=layer)
            polyline(layer, ridge, color, 2)
        add_glow(canvas, layer, 8.0, self.values["glow"])
