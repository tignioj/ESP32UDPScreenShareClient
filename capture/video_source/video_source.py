import cv2
import os
import random
import time
import numpy as np
from typing import Optional, List, Dict, Any
from capture.interface import SourceType, ImageSourceInterface


class VideoFileSource(ImageSourceInterface):
    """视频文件播放源"""

    def __init__(self, source_type: SourceType, source_id: str = ""):
        super().__init__(source_type, source_id)
        self.video_path: str = ""
        self.auto_play_next: bool = True
        self.random_play: bool = False
        self.first_play_video: Optional[str] = None
        self.auto_crop_center: bool = False  # 视频裁边居中

        self._video_files: List[str] = []
        self._current_idx: int = 0
        self._cap: Optional[cv2.VideoCapture] = None
        self._last_frame_time: float = 0.0
        self._frame_interval: float = 1.0 / self._fps

    def initialize(self, **kwargs) -> bool:
        self.video_path = kwargs.get('video_path', '')
        self.auto_play_next = kwargs.get('auto_play_next', True)
        self.random_play = kwargs.get('random_play', False)
        self.first_play_video = kwargs.get('first_play_video', None)
        self.fps = kwargs.get('fps', 30)
        self.auto_crop_center = kwargs.get('auto_crop_center', False)
        if not os.path.isdir(self.video_path):
            print(f"[VideoFileSource] video_path 不存在: {self.video_path}")
            from capture.config import application_path
            sample_video_path = os.path.join(application_path, 'sample_video')
            print(f"[VideoFileSource] 尝试加载内置视频: {sample_video_path}")
            if not os.path.isdir(sample_video_path):
                print(f"[VideoFileSource] 内置视频也不存在，初始化失败: {application_path}")
                return False
            self.video_path = sample_video_path

        # 获取所有 mp4 文件
        self._video_files = [f for f in os.listdir(self.video_path)
                             if f.lower().endswith('.mp4')]
        if not self._video_files:
            print(f"[VideoFileSource] 未找到 mp4 视频: {self.video_path}")
            return False

        # 如果指定第一个播放的视频
        if self.first_play_video and self.first_play_video in self._video_files:
            self._video_files.remove(self.first_play_video)
            self._video_files.insert(0, self.first_play_video)

        self._current_idx = 0
        return self._open_current_video()

    def _open_current_video(self) -> bool:
        """打开当前视频"""
        if self._cap:
            self._cap.release()
            self._cap = None

        if not self._video_files:
            return False

        video_file = os.path.join(self.video_path, self._video_files[self._current_idx])
        self._cap = cv2.VideoCapture(video_file)
        if not self._cap.isOpened():
            print(f"[VideoFileSource] 打开视频失败: {video_file}")
            return False

        # 获取视频帧率，方便同步播放
        video_fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._frame_interval = 1.0 / (self._fps or video_fps or 30)
        self._last_frame_time = time.time()
        return True

    def _next_video_index(self) -> int:
        """计算下一个视频索引"""
        if not self.auto_play_next:
            return 0  # 不自动切换，永远播放第一个视频

        if self.random_play:
            return random.randint(0, len(self._video_files) - 1)
        else:
            return (self._current_idx + 1) % len(self._video_files)

    def resize_crop_square(self, img, target_size=240):
        h, w = img.shape[:2]

        if w > h:
            # 裁左右
            crop = h
            x0 = (w - crop) // 2
            img = img[:, x0:x0 + crop]
        elif h > w:
            # 裁上下
            crop = w
            y0 = (h - crop) // 2
            img = img[y0:y0 + crop, :]
        # w == h 不需要裁

        # 等比例 resize
        img = cv2.resize(img, (target_size, target_size),
                         interpolation=cv2.INTER_AREA)
        return img
    def capture(self) -> Optional[np.ndarray]:
        if not self._cap or not self._is_running:
            return None

        now = time.time()
        if now - self._last_frame_time < self._frame_interval:
            return None  # 控制帧率

        ret, frame = self._cap.read()
        if not ret:
            # 当前视频播放完毕，切换下一个
            self._current_idx = self._next_video_index()
            if not self._open_current_video():
                return None
            ret, frame = self._cap.read()
            if not ret:
                return None

        self._last_frame_time = now
        # 转为 RGB
        # frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if self.auto_crop_center:
            frame = self.resize_crop_square(frame, 240)
        return frame

    def get_info(self) -> Dict[str, Any]:
        info = {
            'video_path': self.video_path,
            'current_video': self._video_files[self._current_idx] if self._video_files else None,
            'fps': self.fps,
            'auto_play_next': self.auto_play_next,
            'random_play': self.random_play,
            'auto_crop_center': self.auto_crop_center
        }
        if self._cap:
            info['width'] = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            info['height'] = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return info

    def get_available_configs(self) -> List[Dict[str, Any]]:
        return [
            {'param': 'video_path', 'type': 'str'},
            {'param': 'fps', 'type': 'float', 'range': [1, 120]},
            {'param': 'auto_play_next', 'type': 'bool'},
            {'param': 'random_play', 'type': 'bool'},
            {'param': 'first_play_video', 'type': 'str'},
            {'param': 'auto_crop_center', 'type': 'bool'}
        ]

    def set_config(self, config: Dict[str, Any]) -> bool:
        for key, value in config.items():
            if key == 'video_path':
                self.video_path = value
            elif key == 'fps':
                self.fps = value
            elif key == 'auto_play_next':
                self.auto_play_next = bool(value)
            elif key == 'random_play':
                self.random_play = bool(value)
            elif key == 'first_play_video': self.first_play_video = value
            elif key == 'auto_crop_center': self.auto_crop_center = value
        # 如果路径变化，需要重新扫描
        if 'video_path' in config or 'first_play_video' in config:
            return self.initialize(
                video_path=self.video_path,
                auto_play_next=self.auto_play_next,
                random_play=self.random_play,
                first_play_video=self.first_play_video,
                fps=self.fps,
                auto_crop_center=self.auto_crop_center
            )
        return True

    def release(self):
        if self._cap:
            self._cap.release()
            self._cap = None
