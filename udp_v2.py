"""High-throughput UDP v2 transport shared by the GUI and benchmark tool."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import secrets
import select
import socket
import struct
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np


WIDTH = HEIGHT = 240
PAYLOAD_SIZE = 1440
DATA_MAGIC = b"SSD2"
FEEDBACK_MAGIC = b"SSF2"
DATA_HEADER = struct.Struct(">4sIIBBH")
FEEDBACK_PACKET = struct.Struct(">4s12IHHII")
DATA_PACKET_SIZE = DATA_HEADER.size + PAYLOAD_SIZE
FEEDBACK_PACKET_SIZE = FEEDBACK_PACKET.size

MODE_RGB332 = 0
MODE_RGB565 = 1

MODE_NAMES = {
    MODE_RGB332: "rgb332",
    MODE_RGB565: "rgb565",
}
MODE_CODES = {value: key for key, value in MODE_NAMES.items()}
LINES_PER_CHUNK = {
    MODE_RGB332: 6,
    MODE_RGB565: 3,
}
CHUNKS_PER_FRAME = {
    mode: HEIGHT // lines for mode, lines in LINES_PER_CHUNK.items()
}
FRAME_PAYLOAD_SIZE = {
    MODE_RGB332: WIDTH * HEIGHT,
    MODE_RGB565: WIDTH * HEIGHT * 2,
}


def migrate_v2_config(document: object, defaults: dict) -> dict:
    """Migrate v1/user YAML data to the small UDP v2 configuration surface."""
    source = document if isinstance(document, dict) else {}
    color_mode = str(source.get("color_mode", defaults["color_mode"])).lower()
    if color_mode not in MODE_CODES:
        color_mode = defaults["color_mode"]
    try:
        port = int(source.get("server_port", defaults["server_port"]))
    except (TypeError, ValueError):
        port = int(defaults["server_port"])
    if not 0 < port < 65536:
        port = int(defaults["server_port"])
    migrated = {
        "server_ip": str(source.get("server_ip") or defaults["server_ip"]),
        "server_port": port,
        "resolution": [240, 240],
        "color_mode": color_mode,
        "transport_version": 2,
    }
    for key in ("preset", "preset_type", "personal_presets"):
        if key in source:
            migrated[key] = source[key]
    return migrated


def normalize_mode(mode: int | str) -> int:
    if isinstance(mode, str):
        try:
            return MODE_CODES[mode.lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported color mode: {mode}") from exc
    if mode not in MODE_NAMES:
        raise ValueError(f"unsupported color mode: {mode}")
    return mode


def encode_frame_bgr(frame: np.ndarray, mode: int | str) -> bytes:
    """Resize a BGR888 image and return the exact v2 frame payload."""
    mode = normalize_mode(mode)
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] < 3:
        raise ValueError("frame must be a BGR numpy array with three channels")
    if frame.shape[:2] != (HEIGHT, WIDTH):
        frame = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
    bgr = np.ascontiguousarray(frame[:, :, :3], dtype=np.uint8)
    b = bgr[:, :, 0]
    g = bgr[:, :, 1]
    r = bgr[:, :, 2]
    if mode == MODE_RGB332:
        encoded = ((r >> 5) << 5) | ((g >> 5) << 2) | (b >> 6)
        return np.ascontiguousarray(encoded, dtype=np.uint8).tobytes()

    # Network byte order is also the byte order expected by ST7789 RAMWR.
    rgb565 = (
        (r.astype(np.uint16) >> 3) << 11
        | (g.astype(np.uint16) >> 2) << 5
        | (b.astype(np.uint16) >> 3)
    )
    return rgb565.astype(">u2", copy=False).tobytes()


def decode_frame_for_preview(payload: bytes, mode: int | str) -> np.ndarray:
    """Decode the quantized wire image to BGR888 for the GUI preview."""
    mode = normalize_mode(mode)
    if len(payload) != FRAME_PAYLOAD_SIZE[mode]:
        raise ValueError("invalid encoded frame length")
    if mode == MODE_RGB332:
        value = np.frombuffer(payload, dtype=np.uint8).reshape(HEIGHT, WIDTH)
        r = ((value >> 5) & 0x07).astype(np.uint16) * 255 // 7
        g = ((value >> 2) & 0x07).astype(np.uint16) * 255 // 7
        b = (value & 0x03).astype(np.uint16) * 255 // 3
    else:
        value = np.frombuffer(payload, dtype=">u2").reshape(HEIGHT, WIDTH)
        r = ((value >> 11) & 0x1F).astype(np.uint16) * 255 // 31
        g = ((value >> 5) & 0x3F).astype(np.uint16) * 255 // 63
        b = (value & 0x1F).astype(np.uint16) * 255 // 31
    return np.dstack((b, g, r)).astype(np.uint8)


def make_data_packet(
    session_id: int,
    frame_id: int,
    mode: int | str,
    chunk_index: int,
    payload: bytes | memoryview,
) -> bytes:
    mode = normalize_mode(mode)
    if len(payload) != PAYLOAD_SIZE:
        raise ValueError(f"v2 chunks must contain exactly {PAYLOAD_SIZE} bytes")
    if not 0 <= chunk_index < CHUNKS_PER_FRAME[mode]:
        raise ValueError("chunk index is outside the selected mode")
    return DATA_HEADER.pack(
        DATA_MAGIC,
        session_id & 0xFFFFFFFF,
        frame_id & 0xFFFFFFFF,
        mode,
        chunk_index,
        PAYLOAD_SIZE,
    ) + payload


def packetize_frame(
    payload: bytes,
    session_id: int,
    frame_id: int,
    mode: int | str,
) -> list[bytes]:
    mode = normalize_mode(mode)
    if len(payload) != FRAME_PAYLOAD_SIZE[mode]:
        raise ValueError("encoded frame has the wrong size for its color mode")
    view = memoryview(payload)
    return [
        make_data_packet(
            session_id,
            frame_id,
            mode,
            chunk_index,
            view[offset:offset + PAYLOAD_SIZE],
        )
        for chunk_index, offset in enumerate(range(0, len(payload), PAYLOAD_SIZE))
    ]


@dataclass(frozen=True)
class Feedback:
    session_id: int
    sequence: int
    latest_rx_frame: int
    latest_complete_frame: int
    latest_displayed_frame: int
    rx_packets: int
    accepted_packets: int
    overflow_packets: int
    invalid_packets: int
    stale_packets: int
    incomplete_frames: int
    displayed_frames: int
    queue_depth: int
    queue_capacity: int
    free_heap: int
    uptime_ms: int


def parse_feedback(data: bytes) -> Feedback:
    if len(data) != FEEDBACK_PACKET_SIZE:
        raise ValueError("invalid feedback size")
    unpacked = FEEDBACK_PACKET.unpack(data)
    if unpacked[0] != FEEDBACK_MAGIC:
        raise ValueError("invalid feedback magic")
    return Feedback(*unpacked[1:])


def _u32_delta(current: int, previous: int) -> int:
    return (current - previous) & 0xFFFFFFFF


def _u32_at_or_before(candidate: int, reference: int) -> bool:
    """Return whether candidate is not newer than reference in serial order."""
    return _u32_delta(reference, candidate) < 0x80000000


class AdaptivePacer:
    """Feedback-driven two-packet burst pacer."""

    def __init__(
        self,
        initial_mbps: float = 22.0,
        minimum_mbps: float = 12.0,
        maximum_mbps: float = 30.0,
    ) -> None:
        self.minimum_bps = minimum_mbps * 1_000_000
        self.maximum_bps = maximum_mbps * 1_000_000
        self.rate_bps = initial_mbps * 1_000_000
        self._next_burst_ns = time.perf_counter_ns()
        self._previous: Optional[Feedback] = None
        self._last_increase_ns = self._next_burst_ns
        self._queue_depth = 0
        self._queue_capacity = 24

    @property
    def rate_mbps(self) -> float:
        return self.rate_bps / 1_000_000

    def update(self, feedback: Feedback, now_ns: Optional[int] = None) -> bool:
        now_ns = time.perf_counter_ns() if now_ns is None else now_ns
        self._queue_capacity = max(1, feedback.queue_capacity)
        congested_depth = max(18, self._queue_capacity - 8)
        loaded_depth = max(12, self._queue_capacity // 2)
        congested = feedback.queue_depth >= congested_depth
        if self._previous is not None:
            overflow_delta = _u32_delta(
                feedback.overflow_packets, self._previous.overflow_packets)
            stale_delta = _u32_delta(
                feedback.stale_packets, self._previous.stale_packets)
            incomplete_delta = _u32_delta(
                feedback.incomplete_frames, self._previous.incomplete_frames)
            # Overflow is always congestion. Stale/incomplete counters can also
            # be the cleanup consequence of one isolated late packet; only let
            # them reduce the rate while the receive window is actually loaded.
            congested = congested or overflow_delta >= 64 or (
                feedback.queue_depth >= congested_depth
                and bool(stale_delta or incomplete_delta)
            )
        self._queue_depth = feedback.queue_depth
        self._previous = feedback
        if congested:
            self.rate_bps = max(self.minimum_bps, self.rate_bps * 0.85)
            self._last_increase_ns = now_ns
            return True
        if feedback.queue_depth <= loaded_depth and now_ns - self._last_increase_ns >= 1_000_000_000:
            self.rate_bps = min(self.maximum_bps, self.rate_bps + 500_000)
            self._last_increase_ns = now_ns
        return False

    def wait_for_burst(self, byte_count: int, stop_event: Optional[threading.Event] = None) -> None:
        duration_ns = int(byte_count * 8 * 1_000_000_000 / self.rate_bps)
        pause_depth = max(22, self._queue_capacity - 6)
        if self._queue_depth >= pause_depth:
            duration_ns += 5_000_000
        now_ns = time.perf_counter_ns()
        # The token bucket holds exactly one two-packet burst. Small scheduler
        # overruns can be recovered against the absolute clock, but a delay of
        # a whole burst period means the bucket is merely full, not that an
        # arbitrary backlog of bursts may be sent at once.
        if self._next_burst_ns < now_ns - duration_ns:
            self._next_burst_ns = now_ns
        wait_ns = self._next_burst_ns - now_ns
        if wait_ns > 250_000:
            time.sleep((wait_ns - 150_000) / 1_000_000_000)
        while time.perf_counter_ns() < self._next_burst_ns:
            if stop_event is not None and stop_event.is_set():
                return
        # Keep an absolute token schedule.  Using max(now, deadline) here would
        # add Python/encoding overhead to every burst and undershoot the
        # configured wire rate by 20% or more.  A caller that is only slightly
        # late may catch up, but still emits at most the configured two-packet
        # microburst.  Long stalls are rebased by the guard at the top.
        self._next_burst_ns += duration_ns


@dataclass(frozen=True)
class SenderSnapshot:
    elapsed: float
    sent_frames: int
    sent_packets: int
    sent_bytes: int
    sent_fps: float
    packet_rate: float
    udp_mbps: float
    rate_limit_mbps: float
    displayed_fps: float
    display_efficiency: float
    queue_depth: int
    queue_capacity: int
    overflow_packets: int
    incomplete_frames: int
    stale_packets: int
    free_heap: int
    latency_p95_ms: Optional[float]
    latest_feedback: Optional[Feedback]


class V2Sender:
    def __init__(self, host: str, port: int, mode: int | str) -> None:
        self.host = host
        self.port = int(port)
        self.mode = normalize_mode(mode)
        self.session_id = secrets.randbits(32) or 1
        self.frame_id = 0
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.connect((host, self.port))
        self.socket.setblocking(False)
        # Validated framed working points: both modes use a 30 Mbit/s packet
        # clock, with mode-specific frame caps and RGB565 display ACK gating.
        # These two high-resolution presets cannot retreat below their physical
        # bandwidth floors; the reusable AdaptivePacer still defaults to the
        # general 12-30 Mbit/s range for diagnostics and future transports.
        packet_rate = 30.0
        self.pacer = AdaptivePacer(
            initial_mbps=packet_rate,
            minimum_mbps=packet_rate,
            maximum_mbps=packet_rate,
        )
        self.frame_rate_limit = 47.0 if self.mode == MODE_RGB332 else 25.5
        self._intra_burst_gap_ns = 400_000 if self.mode == MODE_RGB565 else 0
        self._frame_period_ns = int(1_000_000_000 / self.frame_rate_limit)
        self._next_frame_ns = time.perf_counter_ns()
        self.started_at = time.perf_counter()
        self.sent_frames = 0
        self.sent_packets = 0
        self.sent_bytes = 0
        self.latest_feedback: Optional[Feedback] = None
        self._displayed_at_start = 0
        self._send_times: dict[int, int] = {}
        self._latencies_ms: deque[float] = deque(maxlen=512)

    def close(self) -> None:
        self.socket.close()

    def __enter__(self) -> "V2Sender":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _receive_feedback(self) -> None:
        while True:
            try:
                data = self.socket.recv(FEEDBACK_PACKET_SIZE + 1)
            except BlockingIOError:
                return
            try:
                feedback = parse_feedback(data)
            except ValueError:
                continue
            if feedback.session_id != self.session_id:
                continue
            if self.latest_feedback is None:
                self._displayed_at_start = feedback.displayed_frames
            self.latest_feedback = feedback
            self.pacer.update(feedback)
            sent_at = self._send_times.get(feedback.latest_displayed_frame)
            if sent_at is not None:
                self._latencies_ms.append((time.perf_counter_ns() - sent_at) / 1_000_000)
            # The displayed frame is monotonic within one session, including
            # the uint32 wrap from 0xffffffff back to zero.
            for frame_id in tuple(self._send_times):
                if _u32_at_or_before(frame_id, feedback.latest_displayed_frame):
                    self._send_times.pop(frame_id, None)

    def _wait_for_frame_slot(self, stop_event: Optional[threading.Event]) -> bool:
        now_ns = time.perf_counter_ns()
        if self._next_frame_ns < now_ns - self._frame_period_ns:
            self._next_frame_ns = now_ns
        wait_ns = self._next_frame_ns - now_ns
        if wait_ns > 0:
            if stop_event is not None:
                if stop_event.wait(wait_ns / 1_000_000_000):
                    return False
            else:
                time.sleep(wait_ns / 1_000_000_000)
        self._next_frame_ns += self._frame_period_ns
        return True

    def _send_packets(
        self,
        packets: list[bytes],
        stop_event: Optional[threading.Event],
    ) -> bool:
        for index in range(0, len(packets), 2):
            if stop_event is not None and stop_event.is_set():
                return False
            burst = packets[index:index + 2]
            self.pacer.wait_for_burst(sum(map(len, burst)), stop_event)
            for packet_offset, packet in enumerate(burst):
                while True:
                    try:
                        self.socket.send(packet)
                        break
                    except BlockingIOError:
                        if stop_event is not None and stop_event.is_set():
                            return False
                        select.select([], [self.socket], [], 0.005)
                self.sent_packets += 1
                self.sent_bytes += len(packet)
                if packet_offset + 1 < len(burst):
                    gap_deadline = time.perf_counter_ns() + self._intra_burst_gap_ns
                    while time.perf_counter_ns() < gap_deadline:
                        if stop_event is not None and stop_event.is_set():
                            return False
            self._receive_feedback()
        return True

    def send_payload(
        self,
        payload: bytes,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        packets = packetize_frame(payload, self.session_id, self.frame_id, self.mode)
        if not self._wait_for_frame_slot(stop_event):
            return False
        current_frame_id = self.frame_id
        self._send_times[current_frame_id] = time.perf_counter_ns()
        if not self._send_packets(packets, stop_event):
            self._send_times.pop(current_frame_id, None)
            return False

        # Core 1 sends an immediate feedback packet after the final DMA group.
        # Keep at most two frames in flight: one frame hides ACK round-trip time,
        # while the second-frame guard prevents an unbounded receive backlog.
        display_wait_ns = 12_000_000 if self.mode == MODE_RGB332 else 22_000_000
        maximum_inflight = 2
        ack_deadline = time.perf_counter_ns() + display_wait_ns
        while time.perf_counter_ns() < ack_deadline:
            self._receive_feedback()
            feedback = self.latest_feedback
            if feedback is not None:
                outstanding = _u32_delta(
                    current_frame_id, feedback.latest_displayed_frame
                )
                if outstanding < maximum_inflight:
                    break
            if stop_event is not None and stop_event.is_set():
                self._send_times.pop(current_frame_id, None)
                return False
            time.sleep(0.0002)

        self.sent_frames += 1
        self.frame_id = (self.frame_id + 1) & 0xFFFFFFFF
        return True

    def send_frame_bgr(
        self,
        frame: np.ndarray,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        return self.send_payload(encode_frame_bgr(frame, self.mode), stop_event)

    def snapshot(self) -> SenderSnapshot:
        elapsed = max(time.perf_counter() - self.started_at, 1e-9)
        feedback = self.latest_feedback
        displayed = 0 if feedback is None else _u32_delta(
            feedback.displayed_frames, self._displayed_at_start
        )
        useful_bytes = displayed * FRAME_PAYLOAD_SIZE[self.mode]
        latencies = sorted(self._latencies_ms)
        p95 = None
        if latencies:
            p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        return SenderSnapshot(
            elapsed=elapsed,
            sent_frames=self.sent_frames,
            sent_packets=self.sent_packets,
            sent_bytes=self.sent_bytes,
            sent_fps=self.sent_frames / elapsed,
            packet_rate=self.sent_packets / elapsed,
            udp_mbps=self.sent_bytes * 8 / elapsed / 1_000_000,
            rate_limit_mbps=self.pacer.rate_mbps,
            displayed_fps=displayed / elapsed,
            display_efficiency=useful_bytes / max(
                1, self.sent_frames * FRAME_PAYLOAD_SIZE[self.mode]
            ),
            queue_depth=0 if feedback is None else feedback.queue_depth,
            queue_capacity=0 if feedback is None else feedback.queue_capacity,
            overflow_packets=0 if feedback is None else feedback.overflow_packets,
            incomplete_frames=0 if feedback is None else feedback.incomplete_frames,
            stale_packets=0 if feedback is None else feedback.stale_packets,
            free_heap=0 if feedback is None else feedback.free_heap,
            latency_p95_ms=p95,
            latest_feedback=feedback,
        )


def stream_latest_frames(
    frame_provider: Callable[[], Optional[np.ndarray]],
    sender: V2Sender,
    stop_event: threading.Event,
    preview_callback: Optional[Callable[[np.ndarray], None]] = None,
    stats_callback: Optional[Callable[[SenderSnapshot], None]] = None,
) -> None:
    """Capture/encode on a producer while the caller sends only the latest frame."""
    condition = threading.Condition()
    latest: dict[str, object] = {"version": 0, "payload": None, "error": None}

    def produce() -> None:
        next_capture = time.perf_counter()
        try:
            while not stop_event.is_set():
                frame = frame_provider()
                if frame is None:
                    time.sleep(0.001)
                    continue
                payload = encode_frame_bgr(frame, sender.mode)
                with condition:
                    latest["version"] = int(latest["version"]) + 1
                    latest["payload"] = payload
                    condition.notify()
                next_capture += 1.0 / 120.0
                remaining = next_capture - time.perf_counter()
                if remaining > 0:
                    time.sleep(remaining)
                elif remaining < -0.1:
                    next_capture = time.perf_counter()
        except BaseException as exc:
            with condition:
                latest["error"] = exc
                condition.notify()

    producer = threading.Thread(target=produce, name="udp-v2-capture", daemon=True)
    producer.start()
    consumed_version = 0
    next_stats = time.perf_counter() + 2.0
    try:
        while not stop_event.is_set():
            with condition:
                condition.wait_for(
                    lambda: stop_event.is_set()
                    or latest["error"] is not None
                    or int(latest["version"]) != consumed_version,
                    timeout=0.1,
                )
                if latest["error"] is not None:
                    raise latest["error"]  # type: ignore[misc]
                if stop_event.is_set() or latest["payload"] is None:
                    continue
                consumed_version = int(latest["version"])
                payload = latest["payload"]
            if not sender.send_payload(payload, stop_event):  # type: ignore[arg-type]
                break
            if preview_callback is not None:
                preview_callback(decode_frame_for_preview(payload, sender.mode))  # type: ignore[arg-type]
            if stats_callback is not None and time.perf_counter() >= next_stats:
                stats_callback(sender.snapshot())
                next_stats = time.perf_counter() + 2.0
    finally:
        stop_event.set()
        with condition:
            condition.notify_all()
        producer.join(timeout=1.0)
