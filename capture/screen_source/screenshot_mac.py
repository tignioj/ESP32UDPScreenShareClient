"""macOS screen capture implementation.

``window_region`` is a rectangular region of the desktop, not a native macOS
window handle.  It is captured through ``mss`` so the same configuration can
be used for a window-sized area on Windows, macOS and Linux.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from capture.interface import ImageSourceInterface, ScreenshotError, SourceType

try:
    import mss

    MSS_AVAILABLE = True
except ImportError:
    mss = None
    MSS_AVAILABLE = False


class MacScreenCapture(ImageSourceInterface):
    """Capture a display or a rectangular desktop region on macOS."""

    def __init__(self, source_id: str = "", display_idx: int = 0):
        super().__init__(SourceType.SCREEN, source_id or f"screen_{display_idx}")
        self.display_idx = display_idx
        self._capture_mode = "display"
        self._region: Optional[Tuple[int, int, int, int]] = None

    def initialize(self, **kwargs) -> bool:
        if not MSS_AVAILABLE:
            raise ScreenshotError("macOS 截图需要 mss；请重新安装项目依赖")

        try:
            self.set_config(kwargs)
            self._is_running = True
            return True
        except Exception as exc:
            raise ScreenshotError(f"Failed to initialize macOS screen capture: {exc}") from exc

    def capture(self) -> Optional[np.ndarray]:
        if not self._is_running:
            return None

        try:
            with mss.mss() as sct:
                if self._capture_mode == "region" and self._region is not None:
                    x, y, width, height = self._region
                    monitor = {"left": x, "top": y, "width": width, "height": height}
                else:
                    monitors = sct.monitors
                    # mss monitor 0 is the whole virtual desktop; physical
                    # displays start at 1, while our config uses 0-based IDs.
                    monitor_index = self.display_idx + 1
                    if monitor_index >= len(monitors):
                        raise ScreenshotError(f"显示器索引无效: {self.display_idx}")
                    monitor = monitors[monitor_index]

                # mss returns BGRA.  The rest of this application consumes a
                # three-channel OpenCV-style frame, so drop alpha only.
                return np.asarray(sct.grab(monitor))[:, :, :3].astype(np.uint8, copy=False)
        except Exception as exc:
            print(f"macOS screen capture failed: {exc}")
            return None

    def get_info(self) -> Dict[str, Any]:
        try:
            if self._capture_mode == "region" and self._region is not None:
                _, _, width, height = self._region
                resolution = (width, height)
            else:
                left, top, width, height = self._display_bounds(self.display_idx)
                resolution = (width, height)

            return {
                "capture_mode": self._capture_mode,
                "resolution": resolution,
                "region": self._region,
                "display_idx": self.display_idx,
                "fps": self._fps,
            }
        except Exception as exc:
            return {
                "capture_mode": self._capture_mode,
                "region": self._region,
                "display_idx": self.display_idx,
                "fps": self._fps,
                "error": str(exc),
            }

    def get_available_configs(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "capture_mode",
                "type": "str",
                "description": "截图模式: display 或 region",
                "default": "display",
                "options": ["display", "region"],
            },
            {
                "name": "display_idx",
                "type": "int",
                "description": "显示器索引（从 0 开始）",
                "default": 0,
                "range": f"0-{max(0, len(self.list_displays()) - 1)}",
            },
            {
                "name": "region",
                "type": "tuple",
                "description": "桌面区域 (x, y, width, height)",
                "default": None,
                "optional": True,
            },
            {
                "name": "fps",
                "type": "float",
                "description": "帧率",
                "default": 30.0,
                "range": "1.0-120.0",
            },
        ]

    def set_config(self, config: Dict[str, Any]) -> bool:
        if not isinstance(config, dict):
            raise ValueError("截图配置必须是对象")

        capture_mode = config.get("capture_mode", self._capture_mode)
        if "region" in config and "capture_mode" not in config:
            capture_mode = "region"
        if capture_mode not in ("display", "region"):
            raise ValueError("macOS 只支持 capture_mode=display 或 region")

        region = self._region
        if "region" in config:
            region = self._validate_region(config["region"])
        if capture_mode == "region" and region is None:
            raise ValueError("capture_mode=region 时必须提供 region")

        if "display_idx" in config:
            display_idx = int(config["display_idx"])
            if display_idx < 0:
                raise ValueError("display_idx 必须大于等于 0")
            self.display_idx = display_idx
        if "fps" in config:
            self.fps = float(config["fps"])

        self._capture_mode = capture_mode
        self._region = region
        return True

    def release(self):
        self._is_running = False

    def list_displays(self) -> List[Dict[str, int]]:
        if not MSS_AVAILABLE:
            return []
        try:
            with mss.mss() as sct:
                return [dict(monitor) for monitor in sct.monitors[1:]]
        except Exception:
            return []

    def _display_bounds(self, display_idx: int) -> Tuple[int, int, int, int]:
        displays = self.list_displays()
        if display_idx >= len(displays):
            raise ScreenshotError(f"显示器索引无效: {display_idx}")
        monitor = displays[display_idx]
        return monitor["left"], monitor["top"], monitor["width"], monitor["height"]

    @staticmethod
    def _validate_region(region: Sequence[Any]) -> Tuple[int, int, int, int]:
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise ValueError("region 必须是 (x, y, width, height)")
        x, y, width, height = (int(value) for value in region)
        if width <= 0 or height <= 0:
            raise ValueError("region 的宽和高必须大于 0")
        return x, y, width, height
