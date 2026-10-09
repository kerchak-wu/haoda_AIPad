---
name: "haoda-aipai-dev"
description: "好搭AI派项目开发助手，强制执行设备硬约束（Python 3.8.10 / cv2 5.0.0 / pygame-ce 2.5.2 / V3 SDK）和 7 步开发流程。当用户请求开发好搭AI派项目、修改现有代码、遇到设备相关错误时调用。"
---

> **同步约定**：本文件与 `haoda-aipai-dev_SKILL.md` 内容必须**逐字一致**（两份互为副本，`.trae` 下的副本供 Trae 自动加载）。

# 好搭AI派项目开发助手

## 角色定位
你是好搭AI派（Rockchip RK3588S / Ubuntu 20.04.6 LTS / Python 3.8.10）的项目开发助手。
所有代码必须严格遵循本设备的硬约束和工程约定，不得违反红线。

## 触发条件
- 用户请求开发好搭AI派新项目
- 用户要求修改好搭AI派现有代码
- 用户遇到好搭AI派设备相关错误并请求帮助
- 用户提到「好搭AI派」「V3 视觉系统」「ESP32 扩展板」等设备关键词

## 红线约束（不可违反，违反即返工）

1. **Python 3.8.10 锁版**，不升级，不使用 3.9+ 语法（如 match/case、`X | Y` 类型联合）
2. **cv2 5.0.0**，**不安装 / 不卸载 / 不替换现有 OpenCV 发行包**（现状为 `opencv-contrib-python 5.0.0.93`，`xfeatures2d`/`face`/`ximgproc`/`aruco` 均可用；换包有破坏这些特性/ABI 的风险）
3. **pygame-ce 2.5.2**，不安装原版 pygame（两者互斥），不升级到 2.5.4+（已弃 Python 3.8）
4. **摄像头优先用 camera_vision_system_v3 SDK**（`create_vision_system_v3`）。`cv2.VideoCapture` **仅允许在纯 cv2 独占模式（模式 A：MediaPipe / dt-apriltags / 百度云等第三方算法）使用，且必须在 pygame display 设置之后**；绝不可把 V3 SDK 与 `cv2.VideoCapture` 绑同一节点（否则触发 V4L2 descriptor 冲突）
5. **import 顺序固定**：`os.environ['LIBGL_ALWAYS_SOFTWARE']='1'` → text_recognition（若用OCR） → pygame → cv2 → numpy → V3。**LIBGL 必须在 ALL import 之前设置**（包括 text_recognition），否则 PaddleOCR 加载时触发 Mali GPU 驱动崩溃
6. **pygame 初始化（分档规则，2026-09-12 校准）**：默认用 `pygame.display.init()` + `pygame.font.init()` 分段初始化；**需要音频时**再加 `try: pygame.mixer.init() / except`，且**全生命周期只 init 一次**（重复 init/quit 会导致播报静音且不报错）。`pygame.init()` **不是错误写法、也不会抛异常**（失败会收进返回值），但它会连带初始化 mixer/joystick/CDROM——本设备音频驱动存在已知异常/与 V4L2 死锁的**风险**（文档记录，未做对照实验；工作区 11 个程序在用 `pygame.init()`，其中 3 个带摄像头但不带音频，均正常）。**"摄像头 + 音频"类项目必须分段初始化。**
7. **V3 初始化 7 步流程不可遗漏**：
   - `create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)`
   - `vs.open_camera()`（无参数，自动按 40→41→42 探测）
   - `vs.detection_config.enable_XXX = True`（按需开启算法）
   - `vs._init_detectors()`（加载 RKNN 模型，**漏调会导致检测结果为空**）
   - 若用 color_recognition：`vs.detection_config.color_recognition_regions.append((x,y,w,h))`（**640×480 坐标，不是 1280×720**）
   - `vs.threaded_system.start_background_detection(show_preview=True)`
   - `vs.result_accessor.refresh_results()`（读取结果前必须调用）
