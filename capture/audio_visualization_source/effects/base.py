from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

import numpy as np


@dataclass(frozen=True)
class ParameterSpec:
    """UI and validation metadata owned by one effect module."""

    key: str
    label: str
    minimum: float
    maximum: float
    default: float
    step: float
    digits: int = 2
    help: str = ""

    @property
    def value_type(self) -> str:
        return "integer" if self.digits == 0 else "float"

    def clamp(self, value: Any) -> int | float:
        number = float(value)
        if not np.isfinite(number):
            raise ValueError(f"{self.key} must be finite")
        number = min(self.maximum, max(self.minimum, number))
        number = round(number / self.step) * self.step
        return int(round(number)) if self.digits == 0 else round(number, self.digits)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.key,
            "label": self.label,
            "type": self.value_type,
            "min": self.minimum,
            "max": self.maximum,
            "default": self.default,
            "step": self.step,
            "digits": self.digits,
            "help": self.help,
        }


@dataclass(frozen=True)
class AudioFrame:
    waveform: np.ndarray
    spectrum: np.ndarray
    sample_rate: int
    block_size: int
    rms: float
    bass: float
    beat: float
    time: float


class AudioEffect:
    """Small stateful renderer. Every concrete effect owns its parameters."""

    effect_id = "base"
    label = "Base"
    description = ""
    default_enabled = False
    order = 0
    parameters: tuple[ParameterSpec, ...] = ()

    def __init__(self) -> None:
        self.enabled = self.default_enabled
        self.values = {item.key: item.default for item in self.parameters}
        self._smooth_state: Dict[str, np.ndarray] = {}

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return {
            "id": cls.effect_id,
            "label": cls.label,
            "description": cls.description,
            "default_enabled": cls.default_enabled,
            "order": cls.order,
            "parameters": [item.as_dict() for item in cls.parameters],
        }

    def configure(self, params: Dict[str, Any]) -> None:
        specs = {item.key: item for item in self.parameters}
        unknown = set(params) - set(specs)
        if unknown:
            raise ValueError(f"Unknown {self.effect_id} parameter(s): {', '.join(sorted(unknown))}")
        for key, value in params.items():
            self.values[key] = specs[key].clamp(value)

    def reset(self) -> None:
        self.values = {item.key: item.default for item in self.parameters}
        self._smooth_state.clear()

    def smooth(self, key: str, values: np.ndarray, amount: float) -> np.ndarray:
        values = np.asarray(values, dtype=np.float32)
        previous = self._smooth_state.get(key)
        if previous is None or previous.shape != values.shape:
            previous = np.zeros_like(values)
        decay = float(np.clip(amount, 0.0, 0.98))
        result = np.where(
            values >= previous,
            previous * min(0.35, decay) + values * (1.0 - min(0.35, decay)),
            previous * decay + values * (1.0 - decay),
        )
        self._smooth_state[key] = result
        return result

    def draw(self, canvas: np.ndarray, frame: AudioFrame, dt: float) -> None:
        raise NotImplementedError


def metadata_for(effect_types: Iterable[type[AudioEffect]]) -> list[Dict[str, Any]]:
    return [effect_type.metadata() for effect_type in sorted(effect_types, key=lambda item: item.order)]
