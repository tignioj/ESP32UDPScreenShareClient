"""Hardware fault-injection checks for the ESP32 UDP v2 receiver."""

from __future__ import annotations

import argparse
import json
import secrets
import socket
import time

from udp_v2 import (
    CHUNKS_PER_FRAME,
    FEEDBACK_PACKET_SIZE,
    MODE_RGB332,
    PAYLOAD_SIZE,
    make_data_packet,
    parse_feedback,
)


class HardwareProbe:
    def __init__(self, host: str, port: int) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.connect((host, port))
        self.socket.setblocking(False)
        self.payload = bytes(PAYLOAD_SIZE)

    def close(self) -> None:
        self.socket.close()

    def packet(self, session: int, frame: int, chunk: int) -> bytes:
        return make_data_packet(session, frame, MODE_RGB332, chunk, self.payload)

    def send(self, packet: bytes, delay: float = 0.0) -> None:
        while True:
            try:
                self.socket.send(packet)
                break
            except BlockingIOError:
                time.sleep(0.0002)
        if delay:
            time.sleep(delay)

    def complete_frame(self, session: int, frame: int, order=None) -> None:
        chunks = range(CHUNKS_PER_FRAME[MODE_RGB332]) if order is None else order
        for chunk in chunks:
            self.send(self.packet(session, frame, chunk), 0.0003)

    def wait_feedback(self, session: int, probe_packet: bytes, timeout: float = 1.0):
        deadline = time.perf_counter() + timeout
        next_probe = time.perf_counter() + 0.025
        latest = None
        while time.perf_counter() < deadline:
            try:
                raw = self.socket.recv(FEEDBACK_PACKET_SIZE + 1)
            except BlockingIOError:
                raw = None
            if raw:
                try:
                    feedback = parse_feedback(raw)
                except ValueError:
                    feedback = None
                if feedback is not None and feedback.session_id == session:
                    latest = feedback
                    if feedback.latest_displayed_frame != 0xFFFFFFFF:
                        return feedback
            now = time.perf_counter()
            if now >= next_probe:
                self.send(probe_packet)
                next_probe = now + 0.025
            time.sleep(0.001)
        return latest


def new_session() -> int:
    return secrets.randbits(32) or 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--port", type=int, default=8888)
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    details: dict[str, object] = {}
    probe = HardwareProbe(args.ip, args.port)
    try:
        # Start at chunk zero as required, then swap chunks 1/2 and duplicate 1.
        session = new_session()
        order = [0, 2, 1, 1, *range(3, CHUNKS_PER_FRAME[MODE_RGB332])]
        probe.complete_frame(session, 0, order)
        feedback = probe.wait_feedback(session, probe.packet(session, 0, 39))
        checks["duplicate_and_reorder"] = bool(
            feedback and feedback.displayed_frames >= 1 and feedback.stale_packets >= 1
        )
        details["duplicate_and_reorder"] = None if feedback is None else {
            "displayed_frames": feedback.displayed_frames,
            "stale_packets": feedback.stale_packets,
        }

        # Omit chunk five, allow the deadline to expire, then prove recovery on
        # the newest complete frame within the same session.
        session = new_session()
        missing = [chunk for chunk in range(40) if chunk != 5]
        probe.complete_frame(session, 0, missing)
        time.sleep(0.080)
        probe.complete_frame(session, 1)
        feedback = probe.wait_feedback(session, probe.packet(session, 1, 39))
        checks["missing_chunk_recovery"] = bool(
            feedback
            and feedback.displayed_frames >= 1
            and feedback.incomplete_frames >= 1
            and feedback.latest_displayed_frame == 1
        )
        details["missing_chunk_recovery"] = None if feedback is None else {
            "displayed_frames": feedback.displayed_frames,
            "incomplete_frames": feedback.incomplete_frames,
            "latest_displayed_frame": feedback.latest_displayed_frame,
        }

        # Fill the receive slots with frame starts while Core 1 waits for a
        # missing prebuffer chunk. The receiver must count overflow, then accept
        # a fresh session and draw it completely.
        session = new_session()
        for frame in range(256):
            probe.send(probe.packet(session, frame, 0))
        time.sleep(0.120)
        tail = probe.packet(session, 255, 39)
        probe.send(tail)
        feedback = probe.wait_feedback(session, tail)
        checks["queue_overflow_counted"] = bool(
            feedback and feedback.overflow_packets > 0
        )
        details["queue_overflow_counted"] = None if feedback is None else {
            "overflow_packets": feedback.overflow_packets,
            "queue_depth": feedback.queue_depth,
            "queue_capacity": feedback.queue_capacity,
        }

        recovery_session = new_session()
        probe.complete_frame(recovery_session, 0)
        feedback = probe.wait_feedback(
            recovery_session, probe.packet(recovery_session, 0, 39)
        )
        checks["session_switch_recovery"] = bool(
            feedback
            and feedback.session_id == recovery_session
            and feedback.displayed_frames >= 1
            and feedback.latest_displayed_frame == 0
        )
        details["session_switch_recovery"] = None if feedback is None else {
            "session_id": feedback.session_id,
            "displayed_frames": feedback.displayed_frames,
            "latest_displayed_frame": feedback.latest_displayed_frame,
            "free_heap": feedback.free_heap,
        }
    finally:
        probe.close()

    result = {"checks": checks, "details": details, "passed": all(checks.values())}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
