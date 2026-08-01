import cv2
import numpy as np

from .base import AudioEffect, AudioFrame, ParameterSpec
from .utils import add_glow, frequency_bands, polyline


class IonizedRingEffect(AudioEffect):
    """White spectrum ring with beat-driven red/blue chromatic separation."""

    effect_id = "ionized_ring"
    label = "红蓝电离"
    description = "白色频谱环随节拍呼吸，并向相反方向分离出红蓝电离残影。"
    default_enabled = False
    order = 45
    parameters = (
        ParameterSpec("radius", "环半径", 28, 86, 60, 2, 0),
        ParameterSpec("response", "频谱形变", 6, 64, 46, 2, 0),
        ParameterSpec("separation", "电离范围", 0, 32, 22, 1, 0),
        ParameterSpec("thickness", "线宽", 1, 6, 4, 1, 0),
        ParameterSpec("smoothing", "频谱平滑", 0.0, 0.96, 0.62, 0.04, 2),
        ParameterSpec("pulse_smoothing", "律动平滑", 0.0, 0.98, 0.9, 0.02, 2),
        ParameterSpec("glow", "辉光", 0.0, 1.5, 0.7, 0.05, 2),
    )

    def __init__(self) -> None:
        super().__init__()
        self.rng = np.random.default_rng()
        self._drive = 0.0

    def reset(self) -> None:
        super().reset()
        self._drive = 0.0

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        height, width = canvas.shape[:2]
        count = 100
        bands = frequency_bands(frame, count, high_hz=6000.0)
        bands = self.smooth("ionized_ring", bands, self.values["smoothing"])

        # The former implementation expanded the ring from an energy history and
        # used that expansion as the random red/blue displacement. The analyser
        # now exposes bass and beat directly, so combine both into the same drive.
        target_drive = float(np.clip(frame.beat + frame.bass * 0.35, 0.0, 1.0))
        smoothing = self.values["pulse_smoothing"]
        self._drive = self._drive * smoothing + target_drive * (1.0 - smoothing)
        drive = self._drive
        separation = drive * self.values["separation"]
        radius = self.values["radius"] + separation * 0.42

        angles = np.linspace(0.0, np.pi * 2.0, count, endpoint=False)
        radial = radius + bands * self.values["response"]
        center = np.array([width / 2.0, height / 2.0], dtype=np.float32)
        directions = np.column_stack((np.cos(angles), np.sin(angles)))
        points = center + directions * radial[:, None]

        layer = np.zeros_like(canvas)
        thickness = int(self.values["thickness"])
        if separation >= 0.5:
            offset = self.rng.uniform(-separation, separation, size=2)
            # OpenCV colors are BGR. Draw the side bands first so the white core
            # remains crisp, matching the original red-blue-white layering.
            polyline(layer, points + offset, (255, 0, 0), thickness, True)
            polyline(layer, points, (255, 255, 255), thickness, True)
            polyline(layer, points - offset, (0, 0, 255), thickness, True)
        else:
            polyline(layer, points, (255, 255, 255), thickness, True)

        glow = self.values["glow"]
        if glow > 0:
            add_glow(canvas, layer, 5.5, glow)
        else:
            cv2.add(canvas, layer, dst=canvas)
