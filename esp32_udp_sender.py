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
config1 = {'resolution': ESP32UDPHeader.RES_240, 'color_mode': ESP32UDPHeader.COLOR_RGB565, 'lines_per_packet': 3,'udp_interval': 0.0005}
# 高清低彩
config2 = {'resolution': ESP32UDPHeader.RES_240, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 6,'udp_interval': 0.0005}
# 中清高彩
config3 = {'resolution': ESP32UDPHeader.RES_180, 'color_mode': ESP32UDPHeader.COLOR_RGB565, 'lines_per_packet': 4,'udp_interval': 0.0005}

# 中清低彩
# config4 = {'resolution': ESP32UDPHeader.RES_180, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 4,'udp_interval': 0.0005}
# config4 = {'resolution': ESP32UDPHeader.RES_180, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 8,'udp_interval': 0.001}
config4 = {'resolution': ESP32UDPHeader.RES_180, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 6,'udp_interval': 0.00075}
# 低请高彩
# config5 = {'resolution': ESP32UDPHeader.RES_120, 'color_mode': ESP32UDPHeader.COLOR_RGB565, 'lines_per_packet': 6,'udp_interval': 0.000945}
config5 = {'resolution': ESP32UDPHeader.RES_120, 'color_mode': ESP32UDPHeader.COLOR_RGB565, 'lines_per_packet': 4,'udp_interval': 0.00075}
# 低请低彩
# config6 = {'resolution': ESP32UDPHeader.RES_120, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 6,'udp_interval': 0.000945}
config6 = {'resolution': ESP32UDPHeader.RES_120, 'color_mode': ESP32UDPHeader.COLOR_RGB332, 'lines_per_packet': 4,'udp_interval': 0.00075}

option = config1

LINES_PER_PACKET = option['lines_per_packet']  # 每个 UDP 包发多少行
if option['resolution'] == ESP32UDPHeader.RES_240: WIDTH = 240
elif option['resolution'] == ESP32UDPHeader.RES_180: WIDTH = 180
elif option['resolution'] == ESP32UDPHeader.RES_120: WIDTH = 120
else:
    print("你没有设置分辨率！")
    WIDTH = 240
HEIGHT = WIDTH

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
while True:
    # 控制帧率
    frame_id = (frame_id + 1) & 0xFFFF
    sc = cap.get_frame()
    # sc = cap.capture_region(641,377,600,600)
    # sc = cap.capture_fullscreen()
    sc = cv2.resize(sc, (WIDTH, HEIGHT))
    # cv2.imshow('screenshot',sc)
    # cv2.waitKey(1)
    if option['color_mode'] == ESP32UDPHeader.COLOR_RGB332:
        rgb = bgr_to_rgb332_cv2_style(sc)
    else:
        rgb = cv2.cvtColor(sc, cv2.COLOR_BGR2BGR565)

    for y in range(0, HEIGHT, LINES_PER_PACKET):
        start_time = time.time()
        lines = min(LINES_PER_PACKET, HEIGHT - y)
        payload = rgb[y:y + lines, :].flatten().tobytes()
        header = ESP32UDPHeader.make_header(frame_id=frame_id, y_start=y,resolution=option['resolution'],
                                            color_mode=option['color_mode'], line_count=lines)
        sock.sendto(header + payload, (ESP32_IP, ESP32_PORT))
        cost = time.time() - start_time
        time.sleep(option['udp_interval'])
