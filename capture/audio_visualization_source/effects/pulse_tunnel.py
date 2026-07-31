import math

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
        ParameterSpec("smoothing", "脉冲平滑", 0.0, 0.95, 0.78, 0.05, 2),
        ParameterSpec("speed", "推进速度", 0.0, 2.0, 0.65, 0.05, 2),
        ParameterSpec("thickness", "线宽", 1, 5, 2, 1, 0),
    )

    def __init__(self) -> None:
        super().__init__()
        self._smoothed_bass = 0.0

    def reset(self) -> None:
        super().reset()
        self._smoothed_bass = 0.0

    def _smooth_bass(self, bass: float, dt: float) -> float:
        """Apply a time-based attack/release envelope to avoid block-to-block jumps."""
        smoothing = float(self.values["smoothing"])
        if smoothing <= 0.0:
            self._smoothed_bass = float(bass)
            return self._smoothed_bass

        attack_time = 0.02 + smoothing * 0.13
        release_time = 0.04 + smoothing * 0.34
        time_constant = attack_time if bass >= self._smoothed_bass else release_time
        blend = 1.0 - math.exp(-max(0.0, dt) / time_constant)
        self._smoothed_bass += (float(bass) - self._smoothed_bass) * blend
        return self._smoothed_bass

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = int(self.values["rings"])
        spacing = self.values["spacing"]
        phase = (frame.time * self.values["speed"]) % 1.0
        pulse = self._smooth_bass(frame.bass, dt) * self.values["pulse"]
        layer = np.zeros_like(canvas)
        limit = min(width, height) * 0.56
        coordinate_shift = 4
        coordinate_scale = 1 << coordinate_shift
        center = (width // 2 * coordinate_scale, height // 2 * coordinate_scale)
        # Include one ring beyond either end of the queue. At a phase wrap the
        # visible radii are therefore identical; only zero-opacity boundary
        # rings exchange slots instead of the whole tunnel snapping inward.
        for slot in range(-1, count + 1):
            position = slot + phase
            if position < 0.0 or position > count:
                continue
            depth = position / max(1, count)
            radius = 12 + position * spacing + pulse * (1.0 - depth)
            if radius > limit:
                continue
            edge_fade = min(1.0, position, count - position)
            canvas_fade = min(1.0, max(0.0, (limit - radius) / max(1.0, spacing)))
            opacity = max(0.0, edge_fade) * canvas_fade
            brightness = int(255 * (1.0 - 0.68 * depth) * opacity)
            if brightness <= 0:
                continue
            color = hsv_color(112 + position * 9 + frame.time * 3, 210, brightness)
            cv2.circle(layer, center, int(round(radius * coordinate_scale)), color,
                       int(self.values["thickness"]), cv2.LINE_AA, coordinate_shift)
        add_glow(canvas, layer, 7.0, 0.78)
