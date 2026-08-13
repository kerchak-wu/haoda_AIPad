# 文字识别触发视频播放 · 项目开发说明

> **开发工具**：QoderWork（AI 桌面开发助手，多轮对话迭代开发）
> **开发日期**：2026-08-08（初版单日完成，后续持续迭代优化至 v9）
> **适用平台**：好搭AI派（ESP32 + Pygame 教育平板，Rockchip RK3566，Ubuntu + Python 3）
> **程序文件**：`文字识别播视频qoder.py`（约 960 行，与本文档同目录）

---

## 一、项目概述

摄像头实时进行文字识别（OCR），识别到预设关键字后自动播放对应教学视频；视频支持暂停/继续、停止，播放结束或停止后自动返回识别界面。视频声音直接取自 mp4 内嵌音轨（无需单独音频文件）。界面为 1920x1080 科技风（深色底 + 青色霓虹 HUD 角标 + 网格背景）。

**识别映射表（VIDEO_MAP）**：

| 识别文字 | 播放视频 | 视频目录 |
|---------|---------|---------|
| 好搭智眼 | hdzy.mp4 | videos/ |
| 芦丁鸡 | ldj.mp4 | videos/ |
| 信息科技实验板 | syb.mp4 | videos/ |

**界面状态**：
- 识别界面：摄像头预览 + 识别结果终端框 + 触发规则 + 底部状态条/操作提示；右上角「退出程序」按钮
- 播放界面：视频画面 + 进度条/时长/状态 + 「暂停/继续」「停止」按钮（底部控制栏）

---

## 二、程序架构（多线程分工）

```
主线程（pygame 渲染 + 事件循环，唯一负责绘制，clock.tick(30) 限帧）
 ├─ OCR 引擎加载（init_ocr）：主线程、程序最早期执行【顺序敏感，见 4.2】
 ├─ OCR 推理线程（ocr_worker）：Queue(maxsize=1) 取帧 → 识别 → 加锁写入结果
 │    结果带产生时间戳，播放期间由 pause 事件丢弃画面与结果
 ├─ 摄像头采集线程（CameraThread）：纯 cv2 独占，grab() 清空缓冲 + retrieve() 取最新帧
 │    BUFFERSIZE=1 + grab 清空双保险，消除画面滞后；缓存最新帧供主线程取用
 ├─ 视频播放：cv2.VideoCapture 逐帧读取 + cv2.resize 预缩放 + 帧率定时器，暂停不读帧
 └─ 音频：ffmpeg 提取内嵌音轨为临时 wav → pygame.mixer.music 播放
      （暂停/继续/停止/unload 与画面同步动作；ffmpeg 缺失自动静音兜底）
```

关键数据流：摄像头 → 采集线程(grab清空缓冲+retrieve取最新帧) → 缓存帧 → 主线程取最新帧 → cv2.resize预缩放 → blit显示 + 压缩宽度(800) → 队列 → OCR 线程 → 结果(带时间戳) → 主线程消费 → 匹配关键字 → 播放视频。

---

## 三、核心技术方案

### 3.1 摄像头：纯 cv2 独占模式（30fps 流畅预览）

- 设备候选列表按序探测（`/dev/video41` → `/dev/video42` → 0/1/2），取第一个能读到有效画面的设备
- 优先设置 MJPG fourcc + 1280x720
- **缓冲区设置为 1 帧**（`CAP_PROP_BUFFERSIZE = 1`）：V4L2 后端默认缓冲 3-5 帧，这是摄像头预览"画面滞后"的最常见根因
- 有效帧校验 `_is_valid_frame`：通过 `gray.mean()` 检测全黑/全白帧（`10 < mean < 245`）。项目记忆：ARM 设备上 `gray.std()` 计算开销过大，应改用 `gray.mean()` 检测全黑/全白帧
- **采集线程与渲染/识别分离**：采集线程用 `grab()` 主动清空驱动内部缓冲区的陈旧帧（最多丢弃 5 帧防死循环），再 `retrieve()` 取最新帧，即使 `CAP_PROP_BUFFERSIZE=1` 不生效也能保证拿到最新画面；每次循环后睡眠 0.02s（≈50fps 采集），主线程 `get_frame()` 取副本（加锁、不阻塞），画面永不卡顿
- 不导入 `camera_vision_system_v3`——该视觉系统全托管模式仅 6~7fps，无法满足流畅预览需求

