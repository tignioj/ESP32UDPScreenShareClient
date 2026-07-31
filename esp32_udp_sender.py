import sys

from esp32_udp_header import ESP32UDPHeader

import cv2
import numpy as np
import socket
import time

from capture.config import get_streamer
cap = get_streamer()

# ------------------------------
# 配置参数
# ------------------------------
# ESP32_IP = "192.168.32.116"   # ESP32 的局域网 IP
ESP32_IP = "192.168.30.161"  # ESP32 的局域网 IP
ESP32_PORT = 8888  # UDP 端口

# 固定配置，不要乱改，改了会炸
# 高清全彩
config1 = {'resolution': ESP32UDPHeader.RES_240, 'color_mode': ESP32UDPHeader.COLOR_RGB565, 'lines_per_packet': 3,'udp_interval': 0.00075}
# 高清低彩
config2 = {'resolution': ESP32UDPHeader.RES_240, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 6,'udp_interval': 0.001}
# 中清高彩
config3 = {'resolution': ESP32UDPHeader.RES_180, 'color_mode': ESP32UDPHeader.COLOR_RGB565, 'lines_per_packet': 4,'udp_interval': 0.001}

# 中清低彩
# config4 = {'resolution': ESP32UDPHeader.RES_180, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 4,'udp_interval': 0.0005}
# config4 = {'resolution': ESP32UDPHeader.RES_180, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 8,'udp_interval': 0.001}
config4 = {'resolution': ESP32UDPHeader.RES_180, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 6,'udp_interval': 0.001}
# 低请高彩
# config5 = {'resolution': ESP32UDPHeader.RES_120, 'color_mode': ESP32UDPHeader.COLOR_RGB565, 'lines_per_packet': 6,'udp_interval': 0.000945}
config5 = {'resolution': ESP32UDPHeader.RES_120, 'color_mode': ESP32UDPHeader.COLOR_RGB565, 'lines_per_packet': 4,'udp_interval': 0.001}
# 低请低彩
# config6 = {'resolution': ESP32UDPHeader.RES_120, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 6,'udp_interval': 0.000945}
config6 = {'resolution': ESP32UDPHeader.RES_120, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 4,'udp_interval': 0.001}

option = config2

LINES_PER_PACKET = option['lines_per_packet']  # 每个 UDP 包发多少行
if option['resolution'] == ESP32UDPHeader.RES_240: WIDTH = 240
elif option['resolution'] == ESP32UDPHeader.RES_180: WIDTH = 180
elif option['resolution'] == ESP32UDPHeader.RES_120: WIDTH = 120
else:
    print("你没有设置分辨率！")
    WIDTH = 240
HEIGHT = WIDTH
ESP32UDPHeader.validate_stream_config(WIDTH, option['color_mode'], LINES_PER_PACKET)

# ------------------------------
# 初始化 UDP
# ------------------------------
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def bgr_to_rgb332_cv2_style(bgr_image):
    """类似OpenCV风格的RGB332转换"""
    b, g, r = cv2.split(bgr_image)
    r_332 = (r >> 5) & 0x07
    g_332 = (g >> 5) & 0x07
    b_332 = (b >> 6) & 0x03
    return (r_332 << 5) | (g_332 << 2) | b_332

# 主循环
# ------------------------------
frame_id = 0
stats_started = time.perf_counter()
stats_frames = 0
stats_packets = 0
stats_bytes = 0
while True:
    sc = cap.get_frame()
    if sc is None:
        time.sleep(0.001)
        continue
    # sc = cap.capture_region(641,377,600,600)
    # sc = cap.capture_fullscreen()
    if sc.shape[0] != HEIGHT or sc.shape[1] != WIDTH:
        sc = cv2.resize(sc, (WIDTH, HEIGHT))
    # cv2.imshow('screenshot',sc)
    # cv2.waitKey(1)
    if option['color_mode'] == ESP32UDPHeader.COLOR_RGB332:
        rgb = bgr_to_rgb332_cv2_style(sc)
    else:
        rgb = cv2.cvtColor(sc, cv2.COLOR_BGR2BGR565)

    frame_id = (frame_id + 1) & 0xFFFF
    frame_blob = np.ascontiguousarray(rgb).tobytes()
    row_bytes = WIDTH * (2 if option['color_mode'] == ESP32UDPHeader.COLOR_RGB565 else 1)
    next_packet_at = time.perf_counter()
    for y in range(0, HEIGHT, LINES_PER_PACKET):
        remaining = next_packet_at - time.perf_counter()
        if remaining > 0:
            time.sleep(remaining)

        lines = min(LINES_PER_PACKET, HEIGHT - y)
        offset = y * row_bytes
        payload = frame_blob[offset:offset + lines * row_bytes]
        header = ESP32UDPHeader.make_header(frame_id=frame_id, y_start=y,resolution=option['resolution'],
                                            color_mode=option['color_mode'], line_count=lines)
        datagram = header + payload
        sock.sendto(datagram, (ESP32_IP, ESP32_PORT))
        stats_packets += 1
        stats_bytes += len(datagram)
        next_packet_at += option['udp_interval']

    stats_frames += 1
    now = time.perf_counter()
    elapsed = now - stats_started
    if elapsed >= 2.0:
        print(
            f"发送: {stats_frames / elapsed:.1f} FPS, "
            f"{stats_packets / elapsed:.0f} 包/秒, "
            f"{stats_bytes * 8 / elapsed / 1_000_000:.2f} Mbit/s"
        )
        stats_started = now
        stats_frames = stats_packets = stats_bytes = 0
