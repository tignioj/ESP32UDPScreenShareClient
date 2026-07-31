import struct

class ESP32UDPHeader(object):

    HEADER_SIZE = 5
    MAX_UDP_DATAGRAM = 1460
    DISPLAY_LINE_BATCH = 8

    # 自定义包头信息
    # 一个字节占8位, 前两位表示分辨率，2-4位表示色彩模式，剩下4位表示行数，表示本张图片一次画几行
    # 这里必须定死，和ESP32一致
    # 包头的分辨率信息
    RES_240 = 0
    RES_180 = 1
    RES_120 = 2

    # 包头的色彩模式。
    COLOR_RGB565 = 0
    COLOR_RGB332 = 1

    @classmethod
    def max_lines_per_packet(cls, width, color_mode):
        """Return the largest packet height supported by MTU and the receiver buffer."""
        if width not in (240, 180, 120):
            raise ValueError(f"不支持的分辨率: {width}")
        if color_mode not in (cls.COLOR_RGB565, cls.COLOR_RGB332):
            raise ValueError(f"不支持的颜色模式: {color_mode}")

        bytes_per_pixel = 2 if color_mode == cls.COLOR_RGB565 else 1
        mtu_limit = (cls.MAX_UDP_DATAGRAM - cls.HEADER_SIZE) // (width * bytes_per_pixel)

        # ESP32 stores at most 8 output lines after scaling.
        render_limit = {240: 8, 180: 6, 120: 4}[width]
        return min(15, mtu_limit, render_limit)

    @classmethod
    def validate_stream_config(cls, width, color_mode, lines_per_packet):
        max_lines = cls.max_lines_per_packet(width, color_mode)
        if not 1 <= lines_per_packet <= max_lines:
            mode_name = "RGB565" if color_mode == cls.COLOR_RGB565 else "RGB332"
            raise ValueError(
                f"{width}x{width} {mode_name} 每包行数必须在 1-{max_lines} 之间，"
                f"当前为 {lines_per_packet}"
            )
        return max_lines

    @staticmethod
    def make_flags(resolution, color_mode, line_count):
        assert 0 <= resolution <= 3
        assert 0 <= color_mode <= 3
        assert 0 <= line_count <= 15

        flags = (
            (resolution & 0b11) << 6 |
            (color_mode & 0b11) << 4 |
            (line_count & 0b1111)
        )
        return flags
    @staticmethod
    def make_header(frame_id, y_start, resolution, color_mode, line_count):
        flags = ESP32UDPHeader.make_flags(resolution, color_mode, line_count)

        # > = 大端
        # H = uint16
        # B = uint8
        return struct.pack(">HHB",
                           frame_id,
                           y_start,
                           flags)
    # ESP32如何解析？

"""
uint8_t header[5];
if (udp.read(header, 5) != 5) return;
uint16_t frame_id = (header[0] << 8) | header[1];
uint16_t y_start  = (header[2] << 8) | header[3];

解析flag
uint8_t flags = header[4];

uint8_t resolution = (flags >> 6) & 0b11;
uint8_t color_mode = (flags >> 4) & 0b11;
uint8_t line_count = flags & 0b1111;

"""

if __name__ == '__main__':
    # 示例
    hdr = ESP32UDPHeader.make_header(
        frame_id=123,
        y_start=32,
        resolution=ESP32UDPHeader.RES_240,
        color_mode=ESP32UDPHeader.COLOR_RGB565,
        line_count=12
    )

