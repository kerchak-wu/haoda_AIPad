# project_memory · 好搭AI派默认约定集 + 索引

> **定位（2026-10-09 修订）**：本文件**不是**唯一 / 单一信源，而是「**默认约定集 + 索引**」，供新项目快速取默认值。
> **权威顺序（A0 最高）**：用户裁决 + 设备实测 > 两份基线报告（`系统环境与非视觉官方库探测报告.md`、`camera_vision_system_v3_API分析报告.md`）> 现有可运行代码 > 本文件 / `haoda-aipai-dev_SKILL.md` > 其他文档。
> 每条口径的定案依据见文末「口径决议记录」。

## Hard Constraints
- SoC: **Rockchip RK3588S**（device-tree: rockchip,rk3588s-tablet-f12-v11），**NOT RK3566**。CPU = 4×Cortex-A76 + 4×Cortex-A55 大小核异构；GPU = Mali-G610 MP4；NPU = 6 TOPS @ INT8（3 核），支持 INT4/INT8/INT16/FP16。板载显示屏原生 = 8 寸 1200×1920 竖屏（DSI-1），运行时横向 1920×1200
- **Default UI resolution: 1920×1080 landscape windowed (non-fullscreen)**. Do NOT adapt to native 1200×1920 unless explicitly required by the user. Accept the black bars on top/bottom; do not spend effort eliminating them. 窗口上限 **1920×1280**
- Only the main branch should be kept; all other branches must be deleted
- On rockchip platform, **prefer** the `camera_vision_system_v3` SDK for camera access to avoid V4L2 device-descriptor conflicts with SDL2; use `cv2.VideoCapture` **only in 纯 cv2 独占模式（模式 A：MediaPipe / dt-apriltags / 百度云等第三方算法）**, and only **after** the pygame display mode has been set — never bind the V3 SDK and `cv2.VideoCapture` to the same node at the same time
- All OpenCV (cv2) imports must come after pygame imports to prevent OpenGL initialization conflicts
- Set environment variable `LIBGL_ALWAYS_SOFTWARE=1` to force software rendering and avoid rockchip GPU driver errors; **must be set before ALL imports** (including `text_recognition`/`pygame`/`cv2`), otherwise PaddleOCR triggers Mali GPU driver loading on import, causing `libGL error: failed to create dri screen` / `failed to load driver: rockchip`
- Python version is locked to **3.8.10** (no other versions available on device). Any new dependency must support Python 3.8
- cv2 version is **5.0.0** (not 4.x) — the installed distribution is **`opencv-contrib-python 5.0.0.93`** (`xfeatures2d`/`face`/`ximgproc`/`aruco` all available, i.e. a contrib feature set). **Do NOT install, uninstall, or replace the existing OpenCV distribution** (a swap risks breaking these features / ABI). Verify API compatibility when using newer OpenCV features; fall back to v4-style calls if an error occurs
- AudioPlayer (official lib) has NO pause/resume/stop/volume control; if playback control is needed, use pygame.mixer or pyaudio directly instead
- VoiceAPI token auto-refresh does NOT exist; if HTTP 401 occurs, re-call `VoiceAPI.get_token(user, password)` instead of looking for `refresh_token`
- Use `pygame-ce` (Community Edition) instead of original `pygame` — they are mutually exclusive and cannot be installed simultaneously
- `pygame-ce` version must be fixed at **2.5.2** (newer versions ≥2.5.4 drop Python 3.8 support)
- Face & object data paths are **locked to V3 SDK database directories**: application-layer JSON mapping files must live inside the same folder as V3 SDK binary feature databases, never at project root. Standard layout: `face_database/face_records.json` (side-by-side with V3 face feature files) and `object_database/object_records.json` (side-by-side with V3 object feature files). `object_data/` is a historical leftover — never reference it.

