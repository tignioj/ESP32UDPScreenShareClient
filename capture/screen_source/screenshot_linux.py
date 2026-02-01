# Linux实现 (screenshot_linux.py)
from capture.interface import ImageSourceInterface


class LinuxScreenshot(ImageSourceInterface):
    def capture(self, region=None):
        # 使用X11或Wayland实现
        pass