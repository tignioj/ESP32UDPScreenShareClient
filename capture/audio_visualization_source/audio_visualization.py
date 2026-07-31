import random
import time
import sounddevice as sd
import numpy as np
import cv2
from typing import Optional, Tuple


class AudioVisualizer:
    """
    音频可视化类，将音频信号转换为可视化图像帧
    对外暴露get_frame接口供其他类调用
    """

    def __init__(self, width: int = 800, height: int = 600, sample_rate: int = 48000,
                 block_size: int = 512, channels: int = 2, target_device: str = "CABLE Output"):
        """
        初始化音频可视化器

        Args:
            width: 输出图像宽度
            height: 输出图像高度
            sample_rate: 音频采样率
            block_size: 音频块大小
            channels: 音频通道数
            target_device: 目标音频设备名称
        """
        # 配置参数
        self.SAMPLE_RATE = sample_rate
        self.BLOCK_SIZE = block_size
        self.WIDTH = width
        self.HEIGHT = height
        self.CHANNELS = channels
        self.NOISE_FLOOR = 1e-8  # 可调，VB-Cable 通常在 1e-4 ~ 1e-3
        self.gain = 1.0

        # 音频数据缓冲区
        self.window = np.hanning(self.BLOCK_SIZE)
        self.spectrum = np.zeros(self.BLOCK_SIZE // 2 + 1, dtype=np.float32)
        self.time_data = np.zeros(self.BLOCK_SIZE, dtype=np.float32)
        self.smoothed_spectrum = np.zeros(self.BLOCK_SIZE // 2 + 1, dtype=np.float32)
        self.smoothing_factor = 0.5
        # Each effect keeps its own band smoothing so combinations do not affect
        # one another.  Waterfall and peak state are allocated for the 240x240
        # output but also work with other canvas sizes.
        self.effect_smoothing = {}
        self.neon_peaks = np.zeros(48, dtype=np.float32)
        self.waterfall_history = np.zeros((max(32, self.HEIGHT // 2), 64), dtype=np.float32)

        # 律动检测参数
        self.base_radius = min(self.WIDTH, self.HEIGHT) // 4  # 基础半径
        self.max_radius_expansion = min(self.WIDTH, self.HEIGHT) // 8  # 最大扩张半径
        self.energy_history = np.zeros(10)  # 能量历史记录
        self.energy_index = 0
        self.current_radius = self.base_radius
        self.radius_smoothing = 0.9  # 半径平滑因子

        # 粒子系统
        self.particles = []
        self.max_particles = 200

        # 音频流
        self.stream = None
        self.device_id = self._find_audio_device(target_device)
        self._initialize_audio_stream()

        # 可视化参数
        self.background = self._create_gradient_background()

        # 绘制时间
        self.last_sound_time = time.time()

    def _find_audio_device(self, target_name: str) -> int:
        """查找音频设备"""
        for i, dev in enumerate(sd.query_devices()):
            if target_name in dev['name']:
                print(f"使用设备: {sd.query_devices()[i]['name']}")
                return i
        # print("未找到指定设备，使用默认输入设备")
        print(f"未找到指定设备{target_name}，音频可视化不可用！请确保安装了此驱动https://vb-audio.com/Cable/, 并设置系统声音输出为CableInput")
        return None

    def _should_show_screen_saver(self):
        return None

    def _audio_callback(self, indata, frames, time, status):
        """音频回调函数，处理输入的音频数据[1](@ref)"""
        if status:
            print(f"音频流状态: {status}")

        # 取左声道数据
        mono = indata[:, 0].copy() * self.gain
        energy = np.mean(mono ** 2)
        if energy < self.NOISE_FLOOR:
            self.spectrum[:] = 0
            self.time_data[:] = 0
            self.current_radius = self.base_radius
            self.smoothed_spectrum = np.zeros(self.BLOCK_SIZE // 2 + 1, dtype=np.float32)
            return
        # 时域数据用于波形显示
        self.time_data = mono

        # 频域数据用于频谱显示[1](@ref)
        fft = np.abs(np.fft.rfft(mono * self.window))
        self.spectrum = fft

        # 计算当前音频能量（用于律动检测）
        current_energy = np.sum(mono ** 2) / len(mono)

        # 更新能量历史记录
        self.energy_history[self.energy_index] = current_energy
        self.energy_index = (self.energy_index + 1) % len(self.energy_history)

        # 计算平均能量和峰值能量
        avg_energy = np.mean(self.energy_history)
        peak_energy = np.max(self.energy_history)

        # 避免除零错误
        if peak_energy > avg_energy and peak_energy > 0:
            # 计算能量比率（0到1之间）
            energy_ratio = min(1.0, (current_energy - avg_energy) / (peak_energy - avg_energy))

            # 计算目标半径（基于能量比率）
            target_radius = self.base_radius + int(energy_ratio * self.max_radius_expansion)

            # 平滑半径变化
            self.current_radius = (self.radius_smoothing * self.current_radius +
                                   (1 - self.radius_smoothing) * target_radius)

    def _initialize_audio_stream(self):
        """初始化音频流"""
        try:
            self.stream = sd.InputStream(
                device=self.device_id,
                channels=self.CHANNELS,
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_SIZE,
                callback=self._audio_callback
            )
            self.stream.start()
        except Exception as e:
            print(f"音频流初始化失败: {e}")
            raise RuntimeError(f"无法启动音频流: {e}")

    def _create_gradient_background(self) -> np.ndarray:
        """创建渐变背景"""
        background = np.zeros((self.HEIGHT, self.WIDTH, 3), dtype=np.uint8)
        # background.fill(255)
        # for y in range(self.HEIGHT):
            # blue = int(10 + (y / self.HEIGHT) * 30)
            # green = int(5 + (y / self.HEIGHT) * 20)
            # red = int(5 + (y / self.HEIGHT) * 15)
            # background[y, :] = (blue, green, red)
        return background

    def _draw_spectrum_bars(self, img: np.ndarray) -> None:
        """绘制频谱柱状图"""
        num_bars = 120
        max_index = min(len(self.spectrum), num_bars)
        spec = self.spectrum[:max_index].copy()

        # 平滑处理
        smoothed_display = self.smoothed_spectrum[:max_index]
        if len(smoothed_display) != len(spec):
            self.smoothed_spectrum = np.zeros_like(self.spectrum)
            smoothed_display = self.smoothed_spectrum[:max_index]

        smoothed_display = (self.smoothing_factor * smoothed_display +
                            (1 - self.smoothing_factor) * spec)
        self.smoothed_spectrum[:max_index] = smoothed_display

        if smoothed_display.max() > 0:
            spec_normalized = smoothed_display / smoothed_display.max()
        else:
            spec_normalized = smoothed_display

        bar_width = max(1, self.WIDTH // num_bars)

        for i in range(min(num_bars, len(spec_normalized))):
            bar_height = int(spec_normalized[i] * self.HEIGHT * 0.8)
            if bar_height > 0:
                color_ratio = i / num_bars
                blue = int(255 * (1 - color_ratio))
                red = int(255 * color_ratio)
                green = int(128 * (1 - abs(color_ratio - 0.5) * 2))

                bar_x = i * bar_width
                cv2.rectangle(img,
                              (bar_x, self.HEIGHT - bar_height),
                              (bar_x + bar_width - 1, self.HEIGHT),
                              (blue, green, red), -1)

    def _get_frequency_bands(self, count: int, key: str) -> np.ndarray:
        """Return log-spaced, compressed and temporally smoothed FFT bands."""
        spectrum = np.asarray(self.spectrum, dtype=np.float32)
        if len(spectrum) < 3 or not np.any(spectrum > 0):
            bands = np.zeros(count, dtype=np.float32)
        else:
            # Logarithmic buckets devote more pixels to bass and mid frequencies,
            # which reads much better than raw FFT bins on a tiny square screen.
            upper_bin = max(3, min(len(spectrum) - 1, int(len(spectrum) * 0.78)))
            edges = np.geomspace(1, upper_bin, count + 1)
            bands = np.empty(count, dtype=np.float32)
            for i in range(count):
                start = max(1, int(edges[i]))
                end = max(start + 1, int(edges[i + 1]))
                bands[i] = float(np.mean(spectrum[start:min(end, len(spectrum))]))
            bands = np.log1p(bands)
            peak = float(np.percentile(bands, 96))
            if peak > 1e-6:
                bands = np.clip(bands / peak, 0.0, 1.0)
            else:
                bands.fill(0)

        previous = self.effect_smoothing.get(key)
        if previous is None or len(previous) != count:
            previous = np.zeros(count, dtype=np.float32)
        # Let attacks through quickly while retaining the configured smooth decay.
        decay = float(np.clip(self.smoothing_factor, 0.0, 0.95))
        smoothed = np.where(bands >= previous,
                            previous * 0.25 + bands * 0.75,
                            previous * decay + bands * (1.0 - decay))
        self.effect_smoothing[key] = smoothed
        return smoothed

    @staticmethod
    def _add_glow(img: np.ndarray, glow: np.ndarray, sigma: float = 6.0,
                  strength: float = 0.75) -> None:
        """Blend a cheap neon bloom layer into ``img`` in place."""
        blurred = cv2.GaussianBlur(glow, (0, 0), sigmaX=sigma, sigmaY=sigma)
        cv2.addWeighted(img, 1.0, blurred, strength, 0, dst=img)
        cv2.add(img, glow, dst=img)

    def _draw_neon_mirror(self, img: np.ndarray) -> None:
        """Neon equalizer mirrored around the horizontal centre line."""
        count = 48
        bands = self._get_frequency_bands(count, 'neon_mirror')
        if len(self.neon_peaks) != count:
            self.neon_peaks = np.zeros(count, dtype=np.float32)
        self.neon_peaks = np.maximum(bands, self.neon_peaks - 0.018)

        glow = np.zeros_like(img)
        crisp = np.zeros_like(img)
        center_y = self.HEIGHT // 2
        slot = self.WIDTH / count
        max_height = max(8, int(self.HEIGHT * 0.43))

        cv2.line(glow, (0, center_y), (self.WIDTH - 1, center_y), (160, 30, 120), 3)
        for i, value in enumerate(bands):
            x1 = int(i * slot + 1)
            x2 = max(x1, int((i + 1) * slot - 1))
            height = max(1, int(value * max_height))
            ratio = i / max(1, count - 1)
            # OpenCV uses BGR: cyan -> violet -> hot pink.
            color = (
                int(255 - 80 * ratio),
                int(220 * (1.0 - abs(ratio - 0.35) * 1.35)),
                int(70 + 185 * ratio),
            )
            color = tuple(max(0, min(255, channel)) for channel in color)
            cv2.rectangle(glow, (x1, center_y - height), (x2, center_y + height), color, -1)
            cv2.rectangle(crisp, (x1, center_y - height), (x2, center_y + height), color, -1)

            peak_y = int(self.neon_peaks[i] * max_height)
            cv2.line(crisp, (x1, center_y - peak_y), (x2, center_y - peak_y), (255, 255, 255), 1)
            cv2.line(crisp, (x1, center_y + peak_y), (x2, center_y + peak_y), (255, 255, 255), 1)

        self._add_glow(img, glow, sigma=5.0, strength=0.65)
        cv2.add(img, crisp, dst=img)

    def _draw_aurora(self, img: np.ndarray) -> None:
        """Layered, softly glowing spectrum ridges resembling an aurora."""
        count = 72
        bands = self._get_frequency_bands(count, 'aurora')
        # A small spatial blur removes jagged FFT bucket transitions.
        bands = cv2.GaussianBlur(bands.reshape(1, -1), (9, 1), 0).ravel()
        x_values = np.linspace(0, self.WIDTH - 1, count).astype(np.int32)
        baseline = int(self.HEIGHT * 0.80)
        layers = (
            (0.48, 24, (255, 55, 205)),
            (0.66, 12, (220, 80, 255)),
            (0.88, 0, (90, 255, 175)),
        )
        glow = np.zeros_like(img)

        for scale, offset, color in layers:
            heights = bands * self.HEIGHT * scale
            ridge = np.column_stack((x_values, baseline - offset - heights.astype(np.int32)))
            polygon = np.vstack((ridge, (self.WIDTH - 1, baseline), (0, baseline))).astype(np.int32)
            fill = np.zeros_like(img)
            cv2.fillPoly(fill, [polygon], color)
            cv2.addWeighted(glow, 1.0, fill, 0.18, 0, dst=glow)
            cv2.polylines(glow, [ridge], False, color, 3, cv2.LINE_AA)

        self._add_glow(img, glow, sigma=8.0, strength=0.8)
        # Pin-sharp white-green crest gives the soft layers a readable silhouette.
        crest_y = baseline - (bands * self.HEIGHT * 0.88).astype(np.int32)
        crest = np.column_stack((x_values, crest_y)).astype(np.int32)
        cv2.polylines(img, [crest], False, (190, 255, 225), 1, cv2.LINE_AA)

    def _draw_starburst(self, img: np.ndarray) -> None:
        """Radial starburst with mirrored frequency bands and neon bloom."""
        # Smooth neighbouring frequency buckets before mirroring.  Temporal
        # smoothing alone cannot prevent adjacent ray endpoints from jumping.
        source = self._get_frequency_bands(40, 'starburst')
        source = cv2.GaussianBlur(source.reshape(1, -1), (9, 1), 0).ravel()
        # Repeat the same low-to-high profile in four mirrored quadrants.  A
        # single half-circle mapping puts bass at the top and treble at the
        # bottom, making normal music look permanently top-heavy.
        control = np.concatenate((source, source[::-1], source, source[::-1]))

        # Interpolate the control values to a denser circular profile.  The
        # repeated first value makes the interpolation continuous at 0/360°.
        rays = 192
        control_x = np.arange(len(control) + 1, dtype=np.float32)
        ray_x = np.linspace(0, len(control), rays, endpoint=False, dtype=np.float32)
        bands = np.interp(ray_x, control_x, np.append(control, control[0]))

        # Keep the silhouette circular: full-spectrum energy drives most of the
        # radius uniformly, while individual bands only add smaller local rays.
        # This prevents bass-heavy or treble-light music from pinching an axis.
        global_level = float(np.sqrt(np.mean(source ** 2)))
        bands = global_level * 0.70 + bands * 0.30
        center = (self.WIDTH // 2, self.HEIGHT // 2)
        base_radius = max(24, int(min(self.WIDTH, self.HEIGHT) * 0.19))
        max_length = int(min(self.WIDTH, self.HEIGHT) * 0.28)
        glow = np.zeros_like(img)
        crisp = np.zeros_like(img)
        outer_points = []

        for i, value in enumerate(bands):
            angle = 2.0 * np.pi * i / rays - np.pi / 2
            nx, ny = np.cos(angle), np.sin(angle)
            inner = base_radius + int(3 * np.sin(angle * 5))
            # A near-linear response avoids exaggerating tiny bin differences.
            outer = inner + 3 + int((value ** 0.95) * max_length)
            p1 = (int(center[0] + nx * inner), int(center[1] + ny * inner))
            p2 = (int(center[0] + nx * outer), int(center[1] + ny * outer))
            outer_points.append(p2)
            hue = int((i / rays) * 179)
            bgr = cv2.cvtColor(np.uint8([[[hue, 235, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
            color = tuple(int(channel) for channel in bgr)
            cv2.line(glow, p1, p2, color, 4, cv2.LINE_AA)
            cv2.line(crisp, p1, p2, color, 1, cv2.LINE_AA)

        # A closed contour visually unifies the ray endpoints into one smooth
        # outer halo while the individual coloured rays remain visible beneath.
        contour = np.asarray(outer_points, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(glow, [contour], True, (255, 120, 255), 4, cv2.LINE_AA)
        cv2.polylines(crisp, [contour], True, (255, 235, 255), 1, cv2.LINE_AA)
        cv2.circle(glow, center, base_radius, (255, 170, 255), 4, cv2.LINE_AA)
        self._add_glow(img, glow, sigma=6.0, strength=0.8)
        cv2.add(img, crisp, dst=img)
        cv2.circle(img, center, base_radius, (255, 245, 255), 1, cv2.LINE_AA)

    def _draw_waterfall(self, img: np.ndarray) -> None:
        """Scrolling time/frequency heat map; newest spectrum is at the bottom."""
        count = 64
        bands = self._get_frequency_bands(count, 'waterfall')
        if self.waterfall_history.shape[1] != count:
            self.waterfall_history = np.zeros((max(32, self.HEIGHT // 2), count), dtype=np.float32)
        self.waterfall_history[:-1] = self.waterfall_history[1:]
        self.waterfall_history[-1] = bands ** 0.72

        heat = np.clip(self.waterfall_history * 255, 0, 255).astype(np.uint8)
        heat = cv2.resize(heat, (self.WIDTH, self.HEIGHT), interpolation=cv2.INTER_CUBIC)
        colored = cv2.applyColorMap(heat, cv2.COLORMAP_TURBO)
        # Keep silent areas near black instead of the default dark-red colormap floor.
        colored[heat < 5] = 0
        cv2.addWeighted(img, 0.35, colored, 0.90, 0, dst=img)
        cv2.line(img, (0, self.HEIGHT - 2), (self.WIDTH - 1, self.HEIGHT - 2),
                 (255, 255, 255), 1)

    def _draw_waveform(self, img: np.ndarray) -> None:
        """绘制波形图[4](@ref)"""
        points = []
        for i in range(self.WIDTH):
            idx = int(i / self.WIDTH * len(self.time_data))
            if idx < len(self.time_data):
                wave_height = int(self.time_data[idx] * self.HEIGHT / 2)
                points.append((i, self.HEIGHT // 2 + wave_height))

        if len(points) > 1:
            num_points = len(points)
            for i in range(len(points) - 1):
                # cv2.line(img, points[i], points[i + 1], (255, 255, 255), 2)
                # color = (i, 100, 255-i)
                color_ratio = i / num_points
                red = 100+int(255 * color_ratio)
                # green = int(128 * (1 - abs(color_ratio - 0.5) * 2))
                green = 200
                blue = int(255 * (1 - color_ratio))
                color = (blue,green,red)
                cv2.line(img, points[i], points[i + 1], color, 2)
    def _draw_circular_spectrum2(self, img: np.ndarray) -> None:
        """效果：红蓝白电离，电离范围随着律动变化"""
        num_points = 100
        max_freq_index = min(len(self.spectrum), num_points)

        if self.spectrum.max() > 0:
            # spec_normalized = np.log1p(self.spectrum[:max_freq_index])
            spec_normalized = self.spectrum[:max_freq_index] / self.spectrum.max()
            # spec_normalized = spec_normalized / spec_normalized.max()
        else:
            spec_normalized = self.spectrum[:max_freq_index]

        points = []
        points_blue = []
        points_red = []
        center_x, center_y = self.WIDTH // 2, self.HEIGHT // 2

        # 使用动态计算的半径（基于音频律动）
        radius = max(30, int(self.current_radius))  # 确保半径不小于10像素
        # radius = int(self.current_radius)  # 确保半径不小于10像素

        if radius > 30:
            # 由于base_radius会根据律动自动变化，所以这里计算的random_offset也是随着律动变化的
            # 这里取绝对值是因为后面的randint必须第一个数小于第二个数
            random_offset = np.abs(radius - self.base_radius)
            # 随机偏移的值
            offset_x = random.randint(-random_offset,random_offset)
            offset_y = random.randint(-random_offset,random_offset)
        else:
            offset_x = 0
            offset_y = 0

        for i in range(num_points):

            angle = 2 * np.pi * i / num_points
            freq_index = int(i * max_freq_index / num_points)
            if freq_index >= len(spec_normalized):
                continue

            # 根据频谱强度调整每个点的长度
            snf = int(spec_normalized[freq_index] * radius * 0.8)
            nx = np.cos(angle)
            ny = np.sin(angle)

            point_length = radius + snf
            point_length_blue = radius + snf
            point_length_red = radius + snf

            x = int(center_x + point_length * nx)
            y = int(center_y + point_length * ny)

            x_blue = int(center_x + point_length_blue * nx) + offset_x
            y_blue = int(center_y + point_length_blue * ny) + offset_y

            x_red = int(center_x + point_length_red * nx) - offset_x
            y_red = int(center_y + point_length_red * ny) - offset_y

            points.append((x, y))
            points_blue.append((x_blue, y_blue))
            points_red.append((x_red, y_red))

            # if point_length > radius:
            #     color_ratio = i / num_points
            #     blue = int(255 * (1 - color_ratio))
            #     red = int(255 * color_ratio)
            #     # 根据律动强度调整线条粗细
            #     line_thickness = max(1, min(3, int(2 + spec_normalized[freq_index] * 3)))
            #     # line_thickness = 2
            #     cv2.line(img, (center_x, center_y), (x, y), (blue, 100, red), line_thickness)
            #
        # 绘制外圆环（半径随律动变化）
        if len(points) > 2:
            thickness = 4
            if offset_x == 0:
                for i in range(len(points)):
                    cv2.line(img, points[i], points[(i + 1) % len(points)], (255, 255, 255), thickness)
            else:
                # 先绘制蓝色，再绘制白色，最后绘制红色。三种颜色必须单独绘制，不能在一个循环内完整，否则会被覆盖
                # 蓝色和红色的坐标有随机偏差，这样有视觉错觉，看起来像电离效果一样
                for i in range(len(points)):
                    cv2.line(img, points_blue[i], points_blue[(i + 1) % len(points_blue)], (255, 0, 0), thickness)

                for i in range(len(points)):
                    cv2.line(img, points[i], points[(i + 1) % len(points)], (255, 255, 255), thickness)

                for i in range(len(points)):
                    cv2.line(img, points_red[i], points_red[(i + 1) % len(points_red)], (0, 0, 255), thickness)

        # 在圆心处添加一个随律动变化的小圆
        # center_radius = max(4, int(5 + (self.current_radius - self.base_radius) / self.max_radius_expansion * 10))
        # cv2.circle(img, (center_x, center_y), center_radius, (255, 255, 255), -1)

    def _draw_circular_spectrum(self, img: np.ndarray) -> None:
        """绘制圆形频谱图（现在半径会随律动变化）"""
        num_points = 80
        max_freq_index = min(len(self.spectrum), num_points)

        if self.spectrum.max() > 0:
            spec_normalized = self.spectrum[:max_freq_index] / self.spectrum.max()
        else:
            spec_normalized = self.spectrum[:max_freq_index]

        points = []
        points1 = []
        points2 = []
        center_x, center_y = self.WIDTH // 2, self.HEIGHT // 2

        # 使用动态计算的半径（基于音频律动）
        radius = max(30, int(self.current_radius)-20)  # 确保半径不小于30像素

        for i in range(num_points):

            angle = 2 * np.pi * i / num_points
            freq_index = int(i * max_freq_index / num_points)
            if freq_index >= len(spec_normalized):
                continue

            # 根据频谱强度调整每个点的长度
            snf = int(spec_normalized[freq_index] * radius * 0.8)
            nx = np.cos(angle)
            ny = np.sin(angle)

            point_length = radius + snf
            point_length1 = radius + 20 + snf
            point_length2 = radius + 40 + snf

            x = int(center_x + point_length * nx)
            y = int(center_y + point_length * ny)

            x1 = int(center_x + point_length1 * nx)
            y1 = int(center_y + point_length1 * ny)

            x2 = int(center_x + point_length2 * nx)
            y2 = int(center_y + point_length2 * ny)

            points.append((x, y))
            points1.append((x1, y1))
            points2.append((x2, y2))

            # if point_length > radius:
            #     color_ratio = i / num_points
            #     blue = int(255 * (1 - color_ratio))
            #     red = int(255 * color_ratio)
            #     # 根据律动强度调整线条粗细
            #     line_thickness = max(1, min(3, int(2 + spec_normalized[freq_index] * 3)))
            #     # line_thickness = 2
            #     cv2.line(img, (center_x, center_y), (x, y), (blue, 100, red), line_thickness)
            #
        # 绘制外圆环（半径随律动变化）
        if len(points) > 2:
            for i in range(len(points)):
                # thickness = max(1, int(2 + (self.current_radius - self.base_radius) / self.max_radius_expansion * 3))
                thickness = 4
                cv2.line(img, points[i], points[(i + 1) % len(points)], (100, 255, 255), thickness)
                cv2.line(img, points1[i], points1[(i + 1) % len(points1)], (180, 255, 255), thickness)
                cv2.line(img, points2[i], points2[(i + 1) % len(points2)], (255, 255, 255), thickness)

        # 在圆心处添加一个随律动变化的小圆
        # center_radius = max(4, int(5 + (self.current_radius - self.base_radius) / self.max_radius_expansion * 10))
        # cv2.circle(img, (center_x, center_y), center_radius, (255, 255, 255), -1)

    def _draw_circular_spectrum3(self,img: np.ndarray) -> None:
        """绘制圆形频谱图"""
        spectrum = self.spectrum
        BAR_LEN = 50
        # 取频谱并压缩动态范围
        center_x, center_y = self.WIDTH // 2, self.HEIGHT // 2
        radius = max(30, int(self.current_radius)-5)  # 确保半径不小于10像素
        # radius = 50
        spec = spectrum[5:185]  # 去掉直流 & 超高频
        spec = np.log1p(spec)
        spec /= (spec.max() + 1e-6)

        n = len(spec)

        # 低频能量 → 呼吸
        bass = np.mean(spec[:20])
        dynamic_radius = radius + int(bass * 40)
        points_outer = []
        points = []
        points_inner = []

        for i, v in enumerate(spec):
            angle = 2 * np.pi * i / n
            # 从频谱数据获得动态长度
            length = int(v * BAR_LEN)
            # if length > 30: length = 30

            r1 = dynamic_radius
            r_outer = dynamic_radius + length
            r_inner = dynamic_radius - length

            # 动态半径圆
            x1 = int(center_x + r1 * np.cos(angle))
            y1 = int(center_y + r1 * np.sin(angle))
            points.append((x1,y1))

            # 动态半径+动态长度的外圆
            x2 = int(center_x + r_outer * np.cos(angle))
            y2 = int(center_y + r_outer * np.sin(angle))
            points_outer.append((x2, y2))

            # 动态半径+动态长度的内圆
            x_inner = int(center_x + r_inner * np.cos(angle))
            y_inner = int(center_y + r_inner * np.sin(angle))
            points_inner.append((x_inner, y_inner))

            # 频率 → 颜色
            # hue = int(180 + 75 * i / n)
            hue = int(100 + 75 * i / n)

            bgr = cv2.cvtColor(
                np.uint8([[[hue, 255, 255]]]),
                cv2.COLOR_HSV2BGR
            )[0][0]

            # color = (int(bgr[0]), int(bgr[1]), int(bgr[2]))
            # color = (255,255,255)

            # cv2.line(img, (x1, y1), (x2, y2), color, 2)
            # cv2.line(img, (x1, y1), (x_inner, y_inner), color, 2)
            # cv2.line(img, (x2, y2), (x_inner, y_inner), color, 2)

        # 连接频谱点形成封闭图形
        if len(points) > 2:
            for i in range(len(points)):
                # cv2.line(img, points[i], points[(i + 1) % len(points)], (0, 200, 255), 1)
                cv2.line(img, points[i], points[(i + 1) % len(points)], (255, 255, 255), 3)
        circle_color = (255,255,255)
        # circle_color = (100,255,225)
        if len(points_outer) > 2:
            for i in range(len(points_outer)):
                cv2.line(img, points_outer[i], points_outer[(i + 1) % len(points_outer)], circle_color, 2)
        if len(points_inner) > 2:
            for i in range(len(points_inner)):
                cv2.line(img, points_inner[i], points_inner[(i + 1) % len(points_inner)], circle_color, 2)

    def _update_particles(self) -> None:
        """更新粒子系统[2](@ref)"""
        # 根据频谱强度和律动强度生成新粒子
        current_intensity = min(1.0, (self.current_radius - self.base_radius) / self.max_radius_expansion)

        if len(self.particles) < self.max_particles and self.spectrum.max() > 0:
            num_new_particles = min(int(5 + current_intensity * 10), self.max_particles - len(self.particles))
            for _ in range(num_new_particles):
                if self.spectrum.max() > 0:
                    intensity = (self.spectrum[np.random.randint(0, len(self.spectrum))]
                                 / self.spectrum.max())
                    if intensity > 0.2 + current_intensity * 0.3:
                        x = np.random.randint(10, self.WIDTH - 10)
                        y = self.HEIGHT
                        self.particles.append(self.Particle(x, y, intensity, self.WIDTH, self.HEIGHT))

        # 更新现有粒子
        self.particles = [p for p in self.particles if p.update()]

        # 限制粒子数量
        if len(self.particles) > self.max_particles:
            self.particles = self.particles[-self.max_particles:]

    def _draw_particles(self, img: np.ndarray) -> None:
        """绘制粒子"""
        for particle in self.particles:
            particle.draw(img)

    def get_frame(self, draw_waveform=True,
                  draw_spectrum_bar = True,
                  draw_spectrum_circular1 = False,
                  draw_spectrum_circular2 = True,
                  draw_spectrum_circular3 = False,
                  draw_neon_mirror = False,
                  draw_aurora = False,
                  draw_starburst = False,
                  draw_waterfall = False,
                  draw_particles = True
                  ) -> np.ndarray:
        """
        获取当前可视化帧

        Returns:
            numpy数组表示的图像帧 (BGR格式)
        """
        # 创建背景
        # t = time.time()

        # 静音时1秒内返回静音时候的图片，若超过1秒仍然没数据时，返回空白。
        if self.spectrum.max() <= 0:
            if time.time() - self.last_sound_time > 1:
                return None
        else:
            self.last_sound_time = time.time()

        img = self.background.copy()
        if draw_waveform: self._draw_waveform(img)
        if draw_spectrum_bar: self._draw_spectrum_bars(img)
        if draw_spectrum_circular1: self._draw_circular_spectrum(img)  # 三个环
        if draw_spectrum_circular2: self._draw_circular_spectrum2(img)  # 红白蓝电离
        if draw_spectrum_circular3: self._draw_circular_spectrum3(img)  # 动态圆环+内外双律动扩散
        if draw_waterfall: self._draw_waterfall(img)  # 彩色频谱瀑布
        if draw_aurora: self._draw_aurora(img)  # 极光山脉
        if draw_neon_mirror: self._draw_neon_mirror(img)  # 霓虹镜像柱
        if draw_starburst: self._draw_starburst(img)  # 放射星芒
        if draw_particles:
            self._update_particles()
            self._draw_particles(img)
        # print(time.time() - t)
        return img

    def release(self) -> None:
        """释放资源"""
        if self.stream is not None:
            stream = self.stream
            self.stream = None
            stream.stop()
            stream.close()

    def __del__(self):
        """析构函数确保资源释放"""
        self.release()

    class Particle:
        """粒子类"""

        def __init__(self, x, y, intensity, width, height):
            self.x = x
            self.y = y
            self.vx = np.random.uniform(-1, 1)
            self.vy = np.random.uniform(-5, -2)
            self.life = intensity * 150
            self.max_life = self.life
            self.color = (
                int(np.random.uniform(100, 255)),
                int(np.random.uniform(100, 255)),
                int(np.random.uniform(200, 255))
            )
            self.size = np.random.uniform(2, 8)
            self.width = width
            self.height = height

        def update(self) -> bool:
            """更新粒子状态"""
            self.x += self.vx
            self.y += self.vy
            self.vy += 0.05  # 重力
            self.life -= 1
            return self.life > 0 and 0 <= self.x < self.width and 0 <= self.y < self.height

        def draw(self, img: np.ndarray) -> None:
            """绘制粒子"""
            alpha = self.life / self.max_life
            size = int(self.size * alpha)
            if size > 0:
                cv2.circle(img, (int(self.x), int(self.y)), size, self.color, -1)


if __name__ == '__main__':
    av = AudioVisualizer(width=240, height=240, block_size=512)
    while True:
        cv2.imshow('av', av.get_frame(draw_waveform=False,
                  draw_spectrum_bar = False,
                  draw_spectrum_circular1 = False,
                  draw_spectrum_circular2 = False,
                  draw_spectrum_circular3 = False,
                  draw_neon_mirror = False,
                  draw_aurora = False,
                  draw_starburst = True,
                  draw_waterfall = False,
                  draw_particles = False
        ))
        key = cv2.waitKey(1)
        if key == ord('q'):
            break