## Engineering Conventions
- **所有新建/生成的 `.md` 文件必须使用 UTF-8 no BOM 编码**，禁止使用带 BOM 的 UTF-8 或其他编码
- Pygame init (calibrated 2026-09-12): use `pygame.display.init()` + `pygame.font.init()` (segmented init); add `try: pygame.mixer.init()/except` **only when audio is needed**, and init mixer **once per process** (repeat init/quit ⇒ silent playback with no error). `pygame.init()` is **not an error** — it never raises (failures are collected in its return value) — but it also brings up mixer/joystick/CDROM. This device's audio driver carries a documented exception / V4L2-deadlock **risk** (doc-level claim, no controlled experiment; 11 workspace programs call `pygame.init()`, 3 of them with a camera but none with audio, all working). **Camera + audio ⇒ segmented init is mandatory.**
- Camera initialization must occur after pygame display mode is set to prevent SDL2 from resetting V4L2 device descriptors
- Baidu API image parameters should be **explicitly specified per requirement**; the current working reference is `人脸表情识别（云算法）.py` (JPEG quality **85**, detection interval **1.5 s**). The old `160×120 / JPEG 60 / 5 s` figures are obsolete.
- ESP32 sensor reads have BUILT-IN retry: `__max_retry_count=3`, `__sync_timeout=2.0s`, plus `safe_operation()` wrapper. Do NOT wrap in another retry layer unless custom logic is required
- ESP32 async Callback APIs (8 methods: digitalReadCallback/analogReadCallback/dhtReadTemperatureCallback/dhtReadHumidityCallback/ds18b20ReadCallback/ultrasonicReadCallback/bmp280ReadPressCallback/bmp280ReadTemperatureCallback) are preferred over blocking reads when UI responsiveness matters
- USB webcam device node is **/dev/video40 / 41 / 42** (uvcvideo driver); detection order is **40 → 41 → 42**, each step verified by `os.path.exists` + `cv2.VideoCapture(node, cv2.CAP_V4L2)` + `gray.mean()` frame check (2026-10-09 measured: **first usable = /dev/video40**; video42 absent; video41 opens but yields no frame). **Node numbers change with port/enumeration — always re-probe on site.** Internal MIPI/ISP nodes occupy video0~video39 (skip; note `/dev/video0` can also return a frame on this unit but is not the webcam path). V3 `open_camera()` takes NO arguments (auto-detect via `CameraConfig.backup_camera_ids=[40,41,42,43]`)
- ESP32 connection: this unit exposes **BOTH** the internal UART **/dev/ttyS9** (febc0000, 1500000 baud) and the CH341 USB bridge **/dev/ttyCH341USB0 / /dev/ttyCH341USB1** (`lsmod` shows `ch341`); all three are openable. **Code must call `board.start()` and let it auto-detect — do NOT hard-code a node** (on 2026-10-09 `board.start()` actually connected via `/dev/ttyCH341USB1`). Do not hard-code `/dev/ttyS9`, nor `/dev/ttyUSB*` (ttyUSB* does not exist on this unit)
- text_recognition.TextRecognizer ONLY exposes `recognize_text(image_input, confidence_threshold=0.5)`; module-level `recognize_image_text()` and `extract_text_from_image()` are available for convenience; there is NO set_language/set_region/angle_classify support
- VoiceAPI provides TWO LLM backends: `llm_chat(text)` and `llm_chat_znbw_2025(text)`; prefer the latter for newer models unless older compatibility is required
- AudioRecorder default format is sample_rate=16000, channels=1, dtype='float32' — this matches VoiceAPI.voice_recognition() input requirements exactly; no resampling needed
- **CORRECT V3 INITIALIZATION FLOW (CRITICAL)**: Step 1: `create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)`; Step 2: `vs.open_camera()`; Step 3: `vs.detection_config.enable_XXX = True` for needed algorithms; Step 4: `vs._init_detectors()` (loads RKNN models); Step 5: For color_recognition: append regions with **640x480 coordinates** (actual processing resolution); Step 6: `vs.threaded_system.start_background_detection(show_preview=True)`; Step 7: `vs.result_accessor.refresh_results()` before reads
- **ALL log files MUST go to project-root `logs/` folder** — never in project root. Standard pattern: `_log_dir = 'logs'`; `os.makedirs(_log_dir, exist_ok=True)` before `open()`; LOG_FILE = `'%s/<程序名>_YYYYMMDD.log' % _log_dir`. Scattered `.txt`/`.log` files at project root are forbidden
- `pygame.display.set_mode()` window height must account for overlay text area (frame height + top/bottom UI rows); 640x480 frame needs ~640x620 window to avoid clipping status/gui
- **Face learning & recognition data flow (2-tier storage)**: Tier 1 (V3 SDK internal, auto-managed): `face_database/` (binary features), loaded by `learn_new_face()`, cleared by `clear_face_database()`. Tier 2 (application JSON): `face_database/face_records.json` (JSON array `[{name, face_info:{success,face_id,message}}]`), `face_id` is association key. Save: `os.makedirs('face_database', exist_ok=True)` before JSON access. Single delete: only remove the JSON row. **V3 has NO `delete_face`** — calling it raises `AttributeError` (the old "corrupts the model" warning came from an application-layer private implementation). Full wipe: use `清空人脸数据库.py` in order, must restart Python after
- **Object learning & recognition data flow (2-tier storage, symmetric to face)**: Tier 1 (V3 SDK internal, auto-managed): `object_database/` (binary features + classifier), loaded by `add_object_recognition_class/sample`. Tier 2 (application JSON): `object_database/object_records.json` (JSON array `[{name,sample_count,first_learned,last_learned}]`), `name` is association key. Save: `os.makedirs('object_database', exist_ok=True)` before JSON access. Single delete: only remove the JSON row. `delete_object_recognition_class` **exists** but is intended only for the official full-wipe tool (`清空物体数据库.py`, deletes classes one by one) — do NOT use it for routine single-row deletes. Full wipe: use `清空物体数据库.py` in order, must restart Python after

