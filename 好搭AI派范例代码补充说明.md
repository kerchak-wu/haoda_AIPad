# 好搭AI派范例代码补充说明

> **适用文件**：`好搭AI派范例代码.md`（原文件不修改，本文件为其补充）
> **创建日期**：2026-08-14
> **数据来源**：颜色识别探测、盲点A回调系统探测、盲点B表情投入度探测三份干净日志
> **配套日志**：`logs/logs_探测_颜色识别_20260814.txt`、`logs/logs_探测_盲点A_回调系统_20260814.txt`、`logs/logs_探测_盲点B_表情投入度_20260814.txt`

---

## 一、原范例代码存在的问题

### 1.1 严重问题（会导致运行时报错）

#### A. 颜色识别范例的 color_recognition_regions 坐标全部超范围

**涉及范例**：5.AI视觉算法 04.颜色识别、05.颜色识别-自动分拣

**问题代码**：
```python
vision_system.detection_config.color_recognition_regions.append((300, 200, 400, 400))  # x+w=700>640
vision_system.detection_config.color_recognition_regions.append((800, 200, 400, 400))  # x=800>640
```

**错误原因**：尽管 `create_vision_system_v3` 传 `width=1280, height=720`，V3 内部实际处理分辨率是 **640×480**（从三份日志的 `color_recognition.image_info.width/height=640/480` 实锤确认）。范例代码按 1280×720 空间写坐标，导致：
- 每个 region 的 `error` 字段为 `"无效的区域坐标: (...)"`
- `get_color_recognition_color()` 永远返回 `None`
- 后续 `get_color_recognition_rgb(0)` 解包 None 时触发 `TypeError: 'NoneType' object is not iterable`

**正确写法**（用 640×480 空间坐标）：
```python
vision_system.detection_config.color_recognition_regions.append((50, 100, 200, 200))   # 左侧: 50+200=250≤640
vision_system.detection_config.color_recognition_regions.append((390, 100, 200, 200))  # 右侧: 390+200=590≤640
```

#### B. 颜色识别范例在 color=None 时未做保护

范例直接 `print(get_color_recognition_rgb(0))`，当坐标超范围 color 为 None 时，rgb 也是 None，打印会乱。应先检查 color 是否为 None，为 None 时跳过 rgb 读取。

#### C. 颜色识别范例 L1013 有笔误

```python
print((vision_system.result_accessor.get_color_recognition_color(1)))  # 应该是 _name(1) 或 _rgb(1)
```

第 2 区域第 3 次调用重复了 `_color`，疑似将 `get_color_recognition_name(1)` 误写为 `_color`。不报错但输出信息不完整。

---

### 1.2 中等问题（硬件特性缺失，可能崩溃）

#### D. 所有范例代码缺少 Rockchip 平台兼容性补丁

- **缺少 `LIBGL_ALWAYS_SOFTWARE=1`**：范例顶部没有写 `import os; os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'`。如果程序用了 pygame/cv2，在 Rockchip RK3588S 平台上可能触发 Mali GPU 驱动段错误。
- **使用 `pygame.init()` 全初始化**：部分 pygame 相关范例（如人脸学习、物体学习）用了 `pygame.init()`，应改为 `pygame.display.init()` + `pygame.font.init()`，避免音频子系统异常。
- **GPIO_BUTTON=0 相关代码保留**：范例中的板载按键（GPIO_IO_00）读取代码，实际硬件没有对应实体按键，可删除相关代码。

---

### 1.3 初始化流程正确的部分

**范例代码的 V3 初始化顺序整体正确**：

```
create_vs(enable_basic=False, enable_advanced=False)
  → open_camera()
  → detection_config.enable_color_recognition = True
  → _init_detectors()
  → color_recognition_regions.append(...)
  → start_background_detection()
  → result_accessor.refresh_results() + get_xxx()
```

这个顺序与三份日志验证通过的顺序完全一致。唯一需要修正的就是**第 4 步 append 的坐标空间**。

---

### 1.4 原文件中已删除的补充更新与关键差异提醒原文

> 以下内容原位于《好搭AI派范例代码.md》顶部，2026-08-14 按用户指示从原文件中删除并迁移至此完整保存，供以后项目开发参考。原范例代码文件保持纯净，不再包含任何补充/提醒内容。
> 本节为原文照录，下方第二章为基于三份干净日志的复核结果，第三章为最新探测发现。

**📌 2026-08-14 补充更新**：本文档的范例是早期参考资料，**实际项目开发请优先参照《系统环境与非视觉官方库探测报告_v1.md》** 中反射枚举得到的**完整 ESP32 类 50+ 方法 + GPIO 常量清单**，以及 voice_api / AudioRecorder / AudioPlayer / TextRecognizer / Line_Sensor 的全部签名。

