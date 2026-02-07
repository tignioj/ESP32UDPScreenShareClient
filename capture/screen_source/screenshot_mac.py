# from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly
from typing import List, Dict, Any

from capture.interface import ImageSourceInterface
class MacScreenCapture(ImageSourceInterface):
    def capture(self, region=None):
        # 使用Quartz或PyObjC实现
        pass
    def initialize(self, **kwargs):
        return True

    def get_available_configs(self) -> List[Dict[str, Any]]: pass

    def get_info(self) -> Dict[str, Any]: pass

    def release(self):pass

    def set_config(self, config: Dict[str, Any]) -> None: pass