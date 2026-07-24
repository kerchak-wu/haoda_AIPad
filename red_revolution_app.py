# -*- coding: utf-8 -*-
"""
浙西南革命精神 - 红色文化交互展示程序（好搭AI派）

功能：
  - 首页：背景 jingshen.png，中间两个按钮「浙南红地标」「浙红智助手」
  - P0 口人体红外传感器：感应到人时播放 huanying.wav（每次回到首页只播 1 次）
  - 浙南红地标：背景 hongdibiao.png，3 个按钮「王村口」「安岱后」「小吉村」
        点击对应地标 -> 切换为该地标图片并播放对应 wav
  - 浙红智助手：背景 wenda.png，实现大模型语音互动
  - 每个页面均有「返回」按钮（回到上一级）和「退出」按钮（退出程序）
  - P1 口接 WS2812 灯带（共 4 颗），根据屏幕内容与播音内容变换颜色与效果

资源文件命名：
  images/jingshen.png          首页背景（浙西南革命精神）
  images/hongdibiao.png        地标列表页背景（浙南红地标）
  images/wenda.png             AI 问答页背景（红军故事智能问答）
  images/wangcunkou.jpg        王村口
  images/andaihou.jpg          安岱后
  images/xiaojicun.jpg         小吉村
  recordings/huanying.wav      欢迎词
  recordings/wangcunkou.wav    王村口介绍
  recordings/andaihou.wav      安岱后介绍
  recordings/xiaojicun.wav     小吉村介绍

运行前请修改下方 USERNAME / PASSWORD 为你的好搭AI派账号。
图片放入 images/ 文件夹，音频放入 recordings/ 文件夹。
"""

import os
import sys
import math
import threading
import time
import pygame

# ---------- 硬件 / SDK 导入（缺失时自动降级，保证界面仍可运行） ----------
try:
    from ESP32 import ESP32
    from ESP32 import GPIO_IO_01, GPIO_IO_02
    ESP32_AVAILABLE = True
except Exception:
    ESP32_AVAILABLE = False
    GPIO_IO_01 = 1
    GPIO_IO_02 = 2

    class ESP32:  # 占位，便于在没有扩展板的环境中调试界面
        pass

try:
    from voice_api import VoiceAPI
    from audio_recorder import AudioRecorder
    from audio_player import AudioPlayer
    VOICE_AVAILABLE = True
except Exception:
    VOICE_AVAILABLE = False


# ---------- 配置 ----------
WIDTH, HEIGHT = 1920, 1080
IMAGE_DIR = "images"
AUDIO_DIR = "recordings"

# 各页面背景图
IMG_HOME = os.path.join(IMAGE_DIR, "jingshen.png")
IMG_LANDMARK_LIST = os.path.join(IMAGE_DIR, "hongdibiao.png")
IMG_AI = os.path.join(IMAGE_DIR, "wenda.png")

# 地标：(名称, 背景图, 介绍音频)
LANDMARKS = [
    ("王村口", os.path.join(IMAGE_DIR, "wangcunkou.jpg"), os.path.join(AUDIO_DIR, "wangcunkou.wav")),
    ("安岱后", os.path.join(IMAGE_DIR, "andaihou.jpg"), os.path.join(AUDIO_DIR, "andaihou.wav")),
    ("小吉村", os.path.join(IMAGE_DIR, "xiaojicun.jpg"), os.path.join(AUDIO_DIR, "xiaojicun.wav")),
]
WELCOME_AUDIO = os.path.join(AUDIO_DIR, "huanying.wav")

# 好搭AI派 端口 -> GPIO 编号（P0=IO1, P1=IO2；若你的主板编号不同请在此修改）
PIR_PIN = GPIO_IO_01   # P0：人体红外传感器
LED_PIN = GPIO_IO_02   # P1：WS2812 灯带
LED_COUNT = 4

# 好搭AI派账号 —— 请手动修改
USERNAME = "username"
PASSWORD = "password"
VOICE_API_URL = "http://www.haohaodada.com/project/voiceAI/ApiZNBW.php"

AI_RECORD_FILE = "ai_voice_chat.wav"
AI_ANSWER_FILE = "ai_answer.wav"

# ---------- 颜色 ----------
WHITE = (255, 255, 255)
TEXT_COLOR = (255, 255, 255)
ACCENT = (86, 196, 255)
GOLD = (255, 210, 90)
RED_THEME = (200, 50, 50)
BTN_NORMAL = (40, 90, 160, 70)         # 半透明蓝
BTN_HOVER = (86, 196, 255, 150)
BTN_GOLD_NORMAL = (160, 110, 30, 70)   # 半透明金棕
BTN_GOLD_HOVER = (255, 210, 90, 150)
BTN_RETURN_NORMAL = (60, 60, 60, 70)   # 半透明灰
BTN_RETURN_HOVER = (255, 255, 255, 140)
PANEL_COLOR = (0, 0, 0, 130)
EXIT_RED = (235, 87, 87)
BTN_EXIT_NORMAL = (160, 40, 40, 70)    # 半透明红
BTN_EXIT_HOVER = (235, 87, 87, 150)
BTN_RECORD = (180, 50, 50, 180)
BTN_RECORD_HOVER = (235, 90, 90, 220)
BTN_RECORDING = (255, 60, 60, 240)
BTN_DISABLED = (80, 80, 80, 120)