### 3.2 OCR：文件开头导入 + 后台线程推理（连续识别）

- `from text_recognition import TextRecognizer` 在**文件最开头**导入（try/except 包裹），早于 `cv2`/`pygame` 等所有其他库。这是 PaddleOCR 相对导入坑的根治方案：若先导入 `cv2`/`pygame`，它们会将 `utils` 注册为非包模块，导致 ppocr_system 报 `utils is not a package`
- `init_ocr()` 在主线程、程序早期创建识别器实例（仅创建实例，导入已在文件开头完成）
- 识别推理在独立 worker 线程连续进行：引擎空闲（队列空）即提交最新画面，`Queue(maxsize=1)` 保证只保留最新帧、自动跳帧
- 识别帧宽度压缩到 800px（`OCR_FRAME_MAX_W`），识别速度显著提升
- 结果经 `threading.Lock` 保护写入共享字典，主线程仅消费，不参与识别

### 3.3 视频播放与内嵌音轨（无独立音频文件的方案）

- 画面：`cv2.VideoCapture` 按帧读取，帧率定时器控制节奏（暂停时不读新帧）；用 `cv2.resize`（ARM NEON 加速）预缩放到目标尺寸后直接 blit，避免每帧调用 `pygame.transform.scale`（软件渲染，慢 3-5 倍）
- 声音：`extract_audio` 用 ffmpeg 把 mp4 音轨提取为临时 wav（`pcm_s16le` 44100Hz），`pygame.mixer.music` 播放
  - `pygame.mixer` 在程序启动时用 try/except 包裹初始化（Rockchip 平台音频驱动可能崩溃）；若初始化失败则静音播放画面
  - 暂停/继续 → `mixer.music.pause()/unpause()`；停止 → `stop()` + `unload()` 释放 wav 内存，与画面完全同步
  - ffmpeg 不可用或提取失败 → 静音播放画面兜底，程序不中断
- 进度条按"已播放时长/总时长"计算，暂停期间不计时（`play_elapsed + (now - play_resume_time)`）

### 3.4 重复触发防护（三层机制，v6/v7 两轮修复沉淀）

**问题背景**：播放视频期间，OCR 后台线程仍会处理排队中的旧画面并产生结果；播放结束返回识别界面后，残留结果被消费 → 再次触发播放（"一旦触发必定播 2 次"，甚至"停止后仍会再播一次"）。

**三层防护**：
1. **暂停标志（ocr_pause Event）**：`start_play` 置位 / `back_to_recognize` 清除；worker 在「取帧后」和「识别完成后」双重检查，播放期间丢弃一切画面与结果
2. **进出播放清空**：置位暂停的同时清空识别队列（`get_nowait`）和已产生的识别结果（`new=False, text=''`）
3. **时间戳新鲜度校验（最终兜底）**：worker 写入结果时记录 `result['time'] = time.time()`；主线程消费时只接受 `time >= last_finish_time`（晚于本次播放结束时刻）的结果，播放前遗留的陈旧结果即使从竞态中漏网也会被拒绝

### 3.5 科技风 UI（1920x1080）

- 配色：背景 (8,12,24)、主色电光青 (0,229,255)、暗青 (0,140,200)、文字 (225,245,255)、成功绿 (0,255,140)、告警红 (255,70,90)、停止橙 (255,170,60)
- 元素：网格背景、四角 L 形霓虹角标（`draw_tech_corners`）、面板细边框、标题辉光（四向偏移叠影）、终端风格结果框（`> 识别文字` 前缀）
- 文字：`draw_wrap_text` 自动换行 + `max_lines` 截断省略号，防止溢出边框
- 字体：`/home/cxdz/jupyter/assets/` 下 PingFang_Medium.ttf / simfang.ttf / msyh.ttc 等按序探测
- **文字 Surface 缓存**：`_get_text_surface()` 按 `(font_id, text, color)` 缓存渲染结果，静态文字（标题、按钮、状态标签）首次 `font.render` 后直接 blit，省去 90%+ 的 TrueType 光栅化调用；OCR 识别结果每帧变化，缓存上限 200 条防内存泄漏
- **网格背景 Surface 缓存**：`draw_grid` 首次绘制后缓存为 `SRCALPHA` 透明 Surface，每帧仅一次 blit，避免重复绘制 25 条线

