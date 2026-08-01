import tempfile
import unittest
from pathlib import Path

import yaml

from capture.config import (
    delete_audio_preset,
    load_audio_presets,
    save_audio_preset,
    save_source_runtime_config,
    save_video_source_config,
)


class ConfigPersistenceTests(unittest.TestCase):
    def write_config(self, directory: str) -> Path:
        path = Path(directory) / "config_stream.yaml"
        path.write_text(
            """streamer:
  sources:
    - type: audio_visualization
      id: audio_one
      params:
        target_device: CABLE Output
        input:
          gain: 1.0
        effects:
          waveform:
            enabled: false
    - type: screen
      id: screen_one
      params:
        fps: 30
    - type: video_file
      id: video_one
      params:
        video_path: old_videos
        auto_crop_center: true
  active_source: audio_one
""",
            encoding="utf-8",
        )
        return path

    def test_saves_audio_values_and_preserves_other_source_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory)
            runtime_config = {
                "input": {"gain": 1.6, "noise_gate": 0.002},
                "effects": {
                    "waveform": {
                        "enabled": True,
                        "params": {"amplitude": 0.9},
                    }
                },
            }

            result = save_source_runtime_config("audio_one", runtime_config, path)

            self.assertEqual(path, result)
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            audio = document["streamer"]["sources"][0]
            screen = document["streamer"]["sources"][1]
            self.assertEqual("CABLE Output", audio["params"]["target_device"])
            self.assertEqual(runtime_config["input"], audio["params"]["input"])
            self.assertEqual(runtime_config["effects"], audio["params"]["effects"])
            self.assertEqual({"fps": 30}, screen["params"])

    def test_rejects_a_missing_source_without_changing_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory)
            original = path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "找不到图像源"):
                save_source_runtime_config(
                    "missing",
                    {"input": {"gain": 1.2}, "effects": {}},
                    path,
                )

            self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_saves_loads_and_deletes_multiple_audio_presets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory)
            calm = {
                "input": {"gain": 0.8},
                "effects": {"waveform": {"enabled": True}},
            }
            party = {
                "input": {"gain": 1.8},
                "effects": {"particles": {"enabled": True}},
            }

            save_audio_preset("audio_one", "舒缓", calm, path)
            save_audio_preset("audio_one", "派对", party, path)

            presets = load_audio_presets("audio_one", path)
            self.assertEqual(["舒缓", "派对"], list(presets))
            self.assertEqual(calm, presets["舒缓"])
            self.assertEqual(party, presets["派对"])

            updated_party = {
                "input": {"gain": 2.0},
                "effects": {"starburst": {"enabled": True}},
            }
            save_audio_preset("audio_one", "派对", updated_party, path)
            self.assertEqual(updated_party, load_audio_presets("audio_one", path)["派对"])

            delete_audio_preset("audio_one", "舒缓", path)
            self.assertEqual({"派对": updated_party}, load_audio_presets("audio_one", path))

    def test_saving_default_values_keeps_named_presets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory)
            preset = {
                "input": {"gain": 0.7},
                "effects": {"waveform": {"enabled": True}},
            }
            current = {
                "input": {"gain": 1.3},
                "effects": {"waveform": {"enabled": False}},
            }

            save_audio_preset("audio_one", "保留我", preset, path)
            save_source_runtime_config("audio_one", current, path)

            self.assertEqual({"保留我": preset}, load_audio_presets("audio_one", path))

    def test_saves_video_playback_parameters_and_current_video(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory)

            save_video_source_config(
                "video_one",
                {
                    "video_path": r"D:\Videos\ESP32",
                    "play_mode": "random",
                    "playback_rate": 1.5,
                    "current_video": "demo.mp4",
                    "preview_enabled": False,
                },
                path,
            )

            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            video = document["streamer"]["sources"][2]
            self.assertEqual(r"D:\Videos\ESP32", video["params"]["video_path"])
            self.assertEqual("random", video["params"]["play_mode"])
            self.assertEqual(1.5, video["params"]["playback_rate"])
            self.assertEqual("demo.mp4", video["params"]["first_play_video"])
            self.assertFalse(video["params"]["preview_enabled"])
            self.assertTrue(video["params"]["auto_crop_center"])


if __name__ == "__main__":
    unittest.main()
