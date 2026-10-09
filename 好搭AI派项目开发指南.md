# 好搭AI派项目开发指南

> **版本**：v1.0（基于本资料文件夹现有文档整理）
> **生成日期**：2026-09-12
> **定位**：把 `project_memory.md` / `haoda-aipai-dev_SKILL.md` / `好搭AI派项目开发规范.md` / `视觉系统摄像头调用参考方案.md` / `camera_vision_system_v3_API分析报告.md` / `系统环境与非视觉官方库探测报告.md` / `好搭AI派范例代码补充说明.md` / `好搭AI派基本情况.md` 里散落的开发约束，收敛成一份**可直接照着写代码**的施工手册。
> **配套文件**：`好搭AI派文档矛盾与问题分析报告.md`（本文档历史"待核验口径"条目对应的问题清单与处置方案）。

---

## 0. 怎么用这份指南（权威优先级）

> 📌 **交接入口**：设备探测日志的解读规则与施工步骤见 **`探测工具/探测结果分析指南.md`**（含逐 KEY 判定表、`project_memory.md` 口径决议记录模板、完工自检脚本）。本指南是"施工口径"，那份是"如何把口径定下来"。

**权威模型（2026-10-09 按设备实测日志收口）**：以 **`系统环境与非视觉官方库探测报告.md` + `camera_vision_system_v3_API分析报告.md` 两份为基线**，其余文档一律向其对齐；`project_memory.md` 只当"默认约定集 + 索引"。

| 层级 | 信源 | 规则 |
|---|---|---|
| **A0 你的裁决 / 设备实测** | 本次四条裁决（日志 `.log`、摄像头 `40→41→42`、**无板载按键**、窗口默认 1920×1080 / 上限 1920×1280）+ **设备探测日志**（`logs/探测_待定项核对_*.log`）+ `探测工具/` 脚本日志 + 设备现跑命令输出 | **最高**，直接定案；须写入 `project_memory.md`「口径决议记录」 |
| **A1 基线报告（两份）** | `系统环境与非视觉官方库探测报告.md`、`camera_vision_system_v3_API分析报告.md` | 与其他**文档**冲突时以这两份为准；它们自身仍待修正的条目见分析报告第 9.2 节 |
| **A2 现有可运行代码** | 22 个项目 `.py`（尤其已验证交付物） | 与 A1 冲突时逐条判断：**代码是实测跑通的则代码胜**（例：`40→41→42`、`.log`、`IMWRITE_JPEG_QUALITY 85 / API_INTERVAL 1.5`），并把结论回写 A1 |
| **A3 约定与索引层** | `project_memory.md` + `haoda-aipai-dev_SKILL.md` | 默认约定 + 索引；无任何证据时用它当默认值，用前看分析报告第 10.2 节该行的状态标记（✅已实测 / ⚖️约定 / 需条件 / ❌待更正） |
| **A4 教学/从属层** | `好搭AI派项目开发规范.md`、`视觉系统摄像头调用参考方案.md`、`好搭AI派范例代码补充说明.md`、`好搭AI派学习手册.md`、`好搭AI派范例代码.md`、`好搭AI派基本情况.md` | 最低：只作教学/流程参考，技术事实一律回指 A0~A2。**范例代码是可信的 API 依据、绝大多数可直接运行**（28/65 个纯硬件·音频·语音·物联网范例可直接复制，详见 §13.1）；须先改的只有 5.04/5.05 的坐标。`好搭AI派基本情况.md` 含 2 处错误（ESP32 串口、`object_data/`） |

**四条已定案的口径（本指南全文按此执行）**
1. **日志扩展名统一 `.log`**（不再有 `.txt` 歧义）。
2. **摄像头候选顺序 `40 → 41 → 42`**（2026-10-09 按设备实测修订，原 `42 → 41 → 40` 作废。每步须 `os.path.exists` + `cv2.VideoCapture(path, cv2.CAP_V4L2)` 字符串路径 + 读到有效帧验证；实测首个可用为 `/dev/video40`，`video42` 不存在，`video41` 可打开但无帧。**节点号随插拔变化，以现场实测为准**）。
3. **无板载按键**——`GPIO_BUTTON = 0` 相关代码一律删除；`好搭AI派学习手册.md` 里"按板载按键"的示例作废。
4. **窗口：默认 1920×1080 横屏窗口模式（非全屏），最大 1920×1280**。

**本指南口径已按设备实测日志（2026-10-09）全部收口**；少数无法用程序测定、只能靠实物或人眼的项，已就地标注"需实物/需人眼"，动手前看配套分析报告对应条目。
**P0-9（算法开关名）、P0-10（字段名与返回类型）、第 10.3 节的"经验改口"是纯事实更正，无需设备核验，可直接照本指南执行。**

---

## 1. 设备与硬约束速查

### 1.1 硬件

| 项 | 值 | 来源 |
|---|---|---|
| 主控 | Rockchip **RK3588S**（device-tree `rockchip,rk3588s-tablet-f12-v11`），**不是 RK3566** | project_memory / 探测报告 / 基本情况 |
| CPU | 4×Cortex-A76 + 4×Cortex-A55 | 同上 |
| GPU | Mali-G610 MP4（Kernel DDK g18p0） | 探测报告 |
| NPU | 6 TOPS @ INT8（3 核），INT4/INT8/INT16/FP16 | project_memory |
| 内存 | 7.7 GiB（可用约 6.7 GiB），**无 Swap** | 探测报告 |
| 存储 | 227 GB，已用约 13 GB | 探测报告 |
| 系统 | Ubuntu 20.04.6 LTS，aarch64，主机名 `haoda-pi` | 基本情况 |
| 板载屏 | 8 寸 **1200×1920 竖屏**（DSI-1） | project_memory |
| 扩展板 | ESP32（ESP32-S3，RISC-V，4 MB Flash） | 探测报告 / 硬件规格日志 |
| 网络 | SSH `cxdz@192.168.0.109`；Jupyter `http://192.168.0.109:8888` | 基本情况 |

### 1.2 软件版本红线（不许动）

| 组件 | 锁定版本 | 禁止 |
|---|---|---|
| Python | **3.8.10**（`/usr/bin/python3`，设备无其他版本） | 不升级；不用 3.9+ 语法（`match/case`、`X \| Y` 类型联合）；任何新依赖必须支持 3.8 |
| cv2 (OpenCV) | **5.0.0** | 注意 4.x→5.0 API 变更：`findContours` 返回 **2 值** |
| pygame | **pygame-ce 2.5.2**（SDL 2.30.8） | 不装原版 `pygame`（互斥）；不升到 2.5.4+（弃 Py3.8） |
| numpy | 1.24.4 | 与老 pandas 不兼容 |
| mediapipe | 0.10.9 | — |
| dt-apriltags | 3.1.7（已预装，实测 33.5 FPS） | — |

> **OpenCV 发行包（已定案）**：`我的好搭AI派说明.md` 的安装命令写的是 `pip install opencv-contrib-python pygame-ce numpy`，而基线建议"不要装 opencv-contrib-python"（与 `opencv-python` 互斥）。设备实测日志 A 节确认现装为 **`opencv-contrib-python 5.0.0.93`**（`xfeatures2d/ximgproc/face` 等 contrib 专属子模块可用）。**结论：不得安装/卸载/替换任何 OpenCV 发行包**（保持现状即最安全），红线写作"**不得更换现有 OpenCV 发行包**"。如需复核，跑第 15 章核验命令 2。

### 1.3 UI 分辨率与窗口（已定案）

- **默认 1920×1080 横屏、窗口模式（非全屏）**，接受上下黑边，不要为消除黑边花力气。
- **窗口最大 1920×1280**（高度不要超过这个上限）。
- 不要把 UI 适配成板载屏原生 1200×1920 竖屏，除非用户明确要求。
- 曾被 `好搭AI派项目开发规范.md:162` 写成"全屏 1920×1080（推荐）"——**作废**，一律窗口模式；该行应改为"窗口化 1920×1080（默认），最大 1920×1280"。
- 摄像头画面区若只做 640×480 小画布：画面 480 + 顶部标题(36) + 底部指引(28) + 状态行 ≈ **窗口 640×620** 是安全下限，低于此值底部文字会被裁剪（这只是小画布场景的经验值，不改变上面 1920×1080 / 上限 1280 的默认）。

### 1.4 已实机确认的硬件事实（2026-09-12，用户确认 = A0 级）

