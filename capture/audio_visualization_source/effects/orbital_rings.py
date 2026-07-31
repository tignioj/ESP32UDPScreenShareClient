import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, frequency_bands, hsv_color, polyline


class OrbitalRingsEffect(AudioEffect):
    effect_id = "orbital_rings"
    label = "轨道脉冲"
    description = "三条不同相位的频谱轨道围绕中心旋转，节奏清晰但画面稳定。"
    default_enabled = False
    order = 30
    parameters = (
        ParameterSpec("radius", "基础半径", 28, 88, 50, 2, 0),
        ParameterSpec("spread", "轨道间距", 3, 20, 9, 1, 0),
        ParameterSpec("response", "频谱形变", 4, 42, 21, 1, 0),
        ParameterSpec("rotation", "旋转速度", -1.5, 1.5, 0.18, 0.05, 2),
        ParameterSpec("smoothing", "平滑", 0.0, 0.96, 0.72, 0.04, 2),
    )

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = 96
        bands = self.smooth("rings", frequency_bands(frame, count), self.values["smoothing"])
        center = np.array([width / 2, height / 2], dtype=np.float32)
        angles = np.linspace(0, np.pi * 2, count, endpoint=False)
        phase = frame.time * self.values["rotation"]
        layer = np.zeros_like(canvas)
        for ring in range(3):
            shifted = np.roll(bands, ring * 11)
            radius = self.values["radius"] + (ring - 1) * self.values["spread"]
            radius = radius + shifted * self.values["response"] * (0.72 + ring * 0.14)
            ring_angles = angles + phase * (1 if ring != 1 else -0.72)
            points = np.column_stack((
                center[0] + np.cos(ring_angles) * radius,
                center[1] + np.sin(ring_angles) * radius,
            ))
            polyline(layer, points, hsv_color(88 + ring * 28 + frame.time * 4), 2, True)
        add_glow(canvas, layer, 5.0, 0.78)
        cv2.circle(canvas, tuple(center.astype(int)), 3 + int(frame.beat * 5), (255, 255, 255), -1, cv2.LINE_AA)
