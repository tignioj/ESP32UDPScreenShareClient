"""Hardware benchmark for the ESP32 screen-share v2 transport."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import numpy as np

from udp_v2 import (
    FRAME_PAYLOAD_SIZE,
    MODE_CODES,
    V2Sender,
    encode_frame_bgr,
)


def make_test_frame(sequence: int) -> np.ndarray:
    x = np.arange(240, dtype=np.uint16)[None, :]
    y = np.arange(240, dtype=np.uint16)[:, None]
    frame = np.empty((240, 240, 3), dtype=np.uint8)
    frame[:, :, 0] = (x + sequence * 3) & 0xFF
    frame[:, :, 1] = (y + sequence * 5) & 0xFF
    frame[:, :, 2] = ((x // 2 + y // 2) + sequence * 7) & 0xFF
    return frame


def make_test_payloads(mode: int, count: int = 16) -> list[bytes]:
    """Pre-encode synthetic frames so capture/encoding never stalls pacing."""
    return [encode_frame_bgr(make_test_frame(sequence), mode) for sequence in range(count)]


def run_phase(
    sender: V2Sender,
    seconds: float,
    sequence: int,
    payloads: list[bytes],
    frame_rate: float | None = None,
) -> int:
    deadline = time.perf_counter() + seconds
    next_frame = time.perf_counter()
    while time.perf_counter() < deadline:
        sender.send_payload(payloads[sequence % len(payloads)])
        sequence += 1
        if frame_rate is not None:
            next_frame += 1.0 / frame_rate
            delay = next_frame - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.1:
                next_frame = time.perf_counter()
    return sequence


def feedback_counter(feedback, name: str) -> int:
    return 0 if feedback is None else int(getattr(feedback, name))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True, help="ESP32 IPv4 address")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--mode", choices=sorted(MODE_CODES), default="rgb332")
    parser.add_argument("--warmup", type=float, default=10.0)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument(
        "--fixed-rate",
        type=float,
        metavar="MBIT_S",
        help="diagnostic: disable AIMD and pace at an exact payload datagram rate",
    )
    parser.add_argument(
        "--frame-rate",
        type=float,
        metavar="FPS",
        help="diagnostic: cap completed frame starts while retaining packet pacing",
    )
    parser.add_argument("--json", type=Path, help="write the full result as JSON")
    parser.add_argument("--strict", action="store_true", help="fail when acceptance gates are missed")
    args = parser.parse_args()

    mode = MODE_CODES[args.mode]
    target_fps = 45.0 if args.mode == "rgb332" else 24.0
    latency_limit = 100.0 if args.mode == "rgb332" else 150.0
    sequence = 0
    payloads = make_test_payloads(mode)

    print(f"Warm-up: {args.mode} for {args.warmup:g}s")
    with V2Sender(args.ip, args.port, mode) as sender:
        if args.fixed_rate is not None:
            fixed_bps = args.fixed_rate * 1_000_000
            sender.pacer.minimum_bps = fixed_bps
            sender.pacer.maximum_bps = fixed_bps
            sender.pacer.rate_bps = fixed_bps
        sequence = run_phase(sender, args.warmup, sequence, payloads, args.frame_rate)
        # Drain the warm-up tail so its final accepted/displayed frame is not
        # counted in the measurement interval.
        warmup_tail = (sender.frame_id - 1) & 0xFFFFFFFF
        drain_until = time.perf_counter() + 0.15
        while time.perf_counter() < drain_until:
            sender._receive_feedback()
            feedback = sender.latest_feedback
            if feedback is not None and feedback.latest_displayed_frame == warmup_tail:
                break
            time.sleep(0.002)
        start_feedback = sender.latest_feedback
        start_frames = sender.sent_frames
        start_packets = sender.sent_packets
        start_bytes = sender.sent_bytes
        started = time.perf_counter()
        start_displayed = feedback_counter(start_feedback, "displayed_frames")
        start_overflow = feedback_counter(start_feedback, "overflow_packets")
        start_accepted = feedback_counter(start_feedback, "accepted_packets")
        start_incomplete = feedback_counter(start_feedback, "incomplete_frames")
        start_stale = feedback_counter(start_feedback, "stale_packets")
        start_free_heap = feedback_counter(start_feedback, "free_heap")

        print(f"Measure: {args.mode} for {args.duration:g}s")
        sequence = run_phase(sender, args.duration, sequence, payloads, args.frame_rate)
        # Keep polling briefly so the final DMA completion reaches telemetry.
        settle_until = time.perf_counter() + 0.15
        while time.perf_counter() < settle_until:
            sender._receive_feedback()
            time.sleep(0.005)
        elapsed = time.perf_counter() - started
        final = sender.snapshot()
        feedback = sender.latest_feedback

    sent_frames = sender.sent_frames - start_frames
    sent_packets = sender.sent_packets - start_packets
    sent_bytes = sender.sent_bytes - start_bytes
    displayed_frames = feedback_counter(feedback, "displayed_frames") - start_displayed
    overflow_packets = feedback_counter(feedback, "overflow_packets") - start_overflow
    accepted_packets = feedback_counter(feedback, "accepted_packets") - start_accepted
    incomplete_frames = feedback_counter(feedback, "incomplete_frames") - start_incomplete
    stale_packets = feedback_counter(feedback, "stale_packets") - start_stale
    displayed_fps = displayed_frames / elapsed
    sent_fps = sent_frames / elapsed
    completion_ratio = displayed_frames / max(1, sent_frames)
    efficiency = displayed_frames * FRAME_PAYLOAD_SIZE[mode] / max(
        1, sent_packets * 1440
    )
    overflow_rate = overflow_packets / max(1, sent_packets)
    udp_mbps = sent_bytes * 8 / elapsed / 1_000_000
    estimated_ip_mbps = (sent_bytes + sent_packets * 28) * 8 / elapsed / 1_000_000
    useful_mbps = displayed_frames * FRAME_PAYLOAD_SIZE[mode] * 8 / elapsed / 1_000_000
    final_free_heap = feedback_counter(feedback, "free_heap")
    heap_drift = max(0, start_free_heap - final_free_heap)

    gates = {
        "feedback_received": feedback is not None,
        "displayed_fps": displayed_fps >= target_fps,
        "completion_ratio": completion_ratio >= 0.98,
        "useful_bandwidth_efficiency": efficiency >= 0.90,
        "overflow_rate": overflow_rate < 0.001,
        "free_heap": feedback is not None and feedback.free_heap >= 120_000,
        "heap_drift": feedback is not None and heap_drift <= 2_048,
        "latency_p95": final.latency_p95_ms is not None and final.latency_p95_ms < latency_limit,
    }
    result = {
        "mode": args.mode,
        "target_fps": target_fps,
        "warmup_seconds": args.warmup,
        "measurement_seconds": elapsed,
        "sent_frames": sent_frames,
        "displayed_frames": displayed_frames,
        "sent_fps": sent_fps,
        "displayed_fps": displayed_fps,
        "completion_ratio": completion_ratio,
        "sent_packets": sent_packets,
        "accepted_packets": accepted_packets,
        "sent_image_payload_bytes": sent_packets * 1440,
        "esp_accepted_payload_bytes": accepted_packets * 1440,
        "complete_display_bytes": displayed_frames * FRAME_PAYLOAD_SIZE[mode],
        "overflow_packets": overflow_packets,
        "overflow_rate": overflow_rate,
        "incomplete_frames": incomplete_frames,
        "stale_packets": stale_packets,
        "udp_mbps": udp_mbps,
        "estimated_ip_udp_mbps": estimated_ip_mbps,
        "useful_display_mbps": useful_mbps,
        "useful_bandwidth_efficiency": efficiency,
        "rate_limit_mbps": final.rate_limit_mbps,
        "fixed_rate_mbps": args.fixed_rate,
        "frame_rate_limit": (
            args.frame_rate if args.frame_rate is not None else sender.frame_rate_limit
        ),
        "queue_depth": final.queue_depth,
        "free_heap": final.free_heap,
        "start_free_heap": start_free_heap,
        "heap_drift_bytes": heap_drift,
        "latency_p95_ms": final.latency_p95_ms,
        "gates": gates,
        "feedback": None if feedback is None else asdict(feedback),
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Report: {args.json}")
    return 0 if not args.strict or all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