| 项 | 确认结果 | 注意 |
|---|---|---|
| 扩展板数字 IO | **8 个**（`GPIO_IO_01~08`）；`好搭AI派项目开发规范.md:130` 写的 16 个是**错的** | 引脚分配表只能排到这 8 个 |
| ADC | **`ADC_IO_01~08` 共 8 路，8 个接口都能作 ADC**；`好搭AI派基本情况.md:141` 写的 04 是**错的** | 数字/模拟可复用同一批接口 |
| 板载按键 | **没有** | 不要设计"按键触发"交互（见红线 12） |
| 右下角开关 | **两位**：**左 = 启用外设（ESP32 扩展板）**；**右 = 充电**；无第三档 | 外设不工作时先看这个开关 |
| 充电口 | **独立 Type-C 口**，与 USB 数据口不是同一个 | 别把充电口当数据口用 |
| USB 母口 | 扩展板上有 **2 个 USB 母口**（都会占用同一批摄像头节点号） | 可插 USB 摄像头，也可插 **USB 键盘/鼠标** |
| 摄像头插法 | **插在扩展板的 USB 口上**，两个母口任选 | 这正是节点号在 40/41/42 间变化的原因 |
| 屏幕 | 启动后桌面**横向**；项目窗口**上下出现黑边属正常**；**窗口一般设 1920×1080 即可** | 与 1.3 的 D4 一致 |
| WS2812 | **一般设 10 灯**，项目里可改；**IO1~IO8 都能接** | `ws2812Init(pin, 10)` 起手 |
| 巡线模块 | **外接，I²C 4 线，4 个探头** | 配合基线报告的寄存器枚举使用 |
| 传感器/执行器接线 | **参照范例代码即可**，或按项目要求编程 | 不必逐项实测 |
| 网络 | **WiFi 有外网** | 语音AI / 天气 / 百度云 / LLM 均可用 |
| USB 下载程序 | **不可用**，用 IP 网络连接 | 学习手册 3.2「USB连接/待定」作废 |
| 电源键 | 长按确有【重启】；**自动关机阈值 10%** | — |
| 管理器摄像头提示 | 不插摄像头时**只提示"没有摄像头"，不显示节点号** | 判节点只能用 `探测工具/探测_待定项核对.py` 或 `v4l2-ctl` |

---

## 2. 目录与资源路径

### 2.1 设备上的运行目录（与本地资料文件夹无关）

| 路径 | 用途 |
|---|---|
| `/home/cxdz/jupyter/user/` | **用户程序目录**（程序管理器扫描的就是这里，工作目录） |
| `/home/cxdz/jupyter/lib/` | 厂商闭源 `.so` 驱动库（PYTHONPATH 指向这里） |
| `/home/cxdz/jupyter/model/` | `.rknn` AI 模型 |
| `/home/cxdz/jupyter/assets/` | 中文字体等资源（**字体用绝对路径引用**） |
| `user/images/`、`user/videos/`、`user/recordings/`、`user/icons/` | 资源目录（相对路径引用） |
| `user/face_database/`、`user/object_database/`、`user/logs/` | 程序自动生成 |

程序启动方式（管理器）：工作目录 `user/`，环境变量 `PYTHONPATH=/home/cxdz/jupyter/lib`。
`~/.config/autostart/python-manager.desktop` → `/home/cxdz/manager/app`（PyInstaller 打包的 PyQt5 程序管理器，DISPLAY=:0）。

### 2.2 资源引用方式（三种，别记混）

| 类型 | 位置 | 代码写法 |
|---|---|---|
| 字体 | `/home/cxdz/jupyter/assets/`（绝对路径） | `pygame.font.Font('/home/cxdz/jupyter/assets/simfang.ttf', size)` |
| 图标 | 与运行程序同目录的 `icons/` | `pygame.image.load('icons/xxx.png')` |
| 图片 | 与运行程序同目录的 `images/` | `pygame.image.load('images/xxx.jpg')` |

- 字体文件名 + 绝对路径、图标文件名 → 唯一信源是 `我的好搭AI派说明.md` 对应章节。
- **图片文件名不在任何说明文件中**：只能 ①默认 `images/1.jpg` ②用户需求里给 ③问用户；都没提时回退为纯色绘制 + 渐变填充。
- 本资料文件夹里的 `字体文件/`、`icons/`、`images/` **只是本地副本，不是设备运行路径**。

### 2.3 自动生成的数据目录

| 目录 | 内容 |
|---|---|
| `face_database/` | V3 人脸特征库（二进制）+ `face_records.json`（应用层姓名↔face_id 映射） |
| `object_database/` | V3 物体特征库 + `object_records.json`（名称/样本数/时间戳） |
| `logs/` | 所有程序日志（追加模式） |
| `recordings/` | TTS 语音 WAV 缓存（按文字哈希命名，重复播报不重复合成） |

> **注意：`object_data/` 是历史遗留**（`object_db.json` 内容 `{"objects":{}}`，无人引用）。**新项目绝对不要写这个目录**。
> **注意：**`好搭AI派基本情况.md` 的"使用要点"仍写"物体库 `object_data/`"，属错误，忽略。

---

## 3. 十三条红线（违反即返工）

1. **Python 3.8.10 锁版**，不用 3.9+ 语法。
2. **cv2 5.0.0，且不得安装/卸载/替换任何 OpenCV 发行包**（`opencv-python` 与 `opencv-contrib-python` 互斥；aarch64+cp38+5.x 无 whl，换包必炸）。详见 1.2 的说明与第 15 章核验命令。
3. **pygame-ce 2.5.2**，不装原版 pygame，不升 2.5.4+。
4. **摄像头**：默认走 `camera_vision_system_v3` SDK；**纯 cv2 模式 / 混合模式**下用 `cv2.VideoCapture(path, cv2.CAP_V4L2)`（路径字符串 + V4L2 后端，**禁传 int**），**候选顺序 `40→41→42` + 每步帧验证**；**V3 全托管模式下绝对禁用 `cv2.VideoCapture`**。
5. **import 顺序固定**：`os.environ`（LIBGL）→ `text_recognition`（若用 OCR）→ `pygame` → `cv2` → `numpy` → V3。`LIBGL` **必须在所有 import 之前**设置，否则 PaddleOCR 触发 Mali 驱动崩溃。（现有代码多用 `setdefault`；**建议直接用赋值 `os.environ['LIBGL_ALWAYS_SOFTWARE']='1'`**，避免环境里已有空值时失效。）
6. **pygame 初始化（分档规则，2026-09-12 校准）**：
   - **默认**：`pygame.display.init()` + `pygame.font.init()` 分段初始化。
   - **需要音频时**：另加 `try: pygame.mixer.init() / except`，并**全生命周期只 init 一次**（重复 init/quit ⇒ 播报静音且不报错，见《摄像头调用参考方案》7.1）。
   - **"摄像头 + 音频"必须分段**：工作区里所有同时用摄像头与音频的程序（文字识别播报器/智慧阅读角/文字识别视频播放器/文字识别播视频qoder/物体识别播报/人脸表情识别器（自带算法）/姿态检测）**100% 使用分段初始化**。
   - **不要把"不用 `pygame.init()`"当铁律**：`pygame.init()` **不是错误写法、也不会抛异常**（失败会收进返回值），只是会连带初始化 mixer/joystick/CDROM。工作区 **11 个已交付程序在用 `pygame.init()`**（`人脸学习.py:583`、`人脸识别灯效.py:507`、`人脸表情识别（云算法）.py:450`、`唐诗宋词朗读器.py:507`、`music_player.py:133`、`weather_app.py:482`、`weather_mqtt.py:532`、`voice_llm_chat.py:140`、`fan_control.py:60`、`font_showcase.py:205`、`red_revolution_app.py:469`）——其中带摄像头的 3 个（人脸学习 / 人脸识别灯效 / 人脸表情识别（云算法））**都不使用音频**且运行正常。本设备音频驱动与 V4L2 的异常/死锁属**文档级风险**，未做对照实验。
7. **V3 初始化 7 步不可遗漏**（第 6 章），`_init_detectors()` 漏调 = 所有检测结果为空。
8. **日志必须写 `logs/`，扩展名统一 `.log`**（已定案）；禁止根目录散落 `.txt`/`.log` 文件。
9. **人脸数据 `face_database/face_records.json`、物体数据 `object_database/object_records.json`**，访问前必须 `os.makedirs(..., exist_ok=True)`；**禁用 `object_data/`**。
10. **颜色识别区域坐标用 640×480**（V3 内部处理分辨率），不是 1280×720，越界报"无效的区域坐标"。
11. **删除规则（已按实测更正理由）**：
    - **人脸侧**：V3 **没有**单人删除接口——`delete_face` 方法**根本不存在**，调用只会 `AttributeError`（所谓"会破坏整个识别模型"是**误传**，实际来自旧的应用层私有实现，见 `清空人脸数据库.py:20-22`）。单条删除**只在应用层 `face_records.json` 删行**。
    - **物体侧**：V3 **有** `delete_object_recognition_class(class_name=...)`，而且**官方清库工具 `清空物体数据库.py:118-123` 就是用它逐个删类**。因此"永不调用"的说法与官方工具冲突；正确口径是：**日常单条删除只删 JSON 行，该接口仅用于清库流程**（避免误删类别导致特征库与 JSON 不一致）。
    - 彻底清库只用 `清空人脸数据库.py` / `清空物体数据库.py`，执行完**必须重启 Python 进程**。
