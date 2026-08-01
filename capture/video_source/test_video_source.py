import unittest
from pathlib import Path

from capture.interface import SourceType
from capture.video_source.video_source import VideoFileSource


class VideoFileSourcePlaybackTests(unittest.TestCase):
    def setUp(self):
        self.source = VideoFileSource(SourceType.VIDEO_FILE, "video_test")
        self.video_directory = Path(__file__).resolve().parents[2] / "sample_video"

    def tearDown(self):
        self.source.release()

    def test_lists_videos_and_can_play_a_selected_item(self):
        self.assertTrue(
            self.source.initialize(
                video_path=str(self.video_directory),
                play_mode="list_loop",
                playback_rate=1.0,
            )
        )
        info = self.source.get_info()
        self.assertGreaterEqual(len(info["video_files"]), 2)

        selected = info["video_files"][-1]
        self.assertTrue(self.source.set_config({"play_video": selected}))
        self.assertEqual(selected, self.source.get_info()["current_video"])

    def test_single_loop_keeps_the_selected_video_and_rate_is_clamped(self):
        self.assertTrue(
            self.source.initialize(
                video_path=str(self.video_directory),
                play_mode="single_loop",
                playback_rate=3.0,
            )
        )
        info = self.source.get_info()
        current_index = self.source._current_idx
        self.assertEqual(current_index, self.source._next_video_index())
        self.assertEqual("single_loop", info["play_mode"])
        self.assertEqual(2.0, info["playback_rate"])


if __name__ == "__main__":
    unittest.main()
