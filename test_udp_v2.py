import struct
import unittest

import numpy as np

from udp_v2 import (
    AdaptivePacer,
    CHUNKS_PER_FRAME,
    DATA_HEADER,
    DATA_PACKET_SIZE,
    FEEDBACK_MAGIC,
    FEEDBACK_PACKET,
    Feedback,
    MODE_RGB332,
    MODE_RGB565,
    PAYLOAD_SIZE,
    encode_frame_bgr,
    make_data_packet,
    migrate_v2_config,
    packetize_frame,
    parse_feedback,
    _u32_at_or_before,
    _u32_delta,
)


class ProtocolV2Tests(unittest.TestCase):
    def test_data_header_matches_the_wire_golden_vector(self):
        packet = make_data_packet(
            0x01020304,
            0xA0B0C0D0,
            MODE_RGB332,
            2,
            bytes([0x55]) * PAYLOAD_SIZE,
        )
        expected_header = (
            b"SSD2\x01\x02\x03\x04\xa0\xb0\xc0\xd0"
            b"\x00\x02\x05\xa0"
        )
        self.assertEqual(expected_header, packet[:DATA_HEADER.size])
        self.assertEqual(DATA_PACKET_SIZE, len(packet))

    def test_packetization_is_fixed_mtu_payload_for_both_modes(self):
        for mode, frame_size in ((MODE_RGB332, 57_600), (MODE_RGB565, 115_200)):
            packets = packetize_frame(bytes(frame_size), 7, 9, mode)
            self.assertEqual(CHUNKS_PER_FRAME[mode], len(packets))
            self.assertTrue(all(len(packet) == DATA_PACKET_SIZE for packet in packets))
            indexes = [DATA_HEADER.unpack(packet[:DATA_HEADER.size])[4] for packet in packets]
            self.assertEqual(list(range(len(packets))), indexes)

    def test_rgb_encoders_use_expected_st7789_values(self):
        frame = np.zeros((240, 240, 3), dtype=np.uint8)
        frame[0, 0] = (0, 0, 255)
        frame[0, 1] = (0, 255, 0)
        frame[0, 2] = (255, 0, 0)
        rgb332 = encode_frame_bgr(frame, MODE_RGB332)
        rgb565 = encode_frame_bgr(frame, MODE_RGB565)
        self.assertEqual(bytes((0xE0, 0x1C, 0x03)), rgb332[:3])
        self.assertEqual(b"\xf8\x00\x07\xe0\x00\x1f", rgb565[:6])

    def test_feedback_parser_matches_fixed_64_byte_layout(self):
        integers = tuple(range(1, 13))
        data = FEEDBACK_PACKET.pack(FEEDBACK_MAGIC, *integers, 13, 72, 130_000, 99_000)
        feedback = parse_feedback(data)
        self.assertEqual(64, len(data))
        self.assertEqual(1, feedback.session_id)
        self.assertEqual(5, feedback.latest_displayed_frame)
        self.assertEqual(12, feedback.displayed_frames)
        self.assertEqual(13, feedback.queue_depth)
        self.assertEqual(72, feedback.queue_capacity)
        self.assertEqual(130_000, feedback.free_heap)

    def test_invalid_payload_and_feedback_are_rejected(self):
        with self.assertRaises(ValueError):
            make_data_packet(1, 2, MODE_RGB332, 0, b"short")
        with self.assertRaises(ValueError):
            parse_feedback(b"SSF2")
        with self.assertRaises(ValueError):
            parse_feedback(b"BAD2" + bytes(60))

    def test_frame_serial_arithmetic_wraps_at_uint32(self):
        self.assertEqual(1, _u32_delta(0, 0xFFFFFFFF))
        self.assertTrue(_u32_at_or_before(0xFFFFFFFF, 0))
        self.assertTrue(_u32_at_or_before(0, 0))
        self.assertFalse(_u32_at_or_before(1, 0))

        wrapped = make_data_packet(
            7, 0x1_0000_0000, MODE_RGB332, 0, bytes(PAYLOAD_SIZE)
        )
        self.assertEqual(0, DATA_HEADER.unpack_from(wrapped)[2])


class PacerTests(unittest.TestCase):
    @staticmethod
    def feedback(**changes):
        values = dict(
            session_id=1,
            sequence=1,
            latest_rx_frame=0,
            latest_complete_frame=0,
            latest_displayed_frame=0,
            rx_packets=100,
            accepted_packets=100,
            overflow_packets=0,
            invalid_packets=0,
            stale_packets=0,
            incomplete_frames=0,
            displayed_frames=1,
            queue_depth=4,
            queue_capacity=24,
            free_heap=150_000,
            uptime_ms=1000,
        )
        values.update(changes)
        return Feedback(**values)

    def test_healthy_feedback_increases_and_congestion_decreases_rate(self):
        pacer = AdaptivePacer()
        base = pacer._last_increase_ns
        pacer.update(self.feedback(), base + 1_000_000_000)
        self.assertEqual(22.5, pacer.rate_mbps)
        congested = self.feedback(sequence=2, overflow_packets=1, queue_depth=19)
        self.assertTrue(pacer.update(congested, base + 1_100_000_000))
        self.assertAlmostEqual(19.125, pacer.rate_mbps)

    def test_rate_is_clamped_at_minimum(self):
        pacer = AdaptivePacer(initial_mbps=12.0)
        pacer.update(self.feedback(queue_depth=24))
        self.assertEqual(12.0, pacer.rate_mbps)

    def test_large_slot_window_uses_scaled_queue_threshold(self):
        pacer = AdaptivePacer()
        base = pacer._last_increase_ns
        pacer.update(self.feedback(queue_capacity=72, queue_depth=63), base + 10)
        self.assertEqual(22.0, pacer.rate_mbps)
        reduced = pacer.update(
            self.feedback(sequence=2, queue_capacity=72, queue_depth=64), base + 20
        )
        self.assertTrue(reduced)
        self.assertAlmostEqual(18.7, pacer.rate_mbps)


class ConfigMigrationTests(unittest.TestCase):
    def test_v1_transport_fields_are_removed(self):
        defaults = {
            "server_ip": "192.168.1.2",
            "server_port": 8888,
            "color_mode": "rgb332",
        }
        migrated = migrate_v2_config({
            "server_ip": "192.168.1.9",
            "server_port": "9999",
            "resolution": [120, 120],
            "color_mode": "rgb565",
            "lines_per_packet": 4,
            "udp_interval": 0.001,
        }, defaults)
        self.assertEqual([240, 240], migrated["resolution"])
        self.assertEqual("rgb565", migrated["color_mode"])
        self.assertEqual(2, migrated["transport_version"])
        self.assertNotIn("lines_per_packet", migrated)
        self.assertNotIn("udp_interval", migrated)


if __name__ == "__main__":
    unittest.main()