12. **无板载按键**（已确认）：`GPIO_BUTTON = 0` / `GPIO_IO_00` 相关读取代码**一律删除**；不要设计"按板载按键触发"的交互，改用屏幕按钮、语音、传感器或 ESP32 外接按键模块。
13. **新建/生成的 `.md` 一律 UTF-8 no BOM**（2026-09-12 已全量校验：资料夹现有 `.md` **全部合规**）；**窗口默认 1920×1080、最大 1920×1280、窗口模式**。

---

## 4. 标准启动骨架（新项目必抄）

```python
# -*- coding: utf-8 -*-
"""
<项目名> - 好搭AI派
功能：<一句话描述>
硬件：<外设清单>
依赖：<库清单>
"""
import os
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')  # 必须在 ALL import 之前

# 若用 OCR：必须在 pygame / cv2 / camera_vision_system_v3 之前导入
# （os / sys / time / threading / numpy / ESP32 / Line_Sensor 不冲突，可放前面）
# from text_recognition import TextRecognizer as _TextRecognizer

import datetime
import sys

import pygame
pygame.display.init()
pygame.font.init()
# 需要音频时才初始化 mixer，且整个生命周期只初始化一次：
# try:
#     pygame.mixer.init()
# except Exception as e:
#     print('pygame.mixer 初始化失败，音频功能不可用: %s' % e)

import cv2          # 必须在 pygame 之后
import numpy as np

# ===== 日志标准模式（logs/ + 追加写 + stdout 分路）=====
_LOG_DIR = 'logs'
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(
    _LOG_DIR, '<程序名>_%s.log' % datetime.datetime.now().strftime('%Y%m%d')
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

# ===== pygame 显示（必须在开摄像头之前 set_mode）=====
# screen = pygame.display.set_mode((1920, 1080))   # 默认横屏【窗口】；最大 1920×1280；画面区 640×480 时窗口高度用 620

# ===== V3 视觉系统（涉及 V3 算法时）见第 6 章 =====
# ===== 摄像头（纯 cv2 / 混合模式）见第 5 章 =====
```

**要点**
- `pygame.display.set_mode()` 必须在 `vs.open_camera()` / `cv2.VideoCapture()` **之前**，否则 SDL2 会重置 V4L2 设备描述符。
- `text_recognition` 冲突范围经 v4.1 精确化：真正冲突的只有 `cv2` / `pygame` / `camera_vision_system_v3` 三个库（它们会把 `utils` 注册为非包模块，使 `ppocr_system` 的 `from utils.operators import ...` 失败）。`TextRecognizer()` 实例化必须在**摄像头打开之前**完成。
- `pygame.mixer` 禁止重复 `init()`/`quit()`：一旦重复，后续 `music.load()/play()` 静默失效（无报错、无声音）。

---

## 5. 摄像头：三模式选择

### 5.1 决策树（黄金法则）

```
需要 V3 官方算法的"持续后台检测"（实时追踪 + 硬件联动）？
├─ 是 → 模式 C：V3 全托管（禁用 cv2.VideoCapture；画面用 vs.capture_frame()）
└─ 否 → 用第三方/官方算法但按需触发？
        ├─ 需要 V3 官方算法做特征提取/录入 → 模式 B：混合模式（cv2 采图 + 传帧给 V3）⭐ 默认首选
        └─ 完全不需要 V3（MediaPipe / dt-apriltags / 百度云 / PPOCR）→ 模式 A：纯 cv2 独占
```

> **补充铁律（判据要说全）**：只有当 `enable_basic=False, enable_advanced=False` **并且**没有手动 `enable_XXX = True`、**也没有**调用 `_init_detectors()` 时，才说明"SDK 只被当作帧采集器"→ **直接改纯 cv2 模式**。注意：标准 7 步流程本身就是 `enable_basic=False, enable_advanced=False` + 手动 `enable_XXX` + `_init_detectors()`，**这种程序是真在跑检测的，别误判成帧采集器**。

### 5.2 三模式对照

| | 模式 A 纯 cv2 | 模式 B 混合 ⭐ | 模式 C V3 全托管 |
|---|---|---|---|
| 摄像头 | `cv2.VideoCapture` 独占 | `cv2.VideoCapture` 独占 | V3 `open_camera()` 独占 |
| `open_camera()` | 不调 | **严禁调** | 调 |
| `start_background_detection()` | 不调 | 严禁调 | 调 |
| `cv2.VideoCapture` | 必须 | 必须 | **绝对禁用** |
| 取画面 | 自己的线程 | 自己的线程 | `vs.capture_frame()`（+ `time.sleep(0.15)`） |
| 帧率 | 30 fps | 30 fps | 6~7 fps（视算法组合） |
| 典型项目 | 手势控制RGB灯带、人体姿态识别器、人脸表情识别（云）、文字识别播报器 | 人脸学习、物体学习（传帧） | 人脸识别灯效、物体学习（内部取帧） |

### 5.3 摄像头打开规则（A/B 模式通用，**必须遵守**）

1. **必须** `cv2.VideoCapture('/dev/videoN', cv2.CAP_V4L2)`：字符串路径 + 显式 V4L2 后端。
   **绝对不能传 int**（`cv2.VideoCapture(42)`）：设备号 40~42 ≥ 32 会命中 OpenCV **FFMPEG 后端只有 32 项**的越界，每次失败 4~6 秒，启动要十几秒；V4L2 后端直连内核，毫秒级。
2. **候选顺序：`40 → 41 → 42`（已定案，2026-10-09 按设备实测修订；原 `42 → 41 → 40` 作废）**，逐个尝试，每步：
   `os.path.exists('/dev/videoN')` 检查节点 → `cv2.VideoCapture('/dev/videoN', cv2.CAP_V4L2)`（字符串路径）打开 → 最多读 5 帧用 `gray.mean()` 验证非全黑/全白（**用 `mean` 不用 `std`**，ARM 上 `std` 开销大）。
   - **实测结果（2026-10-09）**：首个可用节点 = `/dev/video40`；`/dev/video42` 不存在；`/dev/video41` 可打开但读不到有效帧。据此把候选顺序定为 `40→41→42`。
   - 因此 `project_memory.md:23`、SKILL、补充说明、探测报告里历史写 `42→41→40`（被推翻的旧口径）与 `41→40` 的地方，**统一改回 `40→41→42`**。
3. **每一步都必须做帧有效性验证，不能只 `os.path.exists`**：`/dev/video41` 常是**元数据节点**（`Not a video capture device`）；`/dev/video40/42` 也可能在某次枚举中不存在（探测报告 2026-08-15 的 44 节点清单里就只有 0~41，没有 42——**节点编号随 USB 口/插拔/枚举变化，不要当成固定事实**）。节点不存在就跳过，不要报错。
4. 可选：`cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))` 降带宽。
5. **架构必须双线程分离**：后台守护线程只做 `cap.read()` 刷新共享帧（`threading.Lock` 保护），主线程取最新帧跑算法。采集线程正常 0.05 s（≈20 fps），连续失败 3 次降为 0.33 s（≈3 fps），恢复后自动回升。主循环永不阻塞。
6. 退出时 `cap.release()`。

> ✅ **口径已定案（2026-10-09 按设备实测修订）**：`40 → 41 → 42` + 每步帧验证。写代码时建议把每个候选的 `os.path.exists / opened / mean` 打进日志，便于以后复核。
> 参考实现（照抄即可）：
> ```python
> CAMERA_CANDIDATES = (40, 41, 42)   # 已定案顺序
> cap = None
> for cid in CAMERA_CANDIDATES:
>     path = '/dev/video%d' % cid
>     if not os.path.exists(path):
>         print('[摄像头] %s 不存在，跳过' % path); continue
>     c = cv2.VideoCapture(path, cv2.CAP_V4L2)
>     if not c.isOpened():
>         print('[摄像头] %s 打开失败，跳过' % path); c.release(); continue
>     ok = False
>     for _ in range(5):
>         r, f = c.read()
>         if r and f is not None and f.mean() > 1.0:   # 排除全黑/全白/元数据节点
>             ok = True; break
>     if ok:
>         cap = c; print('[摄像头] 使用 %s' % path); break
>     print('[摄像头] %s 无有效帧，跳过' % path); c.release()
> ```

