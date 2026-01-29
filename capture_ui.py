import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yaml
import os
from datetime import datetime
from capture.screen_capture_cv import ScreenCaptureCV
from PIL import Image, ImageTk
import cv2

# 导入截图工具
class CaptureConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("截图参数配置工具")
        self.root.geometry("900x700")

        # 配置存储相关
        self.configs_dir = "capture_configs"
        self.current_config = {}
        self.configs = {}  # 存储所有配置 {配置名: 配置内容}

        # 创建配置目录
        if not os.path.exists(self.configs_dir):
            os.makedirs(self.configs_dir)

        # 默认配置
        self.default_config = {
            'capture_mode': 'title',
            'capture_region': [0, 0, 240, 240],
            'capture_title': '原神',
            'remove_title_bar': 0,
            'mss_mode': 0,
            'monitor_index': 0
        }

        # 变量
        self.capture_mode_var = tk.StringVar(value='title')
        self.capture_title_var = tk.StringVar(value='原神')
        self.remove_title_bar_var = tk.IntVar(value=0)
        self.mss_mode_var = tk.IntVar(value=0)
        self.monitor_index_var = tk.IntVar(value=0)

        # 截图区域变量
        self.region_left_var = tk.StringVar(value='0')
        self.region_top_var = tk.StringVar(value='0')
        self.region_width_var = tk.StringVar(value='240')
        self.region_height_var = tk.StringVar(value='240')

        # 配置选择变量
        self.selected_config_var = tk.StringVar()

        # 初始化UI
        self.setup_ui()

        # 加载现有配置
        self.load_all_configs()

        # 更新UI显示
        self.update_ui_from_config()

    def setup_ui(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置列权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # 配置文件管理区域
        config_frame = ttk.LabelFrame(main_frame, text="配置文件管理", padding="10")
        config_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # 配置选择下拉框
        ttk.Label(config_frame, text="选择配置:").grid(row=0, column=0, padx=(0, 5))
        self.config_combo = ttk.Combobox(config_frame, textvariable=self.selected_config_var, width=30)
        self.config_combo.grid(row=0, column=1, padx=(0, 10))
        self.config_combo.bind('<<ComboboxSelected>>', self.on_config_selected)

        # 配置管理按钮
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=0, column=2, padx=(10, 0))

        ttk.Button(btn_frame, text="新建", command=self.new_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="保存", command=self.save_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="另存为", command=self.save_config_as).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", command=self.delete_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="刷新列表", command=self.load_all_configs).pack(side=tk.LEFT, padx=2)

        # 参数设置区域
        params_frame = ttk.LabelFrame(main_frame, text="截图参数设置", padding="15")
        params_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # 截图模式
        row = 0
        ttk.Label(params_frame, text="截图模式:").grid(row=row, column=0, sticky=tk.W, pady=5)
        mode_frame = ttk.Frame(params_frame)
        mode_frame.grid(row=row, column=1, columnspan=3, sticky=tk.W, pady=5)

        ttk.Radiobutton(mode_frame, text="按窗口标题", variable=self.capture_mode_var,
                        value='title', command=self.on_mode_changed).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="全屏截图", variable=self.capture_mode_var,
                        value='full', command=self.on_mode_changed).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="指定区域", variable=self.capture_mode_var,
                        value='region', command=self.on_mode_changed).pack(side=tk.LEFT, padx=5)

        # 窗口标题设置
        row += 1
        self.title_label = ttk.Label(params_frame, text="窗口标题:")
        self.title_label.grid(row=row, column=0, sticky=tk.W, pady=5)
        self.title_entry = ttk.Entry(params_frame, textvariable=self.capture_title_var, width=40)
        self.title_entry.grid(row=row, column=1, columnspan=3, sticky=tk.W, pady=5)

        # 截图区域设置
        row += 1
        self.region_frame = ttk.LabelFrame(params_frame, text="截图区域 (left, top, width, height)")
        self.region_frame.grid(row=row, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=5, padx=5)

        ttk.Label(self.region_frame, text="Left:").grid(row=0, column=0, padx=(5, 2))
        ttk.Entry(self.region_frame, textvariable=self.region_left_var, width=8).grid(row=0, column=1, padx=2)

        ttk.Label(self.region_frame, text="Top:").grid(row=0, column=2, padx=(10, 2))
        ttk.Entry(self.region_frame, textvariable=self.region_top_var, width=8).grid(row=0, column=3, padx=2)

        ttk.Label(self.region_frame, text="Width:").grid(row=0, column=4, padx=(10, 2))
        ttk.Entry(self.region_frame, textvariable=self.region_width_var, width=8).grid(row=0, column=5, padx=2)

        ttk.Label(self.region_frame, text="Height:").grid(row=0, column=6, padx=(10, 2))
        ttk.Entry(self.region_frame, textvariable=self.region_height_var, width=8).grid(row=0, column=7, padx=2)

        ttk.Button(self.region_frame, text="选择区域", command=self.select_region).grid(row=0, column=8, padx=(20, 5))

        # 其他选项
        row += 1
        ttk.Checkbutton(params_frame, text="移除标题栏", variable=self.remove_title_bar_var).grid(
            row=row, column=0, sticky=tk.W, pady=5)

        ttk.Checkbutton(params_frame, text="使用MSS模式", variable=self.mss_mode_var).grid(
            row=row, column=1, sticky=tk.W, pady=5)

        ttk.Label(params_frame, text="显示器索引:").grid(row=row, column=2, sticky=tk.W, pady=5, padx=(10, 0))
        ttk.Spinbox(params_frame, from_=0, to=10, textvariable=self.monitor_index_var, width=8).grid(
            row=row, column=3, sticky=tk.W, pady=5)

        # 预览区域
        preview_frame = ttk.LabelFrame(main_frame, text="截图预览", padding="10")
        preview_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(10, 0), pady=(0, 10))

        # 创建画布用于显示截图
        self.canvas = tk.Canvas(preview_frame, width=400, height=300, bg='gray')
        self.canvas.pack()

        # 测试按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))

        ttk.Button(btn_frame, text="测试截图", command=self.test_capture).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="应用配置", command=self.apply_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="重置为默认", command=self.reset_to_default).pack(side=tk.LEFT, padx=5)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        # 初始显示模式相关控件
        self.on_mode_changed()

    def on_mode_changed(self):
        """根据选择的截图模式显示/隐藏相关控件"""
        mode = self.capture_mode_var.get()

        # 窗口标题相关
        if mode == 'title':
            self.title_label.config(state='normal')
            self.title_entry.config(state='normal')
        else:
            self.title_label.config(state='disabled')
            self.title_entry.config(state='disabled')

        # 截图区域相关
        if mode == 'region':
            self.region_frame.grid()
        else:
            self.region_frame.grid_remove()

    def select_region(self):
        """打开区域选择工具"""
        self.status_var.set("请拖动鼠标选择截图区域...")
        self.root.withdraw()  # 隐藏主窗口

        # 创建区域选择窗口
        region_selector = tk.Toplevel(self.root)
        region_selector.title("选择截图区域")
        region_selector.attributes('-fullscreen', True)
        region_selector.attributes('-alpha', 0.3)
        region_selector.config(bg='black')

        # 创建Canvas用于绘制选择框
        canvas = tk.Canvas(region_selector, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        # 创建选择框
        self.selection_rect = None
        self.start_x = None
        self.start_y = None

        def on_button_press(event):
            self.start_x = event.x
            self.start_y = event.y
            self.selection_rect = canvas.create_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y,
                outline='red', width=2, fill='', dash=(4, 4)
            )

        def on_mouse_drag(event):
            if self.selection_rect:
                canvas.coords(self.selection_rect,
                              self.start_x, self.start_y,
                              event.x, event.y)

        def on_button_release(event):
            # 计算区域
            x1, y1, x2, y2 = self.start_x, self.start_y, event.x, event.y
            left = min(x1, x2)
            top = min(y1, y2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)

            # 更新UI
            self.region_left_var.set(str(left))
            self.region_top_var.set(str(top))
            self.region_width_var.set(str(width))
            self.region_height_var.set(str(height))

            # 恢复主窗口
            region_selector.destroy()
            self.root.deiconify()
            self.status_var.set(f"已选择区域: {left}, {top}, {width}, {height}")

        def cancel_selection(event=None):
            region_selector.destroy()
            self.root.deiconify()
            self.status_var.set("区域选择已取消")

        # 绑定事件到Canvas
        canvas.bind('<Button-1>', on_button_press)
        canvas.bind('<B1-Motion>', on_mouse_drag)
        canvas.bind('<ButtonRelease-1>', on_button_release)
        canvas.bind('<Escape>', cancel_selection)

        # 添加说明标签
        label = tk.Label(canvas, text="拖动鼠标选择区域，按ESC取消",
                         bg='yellow', fg='black', font=('Arial', 12))
        canvas.create_window(canvas.winfo_screenwidth() // 2, 30, window=label)

    def load_all_configs(self):
        """加载所有配置文件"""
        self.configs.clear()
        config_files = []

        # 扫描配置目录
        if os.path.exists(self.configs_dir):
            for file in os.listdir(self.configs_dir):
                if file.endswith('.yaml') or file.endswith('.yml'):
                    config_name = os.path.splitext(file)[0]
                    config_path = os.path.join(self.configs_dir, file)

                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config_data = yaml.safe_load(f)
                        self.configs[config_name] = config_data
                        config_files.append(config_name)
                    except Exception as e:
                        print(f"加载配置文件 {file} 时出错: {e}")

        # 更新下拉框
        self.config_combo['values'] = config_files

        if config_files:
            self.config_combo.set(config_files[0])
            self.on_config_selected()

    def on_config_selected(self, event=None):
        """当选择配置时加载配置"""
        config_name = self.selected_config_var.get()
        if config_name and config_name in self.configs:
            self.current_config = self.configs[config_name].copy()
            self.update_ui_from_config()
            self.status_var.set(f"已加载配置: {config_name}")

    def update_ui_from_config(self):
        """从当前配置更新UI"""
        config = self.current_config

        self.capture_mode_var.set(config.get('capture_mode', 'title'))
        self.capture_title_var.set(config.get('capture_title', '原神'))
        self.remove_title_bar_var.set(config.get('remove_title_bar', 0))
        self.mss_mode_var.set(config.get('mss_mode', 0))
        self.monitor_index_var.set(config.get('monitor_index', 0))

        region = config.get('capture_region', [0, 0, 240, 240])
        if len(region) == 4:
            self.region_left_var.set(str(region[0]))
            self.region_top_var.set(str(region[1]))
            self.region_width_var.set(str(region[2]))
            self.region_height_var.set(str(region[3]))

        self.on_mode_changed()

    def get_config_from_ui(self):
        """从UI获取当前配置"""
        try:
            config = {
                'capture_mode': self.capture_mode_var.get(),
                'capture_region': [
                    int(self.region_left_var.get() or 0),
                    int(self.region_top_var.get() or 0),
                    int(self.region_width_var.get() or 240),
                    int(self.region_height_var.get() or 240)
                ],
                'capture_title': self.capture_title_var.get(),
                'remove_title_bar': self.remove_title_bar_var.get(),
                'mss_mode': self.mss_mode_var.get(),
                'monitor_index': self.monitor_index_var.get(),
                'last_modified': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return config
        except ValueError:
            messagebox.showerror("错误", "区域参数必须为整数")
            return None

    def new_config(self):
        """创建新配置"""
        config_name = tk.simpledialog.askstring("新建配置", "请输入配置名称:", parent=self.root)
        if config_name:
            if config_name in self.configs:
                if not messagebox.askyesno("确认", "配置已存在，是否覆盖?"):
                    return

            # 使用当前UI设置作为新配置
            self.current_config = self.get_config_from_ui()
            if self.current_config is None:
                return
            self.configs[config_name] = self.current_config.copy()

            # 保存到文件
            self.save_config_to_file(config_name)
            self.load_all_configs()
            self.selected_config_var.set(config_name)
            self.status_var.set(f"已创建新配置: {config_name}")

    def save_config(self):
        """保存当前配置"""
        config_name = self.selected_config_var.get()
        if not config_name:
            messagebox.showwarning("警告", "请选择或创建一个配置")
            return

        # 更新当前配置
        self.current_config = self.get_config_from_ui()
        if self.current_config is None:
            return
        self.configs[config_name] = self.current_config.copy()

        # 保存到文件
        self.save_config_to_file(config_name)
        self.status_var.set(f"已保存配置: {config_name}")

    def save_config_as(self):
        """另存为配置"""
        config_name = tk.simpledialog.askstring("另存为", "请输入新的配置名称:", parent=self.root)
        if config_name:
            self.current_config = self.get_config_from_ui()
            if self.current_config is None:
                return
            self.configs[config_name] = self.current_config.copy()

            # 保存到文件
            self.save_config_to_file(config_name)
            self.load_all_configs()
            self.selected_config_var.set(config_name)
            self.status_var.set(f"已另存为配置: {config_name}")

    def save_config_to_file(self, config_name):
        """保存配置到YAML文件"""
        config_path = os.path.join(self.configs_dir, f"{config_name}.yaml")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.current_config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {e}")

    def delete_config(self):
        """删除当前配置"""
        config_name = self.selected_config_var.get()
        if not config_name:
            messagebox.showwarning("警告", "请选择一个配置")
            return

        if messagebox.askyesno("确认", f"确定要删除配置 '{config_name}' 吗?"):
            config_path = os.path.join(self.configs_dir, f"{config_name}.yaml")
            if os.path.exists(config_path):
                os.remove(config_path)

            if config_name in self.configs:
                del self.configs[config_name]

            self.load_all_configs()
            self.current_config = {}
            self.status_var.set(f"已删除配置: {config_name}")

    def test_capture(self):
        """测试截图"""
        try:
            config = self.get_config_from_ui()
            if config is None:
                return

            img = None

            if config['capture_mode'] == 'title':
                img = ScreenCaptureCV.capture_window_by_title(
                    window_title=config['capture_title'],
                    remove_title_bar=bool(config['remove_title_bar']),
                    mss_mode=bool(config['mss_mode'])
                )
            elif config['capture_mode'] == 'full':
                img = ScreenCaptureCV.capture_fullscreen(
                    mss_mode=bool(config['mss_mode']),
                    monitor_index=config['monitor_index']
                )
            elif config['capture_mode'] == 'region':
                x, y, w, h = config['capture_region']
                img = ScreenCaptureCV.capture_region(
                    x, y, w, h,
                    mss_mode=bool(config['mss_mode']),
                    monitor_index=config['monitor_index']
                )

            if img is not None:
                self.display_image(img)
                self.status_var.set("截图成功!")
            else:
                self.status_var.set("截图失败!")

        except Exception as e:
            messagebox.showerror("截图错误", str(e))
            self.status_var.set(f"截图失败: {e}")

    def display_image(self, img):
        """在画布上显示图像"""
        # 调整图像大小以适应画布
        canvas_width = 400
        canvas_height = 300

        # 保持宽高比
        h, w = img.shape[:2]
        scale = min(canvas_width / w, canvas_height / h)
        new_w = int(w * scale)
        new_h = int(h * scale)

        # 调整大小
        resized_img = cv2.resize(img, (new_w, new_h))

        # 转换为RGB
        if len(resized_img.shape) == 3:
            rgb_img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2RGB)
        else:
            rgb_img = cv2.cvtColor(resized_img, cv2.COLOR_GRAY2RGB)

        # 转换为PhotoImage
        pil_img = Image.fromarray(rgb_img)
        photo = ImageTk.PhotoImage(pil_img)

        # 清空画布并显示图像
        self.canvas.delete("all")
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=photo, anchor=tk.CENTER)
        self.canvas.image = photo  # 保持引用

    def apply_config(self):
        """应用当前配置"""
        config = self.get_config_from_ui()
        if config is None:
            return
        self.current_config = config
        self.status_var.set("配置已应用")

        # 这里可以添加调用截图功能的代码
        # 例如: capture_with_config(self.current_config)

    def reset_to_default(self):
        """重置为默认配置"""
        self.current_config = self.default_config.copy()
        self.update_ui_from_config()
        self.status_var.set("已重置为默认配置")

    def get_current_config(self):
        """获取当前配置"""
        return self.get_config_from_ui()


def main():
    root = tk.Tk()
    app = CaptureConfigGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()