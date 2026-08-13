# camera_vision_system_v3 库完整 API 分析报告

> 报告版本：v2.1  
> 生成日期：2026-08-11  
> 数据来源：好搭AI派设备探测脚本（反射式成员枚举 + 签名/docstring 解析）  
> 参考资料：好搭AI派范例代码.md、视觉系统摄像头调用参考方案.md  
> 更新说明：v2.0 基于二次探测补全三个工厂函数用途、DetectionConfig 完整默认值、CameraConfig 字段、各检测器类构造参数；v2.1 追加"第八章 已知易错点"  

---

## 一、模块级导入与工厂函数

### 1.1 模块可用性标志

在 `camera_vision_system_v3` 模块层，可直接通过这些布尔标志判断对应算法是否可用：

| 标志名 | 对应算法 |
|--------|---------|
| `APRILTAG_AVAILABLE` | AprilTag 标签识别 |
| `BLACK_LINE_AVAILABLE` | 黑线检测 |
| `COLOR_BLOCK_AVAILABLE` | 色块检测 |
| `COLOR_RECOGNITION_AVAILABLE` | 颜色识别 |
| `FACE_RECOGNITION_AVAILABLE` | 人脸识别 |
| `FACIAL_EXPRESSION_AVAILABLE` | 人脸表情识别（范例代码未收录） |
| `OBJECT_RECOGNITION_AVAILABLE` | 自定义物体识别 |
| `PEOPLE_COUNTER_AVAILABLE` | 人流计数 |
| `PLATE_RECOGNITION_AVAILABLE` | 车牌识别 |
| `QR_CODE_AVAILABLE` | 二维码识别 |
| `RESNET_AVAILABLE` | ResNet 图像分类 |
| `YOLOV8_AVAILABLE` | YOLOv8 目标检测 |
| `YOLOV8_POSE_AVAILABLE` | YOLOv8 姿态检测 |

### 1.2 三个工厂函数对比（已确认用途）

库共暴露 3 个工厂函数，全部返回 `CameraVisionSystemV3` 实例，区别在于**预启用的算法集合**：

#### ① `create_vision_system_v3` —— 通用版（可精细控制）

```python
create_vision_system_v3(
    camera_id: int = -1,        # 摄像头ID，-1 自动探测
    width: int = 640,           # 画面宽度（默认640，范例常用1280）
    height: int = 480,          # 画面高度（默认480，范例常用720）
    enable_basic: bool = True,  # 【默认True】启用基础算法包
    enable_advanced: bool = False,  # 启用高级算法包
    auto_detect: bool = True,   # 是否自动探测摄像头
) -> CameraVisionSystemV3
```

**官方 docstring**：
> 创建摄像头视觉系统v3.0的便利函数
> - enable_basic: 是否启用基础检测功能（**AprilTag、黑线、二维码**）
> - enable_advanced: 是否启用高级检测功能（**车牌、物体识别、人流计数等**）

> ⚠️ **重要修正**：所有范例代码都传 `enable_basic=False`，但库的真实默认值是 **`True`**。不传参时会默认加载 AprilTag/黑线/二维码 三个基础算法，可能影响初始化速度和内存占用。

#### ② `create_ai_detection_system` —— AI 检测专用版

```python
create_ai_detection_system(
    camera_id: int = -1,
    width: int = 640,
    height: int = 480,
) -> CameraVisionSystemV3
```

**官方 docstring**：
> 创建AI检测专用系统（**主要包含深度学习相关功能**）
> - 返回: AI检测系统实例

**推断启用范围**（基于 docstring + 命名规律）：
- 人脸识别、人脸表情识别、自定义物体识别
- YOLOv8 目标检测、YOLOv8 姿态检测
- ResNet 图像分类
- **不启用**：AprilTag/黑线/二维码/色块/颜色/车牌/人流（这些是传统或非深度学习算法）

> ✅ **使用场景**：只需深度学习类算法时调用，避免加载不必要的基础算法，加快启动。

#### ③ `create_full_detection_system_v3` —— 全功能版

```python
create_full_detection_system_v3(
    camera_id: int = -1,
    width: int = 640,
    height: int = 480,
) -> CameraVisionSystemV3
```

**官方 docstring**：
> 创建启用所有检测功能的视觉系统v3.0
> - 返回: 启用所有功能的视觉系统实例

**启用范围**：全部 13 种算法一次性启用。

> ⚠️ **使用建议**：内存与 CPU 占用最高，启动最慢。仅在确实需要同时运行多种算法的场景使用，否则优先用 ① 或 ②。

#### 三个工厂函数选择决策表