### 5.4 模式 C（全托管）实测约束

- 画面只能 `vs.capture_frame()`；采集线程加 `time.sleep(0.15)` 以免干扰 V4L2 缓冲。
- 启动可能十几秒（SDK 内部对设备号 ≥32 走 FFMPEG 越界 → 回退备用 ID）。
- 退出：`vs.threaded_system.stop_background_detection()` + `vs.close_camera()`（或 `vs.cleanup()`）。
- 误用 `cv2.VideoCapture` 会报 `Device or resource busy`。

---

## 6. V3 视觉系统标准用法

### 6.1 初始化 7 步（顺序不可乱）

```python
from camera_vision_system_v3 import create_vision_system_v3

# Step 1  创建（不自动加载算法）
vs = create_vision_system_v3(
    camera_id=-1, width=1280, height=720,
    enable_basic=False,      # 必须显式 False！库真实默认值是 True（会预载 AprilTag/黑线/二维码）
    enable_advanced=False,
)

# Step 2  打开摄像头（无参数！由 CameraConfig.backup_camera_ids=[40,41,42,43] 自动探测）
#         必须在 pygame.display.set_mode() 之后调用
vs.open_camera()

# Step 3  按需开启算法
# 注意：只有下面这 13 个开关名是真实存在的（来自 DetectionConfig 反射）。
#    写成 enable_yolov8 / enable_resnet 不会报错，但只是给对象挂了个野属性，
#    算法永远不会被启用（静默失效，最难查）。
vs.detection_config.enable_face_recognition = True
# 其余 12 个：enable_apriltag / enable_qr_code / enable_color_recognition / enable_color_block
#             enable_black_line / enable_facial_expression / enable_object_recognition
#             enable_plate_recognition / enable_image_classification（ResNet 图像分类）
#             enable_people_counter / enable_object_detection（YOLOv8 目标检测）
#             enable_pose_detection（YOLOv8 姿态）
# 也可写成 vs.enable_xxx = True（两种访问方式等价）

# Step 4  【关键】加载 RKNN 模型——漏调 = 所有检测器返回空
vs._init_detectors()

# Step 5  仅颜色识别需要：区域坐标必须是 640×480 空间
# vs.detection_config.color_recognition_regions.append((50, 100, 200, 200))   # x+w=250≤640 ✓
# vs.detection_config.color_recognition_regions.append((300, 200, 400, 400))  # x+w=700>640 ✗

# Step 6  启动后台检测
vs.threaded_system.start_background_detection(show_preview=True)

# Step 7  主循环里每次读结果前必须刷新
while True:
    vs.result_accessor.refresh_results()
    # frame = vs.threaded_system.get_latest_frame()
    # ... get_xxx() ...
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            raise KeyboardInterrupt
    pygame.time.delay(33)   # ~30 FPS
```

`open_camera(40)` 会报 `takes exactly 1 positional argument (2 given)`——**它不接受参数**。

### 6.2 工厂函数选择

| 工厂函数 | 预启用算法 | 适用 |
|---|---|---|
| `create_vision_system_v3(enable_basic=False)` + 手动 `enable_xxx=True` | 无 | 单一算法，启动最快（最常用） |
| `create_vision_system_v3(enable_basic=True)`（默认） | AprilTag / 黑线 / 二维码 | 基础算法场景 |
| `create_vision_system_v3(enable_advanced=True)` | 车牌 / 物体识别 / 人流计数等 | 高级算法场景 |
| `create_ai_detection_system(...)` | 深度学习类（人脸/表情/YOLO/ResNet） | 只要 AI 算法 |
| `create_full_detection_system_v3(...)` | 全部算法 | 全都要，最慢 |

签名默认值：`camera_id=-1, width=640, height=480`（文档与范例统一传 1280×720）。

### 6.3 结果获取的四种方式

| 方式 | 写法 | 特点 | 场景 |
|---|---|---|---|
| 轮询刷新 | `refresh_results()` + `get_xxx()` | 非阻塞 | 主循环绘 UI（最常用） |
| 取最新 | `threaded_system.get_latest_results()` | 非阻塞 | 只要最新结果 |
| 阻塞等待 | `threaded_system.get_next_result(timeout=1.0)` | 阻塞带超时 | 串行处理 |
| 批量 | `threaded_system.get_all_pending_results()` | 非阻塞 | 处理积压 |

回调系统（事件驱动）：
```python
ts = vs.threaded_system
ts.add_detection_callback(cb)   # cb(result_dict)  ~8 次/秒（实测 46 次/6s）
ts.add_frame_callback(cb)       # cb(frame(480,640,3), result_dict)
ts.add_error_callback(cb)       # cb(exception)
ts.remove_callback(...)         # 移除
```
- 是 `add_*` **不是** `set_*`。
- detection dict **14 个 key**：apriltag / black_line / color_block / color_recognition / face_recognition / qr_code / plate_recognition / object_recognition / people_counter / image_classification / object_detection / pose_detection / facial_expression / **timestamp**。
- list 型算法（apriltag / qr_code）空时返回 `[]`，dict 型空时返回 `{}`。

### 6.4 算法与结果方法速查（13 类算法 + 通用）

> 口径：`camera_vision_system_v3_API分析报告.md` 第 5 章为 5.1 通用 + 5.2~5.14 共 **13 类算法**；detection dict 的 14 个 key 含 `timestamp`。
> 注意：多份文档称"**14 类算法**"，属把 timestamp 算进去的误记。

| 算法 | result_accessor 主要方法 | 返回结构要点 |
|---|---|---|
| 通用 | `refresh_results()`、`get_detection_summary()`、`get_detection_timestamp()`、`get_active_detection_types()`、`has_any_detection()`、`is_point_in_bbox(p,bbox)`、`calculate_distance_between_points(p1,p2)` | 读结果前必 `refresh_results()` |
| AprilTag | `get_apriltag_count/id/family/center/corners/pose_R/pose_t/hamming/decision_margin` | `pose_t` 可测距 |
| 二维码 | 见 API 报告 5.3 | 空时 `[]`；⚠️ 真实二维码返回结构未实测（需实物），可 fallback `cv2.QRCodeDetector()` |
| 颜色识别 | `get_color_recognition_count/name(i)/color(i)/rgb(i)` | `{image_info:(640,480), regions:[{name:'区域_N', region, error, rgb, hex, area, position, color_label, closest_basic_color}], total_regions, successful_regions}`；越界时 `error='无效的区域坐标: ...'`、`rgb/color_label=None` |
| 色块检测 | `get_color_block_count/color(i)/position(i)/center(i)/area(i)/has_color_block()/get_largest_color_block_index()` | 默认目标色 `'红色'`；`position=(x,y,w,h)`；**`center` 恒为 (0,0)（库 bug）→ 自己算 `x+w//2, y+h//2`** |
| 黑线/巡线 | 见 API 报告 5.6 | 未实测 |
| 人脸识别 | `get_face_count/confidence/position/name/id`、`has_face_id(face_id)`（**必须传参**） | `{success, face_id, confidence, face_position:(x,y,w,h), message}`；无匹配时 `message='未找到匹配的人脸'` |
| 人脸表情 | `get_facial_expression_emotion()/emotions_confidence()/engagement()/engagement_confidence()/success()/inference_time()` | 8 类情绪 Anger/Contempt/Disgust/Fear/Happiness/Neutral/Sadness/Surprise；`engagement` 是字符串 `'Engaged'/'Distracted'`；推理 ~6 ms |
| 自定义物体 | `get_object_recognition_class_name()/confidence()/success()` | **没有 `get_object_name()` / `get_object_recognition_count()`**；只能识别 1 个物体，用 `success` 判断 |
| 车牌 | 见 API 报告 5.10 | 未实测 |
| 图像分类 ResNet | 见 API 报告 5.11 | 1000 类 |
| 人流计数 | 见 API 报告 5.12 | 进入/离开/总通过/净流量 |
| 目标检测 YOLOv8 | 见 API 报告 5.13 | s/m/l/x |
| 姿态 YOLOv8-Pose | 见 API 报告 5.14 | 17 关键点 |

### 6.5 已实测的坑（写代码必看）

