# -*- coding: utf-8 -*-
"""
物体学习程序 - 好搭AI派
======================
功能说明：
  1. USB外接摄像头实时采集画面（由视觉系统 open_camera + capture_frame 管理）
  2. 输入物体名称标签，将当前画面学习为该物体类别/样本
  3. 同一物体可多次学习（多角度/多实例），增强识别鲁棒性
  4. 界面显示摄像头画面、学习状态和已学习物体列表
  5. 物体记录持久化到 JSON 文件，重启后自动加载并继续学习
  6. 可选择删除已学习的物体记录（仅删应用层，不破坏视觉系统模型）
  7. 提供 ObjectLearner 类，可供其他程序导入调用

硬件接线：
  - USB外接摄像头(/dev/video41 或 /dev/video40)
  - 好搭AI派扩展板(ESP32)
  注意：好搭AI派右下角开关需拨到左侧以启用外设接口。

依赖库：
  pygame, cv2(opencv, 仅用于图像格式转换), numpy, ESP32,
  camera_vision_system_v3(好搭AI派自带)

参考范例：
  - 范例代码 5.11 物体识别学习（add_object_recognition_class / sample）
  - 范例代码 5.12 物体识别（result_accessor 获取结果）
  - 人脸学习.py（FaceLearner 类结构与持久化模式）
  - 人脸识别灯效.py（视觉系统 open_camera + capture_frame + 后台检测线程模式）

重要约束：
  - 完全基于外接USB摄像头实时画面学习，不从 images 文件夹读取图片。
  - 物体学习必须 open_camera + start_background_detection（add_object_recognition_sample
    使用视觉系统当前捕获的帧），与人脸学习 learn_new_face(frame=...) 不同。
  - 因此不能使用 cv2 VideoCapture，必须用 vision_system.capture_frame() 获取帧
    用于界面显示，避免与视觉系统的 V4L2 设备冲突。
  - 采集线程固定 0.15s 睡眠，frame_lock 保护 raw_frame 读写。

模块调用示例：
  from 物体学习 import ObjectLearner
  learner = ObjectLearner()
  learner.learn_current_frame('水杯')   # 用当前USB摄像头帧学习/添加样本
  objects = learner.get_learned_objects()
  learner.delete_object(0)
  learner.close()
"""

import json
import time
import signal
import threading
import sys

import pygame
import cv2
import numpy as np

from ESP32 import *
from camera_vision_system_v3 import create_vision_system_v3


# ===================== 日志输出（控制台 + 文件）=====================
# 把所有 print 输出同时写入 logs/ 目录下的日志文件，方便在好搭AI派上导出排查
# 注意：
#   1. 日志统一存到 logs/ 文件夹，避免散落在项目根目录
#   2. 文件名含程序名+日期时间，不会覆盖上次的日志
#   3. 用追加模式 'a'，同一程序多次运行追加到当天日志
#   4. 用块缓冲(buffering=-1)而非行缓冲，避免后台检测线程高频写日志阻塞主循环
import os as _os
import datetime as _datetime
_LOG_DIR = 'logs'
if not _os.path.exists(_LOG_DIR):
    try:
        _os.makedirs(_LOG_DIR)
    except Exception:
        pass