# ---------- 页面 ----------
PAGE_HOME = "home"
PAGE_LANDMARK_LIST = "landmark_list"
PAGE_LANDMARK_DETAIL = "landmark_detail"
PAGE_AI = "ai"

# ---------- AI 状态 ----------
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_RECOGNIZING = "recognizing"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"
STATE_ERROR = "error"
STATE_TEXT = {
    STATE_IDLE: "空闲 - 按住下方按钮开始说话",
    STATE_RECORDING: "录音中... 松开按钮结束",
    STATE_RECOGNIZING: "语音识别中...",
    STATE_THINKING: "红军故事大模型思考中...",
    STATE_SPEAKING: "正在播报回答...",
    STATE_ERROR: "出现错误，可点击重试",
}

# ---------- LED 模式 ----------
LED_HOME = "home"
LED_LANDMARK_LIST = "landmark_list"
LED_LANDMARK_DETAIL = "landmark_detail"
LED_AI_IDLE = "ai_idle"
LED_AI_RECORDING = "ai_recording"
LED_AI_THINKING = "ai_thinking"
LED_AI_SPEAKING = "ai_speaking"
LED_OFF = "off"


# ============================================================
# 通用工具
# ============================================================
def find_chinese_font():
    """寻找系统中可用的中文字体"""
    candidates = [
        "simhei", "microsoftyahei", "msyh", "pingfang",
        "notosanscjksc", "notosanscjk", "wenquanyimicrohei",
        "wqymicrohei", "stheiti", "arialunicodems",
    ]
    available = pygame.font.get_fonts()
    for name in candidates:
        if name in available:
            return name
    paths = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def make_font(font_name, size, bold=False):
    if font_name and (font_name.startswith("/") or "\\" in font_name or
                      (len(font_name) > 2 and font_name[1] == ":")):
        try:
            f = pygame.font.Font(font_name, size)
            f.set_bold(bold)
            return f
        except Exception:
            pass
    try:
        return pygame.font.SysFont(font_name, size, bold=bold)
    except Exception:
        return pygame.font.Font(None, size)


def draw_text(surface, text, font, color, pos, anchor="topleft"):
    surf = font.render(text, True, color)
    rect = surf.get_rect(**{anchor: pos})
    surface.blit(surf, rect)
    return rect


def wrap_text(text, font, max_width):
    """按像素宽度换行（支持中英文）"""
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def clamp_byte(v):
    return max(0, min(255, int(v)))


# ============================================================
# 按钮
# ============================================================
class Button:
    def __init__(self, rect, text, action, font, color=BTN_NORMAL,
                 hover_color=BTN_HOVER, text_color=TEXT_COLOR):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.hovered = False
        self.enabled = True
        self.visible = True

    def update(self, mouse_pos):
        self.hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        if not self.visible:
            return
        if not self.enabled:
            color = BTN_DISABLED
        elif self.hovered:
            color = self.hover_color
        else:
            color = self.color

        btn_surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, color, btn_surf.get_rect(), border_radius=16)
        # 边框：hover 时用金色，否则用半透明白
        border_color = GOLD if (self.hovered and self.enabled) else (255, 255, 255, 60)
        pygame.draw.rect(btn_surf, border_color, btn_surf.get_rect(), 2, border_radius=16)
        surface.blit(btn_surf, self.rect.topleft)

        # 文字带黑色描边，保证在任意背景下都清晰
        txt_color = self.text_color if self.enabled else (150, 150, 150)
        text_surf = self.font.render(self.text, True, txt_color)
        shadow_surf = self.font.render(self.text, True, (0, 0, 0))
        text_rect = text_surf.get_rect(center=self.rect.center)
        # 描边：在 8 个方向偏移 1px 绘制阴影
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                surface.blit(shadow_surf, (text_rect.x + dx, text_rect.y + dy))
        surface.blit(text_surf, text_rect)

    def click(self, pos):
        if self.enabled and self.visible and self.rect.collidepoint(pos):
            self.action()
            return True
        return False