1. **`_init_detectors()` 漏调** → 所有算法字段恒空。历史探测脚本犯过此错，得出过"检测器不可用"的错误结论。
2. **颜色识别坐标**：内部处理分辨率实测 640×480（回调 `image_info.width/height=640/480`），传 1280×720 坐标必报错 → 范例代码 5.04 / 5.05 就是这么错的。
3. **`get_color_block_center(idx)` 恒返回 (0,0)**：用 `get_color_block_position()` 自己算。
4. **`engagement` 不可用于判断"是否看屏幕"**：正视 / 看旁 / 闭眼低头三阶段实测 **100% 返回 Engaged**，confidence 恒 ~50/50。语义是"检测到人脸且足以判情绪"。要做状态区分请用 `emotion`（正视→Neutral、看旁→Anger、闭眼低头→Sadness）+ `face_position` 是否在中心。
5. **`has_face_id(face_id)` 必须传 face_id**（self + 1 个实参），无参 TypeError；**传的是 face_id，不是姓名**——name 与 face_id 是两个字段，face_id 从 `learn_new_face()` 返回的 dict 或 Tier-2 JSON 的 `face_info.face_id` 取。
6. **`get_face_id()` 返回类型（已定案）**：**成功返回 `str`，无人脸返回 `None`**（文档里 `int` / `None 或 0` 的说法作废）；配套 `get_face_name()` 无人脸时返回 `'ID_None'`。代码里**不要 `int()` 或 `%d` 格式化**，按字符串/None 处理。
7. **人脸/物体单条删除没有官方接口**：`delete_face` 不存在（AttributeError），删单人只在应用层 JSON 删行。
8. **`face_db_path='face_database'`、`object_db_path='object_database'` 是相对路径** → **程序工作目录变了，已学习的人脸/物体就"丢了"**。固定在工作目录 `user/` 下跑。
9. **色块目标颜色字段名是 `detection_config.color_block_target`**（实测反射签名），默认 `'红色'`（中文字符串）；**不叫 `color_block_target_color`**（写成后者只是挂个野属性，颜色不会变）。可切换的枚举值未实测。
10. **算法开关名只有 13 个是真实的**（见 6.1 Step 3 清单）；**`enable_yolov8` / `enable_resnet` 不存在**，写成它们会**静默失效**（不报错但不生效）。
11. **`stop_background_detection()` 在 `threaded_system` 下**，不在 `vs` 顶层。
12. **`enable_basic` 真实默认 `True`**，必须显式传 `False`。
13. **`cv2.findContours` 在 5.0 返回 2 值**（contours, hierarchy）。
14. 人脸学习支持 `learn_new_face(frame=None)`（返回 **dict**，含 `success`/`face_id`/`message`）；物体学习支持 `add_object_recognition_class(frame=None, class_name=None)` / `add_object_recognition_sample(frame=None, class_name=None)`——**参数名是 `class_name`，不是 `name`**。
15. **回调实测频率 ≈8 次/秒**（实测 6 秒 46 次；文档别处的 ~15 / ~10 次/秒作废，以 8 为准）；detection dict 共 **14 个 key**（**13 个算法字段 + `timestamp`**，不是"14 个算法字段"）。
16. **`show_preview` 取值**：文档里 `True`/`False` 两种都出现过，未明确语义——传 `False` 时画面由你自己 pygame 绘制（推荐），传 `True` 时会额外弹预览窗口。以实测为准，先按 `False` 写。
17. **清空数据库的三种写法并存**：`vs.cleanup()`（范例）/ `vs.threaded_system.stop_background_detection()` + `vs.close_camera()`（SKILL 模板）——两者都能释放资源，新代码用后者并保证可重复调用。

---

## 7. 非视觉官方库速查（`/home/cxdz/jupyter/lib/` 下的 7 个闭源库）

> 说明：`好搭AI派基本情况.md` 说该目录有 **35 个 `.so`**（含 yolov8/ppocr/face_recognition_module/people_counter/whisper 等）。"7 个官方库"指的是**应用层直接 import 的 7 个**。

### 7.1 ESP32（扩展板）

```python
from ESP32 import *
board = ESP32()
if not board.start():
    raise Exception('扩展板连接异常，请检查硬件')
```
- 串口：**双路径并存（已实测，2026-10-09）**——内部 UART `/dev/ttyS9` 与 CH341 USB `/dev/ttyCH341USB0`、`/dev/ttyCH341USB1` 均存在且可打开。**代码层一律用 `board.start()` 自动探测，不硬编码串口**；排障时按第 15 章命令实测确认。
- 引脚常量：数字 IO `GPIO_IO_01`~`GPIO_IO_08`（**已实机确认 8 个**；规范写 16 个是错的）；模拟 `ADC_IO_01`~`ADC_IO_08`（**已实机确认 8 路，8 个接口都能作 ADC**；基本情况写 01~04 是错的）；`GPIO_BUTTON = 0` **忽略**——**已确认硬件无板载按键**，相关代码一律删除。
- **内置重试**：`__max_retry_count=3`、`__sync_timeout=2.0s` + `safe_operation()` → **不要在外面再包一层重试**。
- **8 个异步 Callback API 优先于阻塞读**（UI 响应性要求高时）：
  `digitalReadCallback` / `analogReadCallback` / `dhtReadTemperatureCallback` / `dhtReadHumidityCallback` / `ds18b20ReadCallback` / `ultrasonicReadCallback` / `bmp280ReadPressCallback` / `bmp280ReadTemperatureCallback`
- 传感器：DHT11、DS18B20、超声波 HC-SR04、BMP280（隐藏功能，走 I2C，默认 `sck=GPIO15, sda=GPIO16`）；**接线参照范例代码即可**（用户口径）。
- 执行器：舵机（0~180°，待实测范围）、电机 `MA`/`MB`（±1023）、**WS2812（默认 10 灯，IO1~IO8 任选一口：`ws2812Init(pin, 10)` / `ws2812Write`）**、继电器风扇。
- 隐藏能力：I²C 6 方法（`i2c_init/i2c_scan/i2c_writeto/i2c_readfrom/i2c_writeto_mem/i2c_readfrom_mem`）、UART 5 方法（`uart_init(uart_id, baudrate=115200, bits=8, parity=None, stop=1, tx=None, rx=None, timeout=10, flow=0)` / `uart_deinit` / `uart_any` / `uart_read` / `uart_write`）、数据打包工具（`char2byte/short2bytes/long2bytes/float2bytes` + `readBytes/readShort/readLong/readFloat/readString`）。
- 硬件操作固定写法见上；完整 50+ 方法签名见探测报告第 3 章。

### 7.2 Line_Sensor（巡线）

**外接模块：I²C 4 线、4 个探头**（用户确认）。独立模块，I²C 固定地址 82；`readline(li)` / `readline_all(li)` / `readlinead(...)` / `linecalibrate()` / `Lineheight`；4 路寄存器枚举见探测报告第 4 章（返回结构未完全实测）。

### 7.3 voice_api（语音 AI）

- 两个 LLM 后端：`llm_chat(text)`、`llm_chat_znbw_2025(text)` → **优先后者**（更新）。
- **token 无自动刷新**：HTTP 401 时重新 `VoiceAPI.get_token(user, password)`，不存在 `refresh_token`。
- 其他：TTS 合成、语音识别（`voice_recognition()`）、翻译。
- 常量：`API_BASE_URL=ApiZNBW.php`、`API_VOICE_URL=ApiXXKJ.php`、`TOKEN_FILE_PATH=/tmp/.system_cache/config.json`。
- 未登录时 LLM 方法返回 `None`（不是抛异常），要判空。

### 7.4 audio_recorder

- 默认 `sample_rate=16000, channels=1, dtype='float32'` —— 与 `VoiceAPI.voice_recognition()` 输入规格**精准匹配，无需重采样**。
- 有固定时长录音 / `start()`+`stop()` 无限录音。
- **没有** `set_sample_rate` / `pause` / `is_recording`。
- `voice_recognition()` 只吃**文件路径**；若录音只拿在内存里，需先落盘（`save_audio` 或录音时传 filename）。

### 7.5 audio_player

- **方法名（已定案）**：仅 `play_file(file_path, prefer_pygame=True)` / `play_audio(audio_bytes, prefer_pygame=True)` / `play_with_pygame` / `play_with_pyaudio` / `cleanup` 共 5 个公开方法；**没有 `play()`**（SKILL 与开发规范写的 `AudioPlayer.play()` 是错的）。**用前先 `dir()` 确认**。
- **没有** pause / resume / stop / 音量 / seek —— 需要播放控制就改用 `pygame.mixer`。
- 需要播放控制的场景一律用 `pygame.mixer`（`music_player.py` 是完整参考）。

### 7.6 text_recognition（本地 PPOCR）

- 导入顺序见第 4 章（必须在 cv2/pygame/V3 之前）；`TextRecognizer()` 必须在开摄像头之前实例化。
- 类只有 `recognize_text(image_input, confidence_threshold=0.5)`；模块级另有 `recognize_image_text()` / `extract_text_from_image()`。
- **没有** `set_language` / `set_region` / `angle_classify`。
- 返回：`{'success', 'text', 'details':[{'text','confidence','bbox':[[x,y]×4]}], 'error'}`；`DET_INPUT_SHAPE=[480,480]`。