| 场景 | 推荐函数 | 理由 |
|------|---------|------|
| 只用 AprilTag / 二维码 / 黑线 | `create_vision_system_v3(enable_basic=True, enable_advanced=False)` | 仅加载基础算法 |
| 只用深度学习算法（人脸/物体/YOLO） | `create_ai_detection_system(...)` | 跳过基础算法，启动更快 |
| 需要全部算法 | `create_full_detection_system_v3(...)` | 一次性全开 |
| 只需单一算法（最常见） | `create_vision_system_v3(enable_basic=False)` + 手动 `enable_xxx=True` | 最精细控制，资源最优 |

### 1.3 模块级工具函数（完整签名）

| 函数签名 | 说明 |
|---------|------|
| `detect_available_cameras(max_cameras=10, primary_cameras=None) -> List[int]` | 探测系统全部可用摄像头（完整探测，最多返回 max_cameras 个） |
| `detect_available_cameras_fast(backup_camera_ids=None, max_additional=5) -> List[int]` | 快速探测（优先检查 backup_camera_ids，最多追加 max_additional 个） |
| `find_best_camera() -> int` | 自动选择最优摄像头ID |
| `get_camera_info(camera_id: int) -> Dict` | 获取指定摄像头的详细信息字典 |
| `list_cameras()` | 枚举系统中的摄像头 |
| `print_system_info_v3()` | 打印视觉系统版本与依赖信息 |
| `test_all_features_v3()` | 执行库的全部功能自测 |
| `_test_single_camera(camera_id: int) -> bool` | 测试单个摄像头是否可用（私有但可用） |

### 1.4 演示函数（可直接运行）

| 函数签名 | docstring |
|---------|-----------|
| `demo_ai_detection()` | AI检测演示 |
| `demo_basic_detection_v3()` | 基础检测演示v3.0 |
| `demo_comprehensive_detection_v3()` | 综合检测演示v3.0 |
| `demo_people_counter()` | 人流计数演示 |
| `demo_plate_recognition_detection()` | 车牌识别专项演示 |
| `interactive_demo_v3()` | 交互式演示菜单v3.0 |

---

## 二、CameraVisionSystemV3 实例成员

### 2.1 算法开关（两种等价访问方式）

既可通过 `vision_system.detection_config.enable_xxx` 设置，也可直接通过 `vision_system.enable_xxx` 设置，两者等价：

| 配置项 | 对应算法 |
|--------|---------|
| `enable_apriltag` | AprilTag 标签识别 |
| `enable_qr_code` | 二维码识别 |
| `enable_color_recognition` | 颜色识别（需要配合 regions 设置） |
| `enable_color_block` | 色块检测 |
| `enable_black_line` | 黑线检测 |
| `enable_face_recognition` | 人脸识别（学习+识别） |
| `enable_facial_expression` | **人脸表情识别**（范例未收录！） |
| `enable_object_recognition` | 自定义物体识别 |
| `enable_plate_recognition` | 车牌识别 |
| `enable_image_classification` | ResNet 图像分类 |
| `enable_people_counter` | 人流计数 |
| `enable_object_detection` | YOLOv8 目标检测 |
| `enable_pose_detection` | YOLOv8 姿态检测 |

### 2.2 摄像头与生命周期方法

| 方法/属性 | 签名 | 说明 |
|----------|------|------|
| `open_camera()` | `() -> bool` | 打开摄像头，返回是否成功 |
| `close_camera()` | `()` | 关闭摄像头（文档未记录） |
| `is_opened` | `bool` 属性 | 摄像头是否已打开 |
| `switch_camera(camera_id)` | 签名未反射 | 切换到指定摄像头 |
| `get_current_camera_info()` | `()` | 获取当前摄像头状态信息 |
| `capture_frame()` | `() -> Optional[np.ndarray]` | 从后台缓存读取一帧画面 |
| `process_one_frame(show_preview=True)` | `(bool) -> Optional[Dict]` | 同步处理一帧，返回检测结果字典 |
| `cleanup()` | `()` | 释放全部视觉系统资源 |
| `current_frame` | `np.ndarray` 属性 | 当前帧的缓存引用 |
| `cap` | `cv2.VideoCapture` 属性 | 底层 cv2 摄像头对象（谨慎使用） |
| `current_fps` | `float` 属性 | 当前采集/检测帧率 |
| `_init_detectors()` | 私有方法 | 按 detection_config 初始化全部已启用检测器 |

### 2.3 检测器状态与运行控制

| 方法/属性 | 说明 |
|----------|------|
| `set_detectors_status(...)` | 批量设置检测器开关（具体签名待进一步探测） |
| `start_continuous_detection()` | 启动连续检测模式（与后台线程模式的区别待验证） |
| `is_running` | `bool` 属性，检测线程是否活跃 |
| `detect_single_frame()` | 对当前帧执行一次检测（签名未反射） |

### 2.4 人脸管理接口（⚠️ 重要确认）

