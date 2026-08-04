# 人体姿态识别器项目说明文档

## 一、项目概述

本项目运行于好搭AI派（ESP32 + rockchip 平台），通过 USB 外接摄像头实时采集人体画面，基于 Google MediaPipe Pose 模型识别 33 个人体关键点，映射为 COCO 17 关键点格式，在 1920×1080 屏幕上展示实时画面与多色骨架叠加效果。

### 核心功能

1. 基于 Google MediaPipe Pose 识别 USB 摄像头画面中的人体姿态
2. 界面 1920×1080，浅蓝科技感主题
3. 实时显示摄像头画面（采集线程 + 识别线程分离，避免画面延迟）
4. 在画面上叠加 33 个关键点与骨架连线（MediaPipe Pose 格式）
5. 右侧面板展示姿态信息（检测状态、置信度、关键点数、简单姿态判断）
6. 退出按钮 + ESC 快捷键

---

## 二、硬件依赖

| 硬件 | 说明 |
| ------ | ------ |
| 好搭AI派 | ESP32 + rockchip RK 平台 |
| USB 外接摄像头 | 接好搭AI派 USB 接口，分辨率 640×480，30fps |
| 显示屏 | 1920×1080 |

### 摄像头连接说明

- 摄像头插入好搭AI派的 USB 接口
- 右下角开关需拨到左侧（USB 摄像头模式）
- 程序探测 `/dev/video41` 和 `/dev/video40` 两个设备节点

---

## 三、软件依赖

### 第三方库

```md
opencv-python      # OpenCV 图像处理
pygame             # 界面显示
numpy              # 数值计算
mediapipe          # Google MediaPipe 人体姿态识别
```

### mediapipe 安装

mediapipe 非系统内置，需手动安装。可通过以下命令验证是否已安装：

```bash
python3 -c "import mediapipe; print(mediapipe.__version__)"
```

如未安装，执行：

```bash
pip3 install mediapipe
```

