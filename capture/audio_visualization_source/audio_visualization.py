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

        # 音频数据缓冲区
        self.window = np.hanning(self.BLOCK_SIZE)
        self.spectrum = np.zeros(self.BLOCK_SIZE // 2 + 1, dtype=np.float32)
        self.time_data = np.zeros(self.BLOCK_SIZE, dtype=np.float32)
        self.smoothed_spectrum = np.zeros(self.BLOCK_SIZE // 2 + 1, dtype=np.float32)
        self.smoothing_factor = 0.5

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

    def _find_audio_device(self, target_name: str) -> int:
        """查找音频设备"""
        for i, dev in enumerate(sd.query_devices()):
            if target_name in dev['name']:
                print(f"使用设备: {sd.query_devices()[i]['name']}")
                return i
        print("未找到指定设备，使用默认输入设备")
        return None

    def _audio_callback(self, indata, frames, time, status):
        """音频回调函数，处理输入的音频数据[1](@ref)"""
        if status:
            print(f"音频流状态: {status}")

        # 取左声道数据
        mono = indata[:, 0].copy()

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
        for y in range(self.HEIGHT):
            blue = int(10 + (y / self.HEIGHT) * 30)
            green = int(5 + (y / self.HEIGHT) * 20)
            red = int(5 + (y / self.HEIGHT) * 15)
            background[y, :] = (blue, green, red)
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
            spec_normalized = self.spectrum[:max_freq_index] / self.spectrum.max()
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
        radius = max(30, int(self.current_radius))  # 确保半径不小于10像素

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

    def get_frame(self) -> np.ndarray:
        """
        获取当前可视化帧

        Returns:
            numpy数组表示的图像帧 (BGR格式)
        """
        # 创建背景
        # t = time.time()
        img = self.background.copy()

        # 绘制各种可视化效果[4](@ref)
        self._draw_waveform(img)
        self._draw_spectrum_bars(img)
        # self._draw_circular_spectrum(img)  # 这个现在会随律动变化
        self._draw_circular_spectrum2(img)  # 这个现在会随律动变化
        self._update_particles()
        self._draw_particles(img)
        # print(time.time() - t)


        return img

    def release(self) -> None:
        """释放资源"""
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()

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
        cv2.imshow('av', av.get_frame())
        key = cv2.waitKey(1)
        if key == ord('q'):
            break