## Lessons Learned
- Using `cv2.VideoCapture` directly causes 'ioctl(VIDIOC_QBUF): Bad file descriptor' errors on rockchip due to SDL2 video subsystem interference
- V3 `color_recognition_regions` must use 640x480 coordinates (internal processing resolution), not 1280x720; out-of-range coordinates cause '无效的区域坐标' errors
- V3 facial expression `engagement='Engaged'` does NOT mean 'looking at screen'; use `emotion` (8-class) instead for meaningful state differentiation
- V3 detectors work when initialized correctly (previously empty due to missing `_init_detectors()` call)
- MediaPipe Hands (15-19 FPS) and cv2.QRCodeDetector are proven alternatives to V3 built-in detectors if needed
- V3 color_block `get_color_block_center()` always returns `(0, 0)` — compute manually from `get_color_block_position()`
- V3 callback system confirmed: detection and frame callbacks fire at the same rate; 2026-10-09 measured **46 callbacks / 6 s (≈8/sec)** with color+face enabled (rate varies with the number of enabled algorithms); frame callback receives `(ndarray(480,640,3), dict)`
- Deleting entire `face_database/` or `object_database/` is a NON-DESTRUCTIVE reset — V3 recreates directory on first write, only data loss
- `object_data/object_db.json` is a historical leftover (not present on this device, 2026-10-09); safe to delete; note it is still referenced by `好搭AI派基本情况.md` (to be corrected)
- If tier-2 JSON is lost but V3 tier-1 DB intact, reconstruct mapping by appending new rows with current user name when V3 returns existing `face_id`/`class_name`
- **LIBGL_ALWAYS_SOFTWARE import order trap**: `text_recognition` (PaddleOCR) must be imported before `pygame`/`cv2` (utils package conflict), but `LIBGL_ALWAYS_SOFTWARE=1` must be set before `text_recognition` — otherwise PaddleOCR import triggers Mali GPU driver loading. Correct order: `os.environ` → `text_recognition` → `pygame` → `cv2`. Found in 智慧阅读角.py, 文字识别播报器.py, 文字识别视频播放器.py, 文字识别播视频qoder.py (all fixed 2026-08-15)
- **Terminal [错误] red tag issue**: 好搭AI派 terminal marks ALL stderr output as red「[错误]」, even normal INFO from third-party libs (color_block_detector, PIL, ESP32, V3 SDK). Fix for programs using `logging`: ① `StreamHandler(sys.stdout)` instead of default stderr; ② redirect `sys.stderr` to a logger wrapper; ③ `logger.propagate = False` to prevent root logger bubble; ④ eliminate all `print(msg)` + `logger.info(msg)` dual output patterns

## 口径决议记录

