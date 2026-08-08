import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import base64
import yaml
import os
import re
import threading
import time
import sys
import queue
from tkinter import scrolledtext
import tkinter.font as tkfont

# 尝试导入UDP发送相关的模块
try:
    import cv2
    import numpy as np
    from udp_v2 import (
        MODE_RGB332,
        MODE_RGB565,
        MIN_FRAME_RATE_LIMIT,
        V2Sender,
        default_frame_rate_limit,
        migrate_v2_config,
        stream_latest_frames,
        validate_frame_rate_limit,
    )
    from capture.config import (
        delete_audio_preset,
        get_streamer,
        load_active_audio_preset,
        load_audio_presets,
        save_active_audio_preset,
        save_audio_preset,
        save_source_frame_rate,
        save_source_runtime_config,
        save_video_source_config,
    )
    from capture.interface import (
        MAX_SOURCE_FRAME_RATE,
        MIN_SOURCE_FRAME_RATE,
        validate_source_frame_rate,
    )
    streamer = get_streamer()

    # 初始化
    if streamer is None:
        print("Failed to initialize streamer")
    UDP_MODULES_AVAILABLE = True
except ImportError as e:
    UDP_MODULES_AVAILABLE = False
    print(f"警告: 图像源加载配置失败: {e}")
    print("推流功能将不可用")