**⚠️ 关键差异提醒**（基于 2026-08-14 探测结果）：
- **USB 摄像头设备号**：范例代码中写的视频设备号不固定，好搭AI派实测可能出现在 **/dev/video40、/dev/video41、/dev/video42**（uvcvideo 驱动），video0~39 是 MIPI/ISP 内部节点。**不能只检测 /dev/video40**，应按 40→41→42 顺序逐个尝试 + `gray.mean()` 帧有效性验证
- **OpenCV 版本**：范例可能基于 4.x，实际装的是 **cv2 5.0.0**，部分旧 API 有变更
- **LIBGL_ALWAYS_SOFTWARE**：系统全局未设置，每个程序开头必须写 `import os; os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'`
- **GPIO_BUTTON = 0 忽略**：范例中的板载按键读取，实际硬件无对应实体按键，可删除相关代码
- **ESP32 隐藏能力**：范例代码只覆盖部分方法，实际还有 I2C、UART、BMP280 气压传感器、WS2812 等 50+ 方法，详见探测报告
- **dt-apriltags**：pip 已装 `dt-apriltags 3.1.7`，纯 cv2 模式下 AprilTag 识别不用依赖 V3 SDK

---

## 二、原范例代码补充更新内容复核

原文件顶部已写入的 2026-08-14 补充更新和关键差异提醒，经三份日志复核，确认无误的内容如下：

| 条目 | 复核结果 |
|------|---------|
| USB 摄像头设备号 /dev/video40、41、42 | ✅ 正确，三份日志均通过 backup_camera_ids 自动探测成功 |
| cv2 5.0.0（非 4.x） | ✅ 正确，日志 L3 确认 Python 3.8.10 + cv2 5.0.0 |
| LIBGL_ALWAYS_SOFTWARE 全局未设置 | ✅ 正确，三个探测脚本均在开头显式设置 |
| GPIO_BUTTON=0 无实体按键 | ✅ 正确，用户确认忽略 |
| ESP32 隐藏能力（I2C/UART/BMP280/WS2812 等 50+ 方法） | ✅ 正确，详见系统环境与非视觉官方库探测报告 |
| dt-apriltags 3.1.7 已预装 | ✅ 正确，纯 cv2 模式下可直接 import 使用 |

---

## 三、基于最新探测结果的补充发现

### 3.1 V3 初始化关键步骤：`_init_detectors()` 不可遗漏

范例代码中正确调用了 `_init_detectors()`，但之前探测脚本曾遗漏此步骤，导致所有检测算法返回空。经三份日志确认：**`_init_detectors()` 是真正加载 RKNN 模型的步骤，漏调=所有检测器空**。

正确初始化 7 步流程：
```
Step 1: create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)
Step 2: vs.open_camera()
Step 3: vs.detection_config.enable_XXX = True
Step 4: vs._init_detectors()                    ← 关键，漏调=检测器全空
Step 5: （仅 color_recognition）color_recognition_regions.append((x,y,w,h))  ← 640×480 坐标
Step 6: vs.threaded_system.start_background_detection(show_preview=True)
Step 7: vs.result_accessor.refresh_results()     ← 每次 get_xxx() 前必调
```

### 3.2 color_recognition 实测返回结构

```python
{
    'image_info': {'width': 640, 'height': 480, 'channels': 3},
    'regions': [
        {
            'name': '区域_1',
            'region': (50, 100, 200, 200),
            'error': 'None',              # 坐标越界时为 '无效的区域坐标: ...'
            'rgb': (193, 193, 173),       # None 时表示识别失败
            'hex': '#c1c1ad',
            'area': 40000,
            'position': {'x': 50, 'y': 100, 'width': 200, 'height': 200},
            'color_label': '其他颜色',     # 已观测到：蓝色/黄色/绿色/红色/其他颜色
            'closest_basic_color': '其他颜色'
        }
    ],
    'total_regions': 2,
    'successful_regions': 2,
    'basic_colors': [],
    'color_threshold': {}
}
```

### 3.3 color_block 实测返回结构

```python
{
    'image_info': {'width': 640, 'height': 480, 'channels': 3},
    'detection_params': {
        'target_color': '红色',       # 默认值，如何修改待探测
        'min_width': 30,
        'min_height': 30,
        'similarity_threshold': 0.5
    },
    'color_blocks': [
        {
            'id': 0,
            'position': {'x': 578, 'y': 154, 'width': 62, 'height': 74},
            'center': {'x': 0, 'y': 0},    # ⚠️ 始终为 (0,0)，V3 库 bug
            'area': 4588,
            'color_label': '红色'
        }
    ],
    'total_blocks': 1
}
```

**已知 bug**：`get_color_block_center(idx)` 始终返回 `(0, 0)`，即使 `position` 有效。规避方法：手动从 position 计算 `cx = x + w//2, cy = y + h//2`。

### 3.4 face_recognition 实测返回结构

```python
{
    'success': True,
    'face_id': None,               # 未注册时为 None
    'confidence': 0.5708712600089131,
    'face_position': (94, 3, 546, 480),   # (x, y, w, h) 四元组
    'message': '未找到匹配的人脸'          # 注册后为注册名
}
```

### 3.5 facial_expression 实测返回结构

