import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, frequency_bands, hsv_color, polyline


class ChromaRingEffect(AudioEffect):
    effect_id = "chroma_ring"
    label = "棱镜光环"
    description = "内外双向生长的彩色光环，强调鼓点并保留频率细节。"
    default_enabled = False
    order = 40
    parameters = (
        ParameterSpec("radius", "环半径", 28, 86, 54, 2, 0),
        ParameterSpec("length", "光刺长度", 6, 58, 29, 2, 0),
        ParameterSpec("thickness", "线宽", 1, 5, 2, 1, 0),
        ParameterSpec("smoothing", "平滑", 0.0, 0.96, 0.68, 0.04, 2),
        ParameterSpec("hue", "色相", 0, 179, 118, 5, 0),
    )

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = 80
        bands = self.smooth("ring", frequency_bands(frame, count), self.values["smoothing"])
        angles = np.linspace(-np.pi / 2, np.pi * 1.5, count, endpoint=False)
        center_x, center_y = width / 2, height / 2
        base = self.values["radius"] + frame.beat * 6
        length = self.values["length"]
        outer_radius = base + bands * length
        inner_radius = np.maximum(8, base - bands * length * 0.34)
        outer = np.column_stack((center_x + np.cos(angles) * outer_radius,
                                 center_y + np.sin(angles) * outer_radius))
        inner = np.column_stack((center_x + np.cos(angles) * inner_radius,
                                 center_y + np.sin(angles) * inner_radius))
        layer = np.zeros_like(canvas)
        thickness = int(self.values["thickness"])
        polyline(layer, outer, hsv_color(self.values["hue"] + frame.time * 5), thickness, True)
        polyline(layer, inner, hsv_color(self.values["hue"] + 58 + frame.time * 5), thickness, True)
        for index in range(0, count, 4):
            color = hsv_color(self.values["hue"] + index * 1.3)
            cv2.line(layer, tuple(inner[index].astype(int)), tuple(outer[index].astype(int)), color, 1, cv2.LINE_AA)
        add_glow(canvas, layer, 5.5, 0.9)