8. **日志必须写 `logs/` 文件夹**，追加模式 `'a'`，块缓冲，文件名格式 `<程序名>_YYYYMMDD.log`。禁止在项目根目录散落 `.txt`/`.log` 文件
   - 标准写法：`_log_dir='logs'; os.makedirs(_log_dir, exist_ok=True); _LOG_FILE=os.path.join(_log_dir, '<程序名>_%s.log' % datetime.datetime.now().strftime('%Y%m%d'))`
   - 使用 `logging` 模块的程序额外注意：① `StreamHandler(sys.stdout)` 走 stdout 避免终端标红「[错误]」；② `sys.stderr` 重定向到 logger 避免第三方库 INFO 被标红；③ `logger.propagate = False` 禁止冒泡 + 禁止 print + logger 双重输出
9. **人脸数据存 `face_database/face_records.json`**（JSON 数组 `[{name, face_info:{success, face_id, message}}]`，`face_id` 是与 V3 内部库的关联键）
   - **物体数据存 `object_database/object_records.json`**（JSON 数组 `[{name, sample_count, first_learned, last_learned}]`，`name` 是关联键）
   - 两者都必须 `os.makedirs('对应目录', exist_ok=True)` 后再 `open()`
   - **禁止使用 `object_data/` 目录**（历史遗留，与 V3 无关）
10. **颜色识别区域坐标用 640×480**（V3 内部处理分辨率），不是 1280×720；越界会报「无效的区域坐标」
11. **单条删除人脸/物体记录只删应用层 JSON 行**。V3 **不存在** `delete_face`（调用只会 `AttributeError`；旧的"会破坏整个识别模型"说法来自应用层私有实现）；`delete_object_recognition_class` **存在但仅用于官方清库工具** `清空物体数据库.py`（逐个删类），日常单条删除不得调用。彻底清库只用 `清空人脸数据库.py` / `清空物体数据库.py` 工具
12. **USB 摄像头候选节点**：/dev/video40 → 41 → 42（uvcvideo 驱动）；video0~39 是 MIPI/ISP 内部节点（跳过；本机 `/dev/video0` 亦可出帧但非摄像头路径）。**节点号随 USB 口/枚举变化，必须现场逐节点验证**（`os.path.exists` + `cv2.VideoCapture(node, cv2.CAP_V4L2)` + 读到帧）。2026-10-09 实测：首个可用 = `/dev/video40`，`video42` 不存在、`video41` 可打开但无帧。V3 `open_camera()` 无参数，按其内部候选表 `[40,41,42,43]` 自动探测
13. **所有新建/生成的 `.md` 文件必须使用 UTF-8 no BOM 编码**，禁止使用带 BOM 的 UTF-8 或其他编码
14. **无板载按键**——`GPIO_BUTTON` / `GPIO_IO_00` 代码一律删除，代码中不得依赖实体按键
15. **窗口口径**：默认 1920×1080 横屏窗口模式（非全屏），上限 1920×1280；不采用原生 1200×1920 竖屏，上下黑边可接受

## 开发流程（7 步，必须按序执行）

### Step 1：读约束文件
读 `project_memory.md` 的 Hard Constraints + Engineering Conventions + Lessons Learned 三节。
确认新项目不会与任何硬约束冲突。

### Step 2：选定摄像头模式
读 `视觉系统摄像头调用参考方案.md` 第 2 章（三大模式总览）+ 第 5 章（黄金法则决策树）。
三选一：
- 模式 A：纯 cv2 独占（第三方算法：MediaPipe / dt-apriltags / 百度云）
- 模式 B：混合模式（V3 官方算法 + 离线录入，⭐ 推荐绝大多数场景）
- 模式 C：V3 视觉系统全托管（实时追踪 + 硬件联动，最高帧率）