```python
{
    'success': True,
    'emotions': {
        'Anger': 0.088, 'Contempt': 0.043, 'Disgust': 0.010,
        'Fear': 0.024, 'Happiness': 0.002, 'Neutral': 0.504,
        'Sadness': 0.233, 'Surprise': 0.096
    },
    'engagement': {'Distracted': 0.436, 'Engaged': 0.564},
    'inference_time': 0.006719                    # 秒，约 6ms
}
```

**engagement 语义警告**：
- `get_facial_expression_engagement()` 返回 `'Engaged'` 或 `'Distracted'`（字符串）
- 三阶段实测（正视/看旁/闭眼低头）**全部返回 Engaged**，confidence 始终 ~50/50
- engagement 含义是「检测到人脸且可分析表情」，**不等于「是否看着屏幕」**
- 实际项目应优先用 `emotion`（8 分类）做状态判断：正视→Neutral、看旁→Anger、闭眼低头→Sadness

### 3.6 回调系统实测

| 回调方法 | 触发次数（15秒） | 参数 |
|---------|----------------|------|
| detection 回调 | 226 次（~15次/秒） | `dict`，14 keys |
| frame 回调 | 226 次（等频） | `(ndarray(480,640,3), dict)` |
| error 回调 | 0 次（无错误时静默） | `Exception` |

detection dict 的 14 keys：`apriltag`、`black_line`、`color_block`、`color_recognition`、`face_recognition`、`qr_code`、`plate_recognition`、`object_recognition`、`people_counter`、`image_classification`、`object_detection`、`pose_detection`、`facial_expression`、`timestamp`。

list 型算法（apriltag/qr_code）空时返回 `[]`，dict 型算法空时返回 `{}`。

### 3.7 pygame 窗口高度计算

640×480 画面 + 顶部标题(36) + 底部指引(28) + 底部状态行(54) ≈ **640×620** 是安全尺寸，低于此值会裁剪底部文字。

### 3.8 日志输出规范

所有日志必须输出到项目根 `logs/` 目录：
```python
import os
_log_dir = 'logs'
if not os.path.exists(_log_dir):
    os.makedirs(_log_dir)
LOG_FILE = '%s/<程序名>_%s.txt' % (_log_dir, datetime.datetime.now().strftime('%Y%m%d'))
```

日志文件应使用**追加模式**（`'a'`）打开，同一程序多次运行追加到当天日志：
```python
_log_fp = open(LOG_FILE, 'a', encoding='utf-8')
```

---

## 四、各范例的适用性评估

| 范例编号 | 范例名称 | 初始化流程 | 已知问题 | 可否直接使用 |
|---------|---------|-----------|---------|------------|
| 5.01 | 标签识别 | ✅ 正确 | 需补 LIBGL + pygame 分段初始化 | 可用，需补补丁 |
| 5.02 | 标签识别-超市自助收银 | ✅ 正确 | 同上 | 可用，需补补丁 |
| 5.03 | 二维码识别 | ✅ 正确 | 同上；qr_code 回调返回结构待验证 | 可用，需补补丁 |
| 5.04 | 颜色识别 | ⚠️ 坐标错误 | 区域坐标用了 1280×720 空间；L1013 笔误 | ❌ 需修正坐标后使用 |
| 5.05 | 颜色识别-自动分拣 | ⚠️ 坐标错误 | 同上 | ❌ 需修正坐标后使用 |
| 5.06 | 色块识别 | ✅ 正确 | center 始终返回 (0,0) | 可用，需补补丁+注意 center bug |
| 5.07 | 黑线检测 | ✅ 正确 | black_line 返回结构待验证 | 可用，需补补丁 |
| 5.08-09 | 人脸学习 | ✅ 正确 | 需补 LIBGL + pygame 分段初始化 | 可用，需补补丁 |
| 5.10 | 人脸识别 | ✅ 正确 | 同上 | 可用，需补补丁 |
| 5.11-12 | 物体识别 | ✅ 正确 | 同上 | 可用，需补补丁 |
| 5.13-14 | 车牌识别 | ✅ 正确 | 同上 | 可用，需补补丁 |
| 5.15 | 图像分类 | ✅ 正确 | 同上 | 可用，需补补丁 |
| 5.16 | 人流计数 | ✅ 正确 | 同上 | 可用，需补补丁 |
| 5.17 | 目标检测 | ✅ 正确 | 同上 | 可用，需补补丁 |
| 5.18 | 姿态检测 | ✅ 正确 | 同上 | 可用，需补补丁 |
| 5.19-21 | 文字识别 | ✅ 正确 | text_recognition 导入顺序需注意 | 可用，需补补丁+注意导入顺序 |

---

*本文件为 `好搭AI派范例代码.md` 的补充说明，原文件不做任何修改。*
*创建日期：2026-08-14*
*配套日志：`logs/logs_探测_颜色识别_20260814.txt`、`logs/logs_探测_盲点A_回调系统_20260814.txt`、`logs/logs_探测_盲点B_表情投入度_20260814.txt`*
