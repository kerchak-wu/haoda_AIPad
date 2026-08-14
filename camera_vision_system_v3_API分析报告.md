# camera_vision_system_v3 库完整 API 分析报告

> 报告版本：v2.4  
> 生成日期：2026-08-14（v2.0/v2.1：2026-08-11）  
> 数据来源：好搭AI派设备探测脚本（反射式成员枚举 + 签名/docstring 解析）+ 三份修复后干净日志实测  
> 参考资料：好搭AI派范例代码.md、视觉系统摄像头调用参考方案.md（v4.3）、**系统环境与非视觉官方库探测报告_v1.md（新，ESP32/语音/音频/OCR 完整 API）**、**好搭AI派范例代码补充说明.md**  
> 更新说明：v2.0 补全三个工厂函数、DetectionConfig/CameraConfig 字段、各检测器构造参数；v2.1 追加第八章"已知易错点"；v2.2 补充 2026-08-14 环境层信息；v2.3 推翻 v2.2 中"检测器不工作"的错误结论（原脚本漏调 `_init_detectors()`），重建 8.8 节；v2.4 基于三份修复后干净日志（零错误），更新 engagement 表格数据+confidence列，新增 8.8.4 回调系统实测总表和 8.8.5 已知 V3 bug 表，修正 5.5/5.8 方法表描述，为未验证算法标注范例代码参考

---

## 📋 目录

