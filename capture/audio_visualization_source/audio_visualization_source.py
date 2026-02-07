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

    def initialize(self, **kwargs) -> bool:
        return True

    def capture(self) -> Optional[np.ndarray]:
        return self.audio_spectrum.get_frame()


    def get_info(self) -> Dict[str, Any]:pass
    def get_available_configs(self) -> List[Dict[str, Any]]: pass

    def set_config(self, config: Dict[str, Any]) -> bool: pass
    def release(self): pass