| 方法 | 签名 | 说明 |
|------|------|------|
| `learn_new_face(frame=None)` | `(np.ndarray=None)` | 学习新人脸；不传帧时从摄像头当前画面取 |
| `clear_face_database()` | `()` | **清空人脸数据库**（确认存在！） |
| `get_face_database_info()` | `()` | **查询人脸数据库信息**（确认存在！） |
| ~~`delete_face(face_id)`~~ | **不存在** | 【结论】库本身**未暴露**删除单个人脸的接口。项目记忆中「delete_face 会破坏模型」的现象实际来自第三方调用，官方 V3 库根本没有该方法。应用层只能用 `clear_face_database()` 全部清空。 |

### 2.5 自定义物体识别管理接口

| 方法 | 签名 | 说明 |
|------|------|------|
| `add_object_recognition_class(frame=None, class_name=None)` | 添加新物体类别（首个样本） |
| `add_object_recognition_sample(frame=None, class_name=None)` | 为已有类别追加训练样本 |
| `delete_object_recognition_class(...)` | 存在但签名未反射 | 删除一个物体类别 |
| `get_object_database_info()` | `()` | 查询物体数据库统计信息 |

### 2.6 各算法独立结果获取（绕过 result_accessor）

每个算法都有对应的直接结果方法（返回原始结果字典，视具体算法而定）：

```
get_apriltag_results()         get_qr_code_results()
get_color_recognition_results()  get_color_block_results()
get_black_line_results()       get_face_recognition_results()
get_facial_expression_results()  get_object_recognition_results()
get_object_detection_results()   get_pose_detection_results()
get_plate_recognition_results()  get_image_classification_results()
get_people_counter_results()

get_all_detection_results()    # 汇总所有算法
get_latest_results()           # 最新一帧汇总
```

---

## 三、DetectionConfig 高级参数详解（含完整默认值）

`DetectionConfig` 是 dataclass，可通过 `DetectionConfig(...)` 直接构造，也可通过 `vision_system.detection_config` 修改。完整构造签名：

```python
DetectionConfig(
    # ===== 13 个算法开关（全部默认 False）=====
    enable_apriltag: bool = False,
    enable_black_line: bool = False,
    enable_color_block: bool = False,
    enable_color_recognition: bool = False,
    enable_face_recognition: bool = False,
    enable_qr_code: bool = False,
    enable_plate_recognition: bool = False,
    enable_object_recognition: bool = False,
    enable_people_counter: bool = False,
    enable_image_classification: bool = False,
    enable_object_detection: bool = False,
    enable_pose_detection: bool = False,
    enable_facial_expression: bool = False,

    # ===== AprilTag =====
    apriltag_family: str = 'tag36h11',          # 标签家族

    # ===== 黑线检测 =====
    max_lines: Optional[int] = 3,                # 返回的最大线条数

    # ===== 色块检测 =====
    color_block_target: str = '红色',            # 目标颜色
    color_block_min_width: int = 30,             # 最小宽度（像素）
    color_block_min_height: int = 30,            # 最小高度（像素）
    color_block_similarity: float = 0.5,         # 相似度阈值

    # ===== 颜色识别 =====
    color_recognition_regions: List[Tuple[int,int,int,int]] = [],  # ROI列表，元素(x,y,w,h)
    color_recognition_threshold: float = 50.0,   # 颜色阈值

    # ===== 人脸识别 =====
    face_model_path: str = None,                 # 模型路径（None则用内置）
    face_db_path: str = 'face_database',         # 数据库目录

    # ===== 自定义物体识别 =====
    object_db_path: str = 'object_database',     # 物体数据库目录

    # ===== 图像分类（ResNet）=====
    resnet_model_path: str = None,
    resnet_labels_path: str = None,

    # ===== YOLOv8 目标检测 =====
    yolov8_model_type: str = 's',                # 模型规格: n/s/m/l/x

    # ===== 全局 =====
    roi: Optional[Tuple[int,int,int,int]] = None,  # 全局ROI (x,y,w,h)

    # ===== 车牌识别 =====
    plate_recognition_mode: str = 'auto',        # 识别模式
)
```

### 关键默认值速查表

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `apriltag_family` | `'tag36h11'` | AprilTag 标签家族 |
| `max_lines` | `3` | 黑线检测最大返回线条数 |
| `color_block_target` | `'红色'` | 色块默认目标颜色 |
| `color_block_min_width/height` | `30 / 30` | 色块最小尺寸 |
| `color_block_similarity` | `0.5` | 色块相似度阈值 |
| `color_recognition_threshold` | `50.0` | 颜色识别阈值 |
| `face_db_path` | `'face_database'` | 人脸数据库目录（相对路径） |
| `face_model_path` | `None` | 人脸模型（None 用内置） |
| `object_db_path` | `'object_database'` | 物体数据库目录 |
| `yolov8_model_type` | `'s'` | YOLOv8 模型规格 |
| `plate_recognition_mode` | `'auto'` | 车牌识别模式 |
| `roi` | `None` | 全局 ROI（None 表示全画面） |

### CameraConfig 摄像头配置（dataclass）

