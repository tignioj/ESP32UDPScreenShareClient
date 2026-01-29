from abc import ABC, abstractmethod
from typing import Optional, Tuple, List, Dict, Any
from enum import Enum
import numpy as np
import time
import cv2
from threading import Lock, Thread
import logging

from capture.interface import ImageSourceInterface, SourceType

# 配置日志
logger = logging.getLogger(__name__)


class RTSPError(Exception):
    """RTSP源异常"""
    pass

class RTSPSource(ImageSourceInterface):
    """RTSP流图像源"""

    DEFAULT_CONFIG = {
        'buffer_size': 100,  # 帧缓冲大小
        'reconnect_attempts': 5,  # 重连尝试次数
        'reconnect_delay': 2.0,  # 重连延迟(秒)
        'timeout': 10,  # 连接超时(秒)
        'use_buffer': True,  # 是否使用缓冲
        'decode_resolution': None,  # 解码分辨率 (width, height)，None表示使用原始分辨率
        'rtsp_transport': 'tcp',  # RTSP传输协议: 'tcp'或'udp'
        'stabilization_frames': 30,  # 稳定帧数，用于计算平均FPS
    }

    def __init__(self, rtsp_url: str, source_id: str = ""):
        super().__init__(SourceType.RTSP, source_id)
        self.rtsp_url = rtsp_url
        self.cap = None
        self.lock = Lock()
        self.last_frame = None
        self.last_frame_time = 0
        self.frame_count = 0
        self.start_time = 0
        self.actual_fps = 0
        self.config = self.DEFAULT_CONFIG.copy()
        self.buffer = []
        self.buffer_lock = Lock()
        self.capture_thread = None
        self.should_stop = False
        self.connected = False
        self.reconnect_count = 0
        self._info_cache = {}

    def initialize(self, **kwargs) -> bool:
        """
        初始化RTSP连接

        Args:
            **kwargs: 可选参数，可覆盖默认配置

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 更新配置
            self.config.update(kwargs)

            # 设置OpenCV RTSP参数
            cap_props = {
                cv2.CAP_PROP_BUFFERSIZE: self.config['buffer_size'],
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC: self.config['timeout'] * 1000,
            }

            # 如果是RTSP，设置传输协议
            if self.rtsp_url.startswith('rtsp://'):
                if self.config['rtsp_transport'] == 'tcp':
                    # 添加TCP传输参数
                    rtsp_url = self.rtsp_url
                # rtsp_url = f"{self.rtsp_url}?tcp"
                else:
                    rtsp_url = self.rtsp_url
            else:
                rtsp_url = self.rtsp_url

            logger.info(f"尝试连接RTSP流: {rtsp_url}")
            self.cap = cv2.VideoCapture(rtsp_url)

            # 设置额外属性
            for prop, value in cap_props.items():
                self.cap.set(prop, value)

            if not self.cap.isOpened():
                logger.error(f"无法打开RTSP流: {rtsp_url}")
                return False

            # 测试读取一帧
            ret, frame = self.cap.read()
            if not ret:
                logger.error("RTSP流连接成功但无法读取帧")
                self.cap.release()
                return False

            self.connected = True
            self.frame_count = 0
            self.start_time = time.time()

            # 启动捕获线程（如果使用缓冲）
            if self.config['use_buffer']:
                self.should_stop = False
                self.capture_thread = Thread(target=self._capture_loop, daemon=True)
                self.capture_thread.start()
                logger.info("RTSP捕获线程已启动")

            logger.info(f"RTSP源初始化成功: {rtsp_url}")
            return True

        except Exception as e:
            logger.error(f"RTSP源初始化失败: {e}")
            if self.cap:
                self.cap.release()
            return False

    def _capture_loop(self):
        """捕获线程的主循环"""
        while not self.should_stop:
            try:
                frame = self._read_frame()
                if frame is not None:
                    with self.buffer_lock:
                        self.buffer.append(frame)
                        # 保持缓冲区大小
                        if len(self.buffer) > self.config['buffer_size']:
                            self.buffer.pop(0)
                else:
                    time.sleep(0.01)  # 避免CPU空转
            except Exception as e:
                logger.error(f"捕获线程错误: {e}")
                time.sleep(0.1)

    def _read_frame(self) -> Optional[np.ndarray]:
        """读取一帧图像（内部方法）"""
        if not self.cap or not self.cap.isOpened():
            if not self._reconnect():
                return None

        ret, frame = self.cap.read()
        if not ret:
            logger.warning("读取帧失败，尝试重连...")
            if not self._reconnect():
                return None
            ret, frame = self.cap.read()
            if not ret:
                return None

        # 转换BGR到RGB
        # frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # 调整分辨率（如果需要）
        if self.config['decode_resolution']:
            width, height = self.config['decode_resolution']
            frame = cv2.resize(frame, (width, height))

        # 更新帧率计算
        current_time = time.time()
        self.frame_count += 1

        if self.frame_count >= self.config['stabilization_frames']:
            elapsed = current_time - self.start_time
            if elapsed > 0:
                self.actual_fps = self.frame_count / elapsed

        return frame

    def _reconnect(self) -> bool:
        """尝试重新连接RTSP流"""
        if self.reconnect_count >= self.config['reconnect_attempts']:
            logger.error(f"重连次数超过限制: {self.config['reconnect_attempts']}")
            return False

        self.reconnect_count += 1
        logger.info(f"尝试重连 ({self.reconnect_count}/{self.config['reconnect_attempts']})")

        if self.cap:
            self.cap.release()

        time.sleep(self.config['reconnect_delay'])

        try:
            rtsp_url = self.rtsp_url
            if self.config['rtsp_transport'] == 'tcp':
                # rtsp_url = f"{self.rtsp_url}?tcp"
                rtsp_url = self.rtsp_url

            self.cap = cv2.VideoCapture(rtsp_url)
            if self.cap.isOpened():
                self.reconnect_count = 0
                self.connected = True
                logger.info("重连成功")
                return True
            else:
                logger.warning("重连失败")
                return False
        except Exception as e:
            logger.error(f"重连异常: {e}")
            return False

    def capture(self) -> Optional[np.ndarray]:
        """
        捕获一帧图像

        Returns:
            RGB888格式的numpy数组，形状为 (height, width, 3)
            如果失败则返回None
        """
        if not self._is_running or not self.connected:
            return None

        try:
            if self.config['use_buffer'] and self.capture_thread:
                # 从缓冲区获取最新帧
                with self.buffer_lock:
                    if self.buffer:
                        self.last_frame = self.buffer.pop(0)
                        return self.last_frame
                    else:
                        return self.last_frame
            else:
                # 直接读取帧
                frame = self._read_frame()
                if frame is not None:
                    self.last_frame = frame
                return frame

        except Exception as e:
            logger.error(f"捕获帧时出错: {e}")
            return None

    def get_info(self) -> Dict[str, Any]:
        """
        获取RTSP源信息

        Returns:
            包含分辨率、帧率等信息的字典
        """
        info = {
            'source_type': self.source_type.value,
            'source_id': self.source_id,
            'rtsp_url': self.rtsp_url,
            'connected': self.connected,
            'is_running': self._is_running,
            'configured_fps': self._fps,
            'actual_fps': round(self.actual_fps, 2),
            'frame_count': self.frame_count,
            'reconnect_count': self.reconnect_count,
            'use_buffer': self.config['use_buffer'],
            'buffer_size': len(self.buffer) if self.config['use_buffer'] else 0,
        }

        # 获取视频流信息
        if self.cap and self.cap.isOpened():
            try:
                width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = self.cap.get(cv2.CAP_PROP_FPS)

                info.update({
                    'width': width,
                    'height': height,
                    'stream_fps': fps if fps > 0 else 'unknown',
                    'codec': self._get_codec_info(),
                    'total_frames': int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) if self.cap.get(
                        cv2.CAP_PROP_FRAME_COUNT) > 0 else 'streaming',
                })
            except Exception as e:
                logger.warning(f"获取视频流信息失败: {e}")

        return info

    def _get_codec_info(self) -> str:
        """获取编解码器信息"""
        if not self.cap:
            return "unknown"

        try:
            fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
            codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
            return codec if codec.strip() else "unknown"
        except:
            return "unknown"

    def get_available_configs(self) -> List[Dict[str, Any]]:
        """
        获取可用的配置选项

        Returns:
            配置选项列表
        """
        configs = [
            {
                'name': 'fps',
                'type': 'float',
                'description': '目标帧率',
                'default': 30.0,
                'range': (1.0, 120.0)
            },
            {
                'name': 'buffer_size',
                'type': 'int',
                'description': '帧缓冲大小',
                'default': 100,
                'range': (1, 1000)
            },
            {
                'name': 'reconnect_attempts',
                'type': 'int',
                'description': '最大重连尝试次数',
                'default': 5,
                'range': (1, 50)
            },
            {
                'name': 'reconnect_delay',
                'type': 'float',
                'description': '重连延迟(秒)',
                'default': 2.0,
                'range': (0.1, 30.0)
            },
            {
                'name': 'timeout',
                'type': 'int',
                'description': '连接超时(秒)',
                'default': 10,
                'range': (1, 60)
            },
            {
                'name': 'use_buffer',
                'type': 'bool',
                'description': '是否使用帧缓冲区',
                'default': True
            },
            {
                'name': 'decode_resolution',
                'type': 'tuple',
                'description': '解码分辨率 (width, height)，None表示原始分辨率',
                'default': None
            },
            {
                'name': 'rtsp_transport',
                'type': 'choice',
                'description': 'RTSP传输协议',
                'default': 'tcp',
                'choices': ['tcp', 'udp']
            },
            {
                'name': 'stabilization_frames',
                'type': 'int',
                'description': '稳定帧数（用于计算平均FPS）',
                'default': 30,
                'range': (10, 1000)
            }
        ]
        return configs

    def set_config(self, config: Dict[str, Any]) -> bool:
        """
        设置配置参数

        Args:
            config: 配置参数字典

        Returns:
            bool: 设置是否成功
        """
        try:
            for key, value in config.items():
                if key in self.config:
                    # 特殊处理某些参数
                    if key == 'decode_resolution' and value is not None:
                        if not isinstance(value, (list, tuple)) or len(value) != 2:
                            logger.error(f"decode_resolution 必须是包含两个元素的列表或元组")
                            continue
                        value = tuple(int(x) for x in value)
                    elif key == 'rtsp_transport' and value not in ['tcp', 'udp']:
                        logger.error(f"rtsp_transport 必须是 'tcp' 或 'udp'")
                        continue

                    self.config[key] = value
                    logger.info(f"配置更新: {key} = {value}")
                elif key == 'fps':
                    self.fps = value
                else:
                    logger.warning(f"忽略未知配置项: {key}")

            return True
        except Exception as e:
            logger.error(f"设置配置失败: {e}")
            return False

    def release(self):
        """释放资源"""
        self.should_stop = True

        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)
            self.capture_thread = None

        if self.cap:
            self.cap.release()
            self.cap = None

        with self.buffer_lock:
            self.buffer.clear()

        self.connected = False
        logger.info("RTSP源资源已释放")

    def start(self):
        """启动RTSP源"""
        super().start()
        if not self.connected:
            self.initialize()

    def stop(self):
        """停止RTSP源"""
        super().stop()
        self.should_stop = True


# 使用示例
def example_usage():
    """RTSP源使用示例"""
    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 创建RTSP源
    rtsp_url ="rtsp://admin:admin@192.168.30.134:8554/live"

    # 简化版，用于测试
    # rtsp_url = "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov"

    rtsp_source = RTSPSource(rtsp_url, source_id="camera_01")

    # 自定义配置
    config = {
        'buffer_size': 50,
        'reconnect_attempts': 10,
        'use_buffer': True,
        'decode_resolution': (640, 480),
        'rtsp_transport': 'tcp'
    }

    # 初始化并启动
    if rtsp_source.initialize(**config):
        rtsp_source.start()

        try:
            # 捕获10帧
            for i in range(10):
                frame = rtsp_source.capture()
                if frame is not None:
                    print(f"帧 {i + 1}: 形状={frame.shape}, 类型={frame.dtype}")

                    # 显示信息
                    if i % 5 == 0:
                        info = rtsp_source.get_info()
                        print(f"源信息: {info}")
                else:
                    print("获取帧失败")

                time.sleep(0.1)  # 模拟处理延迟

        finally:
            rtsp_source.release()
    else:
        print("RTSP源初始化失败")


if __name__ == "__main__":
    example_usage()