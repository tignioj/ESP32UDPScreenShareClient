"""Compatibility facade for the UDP v2 packet format.

New code should import :mod:`udp_v2` directly.  The class remains so existing
application imports fail with useful validation instead of silently emitting
the removed v1 wire format.
"""

from udp_v2 import (
    CHUNKS_PER_FRAME,
    DATA_HEADER,
    DATA_PACKET_SIZE,
    MODE_RGB332,
    MODE_RGB565,
    PAYLOAD_SIZE,
    make_data_packet,
)


class ESP32UDPHeader:
    HEADER_SIZE = DATA_HEADER.size
    DATA_PACKET_SIZE = DATA_PACKET_SIZE
    PAYLOAD_SIZE = PAYLOAD_SIZE
    WIDTH = 240
    COLOR_RGB332 = MODE_RGB332
    COLOR_RGB565 = MODE_RGB565

    @classmethod
    def chunks_per_frame(cls, color_mode):
        try:
            return CHUNKS_PER_FRAME[color_mode]
        except KeyError as exc:
            raise ValueError(f"unsupported v2 color mode: {color_mode}") from exc

    @classmethod
    def make_packet(cls, session_id, frame_id, color_mode, chunk_index, payload):
        return make_data_packet(
            session_id,
            frame_id,
            color_mode,
            chunk_index,
            payload,
        )