---

## 8. UI 与显示规范

1. 分辨率：**1920×1080 横屏窗口**（默认，非全屏）。
2. 配色偏好：浅色背景 / 多色文字 / 不用黑色暗色 / 天空蓝优先。
3. 字体：从 `我的好搭AI派说明.md`「已上传好搭AI派字体文件」章节里挑，**绝对路径**加载。常用中文字体：`simfang.ttf`、`simhei.ttf`、`msyh.ttc`、`PingFang_*.ttf`、`WenQuanWeiMiHei.ttf`、`STXINGKA.TTF` 等（共 24 个）。
   选定前可先跑 `font_showcase.py` 预览 24 种字体。
4. 图标：从 `icons/` 里挑文件名，相对路径 `icons/xxx.png`（说明文件清单与设备 `icons/` 逐名一致，共 97 个）。写"无"= 不用图标。
5. 图片：默认 `images/1.jpg`；需求没提就不贴图（纯色 + 渐变填充）。
6. 窗口尺寸（已定案）：**默认 1920×1080 横屏窗口模式；最大 1920×1280**。若只做 640×480 小画布，则窗口高度至少 620（画面 480 + 顶部标题 36 + 底部指引 28 + 状态行）。
7. 缩放用 `pygame.transform.scale`（最近邻），不要 `smoothscale`（双线性在 ARM 上很慢）。
8. 退出：把退出按钮放标题栏右上角，并处理 `pygame.QUIT`。
9. **摄像头/键鼠/外设开关（已实机确认）**：
   - 管理器界面最下方**只提示"有/没有摄像头"，不显示节点号** → 判节点用 `探测工具/探测_待定项核对.py` 或 `v4l2-ctl --list-devices`，勿按提示猜节点。
   - USB 摄像头**插在扩展板的 USB 母口上（共 2 个，任选）**；换口会改变 `/dev/video4x` 编号。
   - 扩展板的 2 个 USB 母口**也可以插 USB 键盘/鼠标**（OpenCV 窗口要按 `q` 退出时用得上）。
   - **右下角是两位开关：左 = 启用外设（ESP32 扩展板），右 = 充电**；外设不工作时先把它拨到左侧。**充电口是独立的 Type-C 口**，与 USB 数据口不是同一个。

---

## 9. 数据持久化与人脸/物体学习

### 9.1 两层存储模型

| 层 | 归属 | 内容 | 谁管 |
|---|---|---|---|
| Tier 1 | V3 SDK | `face_database/`（二进制特征）、`object_database/`（特征 + 分类器） | SDK 自动管理；`learn_new_face()` / `add_object_recognition_class/sample` 写入 |
| Tier 2 | 应用层 JSON | `face_database/face_records.json` → `[{name, face_info:{success,face_id,message}}]`，关联键 `face_id`<br>`object_database/object_records.json` → `[{name, sample_count, first_learned, last_learned}]`，关联键 `name` | 你的程序 |

- **JSON 必须与 V3 二进制库放在同一目录**（即 `face_database/`、`object_database/` 内），**不许放项目根目录**。
- 访问前 `os.makedirs('face_database', exist_ok=True)`。
- 人脸库容量上限、重复注册行为以 `人脸学习项目说明文档.md`「重复注册补录机制」为准（本指南未实测）。

### 9.2 删除与清库

| 操作 | 正确做法 |
|---|---|
| 删单条 · 人脸 | **只删应用层 `face_records.json` 那一行**。V3 **没有** `delete_face` 方法（调用只会 `AttributeError`）；"会破坏模型"是误传，见 `清空人脸数据库.py:20-22` |
| 删单条 · 物体 | 同样**只删 `object_records.json` 那一行**。注意 V3 **有** `delete_object_recognition_class(class_name=)`，**官方清库工具就是用它逐个删类**（`清空物体数据库.py:118-123`）——所以别把"永不调用"当铁律，但也**不要在日常单条删除时用它**，避免特征库与 JSON 不一致 |
| 彻底清库 | 只用 `清空人脸数据库.py`（`clear_face_database()` + 删目录）/ `清空物体数据库.py`（逐个删类 + 删 JSON + 删目录），执行完**必须重启 Python 进程**再重新学习 |
| 直接删目录 | 删整个 `face_database/` 或 `object_database/` 属**非破坏性重置**（V3 首次写入会重建），只是丢数据 |

### 9.3 灾备

Tier-2 JSON 丢了但 Tier-1 库还在 → 重新录入时 V3 会返回**已存在的** `face_id` / `class_name`，把新行按当前用户给的名称追加进 JSON 即可恢复映射。

### 9.4 其他持久化

- SQLite / CSV：字段结构 + 文件名 + 路径在需求里写清。
- 内存态：明确"每次运行重置"。
- 人脸/物体类项目**不要重造学习 UI**，直接前置跑 `人脸学习.py` / `物体学习.py`。

---

## 10. 日志与终端适配

### 10.1 标准日志模式

```python
_log_dir = 'logs'
os.makedirs(_log_dir, exist_ok=True)
LOG_FILE = os.path.join(_log_dir, '<程序名>_%s.log' % datetime.datetime.now().strftime('%Y%m%d'))
# 追加模式 + 块缓冲：open(LOG_FILE, 'a', buffering=-1, encoding='utf-8')
```

- 必须 `logs/` 目录，**禁止**根目录散落 `.txt`/`.log`。
- 追加模式（`'a'`），同一程序多次运行追加到当天文件。

> ✅ **扩展名已定案：统一 `.log`（2026-09-12 裁决）**
> - 需修订为 `.log` 的地方：`project_memory.md:29`、`视觉系统摄像头调用参考方案.md:895`、`好搭AI派范例代码补充说明.md:234`；`探测工具/` 里 4 个 `.txt` 历史脚本与日志**保持原样**（历史产物），但在探测工具说明里注明"扩展名不代表现行规范"。
> - 与现状一致的部分：`haoda-aipai-dev_SKILL.md:36-37`、`好搭AI派项目开发规范.md:101/206`，以及现有 14 个有日志落盘的项目 `.py`（人脸学习 / 人脸识别灯效 / 物体学习 / 物体识别播报 / 人数实时统计 / 文字识别播报器 / 手势控制RGB灯带 / 智慧阅读角 / 人体姿态识别器 … 全是 `.log`）。
> - 新项目模板：`LOG_FILE = os.path.join('logs', '<程序名>_%s.log' % datetime.datetime.now().strftime('%Y%m%d'))`。

### 10.2 终端「[错误]」红标问题

好搭AI派终端把**所有 stderr 输出**标红为「[错误]」，第三方库的正常 INFO 也会被标红。用 `logging` 的程序必须做四件事：

1. `StreamHandler(sys.stdout)`，不用默认 stderr；
2. `sys.stderr` 重定向到 logger 包装；
3. `logger.propagate = False`（禁冒泡）；
4. 去掉 `print(msg)` + `logger.info(msg)` 双写。

---

## 11. 性能与并发

| 场景 | 目标帧率 |
|---|---|
| 实时交互（画面 + 追踪 + 联动） | ≥ 15 FPS |
| 检测展示类（按一下识别一次） | 5~10 FPS |
| 纯展示（无摄像头） | 30 FPS |

- 实测基准（640×480）：MediaPipe Hands 15.6 FPS、MediaPipe Pose 14.7 FPS、dt-apriltags 33.5 FPS、V3 color_block 推理 ~6 ms。
- 百度云图像 API：**`project_memory.md` 记的"160×120 + JPEG 质量 60 + 5 秒间隔"与现有代码不符** —— `人脸表情识别（云算法）.py` 实际是 `IMWRITE_JPEG_QUALITY 85`（L302）+ `API_INTERVAL = 1.5`（L115），全文无 160×120。**按需求显式指定参数**；没有特别要求时，以该已验证项目的 85 / 1.5 s 为准（要更省 CPU 再自行降分辨率/降质量/拉长间隔）。
- 内存无 OOM 风险（无 Swap，可用 6.7 GiB；V3 + MediaPipe + TTS 峰值约 600 MB）。
- 双线程分离 + 帧有效性验证 + 失败降频是标配。
- `pygame.mixer` 全生命周期只 `init()` 一次。
- 多算法叠加会明显降帧，需求里写明"允许同时开几个算法"。

---

## 12. 开发流程（7 步）+ 需求 8 类信息

### 12.1 7 步流程

