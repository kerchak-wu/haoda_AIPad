## Hard Constraints
- SoC: **Rockchip RK3588S**（device-tree: rockchip,rk3588s-tablet-f12-v11），**NOT RK3566**。CPU = 4×Cortex-A76 + 4×Cortex-A55 大小核异构；GPU = Mali-G610 MP4；NPU = 6 TOPS @ INT8（3 核），支持 INT4/INT8/INT16/FP16。板载显示屏原生 = 8 寸 1200×1920 竖屏（DSI-1）
- **Default UI resolution: 1920×1080 landscape windowed (non-fullscreen)**. Do NOT adapt to native 1200×1920 unless explicitly required by the user. Accept the black bars on top/bottom; do not spend effort eliminating them
- Only the main branch should be kept; all other branches must be deleted
- On rockchip platform, use `camera_vision_system_v3` SDK instead of `cv2.VideoCapture` for camera access to avoid V4L2 device descriptor conflicts with SDL2
- All OpenCV (cv2) imports must come after pygame imports to prevent OpenGL initialization conflicts
- Set environment variable `LIBGL_ALWAYS_SOFTWARE=1` to force software rendering and avoid rockchip GPU driver errors; **must be set before ALL imports** (including `text_recognition`/`pygame`/`cv2`), otherwise PaddleOCR triggers Mali GPU driver loading on import, causing `libGL error: failed to create dri screen` / `failed to load driver: rockchip`
- Python version is locked to **3.8.10** (no other versions available on device). Any new dependency must support Python 3.8
- cv2 version is **5.0.0** (not 4.x) — verify API compatibility when using newer OpenCV features; fallback to v4-style calls if error occurs
- AudioPlayer (official lib) has NO pause/resume/stop/volume control; if playback control is needed, use pygame.mixer or pyaudio directly instead
- VoiceAPI token auto-refresh does NOT exist; if HTTP 401 occurs, re-call `VoiceAPI.get_token(user, password)` instead of looking for `refresh_token`
- Use `pygame-ce` (Community Edition) instead of original `pygame` — they are mutually exclusive and cannot be installed simultaneously
- `pygame-ce` version must be fixed at **2.5.2** (newer versions ≥2.5.4 drop Python 3.8 support)
- Face & object data paths are **locked to V3 SDK database directories**: application-layer JSON mapping files must live inside the same folder as V3 SDK binary feature databases, never at project root. Standard layout: `face_database/face_records.json` (side-by-side with V3 face feature files) and `object_database/object_records.json` (side-by-side with V3 object feature files). `object_data/` is a historical leftover — never reference it.

