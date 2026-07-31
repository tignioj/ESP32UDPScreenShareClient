import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, frequency_bands, hsv_color, polyline


class StarburstEffect(AudioEffect):
    effect_id = "starburst"
    label = "星芒脉冲"
    description = "高对比放射光刺随鼓点旋转，适合节奏强烈的电子音乐。"
    default_enabled = False
    order = 80
    parameters = (
        ParameterSpec("spokes", "光刺数量", 24, 120, 64, 8, 0),
        ParameterSpec("radius", "内圈半径", 16, 72, 35, 2, 0),
        ParameterSpec("length", "光刺长度", 10, 88, 54, 2, 0),
        ParameterSpec("rotation", "旋转速度", -2.0, 2.0, 0.22, 0.05, 2),
        ParameterSpec("smoothing", "平滑", 0.0, 0.96, 0.7, 0.04, 2),
    )

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = int(self.values["spokes"])
        bands = self.smooth("star", frequency_bands(frame, count), self.values["smoothing"])
        angles = np.linspace(0, np.pi * 2, count, endpoint=False) + frame.time * self.values["rotation"]
        center = np.array([width / 2, height / 2])
        inner_radius = self.values["radius"] + frame.beat * 5
        lengths = 3 + np.power(bands, 1.35) * self.values["length"]
        inner = center + np.column_stack((np.cos(angles), np.sin(angles))) * inner_radius
        outer = center + np.column_stack((np.cos(angles), np.sin(angles))) * (inner_radius + lengths[:, None])
        layer = np.zeros_like(canvas)
        for index in range(count):
            color = hsv_color(112 + index * 62 / max(1, count - 1) + frame.time * 3)
            thickness = 2 if bands[index] > 0.72 else 1
            cv2.line(layer, tuple(inner[index].astype(int)), tuple(outer[index].astype(int)), color,
                     thickness, cv2.LINE_AA)
        polyline(layer, outer, (170, 90, 255), 1, True)
        add_glow(canvas, layer, 5.0, 0.82)