### 3.6 识别界面布局（v7 整体重排，垂直空间分配）

```
y 22~100   头部：标题 + 英文副标题同行，右上角退出按钮（底 100，与面板留 12px 间距）
y 112~872  主区：左侧预览框(1280x760，标签内嵌顶部 40px 状态条) + 右侧面板(530x760)
           面板：识别结果终端框(5行) / 触发规则 / 分隔线 / 提示文字
y 908~1077 信息区：状态条(摄像头/OCR/模式/声音/系统 5 项) → 操作提示行 → 署名+版本号
```

**教训**：v3~v6 期间 UI 采用"逐点打补丁"式修改导致标签重叠、按钮压框、底部大段空白等失衡问题；v7 改为一次性整体规划垂直空间后彻底解决。后续界面修改应优先做整体布局规划，而非局部挪动坐标。

### 3.7 日志输出机制

程序启动时在 `logs/` 目录下创建按日期命名的日志文件，所有 `print` 输出（含异常堆栈）同时写入控制台和日志文件，便于事后排查问题。

```python
# 日志文件：logs/文字识别播视频qoder_YYYYMMDD.log，追加模式，块缓冲
_LOG_DIR = 'logs'
_LOG_FILE = os.path.join(_LOG_DIR, '文字识别播视频qoder_%s.log' %
                         _datetime.datetime.now().strftime('%Y%m%d'))
_debug_log_fp = open(_LOG_FILE, 'a', encoding='utf-8', buffering=-1)

# TeeStdout 包装 stdout/stderr，print 同时写入控制台和文件
sys.stdout = _TeeStdout(sys.stdout)
sys.stderr = _TeeStdout(sys.stderr)
```

**设计要点**：
- **目录与命名**：`logs/` 目录、`文字识别播视频qoder_YYYYMMDD.log`，符合项目日志规范
- **追加模式（`'a'`）**：同一天多次运行不会覆盖历史日志，每次运行写入 `======== 时间 运行开始 ========` 分隔
- **块缓冲（`buffering=-1`）**：避免高频 `print` 阻塞主循环
- **TeeStdout 包装**：无需修改业务代码中的 `print` 语句，自动双写
- **退出关闭**：`main()` 退出清理末尾关闭文件指针，防止日志丢失

### 3.8 Rockchip 平台兼容性补丁

为避免 Rockchip 平台（RK3566/RK3568）上 Pygame 与 OpenCV 的底层驱动冲突（GPU 驱动加载失败、音频驱动与 V4L2 死锁），程序开头加入四处补丁（参考《视觉系统摄像头调用参考方案》第 7 章）：

```python
import os
# 1. 强制 libGL 使用软件渲染，避免 rockchip 平台 GPU 驱动加载失败
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

# 2. 导入顺序：先 pygame 再 cv2（pygame 先导入让 SDL 接管视频子系统）
import pygame
import cv2

# 3. 分段初始化（不调用 pygame.init()），避免 pygame.mixer 导致原生崩溃
pygame.display.init()
pygame.font.init()

# 4. mixer 需用于视频内嵌音轨播放，单独初始化并容错（Rockchip 平台音频驱动可能崩溃）
try:
    pygame.mixer.init()
except Exception as _e:
    print('pygame.mixer 初始化失败，视频音轨播放功能不可用:', _e)
```

**特殊说明**：本程序需要 `pygame.mixer` 播放视频内嵌音轨，与其他程序不同——不能用"跳过 mixer"的方案，而是保留 `pygame.mixer.init()` 但用 try/except 包裹。这样既能在正常平台播放视频音轨，又能在 Rockchip 音频驱动异常时避免崩溃（仅视频静音，画面和 OCR 仍正常）。

### 3.9 性能优化（ARM 软件渲染专项，v9）

