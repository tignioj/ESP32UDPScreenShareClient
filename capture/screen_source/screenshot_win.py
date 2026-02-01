# screenshot_win.py
import os
import time
import math
import numpy as np
from typing import Optional, Tuple, List, Dict, Any
import win32gui
import win32ui
import win32con
import ctypes
from ctypes import windll

# 尝试导入mss和cv2，但处理导入失败的情况
try:
    import mss
    import cv2

    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    cv2 = None

from capture.interface import ImageSourceInterface, SourceType, ScreenshotError

user32 = windll.user32
user32.SetProcessDPIAware()


class WindowsScreenCapture(ImageSourceInterface):
    """Windows平台屏幕截图源"""

    def __init__(self, source_id: str = "", display_idx: int = 0):
        super().__init__(SourceType.SCREEN, source_id or f"screen_{display_idx}")
        self.display_idx = display_idx
        self._region = None  # 截图区域 (x, y, width, height)
        self._window_hwnd = None  # 窗口句柄
        self._window_title = None  # 窗口标题
        self._capture_mode = "display"  # display, window, region
        self._remove_title_bar = True  # 是否移除窗口标题栏
        self._use_mss = MSS_AVAILABLE  # 是否使用mss库
        self._last_resolution = None

    def initialize(self, **kwargs) -> bool:
        """初始化截图源"""
        try:
            # 从kwargs获取配置
            if 'region' in kwargs:
                self._region = kwargs['region']
                self._capture_mode = 'region'

            if 'window_title' in kwargs:
                self._window_title = kwargs['window_title']
                self._capture_mode = 'window'
                self._window_hwnd = self._get_hwnd_by_window_title(self._window_title)
                if self._window_hwnd is None:
                    raise ScreenshotError(f"Window '{self._window_title}' not found")

            if 'remove_title_bar' in kwargs:
                self._remove_title_bar = kwargs['remove_title_bar']

            if 'use_mss' in kwargs and MSS_AVAILABLE:
                self._use_mss = kwargs['use_mss']

            if 'display_idx' in kwargs:
                self.display_idx = kwargs['display_idx']

            # 设置帧率
            if 'fps' in kwargs:
                self.fps = kwargs['fps']

            self._is_running = True
            return True

        except Exception as e:
            raise ScreenshotError(f"Failed to initialize Windows screen capture: {e}")

    def capture(self) -> Optional[np.ndarray]:
        """捕获一帧屏幕图像"""
        if not self._is_running:
            return None

        try:
            if self._capture_mode == 'window' and self._window_hwnd:
                # 窗口截图
                img = self._capture_window(
                    hwnd=self._window_hwnd,
                    remove_title_bar=self._remove_title_bar,
                    use_mss=self._use_mss
                )
            elif self._region:
                # 区域截图
                x, y, width, height = self._region
                img = self._capture_region(
                    x, y, width, height,
                    use_mss=self._use_mss,
                    monitor_index=self.display_idx
                )
            else:
                # 全屏截图
                img = self._capture_fullscreen(
                    use_mss=self._use_mss,
                    monitor_index=self.display_idx
                )

            # 确保图像是RGB格式
            if img is not None:
                # 如果使用mss，图像是BGRA，需要转换为RGB
                if self._use_mss and MSS_AVAILABLE:
                    # mss返回的是BGRA
                    img = img[:, :, :3]  # 移除alpha通道
                    # img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                elif img.shape[2] == 4:  # 如果是BGRA
                    img = img[:, :, :3]  # 移除alpha通道
                    # 如果是BGR，转换为RGB
                    if cv2 is not None:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                # 确保是uint8类型
                img = img.astype(np.uint8)

            return img

        except Exception as e:
            print(f"Capture failed: {e}")
            return None

    def get_info(self) -> Dict[str, Any]:
        """获取截图源信息"""
        try:
            if self._capture_mode == 'window' and self._window_hwnd:
                left, top, right, bottom = win32gui.GetWindowRect(self._window_hwnd)
                width = right - left
                height = bottom - top

                if self._remove_title_bar:
                    x, y, window_inner_width, window_inner_height = win32gui.GetClientRect(self._window_hwnd)
                    border_pixels = math.floor((width - window_inner_width) / 2)
                    titlebar_pixels = height - window_inner_height - border_pixels
                    width = window_inner_width
                    height = window_inner_height

                resolution = (width, height)
                window_title = win32gui.GetWindowText(self._window_hwnd)

                info = {
                    'source_type': self.source_type.value,
                    'source_id': self.source_id,
                    'capture_mode': self._capture_mode,
                    'resolution': resolution,
                    'window_title': window_title,
                    'window_hwnd': self._window_hwnd,
                    'fps': self._fps,
                    'remove_title_bar': self._remove_title_bar,
                    'use_mss': self._use_mss
                }
            elif self._region:
                x, y, width, height = self._region
                resolution = (width, height)
                info = {
                    'source_type': self.source_type.value,
                    'source_id': self.source_id,
                    'capture_mode': self._capture_mode,
                    'resolution': resolution,
                    'region': self._region,
                    'fps': self._fps,
                    'use_mss': self._use_mss
                }
            else:
                # 获取显示器分辨率
                width = user32.GetSystemMetrics(0)
                height = user32.GetSystemMetrics(1)
                resolution = (width, height)
                info = {
                    'source_type': self.source_type.value,
                    'source_id': self.source_id,
                    'capture_mode': self._capture_mode,
                    'resolution': resolution,
                    'display_idx': self.display_idx,
                    'fps': self._fps,
                    'use_mss': self._use_mss
                }

            self._last_resolution = resolution
            return info

        except Exception as e:
            print(f"Failed to get info: {e}")
            return {
                'source_type': self.source_type.value,
                'source_id': self.source_id,
                'error': str(e)
            }

    def get_available_configs(self) -> List[Dict[str, Any]]:
        """获取可用的配置选项"""
        configs = [
            {
                'name': 'capture_mode',
                'type': 'str',
                'description': '截图模式: display, window, region',
                'default': 'display',
                'options': ['display', 'window', 'region']
            },
            {
                'name': 'display_idx',
                'type': 'int',
                'description': '显示器索引',
                'default': 0,
                'range': '0-10'
            },
            {
                'name': 'window_title',
                'type': 'str',
                'description': '窗口标题（capture_mode=window时使用）',
                'default': '',
                'optional': True
            },
            {
                'name': 'window_hwnd',
                'type': 'int',
                'description': '窗口句柄（capture_mode=window时使用）',
                'default': None,
                'optional': True
            },
            {
                'name': 'remove_title_bar',
                'type': 'bool',
                'description': '是否移除窗口标题栏',
                'default': True
            },
            {
                'name': 'region',
                'type': 'tuple',
                'description': '截图区域 (x, y, width, height)',
                'default': None,
                'optional': True
            },
            {
                'name': 'fps',
                'type': 'float',
                'description': '帧率',
                'default': 30.0,
                'range': '1.0-120.0'
            },
            {
                'name': 'use_mss',
                'type': 'bool',
                'description': '是否使用mss库（如果可用）',
                'default': MSS_AVAILABLE
            }
        ]

        return configs

    def set_config(self, config: Dict[str, Any]) -> bool:
        """设置配置参数"""
        try:
            if 'capture_mode' in config:
                self._capture_mode = config['capture_mode']

            if 'display_idx' in config:
                self.display_idx = config['display_idx']

            if 'window_title' in config:
                self._window_title = config['window_title']
                self._window_hwnd = self._get_hwnd_by_window_title(self._window_title)
                if self._window_hwnd is None and self._window_title:
                    raise ScreenshotError(f"Window '{self._window_title}' not found")

            if 'window_hwnd' in config:
                self._window_hwnd = config['window_hwnd']

            if 'remove_title_bar' in config:
                self._remove_title_bar = config['remove_title_bar']

            if 'region' in config:
                self._region = config['region']

            if 'fps' in config:
                self.fps = config['fps']

            if 'use_mss' in config:
                if config['use_mss'] and not MSS_AVAILABLE:
                    raise ScreenshotError("MSS library not available")
                self._use_mss = config['use_mss']

            return True

        except Exception as e:
            print(f"Failed to set config: {e}")
            return False

    def release(self):
        """释放资源"""
        self._is_running = False
        # Windows API不需要特殊的清理

    # ========== 现有的截图方法封装 ==========

    @staticmethod
    def _get_hwnd_by_window_title(window_title):
        """通过窗口标题获取句柄"""
        hwnd = win32gui.FindWindow(None, window_title)
        if hwnd is None:
            # 尝试模糊匹配
            def enum_windows_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd) and window_title.lower() in win32gui.GetWindowText(hwnd).lower():
                    results.append(hwnd)
                return True

            results = []
            win32gui.EnumWindows(enum_windows_callback, results)
            if results:
                return results[0]
        return hwnd

    def _capture_fullscreen(self, use_mss=False, monitor_index=0) -> np.ndarray:
        """全屏截图"""
        if use_mss and MSS_AVAILABLE:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[monitor_index])
                return np.array(screenshot)
        else:
            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)
            return self._capture_region(0, 0, width, height, use_mss=False)

    def _capture_region(self, x: int, y: int, width: int, height: int,
                        use_mss=False, monitor_index=0) -> np.ndarray:
        """区域截图"""
        if use_mss and MSS_AVAILABLE:
            with mss.mss() as sct:
                monitor = {"top": y, "left": x, "width": width, "height": height}
                screenshot = sct.grab(monitor)
                return np.array(screenshot)
        else:
            hdesktop = win32gui.GetDesktopWindow()
            desktop_dc = win32gui.GetWindowDC(hdesktop)
            src_dc = win32ui.CreateDCFromHandle(desktop_dc)
            mem_dc = src_dc.CreateCompatibleDC()

            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(src_dc, width, height)
            mem_dc.SelectObject(bmp)

            mem_dc.BitBlt(
                (0, 0),
                (width, height),
                src_dc,
                (x, y),
                win32con.SRCCOPY
            )

            bmp_info = bmp.GetInfo()
            bmp_str = bmp.GetBitmapBits(True)

            img = np.frombuffer(bmp_str, dtype=np.uint8)
            img = img.reshape((bmp_info["bmHeight"], bmp_info["bmWidth"], 4))
            img = img[:, :, :3]  # BGRA -> BGR

            mem_dc.DeleteDC()
            src_dc.DeleteDC()
            win32gui.ReleaseDC(hdesktop, desktop_dc)
            win32gui.DeleteObject(bmp.GetHandle())

            return img

    def _capture_window(self, hwnd=None, remove_title_bar=True, use_mss=False) -> np.ndarray:
        """窗口截图"""
        if not hwnd:
            if self._window_hwnd:
                hwnd = self._window_hwnd
            else:
                raise ValueError("No window handle provided")

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        window_full_width = right - left
        window_full_height = bottom - top

        width = window_full_width
        height = window_full_height

        cropped_x = 0
        cropped_y = 0

        if remove_title_bar:
            x, y, window_inner_width, window_inner_height = win32gui.GetClientRect(hwnd)
            border_pixels = math.floor((window_full_width - window_inner_width) / 2)
            titlebar_pixels = window_full_height - window_inner_height - border_pixels

            cropped_x = border_pixels
            cropped_y = titlebar_pixels

            width = window_inner_width
            height = window_inner_height

        if use_mss and MSS_AVAILABLE:
            if remove_title_bar:
                return self._capture_region(
                    left + cropped_x, top + cropped_y, width, height, use_mss=True
                )
            else:
                return self._capture_region(left, top, window_full_width, window_full_height, use_mss=True)
        else:
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            mem_dc = src_dc.CreateCompatibleDC()

            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(src_dc, width, height)
            mem_dc.SelectObject(bmp)

            mem_dc.BitBlt(
                (0, 0),
                (width, height),
                src_dc,
                (cropped_x, cropped_y),
                win32con.SRCCOPY
            )

            bmp_info = bmp.GetInfo()
            bmp_str = bmp.GetBitmapBits(True)

            img = np.frombuffer(bmp_str, dtype=np.uint8)
            img = img.reshape((bmp_info["bmHeight"], bmp_info["bmWidth"], 4))
            img = img[:, :, :3]  # BGRA -> BGR

            mem_dc.DeleteDC()
            src_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            win32gui.DeleteObject(bmp.GetHandle())

            return img


if __name__ == '__main__':
    sc = WindowsScreenCapture()
    sc.initialize()
    fpscount = 0
    start_time = time.time()
    while True:
        fpscount += 1
        f = sc.capture()
        if time.time() - start_time > 2:
            print(fpscount /2)
            fpscount = 0
            start_time = time.time()
