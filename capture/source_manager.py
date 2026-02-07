from typing import Optional, List, Dict, Any

import numpy as np

from capture.demo_source.demo_source import DemoSource
from capture.camera_source.camera_source import CameraSource
from capture.rtsp_source.rtsp_source import RTSPSource
from capture.interface import SourceType, ImageSourceInterface
from capture.screen_source.screen_capture_source import ScreenCaptureSource
from capture.video_source.video_source import VideoFileSource


class SourceManager:
    """图像源管理器"""

    def __init__(self):
        self._sources = {}  # source_id -> ImageSourceInterface
        self._active_source_id = None

    def create_source(self, source_type: SourceType,
                      source_id: str = "", **kwargs) -> Optional[str]:
        """创建图像源"""

        if source_id and source_id in self._sources:
            print(f"Source {source_id} already exists")
            return None

        # 根据类型创建对应的源
        if source_type == SourceType.DEMO:
            source = DemoSource(source_type,source_id)
        elif source_type == SourceType.SCREEN:
            display_idx = kwargs.get('display_idx', 0)
            source = ScreenCaptureSource(source_id, display_idx)
        elif source_type == SourceType.CAMERA:
            camera_idx = kwargs.get('camera_idx', 0)
            source = CameraSource(source_id, camera_idx)
        elif source_type == SourceType.RTSP:
            rtsp_url = kwargs.get('rtsp_url')
            source = RTSPSource(rtsp_url=rtsp_url,source_id=source_id)
        elif source_type == SourceType.VIDEO_FILE:
            source = VideoFileSource(source_type=source_type,source_id=source_id)

        else:
            raise ValueError(f"Unsupported source type: {source_type}")

        # 初始化
        if not source.initialize(**kwargs):
            print(f"警告：配置源初始化失败：{source_id}")
            return None

        # 生成ID（如果未提供）
        if not source_id:
            source_id = f"{source_type.value}_{len(self._sources)}"
            source.source_id = source_id

        # 添加到管理器
        self._sources[source_id] = source

        # 如果没有活动源，设为第一个源
        if self._active_source_id is None:
            self._active_source_id = source_id

        return source_id

    def get_source(self, source_id: str = None) -> Optional[ImageSourceInterface]:
        """获取图像源"""
        if source_id is None:
            source_id = self._active_source_id

        return self._sources.get(source_id)

    def switch_source(self, source_id: str) -> bool:
        """切换活动图像源"""
        if source_id not in self._sources:
            return False

        # 停止当前源
        current = self.get_source()
        if current:
            current.stop()

        # 启动新源
        self._active_source_id = source_id
        new_source = self._sources[source_id]
        new_source.start()

        return True

    def list_sources(self) -> List[Dict[str, Any]]:
        """列出所有可用的图像源"""
        sources_info = []

        # 列出屏幕源
        for i in range(3):  # 假设最多3个显示器
            sources_info.append({
                'type': SourceType.SCREEN,
                'id': f'screen_{i}',
                'name': f'显示器 {i + 1}',
                'available': True  # 需要实际检测
            })

        # 列出摄像头
        try:
            import cv2
            for i in range(10):  # 检查前10个摄像头
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    sources_info.append({
                        'type': SourceType.CAMERA,
                        'id': f'camera_{i}',
                        'name': f'摄像头 {i}',
                        'available': True
                    })
                    cap.release()
        except ImportError:
            pass

        return sources_info

    def capture_frame(self, source_id: str = None) -> Optional[np.ndarray]:
        """从指定源捕获一帧"""
        source = self.get_source(source_id)
        if not source:
            return None

        return source.capture()

    def cleanup(self):
        """清理所有资源"""
        for source_id, source in self._sources.items():
            try:
                source.release()
            except Exception as e:
                print(f"Error releasing source {source_id}: {e}")

        self._sources.clear()
        self._active_source_id = None