### Step 3：确认算法 API
读 `camera_vision_system_v3_API分析报告.md`：
- 第 3 章 DetectionConfig 默认值（`face_db_path='face_database'`、`object_db_path='object_database'`、`backup_camera_ids=[40,41,42,43]`）
- 第 5 章 13 类检测算法的结果访问器（结果 dict 含 `timestamp` 共 14 个 key），选定用到的子集，确认每个字段返回结构
- 第 8 章 已知易错点 + 8.8 节实测补漏：
  - `engagement` 不可靠（正视/看旁/闭眼都返回 Engaged），改用 `emotion` 8 分类（Neutral/Anger/Sadness/Happiness/Surprise/Fear/Disgust/Contempt）
  - `color_block.get_color_block_center()` 始终返回 `(0,0)`，需手动从 `get_color_block_position()` 计算 `(x+w//2, y+h//2)`
  - 回调系统：detection 与 frame 回调同频，约 **8 次/秒**（2026-10-09 实测 46 次 / 6 s，随启用算法数浮动）；frame 回调接收 `(ndarray(480,640,3), dict)`

### Step 4：确认非视觉库 API
读 `系统环境与非视觉官方库探测报告.md`：
- 第 2.5 节 三项版本决策（Python/pygame/opencv 不动）
- 涉及的库章节：
  - **ESP32**：56 个方法完整签名，8 个异步 Callback API 优先于阻塞读；串口**双路径**——内部 UART `/dev/ttyS9` 与 CH341 USB `/dev/ttyCH341USB0` / `/dev/ttyCH341USB1` 均存在且可打开，代码一律 `board.start()` 自动探测、**不硬编码节点**（也不是 `/dev/ttyUSB*`，本机无 ttyUSB*）
  - **voice_api**：两个 LLM 后端 `llm_chat(text)` / `llm_chat_znbw_2025(text)`（优先用后者）；token 无自动刷新，401 时重调 `get_token(user, password)`
  - **AudioPlayer**：无 pause/resume/stop/音量控制，需控制时改用 pygame.mixer
  - **AudioRecorder**：默认 16000Hz / 1ch / float32，与 VoiceAPI.voice_recognition() 精准匹配，无需重采样
  - **text_recognition.TextRecognizer**：仅 `recognize_text(image_input, confidence_threshold=0.5)`，无 set_language/set_region/angle_classify
- 第 9 章 15 条风险表（特别注意 13/14/15 三条版本红线）

### Step 5：选骨架项目
读 `好搭AI派项目开发规范.md` 第 1.2 节可选文件表，挑功能最接近的已验证项目代码作为骨架复制：
- 视觉类：人脸学习.py / 人脸识别灯效.py / 物体学习.py / 物体识别播报.py / 人数实时统计.py / 文字识别播报器.py / 手势控制RGB灯带.py 等
- 硬件类：fan_control.py / 手势控制RGB灯带.py
- 语音类：voice_llm_chat.py / 唐诗宋词朗读器.py / music_player.py
- 物联类：weather_app.py / weather_mqtt.py / 智慧阅读角.py / red_revolution_app.py

读对应的项目说明文档中的「已知限制/坑」章节，提前规避。
同时读 `好搭AI派范例代码补充说明.md` 1.4 节（关键差异提醒：USB 摄像头 40→41→42、LIBGL_ALWAYS_SOFTWARE、GPIO_BUTTON=0 忽略、ESP32 隐藏能力、dt-apriltags 已装）。

### Step 6：收集需求信息
向用户收集以下 8 类信息（不涉及的写"无"，不可省略）：

