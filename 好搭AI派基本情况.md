# 好搭AI派基本情况

> 整理方式：SSH 登录设备（192.168.0.109，用户 cxdz）实地勘察
> 整理时间：2026-09-12

---

## 一、启动后自动运行的程序在哪里

| 项目 | 路径 |
| --- | --- |
| 自启动入口 | `/home/cxdz/.config/autostart/python-manager.desktop` |
| 桌面快捷方式 | `/home/cxdz/Desktop/python-manager.desktop` |
| 程序本体 | `/home/cxdz/manager/app` |

`app` 是一个 **PyInstaller 打包的 PyQt5 程序**（"好搭AI派 V1.0 Python程序管理器"，内含 Python 3.8，源码不可直接读取）。
它运行在 **DISPLAY=:0** 的 GNOME 桌面会话里，就是你开机后在屏幕上看到的那个界面。

### 启动参数（来自 desktop 文件）

```
Exec=env PYTHONPATH=/home/cxdz/jupyter/lib /home/cxdz/manager/app
Path=/home/cxdz/jupyter/user/
Terminal=false
```

### 管理器界面构成

- **左侧**：扫描列出 `/home/cxdz/jupyter/user/` 下的 Python 文件/目录（2026-09-12 快照为 13 个）
- **右侧**：被运行程序的输出窗口
- **按钮**：运行(F5) / 停止(F6) / 刷新(F7)
- **顶部**：电量、WiFi、IP 地址、网络设置
- **底部**：状态提示（如"无USB摄像头"）
- **启动日志**：管理器启动时会检测外接硬件，日志里可见 "ADBD端口监听正常"

---

## 二、其他程序在哪里

全部集中在 `/home/cxdz/jupyter/` 下：

| 路径 | 用途 |
| --- | --- |
| `jupyter/user/` | **用户程序目录**（管理器扫描的就是这里） |
| `jupyter/lib/` | 厂商闭源驱动库（35 个 `.so`） |
| `jupyter/model/` | AI 模型（`.rknn` 格式，跑在 NPU 上） |
| `jupyter/assets/` | 中文字体等资源文件 |

### `/home/cxdz/jupyter/user/` 内容

**Python 程序**（2026-09-12 快照，设备内容可能随后变化）：智慧阅读角.py、人脸表情识别器.py、人数实时统计.py、人体姿态识别器（mediapipe）.py、手势识别控制RGB灯带.py、姿态检测（自带算法）.py、文字识别播报器.py、文字识别视频播放器.py、文字识别播视频qoder.py、探测_盲点_A_回调系统.py、探测_盲点_B_表情投入度.py、探测_颜色识别.py、tcyj.py

**子目录**：
- `ai/` — AI 视觉示例（AprilTag、巡线、色块、人脸识别、车牌、OCR 等）+ best.rknn
- `multimedia/` — 音频录制播放示例
- `VoiceAssistant/` — 语音助手（config.py / main.py / voice_recognizer.py / voice_synthesizer.py）
- `智能博物/` — 智能博物项目（task1_pre.py、task3_pre.py、ui_components.py）
- `iot/`、`code/` — 当前为空

**资源目录**：`images/`、`videos/`、`recordings/`、`icons/`、`face_database/`、`object_database/`、`logs/`

> 注：另有 `~/music_player.py` 放在家目录下（不在管理器扫描范围；2026-09-12 快照）。

### `/home/cxdz/jupyter/lib/` 关键驱动（cpython-38-aarch64）

| 文件 | 功能 |
| --- | --- |
| `ESP32.so` | 扩展板串口通信（核心） |
| `camera_vision_system_v3.so` | 视觉系统统一入口 |
| `yolov8.so` / `yolov8_pose.so` | 目标检测 / 姿态检测 |
| `ppocr_*.so` / `ocr_module.so` / `text_recognition.so` | 文字识别 |
| `face_recognition_module.so` / `facial_expression_recognizer.so` | 人脸识别 / 表情识别 |
| `object_recognition_module.so` / `resnet.so` / `rknn_feature_extractor.so` | 物体识别 |
| `plate_recognition_system.so` / `lprnet.so` | 车牌识别 |
| `people_counter.so` | 人流计数 |
| `audio_player.so` / `audio_recorder.so` / `whisper.so` | 音频播放/录制/语音识别 |
| `voice_api.so` | 语音 AI 接口（haohaodada.com） |
| `color_*.so` / `Line_Sensor.so` / `apriltag_detector.so` / `qr_code_detector.so` | 颜色、巡线、AprilTag、二维码 |

