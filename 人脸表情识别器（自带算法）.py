# -*- coding: utf-8 -*-
"""
人脸表情识别器 - 好搭AI派（v5.2 颜色对齐+日志分行修复）
==========================
修复项：
  1. 表情识别（全中性 bug 根因修复 ✅）：
     - V3 实际返回 8 类**首字母大写名词**：Happiness/Sadness/Anger/Surprise/Disgust/Fear/Contempt/Neutral
       之前 emotion_idx() 未转小写导致 'Happiness' 查不到，全部兜底中性；
     - 修复：emotion_idx() 先 .strip().lower() 再查表，英文大小写/名词形容词全部命中；
     - 补充 Contempt(轻蔑) → 归入 Disgust(厌恶)，语义最接近且 7 类 UI 不新增槽位；
     - conf_en 规范化增加未识别 key 告警日志，发现第 9+ 类可立即补映射。
  2. 界面拉伸 bug（全屏变超屏 ✅）：
     - 去掉 pygame.FULLSCREEN（物理屏>1920 时会拉伸模糊），
       改为和「手势控制RGB灯带」一致的 pygame.display.set_mode((WIDTH, HEIGHT))；
       好搭AI派桌面正好 1920×1080，视觉效果等同全屏且 1:1 不缩放；
     - SDL_VIDEO_CENTERED 放在 pygame.display.init() 之前设置，确保窗口居中。
  3. RGB 灯带不亮（根因修复 ✅，用户反馈 IO1 接 11 颗灯珠）：
     - 根因 A：**缺少 ws2812Init(pin, count) 初始化**，WS2812 必须先 Init 才能写；
     - 根因 B：ws2812Write 参数完全错位——原传 6 参数 (1,8,0,r,g,b)，
       API 实际为 5 参数 ws2812Write(pin, led_idx, r, g, b)，导致红色分量=0 永远黑灯；
     - 修复：ESP32 连接后先 ws2812Init(GPIO_IO_01, 11)，再做 255 批量+逐颗降级写入；
       _set_led(r,g,b) 统一 RGB 值钳制 0-255、首次失败打印日志不再静默吞错；
       底部状态栏精确区分"灯带就绪/Init失败/未连接"三态颜色。
  4. 界面↔灯带颜色错位（修复 ✅，用户反馈：开心=条黄/灯绿不对应）：
     - 原 EMOTION_LIST 7 个表情中 6 个的 color(UI条色) != led_rgb(灯带色)：
       开心黄/绿、悲伤矢车菊蓝/纯蓝、惊讶暗紫/紫红、厌恶海绿/青、
       恐惧灰/黄、中性灰蓝/白——全部 HUE 错位或分量不一致；
     - 修复：强制 color == led_rgb 完全相同（同色同分量），
       恐惧额外从 (160,160,160) 纯灰改为 (230,110,0) 警示橙（白背景可读、语义贴合）。
  5. 日志粘行/不实时（修复 ✅）：
     - open() buffering=-1(全缓冲 8KB) → buffering=1(行缓冲)，崩溃不丢实时日志；
     - _TeeStdout.write() 捕获 ESP32/V3 底层 `sys.stdout.write(无\\n)` 的粘行场景，
       写入文件时若结尾无 \n 自动补，保证日志文件每条独立一行。
"""

import time
import signal
import threading
import sys
import os as _os
import datetime as _datetime
import re as _re

# =============== pygame 启动前必须设置的环境变量 ===============
_os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
_os.environ.setdefault('SDL_VIDEO_CENTERED', '1')  # 1920×1080 窗口桌面居中

import pygame
import cv2
import numpy as np

try:
    from ESP32 import *
    _ESP32_AVAILABLE = True
    _ESP32_ERROR = None
except Exception as _e:
    _ESP32_AVAILABLE = False
    _ESP32_ERROR = _e

try:
    from camera_vision_system_v3 import create_vision_system_v3, FACIAL_EXPRESSION_AVAILABLE
    _VISION_SYSTEM_AVAILABLE = True
    _VISION_SYSTEM_ERROR = None
except Exception as _e:
    _VISION_SYSTEM_AVAILABLE = False
    _VISION_SYSTEM_ERROR = _e
    FACIAL_EXPRESSION_AVAILABLE = False


# ===================== 日志 =====================
_LOG_DIR = 'logs'
if not _os.path.exists(_LOG_DIR):
    try:
        _os.makedirs(_LOG_DIR)
    except Exception:
        pass
