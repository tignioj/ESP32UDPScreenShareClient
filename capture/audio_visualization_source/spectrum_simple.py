import sounddevice as sd
import numpy as np
import cv2

# ================= 配置 =================
SAMPLE_RATE = 44100
BLOCK_SIZE  = 512
WIDTH       = 240
HEIGHT      = 240
CHANNELS    = 2

# 选择 VB-Cable 的 CABLE Output 设备编号
DEVICE_ID = None
for i, dev in enumerate(sd.query_devices()):
    if "CABLE Output" in dev['name']:
        DEVICE_ID = i
        break

if DEVICE_ID is None:
    raise RuntimeError("未找到 VB-Audio CABLE Output")

print("使用设备:", sd.query_devices()[DEVICE_ID]['name'])

# ================= 数据缓冲 =================
window = np.hanning(BLOCK_SIZE)
spectrum = np.zeros(BLOCK_SIZE // 2 + 1, dtype=np.float32)

def audio_callback(indata, frames, time, status):
    global spectrum
    if status:
        print(status)

    # 取左声道
    mono = indata[:, 0].copy()
    fft = np.abs(np.fft.rfft(mono * window))
    spectrum = fft

# ================= 启动音频流 =================
stream = sd.InputStream(
    device=DEVICE_ID,
    channels=CHANNELS,
    samplerate=SAMPLE_RATE,
    blocksize=BLOCK_SIZE,
    callback=audio_callback
)

# ================= OpenCV 显示 =================
cv2.namedWindow("Audio Spectrum", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Audio Spectrum", WIDTH, HEIGHT)

with stream:
    while True:
        img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        # 取低频段（更有观感）
        spec = spectrum[:WIDTH]
        if spec.max() > 0:
            spec = spec / spec.max()

        for x, v in enumerate(spec):
            y = int(v * HEIGHT)
            cv2.line(
                img,
                (x, HEIGHT),
                (x, HEIGHT - y),
                (0, 255, 0),
                1
            )

        cv2.imshow("Audio Spectrum", img)
        if cv2.waitKey(1) & 0xFF == 27:
            break

cv2.destroyAllWindows()