1. **读约束**：`project_memory.md` 三节（Hard Constraints / Engineering Conventions / Lessons Learned）+ 本指南第 3 章红线。
2. **选摄像头模式**：本指南 5.1 决策树（A / B / C）。
3. **确认算法 API**：`camera_vision_system_v3_API分析报告.md`（DetectionConfig 默认值、第 5 章结果访问器、第 8 章易错点 + 8.8 实测补漏）+ 本指南第 6 章。
4. **确认非视觉库 API**：探测报告第 2.5 节版本决策 + 涉及库章节 + 第 9 章 15 条风险表；再读本指南第 7 章。
5. **选骨架项目**：从 13.1 表里挑功能最接近的**已验证项目**复制（UI 框架 / V3 初始化 / 日志 / 清库 / 持久化 1:1 复用，别从零写），并先读它的"已知限制/坑"章节。
6. **收齐需求 8 类信息**（12.2），不涉及的写"无"。
7. **生成 + 首跑**：确认 `face_database/`、`object_database/`、`logs/` 可写；出问题**先看 `logs/<程序名>_YYYYMMDD.log`**，不要第一时间改代码。

### 12.2 需求 8 类信息清单

1. **项目功能需求**：一句话描述 + 输入清单 + 输出清单 + 交互流程（时间轴）+ 触发模式（轮询/按钮/回调/常驻）。
2. **硬件外设**：ESP32 传感器清单 + 执行器清单 + 引脚分配表 + 非原厂外设协议。
3. **视觉算法**：算法多选（颜色/色块/二维码/AprilTag/人脸学习/人脸识别/表情/物体学习/物体识别/人流计数/YOLOv8/姿态/OCR/巡线/车牌/ResNet/MediaPipe）+ 摄像头模式 + 是否复用现有映射。
4. **UI 设计**：分辨率（默认 1920×1080）+ 配色 + 布局草图 + 字体（从说明文件清单选，给字号）+ 图标（从 icons 清单选）+ 图片（默认 `images/1.jpg` 或需求指定）+ 控件清单。
5. **联网需求**：离线/外网 + 协议细节（HTTP/MQTT/WebSocket…）+ VoiceAPI 用量（TTS/ASR/LLM）。
6. **数据持久化**：存储方式 + 位置 + 字段结构 + 生命周期 + 是否联动 V3 学习库。
7. **性能约束**：帧率 + 延迟 + 资源预算 + 日志要求 + 异常处理策略（重试 N 次退出 / 提示降级）。
8. **交付物与验收**：文件数（推荐 `<项目名>.py` + `<项目名>项目说明文档.md`）+ 1~3 个验收场景 + 性能指标。

---

## 13. 参考资产

### 13.1 骨架项目选择表（优先复制已验证项目）

| 需求 | 骨架代码 | 说明文档 |
|---|---|---|
| 人脸录入 + 姓名管理 | `人脸学习.py` | 人脸学习项目说明文档.md |
| 人脸识别 + 硬件联动 | `人脸识别灯效.py` | 人脸识别灯效项目说明文档.md |
| 表情识别（本地 NPU） | `人脸表情识别器（自带算法）.py` | 人脸表情识别器项目说明文档.md |
| 表情识别（百度云） | `人脸表情识别（云算法）.py` | 人脸表情识别（云算法）项目说明文档.md |
| 手势 + RGB 灯带 | `手势控制RGB灯带.py` | 手势控制RGB灯带项目说明文档.md |
| 姿态（MediaPipe） | `人体姿态识别器（MediaPipe）.py` | 人体姿态识别器（MediaPipe）项目说明文档.md |
| 姿态（V3 YOLOv8-Pose） | `姿态检测（自带算法）.py` | 姿态检测（自带算法）项目说明文档.md |
| 物体学习 | `物体学习.py` | 物体学习项目说明文档.md |
| 物体识别 + 播报 | `物体识别播报.py` | 物体识别播报项目说明文档.md |
| 人流计数 | `人数实时统计.py` | 人数实时统计项目说明文档.md |
| OCR + 播报 | `文字识别播报器.py` | 文字识别播报器项目说明文档.md |
| OCR + 视频字幕 | `文字识别视频播放器.py` / `文字识别播视频qoder.py` | 对应说明文档 |
| 风扇/继电器 | `fan_control.py` | 风扇控制项目说明文档.md |
| 语音 LLM 对话 | `voice_llm_chat.py` | 语音大模型对话项目说明文档.md |
| TTS 朗读 | `唐诗宋词朗读器.py` | 唐诗宋词朗读器项目说明文档.md |
| 本地音乐播放（完整控制） | `music_player.py` | 音乐播放器项目说明文档.md |
| HTTP 天气 | `weather_app.py` | 城市天气展示项目说明文档.md |
| MQTT 天气 | `weather_mqtt.py` | MQTT城市天气订阅展示项目说明文档.md |
| 综合 UI（摄像头+传感器+语音） | `智慧阅读角.py` | 智慧阅读角项目说明文档.md |
| 大型交互展示 | `red_revolution_app.py` | 红色文化交互展示项目说明文档.md |
| 字体预览 | `font_showcase.py` | 字体展示项目说明文档.md |

运维工具：`清空人脸数据库.py`、`清空物体数据库.py`、`探测工具/`（9 份探测脚本 + 4 份基准日志，含本章末的"待定项核对"程序）。
范例代码集：`好搭AI派范例代码.md`（65 个官方范例，编号 5.01~5.21 为 AI 视觉算法部分）。

> **范例代码怎么用（2026-09-12 按实际核查修正）**
> **它是本设备最可信的 API 依据之一，绝大多数可直接运行**，官方补充说明 §四 的 21 行评估里 19 行判"✅ 可用，需补补丁"，§1.3 明确"V3 初始化顺序整体正确"。
> - **可直接复制使用（28 个）**：§1 外设接口(5) + §2 扩展模块(8) + §3 音频(5) + §4 语音AI(7) + §6 物联网(3)——这些不涉及 GL，与 `LIBGL` 无关。
> - **必须先改（仅 2 个）**：**5.04 / 5.05 颜色识别**范例的区域坐标越界（`(300,200,400,400)`、`(800,200,400,400)`，x+w>640），须改为 **640×480**；其中 **5.05** 还会在 `RGBtup[0]` 处对 `None` 取下标抛 `TypeError`，且被裸 `except: pass` 吞掉，表现为"在跑但什么都不做"（详见分析报告 P1-22）。
> - **作为正式项目骨架时按工程约定补齐**：`LIBGL_ALWAYS_SOFTWARE`（置于 pygame/cv2/V3 之前）、日志落 `logs/<程序名>_YYYYMMDD.log`、人脸/物体学习类补 Tier-2 JSON、删除无实体按键的 `GPIO_BUTTON` 代码。
> - **注意信息位置**：范例集顶部原有的"关键差异提醒"已于 2026-08-14 迁至 `好搭AI派范例代码补充说明.md`，只看范例集的人看不到这些前提，用前请对照其 §1 与 §四。

### 13.2 文档阅读顺序

```
新人上手：好搭AI派学习手册.md（图形化/教学）
       → 好搭AI派基本情况.md（设备结构，注意其中 2 处错误见分析报告）
       → 本指南（施工口径）
开发前  ：project_memory.md → haoda-aipai-dev_SKILL.md → 本指南 3/5/6/7 章
查 API ：camera_vision_system_v3_API分析报告.md / 系统环境与非视觉官方库探测报告.md
查骨架 ：本指南 13.1 → 对应 .py + 项目说明文档
排障   ：本指南 14 章 → logs/ → 对应项目说明文档"常见问题"
```

---

## 14. 故障排查速查表