```python
CameraConfig(
    camera_id: int = -1,                         # -1 自动探测
    width: int = 640,
    height: int = 480,
    fps: int = 30,                               # 期望帧率
    auto_detect: bool = True,                    # 自动探测
    backup_camera_ids: List[int] = [40, 41, 42, 43],  # ⚠️ 默认备份摄像头列表
) -> None
```

> 💡 **重要发现**：`backup_camera_ids` 默认值是 `[40, 41, 42, 43]`，与项目记忆中「优先使用 /dev/video41 和 /dev/video40」的约定**完全吻合**。这说明库本身就内置了这些设备号作为备份探测顺序，无需应用层手动指定。

### 各检测器类的构造参数（用于直接实例化或理解内部依赖）

| 检测器类 | 构造签名 |
|---------|---------|
| `AprilTagDetector` | `(family='tag36h11')` |
| `BlackLineDetector` | `()` |
| `QRCodeDetector` | `()` |
| `ColorBlockDetector` | `()` |
| `ColorRecognitionDriver` | `(color_threshold: float = 50.0)` |
| `FaceRecognitionModule` | `(model_path=None, face_db_path='face_database', similarity_threshold=0.8)` |
| `FacialExpressionRecognizer` | `(rknn_model_path=None)` ← **注意是 RKNN 模型，走 NPU 加速** |
| `ObjectRecognitionModule` | `(object_db_path='object_database')` |
| `PlateRecognitionSystem` | `(det_model_path=None, rec_model_path=None, conf_thresh=0.5, nms_thresh=0.5)` |
| `ResNetClassifier` | `(model_path=None, class_label_path=None, debug=False)` |
| `YOLOv8Detector` | `(model_type='s', debug=False)` |
| `YOLOv8PoseDetector` | `(debug=False)` |
| `PeopleCounter` | `(model_type='s')` |

> 💡 **关键信息**：
> - 人脸识别默认相似度阈值 `0.8`（可在构造时调整）
> - 表情识别用 **RKNN** 模型，走 Rockchip NPU 加速
> - YOLOv8 系列默认模型规格 `'s'`（small），平衡精度与速度
> - 车牌识别有独立的 det（检测）+ rec（识别）两阶段模型，置信度阈值 0.5，NMS 阈值 0.5

### 异常类

| 类名 | MRO | 说明 |
|------|-----|------|
| `CameraNotFoundError` | `Exception → BaseException → object` | 摄像头未找到或无法访问时抛出 |
| `CameraStatus` | `object` | 摄像头状态信息（非异常，是数据类） |

---

## 四、ThreadedVisionSystem（后台检测线程管理）

挂在 `vision_system.threaded_system` 下。

### 4.1 线程控制

| 方法 | 签名 | 说明 |
|------|------|------|
| `start_background_detection(show_preview=True)` | `(bool) -> None` | 启动后台检测线程（视觉系统全托管模式入口） |
| `stop_background_detection()` | `() -> None` | **停止后台检测**（重要：存在！位置在 threaded_system 下，不在 vision_system 顶层） |
| `is_detection_running()` | `() -> bool` | 检测循环是否在运行 |
| `is_running()` | `() -> bool` | 线程对象整体是否活跃 |

### 4.2 帧与结果获取

| 方法 | 签名 | 说明 |
|------|------|------|
| `get_latest_frame()` | `() -> Optional[np.ndarray]` | 获取最新一帧（非阻塞） |
| `get_latest_results()` | `() -> Optional[Dict]` | 获取最新一帧的检测结果（非阻塞） |
| `get_next_result(timeout=1.0)` | `(float) -> Optional[Dict]` | 阻塞等待下一个可用结果，带超时 |
| `get_all_pending_results()` | `() -> List[Dict]` | 取出结果队列中全部待处理项并清空队列 |
| `get_current_fps()` | `() -> float` | 后台检测线程的实际帧率 |

### 4.3 回调注册系统

| 方法 | 签名 | 触发时机 |
|------|------|---------|
| `add_detection_callback(cb)` | `cb: Callable[[Dict], None]` | 每次检测完成时，回调接收检测结果字典 |
| `add_frame_callback(cb)` | `cb: Callable[[np.ndarray, Dict], None]` | 每帧都调用，接收画面帧+检测结果 |
| `add_error_callback(cb)` | `cb: Callable[[Exception], None]` | 检测线程内部抛出异常时回调 |
| `remove_callback(callback_type, callback)` | `(str, Callable)` | 移除已注册的回调 |

---

## 五、CompleteDetectionResultAccessor 完整结果访问器

挂在 `vision_system.result_accessor` 下。**所有 getter 方法都需要先调用 `refresh_results()` 刷新缓存。**

