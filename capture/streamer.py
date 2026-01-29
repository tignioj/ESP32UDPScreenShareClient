from typing import Dict, Any, Optional, List

import numpy as np

from capture.interface import SourceType
from capture.source_manager import SourceManager


class Streamer:
    """推流程序"""

    def __init__(self, config: Dict[str, Any] = None):
        self.source_manager = SourceManager()
        self.config = config or {}
        self._initialized = False

    def initialize(self) -> bool:
        """初始化推流程序"""
        # 从配置创建图像源
        source_configs = self.config.get('sources', [])

        for src_config in source_configs:
            src_type = SourceType(src_config.get('type', 'screen'))
            src_id = src_config.get('id', '')

            self.source_manager.create_source(
                source_type=src_type,
                source_id=src_id,
                **src_config.get('params', {})
            )

        # 设置活动源
        active_source = self.config.get('active_source')
        if active_source:
            switch_ok = self.source_manager.switch_source(active_source)
            if not switch_ok: raise Exception(f'配置源不存在，请检查配置文件的active_source: {active_source}')

        self._initialized = True
        return True

    def get_frame(self) -> Optional[np.ndarray]:
        """
        获取帧的接口，供推流程序调用

        这是向后兼容的接口，实际调用当前活动源
        """
        if not self._initialized:
            return None

        return self.source_manager.capture_frame()

    def switch_source(self, source_id: str) -> bool:
        """切换图像源"""
        return self.source_manager.switch_source(source_id)

    def list_available_sources(self) -> List[Dict[str, Any]]:
        """列出可用图像源"""
        return self.source_manager.list_sources()

    def get_source_info(self, source_id: str = None) -> Dict[str, Any]:
        """获取当前源信息"""
        source = self.source_manager.get_source(source_id)
        if source:
            return source.get_info()
        return {}

    def set_source_config(self, config: Dict[str, Any], source_id: str = None) -> bool:
        """设置图像源配置"""
        source = self.source_manager.get_source(source_id)
        if source:
            return source.set_config(config)
        return False

    def close(self):
        """关闭推流程序"""
        self.source_manager.cleanup()
        self._initialized = False