# ============================================================
# WS2812 灯带控制器（后台线程驱动）
# ============================================================
class LEDController:
    def __init__(self, board, pin, count, board_lock=None):
        self.board = board
        self.pin = pin
        self.count = count
        self.board_lock = board_lock  # 与 PIR 等其他串口访问者共享的锁
        self._mode = LED_HOME
        self._lock = threading.Lock()
        self._running = True
        self._thread = None
        if board is not None:
            try:
                self._safe_call(lambda: board.ws2812Init(pin, count))
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
            except Exception as e:
                print(f"WS2812 初始化失败: {e}")
                self.board = None

    def _safe_call(self, fn):
        """加锁访问扩展板串口，避免与 PIR 读取线程并发冲突"""
        if self.board_lock is not None:
            with self.board_lock:
                return fn()
        return fn()

    def set_mode(self, mode):
        with self._lock:
            self._mode = mode

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._write_off()

    def _write_off(self):
        if self.board is None:
            return
        try:
            self._safe_call(lambda: self.board.ws2812Write(self.pin, 255, 0, 0, 0))
        except Exception:
            pass

    def _set_all(self, colors):
        if self.board is None:
            return
        for i, (r, g, b) in enumerate(colors):
            try:
                self._safe_call(lambda i=i, r=r, g=g, b=b:
                                self.board.ws2812Write(self.pin, i, r, g, b))
            except Exception:
                pass

    def _compute(self, mode, t):
        n = self.count
        if mode == LED_OFF:
            return [(0, 0, 0)] * n

        if mode == LED_HOME:
            # 首页：温暖的红色呼吸（革命主题）
            p = 0.5 + 0.5 * math.sin(t * 0.09)
            r = clamp_byte(80 + 150 * p)
            g = clamp_byte(18 + 28 * p)
            b = clamp_byte(15)
            return [(r, g, b)] * n

        if mode == LED_LANDMARK_LIST:
            # 地标列表：金色流光（一颗亮斑循环移动）
            pos = (t * 0.13) % n
            out = []
            for i in range(n):
                d = abs(i - pos)
                if d > n / 2.0:
                    d = n - d
                br = math.exp(-d * d * 1.3)
                out.append((
                    clamp_byte(120 + 135 * br),
                    clamp_byte(90 + 115 * br),
                    clamp_byte(10 + 45 * br),
                ))
            return out

        if mode == LED_LANDMARK_DETAIL:
            # 地标详情播音：蓝色波浪流动
            out = []
            for i in range(n):
                ph = i * 0.6 + t * 0.18
                w = 0.5 + 0.5 * math.sin(ph)
                out.append((
                    clamp_byte(15),
                    clamp_byte(55 + 95 * w),
                    clamp_byte(120 + 135 * w),
                ))
            return out

        if mode == LED_AI_IDLE:
            # AI 空闲：青色轻柔呼吸
            p = 0.5 + 0.5 * math.sin(t * 0.06)
            return [(clamp_byte(15), clamp_byte(115 * p + 45),
                     clamp_byte(150 * p + 40))] * n

        if mode == LED_AI_RECORDING:
            # 录音中：红色快速脉冲
            p = 0.5 + 0.5 * math.sin(t * 0.45)
            return [(clamp_byte(180 * p + 55), clamp_byte(25), clamp_byte(25))] * n

        if mode == LED_AI_THINKING:
            # 思考中：橙色跑马灯
            pos = int((t * 0.25) % n)
            out = []
            for i in range(n):
                if i == pos:
                    out.append((255, 180, 40))
                else:
                    out.append((55, 38, 0))
            return out

        if mode == LED_AI_SPEAKING:
            # 播报中：绿色流动波纹
            out = []
            for i in range(n):
                ph = i * 0.7 + t * 0.22
                w = 0.5 + 0.5 * math.sin(ph)
                out.append((
                    clamp_byte(15),
                    clamp_byte(165 * w + 55),
                    clamp_byte(75 * w + 18),
                ))
            return out

        return [(0, 0, 0)] * n

    def _loop(self):
        t = 0
        while self._running:
            with self._lock:
                mode = self._mode
            colors = self._compute(mode, t)
            self._set_all(colors)
            t += 1
            time.sleep(0.033)


# ============================================================
# 人体红外传感器监测器（后台线程慢速轮询，避免串口超时）
# ============================================================
class PIRSensor:
    def __init__(self, board, pin, board_lock=None, interval=0.3):
        self.board = board
        self.pin = pin
        self.board_lock = board_lock
        self.interval = interval          # 轮询间隔（秒）
        self._detected = False            # 是否检测到人
        self._lock = threading.Lock()
        self._running = True
        self._thread = None
        if board is not None:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self):
        while self._running:
            try:
                if self.board_lock is not None:
                    with self.board_lock:
                        val = self.board.digitalRead(self.pin)
                else:
                    val = self.board.digitalRead(self.pin)
                with self._lock:
                    self._detected = (val == 1)
            except Exception:
                # 串口偶发超时属正常，忽略本次，下次重试
                pass
            time.sleep(self.interval)

    def is_detected(self):
        """主线程读取最近一次检测结果（非阻塞，不访问串口）"""
        with self._lock:
            return self._detected

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