- [一、模块级导入与工厂函数](#一模块级导入与工厂函数)
  - [1.1 模块可用性标志](#11-模块可用性标志)
  - [1.2 三个工厂函数对比（已确认用途）](#12-三个工厂函数对比已确认用途)
  - [1.3 模块级工具函数（完整签名）](#13-模块级工具函数完整签名)
  - [1.4 演示函数（可直接运行）](#14-演示函数可直接运行)
- [二、CameraVisionSystemV3 实例成员](#二cameravisionsystemv3-实例成员)
  - [2.1 算法开关（两种等价访问方式）](#21-算法开关两种等价访问方式)
  - [2.2 摄像头与生命周期方法](#22-摄像头与生命周期方法)
  - [2.3 检测器状态与运行控制](#23-检测器状态与运行控制)
  - [2.4 人脸管理接口（⚠️ 重要确认）](#24-人脸管理接口-重要确认)
  - [2.5 自定义物体识别管理接口](#25-自定义物体识别管理接口)
  - [2.6 各算法独立结果获取（绕过 result_accessor）](#26-各算法独立结果获取绕过-result_accessor)
- [三、DetectionConfig 高级参数详解（含完整默认值）](#三detectionconfig-高级参数详解含完整默认值)
  - [关键默认值速查表](#关键默认值速查表)
  - [CameraConfig 摄像头配置（dataclass）](#cameraconfig-摄像头配置dataclass)
  - [各检测器类的构造参数](#各检测器类的构造参数用于直接实例化或理解内部依赖)
  - [异常类](#异常类)
- [四、ThreadedVisionSystem（后台检测线程管理）](#四threadedvisionsystem后台检测线程管理)
  - [4.1 线程控制](#41-线程控制)
  - [4.2 帧与结果获取](#42-帧与结果获取)
  - [4.3 回调注册系统](#43-回调注册系统)
- [五、CompleteDetectionResultAccessor 完整结果访问器](#五completedetectionresultaccessor-完整结果访问器)
  - [5.1 通用工具方法](#51-通用工具方法)
  - [5.2 AprilTag 标签识别](#52-apriltag-标签识别)
  - [5.3 二维码识别](#53-二维码识别)
  - [5.4 颜色识别（指定区域）](#54-颜色识别指定区域)
  - [5.5 色块检测](#55-色块检测)
  - [5.6 黑线 / 曲线检测](#56-黑线--曲线检测)
  - [5.7 人脸识别](#57-人脸识别)
  - [5.8 人脸表情识别（范例未收录的新增算法 ⚠️）](#58-人脸表情识别范例未收录的新增算法-)
  - [5.9 自定义物体识别](#59-自定义物体识别)
  - [5.10 车牌识别](#510-车牌识别)
  - [5.11 图像分类（ResNet）](#511-图像分类resnet)
  - [5.12 人流计数](#512-人流计数)
  - [5.13 目标检测（YOLOv8）](#513-目标检测yolov8)
  - [5.14 姿态检测（YOLOv8-Pose）](#514-姿态检测yolov8-pose)
- [六、关键修正对照表（文档分析 vs 真实探测）](#六关键修正对照表文档分析-vs-真实探测)
- [七、推荐的标准使用模式（回顾）](#七推荐的标准使用模式回顾)
  - [模式 A：纯 cv2 独占](#模式-a纯-cv2-独占第三方算法mediapipe--yolo--百度云)
  - [模式 B：混合模式（官方算法 + 离线录入）⭐ 推荐](#模式-b混合模式官方算法--离线录入-推荐)
  - [模式 C：视觉系统全托管（实时追踪+硬件联动）](#模式-c视觉系统全托管实时追踪硬件联动)
- [八、已知易错点（写代码前必读）](#八已知易错点写代码前必读)
  - [8.1 接口存在性陷阱](#81-接口存在性陷阱)
  - [8.2 参数名陷阱](#82-参数名陷阱)
  - [8.3 默认值陷阱](#83-默认值陷阱)
  - [8.4 模式选择陷阱](#84-模式选择陷阱)
  - [8.5 结果访问顺序陷阱](#85-结果访问顺序陷阱)
  - [8.6 资源冲突陷阱](#86-资源冲突陷阱)
  - [8.7 清空/重置陷阱](#87-清空重置陷阱)
  - [8.8 2026-08-14 系统实测与 V3 的交叉补漏（v2.4，修复后干净日志验证）](#88-2026-08-14-系统实测与-v3-的交叉补漏v24修复后干净日志验证)

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

> 💡 **重要发现**：`backup_camera_ids` 默认值是 `[40, 41, 42, 43]`，与项目记忆中「优先使用 /dev/video40 和 /dev/video41」的约定**完全吻合**。这说明库本身就内置了这些设备号作为备份探测顺序，无需应用层手动指定。

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
| `add_detection_callback(cb)` | `cb: Callable[[Dict], None]` | 每次检测完成时，回调接收检测结果字典（**实测 ~10次/秒**） |
| `add_frame_callback(cb)` | `cb: Callable[[np.ndarray, Dict], None]` | 每帧都调用，接收画面帧+检测结果 |
| `add_error_callback(cb)` | `cb: Callable[[Exception], None]` | 检测线程内部抛出异常时回调 |
| `remove_callback(callback_type, callback)` | `(str, Callable)` | 移除已注册的回调 |

> **2026-08-14 实测确认**：detection 回调接收的 Dict 含 14 个算法结果字段 + timestamp：
> ```python
> {
>   'apriltag': [],           # list 型，空时为 []
>   'black_line': {},         # dict 型，空时为 {}
>   'color_block': {},
>   'color_recognition': {},
>   'face_recognition': {},
>   'qr_code': [],            # list 型，空时为 []
>   'plate_recognition': {},
>   'object_recognition': {},
>   'people_counter': {},
>   'image_classification': {},
>   'object_detection': {},
>   'pose_detection': {},
>   'facial_expression': {},
>   'timestamp': 1786674893.16  # float, Unix 时间戳
> }
> ```
> frame 回调接收 **2 个参数**：`(ndarray 画面帧, dict 检测结果同上)`

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
| `get_color_block_position(idx)` | `tuple` | (x, y, w, h) 四元组：左上角坐标 + 宽高（实测确认，非仅 (x,y)） |
| `get_color_block_center(idx)` | `tuple` | 中心 (cx, cy) — ⚠️ 实测始终返回 (0,0)，V3 库 bug，见 8.8.5 |
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
| `get_facial_expression_engagement()` | `str` | 二分类字符串 `'Engaged'` / `'Distracted'`（语义：检测到人脸且可分析表情 ≠ 专注屏幕。详细推断见 8.8.3。⚠️ 不要按"投入度等级"理解） |
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
| `CameraConfig.backup_camera_ids` | **`[40, 41, 42, 43]`** | 库内置的备份摄像头 ID 优先级是 40→41→42→43，与项目记忆中「优先 /dev/video40 和 /dev/video41」一致。如需修改顺序，应自定义 `CameraConfig`。 |
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

### 8.8 2026-08-14 系统实测与 V3 的交叉补漏（v2.4，修复后干净日志验证）

> 本节基于「颜色识别探测 + 盲点A 回调系统 + 盲点B 表情投入度」三份日志的**最新实测**编写。
>
> **⚠️ v2.2 中的两条结论已被推翻、必须作废**：
> - ❌ "所有 13 个检测算法字段始终为空" —— 之前的脚本遗漏了 `_init_detectors()` 关键步骤，未加载 RKNN 模型
> - ❌ "人脸/表情识别完全不可用" —— 同一根因
>
> **正确初始化流程（6 步，严格按范例代码）**：
> 1. `vs = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)`
> 2. `vs.open_camera()`
> 3. `vs.detection_config.enable_XXX = True`（逐算法启用）
> 4. **`vs._init_detectors()` ← 之前漏掉，这才是真正加载 RKNN 模型的步骤**
> 5. （仅 color_recognition 需要）`vs.detection_config.color_recognition_regions.append((x, y, w, h))` —— 坐标必须在 **640×480** 范围内（见下文陷阱）
> 6. `vs.threaded_system.start_background_detection(show_preview=True)`
> 7. 每次读结果前：`vs.result_accessor.refresh_results()`

#### 8.8.1 检测算法实测总表

| 算法 | 可用？ | 返回结构（callback dict 字段） | result_accessor 对应方法 | 陷阱与说明 |
|------|--------|-------------------------------|------------------------|-----------|
| **face_recognition**（人脸识别） | ✅ 可用 | `{success:bool, face_id:None\|str, confidence:float 0~1, face_position:(x,y,w,h), message:'未找到匹配的人脸' \| 注册名}` | `get_face_count()`, `get_face_confidence()`, `get_face_position()`, `get_face_name()`, `get_face_id()`, `has_face_id(requires 2 args)` | face_id=None 时 name=`'ID_None'`，message=`'未找到匹配的人脸'`；未注册人脸库时仅返回人脸位置 |
| **facial_expression**（表情识别） | ✅ 可用 | `{success:bool, emotions:{8 种情绪置信度}, engagement:{Distracted:float, Engaged:float}, inference_time:float s}` | `get_facial_expression_emotion()`, `get_facial_expression_emotions_confidence()`, `get_facial_expression_engagement()`, `get_facial_expression_engagement_confidence()`, `get_facial_expression_success()`, `get_facial_expression_inference_time()` | engagement 是**分类字符串** `'Engaged'` / `'Distracted'`（非 float）；情绪 8 类：Anger/Contempt/Disgust/Fear/Happiness/Neutral/Sadness/Surprise；推理 ~6ms |
| **color_block**（颜色块检测） | ✅ 可用 | `{image_info:{w,h,c}, detection_params:{target_color:'红色',min_w:30,min_h:30,similarity:0.5}, color_blocks:[{id,position:{x,y,w,h},center:{x,y},area:int像素²,color_label:'红色'}], total_blocks:int}` | `get_color_block_count()`, `get_color_block_color(i)`, `get_color_block_position(i)`, `get_color_block_center(i)`, `get_color_block_area(i)`, `has_color_block()`, `get_largest_color_block_index()` | **默认目标颜色 = '红色'**，要检测其他颜色需改 `detection_config.color_block_target_color`（枚举值待查） |
| **color_recognition**（区域颜色识别） | ✅ 可用 | `{image_info:{w:640,h:480,c:3}, regions:[{name:'区域_N', region:(x,y,w,h), error:'None'或'无效的区域坐标...', rgb:None或(r,g,b), hex:None或'#RRGGBB', color_label:None或中文颜色名}], total_regions:int, successful_regions:int, basic_colors:[], color_threshold:{}}` | `get_color_recognition_count()`, `get_color_recognition_name(i)`, `get_color_recognition_color(i)`, `get_color_recognition_rgb(i)` | ⚠️ **重大坐标陷阱**：即使创建时 `width=1280 height=720`，内部实际处理分辨率仍是 **640×480**（callback 中 image_info 可证明）。区域坐标必须按 640×480 设置，否则报错「无效的区域坐标」 |
| **qr_code**（二维码） | ❓ 未验证（用户测试时未明确出示可识别的二维码） | `[]` 空 list 时表示无结果（回调 dict 结构为 list，不同于 dict 型算法） | — | 参考范例代码 5.03 二维码识别；需用户专门跑一次测试；失败时可 fallback `cv2.QRCodeDetector()` |
| **apriltag** | ❓ 未验证（本批次脚本未启用） | `[]` | — | 参考范例代码 5.01/5.02 标签识别；可用 `dt-apriltags`（33.8 FPS）作为替代 |
| **black_line / color_block 差异** | ✅ color_block 已工作，black_line 未测 | black_line: `{}` 空 dict | — | 参考范例代码 5.07 黑线检测 |
| **plate_recognition** | ❓ 本批次未启用 | 空 dict | — | 参考范例代码 5.13/5.14 车牌识别 |
| **object_recognition** | ❓ 本批次未启用 | 空 dict | — | 参考范例代码 5.11/5.12 物体识别学习/识别 |
| **object_detection** | ❓ 本批次未启用 | 空 dict | — | 参考范例代码 5.17 目标检测 |
| **people_counter** | ❓ 本批次未启用 | 空 dict | — | 参考范例代码 5.16 人流计数 |
| **image_classification** | ❓ 本批次未启用 | 空 dict | — | 参考范例代码 5.15 图像分类 |
| **pose_detection** | ❓ 本批次未启用 | 空 dict | — | 参考范例代码 5.18 姿态检测 |

#### 8.8.2 环境层已知点

| 项 | 实测值 | 对 V3 开发的影响 |
|----|-------|----------------|
| cv2 版本 | **5.0.0**（非 4.x） | V3 内部封装了 cv2，但应用层若混用 `cv2.xxx`，注意 4.x→5.0 的 API 变更。**实测确认**：`findContours` 返回 **2 值** (contours, hierarchy) 而非 4.x 的 3 值；缺失子模块: tracking/video/videoio/photo/stitching/calib3d/features2d/objdetect；可用子模块: aruco/dnn/cuda/face/xfeatures2d/ximgproc/ml/img_hash/phase_unwrapping。所有常量和 45 个常用函数均存在。 |
| USB 摄像头设备号 | **/dev/video40、/dev/video41、/dev/video42**（uvcvideo 驱动，video0~39 为 MIPI/ISP 内部节点） | 探测顺序 **40→41→42**。`CameraConfig.backup_camera_ids` 默认 [40,41,42,43] 与此一致。**`open_camera()` 无参数** — 摄像头 ID 由 CameraConfig 自动探测，不能传 `open_camera(40)`（会报 `takes exactly 1 positional argument (2 given)`）。 |
| LIBGL_ALWAYS_SOFTWARE | 系统**全局未设置** | V3 内部若用 GL（部分 RKNN 显示路径）可能触发 GPU 驱动崩溃。所有 V3 程序开头统一加：`import os; os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'`（在 pygame/cv2 导入之前）。 |
| AprilTag 备选方案 | `dt-apriltags 3.1.7` 已 pip 安装，**实测 33.8 FPS** | 若仅需 AprilTag 识别而不需要 V3 其他算法，**可直接 `from dt_apriltags import Detector` + 纯 cv2 模式**，避免启动 V3 的算法初始化开销。 |
| pandas 库状态 | 当前版本与 numpy 1.24.4 不兼容，import 直接崩 | V3 本身不依赖 pandas。但如果业务层需要分析 V3 输出（CSV / Excel），必须先执行 `python3 -m pip install -U pandas==2.0.3`。 |
| NPU Python 绑定 | `librknnrt.so` 已装（7.7MB）但 rknnlite2 Python 模块**缺失** | V3 的 RKNN 模型推理走内部 C 绑定（`_init_detectors()` 触发加载），**不依赖 rknnlite2 Python 包**，所以 V3 正常工作无需额外安装。仅当你要用自己的 .rknn 模型绕过 V3 直接推理时，才需要单独装匹配版本的 rknnlite2 whl。 |
| 回调系统实测 | 4 个方法: `add_detection_callback` / `add_error_callback` / `add_frame_callback` / `remove_callback` | **注意是 `add_*` 不是 `set_*`**。注册方式: `ts.add_detection_callback(my_callback)`。detection 回调接收 **1 个 dict 参数**，含 14 个算法结果字段 + timestamp。回调频率 ~10~17 次/秒。frame 回调接收 **2 个参数** (ndarray 480×640×3, dict)。 |
| 性能基准 (640×480) | MediaPipe Hands **15.6 FPS** (+51.0MB), Pose **14.7 FPS** (+54.1MB), dt-apriltags **33.5 FPS** (+0MB) | V3 全托管模式 + 后台检测线程：color_block 推理 ~6ms，多算法并行总 FPS 未知。纯 cv2 + MediaPipe Hands 可达 15-19fps。如需高帧率实时交互，优先用纯 cv2 模式。 |
| Swap | **无 Swap** (SwapTotal=0), MemAvailable=5.7GiB | 单程序开发无 OOM 风险。同时跑 V3 + MediaPipe + TTS 峰值约 600MB，远低于可用内存。 |
| result_accessor 实测 | `CompleteDetectionResultAccessor` 类型，11 个表情/人脸方法 + 12 个 color 方法 | **engagement 返回 string**（'Engaged'/'Distracted'，非 float）；**emotion 返回 string**（8 类之一）；**confidence / emotions_confidence 返回 dict**。所有方法调用前必须先 `refresh_results()`。 |

#### 8.8.3 engagement 语义推断（基于 B 脚本实测）

盲点 B 脚本用 3 个阶段测试了 engagement 的变化：

| 阶段 | user 动作 | engagement 分布（共 19 次） | 情绪分布 | engagement_confidence |
|------|----------|--------------------------|---------|----------------------|
| phase1 正视屏幕 10s | 正对摄像头，自然表情 | **Engaged 19/19 (100%)** | Neutral 19 | Engaged 0.57 / Distracted 0.43 |
| phase2 看向旁边 10s | 头转向左/右，不看屏幕 | **Engaged 19/19 (100%)** | Neutral 13, Anger 6 | Engaged 0.55 / Distracted 0.45 |
| phase3 闭眼/低头 10s | 闭眼或低头看桌面 | **Engaged 19/19 (100%)** | Sadness 16, Neutral 3 | Engaged 0.55 / Distracted 0.45 |

**语义推断**：`engagement` 并非"专注度"或"是否在看屏幕"，而是更宽泛的**二分类**：
- **`'Engaged'`** ≈ 检测到了人脸 + 面部五官足以判断情绪（即使闭眼/侧脸，只要人脸框存在就判为 Engaged）
- **`'Distracted'`** ≈ 未检测到人脸 / 人脸太小 / 面部信息严重缺失

**证据**：3 个阶段 engagement 始终是 Engaged，因为 user 的脸一直被检测到（`face_count` 全程 = 1）。engagement_confidence 始终接近 50/50（Engaged ~0.55, Distracted ~0.45），区分度极低。**如果要检测"是否正视屏幕"这个语义，不能依赖 engagement**，必须自己组合：face_position 是否在画面中心区域 + emotion/pose 的头部朝向估计（V3 pose_detection 可以提供头部姿态，但本批次未启用）。

**emotion 有明显区分度**（engagement 没有的）：正视→Neutral 主导，看旁→Anger 出现，闭眼低头→Sadness 主导。**实际项目中优先使用 emotion 而非 engagement 做状态判断**。

**engagement 的实际用途**：判断"当前帧是否有人脸 + 是否足以做情绪判断"，而不是判断"是否专注"。建议用 `engagement = 'Engaged'` 作为情绪数据可信度的过滤条件。

---

#### 8.8.4 回调系统实测（A 脚本验证）

| 验证项 | 结果 |
|--------|------|
| detection 回调触发 | 226 次（15秒，~15次/秒）✅ |
| frame 回调触发 | 226 次（与 detection 等频）✅ |
| error 回调触发 | 0 次（无错误时静默）✅ |
| detection 回调参数 | `dict`，14 keys（apriltag/black_line/color_block/color_recognition/face_recognition/qr_code/plate_recognition/object_recognition/people_counter/image_classification/object_detection/pose_detection/facial_expression/timestamp） |
| frame 回调参数 | `(ndarray(480,640,3), dict)`，dict 与 detection 回调结构相同 |
| 回调注册方法 | `add_detection_callback(cb)` / `add_frame_callback(cb)` / `add_error_callback(cb)` / `remove_callback(cb)` |

#### 8.8.5 已知 V3 库 bug

| bug | 表现 | 规避方法 |
|-----|------|---------|
| `get_color_block_center(idx)` 始终返回 `(0, 0)` | 即使 `position` 有效（如 (578,154,62,74)），center 仍为 (0,0) | 手动计算：`cx = x + w//2, cy = y + h//2`（从 `get_color_block_position()` 获取 x,y,w,h） |

---

#### 8.8.6 剩余未探测盲点记录

> 以下盲点在以后项目开发时再探测，此处记录供参考。

**P0 级（直接影响常用功能开发）**：

| # | 盲点 | 现状 | 范例代码参考 |
|---|------|------|------------|
| P0-1 | qr_code 能否真识别出二维码内容 | 只确认空时返回 `[]` | 5.03 二维码识别 |
| P0-2 | color_block_target_color 可接受的枚举值 | 默认值 `'红色'`，如何改为蓝色/绿色/黄色未知 | 5.06 色块识别 |
| P0-3 | get_color_recognition_color(i) 完整标签枚举 | 已观测到 5 种：蓝色/黄色/绿色/红色/其他颜色 | 5.04 颜色识别 |
| P0-4 | 运行时新增算法后是否必须重新调 `_init_detectors()` | 颜色脚本在新增 color_block 时重新调了 | — |
| P0-5 | has_face_id(face_id) 具体返回行为 | 只知道签名 `has_face_id(self, face_id)` | 5.10 人脸识别 |
| P0-6 | get_largest_color_block_index() 空场景行为 | 未测 | 5.06 色块识别 |
| P0-7 | remove_callback() 正确用法 | 只知道方法名 | — |
| P0-8 | get_latest_results()/get_next_result()/get_all_pending_results() 返回结构 | 只反射出方法名 | — |

**P1 级（重要算法/API 行为确认）**：

| # | 盲点 | 范例代码参考 |
|---|------|------------|
| P1-1 | apriltag V3 内置识别返回结构 | 5.01/5.02 标签识别 |
| P1-2 | black_line 巡线检测返回结构 | 5.07 黑线检测 |
| P1-3 | pose_detection 姿态返回结构 | 5.18 姿态检测 |
| P1-4 | object_recognition 自定义物体识别完整流程 | 5.11/5.12 物体识别学习/识别 |
| P1-5 | VoiceAPI 两个 LLM 后端差异 | 4.04/4.05/4.06 大模型对话 |

**P2 级（场景化扩展，等需求出现再探测）**：

| # | 盲点 | 范例代码参考 |
|---|------|------------|
| P2-1 | plate_recognition 车牌识别 | 5.13/5.14 车牌识别 |
| P2-2 | people_counter / image_classification / object_detection | 5.15/5.16/5.17 |
| P2-3 | RKNN Python 绑定 (rknnlite2) 安装 + 自定义模型部署 | — |
| P2-4 | pandas / ultralytics 安装状态 | — |
| P2-5 | ESP32 I2C / UART 扩展稳定性 | — |
| P2-6 | Line_Sensor 巡线模块硬件接线 + 返回结构 | — |

> **注意**：表中"范例代码 5.xx"对应 `好搭AI派范例代码.md` 中的范例编号，可作为探测时的参考代码。

---

*报告版本 v2.4 — 2026-08-14 更新：基于修复后三份干净日志（零错误），更新 engagement 表格数据+confidence列，新增 8.8.4 回调系统实测总表和 8.8.5 已知 bug 表，修正 5.5 position/center 描述和 5.8 engagement 描述，为 8.8.1 未验证算法标注范例代码参考，新增 8.8.6 剩余盲点记录。配套日志：`logs/logs_探测_颜色识别_*.txt`、`logs/logs_探测_盲点A_回调系统_*.txt`、`logs/logs_探测_盲点B_表情投入度_*.txt`*
