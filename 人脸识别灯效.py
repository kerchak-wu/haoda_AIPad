# -*- coding: utf-8 -*-
"""
人脸识别灯效程序 - 好搭AI派
============================
功能说明：
  1. 加载人脸学习程序保存的人脸记录（face_records.json）
  2. 视觉系统摄像头实时识别已学习的人脸
  3. 识别到不同人脸，IO1 RGB灯带（11灯珠）显示不同炫酷灯效
  4. 界面显示摄像头画面、识别结果和灯效信息
  5. 未识别到人脸时灯带显示待机效果

硬件接线：
  - IO1 (GPIO_IO_01)  WS2812 RGB灯带(11灯珠)，需接上拉扩展模块
  - USB外接摄像头（由视觉系统管理）
  - 好搭AI派扩展板(ESP32)
  注意：好搭AI派右下角开关需拨到左侧以启用外设接口。

依赖库：
  pygame, cv2(opencv, 仅用于图像格式转换), numpy, ESP32, camera_vision_system_v3(好搭AI派自带)

参考范例：
  - 范例代码 5.10 人脸识别（open_camera + start_background_detection + result_accessor）
  - 范例代码 2.扩展模块使用 4.RGB灯（ws2812Init / ws2812Write / wheel）
  - 手势控制RGB灯带.py（灯效实现与多线程模式）
  - 人脸学习.py（face_records.json 格式与 FaceLearner 类）
"""

import os
import sys
import json
import math
import time
import threading

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
    '人脸识别灯效_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
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

# 引脚定义
LED_PIN = GPIO_IO_01   # IO1 RGB灯带
LED_COUNT = 11          # 11颗灯珠

# 摄像头配置
CAMERA_W, CAMERA_H = 640, 480
CAM_DISP_W, CAM_DISP_H = 880, 660

# 人脸记录文件（由人脸学习.py生成）
FACE_DATA_FILE = 'face_records.json'

# 人脸-灯效映射文件（本程序自定义保存）
FACE_EFFECT_MAP_FILE = 'face_effect_map.json'

# ---- 界面配色（浅色系）----
BG_TOP = (135, 206, 235)        # 天空蓝
BG_BOTTOM = (220, 240, 255)     # 浅蓝白
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


# ===================== 硬件初始化 =====================
# 严格参照范例代码：ESP32 初始化 + 异常处理
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        board.ws2812Init((LED_PIN), LED_COUNT)
        board.ws2812Write((LED_PIN), 255, 0, 0, 0)   # 初始熄灭
        print('RGB灯带初始化完成：IO1，%d颗灯珠' % LED_COUNT)
    except Exception as e:
        print('RGB灯带初始化异常:', e)


# ===================== RGB 灯带效果 =====================
# 参照范例 2.扩展模块使用 4.RGB灯 的 wheel 函数与 ws2812Write 调用方式
def wheel(pos):
    """生成 0-255 位置的彩虹颜色，参照 RGB 灯范例"""
    if pos < 0 or pos > 255:
        pos %= 256
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)


def led_set_all(r, g, b):
    """点亮全部灯珠为同一颜色"""
    try:
        for i in range(LED_COUNT):
            board.ws2812Write((LED_PIN), i, r, g, b)
    except Exception:
        pass


def led_off():
    """熄灭所有灯珠"""
    try:
        board.ws2812Write((LED_PIN), 255, 0, 0, 0)
    except Exception:
        pass


# ---- 灯效定义 ----
# 每个人脸分配一种灯效（按 face_id 取模），外加待机和未知两种
EFFECT_LIST = [
    'rainbow', 'fire', 'ocean', 'breathing', 'twinkle',
    'chase', 'heartbeat', 'aurora', 'meteor', 'lightning',
]

EFFECT_NAMES = {
    'rainbow':   '彩虹流光',
    'fire':      '火焰跳动',
    'ocean':     '海洋波涛',
    'breathing': '呼吸渐变',
    'twinkle':   '星光闪烁',
    'chase':     '色彩追逐',
    'heartbeat': '心跳节奏',
    'aurora':    '极光幻彩',
    'meteor':    '流星飞逝',
    'lightning': '闪电脉冲',
    'standby':   '待机呼吸',
    'unknown':   '未知闪烁',
    'none':      '灯光关闭',
}