_LOG_FILE = _os.path.join(
    _LOG_DIR,
    '人脸表情识别器_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
)
_debug_log_fp = open(_LOG_FILE, 'a', encoding='utf-8', buffering=1)
_debug_log_fp.write('\n\n======== %s 运行开始（v5.2 颜色对齐+日志分行）========\n' %
                    _datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
_debug_log_fp.flush()

_V3_SPAM_PATTERNS = [
    _re.compile(r'^检测到\d+个人脸，使用第一个进行识别\s*$'),
]


class _TeeStdout:
    def __init__(self, original):
        self.original = original

    def write(self, msg):
        self.original.write(msg)
        if not msg or msg.isspace():
            return
        try:
            _stripped = msg.strip()
            for _pat in _V3_SPAM_PATTERNS:
                if _pat.match(_stripped):
                    return
            _debug_log_fp.write(msg)
            # 防止 ESP32/V3 库底层直接 stdout.write(无\n) 导致日志粘行
            if not msg.endswith('\n'):
                _debug_log_fp.write('\n')
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


# ===================== 常量（1920×1080 硬约束）=====================
WIDTH, HEIGHT = 1920, 1080
TITLE_H = 130
FOOTER_H = 110
PANEL_GAP = 20                  # 标题栏-面板、面板-底部栏之间的小间隙
CAM_DISP_W, CAM_DISP_H = 880, 660
CAMERA_W, CAMERA_H = 1280, 720
DETECT_INTERVAL = 15

# ---- RGB 灯带配置（项目约束：IO1 接口，11 颗灯珠）参照手势控制RGB灯带.py ----
try:
    # ESP32 库通过 from ESP32 import * 已导出 GPIO_IO_01
    LED_PIN = GPIO_IO_01
except Exception:
    LED_PIN = 1  # 兜底：扩展板 IO1 引脚编号恒为 1
LED_COUNT = 11  # 用户硬件：IO1 接口接 11 颗 WS2812 灯珠

FONT_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'

# ---- 配色 ----
BG_TOP = (135, 206, 235)
BG_BOTTOM = (220, 240, 255)
PANEL_COLOR = (255, 255, 255)
PANEL_BORDER = (100, 149, 237)
TITLE_COLOR = (25, 60, 130)
TEXT_COLOR = (50, 50, 60)
SUBTLE_COLOR = (120, 130, 150)
ACCENT_COLOR = (255, 140, 0)
SUCCESS_COLOR = (60, 180, 80)
ERROR_COLOR = (220, 80, 80)
EXIT_COLOR = (220, 80, 80)
EXIT_HOVER = (255, 100, 100)
RESET_COLOR = (70, 110, 200)
RESET_HOVER = (100, 149, 237)

# ---- 表情配置（中英文映射，含变体兼容）----
EMOTION_LIST = [
    # ⚠️ color（界面条/标签字色）和 led_rgb（WS2812灯带）必须完全相同，
    #    避免「界面是X色但灯是Y色」的感知错位。v5.2 修复用户反馈：
    #    原 开心=UI金黄(255,193,7)+LED绿(0,255,0) 完全不对应。
    {'key': 'happy',     'name': '开心', 'color': (255, 193, 7),   'led_rgb': (255, 193, 7)},   # 金黄（笑脸黄）
    {'key': 'sad',       'name': '悲伤', 'color': (100, 149, 237), 'led_rgb': (100, 149, 237)}, # 矢车菊蓝
    {'key': 'angry',     'name': '愤怒', 'color': (220, 50, 50),   'led_rgb': (220, 50, 50)},   # 正红
    {'key': 'surprised', 'name': '惊讶', 'color': (180, 80, 220),  'led_rgb': (180, 80, 220)},  # 紫
    {'key': 'disgusted', 'name': '厌恶', 'color': (85, 160, 85),   'led_rgb': (85, 160, 85)},   # 海绿
    {'key': 'fearful',   'name': '恐惧', 'color': (230, 110, 0),   'led_rgb': (230, 110, 0)},   # 警示橙（原灰→对比度/语义更贴合）
    {'key': 'neutral',   'name': '中性', 'color': (120, 130, 150), 'led_rgb': (120, 130, 150)}, # 冷灰蓝
]

# 构建多对一映射：别名/大小写/中文 → 标准 key
EMOTION_ALIAS_MAP = {}
for _i, _emo in enumerate(EMOTION_LIST):
    for _alias in [
        _emo['key'], _emo['key'].upper(), _emo['key'].capitalize(),
        _emo['name'],
    ]:
        EMOTION_ALIAS_MAP[_alias] = _i
# 补充常见名词变体（V3 返回首字母大写名词：Happiness/Sadness/Anger/Surprise/Disgust/Fear/Contempt/Neutral）
# 统一查前转小写，所以这里只存小写 key
_EXTRA_ALIASES = {
    'happiness': 0, 'happy.': 0, 'pleased': 0, 'glad': 0,
    'sadness': 1, 'unhappy': 1, 'sorrow': 1,
    'anger': 2, 'rage': 2, 'mad': 2,
    'surprise': 3, 'astonished': 3, 'amazed': 3,
    'disgust': 4, 'revulsion': 4, 'contempt': 4,  # Contempt轻蔑→归入厌恶（语义最接近）
    'fear': 5, 'scared': 5, 'afraid': 5, 'frightened': 5,
    'calm': 6, 'normal': 6, 'none': 6, 'expressionless': 6,
}
for _k, _i in _EXTRA_ALIASES.items():
    EMOTION_ALIAS_MAP[_k] = _i

ENGAGEMENT_CN_MAP = {
    'high': '高投入', 'HIGH': '高投入', '高': '高投入', '高投入': '高投入',
    'medium': '中投入', 'MEDIUM': '中投入', '中': '中投入', '中投入': '中投入',
    'low': '低投入', 'LOW': '低投入', '低': '低投入', '低投入': '低投入',
}
ENGAGEMENT_COLOR_MAP = {
    '高投入': (60, 180, 80), '中投入': (255, 165, 0), '低投入': (220, 80, 80),
}


def emotion_idx(value):
    """任意返回值 → EMOTION_LIST 索引（找不到返回 6=中性）
    关键：V3 返回首字母大写名词（Happiness/Sadness/Anger/Contempt...），
    这里统一 strip + lower，确保无论大小写、名词形容词变体都能命中。"""
    if value is None:
        return 6
    _key = str(value).strip()
    # 只有纯 ASCII 字母才转小写（避免中文 lower 后也无害，但主要是处理英文）
    _key_lower = _key.lower()
    if _key_lower in EMOTION_ALIAS_MAP:
        return EMOTION_ALIAS_MAP[_key_lower]
    # fallback：原始 key 直接查（应对中文、数字等）
    return EMOTION_ALIAS_MAP.get(_key, 6)


def emotion_cfg(value):
    return EMOTION_LIST[emotion_idx(value)]


def emotion_cn(value):
    return emotion_cfg(value)['name']


def engagement_cn(value):
    if value is None:
        return '中投入'
    return ENGAGEMENT_CN_MAP.get(str(value).strip(), '中投入')


def engagement_color(cn_name):
    return ENGAGEMENT_COLOR_MAP.get(cn_name, SUBTLE_COLOR)


# ===================== 工具函数 =====================
def make_gradient_bg(width, height, top, bottom):
    surf = pygame.Surface((width, height))
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        pygame.draw.line(surf, (r, g, b), (0, y), (width, y))
    return surf


def cvframe_to_surface(frame, target_w, target_h):
    if frame is None:
        return None
    try:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        transposed = np.transpose(rgb, (1, 0, 2))
        surf = pygame.surfarray.make_surface(transposed)
        return pygame.transform.scale(surf, (target_w, target_h)).convert()
    except Exception:
        return None


def _load_font(size, bold=False):
    fp = FONT_BOLD_PATH if bold else FONT_PATH
    try:
        if _os.path.exists(fp):
            return pygame.font.Font(fp, size)
    except Exception:
        pass
    try:
        if _os.path.exists(FONT_PATH):
            return pygame.font.Font(FONT_PATH, size)
    except Exception:
        pass
    try:
        return pygame.font.SysFont('sans-serif', size)
    except Exception:
        return pygame.font.Font(None, size)


def clamp_text(font, text, max_width, ellipsis='…'):
    """渲染文本并在超过 max_width 时截断+加省略号，返回 (surface, rect_w)"""
    if text is None:
        text = ''
    text = str(text)
    surf = font.render(text, True, TEXT_COLOR)
    if surf.get_width() <= max_width:
        return surf, surf.get_width()
    # 二分法截断
    lo, hi = 0, len(text)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        t = text[:mid] + ellipsis
        s = font.render(t, True, TEXT_COLOR)
        if s.get_width() <= max_width:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best <= 0:
        # 连省略号都放不下，返回一个点
        t = ellipsis[:1] if ellipsis else '.'
        return font.render(t, True, TEXT_COLOR), 0
    final_text = text[:best] + ellipsis
    s = font.render(final_text, True, TEXT_COLOR)
    return s, s.get_width()


class Button:
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
        c = (180, 180, 180) if not self.enabled else (
            self.hover_color if self.hovered else self.color)
        btn = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn, c, btn.get_rect(), border_radius=14)
        pygame.draw.rect(btn, (255, 255, 255, 200), btn.get_rect(), 2, border_radius=14)
        surf.blit(btn, self.rect.topleft)
        # 文本做最大宽度裁剪，不超出按钮边框
        max_w = self.rect.width - 16
        label_surf, _ = clamp_text(font, self.text, max_w)
        lr = label_surf.get_rect(center=self.rect.center)
        surf.blit(label_surf, lr)

    def clicked(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


# ===================== 主程序 =====================
class FacialExpressionApp:
    def __init__(self):
        pygame.display.init()
        pygame.font.init()
        try:
            pygame.mixer.init()
            print('[pygame] mixer初始化成功')
        except Exception as _e:
            print('[pygame] mixer初始化失败:', _e)

        # 参考 手势控制RGB灯带.py：不使用 FULLSCREEN（会拉伸物理屏>1920），严格 1920×1080 普通窗口
        # 好搭AI派桌面正好是 1920×1080，窗口标题栏在桌面模式下几乎贴合=全屏效果，且像素 1:1 不缩放
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('人脸表情识别器')
        pygame.mouse.set_visible(True)
        self.clock = pygame.time.Clock()

        # ---- 字体（压缩版：保证整体高度不溢出）----
        self.font_title = _load_font(60, bold=True)      # 标题栏大标题 64→60
        self.font_sub = _load_font(30)                     # 副标题/摄像头标题 32→30
        self.font_sub_bold = _load_font(30, bold=True)
        self.font_item = _load_font(26)                    # 条形图/小标题 30→26（关键压缩）
        self.font_btn = _load_font(30, bold=True)          # 按钮 34→30
        self.font_small = _load_font(22)                   # 子项 24→22
        self.font_status = _load_font(24)                  # 底部栏第二行 26→24
        self.font_big = _load_font(44, bold=True)          # 投入度 56→44（关键压缩）
        self.font_huge = _load_font(90, bold=True)         # 超大表情 120→90（关键压缩）
        self.font_log = _load_font(24)                     # 变化记录 26→24

        # ---- 背景 ----
        try:
            _bg_raw = pygame.image.load('images/1.jpg')
            self.bg = pygame.transform.smoothscale(_bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception:
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # ---- 面板尺寸（严格计算，保证不溢出）----
        # 可用面板区域高度 = 1080 - 130 - 20（标题下间隙）- 20（底栏上间隙）- 110 = 800
        PANEL_H = HEIGHT - TITLE_H - PANEL_GAP - PANEL_GAP - FOOTER_H  # 800
        PANEL_TOP = TITLE_H + PANEL_GAP  # 150
        # 左：摄像头面板
        CAM_PAD = 20
        self.cam_rect = pygame.Rect(
            60, PANEL_TOP,
            CAM_DISP_W + CAM_PAD * 2, PANEL_H
        )
        # 右：表情分析面板（与左等高）
        RIGHT_MARGIN = 60
        RIGHT_LEFT = self.cam_rect.right + PANEL_GAP
        RIGHT_W = WIDTH - RIGHT_LEFT - RIGHT_MARGIN
        self.info_rect = pygame.Rect(RIGHT_LEFT, PANEL_TOP, RIGHT_W, PANEL_H)
        print('[布局] 左面板%dx%d 右面板%dx%d 高=%d（保证等高）' % (
            self.cam_rect.width, self.cam_rect.height,
            self.info_rect.width, self.info_rect.height, PANEL_H))

        # ---- 按钮 ----
        self.btn_exit = Button((WIDTH - 280, 30, 240, 70), '退出程序', EXIT_COLOR, EXIT_HOVER)
        # 重置按钮：缩小到 info_rect 顶部右侧（160×46，不挤压标题）
        self.btn_reset = Button(
            (self.info_rect.right - 170, self.info_rect.y + 14, 160, 46),
            '重置记录', RESET_COLOR, RESET_HOVER
        )

        # ---- 运行状态 ----
        self.running = True
        self.frame_count = 0
        self.raw_frame = None
        self.frame_lock = threading.Lock()
        self.capture_thread_running = True
        self.start_time = time.time()

        # 检测结果
        self.last_success = False
        self.last_emotion_idx = 6          # 永远存索引，避免映射反复不匹配
        self.last_emotion_conf = 0.0
        self.last_emotions_conf_en = {}    # 保存英文key→置信度，显示时再转中文
        self.last_engagement = '中投入'
        self.last_engagement_conf = {}
        self.last_inference_time = 0.0

        # 表情变化记录（限制 6 条，高度可控）
        self.change_log = []
        self.prev_emotion_idx = None

        # FPS
        self.fps = 0.0
        self._fps_start = time.time()
        self._fps_frames = 0

        # 调试日志：检测成功次数计数器，每隔N次打印原始返回值
        self._detect_success_count = 0

        # ESP32 + WS2812 RGB 灯带（手势控制RGB灯带.py 初始化流程）
        self.board = None
        self._led_ok = False  # 灯带初始化是否成功
        if _ESP32_AVAILABLE:
            try:
                self.board = ESP32()
                if self.board.start():
                    print('[ESP32] 扩展板已连接')
                    # ===== WS2812 灯带：必须先 Init，否则 Write 无效 =====
                    try:
                        self.board.ws2812Init(LED_PIN, LED_COUNT)
                        # 先试"全灭"一次确认通信正常
                        try:
                            # 范例：index=255 表示对全部灯珠写入（高效）
                            self.board.ws2812Write(LED_PIN, 255, 0, 0, 0)
                        except Exception:
                            # 某些固件不支持 255 批量：降级逐颗 0..LED_COUNT-1
                            for _i in range(LED_COUNT):
                                self.board.ws2812Write(LED_PIN, _i, 0, 0, 0)
                        self._led_ok = True
                        print('[灯带] WS2812 初始化成功：IO%d，%d 颗灯珠（已熄灭）' % (LED_PIN, LED_COUNT))
                    except Exception as _le:
                        print('[灯带] WS2812 初始化失败：', _le)
                        self._led_ok = False
                else:
                    print('[ESP32] 扩展板启动失败')
                    self.board = None
            except Exception as _e:
                print('[ESP32] 初始化异常:', _e)
                self.board = None

        # V3
        self.camera_ok = False
        self.vision_system = None
        self._init_vision_system()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    # ==============================================================
    # 加载画面
    # ==============================================================
    def _draw_loading_screen(self, msg):
        self.screen.blit(self.bg, (0, 0))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((255, 255, 255, 200))
        self.screen.blit(overlay, (0, 0))
        text, _ = clamp_text(self.font_title, msg, WIDTH - 200)
        self.screen.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - 60))
        sub, _ = clamp_text(self.font_sub, '请稍候...  日志: %s' % _LOG_FILE, WIDTH - 200)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 20))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._emergency_quit()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._emergency_quit()

    def _emergency_quit(self):
        try:
            pygame.quit()
        except Exception:
            pass
        try:
            _debug_log_fp.close()
        except Exception:
            pass
        _os._exit(0)

    # ==============================================================
    # 摄像头 V4L2 预检测
    # ==============================================================
    def _detect_camera_id(self):
        candidates = [41, 40, 42]
        for cam_id in candidates:
            dev_path = '/dev/video%d' % cam_id
            if not _os.path.exists(dev_path):
                print('[摄像头探测] %s 节点不存在，跳过' % dev_path)
                continue
            cap = cv2.VideoCapture(dev_path, cv2.CAP_V4L2)
            if not cap.isOpened():
                cap.release()
                continue
            valid = False
            for _ in range(5):
                ret, frame = cap.read()
                if ret and frame is not None and hasattr(frame, 'shape') and len(frame.shape) == 3:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if 5 < gray.mean() < 250:
                        valid = True
                        break
            cap.release()
            if valid:
                print('[摄像头探测] ✓ %s 可用（ID=%d）' % (dev_path, cam_id))
                time.sleep(0.3)
                return cam_id
            else:
                print('[摄像头探测] %s 无有效帧' % dev_path)
        print('[摄像头探测] 41/40/42 均不可用')
        return None

    # ==============================================================
    # V3 初始化
    # ==============================================================
    def _init_vision_system(self):
        if not _VISION_SYSTEM_AVAILABLE:
            print('[V3] 库不可用:', _VISION_SYSTEM_ERROR)
            return
        if not FACIAL_EXPRESSION_AVAILABLE:
            print('[V3] 表情模块不可用')
            return

        self._draw_loading_screen('正在探测摄像头（41 → 40 → 42）...')
        cam_id = self._detect_camera_id()
        if cam_id is None:
            return

        self._draw_loading_screen('正在加载 RKNN 表情识别模型...')
        try:
            self.vision_system = create_vision_system_v3(
                camera_id=cam_id, width=CAMERA_W, height=CAMERA_H,
                enable_basic=False, enable_advanced=False, auto_detect=False,
            )
            print('[V3] 实例创建成功')
        except Exception as _e:
            print('[V3] 创建失败:', _e)
            return

        self.vision_system.detection_config.enable_facial_expression = True
        print('[V3] 已启用 facial_expression（自动加载人脸识别属正常）')

        self._draw_loading_screen('正在初始化检测器（RKNN 模型加载中）...')
        try:
            self.vision_system._init_detectors()
            print('[V3] 检测器初始化完成')
        except Exception as _e:
            print('[V3] _init_detectors 失败:', _e)

        self._draw_loading_screen('正在打开摄像头（ID=%d）...' % cam_id)
        try:
            if self.vision_system.open_camera():
                self.camera_ok = True
                print('[V3] 摄像头打开成功')
            else:
                print('[V3] open_camera=False')
        except Exception as _e:
            print('[V3] open_camera 异常:', _e)

        if self.camera_ok:
            self._draw_loading_screen('正在启动后台检测...')
            try:
                self.vision_system.threaded_system.start_background_detection(show_preview=False)
                print('[V3] 后台检测线程已启动')
            except Exception as _e:
                print('[V3] 启动后台检测失败:', _e)

    # ==============================================================
    # 帧采集线程
    # ==============================================================
    def _capture_loop(self):
        time.sleep(0.5)
        print('[帧线程] 帧采集线程启动')
        while self.capture_thread_running:
            if not self.camera_ok or self.vision_system is None:
                time.sleep(0.3)
                continue
            try:
                frame = self.vision_system.capture_frame()
                if frame is not None and isinstance(frame, np.ndarray) and frame.ndim == 3:
                    with self.frame_lock:
                        self.raw_frame = frame
                    self._fps_frames += 1
                    _now = time.time()
                    if _now - self._fps_start >= 1.0:
                        self.fps = self._fps_frames / (_now - self._fps_start)
                        self._fps_frames = 0
                        self._fps_start = _now
            except Exception as _e:
                print('[帧线程] 采集异常:', _e)
            time.sleep(0.15)
        print('[帧线程] 帧采集线程退出')

    # ==============================================================
    # 表情检测（核心修复：主表情用全置信度最大值+扩展别名）
    # ==============================================================
    def _refresh_detection(self):
        self.frame_count += 1
        if self.frame_count % DETECT_INTERVAL != 0:
            return
        if self.vision_system is None:
            return

        try:
            self.vision_system.result_accessor.refresh_results()
            _success = self.vision_system.result_accessor.get_facial_expression_success()
            self.last_success = bool(_success) if _success is not None else False

            if self.last_success:
                self._detect_success_count += 1

                # 1) 先拿全置信度字典 → 主表情从这里取最大置信度
                conf_dict_raw = None
                try:
                    conf_dict_raw = self.vision_system.result_accessor.get_facial_expression_emotions_confidence()
                except Exception as _e:
                    print('[检测] emotions_conf() 异常:', _e)
                    conf_dict_raw = None

                # 规范化：英文key → 置信度
                conf_en = {}
                _unmatched_keys = []
                if isinstance(conf_dict_raw, dict):
                    for _k, _v in conf_dict_raw.items():
                        try:
                            _idx = emotion_idx(_k)
                            _key = EMOTION_LIST[_idx]['key']
                            if _key not in conf_en or float(_v) > conf_en[_key]:
                                conf_en[_key] = float(_v)
                            # 记录未识别的 key（原始 key 不在已知别名表，或者被兜到中性但不是 Neutral/Contempt）
                            _raw_lower = str(_k).strip().lower()
                            if _raw_lower not in EMOTION_ALIAS_MAP and _raw_lower != 'neutral':
                                _unmatched_keys.append('%s=%s' % (_k, _v))
                        except Exception:
                            pass
                if _unmatched_keys and self._detect_success_count % 5 == 1:
                    print('[检测-警告] conf_dict 中存在未识别 key：%s' % ', '.join(_unmatched_keys))
                self.last_emotions_conf_en = conf_en

                # 选最大值作为主表情
                best_idx = 6  # 中性兜底
                best_conf = 0.0
                if conf_en:
                    for _key, _v in conf_en.items():
                        if _v > best_conf:
                            best_conf = _v
                            best_idx = emotion_idx(_key)

                # 2) 单一 emotion() 返回值作为交叉参考，如果置信度接近就用它
                try:
                    emo_raw = self.vision_system.result_accessor.get_facial_expression_emotion()
                    emo_idx2 = emotion_idx(emo_raw)
                    emo_conf2 = conf_en.get(EMOTION_LIST[emo_idx2]['key'], 0.0)
                    # 如果 emotion() 结果置信度 >= 最大置信度 * 0.8，则尊重 emotion() 返回
                    if emo_conf2 >= best_conf * 0.8 and emo_conf2 > 0:
                        best_idx = emo_idx2
                        best_conf = emo_conf2
                except Exception as _e:
                    print('[检测] emotion() 异常:', _e)

                self.last_emotion_idx = best_idx
                self.last_emotion_conf = best_conf

                # 调试日志：每 5 次成功检测打印一次原始返回值（观察 V3 返回格式）
                if self._detect_success_count % 5 == 1:
                    try:
                        _emo_raw_debug = self.vision_system.result_accessor.get_facial_expression_emotion()
                    except Exception:
                        _emo_raw_debug = '<异常>'
                    _conf_debug_pairs = []
                    if isinstance(conf_dict_raw, dict):
                        for _dk, _dv in list(conf_dict_raw.items())[:7]:
                            try:
                                _conf_debug_pairs.append('%s=%.3f' % (str(_dk), float(_dv)))
                            except Exception:
                                _conf_debug_pairs.append('%s=%s' % (str(_dk), str(_dv)[:10]))
                    print('[检测-调试 #%d] emotion()=[%s] type=%s | 主表情=%s(%.3f) | conf_dict_keys_type=%s: {%s}' % (
                        self._detect_success_count,
                        str(_emo_raw_debug),
                        type(_emo_raw_debug).__name__,
                        EMOTION_LIST[best_idx]['name'],
                        best_conf,
                        type(list(conf_dict_raw.keys())[0]).__name__ if isinstance(conf_dict_raw, dict) and conf_dict_raw else '空',
                        ', '.join(_conf_debug_pairs)
                    ))

                # 3) 投入度
                try:
                    _eng_raw = self.vision_system.result_accessor.get_facial_expression_engagement()
                    self.last_engagement = engagement_cn(_eng_raw)
                except Exception:
                    self.last_engagement = '中投入'
                try:
                    _eng_conf = self.vision_system.result_accessor.get_facial_expression_engagement_confidence()
                    self.last_engagement_conf = dict(_eng_conf) if isinstance(_eng_conf, dict) else {}
                except Exception:
                    self.last_engagement_conf = {}

                # 4) 推理耗时
                try:
                    _t = self.vision_system.result_accessor.get_facial_expression_inference_time()
                    self.last_inference_time = float(_t) if _t is not None else 0.0
                except Exception:
                    self.last_inference_time = 0.0

                # 5) 变化记录（最多 6 条）
                if self.prev_emotion_idx != self.last_emotion_idx:
                    _now_str = _datetime.datetime.now().strftime('%H:%M:%S')
                    if self.prev_emotion_idx is not None:
                        self.change_log.insert(0, (
                            _now_str,
                            EMOTION_LIST[self.prev_emotion_idx]['name'],
                            EMOTION_LIST[self.last_emotion_idx]['name'],
                            self.last_emotion_conf
                        ))
                        if len(self.change_log) > 6:
                            self.change_log = self.change_log[:6]
                        print('[表情变化] %s → %s（%.1f%%）' % (
                            EMOTION_LIST[self.prev_emotion_idx]['name'],
                            EMOTION_LIST[self.last_emotion_idx]['name'],
                            self.last_emotion_conf * 100
                        ))
                    self.prev_emotion_idx = self.last_emotion_idx

                # 6) 灯带
                _rgb = EMOTION_LIST[self.last_emotion_idx]['led_rgb']
                self._set_led(_rgb[0], _rgb[1], _rgb[2])
            else:
                self._set_led(0, 0, 0)
                self.prev_emotion_idx = None

        except Exception as _e:
            print('[检测] 刷新异常:', _e)

    # ==============================================================
    # LED / 工具
    # 参照手势控制RGB灯带.py：
    #   ws2812Init(pin, count)       → 先初始化
    #   ws2812Write(pin, idx, r, g, b) → 5参数：idx=255 全部/0..N-1 单颗
    # 原 bug：传了 6 参数 (1,8,0,r,g,b)，R=0 永远黑灯，且缺 Init
    # ==============================================================
    def _set_led(self, r, g, b):
        """点亮全部 LED_COUNT(11) 颗灯珠为同一颜色；r/g/b 范围 0-255"""
        if self.board is None or not self._led_ok:
            return
        r = int(max(0, min(255, r)))
        g = int(max(0, min(255, g)))
        b = int(max(0, min(255, b)))
        try:
            # 先尝试 index=255 批量写入（范例推荐，对 11 颗灯珠效率高）
            try:
                self.board.ws2812Write(LED_PIN, 255, r, g, b)
            except Exception:
                # 部分固件版本不支持 255 批量：降级逐颗循环 0..10
                for _i in range(LED_COUNT):
                    self.board.ws2812Write(LED_PIN, _i, r, g, b)
        except Exception as _e:
            # 不再静默吞错：第一次失败打日志，后续避免刷屏
            if not getattr(self, '_led_err_logged', False):
                print('[灯带] 写入失败（pin=%d, count=%d, rgb=%d,%d,%d）：%s' % (
                    LED_PIN, LED_COUNT, r, g, b, _e))
                self._led_err_logged = True

    def _led_off(self):
        """安全熄灭所有灯珠：即使 _led_ok=False 也尝试一次（用于 cleanup）"""
        if self.board is None:
            return
        try:
            try:
                self.board.ws2812Write(LED_PIN, 255, 0, 0, 0)
            except Exception:
                for _i in range(LED_COUNT):
                    self.board.ws2812Write(LED_PIN, _i, 0, 0, 0)
        except Exception:
            pass

    def fmt_duration(self):
        secs = int(time.time() - self.start_time)
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        return '%02d:%02d:%02d' % (h, m, s)

    def reset_records(self):
        self.change_log = []
        self.prev_emotion_idx = None
        _now_str = _datetime.datetime.now().strftime('%H:%M:%S')
        self.change_log.insert(0, (_now_str, '(重置)', '(重置)', 0.0))
        print('[重置] 表情变化记录已清空')

    # ==============================================================
    # 绘制：标题栏
    # ==============================================================
    def draw_title(self):
        mask = pygame.Surface((WIDTH, TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        # 大标题（居中，最大宽度 1000，超长省略）
        title, _ = clamp_text(self.font_title, '人脸表情识别器', 1000)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 20))

        # 副标题（居中，最大宽度 1400）
        sub_text = 'RKNN 本地离线识别 · RK3588S NPU 加速  ·  已运行 %s' % self.fmt_duration()
        sub, _ = clamp_text(self.font_sub, sub_text, 1400)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 92))

        self.btn_exit.draw(self.screen, self.font_btn)

    # ==============================================================
    # 绘制：摄像头面板
    # ==============================================================
    def draw_camera(self):
        panel = pygame.Surface(self.cam_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.cam_rect.topleft)

        # 标题（左）+ 状态（右），同 y=顶部+10
        head, _ = clamp_text(self.font_sub, '摄像头画面', 300)
        self.screen.blit(head, (self.cam_rect.x + 20, self.cam_rect.y + 10))

        status_text = '● 检测中' if self.last_success else ('● 已连接' if self.camera_ok else '○ 未连接')
        sc = SUCCESS_COLOR if self.last_success else (SUCCESS_COLOR if self.camera_ok else ERROR_COLOR)
        st_surf = self.font_small.render(status_text, True, sc)
        self.screen.blit(st_surf, (self.cam_rect.right - st_surf.get_width() - 20,
                                    self.cam_rect.y + 14))

        # 画面
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
            self.screen.blit(
                hint,
                (self.cam_rect.centerx - hint.get_width() // 2,
                 self.cam_rect.centery - hint.get_height() // 2)
            )

        # 右下角分辨率
        res = self.font_small.render('%d × %d' % (CAMERA_W, CAMERA_H), True, SUBTLE_COLOR)
        self.screen.blit(res, (self.cam_rect.right - res.get_width() - 20,
                               self.cam_rect.bottom - 25))

        # 画面叠加表情标签（宽度保护：不超过摄像头显示宽度-80）
        if self.last_success and frame is not None:
            emo_cfg = EMOTION_LIST[self.last_emotion_idx]
            _label = '%s  %.0f%%' % (emo_cfg['name'], self.last_emotion_conf * 100)
            _label_max_w = CAM_DISP_W - 80
            _label_surf = self._render_colored(
                self.font_sub_bold, ' ' + _label + ' ', (255, 255, 255), _label_max_w
            )
            _lw = _label_surf.get_width() + 20
            _lh = _label_surf.get_height() + 10
            _lx = self.cam_rect.x + 40
            _ly = self.cam_rect.y + self.cam_rect.height - _lh - 30
            pygame.draw.rect(self.screen, emo_cfg['color'], (_lx, _ly, _lw, _lh), border_radius=12)
            self.screen.blit(_label_surf, (_lx + 10, _ly + 5))

    # ==============================================================
    # 绘制：右侧表情分析面板（严格高度控制）
    # 高度预算 = 800（self.info_rect.height）
    #   标题区：60 → y=60
    #   当前表情：20(标签)+95(大字)+30(置信度)+20(间距)=165 → y=225
    #   分隔线 18 → 243
    #   投入度：26(标签)+50(大字)+2×24(子项)=124 → y=367
    #   分隔线 18 → 385
    #   7条条形图：26(标题)+7×(22bar+10gap)= 26+224=250 → y=635
    #   分隔线 18 → 653
    #   表情变化记录：26(标题)+6×24(行)= 26+144=170 → y=823 < 800？修正：
    #   重新紧缩：记录 5 条，行高 22 → 26+5×22=136 → 653+136=789，结余 11px ✓
    # ==============================================================
    def draw_info_panel(self):
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 24
        x_end = self.info_rect.right - 24
        cx = (x + x_end) // 2
        y = self.info_rect.y + 14
        max_w = x_end - x

        # --- 1. 标题区：高度 46（y=14→60）---
        head, _ = clamp_text(self.font_sub, '表情分析', 240)
        self.screen.blit(head, (x, y + 4))
        self.btn_reset.draw(self.screen, self.font_btn)
        y = self.info_rect.y + 60  # 固定跳到 y=60，保证后续区块对齐

        # --- 2. 当前表情（y=60 → 220，高160）---
        cur_label = self.font_item.render('当前表情', True, TEXT_COLOR)
        self.screen.blit(cur_label, (x, y))
        y += 24  # 标签高
        if self.last_success:
            emo_cfg = EMOTION_LIST[self.last_emotion_idx]
            _huge, _ = clamp_text(self.font_huge, emo_cfg['name'], max_w)
            self.screen.blit(_huge, (cx - _huge.get_width() // 2, y))
            _conf = '置信度 %.1f%%' % (self.last_emotion_conf * 100)
            _conf_surf, _ = clamp_text(self.font_sub, _conf, max_w)
            self.screen.blit(_conf_surf, (cx - _conf_surf.get_width() // 2,
                                           y + _huge.get_height() + 6))
            y += _huge.get_height() + _conf_surf.get_height() + 18  # ≈ 90+30+18 = 138
        else:
            _none, _ = clamp_text(self.font_huge, '未检测', max_w)
            self.screen.blit(_none, (cx - _none.get_width() // 2, y))
            y += _none.get_height() + 18

        # 分隔线
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 14  # 分隔线下间距

        # --- 3. 投入度（y → y+110 左右）---
        _eng_title = self.font_item.render('投入度等级', True, TEXT_COLOR)
        self.screen.blit(_eng_title, (x, y))
        y += 28
        if self.last_success:
            _ec = engagement_color(self.last_engagement)
            _eng_surf, _ = clamp_text(self.font_big, self.last_engagement, max_w)
            self.screen.blit(_eng_surf, (x, y))
            y += _eng_surf.get_height() + 6
            if isinstance(self.last_engagement_conf, dict):
                n = 0
                for _k, _v in self.last_engagement_conf.items():
                    if n >= 2:  # 最多 2 项，省高度
                        break
                    try:
                        _txt = '  · %s: %.1f%%' % (str(_k), float(_v) * 100)
                        _s, _ = clamp_text(self.font_small, _txt, max_w)
                        self.screen.blit(_s, (x, y))
                        y += 24
                        n += 1
                    except Exception:
                        pass
            y += 4
        else:
            _eng_surf = self.font_item.render('— —', True, SUBTLE_COLOR)
            self.screen.blit(_eng_surf, (x, y))
            y += 50

        # 分隔线
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 14

        # --- 4. 7 表情置信度（bar_h=22 gap=8，7×30=210 + 标题26 = 236，省14px给记录区）---
        _bar_title = self.font_item.render('全表情置信度分布', True, TITLE_COLOR)
        self.screen.blit(_bar_title, (x, y))
        y += 28

        _name_col_w = 80   # 表情名字段固定宽度 80
        _pct_col_w = 80    # 百分比固定宽度 80
        _bar_bg_x = x + _name_col_w
        _bar_w = x_end - _bar_bg_x - _pct_col_w - 14  # 条图宽度
        _bar_h = 22
        _bar_gap = 8
        for _emo in EMOTION_LIST:
            _name_surf, _ = clamp_text(self.font_item, _emo['name'], _name_col_w - 4)
            self.screen.blit(_name_surf, (x, y + 2))
            pygame.draw.rect(self.screen, (230, 235, 245),
                             (_bar_bg_x, y, _bar_w, _bar_h), border_radius=8)
            _conf = float(self.last_emotions_conf_en.get(_emo['key'], 0.0)) if self.last_success else 0.0
            _conf = max(0.0, min(1.0, _conf))
            _fill = int(_bar_w * _conf)
            if _fill > 0:
                pygame.draw.rect(self.screen, _emo['color'],
                                 (_bar_bg_x, y, _fill, _bar_h), border_radius=8)
            _pct = '%.0f%%' % (_conf * 100)
            _pct_surf = self.font_item.render(
                _pct, True, _emo['color'] if _conf > 0.3 else SUBTLE_COLOR
            )
            # 百分比右对齐 _pct_col_w
            pct_x = x_end - _pct_col_w + (_pct_col_w - _pct_surf.get_width())
            self.screen.blit(_pct_surf, (pct_x, y + 2))
            y += _bar_h + _bar_gap

        # 分隔线
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 14

        # --- 5. 表情变化记录（最多 5 条，行高 21，保证不溢出）---
        _log_head = self.font_item.render('表情变化记录', True, TITLE_COLOR)
        self.screen.blit(_log_head, (x, y))
        y += 26

        list_bottom = self.info_rect.bottom - 14  # 绝对不能越过
        row_h = 21
        if not self.change_log:
            _hint = self._render_colored(self.font_log, '暂无变化记录', SUBTLE_COLOR, max_w)
            self.screen.blit(_hint, (x, y))
        else:
            rows_printed = 0
            for t_str, old_e, new_e, conf in self.change_log:
                if y + row_h > list_bottom:
                    break
                if rows_printed >= 5:
                    break
                if old_e == '(重置)' and new_e == '(重置)':
                    arrow = '↻'
                    msg = '记录已重置'
                    color = ACCENT_COLOR
                else:
                    arrow = '→'
                    msg = '%s → %s（%.0f%%）' % (old_e, new_e, conf * 100)
                    color = emotion_cfg(new_e)['color']
                line = '%s %s %s' % (t_str, arrow, msg)
                _s = self._render_colored(self.font_log, line, color, max_w)
                self.screen.blit(_s, (x, y))
                y += row_h
                rows_printed += 1

    def _clamped_line_text(self, font, text, max_width, ellipsis='…'):
        """辅助：返回裁剪后的纯文本内容（不含渲染）"""
        lo, hi = 0, len(text)
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            t = text[:mid] + ellipsis
            if font.size(t)[0] <= max_width:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return (text[:best] + ellipsis) if best > 0 else text[:1]

    def _render_colored(self, font, text, color, max_width):
        """彩色文本+裁剪一体化：返回裁剪后的彩色 surface"""
        if text is None:
            text = ''
        text = str(text)
        if font.size(text)[0] <= max_width:
            return font.render(text, True, color)
        clipped = self._clamped_line_text(font, text, max_width)
        return font.render(clipped, True, color)

    # ==============================================================
    # 绘制：底部栏（4 列严格 x 坐标 + 裁剪，彻底杜绝重叠）
    # ==============================================================
    def draw_footer(self):
        mask = pygame.Surface((WIDTH, FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - FOOTER_H))
        _BY = HEIGHT - FOOTER_H

        # ------------------- 第一行（4 列绝对定位）-------------------
        # 列宽分配：440 | 400 | 400 | 剩余 680
        COL1_X = 40;       COL1_W = 440
        COL2_X = 500;      COL2_W = 380
        COL3_X = 900;      COL3_W = 340
        COL4_X = 1260;     COL4_W = WIDTH - COL4_X - 40

        # 列1：检测状态（标签 TEXT_COLOR + 值彩色）
        _s1 = self.font_status.render('检测状态：', True, TEXT_COLOR)
        self.screen.blit(_s1, (COL1_X, _BY + 16))
        _status_txt = '检测中·已识别' if self.last_success else (
            '运行中·未检测到人脸' if self.camera_ok else '摄像头不可用'
        )
        _status_c = SUCCESS_COLOR if self.last_success else (
            ACCENT_COLOR if self.camera_ok else ERROR_COLOR
        )
        _remain_w = COL1_W - _s1.get_width() - 10
        _s1b = self._render_colored(self.font_status, _status_txt, _status_c, _remain_w)
        self.screen.blit(_s1b, (COL1_X + _s1.get_width(), _BY + 16))

        # 列2：推理耗时
        _col2_text = '推理耗时：%.2f ms' % (self.last_inference_time * 1000) if self.last_success else '推理耗时：—'
        _s2 = self._render_colored(self.font_status, _col2_text, TEXT_COLOR, COL2_W)
        self.screen.blit(_s2, (COL2_X, _BY + 16))

        # 列3：采集帧率
        _col3_text = '采集帧率：%.1f FPS' % self.fps if self.fps > 0 else '采集帧率：—'
        _s3 = self._render_colored(self.font_status, _col3_text, TEXT_COLOR, COL3_W)
        self.screen.blit(_s3, (COL3_X, _BY + 16))

        # 列4：检测频率（橙色强调）
        _col4_text = '检测频率：每 %d 帧（≈ %.0f 次/秒）' % (DETECT_INTERVAL, 30.0 / DETECT_INTERVAL)
        _s4 = self._render_colored(self.font_status, _col4_text, ACCENT_COLOR, COL4_W)
        self.screen.blit(_s4, (COL4_X, _BY + 16))

        # ------------------- 第二行（3 列绝对定位）-------------------
        ROW2_Y = _BY + 64
        R2C1_X = 40;      R2C1_W = 500
        R2C2_X = 560;     R2C2_W = 680
        R2C3_X = 1260;    R2C3_W = WIDTH - R2C3_X - 40

        if self.board is not None and self._led_ok:
            _esp_txt = 'ESP32：已连接（灯带就绪·IO%d·%d颗）' % (LED_PIN, LED_COUNT)
            _esp_c = SUCCESS_COLOR
        elif self.board is not None and not self._led_ok:
            _esp_txt = 'ESP32：已连接（灯带初始化失败）'
            _esp_c = ACCENT_COLOR
        elif _ESP32_AVAILABLE:
            _esp_txt = 'ESP32：未连接（灯带不可用）'
            _esp_c = ERROR_COLOR
        else:
            _esp_txt = 'ESP32：库不可用'
            _esp_c = ERROR_COLOR
        _esp_surf = self._render_colored(self.font_status, _esp_txt, _esp_c, R2C1_W)
        self.screen.blit(_esp_surf, (R2C1_X, ROW2_Y))

        _v3_txt = ('视觉系统V3：表情识别就绪（RKNN本地）'
                   if _VISION_SYSTEM_AVAILABLE and FACIAL_EXPRESSION_AVAILABLE
                   else '视觉系统V3：%s' % ('表情模块不可用'
                   if not FACIAL_EXPRESSION_AVAILABLE else '库加载失败'))
        _v3_c = SUCCESS_COLOR if (_VISION_SYSTEM_AVAILABLE and FACIAL_EXPRESSION_AVAILABLE) else ERROR_COLOR
        _v3_surf = self._render_colored(self.font_status, _v3_txt, _v3_c, R2C2_W)
        self.screen.blit(_v3_surf, (R2C2_X, ROW2_Y))

        _help_txt = 'ESC退出  ·  R键/重置按钮 清空变化日志'
        _help_surf, _ = clamp_text(self.font_status, _help_txt, R2C3_W)
        self.screen.blit(_help_surf, (R2C3_X, ROW2_Y))

    # ==============================================================
    # 事件
    # ==============================================================
    def _handle_events(self):
        _mouse_pos = pygame.mouse.get_pos()
        self.btn_exit.update(_mouse_pos)
        self.btn_reset.update(_mouse_pos)
        for _ev in pygame.event.get():
            if _ev.type == pygame.QUIT:
                self.running = False
            elif _ev.type == pygame.KEYDOWN:
                if _ev.key == pygame.K_ESCAPE:
                    self.running = False
                elif _ev.key == pygame.K_r:
                    self.reset_records()
            elif _ev.type == pygame.MOUSEBUTTONDOWN and _ev.button == 1:
                if self.btn_exit.clicked(_ev.pos):
                    self.running = False
                elif self.btn_reset.clicked(_ev.pos):
                    self.reset_records()

    # ==============================================================
    # 清理
    # ==============================================================
    def _signal_handler(self, signum, _frame):
        print('\n[信号] 收到信号 %s，准备退出...' % signum)
        self.running = False

    def cleanup(self):
        print('[清理] 开始资源释放...')
        self.running = False
        self.capture_thread_running = False
        time.sleep(0.3)
        self._led_off()  # 安全熄灭：即使 _led_ok=False 也强制尝试
        if self.vision_system is not None:
            try:
                if hasattr(self.vision_system, 'threaded_system'):
                    self.vision_system.threaded_system.stop_background_detection()
                    print('[清理] 后台检测已停止')
            except Exception as _e:
                print('[清理] 停止后台检测异常:', _e)
            try:
                self.vision_system.cleanup()
                print('[清理] 视觉系统资源已释放')
            except Exception as _e:
                print('[清理] vision_system.cleanup 异常:', _e)
        if self.board is not None:
            try:
                self.board.stop()
                print('[清理] ESP32 已停止')
            except Exception:
                pass
        try:
            pygame.quit()
            print('[清理] pygame 已退出')
        except Exception:
            pass
        try:
            _debug_log_fp.write('\n======== %s 运行结束 ========\n' %
                                _datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            _debug_log_fp.close()
            print('[清理] 日志:', _LOG_FILE)
        except Exception:
            pass

    # ==============================================================
    # 主循环
    # ==============================================================
    def run(self):
        threading.Thread(target=self._capture_loop, daemon=True).start()
        print('[主循环] 进入主循环')
        try:
            while self.running:
                self._handle_events()
                if not self.running:
                    break
                self._refresh_detection()
                self.screen.blit(self.bg, (0, 0))
                self.draw_title()
                self.draw_camera()
                self.draw_info_panel()
                self.draw_footer()
                pygame.display.flip()
                self.clock.tick(30)
        except Exception as _e:
            print('[主循环] 未捕获异常:', _e)
        finally:
            self.cleanup()
            print('[主循环] 程序已退出')


# ===================== 入口 =====================
if __name__ == '__main__':
    print('=' * 60)
    print('人脸表情识别器 v5.2 · 好搭AI派（1920×1080 窗口·灯带IO%d×%d颗·色对版）' % (LED_PIN, LED_COUNT))
    print('=' * 60)
    print('视觉系统库:', _VISION_SYSTEM_AVAILABLE,
          '| 表情模块:', FACIAL_EXPRESSION_AVAILABLE if _VISION_SYSTEM_AVAILABLE else '-')
    print('ESP32库:', _ESP32_AVAILABLE)
    print('日志文件:', _LOG_FILE)
    print('检测频率: 每 %d 帧（≈ %.0f 次/秒）' % (DETECT_INTERVAL, 30.0 / DETECT_INTERVAL))
    print()
    FacialExpressionApp().run()
