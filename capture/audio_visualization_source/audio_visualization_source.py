import math
import threading
import numpy as np
from typing import Optional, List, Dict, Any
from capture.interface import SourceType, ImageSourceInterface
from capture.audio_visualization_source.audio_visualization import AudioVisualizer


class AudioVisualizationSource(ImageSourceInterface):
    EFFECT_DEFAULTS = {
        'draw_waveform': True,
        'draw_spectrum_bar': True,
        'draw_spectrum_circular1': False,
        'draw_spectrum_circular2': True,
        'draw_spectrum_circular3': False,
        'draw_neon_mirror': False,
        'draw_aurora': False,
        'draw_starburst': False,
        'draw_waterfall': False,
        'draw_particles': True,
    }
    PARAMETER_DEFAULTS = {
        'gain': 1.0,
        'spectrum_smoothing': 0.5,
        'radius_smoothing': 0.9,
        'base_radius': 60,
        'radius_expansion': 30,
        'max_particles': 200,
    }
    PARAMETER_RANGES = {
        'gain': (0.1, 4.0),
        'spectrum_smoothing': (0.0, 0.95),
        'radius_smoothing': (0.0, 0.98),
        'base_radius': (20, 100),
        'radius_expansion': (5, 100),
        'max_particles': (0, 500),
    }

    def __init__(self, source_type: SourceType, source_id: str = ""):
        super().__init__(source_type, source_id)
        self.audio_spectrum = AudioVisualizer(block_size=512,width=240,height=240)
        self._config_lock = threading.RLock()
        for name, value in self.EFFECT_DEFAULTS.items():
            setattr(self, name, value)

    def initialize(self, **kwargs) -> bool:
        initial_config = dict(self.EFFECT_DEFAULTS)
        initial_config.update(self.PARAMETER_DEFAULTS)
        initial_config.update(kwargs)
        return self.set_config(initial_config)

    def capture(self) -> Optional[np.ndarray]:
        with self._config_lock:
            effects = {name: getattr(self, name) for name in self.EFFECT_DEFAULTS}
        return self.audio_spectrum.get_frame(**effects)

    def get_info(self) -> Dict[str, Any]:
        with self._config_lock:
            config = {name: getattr(self, name) for name in self.EFFECT_DEFAULTS}
            config.update({
                'gain': self.audio_spectrum.gain,
                'spectrum_smoothing': self.audio_spectrum.smoothing_factor,
                'radius_smoothing': self.audio_spectrum.radius_smoothing,
                'base_radius': self.audio_spectrum.base_radius,
                'radius_expansion': self.audio_spectrum.max_radius_expansion,
                'max_particles': self.audio_spectrum.max_particles,
            })
        return {
            'source_id': self.source_id,
            'source_type': self.source_type.value,
            'running': self._is_running,
            'config': config,
        }

    def get_available_configs(self) -> List[Dict[str, Any]]:
        configs = [
            {'name': name, 'type': 'boolean', 'default': default}
            for name, default in self.EFFECT_DEFAULTS.items()
        ]
        configs.extend(
            {
                'name': name,
                'type': 'integer' if name in {'base_radius', 'radius_expansion', 'max_particles'} else 'float',
                'min': self.PARAMETER_RANGES[name][0],
                'max': self.PARAMETER_RANGES[name][1],
                'default': default,
            }
            for name, default in self.PARAMETER_DEFAULTS.items()
        )
        return configs

    def set_config(self, config: Dict[str, Any]) -> bool:
        try:
            updates = {}
            for name in self.EFFECT_DEFAULTS:
                if name in config:
                    updates[name] = bool(config[name])

            for name, (minimum, maximum) in self.PARAMETER_RANGES.items():
                if name not in config:
                    continue
                value = float(config[name])
                if not math.isfinite(value) or not minimum <= value <= maximum:
                    return False
                if name in {'base_radius', 'radius_expansion', 'max_particles'}:
                    value = int(round(value))
                updates[name] = value
        except (TypeError, ValueError):
            return False

        with self._config_lock:
            for name in self.EFFECT_DEFAULTS:
                if name in updates:
                    setattr(self, name, updates[name])

            visualizer_attrs = {
                'gain': 'gain',
                'spectrum_smoothing': 'smoothing_factor',
                'radius_smoothing': 'radius_smoothing',
                'base_radius': 'base_radius',
                'radius_expansion': 'max_radius_expansion',
                'max_particles': 'max_particles',
            }
            for name, attr_name in visualizer_attrs.items():
                if name in updates:
                    setattr(self.audio_spectrum, attr_name, updates[name])

            minimum_radius = self.audio_spectrum.base_radius
            maximum_radius = minimum_radius + self.audio_spectrum.max_radius_expansion
            self.audio_spectrum.current_radius = max(
                minimum_radius,
                min(self.audio_spectrum.current_radius, maximum_radius)
            )
            if 'max_particles' in updates:
                if updates['max_particles'] == 0:
                    self.audio_spectrum.particles.clear()
                else:
                    self.audio_spectrum.particles = self.audio_spectrum.particles[-updates['max_particles']:]
        return True

    def release(self):
        self.audio_spectrum.release()