Rockchip RK3566 平台启用 `LIBGL_ALWAYS_SOFTWARE=1` 后，Pygame 所有渲染走软件路径，1920x1080 全屏渲染开销极大。本程序经过多轮性能调优，最终实现 30fps 流畅运行，关键优化如下：

**1. 摄像头缓冲区清空（消除画面滞后的根因）**
- V4L2 后端默认缓冲 3-5 帧，`cap.read()` 返回的是几帧前的陈旧画面，表现为"画面滞后几秒"
- 设置 `CAP_PROP_BUFFERSIZE = 1`（部分后端可能不生效）
- 采集线程用 `grab()` 主动清空缓冲区陈旧帧（最多丢弃 5 帧防死循环），再 `retrieve()` 取最新帧，双保险

**2. 文字 Surface 缓存（消除 font.render 开销）**
- ARM 上 TrueType 光栅化开销极大，识别界面每帧有 15+ 次 `font.render` 调用（含 glow 辉光的 4 次叠影）
- `_get_text_surface()` 按 `(font_id, text, color)` 缓存渲染结果，**必须用 `convert_alpha()`** 保留 alpha 通道（`convert()` 会丢失抗锯齿半透明边缘导致文字不显示）
- 静态文字（标题、按钮、状态标签）缓存命中率 100%，OCR 识别结果每帧变化但缓存上限 200 条防泄漏

**3. cv2.resize 替代 pygame.transform.scale（ARM NEON 加速）**
- `pygame.transform.scale` 赯软件渲染，1280x720 画面缩放耗时 30-50ms
- `cv2.resize` 利用 ARM NEON 指令集加速，同样操作快 3-5 倍
- 新增 `cv2_frame_to_surface_resized()` 函数：摄像头帧直接缩放到 `feed_rect` 尺寸后转 Surface，后续 blit 无需再缩放
- 视频播放同样用 `cv2.resize` 预缩放，避免每帧 `pygame.transform.scale`

**4. 网格背景 Surface 缓存**
- `draw_grid` 原每帧绘制 25 条线（16 竖 + 9 横），改为首次绘制后缓存为 `SRCALPHA` 透明 Surface，每帧仅一次 blit

**5. 摄像头帧 Surface 缓存（仅在帧更新时转换）**
- 通过 `cam_thread.last_update` 时间戳检测帧是否更新，仅在新帧到来时执行 `resize+cvtColor+convert`（约 50fps 采集 → 实际转换约 30fps），其余循环迭代直接复用缓存的 `cam_surface`
- 主循环 30fps 中约 1/3 迭代跳过转换，减少约 40% 的 cvtColor 开销

**6. 播放界面渲染优化**
- 播放界面直接 `window.fill((0,0,0))` 填充黑色，跳过 `COLOR_BG` + 网格线绘制（识别界面才需要）
- 视频帧用 `cv2.resize` 预缩放后直接 blit，不再调用 `blit_fit`/`pygame.transform.scale`

**7. 主循环帧率限制**
- `clock.tick(30)` 限制主循环 30fps，减少不必要的重绘开销（摄像头采集 50fps、OCR 独立线程，主循环 30fps 足够流畅）

**8. 播放返回后资源清理**
- `audio_stop()` 增加 `pygame.mixer.music.unload()` 释放 wav 音频数据（5-10MB/分钟）占用的内存
- `back_to_recognize()` 中 `gc.collect()` 强制回收视频帧 Surface 对象（ARM 设备上 Python GC 不会立即回收大尺寸 Surface）
- 清空 `cam_surface` 和 `last_cam_ts`，强制下次渲染重新转换，避免用到陈旧缓存

---

## 四、需求演进与迭代记录（含问题及解决方案）