---

## 三、工作原理

**一句话：Linux 主板负责"大脑"，ESP32 负责"手脚"，中间靠串口对话。**（串口为**双路径**：内部 UART `/dev/ttyS9` 与 CH341 USB `/dev/ttyCH341USB0`/`/dev/ttyCH341USB1` 均存在可打开，代码一律 `board.start()` 自动探测，不硬编码。）

### 1. 硬件构成

| 部件 | 说明 |
| --- | --- |
| 主控 | Rockchip **RK3588S**（`rockchip,rk3588s-tablet-f12-v11`），8 核（4×A76 + 4×A55），带 NPU |
| 系统 | Ubuntu 20.04.6 LTS，aarch64，主机名 `haoda-pi` |
| Python | Python 3.8.10（`/usr/bin/python3`） |
| 存储 | 227G，已用 13G |
| 扩展板 | ESP32，串口 **双路径并存**：内部 UART `/dev/ttyS9` 与 CH341 USB `/dev/ttyCH341USB0`、`/dev/ttyCH341USB1` 均存在可打开；代码一律 `board.start()` 自动探测，不硬编码节点 |
| 权限 | 用户 cxdz 属于 `dialout` 组，可直接访问串口 |

### 2. 开机流程

```
通电开机 → Ubuntu 启动 → GDM 自动登录 GNOME 桌面（DISPLAY=:0）
   → autostart 读取 python-manager.desktop
   → 拉起 /home/cxdz/manager/app
   → 管理器扫描 /home/cxdz/jupyter/user/，列出程序，等待点击"运行"
```

### 3. 运行一个程序时发生了什么

1. 管理器用 `python3 xxx.py` 启动你选中的程序
   - 工作目录：`/home/cxdz/jupyter/user/`
   - 环境变量：`PYTHONPATH=/home/cxdz/jupyter/lib`
2. 因此程序里 `from ESP32 import *` 能找到厂商驱动库
3. `board = ESP32(); board.start()` 自动探测并打开串口（内部 UART `/dev/ttyS9` 或 CH341 USB `/dev/ttyCH341USB0`/`USB1` 双路径，不硬编码），向 ESP32 固件发指令（读传感器、控电机/灯等）
4. AI 视觉/语音由主板上的 **NPU + rknn 模型** 完成推理
5. 结果通过 **Pygame** 绘制到屏幕

### 4. 三层角色

```
你的 Python 程序   =  指挥官
厂商 .so 驱动库    =  翻译官（把 Python 调用翻译成串口协议 / NPU 推理）
ESP32 固件         =  执行者（真正驱动传感器和执行器）
```

### 5. 其他常驻服务

- **Jupyter Notebook**：`jupyter-notebook --no-browser --allow-root --port=8888`（开机自启，可通过浏览器访问 192.168.0.109:8888 写程序）

---

## 四、使用要点

1. **写程序放哪**：丢到 `/home/cxdz/jupyter/user/` 下（`.py` 文件），在管理器里按 F7 刷新即可看到。
2. **连接**：SSH `ssh cxdz@192.168.0.109`；Jupyter `http://192.168.0.109:8888`。
3. **硬件操作固定写法**：
   ```python
   from ESP32 import *
   board = ESP32()
   if not board.start():
       raise Exception("扩展板连接异常，请检查硬件")
   ```
4. **引脚命名**：GPIO `GPIO_IO_01`~`GPIO_IO_08`（8 路）；ADC `ADC_IO_01`~`ADC_IO_08`（8 路）；电机 `MA`、`MB`。
5. **资源路径**：图片 `images/`、音频 `recordings/`、视频 `videos/`、物体库 `object_database/`。
6. **日志**：程序日志输出到 `user/logs/`。
