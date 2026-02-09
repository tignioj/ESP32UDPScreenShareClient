import os
import random
import time
import numpy as np
from typing import Optional, List, Dict, Any
from capture.interface import SourceType, ImageSourceInterface
from capture.audio_visualization_source.audio_visualization import AudioVisualizer
class AudioVisualizationSource(ImageSourceInterface):
    def __init__(self, source_type: SourceType, source_id: str = ""):
        super().__init__(source_type, source_id)
        self.audio_spectrum = AudioVisualizer(block_size=512,width=240,height=240)
        self.draw_waveform = True
        self.draw_spectrum_bar = True
        self.draw_spectrum_circular1 = False
        self.draw_spectrum_circular2 = True
        self.draw_spectrum_circular3 = False
        self.draw_particles = True

    def initialize(self, **kwargs) -> bool:
        self.draw_waveform = kwargs.get('draw_waveform', True)
        self.draw_spectrum_bar = kwargs.get('draw_spectrum_bar', True)
        self.draw_spectrum_circular1 = kwargs.get('draw_spectrum_circular1', False)
        self.draw_spectrum_circular2 = kwargs.get('draw_spectrum_circular2', True)
        self.draw_spectrum_circular3 = kwargs.get('draw_spectrum_circular3', False)
        self.draw_particles = kwargs.get('draw_particles', True)

        return True

    def capture(self) -> Optional[np.ndarray]:
        return self.audio_spectrum.get_frame(
            draw_waveform=self.draw_waveform,
            draw_spectrum_bar=self.draw_spectrum_bar,
            draw_spectrum_circular1=self.draw_spectrum_circular1,
            draw_spectrum_circular2=self.draw_spectrum_circular2,
            draw_spectrum_circular3=self.draw_spectrum_circular3,
            draw_particles=self.draw_particles
        )


    def get_info(self) -> Dict[str, Any]:pass
    def get_available_configs(self) -> List[Dict[str, Any]]: pass

    def set_config(self, config: Dict[str, Any]) -> bool: pass
    def release(self): pass