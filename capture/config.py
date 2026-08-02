# config.yaml
"""
streamer:
  sources:
    - type: "screen"
      id: "main_screen"
      params:
        display_idx: 0
        fps: 30
        region: [0, 0, 1920, 1080]

    - type: "camera"
      id: "webcam"
      params:
        camera_idx: 0
        resolution: [1280, 720]
        fps: 25

    - type: "camera"
      id: "ip_camera"
      params:
        url: "rtsp://192.168.1.100:554/stream"

  active_source: "main_screen"
  stream_url: "rtmp://server/live/stream"
  bitrate: 2500000
"""
import copy
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, Optional

import cv2
import yaml

from capture.streamer import Streamer
application_path = '.'
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
    application_path = os.path.join(application_path, '_internal')
elif __file__:
    application_path = os.path.dirname(os.path.dirname(__file__))

# def resource_path(rel_path):
#     if getattr(sys, 'frozen', False):
#         return os.path.join(sys._MEIPASS, rel_path)
#     return os.path.abspath(rel_path)

# cfg = resource_path("config.yaml")

__streamer:Streamer = None
_AUDIO_CONFIG_KEYS = ("target_device", "input", "effects")
_VIDEO_CONFIG_KEYS = (
    "video_path",
    "play_mode",
    "playback_rate",
    "first_play_video",
    "auto_play_next",
    "random_play",
    "auto_crop_center",
    "preview_enabled",
    "fps",
)


def get_stream_config_path() -> Path:
    """Return the config_stream.yaml path used by the running application."""
    return Path(application_path) / 'config_stream.yaml'


def _load_stream_config(path: Path) -> Dict[str, Any]:
    with path.open('r', encoding='utf-8') as config_file:
        document = yaml.safe_load(config_file)
    if not isinstance(document, dict) or not isinstance(document.get('streamer'), dict):
        raise ValueError("config_stream.yaml 缺少 streamer 配置")
    if not isinstance(document['streamer'].get('sources'), list):
        raise ValueError("config_stream.yaml 缺少 streamer.sources 列表")
    return document


def _find_audio_source(document: Dict[str, Any], source_id: str) -> Dict[str, Any]:
    source = next(
        (
            item for item in document['streamer']['sources']
            if isinstance(item, dict) and item.get('id') == source_id
        ),
        None,
    )
    if source is None:
        raise ValueError(f"配置文件中找不到图像源: {source_id}")
    if source.get('type') != 'audio_visualization':
        raise ValueError(f"图像源不是音频可视化类型: {source_id}")
    params = source.setdefault('params', {})
    if not isinstance(params, dict):
        raise ValueError(f"图像源 {source_id} 的 params 必须是对象")
    return source


def _find_video_source(document: Dict[str, Any], source_id: str) -> Dict[str, Any]:
    source = next(
        (
            item for item in document['streamer']['sources']
            if isinstance(item, dict) and item.get('id') == source_id
        ),
        None,
    )
    if source is None:
        raise ValueError(f"配置文件中找不到图像源: {source_id}")
    if source.get('type') != 'video_file':
        raise ValueError(f"图像源不是本地视频类型: {source_id}")
    params = source.setdefault('params', {})
    if not isinstance(params, dict):
        raise ValueError(f"图像源 {source_id} 的 params 必须是对象")
    return source


def _write_stream_config(path: Path, document: Dict[str, Any]) -> Path:
    """Atomically replace a stream configuration file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            newline='\n',
            dir=path.parent,
            prefix=f'.{path.name}.',
            suffix='.tmp',
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            yaml.safe_dump(
                document,
                temp_file,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return path


def _audio_runtime_values(runtime_config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(runtime_config, dict):
        raise ValueError("运行时配置必须是对象")
    values = {
        key: copy.deepcopy(runtime_config[key])
        for key in _AUDIO_CONFIG_KEYS
        if key in runtime_config
    }
    if not values:
        raise ValueError("没有可保存的音频参数")
    return values


def save_source_runtime_config(
    source_id: str,
    runtime_config: Dict[str, Any],
    config_path: Optional[os.PathLike] = None,
) -> Path:
    """Persist an audio source's selected device and effect values atomically."""
    if not source_id:
        raise ValueError("图像源 ID 不能为空")
    values = _audio_runtime_values(runtime_config)
    path = Path(config_path) if config_path is not None else get_stream_config_path()
    document = _load_stream_config(path)
    source = _find_audio_source(document, source_id)
    source['params'].update(values)
    # Saving raw runtime values means the source should resume these custom
    # values instead of re-applying an older named preset on next startup.
    source['params'].pop('active_preset', None)
    return _write_stream_config(path, document)


