import unittest
from unittest.mock import patch

from capture.streamer import Streamer


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


if __name__ == "__main__":
    unittest.main()
