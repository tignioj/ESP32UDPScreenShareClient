# config.yaml
"""
streamer:
  sources:
    - type: "screen"
      id: "main_screen"
      params:
        display_idx: 0
        fps: 30
        region: [0, 0, 1920, 1080]

    - type: "camera"
      id: "webcam"
      params:
        camera_idx: 0
        resolution: [1280, 720]
        fps: 25

    - type: "camera"
      id: "ip_camera"
      params:
        url: "rtsp://192.168.1.100:554/stream"

  active_source: "main_screen"
  stream_url: "rtmp://server/live/stream"
  bitrate: 2500000
"""
import cv2

from capture.streamer import Streamer
import yaml
import sys,os
application_path = '.'
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
    application_path = os.path.join(application_path, '_internal')
elif __file__:
    application_path = os.path.dirname(os.path.dirname(__file__))

# def resource_path(rel_path):
#     if getattr(sys, 'frozen', False):
#         return os.path.join(sys._MEIPASS, rel_path)
#     return os.path.abspath(rel_path)

# cfg = resource_path("config.yaml")

__streamer:Streamer = None

def get_streamer() -> Streamer:
    global  __streamer
    # 加载配置
    if __streamer is None:
        with open(os.path.join(application_path,'config_stream.yaml'), encoding="utf-8",mode='r') as f:
            config = yaml.safe_load(f)
        # 创建推流器
        __streamer = Streamer(config.get('streamer', {}))
        # 初始化
        if not __streamer.initialize():
            raise Exception(f"Failed to initialize streamer")
    return __streamer
# 使用示例
def __main():
    streamer = get_streamer()
    try:
        # 推流循环
        while True:
            # 获取帧（自动从当前活动源获取）
            frame = streamer.get_frame()

            if frame is not None:
                # 推流处理...
                # stream_frame(frame)
                print(frame.shape)

                pass

            # 可以动态切换源
            # if some_condition:
            #     streamer.switch_source("webcam")

    except KeyboardInterrupt:
        print("Streaming stopped")
    finally:
        streamer.close()


if __name__ == "__main__":
    __main()