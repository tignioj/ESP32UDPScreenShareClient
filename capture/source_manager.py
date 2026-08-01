import threading
from typing import Optional, List, Dict, Any

import numpy as np

from capture.demo_source.demo_source import DemoSource
from capture.camera_source.camera_source import CameraSource
from capture.rtsp_source.rtsp_source import RTSPSource
from capture.interface import SourceType, ImageSourceInterface
from capture.screen_source.screen_capture_source import ScreenCaptureSource
from capture.video_source.video_source import VideoFileSource
from capture.audio_visualization_source.audio_visualization_source import AudioVisualizationSource


class SourceManager:
    """图像源管理器"""

    def __init__(self):
        self._sources = {}  # source_id -> ImageSourceInterface
        self._active_source_id = None
        # UI 可以在推流线程正在取帧时切换源。用同一把锁保护取帧和
        # stop/start，避免旧源在 capture() 过程中被停止或释放。
        self._source_lock = threading.RLock()

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
        elif source_type == SourceType.AUDIO_VISUALIZATION:
            source = AudioVisualizationSource(source_type=source_type, source_id=source_id)

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
        with self._source_lock:
            if source_id is None:
                source_id = self._active_source_id

            return self._sources.get(source_id)

    def switch_source(self, source_id: str) -> bool:
        """切换活动图像源"""
        with self._source_lock:
            if source_id not in self._sources:
                return False

            current = self.get_source()
            new_source = self._sources[source_id]

            # 已经在使用这个源时无需重新启动，以免视频等源被重置。
            if current is new_source and current._is_running:
                return True

            if current:
                current.stop()

            self._active_source_id = source_id
            new_source.start()
            return True

    def list_configured_sources(self) -> List[Dict[str, Any]]:
        """列出已经成功初始化、可供运行时切换的配置源。"""
        with self._source_lock:
            return [
                {
                    'id': source_id,
                    'type': source.source_type.value,
                    'active': source_id == self._active_source_id
                }
                for source_id, source in self._sources.items()
            ]

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
        with self._source_lock:
            source = self.get_source(source_id)
            if not source:
                return None

            return source.capture()

    def get_source_info(self, source_id: str = None) -> Dict[str, Any]:
        """在线程安全的前提下读取图像源配置。"""
        with self._source_lock:
            source = self.get_source(source_id)
            return source.get_info() if source else {}

    def get_source_preview(self, source_id: str = None) -> Optional[np.ndarray]:
        """读取图像源缓存的预览帧，不推进播放位置。"""
        with self._source_lock:
            source = self.get_source(source_id)
            preview_getter = getattr(source, 'get_preview_frame', None) if source else None
            return preview_getter() if preview_getter else None

    def set_source_config(self, config: Dict[str, Any], source_id: str = None) -> bool:
        """在取帧锁内更新图像源运行时配置。"""
        with self._source_lock:
            source = self.get_source(source_id)
            return source.set_config(config) if source else False

    def cleanup(self):
        """清理所有资源"""
        with self._source_lock:
            for source_id, source in self._sources.items():
                try:
                    source.release()
                except Exception as e:
                    print(f"Error releasing source {source_id}: {e}")

            self._sources.clear()
            self._active_source_id = None
