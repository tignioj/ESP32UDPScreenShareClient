import os
import random
import time
import numpy as np
from typing import Optional, List, Dict, Any
from capture.interface import SourceType, ImageSourceInterface

class DemoSource(ImageSourceInterface):
    def __init__(self, source_type: SourceType, source_id: str = ""):
        super().__init__(source_type, source_id)

    def initialize(self, **kwargs) -> bool:
        return True

    def capture(self) -> Optional[np.ndarray]:
        height, width = 240, 240
        image = np.zeros((height, width, 3), dtype=np.uint8)
        # 将宽度分为7段，创建彩虹色
        segment_width = width // 7
        colors = [
            [255, 0, 0],  # 红色
            [255, 165, 0],  # 橙色
            [255, 255, 0],  # 黄色
            [0, 255, 0],  # 绿色
            [0, 255, 255],  # 青色
            [0, 0, 255],  # 蓝色
            [128, 0, 128]  # 紫色
        ]
        for i in range(7):
            start_x = i * segment_width
            end_x = (i + 1) * segment_width if i < 6 else width
            image[:, start_x:end_x] = colors[i]
        return image

    def get_info(self) -> Dict[str, Any]:pass
    def get_available_configs(self) -> List[Dict[str, Any]]: pass

    def set_config(self, config: Dict[str, Any]) -> bool: pass
    def release(self): pass