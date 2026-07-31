import tkinter as tk
from tkinter import ttk, messagebox, filedialog
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
    from  capture.config import get_streamer
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
    AUDIO_EFFECTS = {
        'draw_waveform': '波形',
        'draw_spectrum_bar': '频谱柱',
        'draw_spectrum_circular1': '三重圆环',
        'draw_spectrum_circular2': '红蓝电离',
        'draw_spectrum_circular3': '双向律动',
        'draw_particles': '粒子',
    }
    AUDIO_PRESETS = {
        '纯波形': {'draw_waveform'},
        '频谱柱': {'draw_spectrum_bar'},
        '三重圆环': {'draw_spectrum_circular1'},
        '红蓝电离': {'draw_spectrum_circular2'},
        '双向律动': {'draw_spectrum_circular3'},
        '粒子频谱': {'draw_spectrum_bar', 'draw_particles'},
        '全效果': set(AUDIO_EFFECTS),
    }
    AUDIO_PARAMETERS = {
        'gain': ('灵敏度', 0.1, 4.0, 0.1, 1),
        'spectrum_smoothing': ('频谱平滑', 0.0, 0.95, 0.05, 2),
        'radius_smoothing': ('律动平滑', 0.0, 0.98, 0.02, 2),
        'base_radius': ('基础半径', 20, 100, 1, 0),
        'radius_expansion': ('律动幅度', 5, 100, 1, 0),
        'max_particles': ('粒子数量', 0, 500, 10, 0),
    }

    def __init__(self, root):
        print("==================================================================================================================")
        print("欢迎使用ESP32Holocubic ScreenShareUDP推流工具，本项目开源免费，地址是:https://github.com/tignioj/ESP32UDPScreenShareClient")
        print("配置文件路径在_internal/config_stream.yaml, 首次使用请查看README.md")
        print("==================================================================================================================")
        self.root = root
        self.root.title("YAML 配置文件编辑器V0.0.5")
        self.root.geometry("760x850")
        self.root.minsize(720, 760)

        # UDP推流相关
        self.streaming = False
        self.stream_thread = None
        self.sock = None

        # 默认配置文件
        self.config_file = "config.yaml"

        # 创建默认配置
        self.default_config = {
            'server_ip': "192.168.30.161",
            'server_port': 8888,
            'resolution': [240, 240],
            'color_mode': "rgb332",
            'lines_per_packet': 3,
            'udp_interval': 0.0002
        }

        # 预设配置 - 根据Header常量修正颜色模式值
        self.presets = {
            "预设1: 高清全彩": {
                'resolution': 240,  # ESP32UDPHeader.RES_240 = 0
                'color_mode': 0,  # ESP32UDPHeader.COLOR_RGB565 = 0
                'lines_per_packet': 3,
                'udp_interval': 0.0003
            },
            "预设2: 高清低彩": {
                'resolution': 240,  # ESP32UDPHeader.RES_240 = 0
                'color_mode': 1,  # ESP32UDPHeader.COLOR_RGB332 = 1
                'lines_per_packet': 6,
                'udp_interval': 0.0005
            },
            "预设3: 中清高彩": {
                'resolution': 180,  # ESP32UDPHeader.RES_180 = 1
                'color_mode': 0,  # ESP32UDPHeader.COLOR_RGB565 = 0
                'lines_per_packet': 4,
                'udp_interval': 0.0005
            },
            "预设4: 中清低彩": {
                'resolution': 180,  # ESP32UDPHeader.RES_180 = 1
                'color_mode': 1,  # ESP32UDPHeader.COLOR_RGB332 = 1
                # 'lines_per_packet': 8,
                # 'udp_interval': 0.001
                'lines_per_packet': 6,
                'udp_interval': 0.00075
            },
            "预设5: 低清高彩": {
                'resolution': 120,  # ESP32UDPHeader.RES_120 = 2
                'color_mode': 0,  # ESP32UDPHeader.COLOR_RGB565 = 0
                # 'lines_per_packet': 6,
                # 'udp_interval': 0.000945
                'lines_per_packet': 4,
                'udp_interval': 0.00075
            },
            "预设6: 低清低彩": {  # 新增预设6
                'resolution': 120,  # ESP32UDPHeader.RES_120 = 2
                'color_mode': 1,  # ESP32UDPHeader.COLOR_RGB332 = 1
                'lines_per_packet': 4,
                'udp_interval': 0.00075
            }
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
        self.preset_var = tk.StringVar(value="")

        # 图像源选择
        self.source_var = tk.StringVar(value="")
        self.source_id_by_label = {}
        self.source_type_by_id = {}

        # 音频可视化运行时控制。切换效果和滑块不会重启推流。
        self.audio_preset_var = tk.StringVar(value="自定义")
        self.audio_effect_vars = {
            name: tk.BooleanVar(value=False) for name in self.AUDIO_EFFECTS
        }
        self.audio_parameter_vars = {
            name: tk.DoubleVar(value=minimum)
            for name, (_, minimum, _, _, _) in self.AUDIO_PARAMETERS.items()
        }
        self.audio_parameter_value_vars = {
            name: tk.StringVar(value="") for name in self.AUDIO_PARAMETERS
        }
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

        # 文件选择部分
        file_frame = ttk.LabelFrame(main_frame, text="文件操作", padding="5")
        file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Button(file_frame, text="选择文件", command=self.select_file).grid(row=0, column=0, padx=5)
        ttk.Button(file_frame, text="新建文件", command=self.create_new_file).grid(row=0, column=1, padx=5)

        self.file_label = ttk.Label(file_frame, text=f"当前文件: {self.config_file}")
        self.file_label.grid(row=0, column=2, padx=20)

        # 预设配置框架 - 增加高度以容纳6个预设
        preset_frame = ttk.LabelFrame(main_frame, text="预设配置 (点击选择)", padding="5")
        preset_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # 创建预设单选按钮 - 调整为每行3个，共6个预设
        row = 0
        col = 0
        preset_names = list(self.presets.keys())

        for i, preset_name in enumerate(preset_names):
            rb = ttk.Radiobutton(
                preset_frame,
                text=preset_name,
                variable=self.preset_var,
                value=preset_name,
                command=lambda name=preset_name: self.apply_preset(name)
            )
            rb.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)
            col += 1
            if col >= 3:  # 每行3个
                col = 0
                row += 1

        # 配置项框架
        config_frame = ttk.LabelFrame(main_frame, text="配置参数", padding="10")
        config_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # 创建配置项输入框
        self.entries = {}
        row = 0

        # server_ip
        ttk.Label(config_frame, text="服务器IP:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.entries['server_ip'] = ttk.Entry(config_frame, width=30)
        self.entries['server_ip'].grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        row += 1

        # server_port
        ttk.Label(config_frame, text="服务器端口:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.entries['server_port'] = ttk.Entry(config_frame, width=30)
        self.entries['server_port'].grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        row += 1

        # resolution
        ttk.Label(config_frame, text="分辨率:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.entries['resolution'] = ttk.Combobox(config_frame,
                                                  values=self.valid_resolution_strings,
                                                  width=27, state="readonly")
        self.entries['resolution'].grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        row += 1

        # color_mode
        ttk.Label(config_frame, text="色彩模式:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.entries['color_mode'] = ttk.Combobox(config_frame,
                                                  values=self.valid_values['color_mode'],
                                                  width=27, state="readonly")
        self.entries['color_mode'].grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        row += 1

        # lines_per_packet - 修正为1-8范围
        ttk.Label(config_frame, text="每包行数:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.entries['lines_per_packet'] = ttk.Spinbox(config_frame, from_=1, to=15, width=27)
        self.entries['lines_per_packet'].grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        row += 1

        # udp_interval
        ttk.Label(config_frame, text="UDP发送间隔:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.entries['udp_interval'] = ttk.Entry(config_frame, width=30)
        self.entries['udp_interval'].grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2)
        ttk.Label(config_frame, text="(0.0001-0.1)").grid(row=row, column=2, sticky=tk.W, padx=5, pady=2)
        row += 1

        # 图像源切换
        source_frame = ttk.LabelFrame(main_frame, text="图像源", padding="5")
        source_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
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

        # 仅在选中 audio_visualization 源时显示。
        self.audio_controls_frame = ttk.LabelFrame(source_frame, text="音频视觉效果（实时生效）", padding="6")
        self.audio_controls_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(8, 0))
        self.audio_controls_frame.columnconfigure(1, weight=1)
        self.audio_controls_frame.columnconfigure(4, weight=1)

        ttk.Label(self.audio_controls_frame, text="效果组合:").grid(row=0, column=0, sticky=tk.W)
        self.audio_preset_combo = ttk.Combobox(
            self.audio_controls_frame,
            textvariable=self.audio_preset_var,
            values=['自定义', *self.AUDIO_PRESETS],
            state="readonly",
            width=16,
        )
        self.audio_preset_combo.grid(row=0, column=1, sticky=tk.W, padx=(5, 12))
        self.audio_preset_combo.bind("<<ComboboxSelected>>", self.on_audio_preset_selected)
        ttk.Label(self.audio_controls_frame, text="也可自由叠加:").grid(row=0, column=2, sticky=tk.W)

        effects_frame = ttk.Frame(self.audio_controls_frame)
        effects_frame.grid(row=0, column=3, columnspan=3, sticky=tk.W)
        for index, (name, label) in enumerate(self.AUDIO_EFFECTS.items()):
            ttk.Checkbutton(
                effects_frame,
                text=label,
                variable=self.audio_effect_vars[name],
                command=lambda effect=name: self.on_audio_effect_changed(effect),
            ).grid(row=index // 3, column=index % 3, sticky=tk.W, padx=(0, 8))

        for index, (name, (label, minimum, maximum, step, digits)) in enumerate(self.AUDIO_PARAMETERS.items()):
            row_index = 1 + index // 2
            column_index = (index % 2) * 3
            ttk.Label(self.audio_controls_frame, text=f"{label}:").grid(
                row=row_index, column=column_index, sticky=tk.W, pady=(5, 0)
            )
            scale = ttk.Scale(
                self.audio_controls_frame,
                from_=minimum,
                to=maximum,
                variable=self.audio_parameter_vars[name],
                command=lambda value, parameter=name: self.on_audio_parameter_changed(parameter, value),
            )
            scale.grid(row=row_index, column=column_index + 1, sticky=(tk.W, tk.E), padx=5, pady=(5, 0))
            ttk.Label(
                self.audio_controls_frame,
                textvariable=self.audio_parameter_value_vars[name],
                width=5,
                anchor=tk.E,
            ).grid(row=row_index, column=column_index + 2, sticky=tk.E, pady=(5, 0))

        self.audio_controls_frame.grid_remove()

        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重置为默认", command=self.reset_to_default).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="查看YAML", command=self.show_yaml).pack(side=tk.LEFT, padx=5)

        # 推流控制按钮
        stream_frame = ttk.Frame(main_frame)
        stream_frame.grid(row=5, column=0, columnspan=2, pady=10)

        self.start_button = ttk.Button(stream_frame, text="开始推流",
                                       command=self.start_streaming,
                                       state=tk.NORMAL if UDP_MODULES_AVAILABLE else tk.DISABLED)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(stream_frame, text="停止推流",
                                      command=self.stop_streaming,
                                      state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        # 添加日志显示区域
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=70)
        self.log_text.pack(expand=True, fill=tk.BOTH)
        self.log_text.config(state=tk.DISABLED)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        # 配置网格权重
        main_frame.columnconfigure(0, weight=1)
        config_frame.columnconfigure(1, weight=1)
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
                self.refresh_audio_controls()
            else:
                self.source_combo.configure(state=tk.DISABLED)
                self.switch_source_button.configure(state=tk.DISABLED)
                self.source_var.set("")
                self.audio_controls_frame.grid_remove()
                self.log_message("没有成功加载的图像源，请检查 config_stream.yaml")
        except Exception as e:
            self.source_combo.configure(values=(), state=tk.DISABLED)
            self.switch_source_button.configure(state=tk.DISABLED)
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
                self.refresh_audio_controls()
            else:
                messagebox.showerror("错误", f"图像源不存在或不可用: {source_id}")
                self.refresh_source_list()
        except Exception as e:
            messagebox.showerror("错误", f"切换图像源失败: {str(e)}")
            self.log_message(f"切换图像源失败: {str(e)}")

    def get_selected_source_id(self):
        return self.source_id_by_label.get(self.source_var.get())

    def refresh_audio_controls(self):
        """按当前音频源的真实运行时配置刷新控制面板。"""
        source_id = self.get_selected_source_id()
        if not source_id or self.source_type_by_id.get(source_id) != 'audio_visualization':
            self.audio_controls_frame.grid_remove()
            return

        try:
            info = streamer.get_source_info(source_id)
            config = info.get('config', {})
            self.updating_audio_controls = True
            for name, variable in self.audio_effect_vars.items():
                variable.set(bool(config.get(name, False)))
            for name, variable in self.audio_parameter_vars.items():
                if name in config:
                    variable.set(float(config[name]))
                self.update_audio_parameter_label(name, variable.get())
            self.audio_preset_var.set(self.find_matching_audio_preset())
            self.audio_controls_frame.grid()
        except Exception as e:
            self.audio_controls_frame.grid_remove()
            self.log_message(f"读取音频视觉参数失败: {str(e)}")
        finally:
            self.updating_audio_controls = False

    def find_matching_audio_preset(self):
        enabled = {
            name for name, variable in self.audio_effect_vars.items() if variable.get()
        }
        for preset_name, preset_effects in self.AUDIO_PRESETS.items():
            if enabled == preset_effects:
                return preset_name
        return '自定义'

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

    def on_audio_preset_selected(self, event=None):
        preset_name = self.audio_preset_var.get()
        if preset_name not in self.AUDIO_PRESETS:
            return
        enabled = self.AUDIO_PRESETS[preset_name]
        config = {}
        self.updating_audio_controls = True
        try:
            for name, variable in self.audio_effect_vars.items():
                value = name in enabled
                variable.set(value)
                config[name] = value
        finally:
            self.updating_audio_controls = False
        self.apply_audio_runtime_config(config)
        self.log_message(f"已切换音频视觉效果: {preset_name}")

    def on_audio_effect_changed(self, effect):
        self.audio_preset_var.set(self.find_matching_audio_preset())
        self.apply_audio_runtime_config({effect: self.audio_effect_vars[effect].get()})

    def update_audio_parameter_label(self, parameter, value):
        digits = self.AUDIO_PARAMETERS[parameter][4]
        self.audio_parameter_value_vars[parameter].set(f"{float(value):.{digits}f}")

    def on_audio_parameter_changed(self, parameter, value):
        _, minimum, maximum, step, digits = self.AUDIO_PARAMETERS[parameter]
        numeric_value = max(minimum, min(maximum, float(value)))
        numeric_value = round(numeric_value / step) * step
        if digits == 0:
            numeric_value = int(round(numeric_value))
        self.update_audio_parameter_label(parameter, numeric_value)
        self.apply_audio_runtime_config({parameter: numeric_value})

    def log_message(self, message):
        """添加消息到日志框"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)  # 滚动到底部
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()  # 立即更新界面

    def select_file(self):
        """选择YAML文件"""
        file_path = filedialog.askopenfilename(
            title="选择配置文件",
            filetypes=[("YAML文件", "*.yaml *.yml"), ("所有文件", "*.*")]
        )
        if file_path:
            self.config_file = file_path
            self.file_label.config(text=f"当前文件: {os.path.basename(file_path)}")
            self.load_config()

    def create_new_file(self):
        """创建新的配置文件"""
        file_path = filedialog.asksaveasfilename(
            title="创建新配置文件",
            defaultextension=".yaml",
            filetypes=[("YAML文件", "*.yaml"), ("所有文件", "*.*")]
        )
        if file_path:
            self.config_file = file_path
            self.file_label.config(text=f"当前文件: {os.path.basename(file_path)}")
            self.reset_to_default()
            self.save_config()

    def apply_preset(self, preset_name):
        """应用预设配置"""
        if preset_name in self.presets:
            preset = self.presets[preset_name]

            # 应用预设值
            resolution_val = preset['resolution']
            resolution_str = f"[{resolution_val},{resolution_val}]"
            self.entries['resolution'].set(resolution_str)

            color_mode_val = preset['color_mode']
            # 根据Header常量，0=rgb565, 1=rgb332
            color_mode_str = "rgb565" if color_mode_val == 0 else "rgb332"
            self.entries['color_mode'].set(color_mode_str)

            self.entries['lines_per_packet'].delete(0, tk.END)
            self.entries['lines_per_packet'].insert(0, str(preset['lines_per_packet']))

            self.entries['udp_interval'].delete(0, tk.END)
            self.entries['udp_interval'].insert(0, str(preset['udp_interval']))

            self.log_message(f"已应用预设: {preset_name}")
            self.status_var.set(f"已应用预设: {preset_name}")
            self.stop_button.invoke()
            time.sleep(0.1)
            self.start_button.invoke()


    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
            else:
                config = self.default_config.copy()
                self.status_var.set(f"文件不存在，已加载默认配置")
                self.log_message(f"文件不存在，已加载默认配置")

            # 填充表单
            self.entries['server_ip'].delete(0, tk.END)
            self.entries['server_ip'].insert(0, config.get('server_ip', ''))

            self.entries['server_port'].delete(0, tk.END)
            self.entries['server_port'].insert(0, str(config.get('server_port', '')))

            resolution = config.get('resolution', [240, 240])
            resolution_str = f"[{resolution[0]},{resolution[1]}]"
            self.entries['resolution'].set(resolution_str)

            self.entries['color_mode'].set(config.get('color_mode', 'rgb332'))

            self.entries['lines_per_packet'].delete(0, tk.END)
            self.entries['lines_per_packet'].insert(0, str(config.get('lines_per_packet', 3)))

            self.entries['udp_interval'].delete(0, tk.END)
            self.entries['udp_interval'].insert(0, str(config.get('udp_interval', 0.0002)))

            # 重置预设选择
            self.preset_var.set("")

            self.log_message(f"已加载配置文件: {self.config_file}")
            self.status_var.set(f"已加载配置文件: {self.config_file}")

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
        """保存配置文件"""
        errors = self.validate_inputs()
        if errors:
            messagebox.showerror("输入错误", "\n".join(errors))
            return

        try:
            # 构建配置字典
            config = {}

            config['server_ip'] = self.entries['server_ip'].get()
            config['server_port'] = int(self.entries['server_port'].get())

            # 解析resolution字符串为列表
            res_text = self.entries['resolution'].get()
            config['resolution'] = self.parse_resolution_string(res_text)

            config['color_mode'] = self.entries['color_mode'].get()
            config['lines_per_packet'] = int(self.entries['lines_per_packet'].get())
            config['udp_interval'] = float(self.entries['udp_interval'].get())

            # 保存到文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

            self.log_message(f"配置文件已保存: {self.config_file}")
            self.status_var.set(f"配置文件已保存: {self.config_file}")
            messagebox.showinfo("成功", "配置文件保存成功！")

        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {str(e)}")
            self.log_message(f"保存配置文件失败: {str(e)}")
            self.status_var.set("保存配置文件失败")

    def reset_to_default(self):
        """重置为默认值"""
        for key, value in self.default_config.items():
            if key in self.entries:
                if key == 'resolution':
                    self.entries[key].set(f"[{value[0]},{value[1]}]")
                elif key == 'color_mode':
                    self.entries[key].set(value)
                else:
                    self.entries[key].delete(0, tk.END)
                    self.entries[key].insert(0, str(value))

        # 重置预设选择
        self.preset_var.set("")

        self.log_message("已重置为默认值")
        self.status_var.set("已重置为默认值")

    def show_yaml(self):
        """显示当前配置的YAML格式"""
        try:
            # 构建配置字典
            config = {}
            config['server_ip'] = self.entries['server_ip'].get()
            config['server_port'] = int(self.entries['server_port'].get())

            res_text = self.entries['resolution'].get()
            config['resolution'] = self.parse_resolution_string(res_text)

            config['color_mode'] = self.entries['color_mode'].get()
            config['lines_per_packet'] = int(self.entries['lines_per_packet'].get())
            config['udp_interval'] = float(self.entries['udp_interval'].get())

            # 生成YAML字符串
            yaml_str = yaml.dump(config, default_flow_style=False, allow_unicode=True)

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
        self.stream_thread = threading.Thread(
            target=self.stream_udp_data,
            args=(server_ip, server_port, width, color_mode_str, lines_per_packet, udp_interval),
            daemon=True
        )
        self.stream_thread.start()

        self.log_message(f"开始推流到 {server_ip}:{server_port}")
        self.status_var.set("推流中...")

    def stop_streaming(self):
        """停止UDP推流"""
        self.streaming = False

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

    def stream_udp_data(self, server_ip, server_port, width, color_mode_str, lines_per_packet, udp_interval):
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

            # 检查lines_per_packet是否超出范围
            if lines_per_packet > 8:
                self.log_message(f"警告: 每包行数{lines_per_packet}超出Header限制(8)，将使用8")
                lines_per_packet = 8

            self.log_message(f"开始推流: 分辨率={width}x{height}, 颜色模式={color_mode_str}")
            self.log_message(
                f"Header参数: 分辨率代码={resolution_code}, 颜色代码={color_mode_code}, 每包行数={lines_per_packet}")

            frame_id = 0  # 这个暂时没什么用
            last_frame = None
            last_frame_time = time.time()
            while self.streaming:
                frame_id = (frame_id + 1) & 0xFFFF
                try:
                    # 捕获屏幕
                    # sc = cap.capture_window_by_title("原神", mss_mode=False)
                    sc = streamer.get_frame()  # 调用这个接口,不关心流来自于哪里，只需要返回一张任意大小的图片
                    # 如果是空白图片，5秒内返回上一张图片
                    if sc is None:
                        if time.time() - last_frame_time> 5:
                            time.sleep(0.1)  # 超过5秒没数据，休息
                            continue
                        if last_frame is None: continue
                        else: sc = last_frame
                    else:
                        last_frame_time = time.time()
                        last_frame = sc

                    # 调整大小
                    sc = cv2.resize(sc, (width, height))

                    # 转换颜色模式
                    if color_mode_code == ESP32UDPHeader.COLOR_RGB332:  # 1
                        # RGB332转换
                        rgb = self.bgr_to_rgb332_cv2_style(sc)
                    else:  # ESP32UDPHeader.COLOR_RGB565 = 0
                        # RGB565转换
                        rgb = cv2.cvtColor(sc, cv2.COLOR_BGR2BGR565)

                    # 发送数据
                    for y in range(0, height, lines_per_packet):
                        start_time = time.time()
                        lines = min(lines_per_packet, height - y)

                        # 准备payload
                        if color_mode_code == ESP32UDPHeader.COLOR_RGB332:
                            # RGB332每个像素1字节
                            payload = rgb[y:y + lines, :].astype(np.uint8).flatten().tobytes()
                        else:
                            # RGB565每个像素2字节
                            payload = rgb[y:y + lines, :].flatten().tobytes()

                        # 创建Header
                        header = ESP32UDPHeader.make_header(
                            frame_id=frame_id,
                            y_start=y,
                            resolution=resolution_code,
                            color_mode=color_mode_code,
                            line_count=lines
                        )

                        # 发送数据包
                        sock.sendto(header + payload, (server_ip, server_port))

                        # 控制发送频率
                        time.sleep(udp_interval)

                        # 检查是否应该停止
                        if not self.streaming:
                            break

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
