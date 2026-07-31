from dataclasses import dataclass

import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, hsv_color


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    hue: float


class ParticlesEffect(AudioEffect):
    effect_id = "particles"
    label = "萤火粒子"
    description = "由低频触发的轻盈发光粒子，可单独使用，也适合作为其他效果的前景层。"
    default_enabled = False
    order = 100
    parameters = (
        ParameterSpec("count", "最大粒子数", 0, 320, 120, 10, 0),
        ParameterSpec("spawn", "生成密度", 0.0, 2.0, 0.8, 0.05, 2),
        ParameterSpec("speed", "上升速度", 0.2, 2.5, 1.0, 0.05, 2),
        ParameterSpec("size", "粒子大小", 1.0, 7.0, 3.2, 0.2, 1),
        ParameterSpec("drift", "横向漂移", 0.0, 2.0, 0.65, 0.05, 2),
    )

    def __init__(self) -> None:
        super().__init__()
        self.items: list[Particle] = []
        self.rng = np.random.default_rng()

    def reset(self) -> None:
        super().reset()
        self.items.clear()

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        maximum = int(self.values["count"])
        if maximum <= 0:
            self.items.clear()
            return
        activity = min(1.0, frame.rms * 16.0 + frame.beat * 0.8)
        spawn_count = int((1 + activity * 8) * self.values["spawn"])
        for _ in range(min(spawn_count, maximum - len(self.items))):
            life = float(self.rng.uniform(0.7, 1.5))
            self.items.append(Particle(
                x=float(self.rng.uniform(4, max(5, width - 4))),
                y=float(height + self.rng.uniform(0, 10)),
                vx=float(self.rng.normal(0, 13 * self.values["drift"])),
                vy=float(self.rng.uniform(-70, -34) * self.values["speed"]),
                life=life,
                max_life=life,
                size=float(self.rng.uniform(0.55, 1.25) * self.values["size"]),
                hue=float(self.rng.uniform(88, 166)),
            ))

        layer = np.zeros_like(canvas)
        alive = []
        step = min(0.08, max(0.001, dt))
        for item in self.items:
            item.vx += np.sin(frame.time * 1.7 + item.y * 0.04) * self.values["drift"] * step * 7
            item.x += item.vx * step
            item.y += item.vy * step
            item.life -= step
            if item.life <= 0 or item.y < -10 or item.x < -10 or item.x > width + 10:
                continue
            alive.append(item)
            alpha = item.life / item.max_life
            radius = max(1, int(item.size * (0.45 + alpha * 0.55)))
            cv2.circle(layer, (int(item.x), int(item.y)), radius,
                       hsv_color(item.hue + frame.time * 4, 180, int(255 * alpha)), -1, cv2.LINE_AA)
        self.items = alive[-maximum:]
        add_glow(canvas, layer, 4.5, 0.82)
