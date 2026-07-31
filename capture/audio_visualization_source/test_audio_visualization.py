import unittest

import numpy as np

from capture.audio_visualization_source.audio_visualization import AudioVisualizer
from capture.audio_visualization_source.audio_visualization_source import AudioVisualizationSource
from capture.audio_visualization_source.effects.base import AudioFrame
from capture.audio_visualization_source.effects.pulse_tunnel import PulseTunnelEffect
from capture.interface import SourceType


class AudioVisualizationTests(unittest.TestCase):
    def setUp(self):
        self.visualizer = AudioVisualizer(width=240, height=240, block_size=1024, start_audio=False)
        samples = np.arange(1024, dtype=np.float32) / 48000
        wave = (0.4 * np.sin(2 * np.pi * 90 * samples) +
                0.25 * np.sin(2 * np.pi * 680 * samples)).astype(np.float32)
        self.visualizer._audio_callback(np.column_stack((wave, wave)), 1024, None, None)

    def tearDown(self):
        self.visualizer.release()

    def test_every_registered_effect_renders_independently(self):
        catalog = self.visualizer.effect_catalog()
        self.assertEqual(10, len(catalog))
        self.assertEqual(10, len({item["id"] for item in catalog}))
        for effect_id, effect in self.visualizer.effects.items():
            for candidate in self.visualizer.effects.values():
                candidate.enabled = False
            effect.enabled = True
            frame = self.visualizer.get_frame()
            self.assertEqual((240, 240, 3), frame.shape, effect_id)
            self.assertEqual(np.uint8, frame.dtype, effect_id)

    def test_effect_parameters_are_namespaced(self):
        original_waveform = dict(self.visualizer.effects["waveform"].values)
        self.visualizer.configure({
            "effects": {"spectrum_bars": {"params": {"smoothing": 0.2}}}
        })
        self.assertEqual(0.2, self.visualizer.effects["spectrum_bars"].values["smoothing"])
        self.assertEqual(original_waveform, self.visualizer.effects["waveform"].values)

    def test_legacy_flat_config_is_migrated(self):
        source = AudioVisualizationSource(SourceType.AUDIO_VISUALIZATION, "test")
        source.visualizer = self.visualizer
        self.assertTrue(source.set_config({
            "draw_waveform": True,
            "gain": 1.4,
            "max_particles": 80,
        }))
        config = source.get_info()["config"]
        self.assertTrue(config["effects"]["waveform"]["enabled"])
        self.assertEqual(80, config["effects"]["particles"]["params"]["count"])
        self.assertEqual(1.4, config["input"]["gain"])
        source.visualizer = None

    def test_pulse_tunnel_is_continuous_across_phase_wrap(self):
        effect = PulseTunnelEffect()
        period = 1.0 / effect.values["speed"]

        def render(timestamp):
            canvas = np.zeros((240, 240, 3), dtype=np.uint8)
            frame = AudioFrame(
                waveform=np.zeros(1024, dtype=np.float32),
                spectrum=np.zeros(513, dtype=np.float32),
                sample_rate=48000,
                block_size=1024,
                rms=0.0,
                bass=0.0,
                beat=0.0,
                time=timestamp,
            )
            effect.draw(canvas, frame, 1.0 / 30.0)
            return canvas

        before = render(period - 0.0001)
        after = render(period + 0.0001)
        self.assertLess(float(np.mean(np.abs(before.astype(float) - after.astype(float)))), 1.0)

    def test_pulse_tunnel_smooths_bass_changes(self):
        effect = PulseTunnelEffect()
        first = effect._smooth_bass(1.0, 1.0 / 30.0)
        second = effect._smooth_bass(1.0, 1.0 / 30.0)
        released = effect._smooth_bass(0.0, 1.0 / 30.0)

        self.assertGreater(first, 0.0)
        self.assertLess(first, second)
        self.assertLess(second, 1.0)
        self.assertLess(released, second)
        self.assertGreater(released, 0.0)


if __name__ == "__main__":
    unittest.main()