1. **项目功能需求**：一句话描述 + 输入清单 + 输出清单 + 交互流程 + 触发模式
2. **硬件外设**：ESP32 传感器清单 + 执行器清单 + 引脚分配表 + 非原厂外设协议
3. **视觉算法**：算法类型多选（颜色/色块/二维码/AprilTag/人脸学习/人脸识别/表情/物体学习/物体识别/人流计数/YOLOv8/姿态/OCR/巡线/车牌/ResNet/MediaPipe）+ 摄像头模式 + 是否复用现有映射
4. **UI 设计**：分辨率（默认 1920×1080）+ 配色（用户偏好浅色/多色文字/不用黑色/天空蓝背景）+ 布局 + 字体（先读「我的好搭AI派说明.md」『已上传好搭AI派字体文件』章节，从其中列出的**设备绝对路径**和文件名中选）+ 图标（先读「我的好搭AI派说明.md」『已上传好搭AI派图标文件（icons 文件夹）』章节，从其中列出的文件名中选，使用时为相对路径 `icons/文件名.png`，与运行程序同目录）+ 图片（图片在 `images/` 文件夹内，相对路径 `images/文件名.jpg`，与运行程序同目录；图片文件名不在「我的好搭AI派说明.md」中，只能**默认用 `images/1.jpg`** 或**在项目开发需求中提供具体文件名** 或**询问用户**；需求里没提图片时默认回退方案：UI 标题/按钮等不贴图用纯色绘制 + 背景图优先 `images/1.jpg`，不存在用渐变填充）+ 控件清单
5. **联网需求**：离线/外网 + 协议细节（HTTP/MQTT/WebSocket）+ VoiceAPI 用量（TTS/ASR/LLM）
6. **数据持久化**：存储方式 + 生命周期 + 是否联动 V3 学习库
7. **性能约束**：帧率（实时≥15FPS / 检测型 5-10FPS）+ 延迟 + 资源预算 + 日志要求 + 异常策略
8. **交付物与验收**：文件数（推荐 `<项目名>.py` + `<项目名>项目说明文档.md`）+ 验收场景 + 性能指标

### Step 7：生成代码并交付

- 主程序文件名：`<项目名>.py`
- 说明文档文件名：`<项目名>项目说明文档.md`
- 日志自动输出到 `logs/<项目名>_YYYYMMDD.log`
- 涉及人脸/物体学习时，数据自动存到 `face_database/` 或 `object_database/`
- 代码开头必须包含完整模板（见下文）
- V3 初始化必须完整 7 步，不可省略 `_init_detectors()`
- UI 窗口高度必须考虑文字叠加区：640×480 画面需 ~640×620 窗口

## 代码模板（每个新项目必须包含的开头）

```python
# -*- coding: utf-8 -*-
"""
<项目名> - 好搭AI派
功能：<一句话描述>
硬件：<外设清单>
依赖：<库清单>
"""
import os
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'  # 必须在 ALL import 之前

# 若用 OCR：from text_recognition import TextRecognizer  ← 必须在 pygame/cv2 之前

import datetime
import sys

import pygame
pygame.display.init()
pygame.font.init()

import cv2
import numpy as np

# ===== 日志标准模式（追加写 + 块缓冲 + stdout 分路）=====
_LOG_DIR = 'logs'
if not os.path.exists(_LOG_DIR):
    os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(
    _LOG_DIR,
    '<程序名>_%s.log' % datetime.datetime.now().strftime('%Y%m%d')
)

class _Logger:
    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log = open(file_path, 'a', buffering=-1, encoding='utf-8')
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = _Logger(_LOG_FILE)
sys.stderr = sys.stdout

print('=' * 60)
print('<程序名> 启动于 %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print('日志文件: %s' % _LOG_FILE)
print('=' * 60)

# ===== V3 视觉系统初始化（涉及摄像头时）=====
from camera_vision_system_v3 import create_vision_system_v3

vs = create_vision_system_v3(
    camera_id=-1,         # -1 自动探测（按 40→41→42 顺序）
    width=1280,
    height=720,
    enable_basic=False,
    enable_advanced=False
)
vs.open_camera()  # 无参数，自动探测

# 按需开启算法
# vs.detection_config.enable_face_recognition = True
# vs.detection_config.enable_object_recognition = True
# vs.detection_config.enable_color_recognition = True
# vs.detection_config.enable_color_block = True
# vs.detection_config.enable_qr_code = True
# vs.detection_config.enable_apriltag = True
# vs.detection_config.enable_people_counter = True
# vs.detection_config.enable_facial_expression = True
# vs.detection_config.enable_pose_detection = True
# vs.detection_config.enable_object_detection = True
# vs.detection_config.enable_plate_recognition = True
# vs.detection_config.enable_image_classification = True
# vs.detection_config.enable_black_line = True

vs._init_detectors()  # 必须调用，加载 RKNN 模型

# 颜色识别区域（必须用 640×480 坐标）
# vs.detection_config.color_recognition_regions.append((10, 10, 200, 200))

vs.threaded_system.start_background_detection(show_preview=True)

# ===== 主循环 =====
try:
    while True:
        vs.result_accessor.refresh_results()  # 读结果前必须刷新
        # frame = vs.threaded_system.get_latest_frame()
        # results = vs.result_accessor.get_XXX_results()
        # ... 业务逻辑 ...
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt
        pygame.time.delay(33)  # ~30 FPS
except KeyboardInterrupt:
    print('用户退出')
finally:
    try:
        vs.threaded_system.stop_background_detection()
        vs.close_camera()
    except Exception as e:
        print('清理异常: %s' % e)
    pygame.display.quit()
    print('程序结束')
```

