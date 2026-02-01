# from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly

from capture.interface import ImageSourceInterface
class MacScreenshot(ImageSourceInterface):
    def capture(self, region=None):
        # 使用Quartz或PyObjC实现
        pass