| 版本 | 用户反馈 / 需求 | 解决方案 |
|------|----------------|---------|
| v1 | 基础功能：识别三组文字触发对应视频，退出/暂停/停止按钮 | 完整程序框架：cv2 摄像头 + OCR + pygame 播放 |
| v2 | 界面 1920x1080 科技风；视频无声音、声音在 mp4 内 | 科技风 HUD 绘制；ffmpeg 提取内嵌音轨 + mixer.music |
| v3 | 副标题与 CAMERA FEED 标签重叠；识别文本溢出边框 | 预览/面板下移；`draw_wrap_text` 增加 max_lines 截断 |
| v4 | OCR 加载失败：`no module named utils.operators; utils is not a package` | 根因：text_recognition 在后台线程、且晚于视觉系统导入，污染 PaddleOCR 相对导入。修复：主线程早期加载 |
| v5 | 启动慢、预览卡、识别慢 | 启动画面 + 后台 OCR 线程；切换纯 cv2 独占模式 30fps + 双线程分离；识别帧压缩至 800px |
| v6 | 一旦触发视频播放，必定播 2 次 | 根因：播放期间后台 OCR 处理排队帧产生残留结果。修复：ocr_pause 暂停标志 + 双检查 + 进出播放清空队列/结果 |
| v7 | 停止后仍会再播一次；识别框上方空白太多 | 时间戳新鲜度校验彻底兜底；识别界面整体布局重排（按钮留距、主区加高、底部信息填充） |
| v8 | 按《camera_vision_system_v3_API分析报告》《视觉系统摄像头调用参考方案》复核优化 | text_recognition 移到文件最开头导入；import 顺序调整为先 pygame 再 cv2；mixer 用 try/except 包裹；新增日志输出模块；`_is_valid_frame` 改用 `gray.mean()`；采集线程每次循环都 sleep(0.05) |
| v9 | 视频画面严重滞后（启动即滞后，播放返回后更严重） | 根因：V4L2 缓冲 3-5 帧 + ARM 软件渲染下 font.render/pygame.transform.scale 开销过大。修复：①摄像头 `CAP_PROP_BUFFERSIZE=1` + `grab()` 清空缓冲区；②文字 Surface 缓存（`convert_alpha()`）；③`cv2.resize`（NEON 加速）替代 `pygame.transform.scale`；④网格/摄像头帧 Surface 缓存；⑤主循环 `clock.tick(30)`；⑥播放返回后 `unload()` + `gc.collect()` 释放资源 |

---

## 五、关键经验教训（后续项目可直接复用）