### 5.1 通用工具方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `refresh_results()` | None | 【必须先调】刷新结果缓存，读取前必调 |
| `get_detection_summary()` | `Dict[str, Any]` | 汇总当前所有算法的检测状态 |
| `get_detection_timestamp()` | `float` | 最近一次检测的时间戳 |
| `get_active_detection_types()` | `List[str]` | 当前有结果的算法类型名列表 |
| `has_any_detection()` | `bool` | 任一算法有检测结果即返回 True |
| `is_point_in_bbox(point, bbox)` | `bool` | 判断点 (x,y) 是否在矩形 (x,y,w,h) 内 |
| `calculate_distance_between_points(p1, p2)` | `float` | 两点欧氏距离 |

### 5.2 AprilTag 标签识别

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_apriltag_count()` | `int` | 检测到的标签数量 |
| `get_apriltag_id(idx)` | `int` | 第 idx 个标签的 ID |
| `get_apriltag_family(idx)` | `str` | 标签家族名 |
| `get_apriltag_center(idx)` | `tuple` | 中心坐标 (x, y) |
| `get_apriltag_corners(idx)` | `List[tuple]` | 四个角坐标 |
| `get_apriltag_pose_R(idx)` | `List[tuple]` | 姿态旋转矩阵 R（3×3） |
| `get_apriltag_pose_t(idx)` | `List[tuple]` | 姿态平移向量 t（3维，可用于测距） |
| `get_apriltag_hamming(idx)` | — | 汉明距离（检测质量） |
| `get_apriltag_decision_margin(idx)` | — | 决策边界余量 |
| `get_apriltag_goodness(idx)` | — | 拟合优度 |
| `has_apriltag_id(target_id)` | `bool` | 当前画面中是否存在指定 ID 的标签 |
| `get_nearest_apriltag_to_point(target_point)` | `int` | 距离指定点最近的标签索引 |

### 5.3 二维码识别

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_qr_code_count()` | `int` | |
| `get_qr_code_content(idx)` | `str` | 二维码解码内容 |
| `get_qr_code_type(idx)` | `str` | 内容类型（URL / TEXT 等） |
| `get_qr_code_position(idx)` | `tuple` | 位置 bbox |
| `qr_code_contains_text(search_text)` | `bool` | 内容是否包含指定子串 |

### 5.4 颜色识别（指定区域）

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_color_recognition_count()` | `int` | 已配置且有结果的区域数 |
| `get_color_recognition_color(idx)` | `str` | 英文颜色名 |
| `get_color_recognition_name(idx)` | `str` | 中文颜色名（范例中误写成重复调用 color，实际应调用 name） |
| `get_color_recognition_rgb(idx)` | `tuple` | RGB 三通道元组 |

### 5.5 色块检测

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_color_block_count()` | `int` | |
| `get_color_block_color(idx)` | `str` | 颜色名 |
| `get_color_block_position(idx)` | `tuple` | 左上角 (x, y) |
| `get_color_block_center(idx)` | `tuple` | 中心 (cx, cy) |
| `get_color_block_area(idx)` | `int` | 面积（像素数） |
| `get_largest_color_block_index()` | `int` | 面积最大色块的索引 |
| `has_color_block(target_color)` | `bool` | 是否出现了指定颜色的色块 |

### 5.6 黑线 / 曲线检测

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_line_count()` | `int` | 检测到的直线条数 |
| `get_line_angle(idx)` | `float` | 直线角度（度） |
| `get_line_length(idx)` | `float` | 直线长度（像素） |
| `get_line_endpoints(idx)` | `tuple` | 两端点坐标 |
| `get_curve_count()` | `int` | 曲线条数（文档未提） |

### 5.7 人脸识别

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_face_count()` | `int` | 画面中检测到的人脸数 |
| `get_face_id()` | `int` | 识别出的人脸 ID |
| `get_face_confidence()` | `float` | 匹配置信度 0~1 |
| `get_face_name()` | `str` | 关联的人脸姓名 |
| `get_face_position()` | `tuple` | 人脸 bbox (x, y, w, h) |
| `has_face_id(target_id)` | `bool` | 当前是否匹配到指定 ID |

### 5.8 人脸表情识别（范例未收录的新增算法 ⚠️）

对应算法开关：`detection_config.enable_facial_expression`

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_facial_expression_success()` | `bool` | 是否成功检测到人脸 |
| `get_facial_expression_emotion()` | `str` | 主表情（如 happy / sad / angry / neutral 等） |
| `get_facial_expression_emotions_confidence()` | `dict` | 全部表情的置信度字典 |
| `get_facial_expression_engagement()` | `str` | 投入度等级（高/中/低 等） |
| `get_facial_expression_engagement_confidence()` | `dict` | 投入度各子项置信度 |
| `get_facial_expression_inference_time()` | `float` | 单次推理耗时（秒） |

### 5.9 自定义物体识别

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_object_recognition_success()` | `bool` | 识别是否成功匹配 |
| `get_object_recognition_status()` | `bool` | 识别状态（与上一项的差异待验证） |
| `get_object_recognition_class_name()` | `str` | 匹配到的物体类别名 |
| `get_object_recognition_confidence()` | `float` | 匹配置信度 |
| `get_object_recognition_message()` | `str` | 识别状态描述文本 |