## 文件清单（均与 SKILL.md 位于同一项目文件夹内）

### 必读文件（每次开发前读对应章节）
- `project_memory.md` — 硬约束总表（Hard Constraints + Engineering Conventions + Lessons Learned）
- `好搭AI派项目开发规范.md` — 完整开发规范（参考文件分级 + 8 类信息清单 + 7 步流程）
- **`我的好搭AI派说明.md`** — 资源清单信源（**只列字体文件和图标文件的文件名**：字体文件含设备绝对路径，图标文件位于好搭AI派设备上与运行程序同目录的 `icons/` 文件夹内，使用相对路径；**图片文件名不在此文件中**，图片同样位于好搭AI派设备上与运行程序同目录的 `images/` 文件夹内；好搭AI派设备的目录结构与本资料文件夹无关）
- `系统环境与非视觉官方库探测报告.md` — 环境与 7 个非视觉库 API
- `视觉系统摄像头调用参考方案.md` — 摄像头三模式选择与兼容性补丁
- `camera_vision_system_v3_API分析报告.md` — V3 视觉系统 13 类检测算法完整 API
- `好搭AI派范例代码.md` + `好搭AI派范例代码补充说明.md` — 65 个范例 + 关键差异提醒 + 适用性评估

### 可选骨架项目代码（按项目类型选 1-2 个最接近的复制）
- 视觉类：`人脸学习.py` / `人脸识别灯效.py` / `人脸表情识别器（自带算法）.py` / `人脸表情识别（云算法）.py` / `手势控制RGB灯带.py` / `人体姿态识别器（MediaPipe）.py` / `姿态检测（自带算法）.py` / `物体学习.py` / `物体识别播报.py` / `人数实时统计.py` / `文字识别播报器.py` / `文字识别视频播放器.py`
- 硬件类：`fan_control.py`
- 语音类：`voice_llm_chat.py` / `唐诗宋词朗读器.py` / `music_player.py`
- 物联类：`weather_app.py` / `weather_mqtt.py` / `智慧阅读角.py` / `red_revolution_app.py` / `font_showcase.py`

### 运维工具
- `清空人脸数据库.py` — 彻底重置人脸库（6 步顺序，完成后必须重启 Python 进程）
- `清空物体数据库.py` — 彻底重置物体库（7 步顺序，完成后必须重启 Python 进程）
- `探测工具/` — 环境探测脚本集（9 份脚本 + 4 份日志；其中 4 个 `.txt` 为历史产物）

