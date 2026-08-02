import sys
from typing import Dict, Any, Optional, List

import numpy as np

from capture.interface import SourceType
from capture.source_manager import SourceManager


def _console_print(message: str) -> None:
    """Print without crashing when the Windows console cannot encode Chinese."""
    stream = sys.stdout
    if stream is None:
        return

    try:
        print(message, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        escaped_message = message.encode(
            encoding,
            errors="backslashreplace",
        ).decode(encoding)
        print(escaped_message, file=stream)


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

            # 只初始化设置为True的源
            if src_config.get('enable', True):
                created_source_id = self.source_manager.create_source(
                    source_type=src_type,
                    source_id=src_id,
                    **src_config.get('params', {})
                )
                if created_source_id:
                    _console_print(f"成功加载配置源{src_id}")
                else:
                    _console_print(f"跳过不可用的配置源:{src_id}")
            else:
                _console_print(f"没有开启的的配置源:{src_id}")

        # 设置活动源
        active_source = self.config.get('active_source')
        if active_source:
            _console_print(f"正在尝试切换到指定源:{active_source}")
            switch_ok = self.source_manager.switch_source(active_source)
            if switch_ok:
                _console_print(f"成功切换到指定源:{active_source}")
            else:
                available_sources = self.source_manager.list_configured_sources()
                if not available_sources:
                    raise RuntimeError("没有任何可用的配置源，请检查 sources 配置和设备连接状态")
                fallback_source = next(
                    (source for source in available_sources if source['active']),
                    available_sources[0],
                )
                _console_print(
                    f"警告：配置源不可用:{active_source}；"
                    f"已自动使用可用源:{fallback_source['id']}"
                )

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

    def list_configured_sources(self) -> List[Dict[str, Any]]:
        """列出配置文件中已成功初始化、可切换的图像源。"""
        return self.source_manager.list_configured_sources()

    def get_source_info(self, source_id: str = None) -> Dict[str, Any]:
        """获取当前源信息"""
        return self.source_manager.get_source_info(source_id)

    def get_source_preview(self, source_id: str = None) -> Optional[np.ndarray]:
        """获取图像源最近缓存的预览画面。"""
        return self.source_manager.get_source_preview(source_id)

    def set_source_config(self, config: Dict[str, Any], source_id: str = None) -> bool:
        """设置图像源配置"""
        return self.source_manager.set_source_config(config, source_id)

    def close(self):
        """关闭推流程序"""
        self.source_manager.cleanup()
        self._initialized = False