## Engineering Conventions
- Pygame initialization should only initialize required modules (display and font) using `pygame.display.init()` and `pygame.font.init()` instead of `pygame.init()` to avoid audio subsystem exceptions
- Camera initialization must occur after pygame display mode is set to prevent SDL2 from resetting V4L2 device descriptors
- Image processing for Baidu API should use 160x120 resolution, JPEG quality 60, and 5-second detection intervals to minimize CPU usage
- ESP32 sensor reads have BUILT-IN retry: `__max_retry_count=3`, `__sync_timeout=2.0s`, plus `safe_operation()` wrapper. Do NOT wrap in another retry layer unless custom logic is required
- ESP32 async Callback APIs (8 methods: digitalReadCallback/analogReadCallback/dhtReadTemperatureCallback/dhtReadHumidityCallback/ds18b20ReadCallback/ultrasonicReadCallback/bmp280ReadPressCallback/bmp280ReadTemperatureCallback) are preferred over blocking reads when UI responsiveness matters
- USB webcam device node is **/dev/video40 or /dev/video41 or /dev/video42** (uvcvideo driver); detection order is **40→41→42**; internal MIPI/ISP nodes occupy video0~video39, skip them; V3 `open_camera()` takes NO arguments (auto-detect via CameraConfig.backup_camera_ids=[40,41,42,43])
- ESP32 connects via internal UART **/dev/ttyS9**, NOT /dev/ttyUSB* (USB serial adapter nodes are empty)
- text_recognition.TextRecognizer ONLY exposes `recognize_text(image_input, confidence_threshold=0.5)`; module-level `recognize_image_text()` and `extract_text_from_image()` are available for convenience; there is NO set_language/set_region/angle_classify support
- VoiceAPI provides TWO LLM backends: `llm_chat(text)` and `llm_chat_znbw_2025(text)`; prefer the latter for newer models unless older compatibility is required
- AudioRecorder default format is sample_rate=16000, channels=1, dtype='float32' — this matches VoiceAPI.voice_recognition() input requirements exactly; no resampling needed
- **CORRECT V3 INITIALIZATION FLOW (CRITICAL)**: Step 1: `create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)`; Step 2: `vs.open_camera()`; Step 3: `vs.detection_config.enable_XXX = True` for needed algorithms; Step 4: `vs._init_detectors()` (loads RKNN models); Step 5: For color_recognition: append regions with **640x480 coordinates** (actual processing resolution); Step 6: `vs.threaded_system.start_background_detection(show_preview=True)`; Step 7: `vs.result_accessor.refresh_results()` before reads
- **ALL log files MUST go to project-root `logs/` folder** — never in project root. Standard pattern: `_log_dir = 'logs'`; `os.makedirs(_log_dir, exist_ok=True)` before `open()`; LOG_FILE = `'%s/<程序名>_YYYYMMDD.txt' % _log_dir`. Scattered `.txt`/`.log` files at project root are forbidden
- `pygame.display.set_mode()` window height must account for overlay text area (frame height + top/bottom UI rows); 640x480 frame needs ~640x620 window to avoid clipping status/gui
- **Face learning & recognition data flow (2-tier storage)**: Tier 1 (V3 SDK internal, auto-managed): `face_database/` (binary features), loaded by `learn_new_face()`, cleared by `clear_face_database()`. Tier 2 (application JSON): `face_database/face_records.json` (JSON array `[{name, face_info:{success,face_id,message}}]`), `face_id` is association key. Save: `os.makedirs('face_database', exist_ok=True)` before JSON access. Single delete: only remove JSON row, never call V3 `delete_face` (corrupts model). Full wipe: use `清空人脸数据库.py` in order, must restart Python after
- **Object learning & recognition data flow (2-tier storage, symmetric to face)**: Tier 1 (V3 SDK internal, auto-managed): `object_database/` (binary features + classifier), loaded by `add_object_recognition_class/sample`. Tier 2 (application JSON): `object_database/object_records.json` (JSON array `[{name,sample_count,first_learned,last_learned}]`), `name` is association key. Save: `os.makedirs('object_database', exist_ok=True)` before JSON access. Single delete: only remove JSON row, never call `delete_object_recognition_class`. Full wipe: use `清空物体数据库.py` in order, must restart Python after

## Lessons Learned
- Using `cv2.VideoCapture` directly causes 'ioctl(VIDIOC_QBUF): Bad file descriptor' errors on rockchip due to SDL2 video subsystem interference
- V3 `color_recognition_regions` must use 640x480 coordinates (internal processing resolution), not 1280x720; out-of-range coordinates cause '无效的区域坐标' errors
- V3 facial expression `engagement='Engaged'` does NOT mean 'looking at screen'; use `emotion` (8-class) instead for meaningful state differentiation
- V3 detectors work when initialized correctly (previously empty due to missing `_init_detectors()` call)
- MediaPipe Face Detection (15-19 FPS) and cv2.QRCodeDetector are proven alternatives to V3 built-in detectors if needed
- V3 color_block `get_color_block_center()` always returns `(0, 0)` — compute manually from `get_color_block_position()`
- V3 callback system confirmed: detection and frame callbacks fire at ~15/sec, frame callback receives `(ndarray(480,640,3), dict)`
- Deleting entire `face_database/` or `object_database/` is a NON-DESTRUCTIVE reset — V3 recreates directory on first write, only data loss
- `object_data/object_db.json` is a historical leftover, not referenced by any code/docs; safe to delete
- If tier-2 JSON is lost but V3 tier-1 DB intact, reconstruct mapping by appending new rows with current user name when V3 returns existing `face_id`/`class_name`
- **LIBGL_ALWAYS_SOFTWARE import order trap**: `text_recognition` (PaddleOCR) must be imported before `pygame`/`cv2` (utils package conflict), but `LIBGL_ALWAYS_SOFTWARE=1` must be set before `text_recognition` — otherwise PaddleOCR import triggers Mali GPU driver loading. Correct order: `os.environ` → `text_recognition` → `pygame` → `cv2`. Found in 智慧阅读角.py, 文字识别播报器.py, 文字识别视频播放器.py, 文字识别播视频qoder.py (all fixed 2026-08-15)
- **Terminal [错误] red tag issue**: 好搭AI派 terminal marks ALL stderr output as red「[错误]」, even normal INFO from third-party libs (color_block_detector, PIL, ESP32, V3 SDK). Fix for programs using `logging`: ① `StreamHandler(sys.stdout)` instead of default stderr; ② redirect `sys.stderr` to a logger wrapper; ③ `logger.propagate = False` to prevent root logger bubble; ④ eliminate all `print(msg)` + `logger.info(msg)` dual output patterns
