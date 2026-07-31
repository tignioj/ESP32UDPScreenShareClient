import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import frequency_bands


class WaterfallEffect(AudioEffect):
    effect_id = "waterfall"
    label = "流光瀑布"
    description = "完整保留时间轴的滚动声谱图，颜色同时表达频率与能量。"
    default_enabled = False
    order = 90
    parameters = (
        ParameterSpec("bands", "频率分辨率", 32, 96, 64, 8, 0),
        ParameterSpec("speed", "滚动速度", 1, 5, 2, 1, 0),
        ParameterSpec("brightness", "亮度", 0.4, 2.0, 1.15, 0.05, 2),
        ParameterSpec("smoothing", "频谱平滑", 0.0, 0.95, 0.62, 0.05, 2),
        ParameterSpec("blend", "叠加浓度", 0.2, 1.0, 0.76, 0.05, 2),
    )

    def __init__(self) -> None:
        super().__init__()
        self.history = np.zeros((1, 1), dtype=np.float32)

    def reset(self) -> None:
        super().reset()
        self.history = np.zeros((1, 1), dtype=np.float32)

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = int(self.values["bands"])
        if self.history.shape != (height, count):
            self.history = np.zeros((height, count), dtype=np.float32)
        bands = self.smooth("waterfall", frequency_bands(frame, count), self.values["smoothing"])
        speed = int(self.values["speed"])
        self.history[:-speed] = self.history[speed:]
        self.history[-speed:] = bands
        intensity = np.clip(self.history * self.values["brightness"], 0.0, 1.0)
        hue = np.clip(150 - intensity * 125, 0, 179).astype(np.uint8)
        saturation = np.full_like(hue, 245)
        value = (np.power(intensity, 0.72) * 255).astype(np.uint8)
        hsv = np.dstack((hue, saturation, value))
        colored = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        colored = cv2.resize(colored, (width, height), interpolation=cv2.INTER_LINEAR)
        cv2.addWeighted(canvas, 1.0 - self.values["blend"] * 0.55, colored,
                        self.values["blend"], 0, dst=canvas)
