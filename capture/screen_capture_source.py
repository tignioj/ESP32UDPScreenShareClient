from typing import Optional, Dict, Any, List

import numpy as np

from capture.interface import ImageSourceInterface, SourceType


class ScreenCaptureSource(ImageSourceInterface):
    """屏幕截图源"""

    def __init__(self, source_id: str = "", display_idx: int = 0):
        super().__init__(SourceType.SCREEN, source_id or f"screen_{display_idx}")
        self.display_idx = display_idx
        self._impl = None  # 平台特定实现

    def initialize(self, **kwargs) -> bool:
        """初始化屏幕截图源"""
        import platform

        system = platform.system()

        # 根据平台选择实现
        if system == "Windows":
            from .screenshot_win import WindowsScreenCapture
            self._impl = WindowsScreenCapture(self.display_idx)
        elif system == "Darwin":
            from .screenshot_mac import MacScreenCapture
            self._impl = MacScreenCapture(self.display_idx)
        elif system == "Linux":
            from .screenshot_linux import LinuxScreenCapture
            self._impl = LinuxScreenCapture(self.display_idx)
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

        # 应用配置
        return self._impl.initialize(**kwargs)

    def capture(self) -> Optional[np.ndarray]:
        if not self._is_running or not self._impl:
            return None

        try:
            return self._impl.capture()
        except Exception as e:
            print(f"Screen capture failed: {e}")
            return None

    def get_info(self) -> Dict[str, Any]:
        if not self._impl:
            return {}

        info = self._impl.get_display_info()
        info.update({
            'source_type': self.source_type.value,
            'source_id': self.source_id,
            'fps': self._fps,
        })
        return info

    def get_available_configs(self) -> List[Dict[str, Any]]:
        if not self._impl:
            return []

        configs = [
            {
                'name': 'region',
                'type': 'tuple',
                'description': '截图区域 (x, y, width, height)',
                'default': None,
                'range': '任意有效区域'
            },
            {
                'name': 'display_idx',
                'type': 'int',
                'description': '显示器索引',
                'default': 0,
                'range': f'0-{len(self._impl.list_displays()) - 1}'
            }
        ]

        return configs

    def set_config(self, config: Dict[str, Any]) -> bool:
        pass
        # if 'region' in config:
        #     self._region = config['region']
        #     return True
        # return False

    def release(self):
        if self._impl:
            self._impl.release()