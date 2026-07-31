import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, hsv_color


class PulseTunnelEffect(AudioEffect):
    effect_id = "pulse_tunnel"
    label = "脉冲隧道"
    description = "同心光圈随低频向外推进，营造纵深和呼吸感。"
    default_enabled = False
    order = 50
    parameters = (
        ParameterSpec("rings", "光圈数量", 3, 10, 6, 1, 0),
        ParameterSpec("spacing", "光圈间距", 7, 24, 13, 1, 0),
        ParameterSpec("pulse", "脉冲强度", 2, 28, 13, 1, 0),
        ParameterSpec("speed", "推进速度", 0.0, 2.0, 0.65, 0.05, 2),
        ParameterSpec("thickness", "线宽", 1, 5, 2, 1, 0),
    )

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = int(self.values["rings"])
        spacing = self.values["spacing"]
        travel = (frame.time * self.values["speed"] * spacing) % spacing
        pulse = frame.bass * self.values["pulse"]
        layer = np.zeros_like(canvas)
        limit = min(width, height) * 0.56
        for index in range(count):
            radius = 12 + index * spacing + travel + pulse * (1 - index / max(1, count))
            if radius > limit:
                continue
            brightness = int(255 * (1.0 - 0.68 * index / max(1, count - 1)))
            color = hsv_color(112 + index * 9 + frame.time * 3, 210, brightness)
            cv2.circle(layer, (width // 2, height // 2), int(radius), color,
                       int(self.values["thickness"]), cv2.LINE_AA)
        add_glow(canvas, layer, 7.0, 0.78)