| 现象 | 原因 | 处置 |
|---|---|---|
| `ioctl(VIDIOC_QBUF): Bad file descriptor` | 与 SDL2 抢 V4L2 / 全托管模式下用 cv2 | 按第 5 章选模式；全托管禁用 cv2 |
| 启动十几秒才出界面 + `Camera index out of range (expected: index < 32)` | `cv2.VideoCapture` 传了 int，FFMPEG 后端越界 | 改 `cv2.VideoCapture('/dev/videoN', cv2.CAP_V4L2)` |
| V4L2 `Not a video capture device` | 打开到 `/dev/video41` 等无有效帧/元数据节点 | 按 `40→41→42` 顺序 + 读帧做 `gray.mean()` 有效性验证，跳过无效节点 |
| 摄像头打不开 / 画面不动 | 节点编号变了（换扩展板 USB 口会变）或外设开关没拨左 | ① 右下角**两位开关拨到左侧**（启用外设，**不一定能解决**）；② 换扩展板另一个 USB 母口试；③ 跑 `探测工具/探测_待定项核对.py` 打印每个候选的 `exists/opened/mean`，按实测结果调整顺序 |
| 管理器提示"没有摄像头"但设备已插 | 管理器**不显示节点号**，只能说明没识别到 | 同上三步；管理器提示本身不给出 `/dev/video4x` 编号 |
| ESP32 扩展板连不上 / `board.start()` 返回 False | 串口路径随批次不同（`/dev/ttyS9` 内部 UART 或 `/dev/ttyCH341USB*` USB 串口） | 代码用 `board.start()` 自动探测、**不硬编码**；先确认右下角开关拨左（启用外设），再按第 15 章命令看 `ls /dev/tty*` |
| 检测结果全空 | 漏调 `_init_detectors()` | 严格按 7 步，第 4 步必调 |
| 颜色识别每帧报「无效的区域坐标」 | 用了 1280×720 坐标 | 改 640×480（x+w≤640, y+h≤480） |
| 色块中心恒为 (0,0) | V3 库 bug | 用 position 自己算 |
| 表情 engagement 恒 Engaged | 语义不是"专注" | 用 emotion 8 分类 + face_position |
| `pygame` 初始化崩溃/音频异常 | 用了 `pygame.init()` | 分段 `display.init()` + `font.init()`；mixer 用 try/except |
| 语音播报无声且无报错 | mixer 重复 init/quit | 全生命周期只 init 一次 |
| `'utils' is not a package` / `ppocr_system` 导入失败 | `text_recognition` 在 cv2/pygame/V3 之后导入 | 调整 import 顺序（第 4 章） |
| OCR 在摄像头打开后不可用 | `TextRecognizer()` 实例化太晚 | 实例化放在开摄像头之前 |
| 底部状态文字被裁剪 | 窗口高度不足 | 640×480 画面用 ≥620 高 |
| `AttributeError: ... has no attribute 'delete_face'` | 调了不存在的接口 | 单条删除只删 JSON 行；清库用专用脚本 |
| `TypeError: unexpected keyword argument 'name'` | 物体接口参数名错 | 用 `class_name=` |
| `get_object_name()` / `get_object_recognition_count()` 不存在 | 方法名错 | 用 `get_object_recognition_class_name()` / `get_object_recognition_success()` |
| `open_camera(40)` 报 takes exactly 1 positional argument | `open_camera()` 不接受参数 | 用 `open_camera()`，ID 由 BackupCameraIds 探测 |
| 人头/物体"丢失" | 换工作目录，相对路径的库找不到 | 固定在 `user/` 下运行 |
| VoiceAPI HTTP 401 | token 过期，无自动刷新 | 重新 `VoiceAPI.get_token(user, password)` |
| AudioPlayer 无法暂停/停止/调音量 | 官方库无这些接口 | 改用 `pygame.mixer` |
| 终端把正常日志标红「[错误]」 | 好搭AI派把所有 stderr 标红 | 用 `StreamHandler(sys.stdout)` + stderr 重定向 + `propagate=False` |
| 程序打不开/点运行没反应 | 上一个程序没关掉 | 先按停止（F6），再运行 |

---

## 15. 设备实测核验（已完成，2026-10-09）

> ✅ **本节核验已于 2026-10-09 在设备上执行完毕**，结论见 `project_memory.md`「口径决议记录」与本指南 §1.2~§1.4 的定案值。下列命令作为**复核手段**保留，供以后换板、换内核或换摄像头时重跑：把 `探测工具/探测_待定项核对.py` 复制到设备 `/home/cxdz/jupyter/user/`，执行
> `cd /home/cxdz/jupyter/user && PYTHONPATH=/home/cxdz/jupyter/lib python3 探测_待定项核对.py`
> 结果在 `logs/探测_待定项核对_YYYYMMDD_HHMMSS.log`，末尾有 `N. 结论速览` 的 `KEY | VALUE` 清单。
> **目测项（IO 数量、ADC 路数、开关、充电口、插口、屏幕、WS2812、巡线、键鼠、网络、USB 下载、电源键、管理器提示）已在 §1.4 由你确认完毕**，无需再测。

设备上执行（SSH `cxdz@192.168.0.109`，密码/DISPLAY 按现场）：

```bash
# 1) 串口真相：ESP32 双路径（ttyS9 内部 UART / ttyCH341USB*）均可打开
ls -l /dev/ttyS* /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
dmesg | grep -iE "ttyS9|ch341|cp210|ftdi|febc0000.serial" | head -20
python3 - <<'PY'
import serial
for p in ('/dev/ttyS9','/dev/ttyCH341USB0','/dev/ttyCH341USB1'):
    try:
        s=serial.Serial(p,115200,timeout=.5); print(p,'OK'); s.close()
    except Exception as e:
        print(p,'FAIL',e)
PY

# 2) opencv 发行包真相（contrib 还是普通版）
python3 -c "import cv2;print(cv2.__version__, cv2.__file__)"
python3 -m pip list 2>/dev/null | grep -i opencv
python3 -c "import cv2;print('xfeatures2d',hasattr(cv2,'xfeatures2d'))"

# 3) 摄像头节点核验（已定案顺序 40→41→42，此处仍把 43 一并打印便于对比）
ls -l /dev/video4* 2>/dev/null
v4l2-ctl --list-devices 2>/dev/null || true
python3 - <<'PY'
import cv2, os
for n in (40,41,42,43):          # 40→41→42 为已定案优先顺序
    p='/dev/video%d'%n
    exists = os.path.exists(p)
    c=cv2.VideoCapture(p, cv2.CAP_V4L2) if exists else None
    ok=bool(c and c.isOpened())
    mean=None
    if ok:
        for _ in range(5):
            r,f=c.read()
            if r and f is not None:
                mean=float(f.mean()); break
    print(p,'exists=',exists,'opened=',ok,'mean=',mean)
    if c: c.release()
    c.release()
PY

# 4) ESP32 引脚常量与 ADC 通道数
python3 -c "import ESP32 as m;print([x for x in dir(m) if x.startswith(('GPIO_IO','ADC_IO','GPIO_BUTTON'))])"

# 5) AudioPlayer 真实方法名
python3 -c "import audio_player as a;print([x for x in dir(a.AudioPlayer) if not x.startswith('_')])"

# 6) 版本三件套
python3 -V; python3 -c "import pygame;print(pygame.version.ver)"; python3 -c "import numpy;print(numpy.__version__)"
```

本节结果已回传落盘，本指南所有原"待核验"条目均已定稿（见 §1.2~§1.4 与 `project_memory.md`「口径决议记录」）。

---

## 16. 一页速记

```
Python 3.8.10 ｜ cv2 5.0.0 ｜ pygame-ce 2.5.2 ｜ RK3588S ｜ 无 Swap
OS 环境变量第一行：os.environ['LIBGL_ALWAYS_SOFTWARE']='1'（现有代码多用 setdefault）
import 顺序：os.environ → text_recognition(OCR) → pygame → cv2 → numpy → V3
pygame：推荐 display.init() + font.init()；需音频时 try: mixer.init() 且只 init 一次
摄像头：用 cv2.VideoCapture('/dev/videoN', cv2.CAP_V4L2)；顺序【40→41→42】+ 每步 gray.mean() 帧验证（实测首个可用 /dev/video40；节点编号随插拔变化，缺了就跳过）
V3 七步：create(basic=False,advanced=False) → open_camera() → enable_XXX（只有 13 个真名） → _init_detectors() → regions(640×480) → start_background_detection() → refresh_results()
读结果：先 refresh_results()；回调 ≈8 次/秒；engagement 别信；color_block center 自己算；face_id 成功 str/无人脸 None
数据：face_database/face_records.json、object_database/object_records.json；object_data/ 禁用；
      人脸无 delete_face（不存在）；物体的 delete_object_recognition_class 只用于清库
硬件：ESP32 数字 IO 8 个(GPIO_IO_01~08)、ADC 8 路(8 个口都能当 ADC)；无板载按键；串口双路径(/dev/ttyS9 与 /dev/ttyCH341USB0/1 均可)，一律 board.start() 自动探测
      摄像头插扩展板 USB 母口(共 2 个，任选，换口会变节点号)；2 个 USB 母口也可插键盘鼠标
      右下角两位开关：左=启用外设，右=充电；充电口是独立 Type-C；WS2812 默认 10 灯(IO1~IO8 任选)
      巡线模块外接 I²C 4 线 4 探头；USB 下载程序不可用(走 IP)；自动关机阈值 10%，长按电源键可重启
日志：logs/<程序名>_YYYYMMDD.log（扩展名已统一 .log），追加写，stdout 分路，别让终端标红
UI：默认 1920×1080 横屏【窗口模式】，最大 1920×1280；字体绝对路径 /home/cxdz/jupyter/assets/；图标 icons/；图片 images/（默认 1.jpg）
```
