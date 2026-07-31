# ESP32UDPScreenShareClient

## ESP32 专用屏幕共享推流工具
- 视频演示: https://www.bilibili.com/video/BV16R6ABCEVN
- ESP32串流固件：
  - 屏幕共享纯享版固件【推荐,更稳定流畅】：https://github.com/tignioj/ESP32UDPScreenShare/releases/tag/v0.0.2
  - AIO固件【目前bug有点多，暂时不推荐，但也能用】，https://github.com/tignioj/HoloCubic_AIO/releases/tag/v2.13.8

![main](main.png)
![demo](demo.jpg)
## 使用手册
###  一、配置推流图像源`config_stream.yaml`

本程序用途：
用于给holocubic ESP32发送“视频流“，视频流的来源可以是屏幕截图

必须要有视频流才能发送，如何配置视频流？

找到`_internal/config_stream.yaml`文件，里面有多个示例，每一个source都是一个“视频流”配置。

程序启动后，主界面的“图像源”下拉框会列出所有已启用且初始化成功的 source。选择一项即可立即切换，推流过程中也可以切换，无需停止后重新启动。

## 配置说明
- type 可选值：`screen|video_file|audio_visualization|rtsp|camera`
- screen 表示截图视频源
- video_file 表示本地视频
- audio_visualization 音频可视化。需要电脑安装[VBCable](https://vb-audio.com/Cable/)
- rtsp仅做了简单的适配，需要注意如果rtsp连接不上，就设置enable为false否则程序打不开，camera没做。
- camera相机,没做。

## 类型一：屏幕源: type:screen
表示来源于屏幕截图
-	id:自定义一个名称，
-	enable: 如果配置了源但是不想开启，可以设置enable为False
-	params:
- display_idx: 不用管。
  -	region: [left, top, width, height]，如果没有指定region，就会全屏截图
  -	fps：没什么用，暂时没做。
  -	use_mss: True|False。 兼容模式。按照标题截图有时候黑屏，就把这个use_mss设置为True
  -	window_title：窗口名称。 表示截取指定符合标题的窗口，如果发现是黑屏，则开启兼容模

## 类型二：本地视频： type:video_file
表示来源于本地mp4文件， 注意，如果路径不存在，程序会闪退。
```yaml
streamer:
  sources:
    - type: "video_file" # 视频源类型
      id: "video_player"  # 自定义的名称
      params:
        video_path: 'I:\genshin_video\character_show'
        auto_play_next: True  # 是否自动循环播放全部视频
        auto_crop_center: True # 是否自动裁边居中
        random_play: True # 是否开启乱序循环播放
#        first_play_video: 'xinhai.mp4'  # 指定第一个播放的视频
        fps: 30
```
## 类型三：音频可视化: type:audio_visualization
来源于系统音频输入并生成可视化图像

### 一、安装[VBCable](https://vb-audio.com/Cable/)
必须要安装该音频驱动，否则无法正常运行。
### 二、设置系统声音输出为Cable-Input
步骤：`系统->声音->选择播放声音的位置->CABLE Input`
注意：有些音乐播放器在切换声卡输出的时候需要重启该播放器(例如Apple Music)，否则不生效。
![cable_input.png](cable_input.png)
经过这一步，你的电脑会没声音，因为声音都传输进这个"CABLE Input"去了，但是这个时候，你播放音乐，可以识别到频谱。
### 三、恢复电脑声音
系统->声音->更多声音设置->录制->CABLE Output>侦听->侦听此设备->通过此设备播放。
选择你的扬声器设备即可。
![audio_output_setting.png](audio_output_setting.png)
经过这一步，你的电脑将恢复声音。

### 四、在配置文件中添加源类型“音频可视化"
找到`config_stream.yaml`，添加一个源，指定type字段为"audio_visualization"，在id中随意输入名称，在params中选择需要的可视化效果。
```yaml
    - type: "audio_visualization"
      id: 'audio_visual1'
      params:
        draw_waveform: True # 特效：波形
        draw_spectrum_bar: True # 特效：频谱柱
        draw_spectrum_circular1: False # 圆环特效1：三个独立的律动圆
        draw_spectrum_circular2: True  # 圆环特效2：红蓝白电离
        draw_spectrum_circular3: False # 圆环特效3：白色动态圆环+内外双律动扩散
        draw_particles: True # 特效：底部发射粒子
        gain: 1.0 # 灵敏度：0.1-4.0
        spectrum_smoothing: 0.5 # 频谱平滑：0.0-0.95
        radius_smoothing: 0.9 # 律动平滑：0.0-0.98
        base_radius: 60 # 圆环基础半径：20-100
        radius_expansion: 30 # 圆环律动幅度：5-100
        max_particles: 200 # 最大粒子数：0-500
```

程序运行后，在“图像源”中选择音频可视化源，界面会自动展开“音频视觉效果”面板。可以直接切换效果组合、自由叠加单项效果和拖动参数滑块；修改会实时作用于当前画面，不需要停止或重新启动推流。界面修改只影响本次运行，如需作为下次启动的默认值，请同时写入上面的 `config_stream.yaml` 参数。

最后，别忘了在配置文件底部选择激活，这里输入上面配置的id名称。
```yaml
  active_source: "audio_visual1"
```

## 类型四：网络视频： type:rtsp
- id: "my_mobile_phone_rtsp_camera"
- enable: false 注意rtsp源如果连接不上就设置为false否则程序无法启动
- params:
  - rtsp_url: "rtsp://admin:admin@192.168.30.134:8554/live"
  - buffer_size: 5000
  - timeout: 3  超过几秒没连上就断开rtsp


## 指定源
最后最重要的是指定`active_source: xxx`这里`xxx`要输入上面配置的任意一个源。例如这里设置的一个本地视频源，
其id为"video_player"，那么在active_source中，写入`video_player`，那么程序启动的时候就会切换该源，如果初始化失败可能会导致程序无法开启或者闪退。
例如加入这里的`video_path`如果不存在，程序就没法启动。另外，这里的`enable`字段必须要设置为`True`，否则无法使用该源
```yaml
streamer:
  sources:
    - type: "video_file" # 视频
      id: "video_player"
      enable: False
      params:
        video_path: 'I:\genshin_video\character_show'
        auto_play_next: True  # 是否自动循环播放全部视频
        random_play: True # 是否开启乱序循环播放
#        first_play_video: 'xinhai.mp4'  # 指定第一个播放的视频
        fps: 30
  active_source: "window_fullscreen"
```

如何全屏截图：去掉region和window_title就可以截全屏

目前只适配了Windows的屏幕共享和简单的rtsp

配置示例:
```yaml
streamer:
  sources:
    - type: "demo" # 基础示例
      id: 'demo1'

    - type: "audio_visualization"
      id: 'audio_visual1'
      params:
        draw_waveform: True # 特效：波形
        draw_spectrum_bar: True # 特效：频谱柱
        draw_spectrum_circular1: False # 圆环特效1：三个独立的律动圆
        draw_spectrum_circular2: True  # 圆环特效2：红蓝白电离
        draw_spectrum_circular3: False # 圆环特效3：白色动态圆环+内外双律动扩散
        draw_particles: True # 特效：底部发射粒子



    - type: "video_file" # 本地视频文件
      id: "video_player"
      enable: True
      params:
#        video_path: 'I:\genshin_video\character_show'
        video_path: 'sample_video'
        auto_play_next: True # 是否自动循环播放全部视频
        auto_crop_center: True # 是否自动裁边居中
        random_play: True # 是否开启乱序循环播放
#        first_play_video: 'xinhai.mp4'  # 指定第一个播放的视频
        fps: 30
    - type: "screen" # 区域截图
      id: "window_region"
      params:
        display_idx: 0
        fps: 30
        region: [684, 330, 300, 300]
        use_mss: False
    - type: "screen"  # 全屏截图
      id: "window_fullscreen"
      params:
        display_idx: 0
        fps: 30
        use_mss: False
    - type: "screen"  # 按窗口截图
      id: "yuanshen"
      params:
        window_title: '原神'
        display_idx: 0
        fps: 30
        use_mss: False
        remove_title_bar: True
    - type: "screen"  # 按窗口截图（use_mss=True兼容模式)
      id: "zzz"
      params:
        window_title: '绝区零'
        display_idx: 0
        fps: 30
        use_mss: True

    - type: "camera" # 相机
      id: "webcam"
      enable: false
      params:
        camera_idx: 0
        resolution: [1280, 720]
        fps: 25

    - type: "rtsp" #rtsp
      id: "my_mobile_phone_rtsp_camera"
      enable: false
      params:
        rtsp_url: "rtsp://admin:admin@192.168.30.134:8554/live"
        buffer_size: 5000
        timeout: 3

#  active_source: "yuanshen"
  active_source: "audio_visual1"
#  active_source: "window_region"
  stream_url: "rtmp://server/live/stream"
  bitrate: 2500000
```


### 二、启动`main_ui.py`
先安装 [uv](https://docs.astral.sh/uv/)，然后在项目目录同步依赖：
```powershell
uv sync
```

启动程序：
```powershell
uv run python main_ui.py
```


### 开发指南
### 1.如何创造自己的source？
在`capture/interface.py`找到一个想要的分类，或者自己再创造一个分类
```text
class SourceType(Enum):
    """图像源类型"""
    SCREEN = "screen"
    CAMERA = "camera"
    VIDEO_FILE = "video_file"
    IMAGE_FILE = "image_file"
    VIRTUAL = "virtual"  # 虚拟源，如测试图、合成图像
    RTSP = "rtsp"  # 新增RTSP类型
```
例如这里我打算实现一个`VIDEO_FILE` 类型的Source，那么在capture下新建一个`video_Source/video_source.py`,
新建一个类叫VideoPlayerSource,并且继承`capture.interface.ImageSourceInterface`,
```python
from capture.interface import ImageSourceInterface, SourceType

class VideoPlayerSource(ImageSourceInterface):
    def __init__(self, source_type: SourceType, source_id: str = ""):
        super().__init__(source_type, source_id)
        pass
```

接下来实现接口的capture方法，返回一个numpy数组。剩余几个抽象方法直接先pass，但是initialize要返回True否则会加载失败
这里capture生成一张彩虹图片
```python
from capture.interface import ImageSourceInterface, SourceType
import numpy as np
from typing import Optional, List, Dict, Any
class VideoPlayerSource(ImageSourceInterface):
  def __init__(self, source_type: SourceType, source_id: str = ""):
    super().__init__(source_type, source_id)

  def capture(self) -> Optional[np.ndarray]:
      height, width = 240, 240
      image = np.zeros((height, width, 3), dtype=np.uint8)
      # 将宽度分为7段，创建彩虹色
      segment_width = width // 7
      colors = [
          [255, 0, 0],  # 红色
          [255, 165, 0],  # 橙色
          [255, 255, 0],  # 黄色
          [0, 255, 0],  # 绿色
          [0, 255, 255],  # 青色
          [0, 0, 255],  # 蓝色
          [128, 0, 128]  # 紫色
      ]
      for i in range(7):
          start_x = i * segment_width
          end_x = (i + 1) * segment_width if i < 6 else width
          image[:, start_x:end_x] = colors[i]
      return image

    def initialize(self, **kwargs) -> bool: return True
    def get_image(self) -> np.ndarray: pass
    def get_info(self) -> dict: pass
    def release(self, **kwargs) -> bool: pass
    def set_config(self, **kwargs) -> bool: pass
    def get_available_configs(self) -> List[Dict[str, Any]]:pass

```

把Source添加到SourceManager
```python
from capture.video_source.video_source import VideoFileSource

class SourceManager:
    """图像源管理器"""
    # 其余代码不变
    def create_source(self, source_type: SourceType,
                      source_id: str = "", **kwargs) -> Optional[str]:
        """创建图像源"""
        # 上面代码不动
        #...添加下面这样，让程序识别配置文件
        elif source_type == SourceType.VIDEO_FILE:
            video_path = kwargs.get('video_path')
            source = VideoFileSource(source_type=source_type,source_id=source_id)


```


然后在配置文件 `config_stream.yaml`中，添加这个源
```yaml
streamer:
  sources:
    - type: "video_file" # 视频
      id: "video_player"
      params:
        display_idx: 0
        fps: 30
  active_source: "video_player" # 启用该源
```
点击推流，就会出现彩虹色图片
![demo_source.png](demo_source.png)

接下来嫌麻烦，不想自己做，直接让AI帮你做，描述需求
```yaml
# 帮我实现一下类型为VIDEO_FILE接口，功能是循环播放指定目录的所有MP4视频，调用capture返回正在播放的某一帧，可以通过参数设置帧率和指定目录，可以指定第一个播放的视频，可以设置是否开启自动播放下一个视频，可以开启是否乱序播放，如果关闭自动播放下一个视频就循环播放指定的第一个视频，指定的视频文件名称也是通过参数传入。
# 粘贴source_mamager.py文件以及streamer.py文件以及config_stream.yaml给他
# 示例配置
streamer:
  sources:
    - type: "video_file" # 视频
      id: "video_player"
      params:
        video_path: 'C:\Users\Administrator\Desktop\obsrecord'
        auto_play_next: True  # 是否自动循环播放全部视频
        random_play: True # 是否开启乱序循环播放
        first_play_video: 'play_me.mp4'  # 指定第一个播放的视频
        fps: 30
```
二话不说直接生成了
