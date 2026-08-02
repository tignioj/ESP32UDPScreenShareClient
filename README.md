# ESP32 UDP Screen Share Client

一个面向 ESP32 屏幕接收端的 Windows 桌面推流工具。程序可以采集屏幕、窗口、本地视频、摄像头、RTSP 流或系统音频可视化画面，并通过 UDP 将图像发送给 ESP32。

- 演示视频：[Bilibili](https://www.bilibili.com/video/BV16R6ABCEVN)
- 推荐接收端固件：[ESP32UDPScreenShare Releases](https://github.com/tignioj/ESP32UDPScreenShare/releases)

![程序主界面](main.png)

## 功能特性

- 支持 `240 × 240`、`180 × 180`、`120 × 120` 三种输出分辨率
- 支持 RGB332 和 RGB565 色彩格式
- 支持全屏、指定区域和指定窗口截图
- 支持本地视频、摄像头及 RTSP 图像源
- 支持音频频谱、波形、粒子等多种可叠加的可视化效果
- 推流过程中可实时切换图像源、调整截图区域和音频效果
- 内置推流预览，可查看完成缩放和色彩量化后实际通过 UDP 发送的画面
- UDP 配置分为不可修改的内置预设和可保存多份的个人预设
- 支持保存 UDP 参数、音频参数及音频效果组合预设

## Windows 发行版

不想安装 Python 或配置开发环境时，可以直接从 [GitHub Releases](https://github.com/tignioj/ESP32UDPScreenShareClient/releases) 下载免安装的 Windows x64 压缩包。下载 `ESP32UDPScreenShareClient-<tag>-windows-x64.zip`，完整解压后运行其中的 `ESP32UDPScreenShareClient.exe`，不要直接在压缩包内启动。

免安装版的图像源配置位于程序目录下的 `_internal/config_stream.yaml`；程序运行后生成的 UDP 配置和个人预设保存在程序工作目录下的 `config.yaml`。源码版则使用项目根目录下的 `config_stream.yaml` 和 `config.yaml`。

维护者在 `main` 分支的提交上推送形如 `vX.Y.Z`（例如 `v0.0.9`）的 tag 后，GitHub Actions 会自动执行测试、打包并创建或更新对应的 Release。也可以在 Actions 页面的 **Build and release Windows app** 工作流中选择 **Run workflow**，输入一个已有 tag 手动重新构建发布。

## 运行环境

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10/11（当前主要测试平台） |
| Python | 3.10 或更高版本 |
| 包管理器 | 推荐使用 [uv](https://docs.astral.sh/uv/) |
| 网络 | 电脑与 ESP32 位于同一局域网，且 UDP 通信未被防火墙拦截 |
| 接收端 | 已刷入兼容的 ESP32 UDP 屏幕接收固件 |

音频可视化不是普通推流的必需条件；只有采集系统播放声音时才需要安装 VB-CABLE。使用免安装版不需要另行安装 Python 或 uv。

## 快速开始

### 1. 准备 ESP32

给 ESP32 刷入上方推荐的接收端固件，启动设备并记下它在局域网中的 IP 地址。接收端默认 UDP 端口通常为 `8888`。

请先确认：

- 电脑和 ESP32 连接到同一个路由器或局域网；
- 路由器没有开启会隔离设备的“访客网络”或“客户端隔离”；
- Windows 防火墙允许 `ESP32UDPScreenShareClient.exe` 或 Python 访问专用网络。

### 2. 选择运行方式

#### 使用 Windows 免安装版

1. 打开[项目 Releases 页面](https://github.com/tignioj/ESP32UDPScreenShareClient/releases)，下载最新的 `ESP32UDPScreenShareClient-<tag>-windows-x64.zip`；
2. 将压缩包完整解压到一个可写目录；
3. 首次验证时，建议编辑 `_internal/config_stream.yaml`，将 `streamer.active_source` 改为 `demo1`；
4. 双击 `ESP32UDPScreenShareClient.exe` 启动程序。

#### 从源码运行

获取项目：

```powershell
git clone https://github.com/tignioj/ESP32UDPScreenShareClient.git
cd ESP32UDPScreenShareClient
```

如果已经下载了项目，直接在项目根目录打开 PowerShell 即可。后续命令必须在包含 `main_ui.py` 和 `config_stream.yaml` 的目录中执行。

安装 uv 和项目依赖：

先按 [uv 官方文档](https://docs.astral.sh/uv/getting-started/installation/) 安装 uv，然后执行：

```powershell
uv sync
```

`uv sync` 会根据 `pyproject.toml` 和 `uv.lock` 创建虚拟环境并安装所需依赖。

首次运行前选择一个可靠的图像源。源码版启动时会读取项目根目录下的 `config_stream.yaml`，并初始化其中所有未设置 `enable: false` 的图像源。

首次验证建议将文件底部的活动源改成内置测试画面，避免因为音频设备、窗口标题或视频路径无效而启动失败：

```yaml
streamer:
  # sources 配置保持不变
  active_source: demo1
```

启动程序：

```powershell
uv run python main_ui.py
```

### 3. 配置并开始推流

窗口打开后：

1. 在“1 UDP 发送配置”页签中填写 ESP32 的局域网 IP，而不是电脑 IP；
2. 将 UDP 端口保持为接收端使用的端口，推荐固件默认为 `8888`；
3. 从“UDP 预设”下拉列表选择内置或个人预设，选择后会立即应用；
4. 在“2 图像源配置”页签中选择需要的来源并点击“切换”；
5. 点击“开始推流”，在右侧查看完成缩放和色彩量化后的实际发送画面，并观察日志中的帧率、包速率和错误信息；
6. 需要结束时点击“停止推流”。

6 个“内置”预设由程序提供，只能应用，不能修改或删除。调整地址或传输参数后，点击“保存为个人预设”并输入名称，即可保存一份包含服务器地址、UDP 端口和全部传输参数的个人预设；可以保存多份，也可以覆盖或删除已选中的个人预设。

保存、覆盖或删除个人预设时，程序会把当前配置、当前预设类型以及全部个人预设写入程序工作目录下的 `config.yaml`，下次启动自动读取。旧版扁平格式的 `config.yaml` 仍可直接加载；首次启动没有该文件时，程序默认选择“预设5：120 高清色彩”。

### 可选：源码版不使用 uv

也可以使用 Python 自带的虚拟环境。以下命令不需要激活虚拟环境：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install mss numpy opencv-python pywin32 pyyaml sounddevice
.\.venv\Scripts\python.exe main_ui.py
```

## 图像源配置

所有图像源都配置在 `config_stream.yaml` 的 `streamer.sources` 中。源码版使用项目根目录下的文件，免安装版使用 `_internal` 目录下的文件。通用结构如下：

```yaml
streamer:
  sources:
    - type: demo
      id: demo1
      enable: true
      params: {}

  active_source: demo1
```

字段说明：

| 字段 | 是否必填 | 说明 |
| --- | --- | --- |
| `type` | 是 | 图像源类型 |
| `id` | 是 | 图像源的唯一名称，用于界面显示和 `active_source` 引用 |
| `enable` | 否 | 是否在启动时初始化，默认为 `true` |
| `params` | 视类型而定 | 该图像源的专属参数 |
| `active_source` | 是 | 程序启动后默认使用的图像源 ID |

目前支持以下类型：

| `type` | 用途 | 主要参数 |
| --- | --- | --- |
| `demo` | 内置测试画面 | 无 |
| `screen` | 屏幕、区域或窗口截图 | `display_idx`、`region`、`window_title`、`use_mss` |
| `video_file` | 循环或随机播放目录中的 MP4 视频 | `video_path`、`play_mode`、`playback_rate`、`first_play_video` |
| `audio_visualization` | 将麦克风、虚拟音频设备或外接输入绘制为动态画面 | `target_device`、`input`、`effects` |
| `camera` | 本地摄像头 | `camera_idx`、`resolution`、`fps` |
| `rtsp` | 网络视频流 | `rtsp_url`、`timeout`、`rtsp_transport` |

> `active_source` 必须指向一个已启用且初始化成功的源。无效的视频路径、找不到的窗口、不可连接的 RTSP 地址或不可用的音频设备都可能使对应源初始化失败。暂时不用的源应设置为 `enable: false`。

### 屏幕截图

全屏截图：

```yaml
- type: screen
  id: fullscreen
  params:
    display_idx: 0
    fps: 30
    use_mss: true
```

指定区域截图，`region` 的格式为 `[左上角 X, 左上角 Y, 宽度, 高度]`：

```yaml
- type: screen
  id: screen_region
  params:
    display_idx: 0
    region: [100, 100, 800, 800]
    fps: 30
    use_mss: true
```

指定窗口截图：

```yaml
- type: screen
  id: game_window
  params:
    window_title: 原神
    remove_title_bar: true
    fps: 30
    use_mss: false
```

`window_title` 支持匹配可见窗口标题。若按窗口截图出现黑屏，可尝试将 `use_mss` 改为 `true`；使用 MSS 时，被遮挡区域可能会一并采集。

程序运行后，选择 `screen` 类型的源，还可以在界面中输入坐标、鼠标框选区域或恢复全屏，修改会实时生效。

### 本地视频

`video_path` 应指向一个包含 MP4 视频的目录：

```yaml
- type: video_file
  id: video_player
  enable: true
  params:
    video_path: sample_video
    play_mode: list_loop
    playback_rate: 1.0
    auto_crop_center: true
    preview_enabled: true
    # first_play_video: example.mp4
    fps: 30
```

`play_mode` 可设为 `single_loop`（循环单个视频）、`list_loop`（循环列表）或
`random`（列表内随机），`playback_rate` 支持 `0.5`～`2.0` 倍速。
程序运行后选择 `video_file` 源，可以直接选择目录或单个 MP4、单击列表点播，
并查看当前视频、播放进度和可关闭的小窗预览。“保存参数”会把视频路径、播放模式、
倍速、当前首播视频及预览设置写回 `config_stream.yaml`。

使用 Windows 绝对路径时，建议使用单引号或正斜杠，例如：

```yaml
video_path: 'D:\Videos\ESP32'
# 或
video_path: D:/Videos/ESP32
```

路径不存在时程序会尝试回退到仓库自带的 `sample_video` 目录；如果回退目录中也没有 MP4 文件，该源会初始化失败。建议将路径改正确，或先设置 `enable: false`。

### 摄像头

```yaml
- type: camera
  id: webcam
  enable: true
  params:
    camera_idx: 0
    resolution: [1280, 720]
    fps: 25
```

`camera_idx` 一般从 `0` 开始。如果摄像头被其他程序占用，该源可能初始化失败。

### RTSP

```yaml
- type: rtsp
  id: network_camera
  enable: true
  params:
    rtsp_url: rtsp://user:password@192.168.1.100:8554/live
    timeout: 3
    rtsp_transport: tcp
```

程序启动时会连接所有已启用的 RTSP 源。地址不可用会延长启动时间或导致该源初始化失败，因此不使用时请设置 `enable: false`。

## 音频可视化

音频可视化会采集一个录音设备，并将声音转换为频谱、波形、光环、粒子等画面。若只需要共享屏幕或播放视频，可以跳过本节。

### 1. 选择音频来源

程序会在“音频可视化工作台”的“音频来源”下拉框列出所有可录音设备，可在运行中切换并点击“保存参数”记住选择：

- **Mac 系统声音**：安装 [BlackHole](https://existential.audio/blackhole/)，在“音频 MIDI 设置”中创建“多输出设备”，将扬声器/耳机和 BlackHole 一起勾选；随后在本程序中选择 `BlackHole 2ch`。这样既能听到声音，也能做可视化。
- **指定应用或更复杂混音**：可使用 Loopback 等虚拟音频设备，选择它创建的录音输入。
- **麦克风、USB 声卡或线路输入**：直接在下拉框选择相应设备即可。首次使用麦克风时，macOS 可能要求在“隐私与安全性 → 麦克风”中授权终端或应用。
- **Windows 系统声音**：可按下面的 VB-CABLE 方法配置。

如果留空 `target_device`，程序使用操作系统的默认录音设备；程序会自动在设备不支持 48 kHz 时改用其原生采样率。

### 2. Windows：安装并配置 VB-CABLE

1. 安装 [VB-CABLE](https://vb-audio.com/Cable/)；
2. 打开 Windows“设置 → 系统 → 声音”，将播放设备设为 `CABLE Input`；
3. 某些播放器切换输出设备后需要重启；
4. 打开“更多声音设置 → 录制 → CABLE Output → 属性 → 侦听”；
5. 勾选“侦听此设备”，并选择实际扬声器，以便电脑仍能播放声音。

![选择 CABLE Input](cable_input.png)

![侦听 CABLE Output](audio_output_setting.png)

### 3. 配置音频源

```yaml
- type: audio_visualization
  id: audio_visual1
  enable: true
  params:
    # macOS 可填写 BlackHole 2ch；Windows 可填写 CABLE Output；留空则用默认输入。
    target_device: ''
    input:
      gain: 1.0
      noise_gate: 0.0015
      beat_sensitivity: 1.25
    effects:
      spectrum_bars:
        enabled: true
        params:
          bars: 16
          height: 0.7
          smoothing: 0.76
          gap: 2
          glow: 0.7
      particles:
        enabled: true
        params:
          count: 120
          spawn: 0.8
          speed: 1.0
          size: 3.2
          drift: 0.65
```

若找不到 `target_device` 指定的设备，程序会尝试使用系统默认录音设备。更推荐从界面下拉框选择，以避免设备名称不完全一致。

程序中的“音频可视化工作台”可以实时启用、叠加和调整效果。“保存参数”会写回 `config_stream.yaml`；效果组合预设可以保存、应用、覆盖或删除完整的效果组合。

内置效果包括：丝带波形、玻璃频谱、轨道脉冲、棱镜光环、红蓝电离、脉冲隧道、镜像城市、极光丝幕、星芒脉冲、流光瀑布和萤火粒子。完整参数及预设请参考仓库自带的 `config_stream.yaml`。

## 推流参数建议

| 使用场景 | 分辨率 | 色彩 | 每包行数 | 发送间隔 |
| --- | --- | --- | --- | --- |
| 推荐起步配置 | 240 × 240 | RGB332 | 6 | 0.001 s |
| 更好色彩 | 240 × 240 | RGB565 | 3 | 0.00075 s |
| 网络较差 | 180 × 180 | RGB332 | 6 | 0.001 s |

RGB565 色彩更好，但数据量约为 RGB332 的两倍。如果画面花屏、卡顿或丢帧，优先尝试 RGB332、降低分辨率，或适当增大发送间隔。

## 常见问题

### 程序一启动就退出或提示图像源初始化失败

- 将当前运行方式使用的 `config_stream.yaml` 中的 `active_source` 改为 `demo1`；
- 把暂时不用的音频、RTSP、摄像头或视频源设置为 `enable: false`；
- 检查 `video_path`、`window_title` 和 `rtsp_url` 是否有效；
- 使用源码版时，确保从项目根目录运行 `main_ui.py`；
- 重新执行 `uv sync`，确认依赖安装完整。

### 程序在发送，但 ESP32 没有画面

- 确认填写的是 ESP32 IP；
- 确认电脑和 ESP32 位于同一局域网；
- 确认两端 UDP 端口一致，推荐固件默认为 `8888`；
- 允许 Python 通过 Windows 防火墙；
- 先用 `demo1 + 240 × 240 + RGB332` 排除图像源和带宽问题；
- 检查 ESP32 串口日志是否已进入接收状态。

### 截取窗口时画面全黑

- 将该源的 `use_mss` 改为 `true`；
- 尝试窗口化或无边框窗口模式；
- 避免最小化目标窗口；
- 某些使用硬件保护或独占全屏的程序无法通过普通桌面截图接口采集。

### PowerShell 不允许执行激活脚本

使用 `uv run python main_ui.py` 不需要手动激活虚拟环境。使用普通 `venv` 时，也可以直接调用 `.\.venv\Scripts\python.exe`，无需修改 PowerShell 执行策略。

## 开发与测试

运行现有单元测试：

```powershell
uv run python -m unittest discover -s capture -p "test*.py"
```

新增图像源时：

1. 在 `capture/interface.py` 的 `SourceType` 中声明类型；
2. 实现 `ImageSourceInterface` 接口；
3. 在 `capture/source_manager.py` 中注册创建逻辑；
4. 在 `config_stream.yaml` 中添加对应配置；
5. 确保初始化失败时能够释放摄像头、网络连接、音频流等资源。

每个音频效果位于 `capture/audio_visualization_source/effects/` 下。新增效果类并在该目录的 `__init__.py` 中注册后，界面会根据效果元数据自动生成名称、说明、开关和参数控件。

## 项目截图

![ESP32 显示效果](demo.jpg)

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。
