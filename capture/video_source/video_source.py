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
        self.play_mode: str = "list_loop"
        self.playback_rate: float = 1.0
        self.first_play_video: Optional[str] = None
        self.auto_crop_center: bool = False  # 视频裁边居中
        self.preview_enabled: bool = True

        self._video_files: List[str] = []
        self._current_idx: int = 0
        self._cap: Optional[cv2.VideoCapture] = None
        self._last_frame_time: float = 0.0
        self._frame_interval: float = 1.0 / self._fps
        self._duration_seconds: float = 0.0
        self._last_frame: Optional[np.ndarray] = None

    def initialize(self, **kwargs) -> bool:
        self.video_path = kwargs.get('video_path', '')
        configured_mode = kwargs.get('play_mode')
        if configured_mode not in {'single_loop', 'list_loop', 'random'}:
            if kwargs.get('random_play', False):
                configured_mode = 'random'
            elif kwargs.get('auto_play_next', True):
                configured_mode = 'list_loop'
            else:
                configured_mode = 'single_loop'
        self._set_play_mode(configured_mode)
        self.playback_rate = self._normalize_playback_rate(kwargs.get('playback_rate', 1.0))
        self.first_play_video = kwargs.get('first_play_video', None)
        self.fps = kwargs.get('fps', 30)
        self.auto_crop_center = kwargs.get('auto_crop_center', False)
        self.preview_enabled = bool(kwargs.get('preview_enabled', True))

        from capture.config import application_path
        sample_video_path = os.path.join(application_path, 'sample_video')
        if self.video_path is None or self.video_path == '':
            print(f"[VideoFileSource] 你没有设置video_path, 默认使用sample_video")
            self.video_path = sample_video_path

        if not os.path.isabs(self.video_path):
            self.video_path = os.path.join(application_path, self.video_path)
        self.video_path = os.path.abspath(self.video_path)

        if not os.path.isdir(self.video_path):
            print(f"[VideoFileSource] 你设置的video_path 不存在: {self.video_path}, 自动使用sample_video")
            self.video_path = os.path.abspath(sample_video_path)

        # 获取所有 mp4 文件
        self._video_files = sorted(
            (f for f in os.listdir(self.video_path) if f.lower().endswith('.mp4')),
            key=str.casefold,
        )
        if not self._video_files:
            print(f"[VideoFileSource] 未找到 mp4 视频: {self.video_path}")
            return False

        self._current_idx = (
            self._video_files.index(self.first_play_video)
            if self.first_play_video in self._video_files
            else 0
        )
        return self._open_current_video()

    @staticmethod
    def _normalize_playback_rate(value: Any) -> float:
        try:
            return max(0.5, min(float(value), 2.0))
        except (TypeError, ValueError):
            return 1.0

    def _set_play_mode(self, mode: str):
        self.play_mode = mode if mode in {'single_loop', 'list_loop', 'random'} else 'list_loop'
        self.auto_play_next = self.play_mode != 'single_loop'
        self.random_play = self.play_mode == 'random'

    def refresh_video_files(self) -> bool:
        """重新扫描当前目录，并尽量保持当前视频的播放状态。"""
        if not os.path.isdir(self.video_path):
            return False

        video_files = sorted(
            (f for f in os.listdir(self.video_path) if f.lower().endswith('.mp4')),
            key=str.casefold,
        )
        if not video_files:
            return False

        current_video = (
            self._video_files[self._current_idx]
            if self._video_files and self._current_idx < len(self._video_files)
            else None
        )
        self._video_files = video_files
        if current_video in self._video_files:
            self._current_idx = self._video_files.index(current_video)
            return True

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
        playback_fps = self._fps or video_fps or 30
        self._frame_interval = 1.0 / (playback_fps * self.playback_rate)
        frame_count = self._cap.get(cv2.CAP_PROP_FRAME_COUNT)
        self._duration_seconds = frame_count / video_fps if video_fps > 0 else 0.0
        self._last_frame_time = time.perf_counter() - self._frame_interval
        self._last_frame = None
        return True

    def _next_video_index(self) -> int:
        """计算下一个视频索引"""
        if self.play_mode == 'single_loop':
            return self._current_idx

        if self.play_mode == 'random':
            if len(self._video_files) <= 1:
                return 0
            choices = [index for index in range(len(self._video_files)) if index != self._current_idx]
            return random.choice(choices)
        else:
            return (self._current_idx + 1) % len(self._video_files)

    def play_video(self, video_name: str) -> bool:
        """立即播放列表中的指定视频。"""
        if not isinstance(video_name, str) or os.path.basename(video_name) != video_name:
            return False
        try:
            self._current_idx = self._video_files.index(video_name)
        except ValueError:
            return False
        return self._open_current_video()

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

        now = time.perf_counter()
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
        self._last_frame = frame.copy()
        return frame

    def get_preview_frame(self) -> Optional[np.ndarray]:
        """返回最近一次送出的画面，避免预览额外消耗视频帧。"""
        return self._last_frame.copy() if self._last_frame is not None else None

    def get_info(self) -> Dict[str, Any]:
        info = {
            'video_path': self.video_path,
            'current_video': self._video_files[self._current_idx] if self._video_files else None,
            'video_files': list(self._video_files),
            'fps': self.fps,
            'auto_play_next': self.auto_play_next,
            'random_play': self.random_play,
            'play_mode': self.play_mode,
            'playback_rate': self.playback_rate,
            'auto_crop_center': self.auto_crop_center,
            'preview_enabled': self.preview_enabled,
            'duration_seconds': self._duration_seconds,
            'position_seconds': 0.0,
        }
        if self._cap:
            info['width'] = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            info['height'] = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            info['position_seconds'] = max(0.0, self._cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0)
        duration = info['duration_seconds']
        info['progress'] = min(1.0, info['position_seconds'] / duration) if duration > 0 else 0.0
        return info

    def get_available_configs(self) -> List[Dict[str, Any]]:
        return [
            {'param': 'video_path', 'type': 'str'},
            {'param': 'fps', 'type': 'float', 'range': [1, 120]},
            {'param': 'auto_play_next', 'type': 'bool'},
            {'param': 'random_play', 'type': 'bool'},
            {'param': 'play_mode', 'type': 'str'},
            {'param': 'playback_rate', 'type': 'float', 'range': [0.5, 2.0]},
            {'param': 'first_play_video', 'type': 'str'},
            {'param': 'auto_crop_center', 'type': 'bool'},
            {'param': 'preview_enabled', 'type': 'bool'},
        ]

    def set_config(self, config: Dict[str, Any]) -> bool:
        for key, value in config.items():
            if key == 'video_path':
                self.video_path = value
            elif key == 'fps':
                self.fps = value
                self._frame_interval = 1.0 / ((self._fps or 30) * self.playback_rate)
            elif key == 'auto_play_next':
                self.auto_play_next = bool(value)
                self._set_play_mode('list_loop' if self.auto_play_next else 'single_loop')
            elif key == 'random_play':
                self.random_play = bool(value)
                self._set_play_mode('random' if self.random_play else ('list_loop' if self.auto_play_next else 'single_loop'))
            elif key == 'play_mode':
                self._set_play_mode(value)
            elif key == 'playback_rate':
                self.playback_rate = self._normalize_playback_rate(value)
                self._frame_interval = 1.0 / ((self._fps or 30) * self.playback_rate)
            elif key == 'first_play_video': self.first_play_video = value
            elif key == 'auto_crop_center': self.auto_crop_center = value
            elif key == 'preview_enabled': self.preview_enabled = bool(value)
        # 如果路径变化，需要重新扫描
        if 'video_path' in config or 'first_play_video' in config:
            initialized = self.initialize(
                video_path=self.video_path,
                play_mode=self.play_mode,
                playback_rate=self.playback_rate,
                first_play_video=self.first_play_video,
                fps=self.fps,
                auto_crop_center=self.auto_crop_center,
                preview_enabled=self.preview_enabled,
            )
            if not initialized:
                return False
        elif config.get('refresh_video_files'):
            if not self.refresh_video_files():
                return False
        requested_video = config.get('current_video', config.get('play_video'))
        if requested_video is not None:
            return self.play_video(requested_video)
        return True

    def release(self):
        if self._cap:
            self._cap.release()
            self._cap = None