> 规则：每条 = 结论 + 依据（A0 用户裁决 / A0 实测日志 / A1 基线 / A2 代码）+ 日期 + 核验方式。
> 本条的用途：**当下次有人质疑某条口径时，能立刻看到它是怎么定下来的、以及怎么复核。**
> 日志依据：`探测工具/logs_探测_待定项核对_20261009_084459.log`（2026-10-09 设备实测）。

| # | 条目 | 决议 | 依据层级 | 日期 | 核验方式 |
|---|---|---|---|---|---|
| 1 | 日志扩展名 | `.log` | A0 用户裁决 | 2026-09-12 | 用户确认；日志 B 节 `logs/` 直方图 8×`.log` vs 3×`.txt`（历史产物） |
| 2 | 摄像头候选顺序 | `40 → 41 → 42` + 每步 `os.path.exists`/`CAP_V4L2`/`gray.mean()` 帧验证（**D2 于 2026-10-09 修订**） | A0 用户裁决（2026-10-09 覆盖 D2） + 日志 D 节 | 2026-10-09 | 日志 D 节：video42 不存在、video41 打开无帧、首个可用 `/dev/video40` |
| 3 | 板载按键 | 无（`GPIO_BUTTON` / `GPIO_IO_00` 代码一律删除） | A0 用户裁决 | 2026-09-12 | 目视确认 |
| 4 | 窗口口径 | 默认 1920×1080 横屏窗口模式（非全屏），上限 1920×1280 | A0 用户裁决 | 2026-09-12 | 目视 + 日志 M 节（`xrandr` max 16384×16384，current 1920×1200） |
| 5 | 数字 IO 数量 | 8（`GPIO_IO_01~08`） | A0 用户裁决 + 日志 G 节 | 2026-09-12 | 目视 + `dir(ESP32)`（`esp32_gpio_count=8`） |
| 6 | ADC 路数 | 8（8 个口都能作 ADC） | A0 用户裁决 + 日志 G 节 | 2026-09-12 | 目视 + `dir(ESP32)`（`esp32_adc_count=8`） |
| 7 | 右下角开关 | 两位：左=启用外设(ESP32)，右=充电；无第三档 | A0 用户裁决 | 2026-09-12 | 目视确认 |
| 8 | 充电口 | 独立 Type-C，与 USB 数据口不同 | A0 用户裁决 | 2026-09-12 | 目视确认 |
| 9 | 摄像头插口 | 扩展板 USB 母口（2 个任选，换口会变节点号） | A0 用户裁决 | 2026-09-12 | 目视确认 |
| 10 | ESP32 串口 | **双路径**：内部 UART `/dev/ttyS9` 与 CH341 USB `/dev/ttyCH341USB0/1` 并存；代码一律 `board.start()` 自动探测，**不硬编码节点** | A0 用户裁决（2026-10-09） + 日志 C/G 节 | 2026-10-09 | 三节点均实测可打开；`board.start()` 实连 `/dev/ttyCH341USB1` |
| 11 | OpenCV 发行包 | **不得安装 / 卸载 / 替换**（现状 `opencv-contrib-python 5.0.0.93`） | A1 基线 + 日志 A 节 | 2026-10-09 | `cv2.__file__` + `xfeatures2d`/`face`/`ximgproc`/`aruco` 均为 True |
| 12 | V3 算法开关 | 仅 13 个真名；**无** `enable_yolov8` / `enable_resnet`（旧口径；写错静默失效） | A1 基线 + 日志 E 节 | 2026-10-09 | `enable_switch_count=13`；`enable_has_object_detection/image_classification=True` |
| 13 | 色块目标颜色字段 | `color_block_target`（值 `红色`），非 `color_block_target_color` | A1 基线 + 日志 E 节 | 2026-10-09 | `field_color_block_target=True`、`field_color_block_target_color=False` |
| 14 | 颜色识别坐标 | 640×480（V3 内部处理分辨率） | A1 基线 + 日志 F 节 | 2026-10-09 | `color_recognition_image_info={'width':640,'height':480}` |
| 15 | `get_face_id()` | 成功为 `str`、无人脸为 `None` | A0 实测 | 2026-10-09 | 日志 F 节 `get_face_id_repr = None (NoneType)` |
| 16 | AudioPlayer | 无 `play()` / 无播放控制（pause/resume/stop/volume）；用 `play_file(...)` / `play_audio(...)` | A1 基线 + 日志 J 节 | 2026-10-09 | 反射 `audio_player_has_play=False` |
| 17 | 录音 → ASR | 必须先落盘再调 `voice_recognition(路径)`；`record_fixed_duration`/`save_audio` 存在 | A1 基线 | 2026-10-09 | 日志 I 节（本次落盘测试因 `recordings/recordings/` 目录 bug 未生成 wav，**待重跑确认**） |
| 18 | `delete_face` | V3 **不存在**该方法（调用 → `AttributeError`） | A1 基线 + A2（`清空人脸数据库.py`） | 2026-10-09 | 日志 F 节反射 + API 报告 §8.1 |
| 19 | `delete_object_recognition_class` | 存在，仅用于官方清库流程（`清空物体数据库.py`） | A2（`清空物体数据库.py:118-123`） | 2026-09-12 | 反射 + 代码 |
| 20 | `.md` 编码 | UTF-8 no BOM（现有文件全量合规） | A0 本机校验 | 2026-09-12 | BOM 扫描无输出 |
| 21 | 回调频率 | detection 与 frame 同频；约 **8 次/秒**（2026-10-09 实测 46 次 / 6 s，随启用算法数浮动） | A0 实测 | 2026-10-09 | 日志 F 节 `callback_detection_in_6s=46` |
| 22 | `vs_has_stop_background_top` | `False` → 停检测用 `vs.threaded_system.stop_background_detection()` | A0 实测 | 2026-10-09 | 日志 E 节反射 |
| 23 | `get_largest_color_block_index` | 空场景返回 `-1` | A0 实测 | 2026-10-09 | 日志 F 节 |
| 24 | 屏幕物理分辨率 | 1920×1200（DSI-1 原生竖屏旋转）；D4 上限 1920×1280 成立 | A0 实测 | 2026-10-09 | 日志 M 节 `xrandr` |
| 25 | V3 结果 dict | 14 个 key（13 检测算法 + `timestamp`） | A1 基线 + 日志 F 节 | 2026-10-09 | `detection_dict_keys=14` |
| 26 | ESP32 方法数 | 56（原文档"50+"） | A0 实测 | 2026-10-09 | 日志 G 节 `esp32_method_count=56` |
| 27 | text_recognition | 仅 `recognize_text`；无 `set_language`/`set_region`/`angle_classify` | A1 基线 + 日志 K 节 | 2026-10-09 | 日志 K 节反射 |
| 28 | `remove_callback` | 可用签名 `remove_callback("detection", cb)` | A0 实测 | 2026-10-09 | 日志 F 节 `remove_callback_sig` |
| 29 | pygame 版本 | 运行时 **pygame-ce 2.5.2**（`pip list` 另见 `pygame 2.6.1`，但实际 import 为 pygame-ce 2.5.2） | A0 实测 | 2026-10-09 | `pygame.version.ver` + 启动 banner |

## 待实测登记（需实物 / 需人眼；未来项目实测后回填）

> 以下项**必须用真实素材、人眼观感或专项实验**才能定案，本轮设备端探测日志无法覆盖；**明细表（含逐条实测方法 + 状态列）见 `好搭AI派文档矛盾与问题分析报告.md` §11**。
> 汇总（12 项）：V1 `qr_code`、V2 `apriltag`、V3 `black_line`、V4 `plate_recognition`、V5 `pose_detection`、V6 `object_recognition` 真实返回结构；V7 `color_block_target` 可接受枚举；V8 `get_color_recognition_color` 完整标签枚举；V9 传感器/执行器量程；V10 人脸库容量/重复注册；V11（人眼）`show_preview` 观感；**V12 `has_face_id` 实参类型（int `target_id` vs str `face_id`——日志 F 节传 str 直接 `TypeError`，文档口径写"传 face_id"）**。
> **回填规则**：实测后把 §11 对应行状态改为 `✅ 已实测（日期 + 依据）`，并把结论回写本文件 / 基线 / 指南 / SKILL。