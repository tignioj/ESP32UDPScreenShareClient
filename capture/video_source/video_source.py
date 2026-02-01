from typing import Optional, List, Dict, Any

import numpy
import numpy as np

from capture.interface import ImageSourceInterface, SourceType


class VideoFileSource(ImageSourceInterface):
    def __init__(self, source_type: SourceType, source_id: str = ""):
        super().__init__(source_type, source_id)
        pass

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

    def initialize(self, **kwargs) -> bool: return True
    def get_image(self) -> np.ndarray: pass
    def get_info(self) -> dict: pass
    def release(self, **kwargs) -> bool: pass
    def set_config(self, **kwargs) -> bool: pass
    def get_available_configs(self) -> List[Dict[str, Any]]:pass