import unittest

import numpy as np

from capture.audio_visualization_source.audio_visualization import AudioVisualizer
from capture.audio_visualization_source.audio_visualization_source import AudioVisualizationSource
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


if __name__ == "__main__":
    unittest.main()
