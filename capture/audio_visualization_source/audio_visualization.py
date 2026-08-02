from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

import numpy as np
import sounddevice as sd

from capture.audio_visualization_source.effects import create_effects, get_effect_catalog
from capture.audio_visualization_source.effects.base import AudioFrame, ParameterSpec
from capture.audio_visualization_source.effects.utils import gradient_background


INPUT_PARAMETERS = (
    ParameterSpec("gain", "输入灵敏度", 0.1, 6.0, 1.0, 0.1, 1,
                  "仅放大分析信号，不改变系统音量。"),
    ParameterSpec("noise_gate", "静音门限", 0.0, 0.03, 0.0015, 0.0005, 4,
                  "过滤声卡底噪；弱信号被截断时请调低。"),
    ParameterSpec("beat_sensitivity", "鼓点灵敏度", 0.5, 2.5, 1.25, 0.05, 2,
                  "影响带有脉冲、呼吸或粒子响应的效果。"),
)


class AudioVisualizer:
    """Audio capture/analyser and a compositor for independent effect modules."""

    def __init__(self, width: int = 240, height: int = 240, sample_rate: int = 48000,
                 block_size: int = 1024, channels: int = 2,
                 target_device: str = "", start_audio: bool = True):
        self.width = int(width)
        self.height = int(height)
        self.requested_sample_rate = int(sample_rate)
        self.sample_rate = int(sample_rate)
        self.block_size = int(block_size)
        self.requested_channels = int(channels)
        self.channels = int(channels)
        self.target_device = target_device
        self.input_values = {item.key: item.default for item in INPUT_PARAMETERS}
        self.effects = create_effects()

        self._lock = threading.RLock()
        self._window = np.hanning(self.block_size).astype(np.float32)
        self._waveform = np.zeros(self.block_size, dtype=np.float32)
        self._spectrum = np.zeros(self.block_size // 2 + 1, dtype=np.float32)
        self._rms = 0.0
        self._bass = 0.0
        self._beat = 0.0
        self._energy_average = 1e-5
        self._start_time = time.monotonic()
        self._last_frame_time = self._start_time
        self._background = gradient_background(self.width, self.height)
        self.stream: Optional[sd.InputStream] = None
        self.device_id: Optional[int] = None

        if start_audio:
            self.device_id = self._find_audio_device(target_device)
            self._initialize_audio_stream()

    @staticmethod
    def input_catalog() -> list[Dict[str, Any]]:
        return [item.as_dict() for item in INPUT_PARAMETERS]

    @staticmethod
    def effect_catalog() -> list[Dict[str, Any]]:
        return get_effect_catalog()

    @staticmethod
    def input_devices() -> list[Dict[str, Any]]:
        """Return every recordable device in a UI-friendly, portable form."""
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        result = []
        for index, device in enumerate(devices):
            if int(device["max_input_channels"]) < 1:
                continue
            name = str(device["name"])
            result.append({
                "name": name,
                "label": name,
                "index": index,
                "channels": int(device["max_input_channels"]),
                "default": index == default_input,
                "sample_rate": int(round(float(device["default_samplerate"]))),
            })
        return result

    def _find_audio_device(self, target_name: str) -> Optional[int]:
        devices = sd.query_devices()
        if target_name:
            for index, device in enumerate(devices):
                if target_name == str(device["name"]) and device["max_input_channels"] > 0:
                    print(f"使用音频设备: {device['name']}")
                    return index
            # Keep partial matching for existing Windows configurations such as
            # "CABLE Output (VB-Audio Virtual Cable)".
            for index, device in enumerate(devices):
                if target_name.lower() in str(device["name"]).lower() and device["max_input_channels"] > 0:
                    print(f"使用音频设备: {device['name']}")
                    return index

        default_input = sd.default.device[0]
        if default_input is not None and int(default_input) >= 0:
            device = devices[int(default_input)]
            print(f"未找到 {target_name}，使用默认输入设备: {device['name']}")
            return int(default_input)
        raise RuntimeError(f"没有可用的音频输入设备（未找到 {target_name}）")

    def _create_audio_stream(self, device_id: Optional[int]) -> sd.InputStream:
        """Open a device, falling back to its native rate when needed.

        CoreAudio exposes microphones and virtual loopback devices at different
        native rates.  Letting PortAudio use that native rate makes both kinds
        of inputs work without a per-device YAML tweak.
        """
        device = sd.query_devices(device_id, "input")
        max_channels = int(device["max_input_channels"])
        if max_channels < 1:
            raise RuntimeError(f"音频设备没有输入声道: {device['name']}")
        channels = min(self.requested_channels, max_channels)
        native_rate = int(round(float(device["default_samplerate"])))
        rates = [self.requested_sample_rate]
        if native_rate not in rates:
            rates.append(native_rate)
        last_error = None
        for rate in rates:
            try:
                stream = sd.InputStream(
                    device=device_id,
                    channels=channels,
                    samplerate=rate,
                    blocksize=self.block_size,
                    callback=self._audio_callback,
                )
                stream.start()
                self.channels = channels
                self.sample_rate = rate
                if rate != self.requested_sample_rate:
                    print(f"音频设备 {device['name']} 不支持 {self.requested_sample_rate} Hz，已使用 {rate} Hz")
                return stream
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"无法打开音频设备 {device['name']}: {last_error}")

    def _initialize_audio_stream(self) -> None:
        try:
            self.stream = self._create_audio_stream(self.device_id)
        except Exception as exc:
            self.stream = None
            raise RuntimeError(f"无法启动音频输入流: {exc}") from exc

    def select_input_device(self, target_device: str) -> None:
        """Switch capture devices without stopping the visualizer source."""
        target_device = str(target_device or "")
        new_device_id = self._find_audio_device(target_device)
        new_stream = self._create_audio_stream(new_device_id)
        old_stream = self.stream
        self.stream = new_stream
        self.device_id = new_device_id
        self.target_device = target_device
        if old_stream is not None:
            try:
                old_stream.stop()
            finally:
                old_stream.close()

    def _audio_callback(self, indata, frames, callback_time, status) -> None:
        if status:
            print(f"音频输入状态: {status}")
        samples = np.asarray(indata, dtype=np.float32)
        mono = samples.mean(axis=1) if samples.ndim > 1 else samples
        if mono.size != self.block_size:
            resized = np.zeros(self.block_size, dtype=np.float32)
            resized[:min(mono.size, self.block_size)] = mono[:self.block_size]
            mono = resized

        gain = self.input_values["gain"]
        mono = np.clip(mono * gain, -1.0, 1.0)
        rms = float(np.sqrt(np.mean(np.square(mono))))
        if rms < self.input_values["noise_gate"]:
            mono = np.zeros_like(mono)
            rms = 0.0

        spectrum = np.abs(np.fft.rfft(mono * self._window)).astype(np.float32)
        bass_end = max(2, min(spectrum.size, int(220 / (self.sample_rate / self.block_size))))
        bass = float(np.mean(spectrum[1:bass_end])) if bass_end > 1 else 0.0
        bass = float(np.clip(np.log1p(bass * 4.0) / 3.0, 0.0, 1.0))

        self._energy_average = self._energy_average * 0.94 + rms * 0.06
        threshold = self._energy_average * self.input_values["beat_sensitivity"] + 1e-6
        beat = float(np.clip((rms - threshold) / max(threshold, 0.002), 0.0, 1.0))
        with self._lock:
            self._waveform = mono.copy()
            self._spectrum = spectrum
            self._rms = rms
            self._bass = bass
            self._beat = max(beat, self._beat * 0.72)

    def configure_input(self, values: Dict[str, Any]) -> None:
        specs = {item.key: item for item in INPUT_PARAMETERS}
        unknown = set(values) - set(specs)
        if unknown:
            raise ValueError(f"未知输入参数: {', '.join(sorted(unknown))}")
        validated = {key: specs[key].clamp(value) for key, value in values.items()}
        with self._lock:
            self.input_values.update(validated)

    def configure_effect(self, effect_id: str, enabled: Optional[bool] = None,
                         params: Optional[Dict[str, Any]] = None, reset: bool = False) -> None:
        effect = self.effects.get(effect_id)
        if effect is None:
            raise ValueError(f"未知音频效果: {effect_id}")
        with self._lock:
            if reset:
                effect.reset()
            if params:
                effect.configure(params)
            if enabled is not None:
                effect.enabled = bool(enabled)

    def configure(self, config: Dict[str, Any]) -> None:
        if "input" in config:
            if not isinstance(config["input"], dict):
                raise ValueError("input 必须是对象")
            self.configure_input(config["input"])
        if "effects" in config:
            if not isinstance(config["effects"], dict):
                raise ValueError("effects 必须是对象")
            for effect_id, effect_config in config["effects"].items():
                if not isinstance(effect_config, dict):
                    raise ValueError(f"effects.{effect_id} 必须是对象")
                allowed = {"enabled", "params", "reset"}
                unknown = set(effect_config) - allowed
                if unknown:
                    raise ValueError(f"effects.{effect_id} 包含未知字段: {', '.join(sorted(unknown))}")
                self.configure_effect(
                    effect_id,
                    enabled=effect_config.get("enabled"),
                    params=effect_config.get("params"),
                    reset=bool(effect_config.get("reset", False)),
                )

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "target_device": self.target_device,
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "input": dict(self.input_values),
                "effects": {
                    effect_id: {
                        "enabled": effect.enabled,
                        "params": dict(effect.values),
                    }
                    for effect_id, effect in self.effects.items()
                },
            }

    def get_frame(self) -> np.ndarray:
        now = time.monotonic()
        dt = min(0.1, max(0.001, now - self._last_frame_time))
        self._last_frame_time = now
        with self._lock:
            frame = AudioFrame(
                waveform=self._waveform.copy(),
                spectrum=self._spectrum.copy(),
                sample_rate=self.sample_rate,
                block_size=self.block_size,
                rms=self._rms,
                bass=self._bass,
                beat=self._beat,
                time=now - self._start_time,
            )
            self._beat *= 0.88
            enabled_effects = [effect for effect in self.effects.values() if effect.enabled]

        canvas = self._background.copy()
        for effect in enabled_effects:
            effect.draw(canvas, frame, dt)
        return canvas

    def release(self) -> None:
        stream = self.stream
        self.stream = None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()

    def __del__(self):
        self.release()


if __name__ == "__main__":
    import cv2

    visualizer = AudioVisualizer()
    try:
        while True:
            cv2.imshow("Audio Visualizer", visualizer.get_frame())
            if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                break
    finally:
        visualizer.release()
        cv2.destroyAllWindows()