def save_video_source_config(
    source_id: str,
    runtime_config: Dict[str, Any],
    config_path: Optional[os.PathLike] = None,
) -> Path:
    """将本地视频源的路径、播放方式和预览参数原子写回配置。"""
    if not source_id:
        raise ValueError("图像源 ID 不能为空")
    if not isinstance(runtime_config, dict):
        raise ValueError("运行时配置必须是对象")
    values = {
        key: copy.deepcopy(runtime_config[key])
        for key in _VIDEO_CONFIG_KEYS
        if key in runtime_config
    }
    current_video = runtime_config.get('current_video')
    if current_video:
        values['first_play_video'] = current_video
    if not values:
        raise ValueError("没有可保存的视频参数")

    path = Path(config_path) if config_path is not None else get_stream_config_path()
    document = _load_stream_config(path)
    source = _find_video_source(document, source_id)
    source['params'].update(values)
    return _write_stream_config(path, document)


def load_audio_presets(
    source_id: str,
    config_path: Optional[os.PathLike] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load all named effect combinations belonging to one audio source."""
    if not source_id:
        raise ValueError("图像源 ID 不能为空")
    path = Path(config_path) if config_path is not None else get_stream_config_path()
    source = _find_audio_source(_load_stream_config(path), source_id)
    presets = source['params'].get('presets', {})
    if not isinstance(presets, dict):
        raise ValueError(f"图像源 {source_id} 的 presets 必须是对象")
    return copy.deepcopy(presets)


def load_active_audio_preset(
    source_id: str,
    config_path: Optional[os.PathLike] = None,
) -> Optional[str]:
    """Load the named preset that an audio source should restore at startup."""
    if not source_id:
        raise ValueError("图像源 ID 不能为空")
    path = Path(config_path) if config_path is not None else get_stream_config_path()
    source = _find_audio_source(_load_stream_config(path), source_id)
    name = source['params'].get('active_preset')
    presets = source['params'].get('presets', {})
    if name is None:
        return None
    if not isinstance(name, str) or not isinstance(presets, dict) or name not in presets:
        return None
    return name


def save_active_audio_preset(
    source_id: str,
    preset_name: str,
    config_path: Optional[os.PathLike] = None,
) -> Path:
    """Persist the preset selection for one audio source."""
    name = preset_name.strip() if isinstance(preset_name, str) else ''
    if not name:
        raise ValueError("预设名称不能为空")
    path = Path(config_path) if config_path is not None else get_stream_config_path()
    document = _load_stream_config(path)
    source = _find_audio_source(document, source_id)
    presets = source['params'].get('presets', {})
    if not isinstance(presets, dict):
        raise ValueError(f"图像源 {source_id} 的 presets 必须是对象")
    if name not in presets:
        raise ValueError(f"找不到音频预设: {name}")
    source['params']['active_preset'] = name
    return _write_stream_config(path, document)


def save_audio_preset(
    source_id: str,
    preset_name: str,
    runtime_config: Dict[str, Any],
    config_path: Optional[os.PathLike] = None,
    *,
    make_active: bool = False,
) -> Path:
    """Save or overwrite a named audio effect combination."""
    name = preset_name.strip() if isinstance(preset_name, str) else ''
    if not name:
        raise ValueError("预设名称不能为空")
    if len(name) > 80 or '\n' in name or '\r' in name:
        raise ValueError("预设名称不能换行且最多 80 个字符")
    values = _audio_runtime_values(runtime_config)
    path = Path(config_path) if config_path is not None else get_stream_config_path()
    document = _load_stream_config(path)
    source = _find_audio_source(document, source_id)
    presets = source['params'].setdefault('presets', {})
    if not isinstance(presets, dict):
        raise ValueError(f"图像源 {source_id} 的 presets 必须是对象")
    presets[name] = values
    if make_active:
        source['params']['active_preset'] = name
    return _write_stream_config(path, document)


def delete_audio_preset(
    source_id: str,
    preset_name: str,
    config_path: Optional[os.PathLike] = None,
) -> Path:
    """Delete one named audio effect combination."""
    path = Path(config_path) if config_path is not None else get_stream_config_path()
    document = _load_stream_config(path)
    source = _find_audio_source(document, source_id)
    presets = source['params'].get('presets', {})
    if not isinstance(presets, dict):
        raise ValueError(f"图像源 {source_id} 的 presets 必须是对象")
    if preset_name not in presets:
        raise ValueError(f"找不到音频预设: {preset_name}")
    del presets[preset_name]
    if source['params'].get('active_preset') == preset_name:
        source['params'].pop('active_preset', None)
    return _write_stream_config(path, document)


def get_streamer() -> Streamer:
    global  __streamer
    # 加载配置
    if __streamer is None:
        with get_stream_config_path().open(encoding="utf-8", mode='r') as f:
            config = yaml.safe_load(f)
        # 创建推流器
        __streamer = Streamer(config.get('streamer', {}))
        # 初始化
        if not __streamer.initialize():
            raise Exception(f"Failed to initialize streamer")
    return __streamer
# 使用示例
def __main():
    streamer = get_streamer()
    try:
        # 推流循环
        while True:
            # 获取帧（自动从当前活动源获取）
            frame = streamer.get_frame()

            if frame is not None:
                # 推流处理...
                # stream_frame(frame)
                print(frame.shape)

                pass

            # 可以动态切换源
            # if some_condition:
            #     streamer.switch_source("webcam")

    except KeyboardInterrupt:
        print("Streaming stopped")
    finally:
        streamer.close()


if __name__ == "__main__":
    __main()