_LOG_FILE = _os.path.join(
    _LOG_DIR,
    '物体学习_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
)
_debug_log_fp = open(_LOG_FILE, 'a', encoding='utf-8', buffering=-1)
# 写入分隔标记，区分不同次运行
_debug_log_fp.write('\n\n======== %s 运行开始 ========\n' %
                    _datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
_debug_log_fp.flush()


class _TeeStdout:
    """同时写入控制台和日志文件的 stdout 包装"""

    def __init__(self, original):
        self.original = original

    def write(self, msg):
        self.original.write(msg)
        try:
            _debug_log_fp.write(msg)
        except Exception:
            pass

    def flush(self):
        self.original.flush()
        try:
            _debug_log_fp.flush()
        except Exception:
            pass


sys.stdout = _TeeStdout(sys.stdout)
sys.stderr = _TeeStdout(sys.stderr)


# ===================== 配置 =====================
WIDTH, HEIGHT = 1920, 1080

# 字体路径（好搭AI派系统字体）
FONT_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'

# 摄像头配置（视觉系统内部使用，这里仅用于显示与分辨率标注）
CAMERA_W, CAMERA_H = 1280, 720
CAM_DISP_W, CAM_DISP_H = 880, 660

# 物体记录持久化文件
OBJECT_DATA_FILE = 'object_records.json'

# ---- 界面配色（浅色系）----
BG_TOP = (135, 206, 235)        # 天空蓝
BG_BOTTOM = (220, 240, 255)    # 浅蓝白
PANEL_COLOR = (255, 255, 255)   # 白色面板
PANEL_BORDER = (100, 149, 237)  # 矢车菊蓝
TITLE_COLOR = (25, 60, 130)     # 深蓝
TEXT_COLOR = (50, 50, 60)       # 深灰
SUBTLE_COLOR = (120, 130, 150)  # 灰色
ACCENT_COLOR = (255, 140, 0)    # 橙色
SUCCESS_COLOR = (60, 180, 80)   # 绿色
ERROR_COLOR = (220, 80, 80)     # 红色
EXIT_COLOR = (220, 80, 80)
EXIT_HOVER = (255, 100, 100)
LEARN_COLOR = (60, 130, 255)
LEARN_HOVER = (80, 150, 255)
DEL_COLOR = (220, 80, 80)
DEL_HOVER = (255, 100, 100)
INPUT_BG = (240, 248, 255)
INPUT_BORDER = (100, 149, 237)
INPUT_ACTIVE_BORDER = (60, 130, 255)


# ===================== 硬件初始化 =====================
# 严格参照范例代码：ESP32 初始化 + 异常处理
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")


# ===================== ObjectLearner 物体学习器 =====================
# 供其他程序调用的物体学习接口
class ObjectLearner:
    """物体学习器，封装视觉系统的物体识别学习功能

    使用方式：
        learn_current_frame(name)：用当前USB摄像头帧学习/添加样本
          - 若该类别未创建，则先用 add_object_recognition_class 创建类别
          - 若该类别已创建，则用 add_object_recognition_sample 添加样本

    注意：物体学习必须 open_camera + start_background_detection，
    因为 add_object_recognition_sample 使用视觉系统当前捕获的帧。
    因此本类内部管理摄像头，不使用 cv2 VideoCapture。

    其他程序可通过以下方式调用：
        from 物体学习 import ObjectLearner
        learner = ObjectLearner()
        learner.learn_current_frame('水杯')
        objects = learner.get_learned_objects()
        learner.delete_object(0)
        learner.close()
    """

    def __init__(self, width=1280, height=720):
        self._lock = threading.RLock()
        self._learned_objects = []  # [{name, sample_count, first_learned, last_learned}, ...]
        self._classes_created = set()  # 已调用 add_object_recognition_class 创建的类别名集合

        # 加载持久化记录
        self._load_records()

        # 创建视觉系统并启动后台检测（严格参照范例 5.11）
        self._init_vision_system(width, height)

        # 启动后台采集线程（用于界面显示，不影响后台检测）
        self._raw_frame = None
        self._frame_lock = threading.Lock()
        self._capture_running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _init_vision_system(self, width=1280, height=720):
        """创建并初始化视觉系统（严格参照范例代码 5.11）

        流程：create_vision_system_v3 → 启用 object_recognition → _init_detectors
              → open_camera → start_background_detection(show_preview=False)
        """
        self.vision_system = create_vision_system_v3(
            camera_id=-1, width=width, height=height,
            enable_basic=False, enable_advanced=False
        )
        self.vision_system.detection_config.enable_object_recognition = True
        self.vision_system._init_detectors()
        print('object_recognition 算法已启用')

        # 打开摄像头（必须，add_object_recognition_sample 需要当前帧）
        print('正在打开视觉系统摄像头...')
        self.camera_ok = False
        if self.vision_system.open_camera():
            print('视觉系统摄像头已打开')
            self.camera_ok = True
        else:
            print('摄像头打开失败，请检查 /dev/video41 和 /dev/video40')
            return

        # 启动后台检测（show_preview=False，不弹 OpenCV 窗口）
        self.vision_system.threaded_system.start_background_detection(show_preview=False)
        print('物体识别后台检测已启动')

        # 调试：列出可用方法，便于排查
        try:
            vs_methods = [m for m in dir(self.vision_system) if not m.startswith('_')]
            ra_methods = [m for m in dir(self.vision_system.result_accessor) if not m.startswith('_')]
            print('[调试] vision_system 方法: %s' % vs_methods)
            print('[调试] result_accessor 方法: %s' % ra_methods)
        except Exception as e:
            print('[调试] 列举方法失败:', e)

    def _capture_loop(self):
        """后台采集线程：调用 capture_frame() 获取帧用于界面显示

        关键改进（参考人脸识别灯效.py 已验证模式）：
        1. 0.05s 睡眠 ≈ 20fps 采集，保证画面流畅
        2. 帧有效性验证，跳过损坏帧
        3. capture_frame() 只读缓存，不访问 V4L2，与后台检测线程不冲突
        """
        # 启动后等待 0.5s 让后台检测线程先稳定
        time.sleep(0.5)
        while self._capture_running:
            if not self.camera_ok:
                time.sleep(0.3)
                continue
            try:
                frame = self.vision_system.capture_frame()
                if frame is not None and hasattr(frame, 'shape') and len(frame.shape) == 3:
                    with self._frame_lock:
                        self._raw_frame = frame
            except Exception as e:
                if self._capture_running:
                    print('采集帧异常:', e)
            # 0.05s 睡眠 ≈ 20fps 采集，提升画面流畅度
            # capture_frame() 只读缓存不访问 V4L2，与后台检测线程不冲突
            time.sleep(0.05)

    def get_current_frame(self):
        """获取当前摄像头帧的副本（线程安全）"""
        with self._frame_lock:
            return self._raw_frame.copy() if self._raw_frame is not None else None

    # ---- 持久化 ----
    def _load_records(self):
        """从 JSON 文件加载已学习的物体记录"""
        try:
            with open(OBJECT_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with self._lock:
                self._learned_objects = []
                for item in data:
                    self._learned_objects.append({
                        'name': item['name'],
                        'sample_count': item.get('sample_count', 0),
                        'first_learned': item.get('first_learned', ''),
                        'last_learned': item.get('last_learned', ''),
                    })
                    # 视觉系统内部类别会跨重启保留，所以已记录的类别视为已创建
                    self._classes_created.add(item['name'])
            print('已加载 %d 条物体记录' % len(self._learned_objects))
        except FileNotFoundError:
            print('无物体记录文件，从零开始')
        except Exception as e:
            print('加载物体记录失败:', e)

    def _save_records(self):
        """保存物体记录到 JSON 文件"""
        try:
            with self._lock:
                data = [
                    {
                        'name': obj['name'],
                        'sample_count': obj['sample_count'],
                        'first_learned': obj['first_learned'],
                        'last_learned': obj['last_learned'],
                    }
                    for obj in self._learned_objects
                ]
            with open(OBJECT_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print('已保存 %d 条物体记录' % len(data))
        except Exception as e:
            print('保存物体记录失败:', e)

    # ---- 学习 ----
    def learn_current_frame(self, name):
        """用当前摄像头帧学习物体

        流程（严格参照范例 5.11）：
          - 若 name 是新类别：调用 add_object_recognition_class(frame=current_frame, class_name=name)
            创建类别，并记录 sample_count=1
          - 若 name 是已创建类别：调用 add_object_recognition_sample(class_name=name)
            添加样本，sample_count+=1

        Args:
            name: 物体类别名（应用层维护，如 '水杯'）

        Returns:
            dict/str: 学习结果信息（视觉系统返回值），失败返回 None
        """
        if not name:
            return None
        try:
            with self._lock:
                is_new_class = name not in self._classes_created

            if is_new_class:
                # 新类别：用当前帧创建类别
                frame = self.get_current_frame()
                if frame is None:
                    print('学习失败：当前无可用帧')
                    return None
                result = self.vision_system.add_object_recognition_class(
                    frame=frame, class_name=name
                )
                print('创建物体类别 [%s] 结果：%s' % (name, str(result)))
                with self._lock:
                    self._classes_created.add(name)
                    # 查找是否已有同名记录（可能 JSON 丢失但 classes_created 重建）
                    existing = None
                    for obj in self._learned_objects:
                        if obj['name'] == name:
                            existing = obj
                            break
                    now = time.strftime('%Y-%m-%d %H:%M:%S')
                    if existing is None:
                        self._learned_objects.append({
                            'name': name,
                            'sample_count': 1,
                            'first_learned': now,
                            'last_learned': now,
                        })
                    else:
                        existing['sample_count'] = existing.get('sample_count', 0) + 1
                        existing['last_learned'] = now
                self._save_records()
                return result
            else:
                # 已有类别：添加样本（视觉系统使用当前捕获的帧）
                result = self.vision_system.add_object_recognition_sample(
                    class_name=name
                )
                print('添加物体样本 [%s] 结果：%s' % (name, str(result)))
                with self._lock:
                    for obj in self._learned_objects:
                        if obj['name'] == name:
                            obj['sample_count'] = obj.get('sample_count', 0) + 1
                            obj['last_learned'] = time.strftime('%Y-%m-%d %H:%M:%S')
                            break
                self._save_records()
                return result
        except Exception as e:
            print('物体学习异常:', e)
            return None

    # ---- 删除 ----
    def delete_object(self, index):
        """删除指定索引的物体记录

        注意：仅删除应用层记录（object_records.json），不调用视觉系统的删除接口。
        与人脸学习类似，视觉系统内部数据保留不影响识别模型（避免 delete 类接口
        破坏模型导致识别功能完全失效）。

        Args:
            index: 物体记录索引（从 0 开始）

        Returns:
            bool: 删除成功返回 True，索引无效返回 False
        """
        with self._lock:
            if 0 <= index < len(self._learned_objects):
                obj = self._learned_objects.pop(index)
                self._save_records()
                print('已删除应用层物体记录：%s（样本数 %d）' % (
                    obj['name'], obj.get('sample_count', 0)))
                print('注意：视觉系统内部数据保留，不影响识别模型')
                return True
            return False

    # ---- 查询 ----
    def get_learned_objects(self):
        """获取已学习的物体列表

        Returns:
            list of dict: 每个元素为 {name, sample_count, first_learned, last_learned}
        """
        with self._lock:
            return [dict(obj) for obj in self._learned_objects]

    def get_object_count(self):
        """获取已学习物体类别数量"""
        with self._lock:
            return len(self._learned_objects)

    def find_by_name(self, name):
        """根据类别名查找物体记录

        Args:
            name: 物体类别名

        Returns:
            dict: 物体记录，未找到返回 None
        """
        with self._lock:
            for obj in self._learned_objects:
                if obj['name'] == name:
                    return dict(obj)
        return None

    # ---- 清理 ----
    def close(self):
        """释放视觉系统资源"""
        self._capture_running = False
        time.sleep(0.2)
        try:
            self.vision_system.cleanup()
        except Exception:
            pass


# ===================== Pygame 界面工具 =====================
def make_gradient_bg(width, height, top, bottom):
    """生成垂直渐变背景"""
    surf = pygame.Surface((width, height))
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        pygame.draw.line(surf, (r, g, b), (0, y), (width, y))
    return surf


def cvframe_to_surface(frame, target_w, target_h):
    """BGR 帧 -> pygame Surface，并缩放到指定尺寸

    使用 pygame.transform.scale（非 smoothscale）以降低 CPU 开销。
    """
    if frame is None:
        return None
    try:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        transposed = np.transpose(rgb, (1, 0, 2))
        surf = pygame.surfarray.make_surface(transposed)
        return pygame.transform.scale(surf, (target_w, target_h)).convert()
    except Exception:
        return None


class Button:
    """通用圆角按钮"""

    def __init__(self, rect, text, color, hover_color, text_color=(255, 255, 255)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.hovered = False
        self.enabled = True

    def update(self, mouse_pos):
        self.hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def draw(self, surf, font):
        if not self.enabled:
            c = (180, 180, 180)
        else:
            c = self.hover_color if self.hovered else self.color
        btn = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn, c, btn.get_rect(), border_radius=14)
        pygame.draw.rect(btn, (255, 255, 255, 200), btn.get_rect(), 2, border_radius=14)
        surf.blit(btn, self.rect.topleft)
        label = font.render(self.text, True, self.text_color)
        lr = label.get_rect(center=self.rect.center)
        surf.blit(label, lr)

    def clicked(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


class SmallButton:
    """小型按钮，用于列表项的删除等操作"""

    def __init__(self, rect, text, color, hover_color, text_color=(255, 255, 255)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.hovered = False

    def update(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surf, font):
        c = self.hover_color if self.hovered else self.color
        pygame.draw.rect(surf, c, self.rect, border_radius=6)
        label = font.render(self.text, True, self.text_color)
        lr = label.get_rect(center=self.rect.center)
        surf.blit(label, lr)

    def clicked(self, pos):
        return self.rect.collidepoint(pos)


class TextInput:
    """简单的文本输入框，支持英文/数字输入"""

    def __init__(self, rect, font, max_len=30):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.text = ''
        self.active = False
        self.max_len = max_len
        self.cursor_visible = True
        self.cursor_timer = 0

    def set_active(self, pos):
        """点击时激活/失活输入框"""
        self.active = self.rect.collidepoint(pos)

    def handle_key(self, event):
        """处理键盘输入"""
        if event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
        elif event.key == pygame.K_RETURN:
            self.active = False
        elif event.unicode and len(self.text) < self.max_len:
            char = event.unicode
            if char.isprintable():
                self.text += char

    def update(self):
        """更新光标闪烁"""
        self.cursor_timer += 1
        if self.cursor_timer >= 30:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0

    def draw(self, surf, hint_text='请输入物体名称...'):
        bg_color = INPUT_BG if self.active else (250, 250, 250)
        pygame.draw.rect(surf, bg_color, self.rect, border_radius=8)
        border_color = INPUT_ACTIVE_BORDER if self.active else INPUT_BORDER
        pygame.draw.rect(surf, border_color, self.rect, 2, border_radius=8)

        text_surf = self.font.render(self.text, True, TEXT_COLOR)
        text_y = self.rect.centery - text_surf.get_height() // 2
        surf.blit(text_surf, (self.rect.x + 12, text_y))

        if self.active and self.cursor_visible:
            cursor_x = self.rect.x + 12 + text_surf.get_width() + 2
            pygame.draw.line(surf, TEXT_COLOR,
                             (cursor_x, self.rect.y + 8),
                             (cursor_x, self.rect.bottom - 8), 2)

        if not self.text:
            hint = self.font.render(hint_text, True, SUBTLE_COLOR)
            surf.blit(hint, (self.rect.x + 12, text_y))


# ===================== 主程序 =====================
class ObjectLearnApp:
    """物体学习 Pygame 界面应用

    摄像头完全由视觉系统管理（open_camera + capture_frame），
    不使用 cv2 VideoCapture，避免设备冲突。
    学习流程严格参照范例代码 5.11。
    """

    TITLE_H = 130
    FOOTER_H = 110

    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('物体学习')
        self.clock = pygame.time.Clock()

        # 字体（适配 1920×1080：标题64、副标题32、列表项30、按钮34）
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 64)
        self.font_sub = pygame.font.Font(FONT_PATH, 32)
        self.font_item = pygame.font.Font(FONT_PATH, 30)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_small = pygame.font.Font(FONT_PATH, 24)
        self.font_status = pygame.font.Font(FONT_PATH, 26)
        self.font_input = pygame.font.Font(FONT_PATH, 32)
        self.font_del = pygame.font.Font(FONT_PATH, 22)

        # 背景：优先加载图片，失败回退渐变
        try:
            bg_raw = pygame.image.load('images/1.jpg')
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception:
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # 布局：左右面板等高 820px
        panel_h = HEIGHT - self.TITLE_H - 20 - self.FOOTER_H  # 820
        self.cam_rect = pygame.Rect(60, self.TITLE_H + 20,
                                    CAM_DISP_W + 40, panel_h)
        self.info_rect = pygame.Rect(self.cam_rect.right + 40, self.TITLE_H + 20,
                                     WIDTH - self.cam_rect.right - 40 - 60,
                                     panel_h)

        ix = self.info_rect.x + 30
        iw = self.info_rect.w - 60

        # 物体名称输入框
        self.name_input = TextInput(
            (ix, self.info_rect.y + 70, iw, 70),
            self.font_input
        )

        # 学习按钮
        btn_y = self.name_input.rect.bottom + 25
        self.btn_learn = Button((ix, btn_y, iw, 70),
                                '学习物体', LEARN_COLOR, LEARN_HOVER)

        # 退出按钮（右上角标题栏内，固定 240×70）
        self.btn_exit = Button((WIDTH - 280, 30, 240, 70),
                               '退出程序', EXIT_COLOR, EXIT_HOVER)

        # 初始化物体学习器（视觉系统初始化 + 摄像头打开 + 后台检测）
        print('正在初始化物体识别系统...')
        self.learner = ObjectLearner()

        # 状态
        self.running = True
        self.status_msg = '请输入物体名称并对准摄像头，然后点击「学习物体」'
        self.status_color = SUBTLE_COLOR

        # 列表项 rect 列表（每帧更新，用于点击检测）
        self.object_delete_rects = []
        self.object_name_rects = []  # [(name_rect, name), ...] 点击回填名称

    def set_status(self, msg, color=SUBTLE_COLOR):
        self.status_msg = msg
        self.status_color = color

    def handle_learn(self):
        """处理学习物体按钮点击"""
        name = self.name_input.text.strip()
        if not name:
            self.set_status('请先输入物体名称', ERROR_COLOR)
            return
        if not self.learner.camera_ok:
            self.set_status('摄像头未就绪，无法学习', ERROR_COLOR)
            return
        self.set_status('正在学习...', ACCENT_COLOR)
        # 在主线程中执行学习（避免多线程并发访问视觉系统）
        result = self.learner.learn_current_frame(name)
        if result is None:
            self.set_status('学习失败，请确保画面中有清晰物体', ERROR_COLOR)
        else:
            obj = self.learner.find_by_name(name)
            sample_count = obj.get('sample_count', 0) if obj else 0
            total = self.learner.get_object_count()
            self.set_status('学习成功：%s（样本 %d，累计 %d 个类别）' % (
                name, sample_count, total), SUCCESS_COLOR)
            self.name_input.text = ''

    def handle_delete_object(self, index):
        """处理删除物体记录"""
        objects = self.learner.get_learned_objects()
        if 0 <= index < len(objects):
            name = objects[index]['name']
            self.learner.delete_object(index)
            self.set_status('已删除：%s（累计 %d 个类别）' % (
                name, self.learner.get_object_count()), ACCENT_COLOR)

    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('物体学习', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 25))
        sub = self.font_sub.render(
            'USB摄像头采集画面  ·  输入名称后点击学习  ·  同一物体可多次学习增强识别',
            True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 90))

        # 退出按钮（右上角）
        self.btn_exit.draw(self.screen, self.font_btn)

    def draw_camera(self):
        """绘制摄像头画面区域"""
        panel = pygame.Surface(self.cam_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.cam_rect.topleft)

        head = self.font_sub.render('摄像头画面', True, TITLE_COLOR)
        self.screen.blit(head, (self.cam_rect.x + 20, self.cam_rect.y + 15))

        status = '● 已连接' if self.learner.camera_ok else '○ 未连接'
        sc = SUCCESS_COLOR if self.learner.camera_ok else ERROR_COLOR
        st = self.font_small.render(status, True, sc)
        self.screen.blit(st, (self.cam_rect.right - st.get_width() - 20,
                              self.cam_rect.y + 20))

        frame = self.learner.get_current_frame()
        if frame is not None:
            surf = cvframe_to_surface(frame, CAM_DISP_W, CAM_DISP_H)
            if surf is not None:
                # 居中显示在面板内
                cam_x = self.cam_rect.x + (self.cam_rect.w - CAM_DISP_W) // 2
                cam_y = self.cam_rect.y + 60
                self.screen.blit(surf, (cam_x, cam_y))
        else:
            hint_text = '摄像头未连接' if not self.learner.camera_ok else '等待画面...'
            hint_color = ERROR_COLOR if not self.learner.camera_ok else SUBTLE_COLOR
            hint = self.font_sub.render(hint_text, True, hint_color)
            self.screen.blit(hint, (self.cam_rect.centerx - hint.get_width() // 2,
                                    self.cam_rect.centery - hint.get_height() // 2))

        res = self.font_small.render('%d × %d' % (CAMERA_W, CAMERA_H), True, SUBTLE_COLOR)
        self.screen.blit(res, (self.cam_rect.right - res.get_width() - 20,
                               self.cam_rect.bottom - 30))

    def draw_info_panel(self):
        """绘制右侧信息面板：名称输入 + 按钮 + 状态 + 已学习列表"""
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 30
        x_end = self.info_rect.right - 30
        y = self.info_rect.y + 20

        # ---- 物体名称输入 ----
        head = self.font_sub.render('物体名称', True, TITLE_COLOR)
        self.screen.blit(head, (x, y))

        self.name_input.update()
        self.name_input.draw(self.screen)

        # ---- 学习按钮 ----
        self.btn_learn.draw(self.screen, self.font_btn)

        # ---- 状态消息 ----
        y = self.btn_learn.rect.bottom + 20
        status_surf = self.font_status.render(self.status_msg, True, self.status_color)
        max_w = x_end - x
        if status_surf.get_width() > max_w:
            status_surf = self.font_small.render(self.status_msg, True, self.status_color)
        self.screen.blit(status_surf, (x, y))

        # 分隔线
        y += 40
        pygame.draw.line(self.screen, PANEL_BORDER,
                         (x, y), (x_end, y), 2)
        y += 25

        # ---- 已学习物体列表 ----
        objects = self.learner.get_learned_objects()
        head2 = self.font_sub.render('已学习物体（%d 个类别）' % len(objects), True, TITLE_COLOR)
        self.screen.blit(head2, (x, y))
        y += 50

        list_bottom = self.info_rect.bottom - 20
        self.object_delete_rects = []
        self.object_name_rects = []  # 每帧重建 (rect, name)，用于点击回填名称
        mouse_pos = pygame.mouse.get_pos()

        if not objects:
            hint = self.font_item.render('暂无学习记录', True, SUBTLE_COLOR)
            self.screen.blit(hint, (x, y))
        else:
            for i, obj in enumerate(objects):
                if y + 70 > list_bottom:
                    more = self.font_small.render(
                        '...共 %d 个类别' % len(objects), True, SUBTLE_COLOR)
                    self.screen.blit(more, (x, y))
                    break

                name = obj.get('name', '?')
                sample_count = obj.get('sample_count', 0)
                last_learned = obj.get('last_learned', '')

                # 删除按钮（先算位置，名称可点击区域需避让删除按钮）
                del_w, del_h = 70, 40
                del_rect = pygame.Rect(x_end - del_w, y + 10, del_w, del_h)

                # 序号
                num = self.font_small.render('%d.' % (i + 1), True, SUBTLE_COLOR)
                self.screen.blit(num, (x, y + 8))

                # 名称可点击区域：整行除删除按钮区域，方便触屏点击
                name_rect = pygame.Rect(x, y, del_rect.left - x - 10, 70)
                name_hovered = name_rect.collidepoint(mouse_pos)

                # 物体名称（hover 时变蓝并加下划线，提示可点击回填）
                name_color = LEARN_COLOR if name_hovered else TEXT_COLOR
                name_surf = self.font_item.render(name, True, name_color)
                self.screen.blit(name_surf, (x + 40, y))
                if name_hovered:
                    underline_y = y + name_surf.get_height() + 2
                    pygame.draw.line(self.screen, LEARN_COLOR,
                                     (x + 40, underline_y),
                                     (x + 40 + name_surf.get_width(), underline_y), 2)

                # 样本数 + 最后学习时间
                info_text = '样本 %d  ·  %s' % (sample_count, last_learned)
                info_surf = self.font_small.render(info_text, True, ACCENT_COLOR)
                self.screen.blit(info_surf, (x + 40, y + 38))

                # 删除按钮
                del_btn = SmallButton(del_rect, '删除', DEL_COLOR, DEL_HOVER)
                del_btn.update(mouse_pos)
                del_btn.draw(self.screen, self.font_del)
                self.object_delete_rects.append((del_rect, i))
                self.object_name_rects.append((name_rect, name))

                y += 70

    def draw_footer(self):
        """绘制底部栏"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        hint = self.font_small.render(
            'ESC 退出  ·  输入物体名称后回车或点击「学习物体」  ·  同一物体多次学习可提升识别准确率',
            True, SUBTLE_COLOR)
        self.screen.blit(hint, (60, HEIGHT - self.FOOTER_H // 2 - hint.get_height() // 2))

    def run(self):
        """主循环"""
        while self.running:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.btn_exit.clicked(event.pos):
                        self.running = False
                    elif self.btn_learn.clicked(event.pos):
                        self.handle_learn()
                    else:
                        # 检测删除按钮点击
                        del_clicked = False
                        for del_rect, obj_index in self.object_delete_rects:
                            if del_rect.collidepoint(event.pos):
                                self.handle_delete_object(obj_index)
                                del_clicked = True
                                break
                        if del_clicked:
                            continue
                        # 检测列表名称点击：回填到输入框，方便多次学习
                        name_clicked = False
                        for name_rect, name in self.object_name_rects:
                            if name_rect.collidepoint(event.pos):
                                self.name_input.text = name
                                self.name_input.active = True
                                self.set_status(
                                    '已选择 [%s]，对准物体后点击「学习物体」添加样本' % name,
                                    ACCENT_COLOR)
                                name_clicked = True
                                break
                        if not name_clicked:
                            self.name_input.set_active(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif self.name_input.active:
                        if event.key == pygame.K_RETURN:
                            self.handle_learn()
                        else:
                            self.name_input.handle_key(event)
                    elif event.key == pygame.K_RETURN:
                        self.name_input.active = True

            self.btn_learn.update(mouse_pos)
            self.btn_exit.update(mouse_pos)

            self.screen.blit(self.bg, (0, 0))
            self.draw_title()
            self.draw_camera()
            self.draw_info_panel()
            self.draw_footer()

            pygame.display.flip()
            self.clock.tick(30)

        # 退出清理
        print('正在关闭程序...')
        self.learner.close()
        pygame.quit()
        try:
            _debug_log_fp.close()
        except Exception:
            pass


# ===================== 入口 =====================
if __name__ == '__main__':
    app = ObjectLearnApp()
    app.run()
