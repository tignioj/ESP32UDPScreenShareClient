from abc import ABC, abstractmethod
from typing import Optional, Tuple, List, Dict, Any
from enum import Enum
import numpy as np
import time


class SourceType(Enum):
    """图像源类型"""
    DEMO = "demo"  # 样本
    SCREEN = "screen"
    CAMERA = "camera"
    VIDEO_FILE = "video_file"
    IMAGE_FILE = "image_file"
    VIRTUAL = "virtual"  # 虚拟源，如测试图、合成图像
    RTSP = "rtsp"  # 新增RTSP类型
    AUDIO_VISUALIZATION = "audio_visualization"  # 音频可视化

class ImageSourceInterface(ABC):
    """图像源接口抽象基类"""

    def __init__(self, source_type: SourceType, source_id: str = ""):
        self.source_type = source_type
        self.source_id = source_id
        self._fps = 30  # 默认帧率
        self._is_running = False

    @property
    def fps(self) -> float:
        """获取当前帧率"""
        return self._fps

    @fps.setter
    def fps(self, value: float):
        """设置帧率"""
        self._fps = max(1.0, min(value, 120.0))

    @abstractmethod
    def initialize(self, **kwargs) -> bool:
        """
        初始化图像源

        Returns:
            bool: 初始化是否成功
        """
        pass

    @abstractmethod
    def capture(self) -> Optional[np.ndarray]:
        """
        捕获一帧图像

        Returns:
            RGB888格式的numpy数组，形状为 (height, width, 3)
            如果失败则返回None
        """
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """
        获取图像源信息

        Returns:
            包含分辨率、帧率等信息的字典
        """
        pass

    @abstractmethod
    def get_available_configs(self) -> List[Dict[str, Any]]:
        """
        获取可用的配置选项

        Returns:
            配置选项列表，每个选项包含参数名、类型、范围等信息
        """
        pass

    @abstractmethod
    def set_config(self, config: Dict[str, Any]) -> bool:
        """
        设置配置参数

        Args:
            config: 配置参数字典

        Returns:
            bool: 设置是否成功
        """
        pass

    @abstractmethod
    def release(self):
        """释放资源"""
        pass

    def start(self):
        """启动图像源（如果需要）"""
        self._is_running = True

    def stop(self):
        """停止图像源"""
        self._is_running = False

    def __enter__(self):
        if self.initialize():
            self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        self.release()


class ScreenshotError(Exception): pass
class CameraError(Exception): pass