import cv2
import time
from capture.video_source.video_source import VideoFileSource
from capture.interface import SourceType

if __name__ == "__main__":
    # 配置视频源
    video_source = VideoFileSource(SourceType.VIDEO_FILE, source_id="video_player")

    # 初始化
    video_source.initialize(
        # video_path=r"C:\Users\Administrator\Desktop\obsrecord",
        video_path=r"I:\genshin_video\character_show",
        auto_play_next=True,
        random_play=True,
        first_play_video="xinhai.mp4",
        fps=30
    )

    video_source.start()

    try:
        while True:
            frame = video_source.capture()
            if frame is not None:
                # 显示视频帧
                cv2.imshow("Video Playback", frame)
            else:
                print('Empty Frame!')

            # 按 q 退出
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            # 控制帧率，如果capture返回None会自动等待下一帧
            time.sleep(0.001)

    finally:
        video_source.stop()
        video_source.release()
        cv2.destroyAllWindows()