> 本项目复用 [手势控制RGB灯带.py](file:///d:/笔记本同步/好搭AI派资料/手势控制RGB灯带.py) 的 mediapipe 环境，无需重复安装。

---

## 四、文件结构

```md
好搭AI派资料/
├── 人体姿态识别器.py              # 主程序
├── 人体姿态识别器项目说明文档.md  # 本说明文档
├── images/
│   └── 1.jpg                     # 背景图片（可选，缺失时自动生成渐变背景）
└── 其他范例程序与学习手册
```

### 资源文件说明

- `images/1.jpg`：背景图片，程序启动时加载。如缺失或加载失败，会自动生成浅蓝渐变背景，不影响运行。

---

## 五、技术架构

### 5.1 整体架构

程序采用**三线程模型**，避免画面延迟与卡顿：

```md
┌─────────────────────────────────────────────────┐
│                  主线程（Pygame）                 │
│  - 事件处理（鼠标、键盘）                         │
│  - 界面绘制（背景、面板、摄像头画面、骨架、结果）   │
│  - 20 FPS 刷新                                   │
└─────────────────────────────────────────────────┘
          ▲ 读取 latest_frame         ▲ 读取姿态结果
          │                           │
┌─────────┴───────────┐  ┌────────────┴──────────────┐
│  采集线程（后台）     │  │  识别线程（后台）           │
│  - cap.read()        │  │  - pose.process(rgb)      │
│  - 写入 raw_frame    │  │  - 提取 COCO 17 关键点     │
│  - 丢弃积压帧        │  │  - 绘制关键点到帧          │
│  - 保证画面实时      │  │  - 写入 latest_frame       │
└──────────────────────┘  └───────────────────────────┘
```

### 5.2 双线程分离设计

参考 [手势控制RGB灯带.py](file:///d:/笔记本同步/好搭AI派资料/手势控制RGB灯带.py) 的线程结构：

- **采集线程**：只快速 `cap.read()`，总是覆盖旧帧，丢弃积压帧，避免 V4L2 内核缓冲区积压旧帧导致画面延迟。
- **识别线程**：取最新帧做 `pose.process()` 处理，处理不过来就跳过中间帧（自动降帧），不阻塞采集线程。

```python
threading.Thread(target=self.camera_capture_loop, daemon=True).start()
threading.Thread(target=self.pose_recognition_loop, daemon=True).start()
```

### 5.3 MediaPipe Pose 识别流程

```md
摄像头帧 (BGR)
    │
    ├── cv2.cvtColor(BGR → RGB)
    │
    ├── pose.process(rgb)
    │       返回 results.pose_landmarks（33 个关键点）
    │
    ├── extract_coco17(landmarks)
    │       从 33 点提取 COCO 17 点（鼻/眼/耳/肩/肘/腕/髋/膝/踝）
    │       坐标格式：归一化 (x, y, visibility)，x/y ∈ [0,1]
    │
    ├── mp_drawing.draw_landmarks(...)
    │       在 RGB 帧上绘制默认样式的关键点与骨架
    │
    └── 写入 latest_frame + latest_pose_keypoints
```

### 5.4 关键点坐标转换

MediaPipe 返回归一化坐标 `(0~1)`，绘制时需转换为屏幕像素坐标：

```python
# 归一化坐标 → 屏幕坐标
sx = ox + int(kx * sw)    # ox=画面偏移x, sw=画面显示宽度
sy = oy + int(ky * sh)    # oy=画面偏移y, sh=画面显示高度
```

### 5.5 多色骨架叠加

程序在 pygame 层叠加多色骨架，覆盖 mediapipe 默认的白色绘制：

| 部位 | 关键点索引 | 颜色 |
| ------ | ---------- | ------ |
| 头部 | 0-4（鼻/眼/耳） | 青色 `(0, 170, 210)` |
| 肩 | 5-6 | 绿色 `(0, 170, 90)` |
| 肘 | 7-8 | 橙色 `(255, 140, 50)` |
| 腕 | 9-10 | 橙色 `(255, 140, 50)` |
| 髋 | 11-12 | 绿色 `(0, 170, 90)` |
| 膝 | 13-14 | 紫色 `(140, 80, 220)` |
| 踝 | 15-16 | 紫色 `(140, 80, 220)` |

### 5.6 姿态判断逻辑

基于 COCO 17 关键点的简单几何判断：

| 姿态 | 判断条件 | 颜色 |
| ------ | -------- | ------ |
| 双手举起 | 左腕 + 右腕均高于肩膀（y 值更小 0.05） | 橙色 |
| 左手举起 | 仅左腕高于左肩 | 黄色 |
| 右手举起 | 仅右腕高于右肩 | 黄色 |
| 站立 | 髋到踝的 y 差值 > 0.25 | 绿色 |
| 坐着/蹲下 | 髋到踝的 y 差值 < 0.12 | 紫色 |
| 已检测到人体 | 以上条件均不满足 | 青色 |

---

## 六、关键配置参数

| 参数 | 值 | 说明 |
| ------ | ----- | ------ |
| `WIDTH, HEIGHT` | 1920, 1080 | 界面分辨率 |
| `CAMERA_W, CAMERA_H` | 640, 480 | 摄像头分辨率 |
| `MODEL_COMPLEXITY` | 1 | MediaPipe 模型复杂度（0=Lite快/1=Full平衡/2=Heavy准） |
| `MIN_DETECTION_CONFIDENCE` | 0.5 | 最小检测置信度 |
| `MIN_TRACKING_CONFIDENCE` | 0.5 | 最小跟踪置信度 |
| 主循环帧率 | 20 FPS | Pygame 界面刷新率 |
| 关键点可见度阈值 | 0.3 | 低于此值的关键点不绘制 |

### 性能调节

- **运行卡顿**：将 `MODEL_COMPLEXITY` 改为 `0`（Lite 模式，速度更快但精度降低）
- **精度不足**：将 `MODEL_COMPLEXITY` 改为 `2`（Heavy 模式，精度更高但速度慢）

---

## 七、运行方式

### 7.1 在好搭AI派上运行

1. 将 `人体姿态识别器.py` 上传到好搭AI派
2. 确保 `images/1.jpg` 存在（可选）
3. 确保 USB 摄像头已连接，右下角开关拨到左侧
4. 运行程序：

```bash
python3 人体姿态识别器.py
```

### 7.2 操作方式

- **退出程序**：点击右下角"退出"按钮，或按 `ESC` 键
- **姿态识别**：自动进行，实时检测，无需手动操作

---

## 八、界面说明

### 界面布局

```md
┌─────────────────────────────────────────────────────────────┐
│                    人体姿态识别系统                          │
│       HUMAN POSE ESTIMATION | MediaPipe Pose                │
├──────────────────────────────────────────────────────────────┤
│                                      │    识别结果          │
│         摄像头实时画面                 │  ● 状态指示灯        │
│         640 × 480                     │ ─────────────────── │
│                                      │  当前姿态           │
│         [多色骨架 + 关键点]            │  站立               │
│         头部=青 躯干=绿               │ ─────────────────── │
│         上肢=橙 下肢=紫               │  置信度             │
│                                      │  85.2%              │
│                                      │  ████████░░         │
│                                      │ ─────────────────── │
│                                      │  检测状态  已检测到  │
│                                      │  关键点数  17/17    │
│                                      │ ─────────────────── │
│                                      │  关键点列表         │
│                                      │  鼻子  (50%,30%)   │
│                                      │  左眼  (48%,28%)   │
│                                      │  ...                │
├──────────────────────────────────────┴──────────────────────┤
│ 状态: 姿态识别中          已检测到人体姿态        [ 退出 ]   │
└─────────────────────────────────────────────────────────────┘
```

### 界面配色（浅蓝科技感主题）

| 元素 | 颜色 |
| ------ | ------ |
| 背景 | 浅天蓝渐变 `(135,206,250) → (70,130,200)` |
| 面板 | 白色半透明 `(255,255,255,235)` |
| 边框 | 青色 `(0,150,200)` |
| 标题 | 深蓝 `(20,50,100)` |
| 状态指示灯 | 绿色=就绪 / 橙色=识别中 / 红色=错误 |

---

## 九、rockchip 平台适配要点

本项目在开发过程中解决了多个 rockchip 平台兼容性问题，以下是关键适配要点：

### 9.1 libGL 驱动加载失败

**现象**：`libGL error: failed to load driver: rockchip`

**解决**：在导入 cv2/pygame 之前设置环境变量

```python
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
```

### 9.2 import 顺序

**现象**：`FATAL: exception not rethrown`

**解决**：必须先 `import pygame`，再 `import cv2`。pygame 先导入让 SDL 接管视频子系统，cv2 不会再重复初始化 OpenGL。

### 9.3 不使用 pygame.init()

**现象**：`FATAL: exception not rethrown`

**解决**：只初始化需要的子模块，避免 `pygame.mixer` 初始化触发 rockchip 原生崩溃

```python
pygame.display.init()
pygame.font.init()
# 不调用 pygame.init()
```

### 9.4 摄像头探测

**方案**：参考 [手势控制RGB灯带.py](file:///d:/笔记本同步/好搭AI派资料/手势控制RGB灯带.py) 的摄像头探测逻辑：

- 固定探测 `/dev/video41` 和 `/dev/video40`
- 使用 `SIGALRM` 超时机制（4秒），避免探测卡死
- 雪花检测：通过 `std()` 判断帧是否有效（非全黑、非雪花噪声）
- 设置 `MJPG` 格式 + `BUFFERSIZE=1`，减少内核缓冲区积压

### 9.5 mediapipe drawing_styles 版本兼容

**现象**：`module 'mediapipe.python.solutions.drawing_styles' has no attribute 'get_default_pose_connections_style'`

**原因**：不同 mediapipe 版本的 `drawing_styles` API 命名不一致。

**解决**：不依赖 `drawing_styles` 模块，直接用 `mp_drawing.DrawingSpec` 指定样式，并加 try-except 兜底：

```python
try:
    mp_drawing.draw_landmarks(
        rgb, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
        landmark_drawing_spec=mp_drawing.DrawingSpec(
            color=(0, 170, 210), thickness=2, circle_radius=3),
        connection_drawing_spec=mp_drawing.DrawingSpec(
            color=(0, 150, 200), thickness=2))
except Exception:
    mp_drawing.draw_landmarks(
        rgb, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
```

### 9.6 性能优化

- **预创建 Surface**：17 个关键点光晕、扫描线 glow、状态灯 glow 全部在 `__init__` 中预创建，避免每帧创建 SRCALPHA Surface（这是主要 CPU 瓶颈）
- **numpy 向量化背景**：`make_gradient_bg` 用 numpy 生成渐变，比逐行绘制快 100 倍
- **20 FPS 帧率**：姿态检测不需要高帧率，降低 CPU 占用
- **双线程分离**：采集与识别分离，避免识别耗时导致画面延迟
- **低可见度过滤**：关键点 `visibility < 0.3` 不绘制，减少绘制开销

---

## 十、MediaPipe 33 → COCO 17 关键点映射

MediaPipe Pose 返回 33 个关键点，本项目映射为 COCO 17 标准格式便于显示与判断：

| COCO 索引 | 名称 | MediaPipe 索引 |
| --------- | ---- | -------------- |
| 0 | 鼻子 | 0 |
| 1 | 左眼 | 2 |
| 2 | 右眼 | 5 |
| 3 | 左耳 | 7 |
| 4 | 右耳 | 8 |
| 5 | 左肩 | 11 |
| 6 | 右肩 | 12 |
| 7 | 左肘 | 13 |
| 8 | 右肘 | 14 |
| 9 | 左腕 | 15 |
| 10 | 右腕 | 16 |
| 11 | 左髋 | 23 |
| 12 | 右髋 | 24 |
| 13 | 左膝 | 25 |
| 14 | 右膝 | 26 |
| 15 | 左踝 | 27 |
| 16 | 右踝 | 28 |

映射函数：

```python
def extract_coco17(landmarks):
    kps = []
    for mp_idx in [0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16,
                   23, 24, 25, 26, 27, 28]:
        lm = landmarks[mp_idx]
        vis = float(lm.visibility) if hasattr(lm, 'visibility') else 1.0
        kps.append((float(lm.x), float(lm.y), vis))
    return kps
```

---

## 十一、参考资源

| 资源 | 用途 |
| ------ | ------ |
| [好搭AI派学习手册.md](file:///d:/笔记本同步/好搭AI派资料/好搭AI派学习手册.md) | 硬件接口规范 |
| [好搭AI派范例代码.md](file:///d:/笔记本同步/好搭AI派资料/好搭AI派范例代码.md) | 摄像头、Pygame 范例 |
| [手势控制RGB灯带.py](file:///d:/笔记本同步/好搭AI派资料/手势控制RGB灯带.py) | cv2 + mediapipe + 双线程参考 |
| [人脸表情识别器.py](file:///d:/笔记本同步/好搭AI派资料/人脸表情识别器.py) | rockchip 适配、性能优化参考 |
| [MediaPipe Pose 文档](https://google.github.io/mediapipe/solutions/pose.html) | API 参数说明 |

---

## 十二、常见问题

### Q1：程序启动后提示"摄像头打开失败"

**A**：检查以下几点：

1. USB 摄像头是否插入好搭AI派的 USB 接口
2. 右下角开关是否拨到左侧（USB 摄像头模式）
3. 终端执行 `ls /dev/video*` 确认设备节点是否存在
4. 确认没有其他程序占用摄像头

### Q2：程序运行后提示 `get_default_pose_connections_style` 错误

**A**：mediapipe 版本兼容问题，已在最新代码中修复。如仍出现，请确认运行的是最新版 `人体姿态识别器.py`。

### Q3：画面卡顿

**A**：按以下顺序尝试：

1. 将 `MODEL_COMPLEXITY` 从 `1` 改为 `0`（Lite 模式）
2. 确认主循环帧率为 20 FPS（不是 30）
3. 检查终端是否有异常日志（异常循环会消耗 CPU）
4. 确认预创建 Surface 优化已生效（关键点光晕不应每帧创建）

### Q4：关键点位置不对

**A**：检查坐标转换是否正确。MediaPipe 返回归一化坐标 `(0~1)`，必须乘以画面显示尺寸再加偏移：

```python
sx = ox + int(kx * sw)    # 不要用 kx * CAMERA_W，要用显示尺寸 sw
sy = oy + int(ky * sh)
```

### Q5：姿态判断不准确

**A**：当前姿态判断是基于关键点几何位置的粗略估计，仅支持举手、站立、坐着等基本姿态。如需更复杂的姿态识别（如瑜伽动作、运动分析），需扩展 `estimate_pose` 函数的判断逻辑。

### Q6：如何扩展更多姿态

**A**：在 `estimate_pose` 函数中添加新的判断条件。例如判断"叉腰"：

```python
# 叉腰：手腕接近髋部
if visible(9) and visible(11):
    dist = math.hypot(kps[9][0] - kps[11][0], kps[9][1] - kps[11][1])
    if dist < 0.1:
        return ('叉腰', ACCENT_PINK)
```

---

## 十三、开发经验总结

### 13.1 方案选型对比

本项目开发过程中对比了两种方案：

| 维度 | SDK 方案（camera_vision_system_v3） | MediaPipe 方案 |
| ------ | ------------------------------------- | --------------- |
| 算法来源 | 好搭AI派自带 SDK | Google MediaPipe |
| 关键点数量 | 17（COCO） | 33（可映射为 17） |
| 坐标格式 | 像素坐标（待核验） | 归一化坐标（确定） |
| 摄像头访问 | SDK 封装 | cv2.VideoCapture |
| 平台兼容性 | 高（SDK 已处理冲突） | 需手动处理（参考手势识别程序） |
| 灵活性 | 低（闭源） | 高（开源，可扩展） |

**最终选择 MediaPipe 方案**：坐标格式确定、可扩展性强、复用手势识别程序的成熟摄像头方案。

### 13.2 关键教训

1. **优先复用已验证的代码**：摄像头探测、双线程结构、rockchip 适配等直接复用手势识别程序，避免重复踩坑。
2. **预创建 Surface 是性能关键**：在 rockchip 平台上，每帧创建 SRCALPHA Surface 的开销极大，必须预创建复用。
3. **mediapipe 版本兼容性**：不同版本的 `drawing_styles` API 不一致，不要依赖具体函数名，用 `DrawingSpec` 直接指定样式更稳定。
4. **双线程分离避免画面延迟**：采集与识别分离，识别耗时不会阻塞画面更新。