# 灯效主题色（用于界面显示）
EFFECT_COLORS = {
    'rainbow':   (255, 100, 200),
    'fire':      (255, 60, 30),
    'ocean':     (30, 100, 255),
    'breathing': (60, 200, 100),
    'twinkle':   (255, 220, 100),
    'chase':     (100, 200, 255),
    'heartbeat': (255, 130, 180),
    'aurora':    (100, 255, 200),
    'meteor':    (200, 100, 255),
    'lightning': (255, 255, 100),
    'standby':   (80, 80, 120),
    'unknown':   (150, 150, 150),
    'none':      (60, 60, 60),
}

# 全局灯效状态
current_effect = 'standby'
led_frame = 0


def update_led_frame():
    """在主循环中按帧更新灯效（单线程，与范例调用风格一致）

    11颗灯珠的炫酷灯效实现，参照手势控制RGB灯带.py的灯效架构。
    """
    global led_frame
    if current_effect == 'none':
        return
    t = led_frame
    try:
        if current_effect == 'rainbow':
            # 彩虹流光：颜色沿灯带流动
            for i in range(LED_COUNT):
                pos = (t * 3 + i * 25) % 256
                c = wheel(pos)
                board.ws2812Write((LED_PIN), i, c[0], c[1], c[2])

        elif current_effect == 'fire':
            # 火焰跳动：红橙黄随机跳动
            for i in range(LED_COUNT):
                flicker = int(50 + 100 * (math.sin((t + i * 15) * 0.3) + 1) * 0.5)
                g = max(0, min(120, flicker))
                b = max(0, min(30, int(20 * math.sin((t + i * 10) * 0.5))))
                board.ws2812Write((LED_PIN), i, 255, g, b)

        elif current_effect == 'ocean':
            # 海洋波涛：蓝色波纹追逐
            for i in range(LED_COUNT):
                wave = math.sin((t * 0.15 + i * 0.6))
                b = int(100 + 155 * (wave + 1) * 0.5)
                g = int(50 + 80 * (wave + 1) * 0.5)
                board.ws2812Write((LED_PIN), i, 20, g, b)

        elif current_effect == 'breathing':
            # 呼吸渐变：绿色缓慢呼吸
            b = (math.sin(t * 0.08) + 1) * 0.5
            g = int(50 + 205 * b)
            led_set_all(20, g, 40)

        elif current_effect == 'twinkle':
            # 星光闪烁：金色随机闪烁
            for i in range(LED_COUNT):
                phase = (t + i * 7) % 30
                if phase < 5:
                    v = 255
                elif phase < 10:
                    v = 100
                else:
                    v = 30
                board.ws2812Write((LED_PIN), i, v, int(v * 0.8), int(v * 0.2))

        elif current_effect == 'chase':
            # 色彩追逐：三色光点沿灯带循环
            for i in range(LED_COUNT):
                pos = (t + i * 5) % 15
                if pos < 3:
                    board.ws2812Write((LED_PIN), i, 255, 0, 0)
                elif pos < 6:
                    board.ws2812Write((LED_PIN), i, 0, 255, 0)
                elif pos < 9:
                    board.ws2812Write((LED_PIN), i, 0, 0, 255)
                else:
                    board.ws2812Write((LED_PIN), i, 20, 20, 20)

        elif current_effect == 'heartbeat':
            # 心跳节奏：粉色双跳
            cycle = t % 40
            if cycle < 3 or (cycle >= 6 and cycle < 9):
                r = 255
            elif cycle < 6 or (cycle >= 9 and cycle < 12):
                r = 150
            else:
                r = 60
            led_set_all(r, int(r * 0.3), int(r * 0.5))

        elif current_effect == 'aurora':
            # 极光幻彩：青绿紫渐变流动
            for i in range(LED_COUNT):
                phase = (t * 0.1 + i * 0.4) % (math.pi * 2)
                r = int(60 + 80 * math.sin(phase))
                g = int(180 + 60 * math.sin(phase + 2))
                b = int(120 + 80 * math.sin(phase + 4))
                board.ws2812Write((LED_PIN), i, r, g, b)

        elif current_effect == 'meteor':
            # 流星飞逝：紫色彗星拖尾
            head = (t * 1) % (LED_COUNT + 5)
            for i in range(LED_COUNT):
                dist = head - i
                if 0 <= dist < 5:
                    brightness = 255 - dist * 50
                    board.ws2812Write((LED_PIN), i, int(brightness * 0.6),
                                      int(brightness * 0.2), brightness)
                else:
                    board.ws2812Write((LED_PIN), i, 15, 5, 25)

        elif current_effect == 'lightning':
            # 闪电脉冲：黄色快速闪烁
            cycle = t % 20
            if cycle < 2:
                led_set_all(255, 255, 100)
            elif cycle < 4:
                led_set_all(60, 60, 20)
            elif cycle < 6:
                led_set_all(255, 255, 80)
            else:
                led_set_all(25, 25, 5)

        elif current_effect == 'standby':
            # 待机呼吸：冷蓝色缓慢呼吸
            b = (math.sin(t * 0.05) + 1) * 0.5
            v = int(30 + 50 * b)
            led_set_all(v // 3, v // 3, v)

        elif current_effect == 'unknown':
            # 未知人脸：灰色闪烁
            cycle = t % 30
            if cycle < 15:
                led_set_all(100, 100, 100)
            else:
                led_set_all(40, 40, 40)

        led_frame += 1
    except Exception:
        pass


def set_led_effect(effect_name):
    """切换灯效"""
    global current_effect, led_frame
    current_effect = effect_name
    led_frame = 0
    if effect_name == 'none':
        led_off()


def get_effect_for_face_id(face_id, custom_map=None):
    """根据 face_id 获取灯效名称

    优先使用自定义映射（custom_map），无映射时按 face_id 取模分配默认灯效。
    """
    if face_id is None:
        return 'standby'
    if custom_map and face_id in custom_map:
        return custom_map[face_id]
    return EFFECT_LIST[face_id % len(EFFECT_LIST)]


# ===================== 人脸记录加载 =====================
def load_face_records():
    """从 face_records.json 加载人脸记录

    返回 {face_id: name} 映射字典。
    """
    records = {}
    try:
        with open(FACE_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for item in data:
            name = item.get('name', '未知')
            face_info = item.get('face_info', {})
            if isinstance(face_info, dict):
                face_id = face_info.get('face_id')
                if face_id is not None:
                    records[face_id] = name
        print('已加载 %d 条人脸记录' % len(records))
    except FileNotFoundError:
        print('未找到人脸记录文件 %s，请先运行人脸学习程序' % FACE_DATA_FILE)
    except Exception as e:
        print('加载人脸记录失败:', e)
    return records


def load_face_effect_map():
    """从 face_effect_map.json 加载人脸-灯效自定义映射

    返回 {face_id: effect_name} 字典。
    """
    try:
        with open(FACE_EFFECT_MAP_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # JSON 键是字符串，转回 int
        result = {int(k): v for k, v in data.items()}
        print('已加载 %d 条自定义灯效映射' % len(result))
        return result
    except FileNotFoundError:
        pass
    except Exception as e:
        print('加载灯效映射失败:', e)
    return {}


def save_face_effect_map(effect_map):
    """保存人脸-灯效映射到 JSON 文件"""
    try:
        # face_id 转字符串作为 JSON 键
        data = {str(k): v for k, v in effect_map.items()}
        with open(FACE_EFFECT_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('保存灯效映射失败:', e)


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


# ===================== 主程序 =====================
class FaceRecognizeApp:
    """人脸识别灯效 Pygame 界面应用

    摄像头完全由视觉系统管理（open_camera + capture_frame），
    不使用 cv2 VideoCapture，避免设备冲突。
    识别流程严格参照范例代码 5.10。
    """

    TITLE_H = 130
    FOOTER_H = 110

    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('人脸识别灯效')
        self.clock = pygame.time.Clock()

        # 字体（1920x1080 下适度增大）
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 64)
        self.font_sub = pygame.font.Font(FONT_PATH, 32)
        self.font_item = pygame.font.Font(FONT_PATH, 30)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_small = pygame.font.Font(FONT_PATH, 24)
        self.font_status = pygame.font.Font(FONT_PATH, 26)
        self.font_big = pygame.font.Font(FONT_BOLD_PATH, 56)
        # 列表与弹窗专用大字体，方便点击选择
        self.font_list = pygame.font.Font(FONT_PATH, 36)
        self.font_list_eff = pygame.font.Font(FONT_PATH, 30)
        self.font_picker_title = pygame.font.Font(FONT_BOLD_PATH, 56)

        # 背景
        try:
            bg_raw = pygame.image.load('images/1.jpg')
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception:
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # 布局：两个面板等高对齐，视觉更整齐
        panel_h = HEIGHT - self.TITLE_H - 20 - self.FOOTER_H  # 820
        self.cam_rect = pygame.Rect(60, self.TITLE_H + 20,
                                    CAM_DISP_W + 40, panel_h)
        self.info_rect = pygame.Rect(self.cam_rect.right + 40, self.TITLE_H + 20,
                                     WIDTH - self.cam_rect.right - 40 - 60,
                                     panel_h)

        # 退出按钮（右上角，标题栏内）
        self.btn_exit = Button((WIDTH - 280, 30, 240, 70),
                               '退出程序', EXIT_COLOR, EXIT_HOVER)

        # 加载人脸记录
        print('正在加载人脸记录...')
        self.face_records = load_face_records()
        self.face_list = sorted(self.face_records.items())  # [(face_id, name), ...]

        # 加载自定义灯效映射
        self.face_effect_map = load_face_effect_map()

        # 灯效选择器状态
        self.effect_picker_face_id = None  # 正在为哪个 face_id 选择灯效
        self.face_item_rects = []  # 列表项的可点击区域，draw_info_panel 中更新

        # 初始化视觉系统
        print('正在初始化视觉系统...')
        self._init_vision_system()

        # 状态
        self.running = True
        self.raw_frame = None
        self.frame_lock = threading.Lock()
        self.capture_fail = 0
        self.status_msg = '正在启动识别...'
        self.status_color = SUBTLE_COLOR

        # 识别结果
        self.current_face_id = None
        self.current_name = '未知'
        self.current_confidence = 0.0
        self.current_effect = 'standby'

        # 启动后台采集线程
        # 固定 0.15s 间隔（约 6-7 fps），给 V4L2 后台检测线程足够的缓冲区访问时间
        self.capture_thread_running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _init_vision_system(self):
        """初始化视觉系统并打开摄像头（严格参照范例代码 5.10）

        关键：不使用 cv2 VideoCapture，摄像头完全由视觉系统管理。
        """
        self.vision_system = create_vision_system_v3(
            camera_id=-1, width=1280, height=720,
            enable_basic=False, enable_advanced=False
        )
        self.vision_system.detection_config.enable_face_recognition = True
        self.vision_system._init_detectors()
        print('face_recognition 算法已启用')

        # 调试：列出 vision_system 和 result_accessor 的所有方法
        # 用于排查识别模型损坏后是否有 reset/clear 接口
        vs_methods = [m for m in dir(self.vision_system) if not m.startswith('_')]
        ra_methods = [m for m in dir(self.vision_system.result_accessor) if not m.startswith('_')]
        print('[调试] vision_system 方法: %s' % vs_methods)
        print('[调试] result_accessor 方法: %s' % ra_methods)

        # 调试：查看人脸数据库信息
        try:
            db_info = self.vision_system.get_face_database_info()
            print('[调试] 人脸数据库信息: %s' % str(db_info))
        except Exception as e:
            print('[调试] 获取人脸数据库信息失败: %s' % e)

        # 打开摄像头（严格参照范例 5.10）
        print('正在打开视觉系统摄像头...')
        if self.vision_system.open_camera():
            print('视觉系统摄像头已打开')
            self.camera_ok = True
        else:
            print('视觉系统摄像头打开失败')
            self.camera_ok = False

        # 启动后台检测（show_preview=False，不弹 OpenCV 窗口）
        if self.camera_ok:
            self.vision_system.threaded_system.start_background_detection(show_preview=False)
            print('人脸识别后台检测已启动')

    def _capture_loop(self):
        """后台线程：固定间隔采集帧用于界面显示

        关键改进（相比之前崩溃版本）：
        1. 固定 0.15s 睡眠（无论成功失败），不紧循环调用
        2. 帧有效性验证，跳过损坏帧
        3. 与主线程的 refresh_results() 不冲突（后者只读缓存，不访问 V4L2）
        """
        # 启动后等待 0.5s 让后台检测线程先稳定
        time.sleep(0.5)
        while self.capture_thread_running:
            if not self.camera_ok:
                time.sleep(0.3)
                continue
            try:
                frame = self.vision_system.capture_frame()
                if frame is not None and hasattr(frame, 'shape') and len(frame.shape) == 3:
                    with self.frame_lock:
                        self.raw_frame = frame
                    self.capture_fail = 0
                else:
                    self.capture_fail += 1
            except Exception:
                self.capture_fail += 1
                if self.capture_fail <= 3:
                    print('[采集] 异常')
            # 固定间隔，给 V4L2 后台检测线程留出缓冲区访问时间
            time.sleep(0.15)

    def check_recognition(self):
        """检查识别结果（严格参照范例代码 5.10 的识别流程）

        在主循环中调用，轮询 result_accessor 获取最新识别结果。
        """
        try:
            self.vision_system.result_accessor.refresh_results()
            count = self.vision_system.result_accessor.get_face_count()
            # 调试打印：每秒输出一次识别状态
            if hasattr(self, '_debug_tick'):
                if time.time() - self._debug_tick > 1.0:
                    face_id_dbg = self.vision_system.result_accessor.get_face_id()
                    conf_dbg = self.vision_system.result_accessor.get_face_confidence()
                    print('[调试] get_face_count=%s, get_face_id=%s, get_face_confidence=%s' % (
                        count, face_id_dbg, conf_dbg))
                    self._debug_tick = time.time()
            else:
                self._debug_tick = time.time()
            if count > 0:
                face_id = self.vision_system.result_accessor.get_face_id()
                confidence = round(self.vision_system.result_accessor.get_face_confidence(), 3)

                # 处理 face_id 为 None 的情况：检测到人脸但识别不出来
                if face_id is None:
                    if self.current_face_id != 'unknown_face':
                        self.current_face_id = 'unknown_face'
                        self.current_name = '检测到人脸（未识别）'
                        self.current_confidence = confidence
                        self.current_effect = 'unknown'
                        set_led_effect('unknown')
                        self.status_msg = '检测到人脸但识别失败，可能需要清空数据库重新学习'
                        self.status_color = ACCENT_COLOR
                        print('[识别] 检测到人脸但 get_face_id=None，置信度:%s' % confidence)
                    return

                # 仅当 face_id 变化时切换灯效（避免每帧重复切换）
                if face_id != self.current_face_id:
                    self.current_face_id = face_id
                    self.current_confidence = confidence

                    if face_id in self.face_records:
                        self.current_name = self.face_records[face_id]
                        effect = get_effect_for_face_id(face_id, self.face_effect_map)
                        self.current_effect = effect
                        set_led_effect(effect)
                        effect_name = EFFECT_NAMES.get(effect, effect)
                        self.status_msg = '识别到：%s（ID:%s，置信度:%s）→ %s' % (
                            self.current_name, face_id, confidence, effect_name)
                        self.status_color = SUCCESS_COLOR
                        print('[识别] %s (ID:%s, 置信度:%s) -> 灯效:%s' % (
                            self.current_name, face_id, confidence, effect))
                    else:
                        self.current_name = '未知（ID:%s）' % face_id
                        self.current_effect = 'unknown'
                        set_led_effect('unknown')
                        self.status_msg = '未知人脸（ID:%s，置信度:%s）' % (face_id, confidence)
                        self.status_color = ACCENT_COLOR
                        print('[识别] 未知人脸 ID:%s, 置信度:%s' % (face_id, confidence))
                else:
                    # 同一人脸，仅更新置信度
                    self.current_confidence = confidence
            else:
                # 无人脸
                if self.current_face_id is not None:
                    self.current_face_id = None
                    self.current_name = '未识别到人脸'
                    self.current_confidence = 0.0
                    self.current_effect = 'standby'
                    set_led_effect('standby')
                    self.status_msg = '等待人脸...'
                    self.status_color = SUBTLE_COLOR
                    print('[识别] 无人脸，切换待机')
        except Exception as e:
            print('识别检查异常:', e)

    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('人脸识别灯效', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 18))
        sub = self.font_sub.render(
            '视觉系统实时识别  ·  不同人脸触发不同灯效  ·  IO1 11灯珠',
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
        self.screen.blit(head, (self.cam_rect.x + 20, self.cam_rect.y + 10))

        status = '● 已连接' if self.camera_ok else '○ 未连接'
        sc = SUCCESS_COLOR if self.camera_ok else ERROR_COLOR
        st = self.font_small.render(status, True, sc)
        self.screen.blit(st, (self.cam_rect.right - st.get_width() - 20,
                              self.cam_rect.y + 15))

        with self.frame_lock:
            frame = self.raw_frame
        if frame is not None:
            surf = cvframe_to_surface(frame, CAM_DISP_W, CAM_DISP_H)
            if surf is not None:
                self.screen.blit(surf, (self.cam_rect.x + 20, self.cam_rect.y + 50))
        else:
            hint_text = '摄像头未连接' if not self.camera_ok else '等待画面...'
            hint_color = ERROR_COLOR if not self.camera_ok else SUBTLE_COLOR
            hint = self.font_sub.render(hint_text, True, hint_color)
            self.screen.blit(hint, (self.cam_rect.centerx - hint.get_width() // 2,
                                    self.cam_rect.centery - hint.get_height() // 2))

        res = self.font_small.render('%d × %d' % (CAMERA_W, CAMERA_H), True, SUBTLE_COLOR)
        self.screen.blit(res, (self.cam_rect.right - res.get_width() - 20,
                               self.cam_rect.bottom - 25))

    def draw_info_panel(self):
        """绘制右侧信息面板：识别结果 + 灯效信息 + 已学习人脸列表"""
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 30
        x_end = self.info_rect.right - 30
        y = self.info_rect.y + 20

        # ---- 当前识别结果 ----
        head = self.font_sub.render('识别结果', True, TITLE_COLOR)
        self.screen.blit(head, (x, y))
        y += 42

        # 姓名（大字）
        name_color = SUCCESS_COLOR if self.current_face_id is not None else SUBTLE_COLOR
        if self.current_face_id is not None and self.current_face_id in self.face_records:
            name_color = SUCCESS_COLOR
        elif self.current_face_id is not None:
            name_color = ACCENT_COLOR
        name_surf = self.font_big.render(self.current_name, True, name_color)
        self.screen.blit(name_surf, (x, y))
        y += 66

        # 置信度和灯效
        if self.current_face_id is not None:
            info_text = 'ID:%s  置信度:%s' % (self.current_face_id, self.current_confidence)
            info_surf = self.font_item.render(info_text, True, TEXT_COLOR)
            self.screen.blit(info_surf, (x, y))
            y += 38

        effect_text = '灯效：%s' % EFFECT_NAMES.get(self.current_effect, self.current_effect)
        effect_color = EFFECT_COLORS.get(self.current_effect, SUBTLE_COLOR)
        effect_surf = self.font_item.render(effect_text, True, effect_color)
        self.screen.blit(effect_surf, (x, y))
        y += 42

        # 状态消息
        status_surf = self.font_status.render(self.status_msg, True, self.status_color)
        max_w = x_end - x
        if status_surf.get_width() > max_w:
            status_surf = self.font_small.render(self.status_msg, True, self.status_color)
        self.screen.blit(status_surf, (x, y))

        # 分隔线
        y += 38
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 20

        # ---- 已学习人脸列表 ----
        head2 = self.font_sub.render('已学习人脸（%d）·点击修改灯效' % len(self.face_list),
                                     True, TITLE_COLOR)
        self.screen.blit(head2, (x, y))
        y += 40

        list_bottom = self.info_rect.bottom - 20
        self.face_item_rects = []  # 重置可点击区域
        row_h = 56  # 列表行高，加大方便点击
        if not self.face_list:
            hint = self.font_list.render('暂无人脸记录', True, SUBTLE_COLOR)
            self.screen.blit(hint, (x, y))
        else:
            for face_id, name in self.face_list:
                if y + row_h > list_bottom:
                    more = self.font_small.render(
                        '...共 %d 条记录' % len(self.face_list), True, SUBTLE_COLOR)
                    self.screen.blit(more, (x, y))
                    break

                effect = get_effect_for_face_id(face_id, self.face_effect_map)
                effect_name = EFFECT_NAMES.get(effect, '')
                effect_color = EFFECT_COLORS.get(effect, SUBTLE_COLOR)
                is_custom = face_id in self.face_effect_map

                # 当前识别到的人脸高亮
                is_current = (face_id == self.current_face_id)
                text_color = SUCCESS_COLOR if is_current else TEXT_COLOR

                # 行背景（鼠标悬停高亮）
                item_rect = pygame.Rect(x - 8, y - 4, x_end - x + 16, row_h)
                mouse_pos = pygame.mouse.get_pos()
                if item_rect.collidepoint(mouse_pos):
                    bg = pygame.Surface(item_rect.size, pygame.SRCALPHA)
                    pygame.draw.rect(bg, (100, 149, 237, 40), bg.get_rect(), border_radius=8)
                    self.screen.blit(bg, item_rect.topleft)
                self.face_item_rects.append((item_rect, face_id))

                # 序号 + 姓名（大字体）
                line = '%d. %s' % (face_id, name)
                line_surf = self.font_list.render(line, True, text_color)
                self.screen.blit(line_surf, (x, y + 8))

                # 灯效名（右侧），自定义的加方括号
                display_name = '[%s]' % effect_name if is_custom else effect_name
                eff_surf = self.font_list_eff.render(display_name, True, effect_color)
                self.screen.blit(eff_surf, (x_end - eff_surf.get_width(), y + 12))

                # 当前项标记
                if is_current:
                    mark = self.font_list_eff.render('●', True, SUCCESS_COLOR)
                    self.screen.blit(mark, (x - 30, y + 12))

                y += row_h

        # 如果灯效选择器打开，绘制在选择器最上层
        if self.effect_picker_face_id is not None:
            self.draw_effect_picker()

    def draw_effect_picker(self):
        """绘制灯效选择弹窗（半透明遮罩 + 居中面板）"""
        face_id = self.effect_picker_face_id
        name = self.face_records.get(face_id, '未知')

        # 半透明遮罩
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (0, 0, 0, 100), overlay.get_rect())
        self.screen.blit(overlay, (0, 0))

        # 弹窗面板（加宽加高，避免文字与背景框重叠，点击不易误触）
        # 高度需容纳：标题区(195) + 10项×72 + 按钮区(76) ≈ 991，故 ph=1010 留余量
        pw, ph = 780, 1010
        px = (WIDTH - pw) // 2
        py = (HEIGHT - ph) // 2
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        pygame.draw.rect(panel, (255, 255, 255, 250), panel.get_rect(), border_radius=20)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 3, border_radius=20)
        self.screen.blit(panel, (px, py))

        # 标题
        title = self.font_picker_title.render('选择灯效', True, TITLE_COLOR)
        self.screen.blit(title, (px + (pw - title.get_width()) // 2, py + 25))
        sub = self.font_sub.render('%s（ID:%s）' % (name, face_id), True, SUBTLE_COLOR)
        self.screen.blit(sub, (px + (pw - sub.get_width()) // 2, py + 90))

        # 当前灯效
        current_eff = get_effect_for_face_id(face_id, self.face_effect_map)
        cur_text = '当前：%s' % EFFECT_NAMES.get(current_eff, current_eff)
        cur_surf = self.font_list_eff.render(cur_text, True,
                                          EFFECT_COLORS.get(current_eff, SUBTLE_COLOR))
        self.screen.blit(cur_surf, (px + (pw - cur_surf.get_width()) // 2, py + 140))

        # 灯效列表（行高加大，背景框与文字不重叠）
        self.effect_picker_rects = []
        list_y = py + 195
        item_h = 68   # 行间距加大，点击区域更大
        item_gap = 8  # 背景框之间的间隙
        mouse_pos = pygame.mouse.get_pos()
        for i, eff_key in enumerate(EFFECT_LIST):
            iy = list_y + i * item_h
            # 背景框高度 = item_h - item_gap，留出间隙避免视觉拥挤
            item_rect = pygame.Rect(px + 45, iy, pw - 90, item_h - item_gap)
            is_selected = (eff_key == current_eff)
            is_hovered = item_rect.collidepoint(mouse_pos)

            # 行背景
            if is_selected:
                bg_color = (60, 180, 80, 60)
            elif is_hovered:
                bg_color = (100, 149, 237, 40)
            else:
                bg_color = (245, 245, 250, 120)
            bg = pygame.Surface(item_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(bg, bg_color, bg.get_rect(), border_radius=10)
            if is_selected:
                pygame.draw.rect(bg, SUCCESS_COLOR, bg.get_rect(), 2, border_radius=10)
            self.screen.blit(bg, item_rect.topleft)
            self.effect_picker_rects.append((item_rect, eff_key))

            # 灯效名（大字体，垂直居中）
            eff_name = EFFECT_NAMES[eff_key]
            eff_color = EFFECT_COLORS[eff_key]
            label = self.font_list.render(eff_name, True, eff_color)
            label_y = item_rect.y + (item_rect.height - label.get_height()) // 2
            self.screen.blit(label, (item_rect.x + 25, label_y))

            # 选中标记（垂直居中）
            if is_selected:
                check = self.font_list.render('✓', True, SUCCESS_COLOR)
                check_y = item_rect.y + (item_rect.height - check.get_height()) // 2
                self.screen.blit(check, (item_rect.right - 45, check_y))

        # 重置按钮
        reset_y = list_y + len(EFFECT_LIST) * item_h + 20
        self.picker_reset_rect = pygame.Rect(px + 45, reset_y, (pw - 110) // 2, 56)
        reset_hovered = self.picker_reset_rect.collidepoint(mouse_pos)
        reset_bg = (220, 80, 80) if reset_hovered else (180, 60, 60)
        pygame.draw.rect(self.screen, reset_bg, self.picker_reset_rect, border_radius=10)
        reset_label = self.font_btn.render('重置默认', True, (255, 255, 255))
        self.screen.blit(reset_label,
                         (self.picker_reset_rect.centerx - reset_label.get_width() // 2,
                          self.picker_reset_rect.centery - reset_label.get_height() // 2))

        # 关闭按钮
        self.picker_close_rect = pygame.Rect(px + 45 + (pw - 110) // 2 + 20, reset_y,
                                              (pw - 110) // 2, 56)
        close_hovered = self.picker_close_rect.collidepoint(mouse_pos)
        close_bg = (100, 149, 237) if close_hovered else (70, 110, 200)
        pygame.draw.rect(self.screen, close_bg, self.picker_close_rect, border_radius=10)
        close_label = self.font_btn.render('关闭', True, (255, 255, 255))
        self.screen.blit(close_label,
                         (self.picker_close_rect.centerx - close_label.get_width() // 2,
                          self.picker_close_rect.centery - close_label.get_height() // 2))

    def handle_effect_picker_click(self, pos):
        """处理灯效选择弹窗的点击，返回 True 表示已处理"""
        if self.effect_picker_face_id is None:
            return False

        # 检查灯效选项
        for rect, eff_key in getattr(self, 'effect_picker_rects', []):
            if rect.collidepoint(pos):
                self.face_effect_map[self.effect_picker_face_id] = eff_key
                save_face_effect_map(self.face_effect_map)
                print('[灯效] %s(ID:%s) -> %s' % (
                    self.face_records.get(self.effect_picker_face_id, '?'),
                    self.effect_picker_face_id, eff_key))
                # 如果当前正在识别这个人，立即切换灯效
                if self.current_face_id == self.effect_picker_face_id:
                    self.current_effect = eff_key
                    set_led_effect(eff_key)
                self.effect_picker_face_id = None
                return True

        # 重置按钮
        if hasattr(self, 'picker_reset_rect') and self.picker_reset_rect.collidepoint(pos):
            if self.effect_picker_face_id in self.face_effect_map:
                del self.face_effect_map[self.effect_picker_face_id]
                save_face_effect_map(self.face_effect_map)
                print('[灯效] %s(ID:%s) -> 重置默认' % (
                    self.face_records.get(self.effect_picker_face_id, '?'),
                    self.effect_picker_face_id))
                if self.current_face_id == self.effect_picker_face_id:
                    default_eff = get_effect_for_face_id(self.effect_picker_face_id)
                    self.current_effect = default_eff
                    set_led_effect(default_eff)
            self.effect_picker_face_id = None
            return True

        # 关闭按钮
        if hasattr(self, 'picker_close_rect') and self.picker_close_rect.collidepoint(pos):
            self.effect_picker_face_id = None
            return True

        # 点击弹窗外部关闭
        self.effect_picker_face_id = None
        return True

    def draw_footer(self, mouse_pos):
        """绘制底部栏"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        hint = self.font_small.render(
            'ESC 退出  ·  对准摄像头即可自动识别  ·  点击右侧列表可修改人脸灯效',
            True, SUBTLE_COLOR)
        self.screen.blit(hint, (40, HEIGHT - self.FOOTER_H // 2 - hint.get_height() // 2))

    def run(self):
        """主循环

        采集线程在后台固定 0.15s 间隔采集帧，主循环只负责：
        1. 事件处理
        2. 识别结果检查（refresh_results 只读缓存，不访问 V4L2）
        3. 灯效更新
        4. 界面绘制
        """
        frame_counter = 0
        while self.running:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # 灯效选择弹窗优先处理点击
                    if self.effect_picker_face_id is not None:
                        self.handle_effect_picker_click(event.pos)
                    elif self.btn_exit.clicked(event.pos):
                        self.running = False
                    else:
                        # 检查是否点击了人脸列表项
                        for rect, face_id in self.face_item_rects:
                            if rect.collidepoint(event.pos):
                                self.effect_picker_face_id = face_id
                                print('[灯效] 打开选择器：%s(ID:%s)' % (
                                    self.face_records.get(face_id, '?'), face_id))
                                break
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.effect_picker_face_id is not None:
                            self.effect_picker_face_id = None
                        else:
                            self.running = False

            frame_counter += 1

            # 识别检查：每 15 帧一次（约 2 次/秒）
            # refresh_results() 只读取后台检测线程的缓存结果，不直接访问 V4L2
            if frame_counter % 15 == 0:
                self.check_recognition()

            # 每帧更新灯效
            update_led_frame()

            self.btn_exit.update(mouse_pos)

            self.screen.blit(self.bg, (0, 0))
            self.draw_title()
            self.draw_camera()
            self.draw_info_panel()
            self.draw_footer(mouse_pos)

            pygame.display.flip()
            self.clock.tick(30)

        # 退出清理
        self.capture_thread_running = False
        time.sleep(0.3)
        led_off()
        try:
            self.vision_system.cleanup()
        except Exception:
            pass
        pygame.quit()
        # 关闭日志文件
        try:
            _debug_log_fp.close()
        except Exception:
            pass


# ===================== 入口 =====================
if __name__ == '__main__':
    app = FaceRecognizeApp()
    app.run()