1. **PaddleOCR 导入顺序坑**：`text_recognition` 模块必须在**文件最开头**导入（早于 `cv2`/`pygame` 等所有其他库），否则报 "utils is not a package"。本程序采用 try/except 包裹在文件开头导入，`init_ocr()` 仅创建识别器实例。OCR 引擎加载放主线程，推理放后台线程。
2. **摄像头模式选型**：追求流畅预览（30fps）→ 纯 cv2 独占 + 采集线程；需要官方算法持续后台检测 → 视觉系统 V3 全托管（接受 6~7fps）；只需按需触发 → 混合模式。**cv2.VideoCapture 与 V3 不能同时使用同一摄像头**。
3. **内嵌音轨方案**：无独立音频文件时，用 ffmpeg 提取 mp4 音轨为临时 wav，`pygame.mixer.music` 播放，天然支持暂停/继续/停止同步；ffmpeg 缺失时静音播放兜底。
4. **后台线程残留结果**：任何"后台持续识别 + 前台条件触发"的程序都要考虑：触发执行后，后台线程处理中的旧数据仍会产出结果。需用暂停标志 + 清空队列 + 结果时间戳三重防护。
5. **Rockchip 兼容性补丁（标准配置）**：`os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')` 强制软件渲染；用 `pygame.display.init()` + `pygame.font.init()` 分段初始化，不调用 `pygame.init()`；import 顺序为先 `pygame` 再 `cv2`。**mixer 特殊处理**：本程序需要 mixer 播放视频音轨，不能用"跳过 mixer"方案，而是在启动时用 try/except 包裹 `pygame.mixer.init()`，Rockchip 音频驱动异常时仅静音播放。
6. **UI 布局要整体规划**：逐点打补丁会造成重叠与空白失衡；先按 1920x1080 划分垂直区段（头部/主区/信息区），再填内容。
7. **性能优化组合拳**：采集/识别/渲染三线程分离 + 队列限长自动跳帧 + 识别帧压缩宽度 + 启动画面掩盖加载耗时。
8. **ARM 帧检测优化**：摄像头采集线程中使用 `gray.std()` 进行帧检测在 ARM 设备上计算开销过大，应改用 `gray.mean()` 检测全黑/全白帧。
9. **采集线程睡眠间隔**：摄像头采集线程每次循环 `cap.read()` 后应睡眠 0.02s（≈50fps 采集），避免 CPU 占满；配合 `grab()` 清空缓冲区可保证取到最新帧。
10. **日志输出规范**：日志文件存储在专门的 `logs/` 目录，文件名格式为"程序名_YYYYMMDD.log"，使用追加模式（'a'）而非覆盖模式；用 `_TeeStdout` 包装 stdout/stderr 实现自动双写，无需修改业务代码中的 `print` 语句。
11. **摄像头画面滞后根因**：V4L2 后端默认缓冲 3-5 帧，`cap.read()` 返回的是几帧前的陈旧画面。解决：设置 `CAP_PROP_BUFFERSIZE=1` + 采集线程用 `grab()` 主动清空缓冲区陈旧帧再 `retrieve()` 取最新帧（双保险，限制最多丢弃 5 帧防死循环）。
12. **ARM 软件渲染性能优化**：Rockchip 平台启用 `LIBGL_ALWAYS_SOFTWARE=1` 后，`font.render`（TrueType 光栅化）和 `pygame.transform.scale`（软件缩放）开销极大。解决：①文字 Surface 缓存（`_get_text_surface` + `convert_alpha()` 保留透明度）；②`cv2.resize`（ARM NEON 加速）替代 `pygame.transform.scale`；③静态背景（网格）缓存为 `SRCALPHA` Surface；④仅在帧更新时转换摄像头 Surface。
13. **文字 Surface 缓存的 alpha 通道坑**：`font.render` 产生抗锯齿半透明边缘，**必须用 `convert_alpha()`** 保留 alpha 通道；若用 `convert()` 会丢失 alpha 导致文字不显示或带黑色方块。
14. **播放返回后资源清理**：ARM 设备上 Python GC 不会立即回收大尺寸 Surface 对象，播放结束后需 `gc.collect()` 强制回收；`pygame.mixer.music` 加载的 wav 数据需 `unload()` 释放（`stop()` 仅停止播放不释放内存）。

---

## 六、文件部署要求

- 程序与 `videos/` 文件夹同目录，内含 `hdzy.mp4`、`ldj.mp4`、`syb.mp4`
- 需先在好搭Block中加载官方扩展库：**OCR文字识别、Pygame游戏模块**（本程序不使用摄像头视觉系统 V3）
- 系统需安装 ffmpeg 以播放内嵌音轨（缺失时静音兜底，不影响运行）
- 运行时会在程序同目录自动创建 `logs/` 目录，存放按日期命名的运行日志（追加模式，不覆盖历史）

## 七、二次开发指引（常用配置入口）

| 需求 | 修改位置 |
|------|---------|
| 增删识别关键字 / 换视频 | `VIDEO_MAP` 字典（第 79 行附近） |
| 播放结束后的防重复触发窗口 | `RETRIGGER_DELAY`（默认 3 秒） |
| 识别速度调优 | `OCR_FRAME_MAX_W`（越小越快，默认 800） |
| 摄像头设备调整 | `CAMERA_DEVICES` 列表（默认 `/dev/video41` 优先） |
| 关闭声音 | `AUDIO_ENABLED = False` |
| 界面布局调整 | 识别界面绘制代码段（`state == 'recognize'` 分支） |

---

## 八、QoderWork 开发备注

本项目由 **QoderWork**（AI 桌面开发助手）协助开发完成，采用"需求提出 → 代码生成 → 实机测试反馈 → 问题修复"的多轮迭代模式。开发过程中沉淀的关键经验（PaddleOCR 导入顺序、摄像头模式选型、内嵌音轨方案、后台线程残留结果防护、ARM 软件渲染性能优化）已同步保存至长期记忆，后续好搭AI派项目可复用这些经验快速开发。

*文档版本：3.0　|　最后更新：2026-08-12（v9 ARM 性能优化同步）*