class YAMLConfigEditor:
    def __init__(self, root):
        print("==================================================================================================================")
        print("欢迎使用ESP32Holocubic ScreenShareUDP推流工具，本项目开源免费，地址是:https://github.com/tignioj/ESP32UDPScreenShareClient")
        print("配置文件路径在_internal/config_stream.yaml, 首次使用请查看README.md")
        print("==================================================================================================================")
        self.root = root
        self.root.title("ESP32 UDP 屏幕推流")
        self.root.geometry("1180x880")
        self.root.minsize(920, 720)

        # UDP推流相关
        self.streaming = False
        self.stream_thread = None
        self.stream_stop_event = None
        # 推流预览只展示已经完整发送的量化帧。发送线程负责发布最新帧，
        # Tk 主线程定时取走并渲染，避免跨线程操作界面控件。
        self.stream_preview_lock = threading.Lock()
        self.stream_preview_frame = None
        self.stream_preview_version = 0
        self.stream_preview_rendered_version = -1
        self.stream_preview_image = None
        self.stream_preview_size = (200, 200)
        self.stream_preview_job = None
        self.stream_preview_info_var = tk.StringVar(value="尚未开始推流")

        # 默认配置文件
        self.config_file = "config.yaml"

        # UDP v2 only supports native 240x240 frames with feedback gating.
        self.presets = {
            "240 高帧率 RGB332": {
                'resolution': 240,
                'color_mode': MODE_RGB332,
                'target_fps': default_frame_rate_limit(MODE_RGB332),
            },
            "240 高画质 RGB565": {
                'resolution': 240,
                'color_mode': MODE_RGB565,
                'target_fps': default_frame_rate_limit(MODE_RGB565),
            }
        }
        self.default_preset_name = "240 高帧率 RGB332"
        self.custom_preset_label = "自定义配置"
        self.builtin_preset_prefix = "内置 · "
        self.personal_preset_prefix = "个人 · "
        self.personal_presets = {}

        # 首次启动没有 config.yaml 时使用高帧率 RGB332。
        default_preset = self.presets[self.default_preset_name]
        self.default_config = {
            'server_ip': "192.168.100.161",
            'server_port': 8888,
            'resolution': [default_preset['resolution'], default_preset['resolution']],
            'color_mode': "rgb565" if default_preset['color_mode'] == MODE_RGB565 else "rgb332",
            'target_fps': default_preset['target_fps'],
            'transport_version': 2,
            'preset': self.default_preset_name,
        }

        # 可选值定义（存储为字符串列表，用于显示）
        self.valid_resolution_strings = ["[240,240]"]
        self.valid_resolution_values = [[240, 240]]

        # UDP v2 固定 240x240，仅色彩模式可选。
        self.valid_values = {
            'resolution': self.valid_resolution_strings,  # 用于下拉框
            'color_mode': ['rgb332', 'rgb565'],
        }

        # 预设变量
        self.preset_var = tk.StringVar(value=self.format_udp_preset_label("builtin", self.default_preset_name))
        self.preset_summary_var = tk.StringVar(value="")
        self.updating_udp_controls = False

        # 图像源选择
        self.source_var = tk.StringVar(value="")
        self.source_id_by_label = {}
        self.source_type_by_id = {}
        self.source_canvas = None
        self.source_content = None
        self.source_window = None
        self.source_fps_var = tk.StringVar(value="30")
        self.updating_source_fps_control = False

        # 屏幕截图源运行时控制。
        self.screen_mode_var = tk.StringVar(value="")
        self.screen_region_vars = {
            name: tk.StringVar(value=value)
            for name, value in zip(('x', 'y', 'width', 'height'), ('0', '0', '240', '240'))
        }

        # 本地视频播放控制和预览。
        self.video_path_var = tk.StringVar(value="")
        self.video_play_mode_var = tk.StringVar(value="循环列表")
        self.video_playback_rate_var = tk.DoubleVar(value=1.0)
        self.video_playback_rate_text_var = tk.StringVar(value="1.0×")
        self.video_now_playing_var = tk.StringVar(value="尚未播放")
        self.video_progress_var = tk.DoubleVar(value=0.0)
        self.video_progress_text_var = tk.StringVar(value="00:00 / 00:00")
        self.video_preview_enabled_var = tk.BooleanVar(value=True)
        self.video_list_items = {}
        self.video_list_signature = ()
        self.video_preview_image = None
        self.video_preview_size = (360, 240)
        self.video_refresh_job = None
        self.video_idle_playback_job = None
        self.updating_video_controls = False

        # 音频效果和参数完全由各效果模块提供，UI 不再维护重复常量。
        self.audio_effect_catalog = []
        self.audio_effect_meta = {}
        self.audio_effect_label_to_id = {}
        self.audio_effect_config = {}
        self.audio_input_catalog = []
        self.audio_device_label_to_name = {"系统默认输入": ""}
        self.audio_selected_device_var = tk.StringVar(value="系统默认输入")
        self.audio_selected_effect_var = tk.StringVar(value="")
        self.audio_selected_effect_enabled_var = tk.BooleanVar(value=False)
        self.audio_effect_description_var = tk.StringVar(value="")
        self.audio_enabled_summary_var = tk.StringVar(value="尚未加载效果")
        self.audio_preset_var = tk.StringVar(value="")
        self.audio_presets = {}
        self.audio_input_vars = {}
        self.audio_input_value_vars = {}
        self.audio_effect_parameter_vars = {}
        self.audio_effect_parameter_value_vars = {}
        self.updating_audio_controls = False

        # 音频可视化可以脱离 UDP 推流，以无边框透明悬浮窗独立运行。
        # 帧生成留在后台线程，Tk 主线程只负责交换已经编码好的 PNG。
        self.audio_overlay_fps_var = tk.StringVar(value="30")
        self.audio_overlay_status_var = tk.StringVar(value="独立窗口未运行")
        self.audio_overlay_frame_rate = 30.0
        self.audio_overlay_running = False
        self.audio_overlay_source_id = None
        self.audio_overlay_window = None
        self.audio_overlay_label = None
        self.audio_overlay_image = None
        self.audio_overlay_thread = None
        self.audio_overlay_stop_event = None
        self.audio_overlay_refresh_job = None
        self.audio_overlay_lock = threading.Lock()
        self.audio_overlay_png = None
        self.audio_overlay_version = 0
        self.audio_overlay_rendered_version = -1
        self.audio_overlay_size = 480
        self.audio_overlay_drag_origin = None
        self.audio_overlay_error = None

        # 日志文本框
        self.log_text = None
        # Tk 控件只能在主线程访问。推流线程把日志放入队列，由主线程刷新。
        self.log_queue = queue.Queue()
        self.ui_action_queue = queue.Queue()
        self.log_flush_job = None

        self.setup_ui()
        self.refresh_source_list()
        self.load_config()
        self.video_refresh_job = self.root.after(200, self.update_video_playback_status)
        self.video_idle_playback_job = self.root.after(15, self.drive_video_when_not_streaming)
        self.stream_preview_job = self.root.after(100, self.update_stream_preview)
        self.log_flush_job = self.root.after(100, self.flush_log_messages)

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # 两层配置分别放到页签中，避免发送参数和图像源参数混在一起。
        config_notebook = ttk.Notebook(main_frame)
        config_notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        udp_tab = ttk.Frame(config_notebook, padding=12)
        source_tab = ttk.Frame(config_notebook, padding=12)
        config_notebook.add(udp_tab, text="  1  UDP 发送配置  ")
        config_notebook.add(source_tab, text="  2  图像源配置  ")
        udp_tab.columnconfigure(0, weight=1)
        source_tab.columnconfigure(0, weight=1)
        source_tab.rowconfigure(0, weight=1)

        self.source_canvas = tk.Canvas(source_tab, highlightthickness=0, height=500)
        source_scrollbar = ttk.Scrollbar(
            source_tab,
            orient=tk.VERTICAL,
            command=self.source_canvas.yview,
        )
        self.source_canvas.configure(yscrollcommand=source_scrollbar.set)
        self.source_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        source_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.source_content = ttk.Frame(self.source_canvas)
        self.source_content.columnconfigure(0, weight=1)
        self.source_window = self.source_canvas.create_window(
            (0, 0),
            window=self.source_content,
            anchor=tk.NW,
        )
        self.source_content.bind("<Configure>", self.on_source_content_configure)
        self.source_canvas.bind("<Configure>", self.on_source_canvas_configure)

        def scroll_source(event):
            # 动态面板比视口矮时不应保留或产生任何纵向偏移。
            if self.source_content.winfo_reqheight() <= self.source_canvas.winfo_height():
                self.source_canvas.yview_moveto(0)
                return "break"
            self.source_canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"

        self.source_canvas.bind(
            "<Enter>",
            lambda event: self.source_canvas.bind_all("<MouseWheel>", scroll_source),
        )
        self.source_canvas.bind(
            "<Leave>",
            lambda event: self.source_canvas.unbind_all("<MouseWheel>"),
        )

        ttk.Label(
            udp_tab,
            text="先选择适合接收端和网络的发送预设，再填写 ESP32 的地址。",
            foreground="#555555",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        preset_frame = ttk.LabelFrame(udp_tab, text="发送预设", padding=10)
        preset_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        preset_frame.columnconfigure(1, weight=1)
        ttk.Label(preset_frame, text="UDP 预设:").grid(row=0, column=0, sticky=tk.W)
        self.preset_combo = ttk.Combobox(
            preset_frame,
            textvariable=self.preset_var,
            values=self.get_udp_preset_labels(),
            state="readonly",
            width=30,
        )
        self.preset_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(8, 0))
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_udp_preset_selected)
        preset_buttons = ttk.Frame(preset_frame)
        preset_buttons.grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0))
        ttk.Button(
            preset_buttons,
            text="保存为个人预设",
            command=self.save_personal_udp_preset,
        ).pack(side=tk.LEFT)
        ttk.Button(
            preset_buttons,
            text="删除个人预设",
            command=self.delete_personal_udp_preset,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            preset_frame,
            textvariable=self.preset_summary_var,
            foreground="#356a8a",
        ).grid(row=2, column=1, sticky=tk.W, padx=(8, 0), pady=(5, 0))
        ttk.Label(
            preset_frame,
            text="内置预设只读；个人预设可保存多份完整 UDP 配置。",
            foreground="#777777",
        ).grid(row=3, column=1, sticky=tk.W, padx=(8, 0), pady=(4, 0))

        destination_frame = ttk.LabelFrame(udp_tab, text="接收端", padding=10)
        destination_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        destination_frame.columnconfigure(1, weight=1)
        destination_frame.columnconfigure(3, weight=1)

        # 创建配置项输入框
        self.entries = {}
        ttk.Label(destination_frame, text="ESP32 IP:").grid(row=0, column=0, sticky=tk.W)
        self.entries['server_ip'] = ttk.Entry(destination_frame, width=24)
        self.entries['server_ip'].grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(8, 20))
        ttk.Label(destination_frame, text="UDP 端口:").grid(row=0, column=2, sticky=tk.W)
        self.entries['server_port'] = ttk.Entry(destination_frame, width=12)
        self.entries['server_port'].grid(row=0, column=3, sticky=(tk.W, tk.E), padx=(8, 0))

        transport_frame = ttk.LabelFrame(udp_tab, text="传输参数", padding=10)
        transport_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        transport_frame.columnconfigure(1, weight=1)
        transport_frame.columnconfigure(3, weight=1)

        ttk.Label(transport_frame, text="输出分辨率:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.entries['resolution'] = ttk.Combobox(
            transport_frame,
            values=self.valid_resolution_strings,
            width=13,
            state="readonly",
        )
        self.entries['resolution'].grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(8, 20), pady=3)
        ttk.Label(transport_frame, text="色彩模式:").grid(row=0, column=2, sticky=tk.W, pady=3)
        self.entries['color_mode'] = ttk.Combobox(
            transport_frame,
            values=self.valid_values['color_mode'],
            width=13,
            state="readonly",
        )
        self.entries['color_mode'].grid(row=0, column=3, sticky=(tk.W, tk.E), padx=(8, 0), pady=3)

        ttk.Label(transport_frame, text="目标发送 FPS:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.entries['target_fps'] = ttk.Spinbox(
            transport_frame,
            from_=MIN_FRAME_RATE_LIMIT,
            to=default_frame_rate_limit(MODE_RGB332),
            increment=0.5,
            width=13,
            command=self.on_udp_parameter_edited,
        )
        self.entries['target_fps'].grid(
            row=1, column=1, sticky=(tk.W, tk.E), padx=(8, 20), pady=3
        )

        ttk.Label(
            transport_frame,
            text="目标 FPS 控制整帧发送节奏；RGB332 上限 47，RGB565 上限 25.5。",
            foreground="#777777",
        ).grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))

        self.entries['resolution'].bind("<<ComboboxSelected>>", self.on_udp_parameter_edited)
        self.entries['color_mode'].bind("<<ComboboxSelected>>", self.on_color_mode_edited)
        self.entries['target_fps'].bind("<KeyRelease>", self.on_udp_parameter_edited)
        self.entries['target_fps'].bind("<FocusOut>", self.on_udp_parameter_edited)
        for key in ('server_ip', 'server_port'):
            self.entries[key].bind("<KeyRelease>", self.on_udp_parameter_edited)

        ttk.Label(
            self.source_content,
            text="选择画面来源；不同来源的专属参数会显示在下方。",
            foreground="#555555",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        # 图像源切换
        source_frame = ttk.LabelFrame(self.source_content, text="图像源", padding=10)
        source_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        source_frame.columnconfigure(1, weight=1)

        ttk.Label(source_frame, text="当前源:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.source_combo = ttk.Combobox(
            source_frame,
            textvariable=self.source_var,
            state="readonly",
            width=42
        )
        self.source_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        self.source_combo.bind("<<ComboboxSelected>>", self.on_source_selected)

        self.switch_source_button = ttk.Button(
            source_frame,
            text="切换",
            command=self.switch_source
        )
        self.switch_source_button.grid(row=0, column=2, padx=(5, 0))

        source_fps_frame = ttk.Frame(source_frame)
        source_fps_frame.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky=(tk.W, tk.E),
            pady=(8, 0),
        )
        source_fps_frame.columnconfigure(1, weight=1)
        ttk.Label(source_fps_frame, text="图像源 FPS:").grid(row=0, column=0, sticky=tk.W)
        self.source_fps_spinbox = ttk.Spinbox(
            source_fps_frame,
            from_=MIN_SOURCE_FRAME_RATE,
            to=MAX_SOURCE_FRAME_RATE,
            increment=1,
            textvariable=self.source_fps_var,
            width=10,
            command=self.apply_source_frame_rate,
        )
        self.source_fps_spinbox.grid(row=0, column=1, sticky=tk.W, padx=(8, 8))
        self.source_fps_spinbox.bind('<Return>', self.apply_source_frame_rate)
        self.source_fps_apply_button = ttk.Button(
            source_fps_frame,
            text="应用并保存",
            command=self.apply_source_frame_rate,
        )
        self.source_fps_apply_button.grid(row=0, column=2, sticky=tk.E)
        ttk.Label(
            source_fps_frame,
            text="控制当前图像源的采集/生成频率；UDP 发送帧率在发送配置页单独设置。",
            foreground="#777777",
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))

        # 仅在选中 screen 源时显示，修改后直接作用于运行中的截图源。
        self.screen_controls_frame = ttk.LabelFrame(source_frame, text="截图区域（实时生效）", padding="6")
        self.screen_controls_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 0))
        self.screen_controls_frame.columnconfigure(1, weight=1)

        ttk.Label(self.screen_controls_frame, text="当前模式:").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(self.screen_controls_frame, textvariable=self.screen_mode_var, width=12).grid(
            row=0, column=1, sticky=tk.W, padx=(5, 15)
        )

        screen_button_frame = ttk.Frame(self.screen_controls_frame)
        screen_button_frame.grid(row=0, column=2, sticky=tk.E)
        ttk.Button(
            screen_button_frame,
            text="应用区域",
            command=self.apply_screen_region,
        ).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(
            screen_button_frame,
            text="鼠标框选",
            command=self.select_screen_region,
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(
            screen_button_frame,
            text="恢复全屏",
            command=self.use_full_screen,
        ).pack(side=tk.LEFT, padx=(3, 0))

        region_input_frame = ttk.Frame(self.screen_controls_frame)
        region_input_frame.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(7, 0))
        ttk.Label(region_input_frame, text="坐标与尺寸:").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        region_labels = (('x', 'X'), ('y', 'Y'), ('width', '宽'), ('height', '高'))
        for index, (name, label) in enumerate(region_labels):
            column = 1 + index * 2
            ttk.Label(region_input_frame, text=f"{label}:").grid(row=0, column=column, sticky=tk.E)
            entry = ttk.Entry(
                region_input_frame,
                textvariable=self.screen_region_vars[name],
                width=7,
            )
            entry.grid(row=0, column=column + 1, sticky=tk.W, padx=(3, 10))
            entry.bind('<Return>', lambda event: self.apply_screen_region())
        self.screen_controls_frame.grid_remove()

        # 仅在选中 video_file 源时显示，播放参数可实时应用并保存。
        self.video_controls_frame = ttk.LabelFrame(source_frame, text="本地视频播放", padding="8")
        self.video_controls_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 0))
        self.video_controls_frame.columnconfigure(1, weight=1)

        ttk.Label(self.video_controls_frame, text="视频路径:").grid(row=0, column=0, sticky=tk.W)
        video_path_entry = ttk.Entry(self.video_controls_frame, textvariable=self.video_path_var)
        video_path_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(6, 6))
        video_path_entry.bind('<Return>', lambda event: self.apply_video_settings(include_path=True))
        video_path_buttons = ttk.Frame(self.video_controls_frame)
        video_path_buttons.grid(row=0, column=2, sticky=tk.E)
        ttk.Button(video_path_buttons, text="选择目录", command=self.choose_video_directory).pack(side=tk.LEFT)
        ttk.Button(video_path_buttons, text="选择视频", command=self.choose_video_file).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(video_path_buttons, text="刷新目录", command=self.refresh_video_directory).pack(side=tk.LEFT, padx=(6, 0))

        playback_settings = ttk.Frame(self.video_controls_frame)
        playback_settings.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 6))
        playback_settings.columnconfigure(3, weight=1)
        ttk.Label(playback_settings, text="播放模式:").grid(row=0, column=0, sticky=tk.W)
        self.video_play_mode_combo = ttk.Combobox(
            playback_settings,
            textvariable=self.video_play_mode_var,
            values=("循环单个视频", "循环列表", "列表内随机"),
            state="readonly",
            width=14,
        )
        self.video_play_mode_combo.grid(row=0, column=1, sticky=tk.W, padx=(6, 18))
        self.video_play_mode_combo.bind(
            '<<ComboboxSelected>>',
            lambda event: self.apply_video_settings(),
        )
        ttk.Label(playback_settings, text="播放速率:").grid(row=0, column=2, sticky=tk.W)
        self.video_rate_scale = ttk.Scale(
            playback_settings,
            from_=0.5,
            to=2.0,
            variable=self.video_playback_rate_var,
            command=self.on_video_rate_changed,
        )
        self.video_rate_scale.grid(row=0, column=3, sticky=(tk.W, tk.E), padx=(6, 6))
        self.video_rate_scale.bind('<ButtonRelease-1>', lambda event: self.apply_video_settings())
        ttk.Label(
            playback_settings,
            textvariable=self.video_playback_rate_text_var,
            width=5,
        ).grid(row=0, column=4, sticky=tk.W)
        ttk.Checkbutton(
            playback_settings,
            text="显示预览",
            variable=self.video_preview_enabled_var,
            command=self.toggle_video_preview,
        ).grid(row=0, column=5, padx=(10, 6))
        ttk.Button(
            playback_settings,
            text="保存参数",
            command=self.save_video_config,
        ).grid(row=0, column=6)

        video_status_frame = ttk.Frame(self.video_controls_frame)
        video_status_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 6))
        video_status_frame.columnconfigure(0, weight=1)
        ttk.Label(
            video_status_frame,
            textvariable=self.video_now_playing_var,
            foreground="#356a8a",
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            video_status_frame,
            textvariable=self.video_progress_text_var,
        ).grid(row=0, column=1, sticky=tk.E)
        ttk.Progressbar(
            video_status_frame,
            variable=self.video_progress_var,
            maximum=100.0,
        ).grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(4, 0))

        video_content = ttk.Frame(self.video_controls_frame)
        video_content.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E))
        video_content.columnconfigure(0, weight=1)
        list_frame = ttk.LabelFrame(video_content, text="视频列表（单击立即播放）", padding=4)
        list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        tree_style = ttk.Style(self.root)
        tree_font = tree_style.lookup('Treeview', 'font') or 'TkDefaultFont'
        tree_line_height = tkfont.Font(root=self.root, font=tree_font).metrics('linespace')
        tree_style.configure(
            'Video.Treeview',
            rowheight=max(24, tree_line_height + 6),
        )
        self.video_list = ttk.Treeview(
            list_frame,
            show='tree',
            height=7,
            selectmode='browse',
            style='Video.Treeview',
        )
        self.video_list.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        video_list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.video_list.yview)
        video_list_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.video_list.configure(yscrollcommand=video_list_scrollbar.set)
        self.video_list.bind('<<TreeviewSelect>>', self.on_video_list_selected)

        self.video_preview_frame = ttk.LabelFrame(video_content, text="播放预览", padding=4)
        self.video_preview_frame.grid(row=0, column=1, sticky=(tk.N, tk.E))
        preview_surface = ttk.Frame(
            self.video_preview_frame,
            width=self.video_preview_size[0],
            height=self.video_preview_size[1],
        )
        preview_surface.pack()
        preview_surface.pack_propagate(False)
        self.video_preview_label = tk.Label(
            preview_surface,
            text="等待视频画面",
            bg="#111111",
            fg="#dddddd",
        )
        self.video_preview_label.pack(fill=tk.BOTH, expand=True)
        ttk.Button(
            self.video_preview_frame,
            text="关闭预览",
            command=self.close_video_preview,
        ).pack(anchor=tk.E, pady=(4, 0))
        self.video_controls_frame.grid_remove()

        # 音频工作台由效果模块的元数据动态生成。
        self.audio_controls_frame = ttk.LabelFrame(source_frame, text="音频可视化工作台（实时生效）", padding="8")
        self.audio_controls_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 0))
        self.audio_controls_frame.columnconfigure(0, weight=1)

        device_toolbar = ttk.Frame(self.audio_controls_frame)
        device_toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        device_toolbar.columnconfigure(1, weight=1)
        ttk.Label(device_toolbar, text="音频来源:").grid(row=0, column=0, sticky=tk.W)
        self.audio_device_combo = ttk.Combobox(
            device_toolbar,
            textvariable=self.audio_selected_device_var,
            state="readonly",
            width=42,
        )
        self.audio_device_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(6, 0))
        self.audio_device_combo.bind("<<ComboboxSelected>>", self.on_audio_device_selected)

        effect_toolbar = ttk.Frame(self.audio_controls_frame)
        effect_toolbar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        effect_toolbar.columnconfigure(1, weight=1)
        ttk.Label(effect_toolbar, text="编辑效果:").grid(row=0, column=0, sticky=tk.W)
        self.audio_effect_combo = ttk.Combobox(
            effect_toolbar,
            textvariable=self.audio_selected_effect_var,
            state="readonly",
            width=20,
        )
        self.audio_effect_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(6, 10))
        self.audio_effect_combo.bind("<<ComboboxSelected>>", self.on_audio_effect_selected)
        ttk.Checkbutton(
            effect_toolbar,
            text="启用当前效果",
            variable=self.audio_selected_effect_enabled_var,
            command=self.on_audio_effect_enabled_changed,
        ).grid(row=0, column=2, padx=(0, 8))
        effect_button_frame = ttk.Frame(effect_toolbar)
        effect_button_frame.grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=(6, 0))
        ttk.Button(
            effect_button_frame,
            text="仅用当前",
            command=self.enable_only_current_audio_effect,
        ).pack(side=tk.LEFT)
        ttk.Button(
            effect_button_frame,
            text="重置参数",
            command=self.reset_current_audio_effect,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            effect_button_frame,
            text="全部关闭",
            command=self.disable_all_audio_effects,
        ).pack(side=tk.LEFT)

        ttk.Label(
            self.audio_controls_frame,
            textvariable=self.audio_effect_description_var,
            foreground="#666666",
            wraplength=680,
        ).grid(row=2, column=0, sticky=tk.W, pady=(5, 1))
        audio_summary_frame = ttk.Frame(self.audio_controls_frame)
        audio_summary_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        audio_summary_frame.columnconfigure(0, weight=1)
        ttk.Label(
            audio_summary_frame,
            textvariable=self.audio_enabled_summary_var,
            foreground="#356a8a",
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Button(
            audio_summary_frame,
            text="保存参数",
            command=self.save_audio_config,
        ).grid(row=0, column=1, sticky=tk.E)

        standalone_frame = ttk.LabelFrame(
            self.audio_controls_frame,
            text="独立透明窗口",
            padding=(8, 5),
        )
        standalone_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(2, 7))
        standalone_frame.columnconfigure(5, weight=1)
        self.audio_overlay_start_button = ttk.Button(
            standalone_frame,
            text="启动独立窗口",
            command=self.start_audio_overlay,
        )
        self.audio_overlay_start_button.grid(row=0, column=0, padx=(0, 6))
        self.audio_overlay_stop_button = ttk.Button(
            standalone_frame,
            text="关闭",
            command=self.stop_audio_overlay,
            state=tk.DISABLED,
        )
        self.audio_overlay_stop_button.grid(row=0, column=1, padx=(0, 14))
        ttk.Label(standalone_frame, text="窗口 FPS:").grid(row=0, column=2, sticky=tk.W)
        self.audio_overlay_fps_spinbox = ttk.Spinbox(
            standalone_frame,
            from_=MIN_SOURCE_FRAME_RATE,
            to=MAX_SOURCE_FRAME_RATE,
            increment=1,
            textvariable=self.audio_overlay_fps_var,
            width=8,
            command=self.apply_audio_overlay_frame_rate,
        )
        self.audio_overlay_fps_spinbox.grid(row=0, column=3, padx=(6, 6))
        self.audio_overlay_fps_spinbox.bind('<Return>', self.apply_audio_overlay_frame_rate)
        ttk.Button(
            standalone_frame,
            text="应用并保存",
            command=self.apply_audio_overlay_frame_rate,
        ).grid(row=0, column=4, padx=(0, 10))
        ttk.Label(
            standalone_frame,
            textvariable=self.audio_overlay_status_var,
            foreground="#356a8a",
        ).grid(row=0, column=5, sticky=tk.W)
        ttk.Label(
            standalone_frame,
            text="无需开始 UDP 推流；拖动窗口可移动，滚轮缩放，右键或 Esc 关闭。效果预设仍在下方管理。",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(5, 0))

        parameter_columns = ttk.Frame(self.audio_controls_frame)
        parameter_columns.grid(row=5, column=0, sticky=(tk.W, tk.E))
        parameter_columns.columnconfigure(0, weight=1, uniform="audio_settings")
        parameter_columns.columnconfigure(1, weight=1, uniform="audio_settings")

        input_frame = ttk.LabelFrame(parameter_columns, text="输入分析（全局）", padding=(8, 5))
        input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 4))
        input_frame.columnconfigure(0, weight=1)
        ttk.Label(
            input_frame,
            text="只负责采集和节拍检测，不包含任何画面参数。",
            foreground="#666666",
            wraplength=300,
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        self.audio_input_parameters_frame = ttk.Frame(input_frame)
        self.audio_input_parameters_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.audio_input_parameters_frame.columnconfigure(1, weight=1)

        effect_frame = ttk.LabelFrame(parameter_columns, text="当前效果专属参数", padding=(8, 5))
        effect_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(4, 0))
        effect_frame.columnconfigure(0, weight=1)
        self.audio_effect_parameters_frame = ttk.Frame(effect_frame)
        self.audio_effect_parameters_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.audio_effect_parameters_frame.columnconfigure(1, weight=1)

        audio_preset_frame = ttk.LabelFrame(
            self.audio_controls_frame,
            text="效果组合预设",
            padding=(8, 5),
        )
        audio_preset_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=(7, 0))
        audio_preset_frame.columnconfigure(1, weight=1)
        ttk.Label(audio_preset_frame, text="预设:").grid(row=0, column=0, sticky=tk.W)
        self.audio_preset_combo = ttk.Combobox(
            audio_preset_frame,
            textvariable=self.audio_preset_var,
            state="readonly",
            width=24,
        )
        self.audio_preset_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(6, 8))
        self.audio_preset_combo.bind("<<ComboboxSelected>>", self.on_audio_preset_selected)
        audio_preset_buttons = ttk.Frame(audio_preset_frame)
        audio_preset_buttons.grid(row=1, column=1, sticky=tk.W, pady=(6, 0))
        ttk.Button(
            audio_preset_buttons,
            text="应用",
            command=self.apply_audio_preset,
        ).pack(side=tk.LEFT)
        ttk.Button(
            audio_preset_buttons,
            text="保存当前组合",
            command=self.save_current_audio_preset,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            audio_preset_buttons,
            text="删除",
            command=self.delete_selected_audio_preset,
        ).pack(side=tk.LEFT)
        ttk.Label(
            audio_preset_frame,
            text="选择后会立即应用并记住，下次启动自动恢复。",
            foreground="#666666",
        ).grid(row=2, column=1, sticky=tk.W, pady=(5, 0))

        self.audio_controls_frame.grid_remove()

        # 推流控制独立于两层配置，切换页签后仍然可见。
        stream_frame = ttk.LabelFrame(main_frame, text="推流控制", padding=8)
        stream_frame.grid(row=0, column=1, sticky=(tk.N, tk.E), padx=(10, 0))
        stream_frame.columnconfigure(0, weight=1)

        stream_controls = ttk.Frame(stream_frame)
        stream_controls.grid(row=0, column=0, sticky=(tk.W, tk.E))

        stream_buttons = ttk.Frame(stream_controls)
        stream_buttons.pack(anchor=tk.W)

        self.start_button = ttk.Button(stream_buttons, text="开始推流",
                                       command=self.start_streaming,
                                       state=tk.NORMAL if UDP_MODULES_AVAILABLE else tk.DISABLED)
        self.start_button.pack(side=tk.LEFT)

        self.stop_button = ttk.Button(stream_buttons, text="停止推流",
                                      command=self.stop_streaming,
                                      state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=8)

        ttk.Label(
            stream_controls,
            textvariable=self.stream_preview_info_var,
            foreground="#555555",
        ).pack(anchor=tk.W, pady=(10, 4))
        ttk.Label(
            stream_controls,
            text="预览显示完成缩放和色彩量化后、实际通过 UDP 发送的画面。",
            foreground="#777777",
            wraplength=200,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        stream_preview_frame = ttk.LabelFrame(stream_frame, text="当前推送画面", padding=4)
        stream_preview_frame.grid(row=1, column=0, sticky=(tk.N, tk.E), pady=(10, 0))
        stream_preview_surface = ttk.Frame(
            stream_preview_frame,
            width=self.stream_preview_size[0],
            height=self.stream_preview_size[1],
        )
        stream_preview_surface.pack()
        stream_preview_surface.pack_propagate(False)
        self.stream_preview_label = tk.Label(
            stream_preview_surface,
            text="等待开始推流",
            bg="#161616",
            fg="#aaaaaa",
        )
        self.stream_preview_label.pack(fill=tk.BOTH, expand=True)

        # 添加日志显示区域
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=4, width=58)
        self.log_text.pack(expand=True, fill=tk.BOTH)
        self.log_text.config(state=tk.DISABLED)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        # 配置网格权重
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # 如果没有UDP模块，显示警告
        if not UDP_MODULES_AVAILABLE:
            self.log_message("警告: UDP推流模块不可用，请确保安装了必要的依赖库")
            self.log_message("需要安装: pip install opencv-python numpy mss")

    def refresh_source_scroll_layout(self, reset_to_top=False):
        """让图像源滚动区贴合当前可见配置，避免切换后残留旧偏移。"""
        canvas = self.source_canvas
        content = self.source_content
        if canvas is None or content is None or self.source_window is None:
            return

        canvas_width = max(canvas.winfo_width(), 1)
        viewport_height = max(canvas.winfo_height(), 1)
        content_height = max(content.winfo_reqheight(), 1)
        scroll_height = max(content_height, viewport_height)

        canvas.itemconfigure(self.source_window, width=canvas_width)
        canvas.configure(scrollregion=(0, 0, canvas_width, scroll_height))

        if reset_to_top or content_height <= viewport_height:
            canvas.yview_moveto(0)
            return

        # 内容在当前配置变化后仍超过一屏时，也要把旧位置限制在新的底部以内。
        current_top = canvas.canvasy(0)
        maximum_top = content_height - viewport_height
        if current_top < 0:
            canvas.yview_moveto(0)
        elif current_top > maximum_top:
            canvas.yview_moveto(maximum_top / scroll_height)

    def on_source_content_configure(self, event=None):
        self.refresh_source_scroll_layout()

    def on_source_canvas_configure(self, event=None):
        self.refresh_source_scroll_layout()

    def reset_source_scroll_position(self):
        """等所有动态面板完成 grid 更新后，将新来源从顶部显示。"""
        self.root.after_idle(lambda: self.refresh_source_scroll_layout(reset_to_top=True))

    def refresh_source_list(self):
        """把 config_stream.yaml 中成功加载的源显示到下拉框。"""
        self.source_id_by_label.clear()
        self.source_type_by_id.clear()

        if not UDP_MODULES_AVAILABLE or streamer is None:
            self.source_combo.configure(values=(), state=tk.DISABLED)
            self.switch_source_button.configure(state=tk.DISABLED)
            self.set_source_fps_control_enabled(False)
            self.screen_controls_frame.grid_remove()
            self.video_controls_frame.grid_remove()
            self.audio_controls_frame.grid_remove()
            return

        try:
            sources = streamer.list_configured_sources()
            labels = []
            active_label = None

            for source in sources:
                label = f"{source['id']} ({source['type']})"
                labels.append(label)
                self.source_id_by_label[label] = source['id']
                self.source_type_by_id[source['id']] = source['type']
                if source.get('active'):
                    active_label = label

            self.source_combo.configure(values=labels)
            if labels:
                self.source_combo.configure(state="readonly")
                self.switch_source_button.configure(state=tk.NORMAL)
                self.source_var.set(active_label or labels[0])
                self.refresh_source_fps_control()
                self.refresh_screen_controls()
                self.refresh_video_controls()
                self.refresh_audio_controls()
                self.reset_source_scroll_position()
            else:
                self.source_combo.configure(state=tk.DISABLED)
                self.switch_source_button.configure(state=tk.DISABLED)
                self.source_var.set("")
                self.set_source_fps_control_enabled(False)
                self.screen_controls_frame.grid_remove()
                self.video_controls_frame.grid_remove()
                self.audio_controls_frame.grid_remove()
                self.log_message("没有成功加载的图像源，请检查 config_stream.yaml")
        except Exception as e:
            self.source_combo.configure(values=(), state=tk.DISABLED)
            self.switch_source_button.configure(state=tk.DISABLED)
            self.set_source_fps_control_enabled(False)
            self.screen_controls_frame.grid_remove()
            self.video_controls_frame.grid_remove()
            self.audio_controls_frame.grid_remove()
            self.log_message(f"读取图像源失败: {str(e)}")

    def on_source_selected(self, event=None):
        """选择下拉项后立即切换。"""
        self.switch_source()

    def switch_source(self):
        """切换 streamer 当前使用的图像源，推流中也可调用。"""
        label = self.source_var.get()
        source_id = self.source_id_by_label.get(label)
        if not source_id:
            messagebox.showwarning("提示", "请先选择一个图像源")
            return

        try:
            if streamer.switch_source(source_id):
                self.log_message(f"已切换图像源: {source_id}")
                self.status_var.set(f"当前图像源: {source_id}")
                self.refresh_source_fps_control()
                self.refresh_screen_controls()
                self.refresh_video_controls()
                self.refresh_audio_controls()
                self.reset_source_scroll_position()
            else:
                messagebox.showerror("错误", f"图像源不存在或不可用: {source_id}")
                self.refresh_source_list()
        except Exception as e:
            messagebox.showerror("错误", f"切换图像源失败: {str(e)}")
            self.log_message(f"切换图像源失败: {str(e)}")

    def get_selected_source_id(self):
        return self.source_id_by_label.get(self.source_var.get())

    def set_source_fps_control_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.source_fps_spinbox.configure(state=state)
        self.source_fps_apply_button.configure(state=state)

    def refresh_source_fps_control(self):
        """Load the selected source's runtime FPS into the shared control."""
        source_id = self.get_selected_source_id()
        if not source_id or streamer is None:
            self.set_source_fps_control_enabled(False)
            return

        self.updating_source_fps_control = True
        try:
            frame_rate = streamer.get_source_frame_rate(source_id)
            self.source_fps_var.set(f"{frame_rate:g}")
            if self.source_type_by_id.get(source_id) == 'audio_visualization':
                self.audio_overlay_frame_rate = frame_rate
                self.audio_overlay_fps_var.set(f"{frame_rate:g}")
            self.set_source_fps_control_enabled(True)
        except Exception as e:
            self.set_source_fps_control_enabled(False)
            self.log_message(f"读取图像源帧率失败: {str(e)}")
        finally:
            self.updating_source_fps_control = False

    def apply_source_frame_rate(self, event=None):
        """Apply and persist the selected source's capture/render cadence."""
        if self.updating_source_fps_control:
            return False
        source_id = self.get_selected_source_id()
        if not source_id or streamer is None:
            return False

        try:
            frame_rate = validate_source_frame_rate(self.source_fps_var.get())
            previous_rate = streamer.get_source_frame_rate(source_id)
            applied_rate = streamer.set_source_frame_rate(frame_rate, source_id)
            try:
                save_source_frame_rate(source_id, applied_rate)
            except Exception:
                streamer.set_source_frame_rate(previous_rate, source_id)
                raise
            self.source_fps_var.set(f"{applied_rate:g}")
            if self.source_type_by_id.get(source_id) == 'audio_visualization':
                self.audio_overlay_frame_rate = applied_rate
                self.audio_overlay_fps_var.set(f"{applied_rate:g}")
            self.status_var.set(f"图像源 FPS: {applied_rate:g}")
            self.log_message(
                f"已更新图像源 {source_id} 的帧率: {applied_rate:g} FPS"
            )
            return True
        except Exception as e:
            messagebox.showerror("图像源帧率无效", str(e))
            self.refresh_source_fps_control()
            return False

    def refresh_screen_controls(self):
        """按当前屏幕源的真实运行时参数刷新区域控制面板。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'screen':
            self.screen_controls_frame.grid_remove()
            return

        try:
            info = streamer.get_source_info(source_id)
            mode = info.get('capture_mode', 'display')
            mode_labels = {'display': '全屏', 'window': '窗口', 'region': '区域'}
            self.screen_mode_var.set(mode_labels.get(mode, mode))

            region = info.get('region')
            if not region:
                resolution = info.get('resolution', (240, 240))
                region = (0, 0, resolution[0], resolution[1])
            for name, value in zip(('x', 'y', 'width', 'height'), region):
                self.screen_region_vars[name].set(str(int(value)))
            self.screen_controls_frame.grid()
        except Exception as e:
            self.screen_controls_frame.grid_remove()
            self.log_message(f"读取截图参数失败: {str(e)}")

    def get_screen_region_inputs(self):
        try:
            region = [
                int(self.screen_region_vars[name].get())
                for name in ('x', 'y', 'width', 'height')
            ]
        except ValueError as e:
            raise ValueError("X、Y、宽和高都必须是整数") from e
        if region[2] <= 0 or region[3] <= 0:
            raise ValueError("宽和高必须大于 0")
        return region

    def apply_screen_region(self):
        """把输入的矩形区域立即应用到选中的屏幕源。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'screen':
            return
        try:
            region = self.get_screen_region_inputs()
            if not streamer.set_source_config(
                {'capture_mode': 'region', 'region': region},
                source_id,
            ):
                raise ValueError("截图源拒绝了该区域")
            self.screen_mode_var.set("区域")
            self.status_var.set(f"截图区域: {region[0]}, {region[1]}, {region[2]} × {region[3]}")
            self.log_message(f"已更新截图区域: {region}")
        except Exception as e:
            messagebox.showerror("截图区域无效", str(e))
            self.refresh_screen_controls()

    def use_full_screen(self):
        """让选中的屏幕源恢复显示器全屏截图。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'screen':
            return
        try:
            if not streamer.set_source_config({'capture_mode': 'display'}, source_id):
                raise ValueError("截图源无法切换到全屏模式")
            self.status_var.set("截图源已恢复全屏")
            self.log_message("截图源已恢复全屏")
            self.refresh_screen_controls()
        except Exception as e:
            messagebox.showerror("切换失败", str(e))

    def get_virtual_screen_bounds(self):
        """返回整个虚拟桌面的坐标，支持副屏位于主屏左侧或上方。"""
        if sys.platform == 'win32':
            import ctypes
            user32 = ctypes.windll.user32
            return (
                user32.GetSystemMetrics(76),
                user32.GetSystemMetrics(77),
                user32.GetSystemMetrics(78),
                user32.GetSystemMetrics(79),
            )
        return (
            self.root.winfo_vrootx(),
            self.root.winfo_vrooty(),
            self.root.winfo_vrootwidth(),
            self.root.winfo_vrootheight(),
        )

    def select_screen_region(self):
        """显示半透明虚拟桌面遮罩，让用户拖动选择截图区域。"""
        virtual_x, virtual_y, virtual_width, virtual_height = self.get_virtual_screen_bounds()
        selector = tk.Toplevel(self.root)
        selector.overrideredirect(True)
        selector.geometry(
            f"{virtual_width}x{virtual_height}{virtual_x:+d}{virtual_y:+d}"
        )
        selector.attributes('-topmost', True)
        selector.attributes('-alpha', 0.28)
        selector.configure(bg='black', cursor='crosshair')

        canvas = tk.Canvas(selector, bg='black', highlightthickness=0, cursor='crosshair')
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_text(
            virtual_width // 2,
            32,
            text="拖动鼠标选择截图区域 · ESC / 右键取消",
            fill='white',
            font=('Microsoft YaHei UI', 14, 'bold'),
        )
        drag = {'start': None, 'rectangle': None}

        def cancel(event=None):
            selector.destroy()
            self.status_var.set("已取消区域选择")

        def on_press(event):
            drag['start'] = (event.x, event.y)
            if drag['rectangle'] is not None:
                canvas.delete(drag['rectangle'])
            drag['rectangle'] = canvas.create_rectangle(
                event.x,
                event.y,
                event.x,
                event.y,
                outline='#ff3b30',
                width=4,
            )

        def on_drag(event):
            if drag['start'] is not None:
                canvas.coords(
                    drag['rectangle'],
                    drag['start'][0],
                    drag['start'][1],
                    event.x,
                    event.y,
                )

        def on_release(event):
            if drag['start'] is None:
                return
            start_x, start_y = drag['start']
            left = min(start_x, event.x)
            top = min(start_y, event.y)
            width = abs(event.x - start_x)
            height = abs(event.y - start_y)
            if width < 2 or height < 2:
                return
            region = (virtual_x + left, virtual_y + top, width, height)
            for name, value in zip(('x', 'y', 'width', 'height'), region):
                self.screen_region_vars[name].set(str(value))
            selector.destroy()
            self.apply_screen_region()

        canvas.bind('<ButtonPress-1>', on_press)
        canvas.bind('<B1-Motion>', on_drag)
        canvas.bind('<ButtonRelease-1>', on_release)
        canvas.bind('<Button-3>', cancel)
        selector.bind('<Escape>', cancel)
        selector.focus_force()
        self.status_var.set("请拖动鼠标选择截图区域")

    @staticmethod
    def format_video_time(seconds):
        seconds = max(0, int(seconds or 0))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    def refresh_video_controls(self):
        """从选中的本地视频源加载路径、列表和播放参数。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'video_file':
            self.video_controls_frame.grid_remove()
            return

        try:
            info = streamer.get_source_info(source_id)
            mode_labels = {
                'single_loop': '循环单个视频',
                'list_loop': '循环列表',
                'random': '列表内随机',
            }
            self.updating_video_controls = True
            self.video_path_var.set(info.get('video_path', ''))
            self.video_play_mode_var.set(mode_labels.get(info.get('play_mode'), '循环列表'))
            rate = float(info.get('playback_rate', 1.0))
            self.video_playback_rate_var.set(rate)
            self.video_playback_rate_text_var.set(f"{rate:g}×")
            self.video_preview_enabled_var.set(bool(info.get('preview_enabled', True)))
            self.rebuild_video_list(info.get('video_files', []))
            self.update_video_status_widgets(info)
            self.update_video_preview_visibility()
            self.video_controls_frame.grid()
        except Exception as e:
            self.video_controls_frame.grid_remove()
            self.log_message(f"读取视频参数失败: {str(e)}")
        finally:
            self.updating_video_controls = False

    def rebuild_video_list(self, video_files):
        signature = tuple(video_files or ())
        if signature == self.video_list_signature:
            return
        self.video_list_signature = signature
        self.video_list_items.clear()
        for item_id in self.video_list.get_children():
            self.video_list.delete(item_id)
        for index, video_name in enumerate(signature):
            item_id = self.video_list.insert('', tk.END, text=video_name)
            self.video_list_items[item_id] = video_name
        self.video_list.tag_configure('playing', foreground='#0b6e99')

    def update_video_status_widgets(self, info):
        current_video = info.get('current_video')
        self.video_now_playing_var.set(
            f"正在播放：{current_video}" if current_video else "尚未播放"
        )
        position = float(info.get('position_seconds', 0.0) or 0.0)
        duration = float(info.get('duration_seconds', 0.0) or 0.0)
        progress = float(info.get('progress', 0.0) or 0.0)
        self.video_progress_var.set(max(0.0, min(progress * 100.0, 100.0)))
        self.video_progress_text_var.set(
            f"{self.format_video_time(position)} / {self.format_video_time(duration)}"
        )
        for item_id, video_name in self.video_list_items.items():
            self.video_list.item(item_id, tags=('playing',) if video_name == current_video else ())

    def on_video_rate_changed(self, value):
        try:
            rate = max(0.5, min(float(value), 2.0))
            self.video_playback_rate_text_var.set(f"{rate:.2f}".rstrip('0').rstrip('.') + "×")
        except (TypeError, ValueError):
            pass

    def apply_video_settings(self, include_path=False):
        if self.updating_video_controls:
            return False
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'video_file':
            return False
        mode_values = {
            '循环单个视频': 'single_loop',
            '循环列表': 'list_loop',
            '列表内随机': 'random',
        }
        config = {
            'play_mode': mode_values.get(self.video_play_mode_var.get(), 'list_loop'),
            'playback_rate': max(0.5, min(float(self.video_playback_rate_var.get()), 2.0)),
            'preview_enabled': bool(self.video_preview_enabled_var.get()),
        }
        if include_path:
            video_path = self.video_path_var.get().strip()
            if not video_path:
                messagebox.showwarning("视频路径", "请先选择包含 MP4 视频的目录")
                return False
            current_path = streamer.get_source_info(source_id).get('video_path', '')
            if os.path.normcase(os.path.abspath(video_path)) != os.path.normcase(os.path.abspath(current_path)):
                config['video_path'] = video_path
        try:
            if not streamer.set_source_config(config, source_id):
                raise ValueError("路径中没有可播放的 MP4 视频，或视频无法打开")
            self.refresh_video_controls()
            return True
        except Exception as e:
            messagebox.showerror("应用视频参数失败", str(e))
            self.log_message(f"应用视频参数失败: {str(e)}")
            return False

    def choose_video_directory(self):
        initial = self.video_path_var.get().strip()
        directory = filedialog.askdirectory(
            parent=self.root,
            title="选择包含 MP4 视频的目录",
            initialdir=initial if os.path.isdir(initial) else None,
        )
        if directory:
            self.video_path_var.set(directory)
            if self.apply_video_settings(include_path=True):
                self.log_message(f"已加载视频目录: {directory}")

    def refresh_video_directory(self):
        """重新扫描当前视频目录并更新视频列表。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'video_file':
            return
        try:
            if not streamer.set_source_config({'refresh_video_files': True}, source_id):
                raise ValueError("当前目录中没有可播放的 MP4 视频")
            self.refresh_video_controls()
            video_count = len(streamer.get_source_info(source_id).get('video_files', ()))
            self.log_message(f"已刷新视频目录，共发现 {video_count} 个视频")
        except Exception as e:
            messagebox.showerror("刷新视频目录失败", str(e))
            self.log_message(f"刷新视频目录失败: {str(e)}")

    def choose_video_file(self):
        initial = self.video_path_var.get().strip()
        video_file = filedialog.askopenfilename(
            parent=self.root,
            title="选择要播放的视频",
            initialdir=initial if os.path.isdir(initial) else None,
            filetypes=(("MP4 视频", "*.mp4"), ("所有文件", "*.*")),
        )
        if not video_file:
            return
        directory, video_name = os.path.split(video_file)
        self.video_path_var.set(directory)
        if self.apply_video_settings(include_path=True):
            source_id = self.get_selected_source_id()
            if streamer.set_source_config({'play_video': video_name}, source_id):
                self.log_message(f"正在播放指定视频: {video_name}")

    def on_video_list_selected(self, event=None):
        if self.updating_video_controls:
            return
        selection = self.video_list.selection()
        if not selection:
            return
        video_name = self.video_list_items.get(selection[0])
        source_id = self.get_selected_source_id()
        if not video_name or not source_id:
            return
        try:
            if not streamer.set_source_config({'play_video': video_name}, source_id):
                raise ValueError("无法打开所选视频")
            self.log_message(f"正在播放指定视频: {video_name}")
            self.update_video_playback_status(reschedule=False)
        except Exception as e:
            messagebox.showerror("播放失败", str(e))

    def update_video_preview_visibility(self):
        if self.video_preview_enabled_var.get():
            self.video_preview_frame.grid()
        else:
            self.video_preview_frame.grid_remove()
            self.video_preview_image = None
            self.video_preview_label.configure(image='', text="预览已关闭")

    def toggle_video_preview(self):
        self.update_video_preview_visibility()
        self.apply_video_settings()

    def close_video_preview(self):
        self.video_preview_enabled_var.set(False)
        self.toggle_video_preview()

    def update_video_preview(self, source_id):
        frame = streamer.get_source_preview(source_id)
        if frame is None:
            self.video_preview_label.configure(image='', text="等待视频画面")
            self.video_preview_image = None
            return
        height, width = frame.shape[:2]
        preview_width_limit, preview_height_limit = self.video_preview_size
        scale = min(
            preview_width_limit / max(width, 1),
            preview_height_limit / max(height, 1),
        )
        preview_width = max(1, int(width * scale))
        preview_height = max(1, int(height * scale))
        preview = cv2.resize(frame, (preview_width, preview_height), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.png', preview)
        if not ok:
            return
        image_data = base64.b64encode(encoded.tobytes()).decode('ascii')
        self.video_preview_image = tk.PhotoImage(data=image_data, format='png')
        self.video_preview_label.configure(image=self.video_preview_image, text='')

    def update_video_playback_status(self, reschedule=True):
        try:
            source_id = self.get_selected_source_id()
            if source_id and self.source_type_by_id.get(source_id) == 'video_file':
                info = streamer.get_source_info(source_id)
                self.update_video_status_widgets(info)
                if self.video_preview_enabled_var.get():
                    self.update_video_preview(source_id)
        except (RuntimeError, tk.TclError):
            return
        except Exception as e:
            self.log_message(f"刷新视频播放状态失败: {str(e)}")
        finally:
            if reschedule:
                try:
                    if self.root.winfo_exists():
                        self.video_refresh_job = self.root.after(200, self.update_video_playback_status)
                except tk.TclError:
                    self.video_refresh_job = None

    def drive_video_when_not_streaming(self):
        """未开始 UDP 推流时也推进活动视频，让列表点播与预览可以独立工作。"""
        try:
            source_id = self.get_selected_source_id()
            if (
                not self.streaming
                and source_id
                and self.source_type_by_id.get(source_id) == 'video_file'
            ):
                streamer.get_frame()
        except Exception:
            pass
        finally:
            try:
                self.video_idle_playback_job = self.root.after(15, self.drive_video_when_not_streaming)
            except tk.TclError:
                self.video_idle_playback_job = None

    def save_video_config(self):
        """保存当前视频源的路径、模式、倍速、首播视频和预览设置。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'video_file':
            return
        if not self.apply_video_settings(include_path=True):
            return
        try:
            runtime_config = streamer.get_source_info(source_id)
            path = save_video_source_config(source_id, runtime_config)
            self.log_message(f"视频参数已保存: {path}")
            self.status_var.set(f"视频参数已保存: {source_id}")
            messagebox.showinfo("成功", "视频参数已保存，下次启动时会自动恢复。")
        except Exception as e:
            messagebox.showerror("错误", f"保存视频参数失败: {str(e)}")
            self.log_message(f"保存视频参数失败: {str(e)}")

    def apply_audio_overlay_frame_rate(self, event=None):
        """Use the audio source FPS as the independent window's saved cadence."""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'audio_visualization':
            return False
        try:
            frame_rate = validate_source_frame_rate(self.audio_overlay_fps_var.get())
        except ValueError as e:
            messagebox.showerror("窗口帧率无效", str(e))
            self.audio_overlay_fps_var.set(f"{self.audio_overlay_frame_rate:g}")
            return False

        self.source_fps_var.set(f"{frame_rate:g}")
        if not self.apply_source_frame_rate():
            return False
        self.audio_overlay_frame_rate = frame_rate
        self.audio_overlay_fps_var.set(f"{frame_rate:g}")
        if self.audio_overlay_running:
            self.audio_overlay_status_var.set(f"运行中 · {frame_rate:g} FPS")
        return True

    def _create_audio_overlay_window(self):
        chroma_key = "#010203"
        window = tk.Toplevel(self.root)
        window.withdraw()
        window.title("音频可视化")
        window.overrideredirect(True)
        window.configure(bg=chroma_key)
        window.attributes('-topmost', True)
        try:
            window.attributes('-transparentcolor', chroma_key)
        except tk.TclError:
            # -transparentcolor is provided by Windows.  Other Tk builds still
            # get a borderless, gently translucent standalone window.
            try:
                window.attributes('-alpha', 0.92)
            except tk.TclError:
                pass

        screen_width = window.winfo_screenwidth()
        x = max(0, screen_width - self.audio_overlay_size - 40)
        window.geometry(f"{self.audio_overlay_size}x{self.audio_overlay_size}+{x}+80")
        label = tk.Label(window, bg=chroma_key, bd=0, highlightthickness=0)
        label.pack(fill=tk.BOTH, expand=True)
        for widget in (window, label):
            widget.bind('<ButtonPress-1>', self.begin_audio_overlay_drag)
            widget.bind('<B1-Motion>', self.drag_audio_overlay)
            widget.bind('<MouseWheel>', self.resize_audio_overlay)
            widget.bind('<Button-3>', lambda event: self.stop_audio_overlay())
            widget.bind('<Escape>', lambda event: self.stop_audio_overlay())
        window.protocol("WM_DELETE_WINDOW", self.stop_audio_overlay)
        self.audio_overlay_window = window
        self.audio_overlay_label = label
        window.deiconify()
        window.focus_force()

    def start_audio_overlay(self):
        """Start the transparent visualizer without starting UDP streaming."""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'audio_visualization':
            messagebox.showwarning("提示", "请先选择一个音频可视化源")
            return
        if self.audio_overlay_running:
            if self.audio_overlay_window is not None:
                self.audio_overlay_window.lift()
            return
        if self.audio_overlay_thread and self.audio_overlay_thread.is_alive():
            self.audio_overlay_thread.join(timeout=0.5)
            if self.audio_overlay_thread.is_alive():
                messagebox.showwarning("等待关闭", "上一个独立窗口正在关闭，请稍后再试。")
                return
        if not self.apply_audio_overlay_frame_rate():
            return

        self.audio_overlay_running = True
        self.audio_overlay_source_id = source_id
        self.audio_overlay_error = None
        with self.audio_overlay_lock:
            self.audio_overlay_png = None
            self.audio_overlay_version += 1
            self.audio_overlay_rendered_version = self.audio_overlay_version
        self._create_audio_overlay_window()
        self.audio_overlay_start_button.configure(state=tk.DISABLED)
        self.audio_overlay_stop_button.configure(state=tk.NORMAL)
        self.audio_overlay_status_var.set(f"运行中 · {self.audio_overlay_frame_rate:g} FPS")

        stop_event = threading.Event()
        self.audio_overlay_stop_event = stop_event
        self.audio_overlay_thread = threading.Thread(
            target=self.run_audio_overlay,
            args=(source_id, stop_event),
            daemon=True,
        )
        self.audio_overlay_thread.start()
        self.audio_overlay_refresh_job = self.root.after(10, self.update_audio_overlay)
        self.log_message(f"音频可视化独立窗口已启动: {source_id}")
        self.status_var.set("音频可视化独立窗口运行中")

    def run_audio_overlay(self, source_id, stop_event):
        """Render and PNG-encode overlay frames away from Tk's UI thread."""
        next_frame_at = time.monotonic()
        try:
            while not stop_event.is_set():
                frame = streamer.get_audio_overlay_frame(source_id)
                if frame is None:
                    raise RuntimeError("音频可视化源没有返回透明画面")
                size = self.audio_overlay_size
                if frame.shape[0] != size or frame.shape[1] != size:
                    interpolation = cv2.INTER_AREA if size < frame.shape[0] else cv2.INTER_LINEAR
                    frame = cv2.resize(frame, (size, size), interpolation=interpolation)
                # Resizing BGRA introduces partially transparent edge pixels.
                # Tk pre-blends those against black on Windows, so restore the
                # binary mask before handing the PNG to PhotoImage.
                if frame.ndim == 3 and frame.shape[2] == 4:
                    visible = frame[:, :, 3] >= 128
                    frame[:, :, 3] = np.where(visible, 255, 0).astype(np.uint8)
                    frame[~visible, :3] = 0
                ok, encoded = cv2.imencode('.png', frame)
                if not ok:
                    raise RuntimeError("无法编码透明窗口画面")
                image_data = base64.b64encode(encoded.tobytes()).decode('ascii')
                with self.audio_overlay_lock:
                    self.audio_overlay_png = image_data
                    self.audio_overlay_version += 1

                interval = 1.0 / max(self.audio_overlay_frame_rate, MIN_SOURCE_FRAME_RATE)
                next_frame_at = max(next_frame_at + interval, time.monotonic())
                stop_event.wait(max(0.0, next_frame_at - time.monotonic()))
        except Exception as e:
            if not stop_event.is_set():
                self.audio_overlay_error = str(e)
                self.ui_action_queue.put(self.handle_audio_overlay_failure)

    def update_audio_overlay(self):
        try:
            if not self.audio_overlay_running or self.audio_overlay_window is None:
                return
            with self.audio_overlay_lock:
                version = self.audio_overlay_version
                image_data = self.audio_overlay_png
            if image_data is not None and version != self.audio_overlay_rendered_version:
                self.audio_overlay_image = tk.PhotoImage(data=image_data, format='png')
                self.audio_overlay_label.configure(image=self.audio_overlay_image)
                self.audio_overlay_rendered_version = version
        except (RuntimeError, tk.TclError):
            return
        except Exception as e:
            self.log_message(f"刷新音频透明窗口失败: {str(e)}")
        finally:
            if self.audio_overlay_running:
                try:
                    self.audio_overlay_refresh_job = self.root.after(10, self.update_audio_overlay)
                except tk.TclError:
                    self.audio_overlay_refresh_job = None

    def begin_audio_overlay_drag(self, event):
        window = self.audio_overlay_window
        if window is not None:
            self.audio_overlay_drag_origin = (
                event.x_root,
                event.y_root,
                window.winfo_x(),
                window.winfo_y(),
            )

    def drag_audio_overlay(self, event):
        if self.audio_overlay_window is None or self.audio_overlay_drag_origin is None:
            return
        start_x, start_y, window_x, window_y = self.audio_overlay_drag_origin
        x = window_x + event.x_root - start_x
        y = window_y + event.y_root - start_y
        self.audio_overlay_window.geometry(f"+{x}+{y}")

    def resize_audio_overlay(self, event):
        window = self.audio_overlay_window
        if window is None:
            return
        delta = 40 if event.delta > 0 else -40
        self.audio_overlay_size = max(160, min(1200, self.audio_overlay_size + delta))
        window.geometry(
            f"{self.audio_overlay_size}x{self.audio_overlay_size}+"
            f"{window.winfo_x()}+{window.winfo_y()}"
        )

    def stop_audio_overlay(self):
        was_running = self.audio_overlay_running
        self.audio_overlay_running = False
        if self.audio_overlay_stop_event is not None:
            self.audio_overlay_stop_event.set()
        if self.audio_overlay_refresh_job is not None:
            try:
                self.root.after_cancel(self.audio_overlay_refresh_job)
            except tk.TclError:
                pass
            self.audio_overlay_refresh_job = None
        if self.audio_overlay_window is not None:
            try:
                self.audio_overlay_window.destroy()
            except tk.TclError:
                pass
        self.audio_overlay_window = None
        self.audio_overlay_label = None
        self.audio_overlay_image = None
        self.audio_overlay_source_id = None
        self.audio_overlay_start_button.configure(state=tk.NORMAL)
        self.audio_overlay_stop_button.configure(state=tk.DISABLED)
        self.audio_overlay_status_var.set("独立窗口未运行")
        if was_running:
            self.log_message("音频可视化独立窗口已关闭")
            self.status_var.set("音频可视化独立窗口已关闭")

    def handle_audio_overlay_failure(self):
        error = self.audio_overlay_error or "未知错误"
        self.stop_audio_overlay()
        self.log_message(f"音频可视化独立窗口错误: {error}")
        self.status_var.set("音频可视化独立窗口出错")

    def refresh_audio_controls(self):
        """从当前音频源读取效果目录、参数元数据和运行时值。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'audio_visualization':
            self.audio_controls_frame.grid_remove()
            return

        try:
            info = streamer.get_source_info(source_id)
            config = info.get('config', {})
            audio_ui = info.get('audio_ui', {})
            frame_rate = float(info.get('fps', self.audio_overlay_frame_rate))
            self.audio_overlay_frame_rate = frame_rate
            self.audio_overlay_fps_var.set(f"{frame_rate:g}")
            self.updating_audio_controls = True
            self.audio_effect_catalog = list(audio_ui.get('effects', []))
            self.audio_effect_meta = {item['id']: item for item in self.audio_effect_catalog}
            self.audio_effect_label_to_id = {item['label']: item['id'] for item in self.audio_effect_catalog}
            self.audio_effect_config = dict(config.get('effects', {}))
            self.audio_input_catalog = list(audio_ui.get('input_parameters', []))
            devices = list(audio_ui.get('devices', []))
            self.audio_device_label_to_name = {"系统默认输入": ""}
            for device in devices:
                name = device.get('name')
                if not isinstance(name, str) or not name:
                    continue
                label = name
                if label in self.audio_device_label_to_name:
                    label = f"{name} ({device.get('index')})"
                self.audio_device_label_to_name[label] = name
            self.audio_device_combo.configure(values=list(self.audio_device_label_to_name))
            configured_device = config.get('target_device', '')
            selected_device = next(
                (label for label, name in self.audio_device_label_to_name.items()
                 if name == configured_device),
                "系统默认输入",
            )
            self.audio_selected_device_var.set(selected_device)

            labels = [item['label'] for item in self.audio_effect_catalog]
            self.audio_effect_combo.configure(values=labels)
            selected_label = self.audio_selected_effect_var.get()
            if selected_label not in self.audio_effect_label_to_id:
                selected_id = next(
                    (item['id'] for item in self.audio_effect_catalog
                     if self.audio_effect_config.get(item['id'], {}).get('enabled')),
                    self.audio_effect_catalog[0]['id'] if self.audio_effect_catalog else None,
                )
                selected_label = self.audio_effect_meta[selected_id]['label'] if selected_id else ""
                self.audio_selected_effect_var.set(selected_label)

            self.rebuild_audio_input_parameters(config.get('input', {}))
            self.rebuild_selected_audio_effect()
            self.update_audio_enabled_summary()
            self.refresh_audio_presets(source_id)
            self.audio_controls_frame.grid()
        except Exception as e:
            self.audio_controls_frame.grid_remove()
            self.log_message(f"读取音频视觉参数失败: {str(e)}")
        finally:
            self.updating_audio_controls = False

    @staticmethod
    def clear_frame(frame):
        for child in frame.winfo_children():
            child.destroy()

    @staticmethod
    def normalize_audio_parameter(spec, value):
        minimum = float(spec['min'])
        maximum = float(spec['max'])
        step = float(spec['step'])
        digits = int(spec.get('digits', 2))
        numeric = max(minimum, min(maximum, float(value)))
        numeric = round(numeric / step) * step
        return int(round(numeric)) if digits == 0 else round(numeric, digits)

    @staticmethod
    def format_audio_parameter(spec, value):
        return f"{float(value):.{int(spec.get('digits', 2))}f}"

    def add_audio_parameter_row(self, parent, row, spec, value, callback, variable_store, value_store):
        name = spec['name']
        variable = tk.DoubleVar(value=float(value))
        value_variable = tk.StringVar(value=self.format_audio_parameter(spec, value))
        variable_store[name] = variable
        value_store[name] = value_variable
        ttk.Label(parent, text=f"{spec['label']}:").grid(row=row, column=0, sticky=tk.W, pady=2)
        ttk.Scale(
            parent,
            from_=spec['min'],
            to=spec['max'],
            variable=variable,
            command=lambda raw, item=spec: callback(item, raw),
        ).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        ttk.Label(parent, textvariable=value_variable, width=7, anchor=tk.E).grid(
            row=row, column=2, sticky=tk.E, pady=2
        )

    def rebuild_audio_input_parameters(self, values):
        self.clear_frame(self.audio_input_parameters_frame)
        self.audio_input_vars = {}
        self.audio_input_value_vars = {}
        for row, spec in enumerate(self.audio_input_catalog):
            value = values.get(spec['name'], spec['default'])
            self.add_audio_parameter_row(
                self.audio_input_parameters_frame,
                row,
                spec,
                value,
                self.on_audio_input_parameter_changed,
                self.audio_input_vars,
                self.audio_input_value_vars,
            )

    def get_selected_audio_effect_id(self):
        return self.audio_effect_label_to_id.get(self.audio_selected_effect_var.get())

    def rebuild_selected_audio_effect(self):
        self.clear_frame(self.audio_effect_parameters_frame)
        self.audio_effect_parameter_vars = {}
        self.audio_effect_parameter_value_vars = {}
        effect_id = self.get_selected_audio_effect_id()
        if not effect_id:
            self.audio_selected_effect_enabled_var.set(False)
            self.audio_effect_description_var.set("没有可用的效果模块")
            return
        metadata = self.audio_effect_meta[effect_id]
        current = self.audio_effect_config.get(effect_id, {})
        self.audio_selected_effect_enabled_var.set(bool(current.get('enabled', False)))
        self.audio_effect_description_var.set(metadata.get('description', ''))
        values = current.get('params', {})
        for row, spec in enumerate(metadata.get('parameters', [])):
            value = values.get(spec['name'], spec['default'])
            self.add_audio_parameter_row(
                self.audio_effect_parameters_frame,
                row,
                spec,
                value,
                self.on_audio_effect_parameter_changed,
                self.audio_effect_parameter_vars,
                self.audio_effect_parameter_value_vars,
            )

    def update_audio_enabled_summary(self):
        enabled = [
            item['label'] for item in self.audio_effect_catalog
            if self.audio_effect_config.get(item['id'], {}).get('enabled')
        ]
        summary = "已启用：" + ("、".join(enabled) if enabled else "无（仅显示背景）")
        self.audio_enabled_summary_var.set(summary)

    def on_audio_device_selected(self, event=None):
        if self.updating_audio_controls:
            return
        target_device = self.audio_device_label_to_name.get(self.audio_selected_device_var.get())
        if target_device is None:
            return
        self.apply_audio_runtime_config({'target_device': target_device})

    def apply_audio_runtime_config(self, config):
        if self.updating_audio_controls:
            return
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'audio_visualization':
            return
        try:
            if not streamer.set_source_config(config, source_id):
                raise ValueError("参数超出允许范围")
            self.status_var.set("音频视觉参数已实时更新")
        except Exception as e:
            self.log_message(f"更新音频视觉参数失败: {str(e)}")
            self.refresh_audio_controls()

    def save_audio_config(self):
        """将当前音频源的完整运行时参数保存到 config_stream.yaml。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'audio_visualization':
            messagebox.showwarning("提示", "请先选择一个音频可视化源")
            return

        try:
            info = streamer.get_source_info(source_id)
            runtime_config = info.get('config', {})
            path = save_source_runtime_config(source_id, runtime_config)
            self.log_message(f"音频参数已保存: {path}")
            self.status_var.set(f"音频参数已保存: {source_id}")
            messagebox.showinfo("成功", "音频参数已保存，下次启动时会自动恢复。")
        except Exception as e:
            messagebox.showerror("错误", f"保存音频参数失败: {str(e)}")
            self.log_message(f"保存音频参数失败: {str(e)}")
            self.status_var.set("保存音频参数失败")

    def refresh_audio_presets(self, source_id=None):
        """刷新当前音频源拥有的命名效果组合。"""
        source_id = source_id or self.get_selected_source_id()
        try:
            self.audio_presets = load_audio_presets(source_id) if source_id else {}
            names = list(self.audio_presets)
            self.audio_preset_combo.configure(values=names)
            active_name = load_active_audio_preset(source_id) if source_id else None
            self.audio_preset_var.set(active_name or (names[0] if names else ""))
        except Exception as e:
            self.audio_presets = {}
            self.audio_preset_combo.configure(values=())
            self.audio_preset_var.set("")
            self.log_message(f"读取音频预设失败: {str(e)}")

    def save_current_audio_preset(self):
        """将当前完整音频组合另存为命名预设。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'audio_visualization':
            messagebox.showwarning("提示", "请先选择一个音频可视化源")
            return

        name = simpledialog.askstring(
            "保存效果组合",
            "请输入预设名称:",
            parent=self.root,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("提示", "预设名称不能为空")
            return
        if name in self.audio_presets and not messagebox.askyesno(
            "覆盖预设",
            f"预设“{name}”已存在，是否覆盖？",
        ):
            return

        try:
            runtime_config = streamer.get_source_info(source_id).get('config', {})
            save_audio_preset(source_id, name, runtime_config, make_active=True)
            self.refresh_audio_presets(source_id)
            self.audio_preset_var.set(name)
            self.log_message(f"音频组合预设已保存: {name}")
            self.status_var.set(f"已保存音频预设: {name}")
        except Exception as e:
            messagebox.showerror("错误", f"保存音频预设失败: {str(e)}")
            self.log_message(f"保存音频预设失败: {str(e)}")

    def apply_audio_preset(self):
        """将选中的效果组合应用到当前音频源。"""
        source_id = self.get_selected_source_id()
        name = self.audio_preset_var.get()
        if not source_id or not name:
            messagebox.showwarning("提示", "请先选择一个音频预设")
            return
        try:
            presets = load_audio_presets(source_id)
            preset = presets.get(name)
            if preset is None:
                raise ValueError(f"找不到音频预设: {name}")
            if not streamer.set_source_config(preset, source_id):
                raise ValueError("预设中包含无效或超出范围的参数")
            save_active_audio_preset(source_id, name)
            self.audio_presets = presets
            self.refresh_audio_controls()
            self.audio_preset_var.set(name)
            self.log_message(f"已应用音频组合预设: {name}")
            self.status_var.set(f"已应用音频预设: {name}")
        except Exception as e:
            messagebox.showerror("错误", f"应用音频预设失败: {str(e)}")
            self.log_message(f"应用音频预设失败: {str(e)}")
            self.refresh_audio_presets(source_id)

    def on_audio_preset_selected(self, event=None):
        """选择效果预设后立即应用，并记住每个音频源的选择。"""
        self.apply_audio_preset()

    def delete_selected_audio_preset(self):
        """删除当前选中的命名效果组合。"""
        source_id = self.get_selected_source_id()
        name = self.audio_preset_var.get()
        if not source_id or not name:
            messagebox.showwarning("提示", "请先选择一个音频预设")
            return
        if not messagebox.askyesno("删除预设", f"确定删除预设“{name}”吗？"):
            return
        try:
            delete_audio_preset(source_id, name)
            self.refresh_audio_presets(source_id)
            self.log_message(f"已删除音频组合预设: {name}")
            self.status_var.set(f"已删除音频预设: {name}")
        except Exception as e:
            messagebox.showerror("错误", f"删除音频预设失败: {str(e)}")
            self.log_message(f"删除音频预设失败: {str(e)}")

    def on_audio_effect_selected(self, event=None):
        self.updating_audio_controls = True
        try:
            self.rebuild_selected_audio_effect()
        finally:
            self.updating_audio_controls = False

    def on_audio_effect_enabled_changed(self):
        effect_id = self.get_selected_audio_effect_id()
        if not effect_id:
            return
        enabled = self.audio_selected_effect_enabled_var.get()
        self.audio_effect_config.setdefault(effect_id, {})['enabled'] = enabled
        self.update_audio_enabled_summary()
        self.apply_audio_runtime_config({'effects': {effect_id: {'enabled': enabled}}})

    def enable_only_current_audio_effect(self):
        effect_id = self.get_selected_audio_effect_id()
        if not effect_id:
            return
        effects = {
            item['id']: {'enabled': item['id'] == effect_id}
            for item in self.audio_effect_catalog
        }
        for item_id, item_config in effects.items():
            self.audio_effect_config.setdefault(item_id, {})['enabled'] = item_config['enabled']
        self.audio_selected_effect_enabled_var.set(True)
        self.update_audio_enabled_summary()
        self.apply_audio_runtime_config({'effects': effects})

    def disable_all_audio_effects(self):
        effects = {item['id']: {'enabled': False} for item in self.audio_effect_catalog}
        for item_id in effects:
            self.audio_effect_config.setdefault(item_id, {})['enabled'] = False
        self.audio_selected_effect_enabled_var.set(False)
        self.update_audio_enabled_summary()
        self.apply_audio_runtime_config({'effects': effects})

    def reset_current_audio_effect(self):
        effect_id = self.get_selected_audio_effect_id()
        if not effect_id:
            return
        self.apply_audio_runtime_config({'effects': {effect_id: {'reset': True}}})
        self.refresh_audio_controls()

    def on_audio_input_parameter_changed(self, spec, value):
        numeric = self.normalize_audio_parameter(spec, value)
        self.audio_input_value_vars[spec['name']].set(self.format_audio_parameter(spec, numeric))
        self.apply_audio_runtime_config({'input': {spec['name']: numeric}})

    def on_audio_effect_parameter_changed(self, spec, value):
        effect_id = self.get_selected_audio_effect_id()
        if not effect_id:
            return
        numeric = self.normalize_audio_parameter(spec, value)
        self.audio_effect_parameter_value_vars[spec['name']].set(
            self.format_audio_parameter(spec, numeric)
        )
        self.audio_effect_config.setdefault(effect_id, {}).setdefault('params', {})[spec['name']] = numeric
        self.apply_audio_runtime_config({
            'effects': {effect_id: {'params': {spec['name']: numeric}}}
        })

    def log_message(self, message):
        """添加消息到日志框；后台线程不会直接操作 Tk 控件。"""
        if threading.current_thread() is not threading.main_thread():
            self.log_queue.put(str(message))
            return
        self._append_log_message(message)

    def _append_log_message(self, message):
        """在 Tk 主线程中将一条日志写入界面。"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)  # 滚动到底部
        self.log_text.config(state=tk.DISABLED)

    def flush_log_messages(self):
        """定时执行后台线程排入的界面操作，并显示它产生的日志。"""
        try:
            while True:
                self.ui_action_queue.get_nowait()()
        except queue.Empty:
            pass
        try:
            while True:
                self._append_log_message(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        finally:
            try:
                if self.root.winfo_exists():
                    self.log_flush_job = self.root.after(100, self.flush_log_messages)
            except tk.TclError:
                self.log_flush_job = None

    def handle_streaming_failure(self):
        """在 Tk 主线程中恢复推流控件。"""
        self.streaming = False
        self.stop_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)
        self.status_var.set("推流出错")
        self.clear_stream_preview("推流出错")

    def format_udp_preset_label(self, preset_type, preset_name):
        """为下拉框生成带类别的预设名称。"""
        prefix = self.builtin_preset_prefix if preset_type == "builtin" else self.personal_preset_prefix
        return f"{prefix}{preset_name}"

    def get_udp_preset_labels(self):
        """内置预设固定在前，个人预设按保存顺序显示在后。"""
        return [
            *(self.format_udp_preset_label("builtin", name) for name in self.presets),
            *(self.format_udp_preset_label("personal", name) for name in self.personal_presets),
        ]

    def parse_udp_preset_label(self, label):
        """将下拉框文字解析为 (类别, 名称)，自定义配置返回空值。"""
        if label.startswith(self.builtin_preset_prefix):
            name = label[len(self.builtin_preset_prefix):]
            if name in self.presets:
                return "builtin", name
        if label.startswith(self.personal_preset_prefix):
            name = label[len(self.personal_preset_prefix):]
            if name in self.personal_presets:
                return "personal", name
        return None, None

    def refresh_udp_preset_list(self, selected_label=None):
        """个人预设变动后刷新选择器，并尽量保留当前选择。"""
        labels = self.get_udp_preset_labels()
        self.preset_combo.configure(values=labels)
        if selected_label in labels:
            self.preset_var.set(selected_label)

    def normalize_personal_udp_presets(self, raw_presets):
        """读取个人预设，忽略损坏或不完整的条目。"""
        if raw_presets is None:
            return {}
        if not isinstance(raw_presets, dict):
            raise ValueError("personal_presets 必须是 YAML 对象")

        normalized = {}
        for raw_name, raw_config in raw_presets.items():
            name = str(raw_name).strip()
            if not name or "\n" in name or "\r" in name or len(name) > 80:
                continue
            if not isinstance(raw_config, dict):
                continue
            try:
                color_mode = str(raw_config['color_mode'])
                config = {
                    'server_ip': str(raw_config['server_ip']),
                    'server_port': int(raw_config['server_port']),
                    'resolution': [240, 240],
                    'color_mode': color_mode,
                    'target_fps': validate_frame_rate_limit(
                        raw_config.get(
                            'target_fps', default_frame_rate_limit(color_mode)
                        ),
                        color_mode,
                    ),
                    'transport_version': 2,
                }
            except (KeyError, TypeError, ValueError):
                continue
            if (
                config['server_ip']
                and 0 < config['server_port'] < 65536
                and config['color_mode'] in self.valid_values['color_mode']
            ):
                normalized[name] = config
        return normalized

    def configs_equal(self, first, second):
        """比较两份完整 UDP 配置，避免浮点文本格式导致误判。"""
        try:
            return (
                first.get('server_ip') == second.get('server_ip')
                and int(first.get('server_port')) == int(second.get('server_port'))
                and first.get('color_mode') == second.get('color_mode')
                and abs(float(first.get('target_fps')) - float(second.get('target_fps'))) < 1e-6
            )
        except (TypeError, ValueError):
            return False

    def find_matching_personal_preset(self, config):
        for name, preset in self.personal_presets.items():
            if self.configs_equal(config, preset):
                return name
        return None

    def on_udp_preset_selected(self, event=None):
        """下拉框选择后立即应用预设。"""
        self.apply_preset(self.preset_var.get(), restart_if_streaming=True)

    def update_preset_summary(self, preset_label):
        preset_type, preset_name = self.parse_udp_preset_label(preset_label or "")
        if preset_type == "personal":
            preset = self.personal_presets[preset_name]
            color = "RGB565 高画质" if preset['color_mode'] == "rgb565" else "RGB332 高帧率"
            self.preset_summary_var.set(
                f"个人 · {preset['server_ip']}:{preset['server_port']} · "
                f"240 × 240 · {color} · {preset['target_fps']:.1f} FPS · V2 反馈闭环"
            )
            return
        if preset_type != "builtin":
            self.preset_summary_var.set("当前参数尚未保存为预设")
            return
        preset = self.presets[preset_name]
        color = "RGB565 高画质" if preset['color_mode'] == MODE_RGB565 else "RGB332 高帧率"
        self.preset_summary_var.set(
            f"内置只读 · 240 × 240 · {color} · "
            f"{preset['target_fps']:.1f} FPS · V2 反馈闭环"
        )

    def get_matching_preset(self, config):
        """返回与发送参数完全匹配的内置预设。"""
        for name, preset in self.presets.items():
            color = "rgb565" if preset['color_mode'] == MODE_RGB565 else "rgb332"
            if (
                config.get('color_mode') == color
                and abs(float(config.get('target_fps')) - preset['target_fps']) < 1e-6
            ):
                return name
        return None

    def get_udp_form_config(self):
        """读取当前 UDP 表单；输入不完整时由调用者处理异常。"""
        return {
            'server_ip': self.entries['server_ip'].get(),
            'server_port': int(self.entries['server_port'].get()),
            'resolution': [240, 240],
            'color_mode': self.entries['color_mode'].get(),
            'target_fps': float(self.entries['target_fps'].get()),
            'transport_version': 2,
        }

    def set_target_fps_control(self, color_mode, target_fps):
        """Update the spinbox range and value without changing preset state."""
        maximum = default_frame_rate_limit(color_mode)
        target_fps = validate_frame_rate_limit(target_fps, color_mode)
        self.entries['target_fps'].configure(
            from_=MIN_FRAME_RATE_LIMIT,
            to=maximum,
        )
        self.entries['target_fps'].delete(0, tk.END)
        self.entries['target_fps'].insert(0, f"{target_fps:g}")

    def on_color_mode_edited(self, event=None):
        """Keep a custom FPS when valid, otherwise use the new mode's safe maximum."""
        if self.updating_udp_controls:
            return
        color_mode = self.entries['color_mode'].get()
        try:
            target_fps = validate_frame_rate_limit(
                self.entries['target_fps'].get(), color_mode
            )
        except ValueError:
            target_fps = default_frame_rate_limit(color_mode)
        self.set_target_fps_control(color_mode, target_fps)
        self.on_udp_parameter_edited()

    def on_udp_parameter_edited(self, event=None):
        """手动修改传输参数后同步预设下拉框状态。"""
        if self.updating_udp_controls:
            return
        try:
            config = self.get_udp_form_config()
        except (TypeError, ValueError):
            config = None

        current_type, current_name = self.parse_udp_preset_label(self.preset_var.get())
        preset_label = None
        if config is not None and current_type == "personal":
            if self.configs_equal(config, self.personal_presets[current_name]):
                preset_label = self.format_udp_preset_label("personal", current_name)
        elif config is not None and current_type == "builtin":
            if self.get_matching_preset(config) == current_name:
                preset_label = self.format_udp_preset_label("builtin", current_name)

        if config is not None and preset_label is None:
            personal_name = self.find_matching_personal_preset(config)
            builtin_name = self.get_matching_preset(config)
            if personal_name:
                preset_label = self.format_udp_preset_label("personal", personal_name)
            elif builtin_name:
                preset_label = self.format_udp_preset_label("builtin", builtin_name)
        self.preset_var.set(preset_label or self.custom_preset_label)
        self.update_preset_summary(preset_label)

    def apply_preset(self, preset_label, restart_if_streaming=False):
        """应用预设；仅在原本正在推流时重启发送线程。"""
        preset_type, preset_name = self.parse_udp_preset_label(preset_label)
        if preset_type is None and preset_label in self.presets:
            # 兼容内部旧调用和旧版 config.yaml 中的名称。
            preset_type, preset_name = "builtin", preset_label
            preset_label = self.format_udp_preset_label(preset_type, preset_name)
        if preset_type == "builtin":
            preset = self.presets[preset_name]
        elif preset_type == "personal":
            preset = self.personal_presets[preset_name]
        else:
            return

        was_streaming = self.streaming
        self.updating_udp_controls = True
        try:
            if preset_type == "personal":
                self.entries['server_ip'].delete(0, tk.END)
                self.entries['server_ip'].insert(0, preset['server_ip'])
                self.entries['server_port'].delete(0, tk.END)
                self.entries['server_port'].insert(0, str(preset['server_port']))
                resolution = preset['resolution']
                color_mode = preset['color_mode']
                target_fps = preset['target_fps']
            else:
                resolution = [preset['resolution'], preset['resolution']]
                color_mode = "rgb565" if preset['color_mode'] == MODE_RGB565 else "rgb332"
                target_fps = preset['target_fps']

            self.entries['resolution'].set(f"[{resolution[0]},{resolution[1]}]")
            self.entries['color_mode'].set(color_mode)
            self.set_target_fps_control(color_mode, target_fps)

            self.preset_var.set(preset_label)
            self.update_preset_summary(preset_label)
        finally:
            self.updating_udp_controls = False

        category = "内置" if preset_type == "builtin" else "个人"
        self.log_message(f"已应用{category}发送预设: {preset_name}")
        self.status_var.set(f"已应用{category}发送预设: {preset_name}")
        if restart_if_streaming and was_streaming:
            self.stop_streaming()
            self.root.after(120, self.start_streaming)

    def load_config(self):
        """加载配置文件"""
        try:
            config_exists = os.path.exists(self.config_file)
            using_default_config = not config_exists
            if config_exists:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                if config is None:
                    config = self.default_config.copy()
                    using_default_config = True
                elif not isinstance(config, dict):
                    raise ValueError("配置内容必须是 YAML 对象")
            else:
                config = self.default_config.copy()
            config = migrate_v2_config(config, self.default_config)
            self.personal_presets = self.normalize_personal_udp_presets(config.get('personal_presets'))
            self.refresh_udp_preset_list()
            if using_default_config:
                self.log_message("未找到有效的 UDP 配置，已选择 240 高帧率 RGB332")

            # 填充表单
            self.updating_udp_controls = True
            try:
                self.entries['server_ip'].delete(0, tk.END)
                self.entries['server_ip'].insert(0, config.get('server_ip', self.default_config['server_ip']))
                self.entries['server_port'].delete(0, tk.END)
                self.entries['server_port'].insert(0, str(config.get('server_port', self.default_config['server_port'])))

                self.entries['resolution'].set("[240,240]")
                color_mode = config.get('color_mode', self.default_config['color_mode'])
                self.entries['color_mode'].set(color_mode)
                self.set_target_fps_control(
                    color_mode,
                    config.get('target_fps', default_frame_rate_limit(color_mode)),
                )
            finally:
                self.updating_udp_controls = False

            current_config = self.get_udp_form_config()
            saved_type = config.get('preset_type')
            saved_name = config.get('preset')
            preset_label = None
            if (
                saved_type == 'personal'
                and saved_name in self.personal_presets
                and self.configs_equal(current_config, self.personal_presets[saved_name])
            ):
                preset_label = self.format_udp_preset_label('personal', saved_name)
            elif (
                saved_name in self.presets
                and self.get_matching_preset(current_config) == saved_name
            ):
                preset_label = self.format_udp_preset_label('builtin', saved_name)
            else:
                personal_name = self.find_matching_personal_preset(current_config)
                builtin_name = self.get_matching_preset(current_config)
                if personal_name:
                    preset_label = self.format_udp_preset_label('personal', personal_name)
                elif builtin_name:
                    preset_label = self.format_udp_preset_label('builtin', builtin_name)
            if using_default_config and preset_label is None:
                preset_label = self.format_udp_preset_label('builtin', self.default_preset_name)
                self.apply_preset(preset_label)
            self.preset_var.set(preset_label or self.custom_preset_label)
            self.update_preset_summary(preset_label)

            if not using_default_config:
                self.log_message(f"已自动加载 UDP 配置: {self.config_file}")
                self.status_var.set(f"已加载 UDP 配置: {self.config_file}")
            else:
                self.status_var.set(f"首次启动默认使用 {self.default_preset_name}")

        except Exception as e:
            messagebox.showerror("错误", f"加载配置文件失败: {str(e)}")
            self.log_message(f"加载配置文件失败: {str(e)}")
            self.status_var.set("加载配置文件失败")

    def validate_inputs(self):
        """验证输入值"""
        errors = []

        # 验证server_ip
        ip = self.entries['server_ip'].get()
        if not ip:
            errors.append("服务器IP不能为空")

        # 验证server_port
        try:
            port = int(self.entries['server_port'].get())
            if not (0 < port < 65536):
                errors.append("端口号必须在1-65535之间")
        except ValueError:
            errors.append("端口号必须是整数")

        # 验证resolution
        res_text = self.entries['resolution'].get()
        if res_text not in self.valid_resolution_strings:
            errors.append("请选择有效的分辨率")

        # 验证color_mode
        color = self.entries['color_mode'].get()
        if color not in self.valid_values['color_mode']:
            errors.append("请选择有效的色彩模式")
        else:
            try:
                validate_frame_rate_limit(
                    self.entries['target_fps'].get(), color
                )
            except ValueError:
                maximum = default_frame_rate_limit(color)
                errors.append(
                    f"目标发送帧率必须在 {MIN_FRAME_RATE_LIMIT:g}-{maximum:g} FPS 之间"
                )

        return errors

    def parse_resolution_string(self, res_text):
        """解析分辨率字符串为列表"""
        match = re.match(r'\[(\d+),(\d+)\]', res_text)
        if match:
            return [int(match.group(1)), int(match.group(2))]
        return [240, 240]  # 默认值

    def get_color_mode_code(self, color_mode_str):
        """根据字符串获取颜色模式代码"""
        if color_mode_str == "rgb565":
            return MODE_RGB565
        return MODE_RGB332

    def build_udp_config_document(self, config=None):
        """生成 UDP v2 配置文档。"""
        current = dict(config or self.get_udp_form_config())
        preset_type, preset_name = self.parse_udp_preset_label(self.preset_var.get())
        if preset_type == 'personal':
            if not self.configs_equal(current, self.personal_presets[preset_name]):
                preset_type = preset_name = None
        elif preset_type == 'builtin':
            if self.get_matching_preset(current) != preset_name:
                preset_type = preset_name = None

        if preset_type is None:
            personal_name = self.find_matching_personal_preset(current)
            builtin_name = self.get_matching_preset(current)
            if personal_name:
                preset_type, preset_name = 'personal', personal_name
            elif builtin_name:
                preset_type, preset_name = 'builtin', builtin_name

        if preset_type:
            current['preset_type'] = preset_type
            current['preset'] = preset_name
        current['personal_presets'] = {
            name: dict(values) for name, values in self.personal_presets.items()
        }
        current['transport_version'] = 2
        return current

    def write_udp_config(self, config=None):
        document = self.build_udp_config_document(config)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(document, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return document

    def save_personal_udp_preset(self):
        """将当前完整 UDP 配置保存为一个命名个人预设。"""
        errors = self.validate_inputs()
        if errors:
            messagebox.showerror("输入错误", "\n".join(errors))
            return

        selected_type, selected_name = self.parse_udp_preset_label(self.preset_var.get())
        name = simpledialog.askstring(
            "保存个人预设",
            "请输入个人预设名称:",
            initialvalue=selected_name if selected_type == 'personal' else "",
            parent=self.root,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("提示", "个人预设名称不能为空")
            return
        if "\n" in name or "\r" in name or len(name) > 80:
            messagebox.showwarning("提示", "个人预设名称不能换行且最多 80 个字符")
            return
        if name in self.personal_presets and not messagebox.askyesno(
            "覆盖个人预设",
            f"个人预设“{name}”已存在，是否覆盖？",
        ):
            return

        try:
            self.personal_presets[name] = self.get_udp_form_config()
            label = self.format_udp_preset_label('personal', name)
            self.refresh_udp_preset_list(label)
            self.update_preset_summary(label)
            self.write_udp_config()
            self.log_message(f"个人 UDP 预设已保存: {name}")
            self.status_var.set(f"已保存个人 UDP 预设: {name}")
        except Exception as e:
            messagebox.showerror("错误", f"保存个人 UDP 预设失败: {str(e)}")
            self.log_message(f"保存个人 UDP 预设失败: {str(e)}")

    def delete_personal_udp_preset(self):
        """删除当前选中的个人预设；内置预设始终不可删除。"""
        preset_type, preset_name = self.parse_udp_preset_label(self.preset_var.get())
        if preset_type != 'personal':
            messagebox.showinfo("内置预设只读", "只能删除个人预设，内置预设不可修改或删除。")
            return
        if not messagebox.askyesno("删除个人预设", f"确定删除个人预设“{preset_name}”吗？"):
            return

        try:
            del self.personal_presets[preset_name]
            builtin_name = self.get_matching_preset(self.get_udp_form_config())
            label = (
                self.format_udp_preset_label('builtin', builtin_name)
                if builtin_name else self.custom_preset_label
            )
            self.refresh_udp_preset_list()
            self.preset_var.set(label)
            self.update_preset_summary(label)
            self.write_udp_config()
            self.log_message(f"个人 UDP 预设已删除: {preset_name}")
            self.status_var.set(f"已删除个人 UDP 预设: {preset_name}")
        except Exception as e:
            messagebox.showerror("错误", f"删除个人 UDP 预设失败: {str(e)}")
            self.log_message(f"删除个人 UDP 预设失败: {str(e)}")

    def start_streaming(self):
        """开始UDP推流"""
        if not UDP_MODULES_AVAILABLE:
            messagebox.showerror("错误", "UDP推流模块不可用，请安装必要的依赖库")
            return

        # A stopped worker owns its Event and must fully exit before another
        # worker is started. Otherwise rapid stop/start can create two senders.
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=0.5)
            if self.stream_thread.is_alive():
                messagebox.showwarning("等待停止", "上一个推流线程正在停止，请稍后再试。")
                return

        # 验证配置
        errors = self.validate_inputs()
        if errors:
            messagebox.showerror("输入错误", "请先修正配置错误:\n" + "\n".join(errors))
            return

        # 禁用开始按钮，启用停止按钮
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # 获取配置
        server_ip = self.entries['server_ip'].get()
        server_port = int(self.entries['server_port'].get())

        width = 240
        color_mode_str = self.entries['color_mode'].get()
        target_fps = float(self.entries['target_fps'].get())

        # 开始推流线程
        self.clear_stream_preview("等待第一帧")
        self.stream_preview_info_var.set(
            f"正在启动 · {width}×{width} · {color_mode_str.upper()} · {target_fps:g} FPS"
        )
        self.streaming = True
        stop_event = threading.Event()
        self.stream_stop_event = stop_event
        self.stream_thread = threading.Thread(
            target=self.stream_udp_data,
            args=(server_ip, server_port, color_mode_str, target_fps, stop_event),
            daemon=True
        )
        self.stream_thread.start()

        self.log_message(f"开始推流到 {server_ip}:{server_port}")
        self.status_var.set("推流中...")

    def stop_streaming(self):
        """停止UDP推流"""
        self.streaming = False
        if self.stream_stop_event is not None:
            self.stream_stop_event.set()
        self.clear_stream_preview("推流已停止")

        # 启用开始按钮，禁用停止按钮
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

        self.log_message("停止推流")
        self.status_var.set("推流已停止")

    def publish_stream_preview(self, frame, color_mode_str):
        """由发送线程发布一张已经完整发送的预览帧。"""
        with self.stream_preview_lock:
            self.stream_preview_frame = (frame, color_mode_str)
            self.stream_preview_version += 1

    def clear_stream_preview(self, message):
        """清空发送线程共享帧，并将预览区恢复为提示文字。"""
        with self.stream_preview_lock:
            self.stream_preview_frame = None
            self.stream_preview_version += 1
            self.stream_preview_rendered_version = self.stream_preview_version
        self.stream_preview_image = None
        self.stream_preview_label.configure(image='', text=message)
        self.stream_preview_info_var.set(message)

    def update_stream_preview(self):
        """在 Tk 主线程中刷新推流预览，最多每 100 毫秒渲染一次。"""
        try:
            with self.stream_preview_lock:
                version = self.stream_preview_version
                item = self.stream_preview_frame

            if item is not None and version != self.stream_preview_rendered_version:
                frame, color_mode_str = item
                height, width = frame.shape[:2]
                preview_width_limit, preview_height_limit = self.stream_preview_size
                scale = min(
                    preview_width_limit / max(width, 1),
                    preview_height_limit / max(height, 1),
                )
                preview_width = max(1, int(width * scale))
                preview_height = max(1, int(height * scale))
                interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_NEAREST
                preview = cv2.resize(
                    frame,
                    (preview_width, preview_height),
                    interpolation=interpolation,
                )
                ok, encoded = cv2.imencode('.png', preview)
                if ok:
                    image_data = base64.b64encode(encoded.tobytes()).decode('ascii')
                    self.stream_preview_image = tk.PhotoImage(data=image_data, format='png')
                    self.stream_preview_label.configure(
                        image=self.stream_preview_image,
                        text='',
                    )
                    self.stream_preview_info_var.set(
                        f"正在推送 · {width}×{height} · {color_mode_str.upper()}"
                    )
                    self.stream_preview_rendered_version = version
        except (RuntimeError, tk.TclError):
            return
        except Exception as e:
            self.log_message(f"刷新推流预览失败: {str(e)}")
        finally:
            try:
                if self.root.winfo_exists():
                    self.stream_preview_job = self.root.after(100, self.update_stream_preview)
            except tk.TclError:
                self.stream_preview_job = None

    def stream_udp_data(
        self,
        server_ip,
        server_port,
        color_mode_str,
        target_fps,
        stop_event,
    ):
        """Run the UDP v2 capture, encoder, pacer, and feedback loop."""
        try:
            mode = self.get_color_mode_code(color_mode_str)

            def publish_preview(frame):
                self.publish_stream_preview(frame, color_mode_str)

            def publish_stats(snapshot):
                latency = (
                    "--" if snapshot.latency_p95_ms is None
                    else f"{snapshot.latency_p95_ms:.0f} ms"
                )
                self.log_message(
                    f"V2统计: 发送 {snapshot.sent_fps:.1f} FPS / "
                    f"完整显示 {snapshot.displayed_fps:.1f} FPS, "
                    f"{snapshot.udp_mbps:.2f} Mbit/s, "
                    f"有效率 {snapshot.display_efficiency * 100:.1f}%, "
                    f"队列 {snapshot.queue_depth}/{snapshot.queue_capacity or '--'}, "
                    f"P95 {latency}, 堆 {snapshot.free_heap} B"
                )

            with V2Sender(
                server_ip,
                server_port,
                mode,
                frame_rate_limit=target_fps,
            ) as sender:
                self.log_message(
                    f"UDP v2 会话 {sender.session_id:08x}: 240x240 {color_mode_str.upper()}, "
                    f"包内节拍 {sender.pacer.rate_mbps:.1f} Mbit/s, "
                    f"帧率上限 {sender.frame_rate_limit:.1f} FPS"
                )
                stream_latest_frames(
                    streamer.get_frame,
                    sender,
                    stop_event,
                    preview_callback=publish_preview,
                    stats_callback=publish_stats,
                    frame_rate_provider=streamer.get_frame_rate,
                )
        except Exception as e:
            self.log_message(f"V2 推流线程错误: {str(e)}")
            self.ui_action_queue.put(self.handle_streaming_failure)

    def on_closing(self):
        """窗口关闭时的处理"""
        if self.audio_overlay_running or self.audio_overlay_window is not None:
            self.stop_audio_overlay()
        if self.audio_overlay_thread and self.audio_overlay_thread.is_alive():
            self.audio_overlay_thread.join(timeout=2)
        if self.log_flush_job is not None:
            try:
                self.root.after_cancel(self.log_flush_job)
            except tk.TclError:
                pass
            self.log_flush_job = None
        if self.video_refresh_job is not None:
            try:
                self.root.after_cancel(self.video_refresh_job)
            except tk.TclError:
                pass
            self.video_refresh_job = None
        if self.video_idle_playback_job is not None:
            try:
                self.root.after_cancel(self.video_idle_playback_job)
            except tk.TclError:
                pass
            self.video_idle_playback_job = None
        if self.stream_preview_job is not None:
            try:
                self.root.after_cancel(self.stream_preview_job)
            except tk.TclError:
                pass
            self.stream_preview_job = None
        if self.streaming:
            self.stop_streaming()
            # 等待一小段时间让线程结束
            if self.stream_thread:
                self.stream_thread.join(timeout=2)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = YAMLConfigEditor(root)

    # 配置网格权重
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    root.mainloop()


if __name__ == "__main__":
    # 检查依赖
    try:
        import yaml
    except ImportError:
        print("错误: 需要安装PyYAML库")
        print("请运行: pip install pyyaml")
        exit(1)

    main()