> ✅ **确认**：该算法一次只返回一个匹配对象，因此没有 `get_object_recognition_count()`。

### 5.10 车牌识别

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_plate_recognition_count()` | `int` | |
| `get_plate_recognition_text(idx=0)` | `str` | 车牌号字符串 |
| `get_plate_recognition_confidence(idx=0)` | `float` | OCR 置信度 |
| `get_plate_recognition_color(idx=0)` | `str` | 车牌底色（蓝/黄/绿等） |
| `get_plate_recognition_type(idx=0)` | `str` | 车牌类型（小型车/大型车/新能源等） |
| `get_plate_recognition_position(idx=0)` | `tuple` | 车牌在画面中的 bbox |
| `get_plate_recognition_success()` | `bool` | 是否成功识别到车牌 |

> 所有带 `idx=0` 的方法支持多车牌同时识别。

### 5.11 图像分类（ResNet）

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_image_classification_count()` | `int` | 返回 Top-K 的有效结果数 |
| `get_image_classification_class_name(idx)` | `str` | 第 idx 个分类标签 |
| `get_image_classification_confidence(idx)` | `float` | 对应置信度 |
| `get_image_classification_class_name_top()` | `str` | 仅返回 Top-1 标签（便捷封装） |
| `has_image_classification(class_name)` | `bool` | 前 K 项中是否出现指定类别 |

### 5.12 人流计数

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_people_counter_in()` | `int` | 累计进入人数 |
| `get_people_counter_out()` | `int` | 累计离开人数 |
| `get_people_counter_net_flow()` | `int` | **净流量 = 进入 - 离开**（新增） |
| `get_people_counter_total_count()` | `int` | **总通行人数 = 进入 + 离开**（新增） |
| `has_people_counter_movement()` | `bool` | 当前是否有人在通过 |

### 5.13 目标检测（YOLOv8）

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_object_detection_count()` | `int` | 检测框数量 |
| `get_object_detection_class_name(idx)` | `str` | 目标类别名 |
| `get_object_detection_class_id(idx)` | `str` | 目标类别 ID |
| `get_object_detection_confidence(idx)` | `float` | 检测框置信度 |
| `get_object_detection_bbox(idx)` | `tuple` | 边界框 (x, y, w, h) |
| `count_detected_objects_by_class(target_class)` | `int` | 指定类别的检测数量统计 |
| `has_object_detection_class(target_class)` | `bool` | 是否存在指定类别的目标 |

### 5.14 姿态检测（YOLOv8-Pose）

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_pose_detection_count()` | `int` | 检测到的人体数 |
| `get_pose_detection_box(idx)` | `tuple` | 人体 bbox |
| `get_pose_detection_confidence(idx)` | `float` | |
| `get_pose_detection_keypoints(idx)` | `List[tuple]` | 全部关键点坐标列表 |
| `get_pose_detection_specific_keypoint(pose_index, keypoint_name)` | `tuple` | **按关键点名取坐标**（如 'nose', 'left_shoulder'），无需记忆索引。推荐优先使用此接口。 |

---

## 六、关键修正对照表（文档分析 vs 真实探测）

| 项目 | 最初文档分析 | 真实探测结果 |
|------|-------------|-------------|
| `create_vision_system_v3` 参数数 | 5 个（缺 `auto_detect`） | **6 个**，含 `auto_detect: bool=True` |
| `width / height` 默认值 | 未记录（范例常用 1280×720） | **640×480** |
| `enable_basic` 默认值 | 未记录（范例全部传 False） | **True**（重要！不传参即加载基础算法） |
| `stop_background_detection` | 待核验 | **存在**，在 `threaded_system` 对象下 |
| `clear_face_database` | 记忆中提及但未确认 | **确认存在**，签名 `()` |
| `delete_face(face_id)` | 记忆中「会破坏模型」 | **库中完全不存在**，仅应用层私有实现 |
| `get_face_name / get_face_position` | 未记录 | **均存在** |
| 人脸表情识别整套 API | 完全未记录 | **完整存在**（7 个方法 + enable 开关） |
| `get_object_detection_class_id` | 未记录 | **存在** |
| `count_detected_objects_by_class` | 未记录 | **存在** |
| `get_pose_detection_specific_keypoint` | 未记录 | **存在**，支持按名取关键点 |
| 人流计数 net_flow / total_count | 仅有 in / out | **另有 2 个聚合统计** |
| 车牌 color / type / position | 仅有 text / confidence | **另有 3 项属性** |
| 二维码 position / contains_text | 未记录 | **存在** |
| 色块 largest_index / has_color_block | 未记录 | **存在** |
| 图像分类 class_name_top | 未记录 | **存在**（便捷 Top-1） |
| AprilTag pose_R / pose_t（6DoF 姿态） | 未记录 | **完整存在**，可直接用于机器人定位测距 |
| 回调函数系统 | 未记录 | detection / frame / error 三种回调齐全 |
| 线程结果获取方式 | 仅提到 refresh_results | latest / next(阻塞) / all_pending 三种模式 |
| 三个工厂函数用途 | 「待进一步确认」 | **docstring 明确**：v3 通用版 / ai 深度学习版 / full 全开版 |
| `enable_basic` 启用范围 | 未知 | **AprilTag、黑线、二维码**（docstring 确认） |
| `enable_advanced` 启用范围 | 未知 | **车牌、物体识别、人流计数等**（docstring 确认） |
| `DetectionConfig` 默认值 | 全部未知 | **29 个字段默认值全部获取**（见第三章） |
| `CameraConfig.backup_camera_ids` | 未记录 | **默认 [40, 41, 42, 43]**，与项目约定吻合 |
| `CameraConfig.fps` | 未记录 | **默认 30** |
| 各检测器类构造参数 | 未记录 | **13 个检测器类签名全部获取**（见第三章） |
| 表情识别底层模型 | 未记录 | **RKNN 模型，走 Rockchip NPU 加速** |
| 人脸识别相似度阈值 | 未记录 | **默认 0.8**（FaceRecognitionModule 构造参数） |
| `detect_available_cameras` 签名 | 仅函数名 | `(max_cameras=10, primary_cameras=None) -> List[int]` |
| `detect_available_cameras_fast` 签名 | 仅函数名 | `(backup_camera_ids=None, max_additional=5) -> List[int]` |
| 演示函数 | 未记录 | **6 个 demo_* 函数**可直接运行体验 |

---

## 七、推荐的标准使用模式（回顾）

### 模式 A：纯 cv2 独占（第三方算法：MediaPipe / YOLO / 百度云）

```python
# 不导入 camera_vision_system_v3
import cv2
cap = cv2.VideoCapture("/dev/video41")  # 直接独占摄像头
```

### 模式 B：混合模式（官方算法 + 离线录入）⭐ 推荐

```python
from camera_vision_system_v3 import create_vision_system_v3
import cv2

