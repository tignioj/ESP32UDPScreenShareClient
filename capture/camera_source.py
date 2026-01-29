import time
from typing import Optional, Dict, Any, List

import numpy as np

from capture.interface import ImageSourceInterface, SourceType


class CameraSource(ImageSourceInterface):
    """摄像头源"""

    def __init__(self, source_id: str = "", camera_idx: int = 0):
        super().__init__(SourceType.CAMERA, source_id or f"camera_{camera_idx}")
        self.camera_idx = camera_idx
        self._cap = None  # OpenCV VideoCapture对象
        self._resolution = (1920, 1080)
        self._last_capture_time = 0

    def initialize(self, **kwargs) -> bool:
        """初始化摄像头"""
        try:
            import cv2

            # 创建VideoCapture对象
            self._cap = cv2.VideoCapture(self.camera_idx)
            if not self._cap.isOpened():
                return False

            # 设置分辨率
            if 'resolution' in kwargs:
                width, height = kwargs['resolution']
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            # 设置其他参数
            if 'fps' in kwargs:
                self._cap.set(cv2.CAP_PROP_FPS, kwargs['fps'])
                self._fps = kwargs['fps']

            # 获取实际分辨率
            width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._resolution = (width, height)

            return True
        except ImportError:
            print("OpenCV not installed. Install with: pip install opencv-python")
            return False
        except Exception as e:
            print(f"Camera initialization failed: {e}")
            return False

    def capture(self) -> Optional[np.ndarray]:
        if not self._is_running or not self._cap:
            return None

        try:
            # 控制帧率
            current_time = time.time()
            if current_time - self._last_capture_time < 1.0 / self._fps:
                return None

            ret, frame = self._cap.read()
            self._last_capture_time = current_time

            if not ret or frame is None:
                return None

            # BGR转换为RGB
            import cv2
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return frame_rgb

        except Exception as e:
            print(f"Camera capture failed: {e}")
            return None

    def get_info(self) -> Dict[str, Any]:
        if not self._cap:
            return {}

        import cv2

        info = {
            'source_type': self.source_type.value,
            'source_id': self.source_id,
            'resolution': self._resolution,
            'fps': self._fps,
            'camera_idx': self.camera_idx,
            'brightness': self._cap.get(cv2.CAP_PROP_BRIGHTNESS),
            'contrast': self._cap.get(cv2.CAP_PROP_CONTRAST),
            'saturation': self._cap.get(cv2.CAP_PROP_SATURATION),
        }

        return info

    def get_available_configs(self) -> List[Dict[str, Any]]:
        configs = [
            {
                'name': 'resolution',
                'type': 'tuple',
                'description': '分辨率 (width, height)',
                'default': (1920, 1080),
                'range': '常见分辨率如(640,480), (1280,720), (1920,1080)'
            },
            {
                'name': 'fps',
                'type': 'float',
                'description': '帧率',
                'default': 30.0,
                'range': '1.0-60.0'
            },
            {
                'name': 'camera_idx',
                'type': 'int',
                'description': '摄像头索引',
                'default': 0,
                'range': '0-10'
            }
        ]

        return configs

    def set_config(self, config: Dict[str, Any]) -> bool:
        if not self._cap:
            return False

        import cv2

        success = True
        if 'resolution' in config:
            width, height = config['resolution']
            success &= self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            success &= self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if 'fps' in config:
            self._fps = config['fps']
            success &= self._cap.set(cv2.CAP_PROP_FPS, self._fps)

        return success

    def release(self):
        if self._cap:
            self._cap.release()
            self._cap = None