import io
import unittest
from unittest.mock import patch

from capture.streamer import Streamer
from capture.interface import SourceType
from capture.source_manager import SourceManager


class Cp1252Stream(io.StringIO):
    @property
    def encoding(self):
        return "cp1252"

    def write(self, text):
        text.encode(self.encoding)
        return super().write(text)


class StreamerInitializationTests(unittest.TestCase):
    @patch("capture.streamer.SourceManager")
    def test_falls_back_when_the_configured_active_source_failed_to_initialize(self, manager_type):
        manager = manager_type.return_value
        manager.create_source.side_effect = ["demo1", None]
        manager.switch_source.return_value = False
        manager.list_configured_sources.return_value = [
            {"id": "demo1", "type": "demo", "active": True},
        ]

        streamer = Streamer({
            "sources": [
                {"type": "demo", "id": "demo1"},
                {"type": "audio_visualization", "id": "audio_visual1"},
            ],
            "active_source": "audio_visual1",
        })

        self.assertTrue(streamer.initialize())
        self.assertTrue(streamer._initialized)
        manager.switch_source.assert_called_once_with("audio_visual1")

    @patch("capture.streamer.SourceManager")
    def test_raises_a_clear_error_when_every_source_failed_to_initialize(self, manager_type):
        manager = manager_type.return_value
        manager.create_source.return_value = None
        manager.switch_source.return_value = False
        manager.list_configured_sources.return_value = []

        streamer = Streamer({
            "sources": [{"type": "demo", "id": "demo1"}],
            "active_source": "demo1",
        })

        with self.assertRaisesRegex(RuntimeError, "没有任何可用的配置源"):
            streamer.initialize()

    @patch("capture.streamer.SourceManager")
    def test_initializes_when_console_cannot_encode_chinese(self, manager_type):
        manager = manager_type.return_value
        manager.create_source.return_value = "demo1"

        streamer = Streamer({
            "sources": [{"type": "demo", "id": "demo1"}],
        })
        output = Cp1252Stream()

        with patch("sys.stdout", output):
            self.assertTrue(streamer.initialize())

            self.assertIn(r"\u6210\u529f", output.getvalue())


class SourceFrameRateTests(unittest.TestCase):
    def test_updates_demo_source_frame_rate_at_runtime(self):
        manager = SourceManager()
        self.assertEqual("demo1", manager.create_source(SourceType.DEMO, "demo1", fps=24))

        self.assertEqual(24.0, manager.get_source_frame_rate("demo1"))
        self.assertEqual(47.5, manager.set_source_frame_rate(47.5, "demo1"))
        self.assertEqual(47.5, manager.get_source_frame_rate("demo1"))
        self.assertEqual(47.5, manager.get_source_info("demo1")["fps"])

    def test_rejects_an_invalid_runtime_frame_rate(self):
        manager = SourceManager()
        manager.create_source(SourceType.DEMO, "demo1")

        with self.assertRaisesRegex(ValueError, "1-120"):
            manager.set_source_frame_rate(121, "demo1")


if __name__ == "__main__":
    unittest.main()
