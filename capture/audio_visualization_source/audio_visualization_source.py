from __future__ import annotations

import copy
import threading
from typing import Any, Dict, List, Optional

import numpy as np

from capture.interface import ImageSourceInterface, SourceType
from capture.audio_visualization_source.audio_visualization import AudioVisualizer


class AudioVisualizationSource(ImageSourceInterface):
    """Runtime source exposing the visualizer's namespaced configuration."""

    LEGACY_EFFECTS = {
        "draw_waveform": "waveform",
        "draw_spectrum_bar": "spectrum_bars",
        "draw_spectrum_circular1": "orbital_rings",
        "draw_spectrum_circular2": "ionized_ring",
        "draw_spectrum_circular3": "pulse_tunnel",
        "draw_neon_mirror": "mirror_bars",
        "draw_aurora": "aurora",
        "draw_starburst": "starburst",
        "draw_waterfall": "waterfall",
        "draw_particles": "particles",
    }
    LEGACY_INPUTS = {"gain": "gain"}
    VISUALIZER_OPTIONS = {
        "width", "height", "sample_rate", "block_size", "channels", "target_device"
    }

    def __init__(self, source_type: SourceType, source_id: str = ""):
        super().__init__(source_type, source_id)
        self.visualizer: Optional[AudioVisualizer] = None
        self._config_lock = threading.RLock()

    def initialize(self, **kwargs) -> bool:
        if "fps" in kwargs:
            self.fps = kwargs["fps"]
        options = {
            "width": 240,
            "height": 240,
            "sample_rate": 48000,
            "block_size": 1024,
            "channels": 2,
            # An empty device means the operating system's default recording
            # input. This works on macOS out of the box and remains compatible
            # with Windows users who configure CABLE Output explicitly.
            "target_device": "",
        }
        options.update({key: kwargs[key] for key in self.VISUALIZER_OPTIONS if key in kwargs})
        try:
            self.visualizer = AudioVisualizer(**options)
            config = self._translate_config(kwargs)
            if config:
                self.visualizer.configure(config)
            active_preset = self._get_active_preset_config(kwargs)
            if active_preset:
                self.visualizer.configure(self._translate_config(active_preset))
            return True
        except Exception as exc:
            if self.visualizer is not None:
                self.visualizer.release()
                self.visualizer = None
            print(f"音频可视化初始化失败: {exc}")
            return False

    @staticmethod
    def _get_active_preset_config(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Resolve a valid saved selection without letting stale YAML break startup."""
        name = config.get("active_preset")
        presets = config.get("presets")
        if not isinstance(name, str) or not isinstance(presets, dict):
            return None
        preset = presets.get(name)
        return copy.deepcopy(preset) if isinstance(preset, dict) else None

    def capture(self) -> Optional[np.ndarray]:
        with self._config_lock:
            return self.visualizer.get_frame() if self.visualizer is not None else None

    def get_info(self) -> Dict[str, Any]:
        with self._config_lock:
            config = self.visualizer.get_config() if self.visualizer is not None else {}
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "fps": self.fps,
            "running": self._is_running,
            "config": config,
            "audio_ui": {
                "input_parameters": AudioVisualizer.input_catalog(),
                "effects": AudioVisualizer.effect_catalog(),
                "devices": AudioVisualizer.input_devices(),
            },
        }

    def get_available_configs(self) -> List[Dict[str, Any]]:
        return [
            {"name": "input", "type": "group", "parameters": AudioVisualizer.input_catalog()},
            {"name": "effects", "type": "effects", "items": AudioVisualizer.effect_catalog()},
        ]

    def _translate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Accept the new schema and migrate pre-refactor flat keys in memory."""
        translated: Dict[str, Any] = {}
        if isinstance(config.get("input"), dict):
            translated["input"] = dict(config["input"])
        if isinstance(config.get("effects"), dict):
            translated["effects"] = {
                effect_id: dict(effect_config)
                for effect_id, effect_config in config["effects"].items()
                if isinstance(effect_config, dict)
            }

        input_config = translated.setdefault("input", {})
        effects_config = translated.setdefault("effects", {})
        for old_key, new_key in self.LEGACY_INPUTS.items():
            if old_key in config and new_key not in input_config:
                input_config[new_key] = config[old_key]
        for old_key, effect_id in self.LEGACY_EFFECTS.items():
            if old_key in config:
                effects_config.setdefault(effect_id, {}).setdefault("enabled", bool(config[old_key]))

        smoothing = config.get("spectrum_smoothing")
        if smoothing is not None:
            for effect_id in (
                "waveform", "spectrum_bars", "orbital_rings", "chroma_ring", "ionized_ring",
                "mirror_bars", "aurora", "starburst", "waterfall",
            ):
                effects_config.setdefault(effect_id, {}).setdefault("params", {}).setdefault(
                    "smoothing", smoothing
                )
        if "base_radius" in config:
            for effect_id in ("orbital_rings", "chroma_ring", "ionized_ring"):
                effects_config.setdefault(effect_id, {}).setdefault("params", {}).setdefault(
                    "radius", config["base_radius"]
                )
        if "radius_expansion" in config:
            effects_config.setdefault("orbital_rings", {}).setdefault("params", {}).setdefault(
                "response", config["radius_expansion"]
            )
            effects_config.setdefault("chroma_ring", {}).setdefault("params", {}).setdefault(
                "length", config["radius_expansion"]
            )
            effects_config.setdefault("ionized_ring", {}).setdefault("params", {}).setdefault(
                "separation", config["radius_expansion"]
            )
        if "radius_smoothing" in config:
            effects_config.setdefault("ionized_ring", {}).setdefault("params", {}).setdefault(
                "pulse_smoothing", config["radius_smoothing"]
            )
        if "max_particles" in config:
            effects_config.setdefault("particles", {}).setdefault("params", {}).setdefault(
                "count", config["max_particles"]
            )

        if not input_config:
            translated.pop("input", None)
        if not effects_config:
            translated.pop("effects", None)
        return translated

    def set_config(self, config: Dict[str, Any]) -> bool:
        if self.visualizer is None or not isinstance(config, dict):
            return False
        try:
            handled_fps = "fps" in config
            if handled_fps:
                self.fps = config["fps"]
            target_device = config.get("target_device")
            handled_device = target_device is not None
            if target_device is not None:
                if not isinstance(target_device, str):
                    raise ValueError("target_device 必须是字符串")
                with self._config_lock:
                    self.visualizer.select_input_device(target_device)
            translated = self._translate_config(config)
            if not translated and config and not handled_device and not handled_fps:
                return False
            with self._config_lock:
                self.visualizer.configure(translated)
            return True
        except (TypeError, ValueError):
            return False

    def release(self) -> None:
        with self._config_lock:
            if self.visualizer is not None:
                self.visualizer.release()
                self.visualizer = None
