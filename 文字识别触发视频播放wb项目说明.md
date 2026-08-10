# 好搭AI派 · 文字识别触发视频播放 — 项目说明文档

> **开发工具：WorkBuddy（AI 编程助手）** 🤖
> **项目状态**：已完成 ✅
> **开发日期**：2026-08-08
> **交付物**：`文字识别触发视频播放.py`（完整可运行程序）

---

## 目录

1. [项目概述](#一项目概述)
2. [功能需求（用户提示词全记录）](#二功能需求用户提示词全记录)
3. [系统架构与关键技术](#三系统架构与关键技术)
4. [开发迭代记录](#四开发迭代记录)
5. [使用说明](#五使用说明)
6. [常见问题与排查](#六常见问题与排查)
7. [可复用经验（供以后项目参考）](#七可复用经验供以后项目参考)
8. [项目元信息](#八项目元信息)

---

## 一、项目概述

本项目为好搭AI派（ESP32 + Pygame 平台）开发的一款**文字识别触发视频播放**应用：

- 摄像头持续进行 OCR 文字识别，识别到指定关键词自动播放对应视频；
- 带完整 Pygame 交互界面（1920×1080 科技感 UI），识别界面与视频播放界面双界面切换；
- 视频播放支持**暂停/继续**（与声音联动）、**停止**、**进度条**，播完自动返回识别界面；
- 声音直接取自视频自带音轨（自动用 ffmpeg 提取），无需手动准备音频文件。

| 识别关键词 | 触发视频 |
|---|---|
| 好搭智眼 | `videos/hdzy.mp4` |
| 芦丁鸡 | `videos/ldj.mp4` |
| 信息科技实验板 | `videos/syb.mp4` |

---

## 二、功能需求（用户提示词全记录）

> 以下为开发过程中用户的全部原始提示词（按顺序），每条附对应的开发处理说明。

### 提示词 1（初始需求）

> 写一个文字识别触发视频播放视频的程序，识别到"好搭智眼"播放视频hdzy.mp4，识别到"芦丁鸡"播放视频ldj.mp4，识别到"信息科技实验板"播放视频syb.mp4。视频文件全部在videos文件夹下。识别界面有退出程序按钮，视频播放界面有暂停、停止按钮，点击暂停按钮视频播放暂停并且按钮变成继续，点击继续按钮继续播放。

**处理**：生成 v1 完整程序。核心实现——
- OCR：`TextRecognizer`（text_recognition 模块）+ 视觉系统 V3 全托管取帧；
- 关键词 → 视频映射表 `VIDEO_MAP`，子串匹配触发；
- Pygame 双界面：识别界面（退出程序按钮）+ 视频播放界面（暂停/继续、停止）；
- 暂停状态变量 `paused` 控制按钮文字在"暂停/继续"间切换。

### 提示词 2（Bug 反馈）

> 报错：line222，if trigger_video: unboundlocalerror: local variable "trigger_video' refrenced before assignment. terminate called without an active exception

**处理**：修复 UnboundLocalError。根因：`main()` 函数体内存在 `trigger_video = None` 赋值语句，Python 将 `trigger_video` 判定为函数局部变量，导致循环开头读取时报"引用前未赋值"。修复：在 `main()` 顶部补全 `global running, in_video, trigger_video, ocr_text_display, display_frame_cache`。`terminate called without an active exception` 是 Pygame/SDL 的 C++ 层随 Python 异常退出抛出的伴随提示，修掉 Python 异常即消失。

### 提示词 3（界面升级 + 卡顿修复 + 声音需求）

> 界面1920*1080，识别界面时间长了会 卡住，识别界面视频画面不用占满整个界面，视频播放界面也是，可以留空，整个界面要有科技感。视频播放没有声音。

**处理**：v2 大版本升级——
- 窗口升级 1920×1080，深色网格**科技感 UI**（青色 #00C8FF 主色、面板四角角标、发光标题、按钮悬停高亮）；
- **卡顿修复三招**：
  1. **脏帧机制**：画面加版本号 `frame_version`，仅版本变化时才做 `resize + cvtColor + make_surface`，主循环其余帧只 blit 缓存 Surface；
  2. **OCR 降频**：识别线程 `time.sleep(0.3)`，识别频率约 1.5~2 秒/次；
  3. **背景预渲染**：`create_background()` 网格背景只生成一次；
- 布局留空：摄像头画面居中 1280×720、视频画面居中 1600×800，四周留空放左右信息面板（识别目标/系统状态）与底部识别栏；
- 声音方案（v2 初版）：`pygame.mixer.music` 播放 `recordings/` 同名 mp3。

### 提示词 4（声音方案调整）

> recordings下没有同名音轨，声音在视频文件里

**处理**：v3 声音方案改为三级降级——
1. 优先使用 `recordings/` 下同名音轨（`xxx.mp3` / `xxx.wav`）；
2. 无同名音轨时，自动用 `ffmpeg` 从 mp4 提取音轨（`-vn -acodec pcm_s16le -ar 44100 -ac 2`），缓存为 `recordings/xxx_tmp.wav`（二次播放秒开）；
3. ffmpeg 不可用或视频无音轨 → 无声播放，程序照常运行。
另在 `play_video` 开头加"正在加载视频..."提示画面，避免提取音轨时界面空白。

### 提示词 5（按钮位置调整）

> 退出程序按钮放到右上角，不要跟其他字重叠

**处理**：v4 微调——`BTN_EXIT` 从右下角 `(WINDOW_W-300, 960, 250, 70)` 改为右上角标题栏内 `(WINDOW_W-310, 18, 280, 52)`；原右上角"识别中"状态指示移到标题文字右侧（512, 44），形成"标题 → 状态指示 → 退出按钮"三段横向布局，互不重叠；删除原底部退出按钮。

### 提示词 6（当前）

> 程序完成。整理一个项目说明文档，供以后项目开发参考。要包括所有提示词。要备注是用workbuddy开发的。

**处理**：生成本文档（本说明文档）。

---

## 三、系统架构与关键技术

### 3.1 总体架构（三模块协同）

```
┌────────────────────────────────────────────────────────┐
│                     Pygame 主线程 (UI)                  │
│  识别界面（1920x1080）⇄ 视频播放界面                     │
│  事件处理 / 脏帧绘制 / 按钮交互 / 视频帧显示              │
└───────────────────────┬────────────────────────────────┘
                        │ 共享全局状态
┌───────────────────────▼────────────────────────────────┐
│              OCR 识别线程（daemon）                      │
│  capture_frame() → 更新画面缓存+版本号 → OCR 识别        │
│  → 关键词匹配 → 设置 trigger_video / trigger_audio       │
└───────────────────────┬────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────┐
│   视觉系统 V3（全托管模式，独占摄像头硬件）                │
│    open_camera + start_background_detection             │
└────────────────────────────────────────────────────────┘

视频播放：cv2.VideoCapture 读本地 mp4（不碰摄像头硬件）
音频播放：pygame.mixer.music（ffmpeg 提取音轨或同名音轨）
```

### 3.2 关键技术点

| 技术点 | 说明 |
|---|---|
| **视觉系统 V3 全托管** | `create_vision_system_v3(camera_id=-1, 1280x720)` + `open_camera()` + `start_background_detection(show_preview=False)`，OCR 用 `capture_frame()` 取帧。**全程禁止 `cv2.VideoCapture` 再开摄像头**（避免 V4L2 资源冲突） |
| **OCR 识别** | `TextRecognizer().recognize_text(frame, confidence_threshold=0.5)`，识别文本清理空格/换行/全角空格后做子串匹配 |
| **多线程 + 全局状态** | OCR 线程与 UI 主线程共享 `running / in_video / trigger_video / trigger_audio / ocr_text_display / display_frame_cache / frame_version`；**函数内出现赋值就必须在函数开头 `global` 声明** |
| **脏帧机制** | 摄像头帧只在 `frame_version` 变化时转换一次 Surface，UI 主循环零重活，解决长时间运行卡顿 |
| **双界面状态机** | 主循环检测 `trigger_video` 非空即切入视频界面；视频播完/停止/退出后 `in_video=False`、重置触发值，回到识别界面继续识别 |
| **视频播放** | `cv2.VideoCapture` 打开本地 mp4；暂停时停止 `read()` 保留当前帧；播放进度 `get(CAP_PROP_POS_FRAMES) / get(CAP_PROP_FRAME_COUNT)` |
| **音频三级降级** | 同名音轨 mp3/wav → ffmpeg 提取缓存 wav → 无声播放；暂停/继续用 `pygame.mixer.music.pause()/unpause()` 与视频联动 |
| **Rockchip 兼容补丁** | `os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')` + pygame 分段初始化（`display.init()` + `font.init()`，**不调用 `pygame.init()`**），避免 Mali GPU 驱动缺陷与音频/V4L2 死锁 |
| **中文字体** | `/home/cxdz/jupyter/assets/simhei.ttf`（好搭AI派自带字体目录） |

### 3.3 文件目录规范

| 内容 | 位置 |
|---|---|
| 程序文件 | 设备根目录（或对应文件夹） |
| 视频文件 | `videos/`（hdzy.mp4 / ldj.mp4 / syb.mp4） |
| 音频文件 | `recordings/`（可选同名音轨；自动提取缓存 `xxx_tmp.wav`） |
| 中文字体 | `/home/cxdz/jupyter/assets/` |

---

## 四、开发迭代记录

| 版本 | 时间 | 主要变更 |
|---|---|---|
| v1 | 2026-08-08 | 初始完整程序：OCR 识别触发视频播放，识别界面 + 视频播放界面（暂停/继续、停止） |
| v1.1 | 2026-08-08 | 修复 `UnboundLocalError`（补全 `main()` 的 global 声明） |
| v2 | 2026-08-08 | 1920×1080 科技感 UI；脏帧机制 + OCR 降频 + 背景预渲染修复卡顿；画面留空布局；视频加声音（同名 mp3） |
| v3 | 2026-08-08 | 声音改为三级降级：同名音轨 → ffmpeg 从视频自动提取 → 无声；加"正在加载视频"提示画面 |
| v4 | 2026-08-08 | 退出程序按钮移至右上角标题栏内，状态指示左移避免重叠 |
| 完成 | 2026-08-08 | 整理项目说明文档（本文档） |

---

## 五、使用说明

### 5.1 部署步骤

1. 通过好搭Block（IP 网络连接或 USB）把 `文字识别触发视频播放.py` 下载到好搭AI派；
2. 将 `hdzy.mp4`、`ldj.mp4`、`syb.mp4` 导入到设备 **videos** 文件夹；
3. 连接 USB 摄像头，好搭AI派右下角开关拨到**左侧**（启用外设）；
4. 运行程序，把写有"好搭智眼 / 芦丁鸡 / 信息科技实验板"的卡片对准摄像头即可触发。

### 5.2 界面操作

- **识别界面**：右上角【退出程序】按钮退出；底部显示实时识别文字；左侧面板显示识别目标列表；右侧面板显示系统状态（运行时长等）；
- **视频播放界面**：【暂停/继续】按钮（暂停后变"继续"，与声音联动）、【停止】按钮、播放进度条；视频播完自动返回识别界面。

### 5.3 声音说明

- 有同名音轨（`recordings/hdzy.mp3` 等）优先使用；
- 无同名音轨时自动 ffmpeg 提取视频自带声音，缓存 `recordings/xxx_tmp.wav`，第二次播放秒开；
- 首次播放某视频会等待 1~3 秒提取音轨（界面有加载提示）。

---

## 六、常见问题与排查

| 问题 | 原因 | 解决方法 |
|---|---|---|
| `UnboundLocalError: local variable referenced before assignment` | 函数内有赋值却未声明 `global` | 函数开头补全 `global` 声明（本项目踩坑点） |
| `terminate called without an active exception` | Pygame/SDL C++ 层随 Python 异常退出抛出的伴随提示 | 修掉 Python 异常即消失，非独立问题 |
| 识别界面长时间运行卡顿 | 主循环每帧重复做图像转换 + OCR 高频识别 | 脏帧机制 / OCR 降频 / 背景预渲染（本项目已内置） |
| 视频无声 | 无同名音轨且 ffmpeg 不可用；或视频本身无音轨 | 确认设备有 ffmpeg；或手动放置同名 mp3/wav |
| 音频播放导致程序崩溃 | Rockchip 平台音频驱动与摄像头 V4L2 冲突 | 注释掉 `play_video()` 中 `pygame.mixer` 相关代码改无声播放 |
| 摄像头打开失败 | 未连接 / 开关未拨到左侧 / 线材问题 | 检查设备界面底部摄像头状态（应显示 `/dev/video40` 等） |
| OCR 识别不到关键词 | 光线、角度、文字大小、字体 | 调整卡片位置与光照；识别文字过大过小都会降低准确率 |

---

## 七、可复用经验（供以后项目参考）

1. **多线程共享状态必须显式 `global`**：只要函数体内出现对共享变量的赋值，就必须在函数开头声明 `global`，否则读取在前时必然 UnboundLocalError；
2. **视觉系统 V3 全托管模式下禁用 `cv2.VideoCapture` 开摄像头**：摄像头硬件由 V3 独占，但**播放本地视频文件不受限制**；
3. **Pygame 界面刷新用脏帧机制**：图像转换（resize/cvtColor/make_surface）开销大，只在数据版本变化时做一次，主循环其余时间 blit 缓存，可显著提升长时间运行稳定性；
4. **背景/静态元素预渲染**：网格、边框等不变元素只渲染一次存 Surface，避免逐帧绘制；
5. **Rockchip 兼容补丁是标配**：`LIBGL_ALWAYS_SOFTWARE=1` + pygame 分段初始化（不调 `pygame.init()`）；
6. **中文字体统一用系统路径**：`/home/cxdz/jupyter/assets/simhei.ttf`（其他可用字体见字体列表文档）；
7. **声音从视频提取用 ffmpeg 命令**：`ffmpeg -y -i in.mp4 -vn -acodec pcm_s16le -ar 44100 -ac 2 out.wav`，只解码音频流速度快，适合播放前提取；
8. **按钮/面板坐标集中在顶部常量区**：`BTN_EXIT`、`PANEL_L` 等常量集中管理，便于布局微调（本项目多次调整均只改常量）；
9. **OCR 匹配前清理文本**：去空格/换行/全角空格再子串匹配，命中率显著提升；
10. **视频暂停 = 不调用 `read()`**：保留当前帧显示即可；进度条用 `get(CAP_PROP_POS_FRAMES)` 随时可取。

---

## 八、项目元信息

| 项目 | 内容 |
|---|---|
| 项目名称 | 好搭AI派 · 文字识别触发视频播放 |
| **开发工具** | **WorkBuddy（AI 编程助手）** |
| 开发平台 | 好搭AI派（ESP32 + Pygame）/ Ubuntu / Python 3.8+ |
| 核心依赖 | opencv-python、pygame、text_recognition、camera_vision_system_v3、ffmpeg |
| 交付物 | `文字识别触发视频播放.py` |
| 关联文档 | 好搭AI派学习手册.md / 好搭AI派范例代码.md / 好搭AI派可用字体列表.txt / 视觉系统摄像头调用参考方案.md |

---

*文档由 WorkBuddy 生成 · 2026-08-08*