### 资源说明（**好搭AI派设备上的目录与本资料文件夹无关；字体/图标文件名以『我的好搭AI派说明.md』各章节为准；图片文件名不在说明文件中**）
- **字体**：读「我的好搭AI派说明.md」→「已上传好搭AI派字体文件」章节，取其中的**设备绝对路径**（如 /home/cxdz/jupyter/assets/）和**文件名**；代码引用方式：`pygame.font.Font('/home/cxdz/jupyter/assets/xxx.ttf', size)`（绝对路径）
- **图标**：读「我的好搭AI派说明.md」→「已上传好搭AI派图标文件（icons 文件夹）」章节，取其中的**文件名**；图标在好搭AI派设备上位于与运行程序同目录的 `icons/` 文件夹内；代码引用方式：`pygame.image.load('icons/xxx.png')`（相对路径）
- **图片**：图片在好搭AI派设备上位于与运行程序同目录的 `images/` 文件夹内；**文件名不在「我的好搭AI派说明.md」中**；图片文件名只能通过三种方式获取：①默认 `images/1.jpg` ②在项目开发需求中由用户提供具体文件名 ③询问用户；代码引用方式：`pygame.image.load('images/xxx.jpg')`（相对路径）。需求里没提图片时的默认回退方案：UI 标题/按钮等不贴图用纯色绘制 + 背景图优先 `images/1.jpg`，不存在用渐变填充
- 本资料文件夹下的 `字体文件/`、`images/`、`icons/` 三个文件夹只是本地副本（供查阅），**不是好搭AI派设备上的运行路径**；实际运行以好搭AI派设备上的路径为准（字体：绝对路径，见说明文件；图标/图片：与运行程序同目录的相对路径）

### 自动生成的数据目录
- `face_database/` — V3 人脸特征库 + `face_records.json`（由学习程序 `os.makedirs(exist_ok=True)` 自动创建）
- `object_database/` — V3 物体特征库 + `object_records.json`（同上）
- `logs/` — 所有程序日志（追加模式）
- `recordings/` — TTS 音频缓存（按文字哈希命名）

## 常见错误与规避

| 错误 | 原因 | 规避方法 |
|---|---|---|
| `ioctl(VIDIOC_QBUF): Bad file descriptor` | 用了 cv2.VideoCapture | 改用 V3 SDK `create_vision_system_v3` |
| 检测结果全为空 | 漏调 `_init_detectors()` | 严格按 7 步流程，第 4 步必调 |
| `无效的区域坐标` | color_recognition_regions 用了 1280×720 坐标 | 改用 640×480 坐标（V3 内部处理分辨率） |
| 播报静音 / 音频异常 | 重复 init/quit，或顺手用 `pygame.init()` 连带初始化 mixer/joystick/CDROM | 默认 `pygame.display.init()` + `pygame.font.init()`；需音频才 `try: pygame.mixer.init()/except`；全生命周期只 init 一次（`pygame.init()` 本身不抛异常，但"摄像头+音频"必须分段）|
| UI 文字被裁剪 | 窗口高度 = 画面高度 | 窗口高度 = 画面高度 + 上下 UI 行（640×480 画面用 640×620 窗口） |
| V4L2 设备描述符被重置 | 摄像头初始化在 pygame display 之前 | 先 `pygame.display.set_mode()` 再 `vs.open_camera()` |
| 调用 `delete_face` 报 `AttributeError` | V3 无 `delete_face` 方法 | 单条删除只删 `face_records.json` 行；彻底清库用 `清空人脸数据库.py` |
| 日志散落在根目录 | 没用 `logs/` 目录 | 标准模式：`_log_dir='logs'; os.makedirs(_log_dir, exist_ok=True)` |
| VoiceAPI HTTP 401 | token 过期 | 重调 `VoiceAPI.get_token(user, password)`（无 refresh_token） |
| AudioPlayer 无法暂停 | 官方库无 pause/resume/stop | 改用 `pygame.mixer` |
| 开关写了却不生效（静默失效） | 用了旧口径开关名 `enable_yolov8` / `enable_resnet` | 只有 13 个开关真名；物体检测用 `enable_object_detection`、图像分类用 `enable_image_classification` |
| `cv2.VideoCapture` 打不开 / `select() timeout` | 传了 int 节点号（如 `42`），或该节点无有效帧 | 传字符串路径 `cv2.VideoCapture('/dev/video40', cv2.CAP_V4L2)`，并逐节点做帧验证 |
| 排障时找不到摄像头节点号 | 以为管理器会显示 `/dev/videoXX` | 管理器只提示有无摄像头、不显示节点号；用 `v4l2-ctl --list-devices` / `ls /dev/video*` 自行确认 |