# ============================================================
# 主程序
# ============================================================
def main():
    pygame.init()
    try:
        pygame.mixer.init()
        audio_ok = True
    except pygame.error:
        audio_ok = False

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("浙西南革命精神 - 红色文化交互展示")
    clock = pygame.time.Clock()

    font_name = find_chinese_font()
    font_btn = make_font(font_name, 40, bold=True)
    font_btn_small = make_font(font_name, 32, bold=True)
    font_title = make_font(font_name, 60, bold=True)
    font_status = make_font(font_name, 42)
    font_role = make_font(font_name, 36, bold=True)
    font_msg = make_font(font_name, 34)
    font_exit = make_font(font_name, 30, bold=True)
    font_small = make_font(font_name, 26)
    font_record = make_font(font_name, 26, bold=True)
    font_lm_title = make_font(font_name, 46, bold=True)

    # ---------- 背景图缓存 ----------
    bg_cache = {}

    def load_bg(path):
        if path in bg_cache:
            return bg_cache[path]
        surf = None
        if path and os.path.exists(path):
            try:
                img = pygame.image.load(path)
                surf = pygame.transform.smoothscale(img, (WIDTH, HEIGHT)).convert()
            except Exception as e:
                print(f"背景加载失败 {path}: {e}")
        bg_cache[path] = surf
        return surf

    def draw_background(path):
        bg = load_bg(path)
        if bg:
            screen.blit(bg, (0, 0))
        else:
            # 降级：深红渐变
            screen.fill((28, 16, 20))
            for y in range(0, HEIGHT, 4):
                c = clamp_byte(30 + 30 * (y / HEIGHT))
                pygame.draw.rect(screen, (c, 12, 14), (0, y, WIDTH, 4))

    # ---------- 初始化扩展板 / LED ----------
    board = None
    board_ok = False
    if ESP32_AVAILABLE:
        try:
            board = ESP32()
            if board.start():
                board_ok = True
                print("扩展板连接成功")
            else:
                print("扩展板连接异常，请检查硬件")
        except Exception as e:
            print(f"扩展板异常: {e}")
    else:
        print("未检测到 ESP32 模块，硬件功能将不可用（仅界面可用）")

    # 扩展板串口共享锁：LED 写入与 PIR 读取通过同一把锁串行化，
    # 避免并发访问导致"读取引脚超时"
    board_lock = threading.Lock() if board_ok else None

    led = LEDController(board if board_ok else None, LED_PIN, LED_COUNT,
                        board_lock=board_lock)
    led.set_mode(LED_HOME)

    # PIR 人体红外：后台线程慢速轮询（每 0.3s 一次），主线程只读缓存值
    pir = PIRSensor(board if board_ok else None, PIR_PIN,
                    board_lock=board_lock, interval=0.3)

    # ---------- 初始化语音 AI ----------
    voice_api = None
    recorder = None
    ai_player = None
    if VOICE_AVAILABLE:
        try:
            voice_api = VoiceAPI(VOICE_API_URL)
            if voice_api.get_token(USERNAME, PASSWORD):
                print("语音 API 认证成功")
                recorder = AudioRecorder(sample_rate=16000, channels=1)
                # AI 回答播报用 SDK 的 AudioPlayer（与 AudioRecorder 共存，避免
                # 录音后 pygame.mixer.music 无法发声的问题）
                try:
                    ai_player = AudioPlayer()
                except Exception as e:
                    print(f"AudioPlayer 初始化异常: {e}")
                    ai_player = None
            else:
                print("语音 API 认证失败，请检查用户名和密码")
                voice_api = None
        except Exception as e:
            print(f"语音 API 初始化异常: {e}")
            voice_api = None
    else:
        print("未检测到 voice_api / audio_recorder 模块，AI 语音功能不可用")

    if not os.path.isdir(AUDIO_DIR):
        os.makedirs(AUDIO_DIR, exist_ok=True)

    # ---------- 页面状态 ----------
    page_stack = []
    current_page = PAGE_HOME
    welcome_played = False        # 本次停留在首页是否已播过欢迎词
    current_landmark_idx = None   # 地标详情页当前地标索引
    last_nav_tick = -1000         # 上次导航时间（pygame 毫秒刻度），用于防抖
    NAV_DEBOUNCE_MS = 350         # 导航防抖间隔，避免连点触发多次跳转

    # ---------- 音频播放（pygame.mixer.music，单通道非阻塞） ----------
    def play_audio(path):
        if not audio_ok:
            return
        if not path or not os.path.exists(path):
            print(f"音频文件不存在: {path}")
            return
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"播放失败 {path}: {e}")

    def stop_audio():
        if audio_ok:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            # 同时停止所有 Sound 通道（AudioPlayer 可能使用 pygame.mixer.Sound）
            try:
                pygame.mixer.stop()
            except Exception:
                pass

    # ---------- 导航 ----------
    def enter_home():
        nonlocal current_page, welcome_played
        stop_audio()
        current_page = PAGE_HOME
        welcome_played = False
        led.set_mode(LED_HOME)

    def enter_landmark_list():
        nonlocal current_page
        stop_audio()
        current_page = PAGE_LANDMARK_LIST
        led.set_mode(LED_LANDMARK_LIST)

    def open_landmark(idx):
        nonlocal current_page, current_landmark_idx
        stop_audio()
        current_page = PAGE_LANDMARK_DETAIL
        current_landmark_idx = idx
        led.set_mode(LED_LANDMARK_DETAIL)
        play_audio(LANDMARKS[idx][2])

    def enter_ai():
        nonlocal current_page, ai_state, ai_error_msg, ai_session, recording
        stop_audio()
        current_page = PAGE_AI
        ai_session += 1
        ai_state = STATE_IDLE
        ai_error_msg = ""
        recording = False
        led.set_mode(LED_AI_IDLE)

    def navigate_to(page, landmark_idx=None):
        nonlocal last_nav_tick
        now = pygame.time.get_ticks()
        if now - last_nav_tick < NAV_DEBOUNCE_MS:
            return  # 防抖：距上次导航太近，忽略本次点击
        last_nav_tick = now
        page_stack.append(current_page)
        if page == PAGE_HOME:
            enter_home()
        elif page == PAGE_LANDMARK_LIST:
            enter_landmark_list()
        elif page == PAGE_LANDMARK_DETAIL:
            open_landmark(landmark_idx)
        elif page == PAGE_AI:
            enter_ai()

    def go_back():
        nonlocal last_nav_tick
        if not page_stack:
            return
        now = pygame.time.get_ticks()
        if now - last_nav_tick < NAV_DEBOUNCE_MS:
            return  # 防抖：距上次导航太近，忽略本次点击
        last_nav_tick = now
        prev = page_stack.pop()
        stop_audio()
        if prev == PAGE_HOME:
            enter_home()
        elif prev == PAGE_LANDMARK_LIST:
            enter_landmark_list()
        elif prev == PAGE_LANDMARK_DETAIL:
            # 恢复到对应地标详情
            open_landmark(current_landmark_idx)
        elif prev == PAGE_AI:
            enter_ai()

    def quit_app():
        nonlocal running
        running = False

    # ---------- 按钮定义 ----------
    # 首页两个按钮（屏幕中间）
    home_btn_w, home_btn_h = 340, 120
    home_gap = 80
    home_total = home_btn_w * 2 + home_gap
    home_start_x = (WIDTH - home_total) // 2
    home_btn_y = HEIGHT // 2 - home_btn_h // 2
    btn_landmark = Button((home_start_x, home_btn_y, home_btn_w, home_btn_h),
                          "浙南红地标", lambda: navigate_to(PAGE_LANDMARK_LIST),
                          font_btn, color=BTN_GOLD_NORMAL, hover_color=BTN_GOLD_HOVER,
                          text_color=WHITE)
    btn_ai = Button((home_start_x + home_btn_w + home_gap, home_btn_y,
                     home_btn_w, home_btn_h),
                    "浙红智助手", lambda: navigate_to(PAGE_AI),
                    font_btn, color=BTN_NORMAL, hover_color=BTN_HOVER, text_color=WHITE)
    home_buttons = [btn_landmark, btn_ai]

    # 地标列表三个按钮（屏幕中间）
    lm_btn_w, lm_btn_h = 300, 110
    lm_gap = 50
    lm_total = lm_btn_w * 3 + lm_gap * 2
    lm_start_x = (WIDTH - lm_total) // 2
    lm_btn_y = HEIGHT // 2 - lm_btn_h // 2
    landmark_buttons = []
    for i, (name, _img, _aud) in enumerate(LANDMARKS):
        b = Button((lm_start_x + i * (lm_btn_w + lm_gap), lm_btn_y, lm_btn_w, lm_btn_h),
                   name, lambda idx=i: navigate_to(PAGE_LANDMARK_DETAIL, idx),
                   font_btn, color=BTN_GOLD_NORMAL, hover_color=BTN_GOLD_HOVER, text_color=WHITE)
        landmark_buttons.append(b)

    # 返回 / 退出按钮
    return_btn = Button((40, 40, 170, 70), "返回", go_back, font_btn_small,
                        color=BTN_RETURN_NORMAL, hover_color=BTN_RETURN_HOVER,
                        text_color=WHITE)
    exit_btn = Button((WIDTH - 210, 40, 170, 70), "退出程序", quit_app, font_exit,
                      color=BTN_EXIT_NORMAL, hover_color=BTN_EXIT_HOVER,
                      text_color=WHITE)

    # ---------- AI 语音对话状态 ----------
    ai_state = STATE_IDLE
    ai_error_msg = ""
    ai_state_lock = threading.Lock()
    ai_history = []           # [("user"/"assistant", text), ...]
    ai_session = 0
    recording = False
    record_start_tick = 0
    processing_thread = None

    def set_ai_state(new_state, err="", session=None):
        nonlocal ai_state, ai_error_msg
        if session is not None and session != ai_session:
            return
        with ai_state_lock:
            ai_state = new_state
            ai_error_msg = err

    def get_ai_state():
        with ai_state_lock:
            return ai_state

    def add_history(role, text, session=None):
        if session is not None and session != ai_session:
            return
        with ai_state_lock:
            ai_history.append((role, text))

    def process_conversation(my_session):
        audio_path = os.path.join(AUDIO_DIR, AI_RECORD_FILE)

        # 1. 语音识别
        set_ai_state(STATE_RECOGNIZING, session=my_session)
        try:
            text = voice_api.voice_recognition(audio_path)
        except Exception as e:
            set_ai_state(STATE_ERROR, f"语音识别异常: {e}", session=my_session)
            return
        if my_session != ai_session:
            return
        if not text:
            set_ai_state(STATE_ERROR, "未识别到内容，请重试", session=my_session)
            return
        add_history("user", text, session=my_session)

        # 2. 大模型对话（限定红军故事主题）
        set_ai_state(STATE_THINKING, session=my_session)
        prompt = ("你是「浙红智助手」——一个专注于浙西南革命精神和红军故事的智能问答助手。"
                  "请围绕革命历史、红军故事、红色地标等内容简短回答（不超过150字）：") + text
        try:
            answer = voice_api.llm_chat(prompt)
        except Exception as e:
            set_ai_state(STATE_ERROR, f"大模型调用异常: {e}", session=my_session)
            return
        if my_session != ai_session:
            return
        if not answer:
            set_ai_state(STATE_ERROR, "大模型返回为空", session=my_session)
            return
        add_history("assistant", answer, session=my_session)

        # 3. 语音合成（必须检查返回值，失败则文件未生成）
        answer_path = os.path.join(AUDIO_DIR, AI_ANSWER_FILE)
        try:
            audio_data = voice_api.tts_synthesize(answer, answer_path)
        except Exception as e:
            set_ai_state(STATE_ERROR, f"语音合成异常: {e}", session=my_session)
            return
        if my_session != ai_session:
            return
        if not audio_data:
            set_ai_state(STATE_ERROR, "语音合成失败，未生成音频", session=my_session)
            return
        # 确认文件确实存在
        if not os.path.exists(answer_path):
            set_ai_state(STATE_ERROR, "合成音频文件未生成", session=my_session)
            return

        # 4. 播报回答 —— 使用 SDK 的 AudioPlayer（阻塞式播放，与 AudioRecorder 共存）
        set_ai_state(STATE_SPEAKING, session=my_session)
        if ai_player is not None:
            try:
                ai_player.play_file(answer_path)
            except Exception as e:
                set_ai_state(STATE_ERROR, f"播放异常: {e}", session=my_session)
                return
        else:
            # AudioPlayer 不可用时回退到 pygame.mixer.music
            try:
                if audio_ok:
                    pygame.mixer.music.load(answer_path)
                    pygame.mixer.music.play()
                    # 等待播放结束（阻塞本线程，避免提前回到 IDLE）
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.05)
            except Exception as e:
                set_ai_state(STATE_ERROR, f"播放异常: {e}", session=my_session)
                return

        if my_session != ai_session:
            return
        set_ai_state(STATE_IDLE, session=my_session)

    # AI 录音按钮（圆形，按住说话）
    record_btn_rect = pygame.Rect(0, 0, 150, 150)
    record_btn_rect.center = (WIDTH // 2, HEIGHT - 95)

    # ---------- 主循环 ----------
    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        cur_state = get_ai_state()

        # 返回按钮在首页不显示
        return_btn.visible = (current_page != PAGE_HOME)
        return_btn.enabled = return_btn.visible and bool(page_stack)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                # 退出按钮（所有页面）
                if exit_btn.click(pos):
                    continue
                # 返回按钮（非首页）
                if return_btn.click(pos):
                    continue

                if current_page == PAGE_HOME:
                    for b in home_buttons:
                        if b.click(pos):
                            break
                elif current_page == PAGE_LANDMARK_LIST:
                    for b in landmark_buttons:
                        if b.click(pos):
                            break
                elif current_page == PAGE_AI:
                    # 录音按钮：按下开始录音
                    if (record_btn_rect.collidepoint(pos)
                            and cur_state in (STATE_IDLE, STATE_ERROR)
                            and not recording and recorder is not None):
                        recording = True
                        record_start_tick = pygame.time.get_ticks()
                        try:
                            stop_audio()
                            recorder.start_recording(device=None)
                            ai_session += 1  # 新会话
                            set_ai_state(STATE_RECORDING)
                        except Exception as e:
                            set_ai_state(STATE_ERROR, f"录音启动失败: {e}")
                            recording = False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if current_page == PAGE_AI and recording:
                    recording = False
                    duration = (pygame.time.get_ticks() - record_start_tick) / 1000.0
                    my_session = ai_session
                    try:
                        audio_data = recorder.stop_recording()
                        if audio_data is None or duration < 0.3:
                            set_ai_state(STATE_IDLE)
                        else:
                            file_path = recorder.save_audio(audio_data,
                                                            filename=AI_RECORD_FILE)
                            if file_path:
                                processing_thread = threading.Thread(
                                    target=process_conversation,
                                    args=(my_session,), daemon=True)
                                processing_thread.start()
                            else:
                                set_ai_state(STATE_IDLE)
                    except Exception as e:
                        set_ai_state(STATE_ERROR, f"录音结束异常: {e}")

        # ----- P0 人体红外：首页欢迎词 -----
        # 读取 PIR 监测器的缓存值（后台线程已慢速轮询，主线程不直接访问串口）
        if (current_page == PAGE_HOME and board_ok and not welcome_played):
            if pir.is_detected():
                play_audio(WELCOME_AUDIO)
                welcome_played = True

        # ----- AI 页面：LED 随状态变化 -----
        # 回答播报已在工作线程中由 AudioPlayer 阻塞播放，播放结束自动置 IDLE，
        # 主线程只需根据状态切换 LED 即可。
        if current_page == PAGE_AI:
            s = get_ai_state()
            if s == STATE_RECORDING:
                led.set_mode(LED_AI_RECORDING)
            elif s in (STATE_RECOGNIZING, STATE_THINKING):
                led.set_mode(LED_AI_THINKING)
            elif s == STATE_SPEAKING:
                led.set_mode(LED_AI_SPEAKING)
            else:
                led.set_mode(LED_AI_IDLE)

        # ====================================================
        # 绘制
        # ====================================================
        if current_page == PAGE_HOME:
            draw_background(IMG_HOME)
            for b in home_buttons:
                b.update(mouse_pos)
                b.draw(screen)
            draw_text(screen, "感应到人后将自动播放欢迎词", font_small, (230, 230, 230),
                      (WIDTH // 2, home_btn_y + home_btn_h + 50), anchor="midtop")

        elif current_page == PAGE_LANDMARK_LIST:
            draw_background(IMG_LANDMARK_LIST)
            for b in landmark_buttons:
                b.update(mouse_pos)
                b.draw(screen)

        elif current_page == PAGE_LANDMARK_DETAIL:
            if current_landmark_idx is not None:
                name, img_path, _aud = LANDMARKS[current_landmark_idx]
                draw_background(img_path)
                # 顶部半透明标题条
                title_bar = pygame.Surface((WIDTH, 90), pygame.SRCALPHA)
                title_bar.fill((0, 0, 0, 130))
                screen.blit(title_bar, (0, 0))
                draw_text(screen, name, font_lm_title, GOLD,
                          (WIDTH // 2, 45), anchor="center")
                draw_text(screen, "正在播放地标介绍...", font_small, (230, 230, 230),
                          (WIDTH // 2, HEIGHT - 40), anchor="center")

        elif current_page == PAGE_AI:
            draw_background(IMG_AI)
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            screen.blit(overlay, (0, 0))

            draw_text(screen, "红军故事智能问答", font_title, TEXT_COLOR,
                      (WIDTH // 2, 130), anchor="midtop")

            # 状态栏
            status_color = ACCENT
            s = get_ai_state()
            if s == STATE_RECORDING:
                status_color = (255, 120, 120)
            elif s == STATE_ERROR:
                status_color = (255, 150, 150)
            elif s == STATE_SPEAKING:
                status_color = (130, 255, 170)
            elif s in (STATE_RECOGNIZING, STATE_THINKING):
                status_color = (255, 220, 130)

            status_text = STATE_TEXT.get(s, "")
            if s == STATE_ERROR and ai_error_msg:
                status_text = ai_error_msg
            draw_text(screen, status_text, font_status, status_color,
                      (WIDTH // 2, 270), anchor="center")

            # 对话记录面板
            panel_x, panel_y = 160, 340
            panel_w = WIDTH - 320
            panel_h = HEIGHT - 340 - 230
            panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel.fill(PANEL_COLOR)
            screen.blit(panel, (panel_x, panel_y))
            pygame.draw.rect(screen, ACCENT,
                             (panel_x, panel_y, panel_w, panel_h), 2, border_radius=12)
            draw_text(screen, "对话记录", font_role, ACCENT,
                      (panel_x + 24, panel_y + 16), anchor="topleft")

            with ai_state_lock:
                history_snapshot = list(ai_history)
            if history_snapshot:
                content_w = panel_w - 80
                rendered = []
                for role, text in reversed(history_snapshot):
                    lines = wrap_text(text, font_msg, content_w - 60)
                    for ln in reversed(lines):
                        rendered.append((role, ln))
                    rendered.append(("gap", ""))
                y = panel_y + panel_h - 26
                top_limit = panel_y + 70
                for role, ln in rendered:
                    if role == "gap":
                        y -= 18
                        continue
                    color = ACCENT if role == "user" else (150, 255, 180)
                    label = "我：" if role == "user" else "助手："
                    ts = font_msg.render(label + ln, True, color)
                    y -= ts.get_height() + 8
                    if y < top_limit:
                        break
                    screen.blit(ts, (panel_x + 40, y))
            else:
                if recorder is None:
                    hint_msg = "语音 AI 模块不可用，请检查账号或 SDK"
                    hint_color = (255, 170, 170)
                else:
                    hint_msg = "按住下方圆形按钮说话，松开后自动识别并与大模型对话"
                    hint_color = (210, 210, 210)
                draw_text(screen, hint_msg, font_msg, hint_color,
                          (WIDTH // 2, panel_y + panel_h // 2), anchor="center")

            # 录音按钮（圆形）
            btn_center = record_btn_rect.center
            btn_radius = record_btn_rect.width // 2
            hovering = record_btn_rect.collidepoint(mouse_pos)
            can_record = recorder is not None and s in (STATE_IDLE, STATE_ERROR) and not recording

            if s == STATE_RECORDING:
                btn_color = BTN_RECORDING
                btn_label = ["录音中", "松开结束"]
                pulse = abs((pygame.time.get_ticks() // 8) % 80 - 40)
                glow = pygame.Surface((record_btn_rect.width + 80,
                                       record_btn_rect.height + 80), pygame.SRCALPHA)
                pygame.draw.circle(glow, (255, 60, 60, 60),
                                   (glow.get_width() // 2, glow.get_height() // 2),
                                   btn_radius + 10 + pulse // 4)
                screen.blit(glow, glow.get_rect(center=btn_center))
            elif s == STATE_ERROR:
                btn_color = BTN_RECORD_HOVER if hovering else BTN_RECORD
                btn_label = ["点击重试"] if can_record else ["处理中"]
            elif s == STATE_IDLE:
                if recorder is None:
                    btn_color = BTN_DISABLED
                    btn_label = ["不可用"]
                else:
                    btn_color = BTN_RECORD_HOVER if hovering else BTN_RECORD
                    btn_label = ["按住说话"]
            else:
                btn_color = BTN_DISABLED
                btn_label = ["处理中"]

            btn_surf = pygame.Surface(record_btn_rect.size, pygame.SRCALPHA)
            pygame.draw.circle(btn_surf, btn_color, (btn_radius, btn_radius), btn_radius)
            pygame.draw.circle(btn_surf, (255, 255, 255, 200),
                               (btn_radius, btn_radius), btn_radius, 3)
            screen.blit(btn_surf, record_btn_rect.topleft)

            total_h = sum(font_record.size(l)[1] for l in btn_label) + 10 * (len(btn_label) - 1)
            ly = btn_center[1] - total_h // 2
            for l in btn_label:
                ts = font_record.render(l, True, WHITE)
                shadow = font_record.render(l, True, (0, 0, 0))
                ts_rect = ts.get_rect(center=(btn_center[0], ly + ts.get_height() // 2))
                # 黑色描边
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        screen.blit(shadow, (ts_rect.x + dx, ts_rect.y + dy))
                screen.blit(ts, ts_rect)
                ly += ts.get_height() + 10

            if s in (STATE_IDLE, STATE_RECORDING):
                hint = "按住按钮说话，松开自动识别并对话"
            else:
                hint = "请等待当前对话完成..."
            draw_text(screen, hint, font_small, (200, 200, 200),
                      (WIDTH // 2, record_btn_rect.top - 26), anchor="center")

        # 通用：返回 / 退出按钮
        return_btn.update(mouse_pos)
        return_btn.draw(screen)
        exit_btn.update(mouse_pos)
        exit_btn.draw(screen)

        pygame.display.flip()
        clock.tick(60)

    # ---------- 退出清理 ----------
    stop_audio()
    led.set_mode(LED_OFF)
    led.stop()
    pir.stop()
    if processing_thread and processing_thread.is_alive():
        processing_thread.join(timeout=2)
    if ai_player is not None:
        try:
            ai_player.cleanup()
        except Exception:
            pass
    pygame.quit()


if __name__ == "__main__":
    main()
