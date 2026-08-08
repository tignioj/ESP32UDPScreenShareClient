import unittest
from unittest.mock import ANY, Mock, patch

import numpy as np

from capture.audio_visualization_source.audio_visualization import AudioVisualizer
from capture.audio_visualization_source.audio_visualization_source import AudioVisualizationSource
from capture.audio_visualization_source.effects.base import AudioFrame
from capture.audio_visualization_source.effects.ionized_ring import IonizedRingEffect
from capture.audio_visualization_source.effects.pulse_tunnel import PulseTunnelEffect
from capture.audio_visualization_source.effects.waveform import WaveformEffect
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
        self.assertEqual(11, len(catalog))
        self.assertEqual(11, len({item["id"] for item in catalog}))
        for effect_id, effect in self.visualizer.effects.items():
            for candidate in self.visualizer.effects.values():
                candidate.enabled = False
            effect.enabled = True
            frame = self.visualizer.get_frame()
            self.assertEqual((240, 240, 3), frame.shape, effect_id)
            self.assertEqual(np.uint8, frame.dtype, effect_id)

    def test_overlay_frame_has_transparent_background_and_visible_effects(self):
        for effect in self.visualizer.effects.values():
            effect.enabled = False
        self.visualizer.effects["waveform"].enabled = True

        frame = self.visualizer.get_overlay_frame()

        self.assertEqual((240, 240, 4), frame.shape)
        self.assertEqual(np.uint8, frame.dtype)
        self.assertGreater(np.count_nonzero(frame[:, :, 3]), 0)
        self.assertGreater(np.count_nonzero(frame[:, :, 3] == 0), 0)
        self.assertEqual({0, 255}, set(np.unique(frame[:, :, 3])))

    def test_effect_parameters_are_namespaced(self):
        original_waveform = dict(self.visualizer.effects["waveform"].values)
        self.visualizer.configure({
            "effects": {"spectrum_bars": {"params": {"smoothing": 0.2}}}
        })
        self.assertEqual(0.2, self.visualizer.effects["spectrum_bars"].values["smoothing"])
        self.assertEqual(original_waveform, self.visualizer.effects["waveform"].values)

    @patch("capture.audio_visualization_source.effects.waveform.cv2.line")
    def test_waveform_vertical_position_uses_screen_y_coordinate(self, draw_line):
        effect = WaveformEffect()
        effect.configure({"vertical_position": 42})
        canvas = np.zeros((240, 240, 3), dtype=np.uint8)
        frame = AudioFrame(
            waveform=np.zeros(1024, dtype=np.float32),
            spectrum=np.zeros(513, dtype=np.float32),
            sample_rate=48000,
            block_size=1024,
            rms=0.0,
            bass=0.0,
            beat=0.0,
            time=0.0,
        )

        effect.draw(canvas, frame, 1.0 / 30.0)

        draw_line.assert_called_once_with(
            canvas, (0, 42), (239, 42), (45, 25, 55), 1, ANY
        )
        position = next(item for item in effect.metadata()["parameters"]
                        if item["name"] == "vertical_position")
        self.assertEqual((0, 239, 120),
                         (position["min"], position["max"], position["default"]))

    def test_ionized_ring_adds_red_and_blue_layers_on_a_beat(self):
        effect = IonizedRingEffect()
        effect.rng = np.random.default_rng(7)
        canvas = np.zeros((240, 240, 3), dtype=np.uint8)
        frame = AudioFrame(
            waveform=np.zeros(1024, dtype=np.float32),
            spectrum=np.linspace(0.1, 1.0, 513, dtype=np.float32),
            sample_rate=48000,
            block_size=1024,
            rms=0.2,
            bass=0.8,
            beat=1.0,
            time=0.0,
        )

        effect.draw(canvas, frame, 1.0 / 30.0)

        channels = canvas.astype(np.int16)
        blue_pixels = (channels[:, :, 0] > channels[:, :, 2] + 20).sum()
        red_pixels = (channels[:, :, 2] > channels[:, :, 0] + 20).sum()
        self.assertGreater(blue_pixels, 0)
        self.assertGreater(red_pixels, 0)

    def test_legacy_flat_config_is_migrated(self):
        source = AudioVisualizationSource(SourceType.AUDIO_VISUALIZATION, "test")
        source.visualizer = self.visualizer
        self.assertTrue(source.set_config({
            "draw_waveform": True,
            "draw_spectrum_circular2": True,
            "gain": 1.4,
            "radius_smoothing": 0.8,
            "max_particles": 80,
        }))
        config = source.get_info()["config"]
        self.assertTrue(config["effects"]["waveform"]["enabled"])
        self.assertTrue(config["effects"]["ionized_ring"]["enabled"])
        self.assertFalse(config["effects"]["chroma_ring"]["enabled"])
        self.assertEqual(0.8, config["effects"]["ionized_ring"]["params"]["pulse_smoothing"])
        self.assertEqual(80, config["effects"]["particles"]["params"]["count"])
        self.assertEqual(1.4, config["input"]["gain"])
        source.visualizer = None

    def test_resolves_the_active_preset_for_startup(self):
        config = {
            "active_preset": "派对",
            "presets": {
                "舒缓": {"input": {"gain": 0.8}},
                "派对": {"input": {"gain": 1.8}},
            },
        }

        resolved = AudioVisualizationSource._get_active_preset_config(config)
        self.assertEqual({"input": {"gain": 1.8}}, resolved)
        config["presets"]["派对"]["input"]["gain"] = 2.0
        self.assertEqual({"input": {"gain": 1.8}}, resolved)

    def test_ignores_a_stale_active_preset_at_startup(self):
        self.assertIsNone(AudioVisualizationSource._get_active_preset_config({
            "active_preset": "已删除",
            "presets": {},
        }))

    def test_runtime_device_selection_is_forwarded_to_visualizer(self):
        source = AudioVisualizationSource(SourceType.AUDIO_VISUALIZATION, "test")
        source.visualizer = Mock()

        self.assertTrue(source.set_config({"target_device": "BlackHole 2ch"}))
        source.visualizer.select_input_device.assert_called_once_with("BlackHole 2ch")

    @patch("capture.audio_visualization_source.audio_visualization_source.AudioVisualizer")
    def test_initialize_applies_the_saved_preset_after_base_values(self, visualizer_type):
        source = AudioVisualizationSource(SourceType.AUDIO_VISUALIZATION, "test")
        visualizer = visualizer_type.return_value

        self.assertTrue(source.initialize(
            input={"gain": 1.0},
            effects={"waveform": {"enabled": False}},
            active_preset="派对",
            presets={
                "派对": {
                    "input": {"gain": 1.8},
                    "effects": {"waveform": {"enabled": True}},
                },
            },
        ))

        self.assertEqual(2, visualizer.configure.call_count)
        self.assertEqual({"input": {"gain": 1.0}, "effects": {"waveform": {"enabled": False}}},
                         visualizer.configure.call_args_list[0].args[0])
        self.assertEqual({"input": {"gain": 1.8}, "effects": {"waveform": {"enabled": True}}},
                         visualizer.configure.call_args_list[1].args[0])

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
