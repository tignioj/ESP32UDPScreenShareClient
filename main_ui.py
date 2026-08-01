import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import yaml
import os
import re
import threading
import time
import sys
from tkinter import scrolledtext

# 尝试导入UDP发送相关的模块
try:
    from esp32_udp_header import ESP32UDPHeader
    import cv2
    import numpy as np
    import socket
    from capture.config import (
        delete_audio_preset,
        get_streamer,
        load_audio_presets,
        save_audio_preset,
        save_source_runtime_config,
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
        self.root.geometry("880x880")
        self.root.minsize(760, 720)

        # UDP推流相关
        self.streaming = False
        self.stream_thread = None
        self.stream_stop_event = None
        self.sock = None
        # Keep frame IDs monotonic across UI stop/start cycles. Starting from a
        # process-specific value also reduces collisions after an app restart.
        self.frame_id = time.time_ns() & 0xFFFF
        self.frame_id_lock = threading.Lock()

        # 默认配置文件
        self.config_file = "config.yaml"

        # 预设配置 - 根据Header常量修正颜色模式值
        self.presets = {
            "预设1：240 高清色彩": {
                'resolution': 240,  # ESP32UDPHeader.RES_240 = 0
                'color_mode': 0,  # ESP32UDPHeader.COLOR_RGB565 = 0
                'lines_per_packet': 3,
                'udp_interval': 0.00075
            },
            "预设2：240 节省带宽": {
                'resolution': 240,  # ESP32UDPHeader.RES_240 = 0
                'color_mode': 1,  # ESP32UDPHeader.COLOR_RGB332 = 1
                'lines_per_packet': 6,
                'udp_interval': 0.001
            },
            "预设3：180 高清色彩": {
                'resolution': 180,  # ESP32UDPHeader.RES_180 = 1
                'color_mode': 0,  # ESP32UDPHeader.COLOR_RGB565 = 0
                'lines_per_packet': 4,
                'udp_interval': 0.001
            },
            "预设4：180 节省带宽": {
                'resolution': 180,  # ESP32UDPHeader.RES_180 = 1
                'color_mode': 1,  # ESP32UDPHeader.COLOR_RGB332 = 1
                'lines_per_packet': 6,
                'udp_interval': 0.001
            },
            "预设5：120 高清色彩": {
                'resolution': 120,  # ESP32UDPHeader.RES_120 = 2
                'color_mode': 0,  # ESP32UDPHeader.COLOR_RGB565 = 0
                'lines_per_packet': 4,
                'udp_interval': 0.001
            },
            "预设6：120 节省带宽": {
                'resolution': 120,  # ESP32UDPHeader.RES_120 = 2
                'color_mode': 1,  # ESP32UDPHeader.COLOR_RGB332 = 1
                'lines_per_packet': 4,
                'udp_interval': 0.001
            }
        }
        self.default_preset_name = "预设5：120 高清色彩"
        self.custom_preset_label = "自定义配置"

        # 首次启动没有 config.yaml 时使用预设5的发送参数。
        default_preset = self.presets[self.default_preset_name]
        self.default_config = {
            'server_ip': "192.168.100.161",
            'server_port': 8888,
            'resolution': [default_preset['resolution'], default_preset['resolution']],
            'color_mode': "rgb565" if default_preset['color_mode'] == 0 else "rgb332",
            'lines_per_packet': default_preset['lines_per_packet'],
            'udp_interval': default_preset['udp_interval'],
            'preset': self.default_preset_name,
        }

        # 可选值定义（存储为字符串列表，用于显示）
        self.valid_resolution_strings = ["[240,240]", "[180,180]", "[120,120]"]
        self.valid_resolution_values = [[240, 240], [180, 180], [120, 120]]

        # 根据Header限制lines_per_packet范围（0-8）
        self.valid_values = {
            'resolution': self.valid_resolution_strings,  # 用于下拉框
            'color_mode': ['rgb332', 'rgb565'],
            'lines_per_packet': {'min': 1, 'max': 8},  # Header限制：0-15
            'udp_interval': {'min': 0.0001, 'max': 0.1}
        }

        # 预设变量
        self.preset_var = tk.StringVar(value=self.default_preset_name)
        self.preset_summary_var = tk.StringVar(value="")
        self.updating_udp_controls = False

        # 图像源选择
        self.source_var = tk.StringVar(value="")
        self.source_id_by_label = {}
        self.source_type_by_id = {}

        # 屏幕截图源运行时控制。
        self.screen_mode_var = tk.StringVar(value="")
        self.screen_region_vars = {
            name: tk.StringVar(value=value)
            for name, value in zip(('x', 'y', 'width', 'height'), ('0', '0', '240', '240'))
        }

        # 音频效果和参数完全由各效果模块提供，UI 不再维护重复常量。
        self.audio_effect_catalog = []
        self.audio_effect_meta = {}
        self.audio_effect_label_to_id = {}
        self.audio_effect_config = {}
        self.audio_input_catalog = []
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

        # 日志文本框
        self.log_text = None

        self.setup_ui()
        self.refresh_source_list()
        self.load_config()

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

        source_canvas = tk.Canvas(source_tab, highlightthickness=0, height=500)
        source_scrollbar = ttk.Scrollbar(source_tab, orient=tk.VERTICAL, command=source_canvas.yview)
        source_canvas.configure(yscrollcommand=source_scrollbar.set)
        source_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        source_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        source_content = ttk.Frame(source_canvas)
        source_content.columnconfigure(0, weight=1)
        source_window = source_canvas.create_window((0, 0), window=source_content, anchor=tk.NW)
        source_content.bind(
            "<Configure>",
            lambda event: source_canvas.configure(scrollregion=source_canvas.bbox("all")),
        )
        source_canvas.bind(
            "<Configure>",
            lambda event: source_canvas.itemconfigure(source_window, width=event.width),
        )

        def scroll_source(event):
            source_canvas.yview_scroll(-int(event.delta / 120), "units")

        source_canvas.bind("<Enter>", lambda event: source_canvas.bind_all("<MouseWheel>", scroll_source))
        source_canvas.bind("<Leave>", lambda event: source_canvas.unbind_all("<MouseWheel>"))

        ttk.Label(
            udp_tab,
            text="先选择适合接收端和网络的发送预设，再填写 ESP32 的地址。",
            foreground="#555555",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        preset_frame = ttk.LabelFrame(udp_tab, text="发送预设", padding=10)
        preset_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        preset_frame.columnconfigure(1, weight=1)
        ttk.Label(preset_frame, text="分辨率预设:").grid(row=0, column=0, sticky=tk.W)
        self.preset_combo = ttk.Combobox(
            preset_frame,
            textvariable=self.preset_var,
            values=list(self.presets),
            state="readonly",
            width=30,
        )
        self.preset_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(8, 0))
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_udp_preset_selected)
        ttk.Label(
            preset_frame,
            textvariable=self.preset_summary_var,
            foreground="#356a8a",
        ).grid(row=1, column=1, sticky=tk.W, pady=(5, 0))

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

        ttk.Label(transport_frame, text="每包行数:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.entries['lines_per_packet'] = ttk.Spinbox(
            transport_frame,
            from_=1,
            to=8,
            width=13,
            command=self.on_udp_parameter_edited,
        )
        self.entries['lines_per_packet'].grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(8, 20), pady=3)
        ttk.Label(transport_frame, text="发包间隔 (秒):").grid(row=1, column=2, sticky=tk.W, pady=3)
        self.entries['udp_interval'] = ttk.Entry(transport_frame, width=13)
        self.entries['udp_interval'].grid(row=1, column=3, sticky=(tk.W, tk.E), padx=(8, 0), pady=3)
        ttk.Label(
            transport_frame,
            text="高级参数会随预设自动填写；手动修改后将显示为“自定义配置”。",
            foreground="#777777",
        ).grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))

        for key in ('resolution', 'color_mode'):
            self.entries[key].bind("<<ComboboxSelected>>", self.on_udp_parameter_edited)
        for key in ('lines_per_packet', 'udp_interval'):
            self.entries[key].bind("<KeyRelease>", self.on_udp_parameter_edited)

        udp_action_frame = ttk.Frame(udp_tab)
        udp_action_frame.grid(row=4, column=0, sticky=(tk.W, tk.E))
        ttk.Button(udp_action_frame, text="保存 UDP 配置", command=self.save_config).pack(side=tk.LEFT)
        ttk.Button(udp_action_frame, text="恢复预设5", command=self.reset_to_default).pack(side=tk.LEFT, padx=8)
        ttk.Button(udp_action_frame, text="查看 YAML", command=self.show_yaml).pack(side=tk.LEFT)
        ttk.Label(
            udp_action_frame,
            text=f"自动读取/保存：{self.config_file}",
            foreground="#777777",
        ).pack(side=tk.RIGHT)

        ttk.Label(
            source_content,
            text="选择画面来源；不同来源的专属参数会显示在下方。",
            foreground="#555555",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        # 图像源切换
        source_frame = ttk.LabelFrame(source_content, text="图像源", padding=10)
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

        # 仅在选中 screen 源时显示，修改后直接作用于运行中的截图源。
        self.screen_controls_frame = ttk.LabelFrame(source_frame, text="截图区域（实时生效）", padding="6")
        self.screen_controls_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 0))
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

        # 音频工作台由效果模块的元数据动态生成。
        self.audio_controls_frame = ttk.LabelFrame(source_frame, text="音频可视化工作台（实时生效）", padding="8")
        self.audio_controls_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 0))
        self.audio_controls_frame.columnconfigure(0, weight=1)

        effect_toolbar = ttk.Frame(self.audio_controls_frame)
        effect_toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E))
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
        ).grid(row=1, column=0, sticky=tk.W, pady=(5, 1))
        audio_summary_frame = ttk.Frame(self.audio_controls_frame)
        audio_summary_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
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

        parameter_columns = ttk.Frame(self.audio_controls_frame)
        parameter_columns.grid(row=3, column=0, sticky=(tk.W, tk.E))
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
        audio_preset_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(7, 0))
        audio_preset_frame.columnconfigure(1, weight=1)
        ttk.Label(audio_preset_frame, text="预设:").grid(row=0, column=0, sticky=tk.W)
        self.audio_preset_combo = ttk.Combobox(
            audio_preset_frame,
            textvariable=self.audio_preset_var,
            state="readonly",
            width=24,
        )
        self.audio_preset_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(6, 8))
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

        self.audio_controls_frame.grid_remove()

        # 推流控制独立于两层配置，切换页签后仍然可见。
        stream_frame = ttk.LabelFrame(main_frame, text="推流控制", padding=8)
        stream_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 0))

        self.start_button = ttk.Button(stream_frame, text="开始推流",
                                       command=self.start_streaming,
                                       state=tk.NORMAL if UDP_MODULES_AVAILABLE else tk.DISABLED)
        self.start_button.pack(side=tk.LEFT)

        self.stop_button = ttk.Button(stream_frame, text="停止推流",
                                      command=self.stop_streaming,
                                      state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=8)

        # 添加日志显示区域
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=4, width=58)
        self.log_text.pack(expand=True, fill=tk.BOTH)
        self.log_text.config(state=tk.DISABLED)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(10, 0))

        # 配置网格权重
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # 如果没有UDP模块，显示警告
        if not UDP_MODULES_AVAILABLE:
            self.log_message("警告: UDP推流模块不可用，请确保安装了必要的依赖库")
            self.log_message("需要安装: pip install opencv-python numpy mss")

    def refresh_source_list(self):
        """把 config_stream.yaml 中成功加载的源显示到下拉框。"""
        self.source_id_by_label.clear()
        self.source_type_by_id.clear()

        if not UDP_MODULES_AVAILABLE or streamer is None:
            self.source_combo.configure(values=(), state=tk.DISABLED)
            self.switch_source_button.configure(state=tk.DISABLED)
            self.screen_controls_frame.grid_remove()
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
                self.refresh_screen_controls()
                self.refresh_audio_controls()
            else:
                self.source_combo.configure(state=tk.DISABLED)
                self.switch_source_button.configure(state=tk.DISABLED)
                self.source_var.set("")
                self.screen_controls_frame.grid_remove()
                self.audio_controls_frame.grid_remove()
                self.log_message("没有成功加载的图像源，请检查 config_stream.yaml")
        except Exception as e:
            self.source_combo.configure(values=(), state=tk.DISABLED)
            self.switch_source_button.configure(state=tk.DISABLED)
            self.screen_controls_frame.grid_remove()
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
                self.refresh_screen_controls()
                self.refresh_audio_controls()
            else:
                messagebox.showerror("错误", f"图像源不存在或不可用: {source_id}")
                self.refresh_source_list()
        except Exception as e:
            messagebox.showerror("错误", f"切换图像源失败: {str(e)}")
            self.log_message(f"切换图像源失败: {str(e)}")

    def get_selected_source_id(self):
        return self.source_id_by_label.get(self.source_var.get())

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
            self.updating_audio_controls = True
            self.audio_effect_catalog = list(audio_ui.get('effects', []))
            self.audio_effect_meta = {item['id']: item for item in self.audio_effect_catalog}
            self.audio_effect_label_to_id = {item['label']: item['id'] for item in self.audio_effect_catalog}
            self.audio_effect_config = dict(config.get('effects', {}))
            self.audio_input_catalog = list(audio_ui.get('input_parameters', []))

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
            if self.audio_preset_var.get() not in self.audio_presets:
                self.audio_preset_var.set(names[0] if names else "")
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
            save_audio_preset(source_id, name, runtime_config)
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
            self.audio_presets = presets
            self.refresh_audio_controls()
            self.audio_preset_var.set(name)
            self.log_message(f"已应用音频组合预设: {name}")
            self.status_var.set(f"已应用音频预设: {name}")
        except Exception as e:
            messagebox.showerror("错误", f"应用音频预设失败: {str(e)}")
            self.log_message(f"应用音频预设失败: {str(e)}")
            self.refresh_audio_presets(source_id)

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
        """添加消息到日志框"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)  # 滚动到底部
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()  # 立即更新界面

    def on_udp_preset_selected(self, event=None):
        """下拉框选择后立即应用预设。"""
        self.apply_preset(self.preset_var.get(), restart_if_streaming=True)

    def update_preset_summary(self, preset_name):
        preset = self.presets.get(preset_name)
        if preset is None:
            self.preset_summary_var.set("当前参数不属于内置预设")
            return
        color = "RGB565 高清色彩" if preset['color_mode'] == 0 else "RGB332 节省带宽"
        interval_ms = preset['udp_interval'] * 1000
        self.preset_summary_var.set(
            f"{preset['resolution']} × {preset['resolution']} · {color} · "
            f"每包 {preset['lines_per_packet']} 行 · {interval_ms:g} ms"
        )

    def get_matching_preset(self, config):
        """返回与发送参数完全匹配的内置预设。"""
        resolution = config.get('resolution')
        if not isinstance(resolution, (list, tuple)) or len(resolution) != 2:
            return None
        try:
            lines = int(config.get('lines_per_packet'))
            interval = float(config.get('udp_interval'))
        except (TypeError, ValueError):
            return None

        for name, preset in self.presets.items():
            color = "rgb565" if preset['color_mode'] == 0 else "rgb332"
            if (
                list(resolution) == [preset['resolution'], preset['resolution']]
                and config.get('color_mode') == color
                and lines == preset['lines_per_packet']
                and abs(interval - preset['udp_interval']) < 1e-12
            ):
                return name
        return None

    def get_udp_form_config(self):
        """读取当前 UDP 表单；输入不完整时由调用者处理异常。"""
        return {
            'server_ip': self.entries['server_ip'].get(),
            'server_port': int(self.entries['server_port'].get()),
            'resolution': self.parse_resolution_string(self.entries['resolution'].get()),
            'color_mode': self.entries['color_mode'].get(),
            'lines_per_packet': int(self.entries['lines_per_packet'].get()),
            'udp_interval': float(self.entries['udp_interval'].get()),
        }

    def on_udp_parameter_edited(self, event=None):
        """手动修改传输参数后同步预设下拉框状态。"""
        if self.updating_udp_controls:
            return
        try:
            preset_name = self.get_matching_preset(self.get_udp_form_config())
        except (TypeError, ValueError):
            preset_name = None
        self.preset_var.set(preset_name or self.custom_preset_label)
        self.update_preset_summary(preset_name)

    def apply_preset(self, preset_name, restart_if_streaming=False):
        """应用预设；仅在原本正在推流时重启发送线程。"""
        preset = self.presets.get(preset_name)
        if preset is None:
            return

        was_streaming = self.streaming
        self.updating_udp_controls = True
        try:
            resolution_val = preset['resolution']
            self.entries['resolution'].set(f"[{resolution_val},{resolution_val}]")
            self.entries['color_mode'].set("rgb565" if preset['color_mode'] == 0 else "rgb332")

            self.entries['lines_per_packet'].delete(0, tk.END)
            self.entries['lines_per_packet'].insert(0, str(preset['lines_per_packet']))
            self.entries['udp_interval'].delete(0, tk.END)
            self.entries['udp_interval'].insert(0, str(preset['udp_interval']))
            self.preset_var.set(preset_name)
            self.update_preset_summary(preset_name)
        finally:
            self.updating_udp_controls = False

        self.log_message(f"已应用发送预设: {preset_name}")
        self.status_var.set(f"已应用发送预设: {preset_name}")
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
            if using_default_config:
                self.log_message("未找到有效的 UDP 配置，已选择预设5：120 高清色彩")

            # 填充表单
            self.updating_udp_controls = True
            try:
                self.entries['server_ip'].delete(0, tk.END)
                self.entries['server_ip'].insert(0, config.get('server_ip', self.default_config['server_ip']))
                self.entries['server_port'].delete(0, tk.END)
                self.entries['server_port'].insert(0, str(config.get('server_port', self.default_config['server_port'])))

                resolution = config.get('resolution', self.default_config['resolution'])
                self.entries['resolution'].set(f"[{resolution[0]},{resolution[1]}]")
                self.entries['color_mode'].set(config.get('color_mode', self.default_config['color_mode']))
                self.entries['lines_per_packet'].delete(0, tk.END)
                self.entries['lines_per_packet'].insert(
                    0, str(config.get('lines_per_packet', self.default_config['lines_per_packet']))
                )
                self.entries['udp_interval'].delete(0, tk.END)
                self.entries['udp_interval'].insert(
                    0, str(config.get('udp_interval', self.default_config['udp_interval']))
                )
            finally:
                self.updating_udp_controls = False

            preset_name = self.get_matching_preset(self.get_udp_form_config())
            if using_default_config and preset_name is None:
                preset_name = self.default_preset_name
                self.apply_preset(preset_name)
            self.preset_var.set(preset_name or self.custom_preset_label)
            self.update_preset_summary(preset_name)

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
        else:
            # 检查是否为正方形分辨率
            match = re.match(r'\[(\d+),(\d+)\]', res_text)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                if width != height:
                    errors.append("分辨率必须是正方形")

        # 验证color_mode
        color = self.entries['color_mode'].get()
        if color not in self.valid_values['color_mode']:
            errors.append("请选择有效的色彩模式")

        # 验证lines_per_packet - 修正范围为1-8
        try:
            lines = int(self.entries['lines_per_packet'].get())
            if not (1 <= lines <= 8):
                errors.append("每包行数必须在1-8之间")
            elif res_text in self.valid_resolution_strings and color in self.valid_values['color_mode']:
                width = self.parse_resolution_string(res_text)[0]
                color_mode = self.get_color_mode_code(color)
                try:
                    ESP32UDPHeader.validate_stream_config(width, color_mode, lines)
                except ValueError as exc:
                    errors.append(str(exc))
        except ValueError:
            errors.append("每包行数必须是整数")

        # 验证udp_interval
        try:
            interval = float(self.entries['udp_interval'].get())
            if not (0.0001 <= interval <= 0.1):
                errors.append("UDP发送间隔必须在0.0001到0.1之间")
        except ValueError:
            errors.append("UDP发送间隔必须是数字")

        return errors

    def parse_resolution_string(self, res_text):
        """解析分辨率字符串为列表"""
        match = re.match(r'\[(\d+),(\d+)\]', res_text)
        if match:
            return [int(match.group(1)), int(match.group(2))]
        return [240, 240]  # 默认值

    def get_resolution_code(self, width):
        """根据宽度获取分辨率代码"""
        if width == 240:
            return ESP32UDPHeader.RES_240  # 0
        elif width == 180:
            return ESP32UDPHeader.RES_180  # 1
        elif width == 120:
            return ESP32UDPHeader.RES_120  # 2
        else:
            return ESP32UDPHeader.RES_240  # 默认

    def get_color_mode_code(self, color_mode_str):
        """根据字符串获取颜色模式代码"""
        # 根据Header：COLOR_RGB565=0, COLOR_RGB332=1
        if color_mode_str == "rgb565":
            return ESP32UDPHeader.COLOR_RGB565  # 0
        else:
            return ESP32UDPHeader.COLOR_RGB332  # 1

    def save_config(self):
        """保存固定位置的 UDP 配置文件。"""
        errors = self.validate_inputs()
        if errors:
            messagebox.showerror("输入错误", "\n".join(errors))
            return

        try:
            config = self.get_udp_form_config()
            preset_name = self.get_matching_preset(config)
            if preset_name:
                config['preset'] = preset_name

            # 保存到文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            self.log_message(f"UDP 配置已保存: {self.config_file}")
            self.status_var.set(f"UDP 配置已保存: {self.config_file}")
            messagebox.showinfo("成功", "UDP 发送配置已保存")

        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {str(e)}")
            self.log_message(f"保存配置文件失败: {str(e)}")
            self.status_var.set("保存配置文件失败")

    def reset_to_default(self):
        """恢复预设5，同时保留用户已填写的 ESP32 地址。"""
        self.apply_preset(self.default_preset_name, restart_if_streaming=True)

    def show_yaml(self):
        """显示当前配置的YAML格式"""
        try:
            config = self.get_udp_form_config()
            preset_name = self.get_matching_preset(config)
            if preset_name:
                config['preset'] = preset_name

            # 生成YAML字符串
            yaml_str = yaml.safe_dump(
                config,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

            # 显示在弹窗中
            popup = tk.Toplevel(self.root)
            popup.title("YAML 内容预览")
            popup.geometry("400x300")

            text_widget = tk.Text(popup, wrap=tk.WORD)
            text_widget.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

            text_widget.insert(tk.END, yaml_str)
            text_widget.config(state=tk.DISABLED)

            ttk.Button(popup, text="关闭", command=popup.destroy).pack(pady=5)

        except Exception as e:
            messagebox.showerror("错误", f"生成YAML失败: {str(e)}")

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

        # 解析分辨率
        res_text = self.entries['resolution'].get()
        resolution_list = self.parse_resolution_string(res_text)
        width = resolution_list[0]

        # 获取其他配置
        color_mode_str = self.entries['color_mode'].get()
        lines_per_packet = int(self.entries['lines_per_packet'].get())
        udp_interval = float(self.entries['udp_interval'].get())

        # 开始推流线程
        self.streaming = True
        stop_event = threading.Event()
        self.stream_stop_event = stop_event
        self.stream_thread = threading.Thread(
            target=self.stream_udp_data,
            args=(server_ip, server_port, width, color_mode_str, lines_per_packet, udp_interval, stop_event),
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

        # 启用开始按钮，禁用停止按钮
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

        self.log_message("停止推流")
        self.status_var.set("推流已停止")

    def bgr_to_rgb332_cv2_style(self, bgr_image):
        """类似OpenCV风格的RGB332转换"""
        b, g, r = cv2.split(bgr_image)
        r_332 = (r >> 5) & 0x07
        g_332 = (g >> 5) & 0x07
        b_332 = (b >> 6) & 0x03
        return (r_332 << 5) | (g_332 << 2) | b_332

    def stream_udp_data(self, server_ip, server_port, width, color_mode_str, lines_per_packet, udp_interval, stop_event):
        """UDP推流线程函数"""
        try:
            # 初始化UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock = sock

            # 初始化屏幕捕获
            # cap = ScreenCaptureCV()

            # 设置分辨率
            height = width

            # 获取分辨率代码
            resolution_code = self.get_resolution_code(width)

            # 获取颜色模式代码
            color_mode_code = self.get_color_mode_code(color_mode_str)

            # MTU and the ESP32 post-scale line buffer both constrain packet height.
            ESP32UDPHeader.validate_stream_config(width, color_mode_code, lines_per_packet)

            self.log_message(f"开始推流: 分辨率={width}x{height}, 颜色模式={color_mode_str}")
            self.log_message(
                f"Header参数: 分辨率代码={resolution_code}, 颜色代码={color_mode_code}, 每包行数={lines_per_packet}")

            last_frame_time = time.perf_counter()
            stats_started = time.perf_counter()
            stats_frames = 0
            stats_packets = 0
            stats_bytes = 0
            while not stop_event.is_set():
                try:
                    # 捕获屏幕
                    # sc = cap.capture_window_by_title("原神", mss_mode=False)
                    sc = streamer.get_frame()  # 调用这个接口,不关心流来自于哪里，只需要返回一张任意大小的图片
                    # Do not retransmit the same source frame under a new frame_id.
                    if sc is None:
                        if time.perf_counter() - last_frame_time > 5:
                            time.sleep(0.1)  # 超过5秒没数据，休息
                        else:
                            time.sleep(0.001)
                        continue

                    last_frame_time = time.perf_counter()

                    # 调整大小
                    if sc.shape[0] != height or sc.shape[1] != width:
                        sc = cv2.resize(sc, (width, height))

                    # 转换颜色模式
                    if color_mode_code == ESP32UDPHeader.COLOR_RGB332:  # 1
                        # RGB332转换
                        rgb = self.bgr_to_rgb332_cv2_style(sc)
                    else:  # ESP32UDPHeader.COLOR_RGB565 = 0
                        # RGB565转换
                        rgb = cv2.cvtColor(sc, cv2.COLOR_BGR2BGR565)

                    with self.frame_id_lock:
                        self.frame_id = (self.frame_id + 1) & 0xFFFF
                        frame_id = self.frame_id
                    frame_blob = np.ascontiguousarray(rgb).tobytes()
                    row_bytes = width * (2 if color_mode_code == ESP32UDPHeader.COLOR_RGB565 else 1)
                    next_packet_at = time.perf_counter()

                    # 发送数据
                    for y in range(0, height, lines_per_packet):
                        remaining = next_packet_at - time.perf_counter()
                        if remaining > 0:
                            time.sleep(remaining)

                        lines = min(lines_per_packet, height - y)

                        # The converted frame is contiguous, so packetization only slices bytes.
                        offset = y * row_bytes
                        payload = frame_blob[offset:offset + lines * row_bytes]

                        # 创建Header
                        header = ESP32UDPHeader.make_header(
                            frame_id=frame_id,
                            y_start=y,
                            resolution=resolution_code,
                            color_mode=color_mode_code,
                            line_count=lines
                        )

                        # 发送数据包
                        datagram = header + payload
                        sock.sendto(datagram, (server_ip, server_port))
                        stats_packets += 1
                        stats_bytes += len(datagram)
                        next_packet_at += udp_interval

                        # 检查是否应该停止
                        if stop_event.is_set():
                            break

                    stats_frames += 1
                    now = time.perf_counter()
                    elapsed = now - stats_started
                    if elapsed >= 2.0:
                        self.log_message(
                            f"发送统计: {stats_frames / elapsed:.1f} FPS, "
                            f"{stats_packets / elapsed:.0f} 包/秒, "
                            f"{stats_bytes * 8 / elapsed / 1_000_000:.2f} Mbit/s"
                        )
                        stats_started = now
                        stats_frames = stats_packets = stats_bytes = 0

                except Exception as e:
                    self.log_message(f"推流错误: {str(e)}")
                    time.sleep(1)  # 出错后等待1秒

            # 关闭socket
            sock.close()
            self.sock = None

        except Exception as e:
            self.log_message(f"推流线程错误: {str(e)}")
            # 在主线程中更新按钮状态
            self.root.after(0, lambda: self.stop_button.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.status_var.set("推流出错"))

    def on_closing(self):
        """窗口关闭时的处理"""
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