vision_system = create_vision_system_v3(enable_basic=False)  # 不预加载
vision_system.detection_config.enable_face_recognition = True
vision_system._init_detectors()
# ❌ 不调用 open_camera() 和 start_background_detection()
# ✅ 用 cv2 独占采图
cap = cv2.VideoCapture("/dev/video41")
# 需要录入时，从 cv2 取帧传给视觉系统
vision_system.learn_new_face(frame=frame_from_cv2)
```

### 模式 C：视觉系统全托管（实时追踪+硬件联动）

```python
from camera_vision_system_v3 import create_vision_system_v3

vision_system = create_vision_system_v3(enable_basic=False)
vision_system.detection_config.enable_face_recognition = True
vision_system._init_detectors()
vision_system.open_camera()
vision_system.threaded_system.start_background_detection(show_preview=False)
# ❌ 绝对禁止再使用 cv2.VideoCapture
# ✅ 用 capture_frame 取画面，result_accessor 读结果
while True:
    vision_system.result_accessor.refresh_results()
    face_id = vision_system.result_accessor.get_face_id()
    frame = vision_system.capture_frame()
    # 停止后台检测（新确认的方法）：
    # vision_system.threaded_system.stop_background_detection()
```

---

## 八、已知易错点（写代码前必读）

> 本节汇总在实际开发和文档校对中发现的 V3 库 API 易错点。每条均来自反射探测或运行时验证。新项目开发前请逐条对照，旧项目复核时优先检查这些点。

### 8.1 接口存在性陷阱

| ❌ 错误调用 | ✅ 正确调用 | 原因 |
|------------|-----------|------|
| `vision_system.delete_face(face_id)` | `vision_system.clear_face_database()` | **V3 库未暴露删除单个人脸的接口**。`delete_face` 方法不存在，调用会抛 `AttributeError`。如需删除单人，应用层自行维护 `face_id → name` 映射表，但视觉系统内部数据无法删除（重新学习同一人脸会返回旧 `face_id` 并触发补录）。 |
| `result_accessor.get_object_name()` | `result_accessor.get_object_recognition_class_name()` | **没有 `get_object_name()` 方法**。物体识别结果应通过 `get_object_recognition_class_name()` / `get_object_recognition_confidence()` / `get_object_recognition_success()` 等方法读取。 |
| `result_accessor.get_object_recognition_count()` | `result_accessor.get_object_recognition_success()` | **没有 `get_object_recognition_count()` 方法**。物体识别算法只能识别 1 个物体，用 `success` 判断是否识别到。 |
| `vision_system.stop_background_detection()` | `vision_system.threaded_system.stop_background_detection()` | **`stop_background_detection` 在 `threaded_system` 对象下**，不在 `vision_system` 顶层。 |
| `vision_system.set_camera_resolution(w, h)` | 重建 `CameraConfig` 并重新 `open_camera()` | **V3 库没有运行时修改分辨率的接口**。 |

### 8.2 参数名陷阱

| ❌ 错误参数名 | ✅ 正确参数名 | 涉及方法 | 错误类型 |
|-------------|-------------|---------|---------|
| `name=...` | `class_name=...` | `add_object_recognition_class(frame=, class_name=)` | `TypeError: unexpected keyword argument 'name'` |
| `name=...` | `class_name=...` | `add_object_recognition_sample(frame=, class_name=)` | 同上 |

### 8.3 默认值陷阱

| 配置项 | 真实默认值 | 易错点 |
|--------|-----------|--------|
| `create_vision_system_v3.enable_basic` | **`True`** | 范例代码全部传 `enable_basic=False`，但库的真实默认值是 `True`。不传参会默认加载 AprilTag/黑线/二维码三个基础算法，导致启动变慢、内存占用升高。**单一算法场景务必显式传 `enable_basic=False`**。 |
| `CameraConfig.backup_camera_ids` | **`[40, 41, 42, 43]`** | 库内置的备份摄像头 ID 优先级是 40→41→42→43，与项目记忆中「优先 /dev/video41 和 /dev/video40」一致。如需修改顺序，应自定义 `CameraConfig`。 |
| `DetectionConfig.color_block_target` | **`'红色'`** | 色块检测默认目标是红色，且为**中文字符串**。切换目标颜色时必须用中文（如 `'蓝色'`、`'绿色'`）。 |
| `DetectionConfig.face_db_path` | **`'face_database'`** | 人脸数据库默认存放在当前工作目录下的 `face_database/` 文件夹。**程序的工作目录会影响人脸库位置**，换目录运行会导致已学习人脸"丢失"。 |

### 8.4 模式选择陷阱

| 误区 | 正确认知 |
|------|---------|
| 「物体学习必须走全托管模式，不接受外部帧」 | **错误**。`add_object_recognition_class(frame=None, class_name=None)` 和 `add_object_recognition_sample(frame=None, class_name=None)` 都支持外部传帧：`frame=None` 时从摄像头取，传 `frame=ndarray` 时从外部帧取。模式选择应由**是否需要持续后台检测**决定，而非算法本身。 |
| 「人脸学习必须走混合模式」 | **错误**。`learn_new_face(frame=None)` 同样支持两种模式：`frame=None` 内部取帧，`frame=ndarray` 外部传帧。 |
| 「表情识别只能用百度云 API」 | **不准确**。V3 库自带本地 RKNN 表情识别能力（`enable_facial_expression=True` + `FacialExpressionRecognizer`），走 Rockchip NPU 加速，离线可用。仅在需要云端属性分析（年龄、性别）时才必须用百度云。 |

### 8.5 结果访问顺序陷阱

| 误区 | 正确做法 |
|------|---------|
| 直接调用 `result_accessor.get_xxx()` | **必须先调用 `result_accessor.refresh_results()`**，否则读到的是上次缓存的结果（或空结果）。正确顺序：`refresh_results()` → `get_xxx()`。 |
| 在 `get_face_count() == 0` 时调用 `get_face_id()` | `get_face_id()` 在无人脸时返回 `None` 或 `0`（具体值待核验），但**语义上无意义**。应先判断 `get_face_count() > 0` 再读 `get_face_id()`。 |

### 8.6 资源冲突陷阱

| 误区 | 后果 | 正确做法 |
|------|------|---------|
| 全托管模式下同时用 `cv2.VideoCapture` | `Device or resource busy` 错误，摄像头无法打开 | 全托管模式下**绝对禁用** `cv2.VideoCapture`，画面只能用 `vision_system.capture_frame()` |
| `vision_system.open_camera()` 与 `cv2.VideoCapture` 同时使用 | 同上 | 混合模式下**不调用** `open_camera()`，只调 `_init_detectors()` 加载算法 |
| 后台检测线程与主循环同时读写 `current_frame` | 帧数据竞争，画面撕裂或崩溃 | 用 `threading.Lock` 保护帧读写，或通过 `threaded_system.get_latest_frame()` 取帧 |

### 8.7 清空/重置陷阱

| 操作 | 行为 | 注意事项 |
|------|------|---------|
| `clear_face_database()` | 清空**全部**人脸数据 | 无法删除单人。操作后需重新学习所有人脸。配合删除 `face_features.npy` / `face_ids.npy` 可彻底重置识别模型。 |
| `clear_face_database()` 之后立即 `learn_new_face()` | 可能因模型未完全重置导致 `face_id` 从旧值继续递增 | 如需彻底从 0 开始，删除 `face_database/` 整个文件夹后重启程序。 |

---

*报告版本 v2.1 — 2026-08-11 追加"已知易错点"章节*
