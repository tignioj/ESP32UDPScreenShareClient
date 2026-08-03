"""Minimal command-line sender using the shared UDP v2 implementation."""

from __future__ import annotations

import argparse
import signal
import threading

from capture.config import get_streamer
from udp_v2 import (
    MODE_CODES,
    V2Sender,
    default_frame_rate_limit,
    stream_latest_frames,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--mode", choices=sorted(MODE_CODES), default="rgb332")
    parser.add_argument(
        "--fps",
        type=float,
        help="target send FPS (default/max: rgb332=47, rgb565=25.5)",
    )
    args = parser.parse_args()

    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    streamer = get_streamer()
    target_fps = args.fps if args.fps is not None else default_frame_rate_limit(args.mode)
    with V2Sender(
        args.ip,
        args.port,
        args.mode,
        frame_rate_limit=target_fps,
    ) as sender:
        stream_latest_frames(
            streamer.get_frame,
            sender,
            stop_event,
            frame_rate_provider=streamer.get_frame_rate,
        )


if __name__ == "__main__":
    main()
