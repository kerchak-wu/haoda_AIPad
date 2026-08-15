# -*- coding: utf-8 -*-
"""
智慧阅读角 - 好搭AI派案例
=====================================
功能说明：
1. 欢迎屏幕：显示"欢迎来到智慧阅读角，享受阅读时光"，含退出按钮
2. 人体红外传感器(io1)检测到人 → 切换到功能选择界面
3. 功能选择：馆藏图书 / 图书视频 / 智能导读，30秒无人自动返回欢迎屏
4. 馆藏图书：点击书名，语音+文字介绍图书
5. 图书视频：西游记/三国演义/红楼梦，点击播放对应视频
6. 智能导读：USB摄像头OCR识别文字 + 按住说话语音对话
7. RGB灯带(io2, 11灯珠)：全程配合不同灯效

硬件接线：
- IO1: 人体红外传感器(PIR)
- IO2: WS2812 RGB灯带(11灯珠，需接上拉扩展模块)
- USB摄像头: 用于智能导读OCR识别

依赖文件：
- videos/1.mp4  videos/2.mp4  videos/3.mp4 (图书视频)
"""

import os
# Rockchip 平台兼容性补丁（参照《视觉系统摄像头调用参考方案》第7章）
# 必须在 ALL import 之前设置（包括 text_recognition、pygame、cv2），
# 强制 libGL 使用软件渲染，避免 Mali GPU 硬件 DRI 驱动崩溃报错：
#   libGL error: failed to create dri screen
#   libGL error: failed to load driver: rockchip
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

# ====== 注意：text_recognition 导入顺序放在其他第三方库之前，否则OCR会报错 ======
# try/except 容错：导入失败时记录错误，程序仍可启动（智能导读功能不可用）
try:
    from text_recognition import TextRecognizer as _TextRecognizer
    _TEXT_RECOGNITION_AVAILABLE = True
    _TEXT_RECOGNITION_ERROR = None
except Exception as _e:
    _TEXT_RECOGNITION_AVAILABLE = False
    _TEXT_RECOGNITION_ERROR = _e

import sys
import pygame
import cv2
import time
import math
import threading
import logging
import queue
import wave
import struct
import numpy as np
from datetime import datetime

try:
    from ESP32 import *
    _ESP32_AVAILABLE = True
    _ESP32_ERROR = None
except Exception as _e:
    _ESP32_AVAILABLE = False
    _ESP32_ERROR = _e

try:
    from voice_api import VoiceAPI
    _VOICE_API_AVAILABLE = True
except Exception as _e:
    _VOICE_API_AVAILABLE = False
    _VOICE_API_ERROR = _e

try:
    from audio_player import AudioPlayer
    _AUDIO_PLAYER_AVAILABLE = True
except Exception as _e:
    _AUDIO_PLAYER_AVAILABLE = False
    _AUDIO_PLAYER_ERROR = _e

try:
    from audio_recorder import AudioRecorder
    _AUDIO_RECORDER_AVAILABLE = True
except Exception as _e:
    _AUDIO_RECORDER_AVAILABLE = False
    _AUDIO_RECORDER_ERROR = _e

try:
    from camera_vision_system_v3 import create_vision_system_v3
    _VISION_SYSTEM_AVAILABLE = True
    _VISION_SYSTEM_ERROR = None
except Exception as _e:
    _VISION_SYSTEM_AVAILABLE = False
    _VISION_SYSTEM_ERROR = _e

# ==================== 配置参数 ====================
WINDOW_W, WINDOW_H = 1920, 1080
# GPIO_IO_01/02 来自 ESP32 模块；ESP32 导入失败时回退到数字引脚号，避免 NameError
PIR_PIN = GPIO_IO_01 if _ESP32_AVAILABLE else 1
RGB_PIN = GPIO_IO_02 if _ESP32_AVAILABLE else 2
NUM_LEDS = 11
MENU_TIMEOUT = 30  # 功能选择界面无人操作超时(秒)

# 语音AI认证信息（请替换为自己的好好搭搭账号密码）
VOICE_USERNAME = '用户名'
VOICE_PASSWORD = '密码'

# ==================== 颜色主题 ====================
C_BG_TOP = (35, 28, 50)
C_BG_BOT = (55, 40, 35)
C_PANEL = (250, 245, 235)
C_PRIMARY = (190, 130, 55)
C_PRIMARY_DARK = (140, 90, 35)
C_ACCENT_BLUE = (70, 130, 180)
C_ACCENT_GREEN = (80, 160, 90)
C_ACCENT_PURPLE = (130, 80, 160)
C_ACCENT_CYAN = (70, 160, 170)
C_TEXT_DARK = (55, 45, 38)
C_TEXT_LIGHT = (230, 225, 215)
C_TEXT_GRAY = (140, 130, 120)
C_BTN_RETURN = (180, 70, 60)

# ==================== 图书数据库 ====================
BOOKS = [
    {"title": "西游记", "author": "吴承恩",
     "intro": "《西游记》是中国古典四大名著之一，由明代小说家吴承恩编撰而成。全书共一百回，讲述了唐僧师徒四人历经九九八十一难，前往西天取经的传奇故事。书中塑造了孙悟空、猪八戒、沙僧等鲜活形象，想象瑰丽，语言幽默，是中国神魔小说的巅峰之作。"},
    {"title": "三国演义", "author": "罗贯中",
     "intro": "《三国演义》由元末明初小说家罗贯中所著，是中国第一部长篇章回体历史演义小说。全书共一百二十回，以东汉末年至西晋初年的历史为背景，生动描绘了魏、蜀、吴三国鼎立的政治军事斗争。书中塑造了诸葛亮、关羽、曹操等众多经典人物形象，气势恢宏，影响深远。"},
    {"title": "红楼梦", "author": "曹雪芹",
     "intro": "《红楼梦》由清代作家曹雪芹所著，是中国古典小说的最高成就。全书以贾宝玉、林黛玉、薛宝钗的爱情婚姻悲剧为主线，深刻描写了贾府由盛转衰的过程。作品涉及诗词、医药、建筑、饮食等百科全书式的内容，人物刻画细腻入微，思想内涵极为丰富。"},
    {"title": "水浒传", "author": "施耐庵",
     "intro": "《水浒传》由元末明初作家施耐庵所著，是中国古典四大名著之一。全书描写了北宋末年以宋江为首的一百零八位好汉聚义梁山泊、替天行道的故事。作品塑造了武松、林冲、鲁智深等众多英雄形象，歌颂了反抗压迫的精神，语言生动，情节跌宕起伏。"},
    {"title": "小王子", "author": "圣埃克苏佩里",
     "intro": "《小王子》是法国作家圣埃克苏佩里创作的经典童话小说。故事讲述了一位来自小行星B612的小王子，在游历各个星球后最终来到地球的奇妙旅程。作品以孩子的视角探讨了爱、责任、友谊与生命的意义，语言简洁而富有哲理，深受全世界读者喜爱。"},
    {"title": "钢铁是怎样炼成的", "author": "奥斯特洛夫斯基",
     "intro": "《钢铁是怎样炼成的》由苏联作家奥斯特洛夫斯基所著，是一部激励了无数人的经典小说。作品以主人公保尔·柯察金的成长经历为主线，展现了他在革命战争和和平建设时期的坚定信念与顽强意志。书中关于生命意义的思考至今仍发人深省。"},
    {"title": "鲁滨逊漂流记", "author": "笛福",
     "intro": "《鲁滨逊漂流记》由英国作家笛福所著，是一部经典的冒险小说。故事讲述了主人公鲁滨逊因海难流落荒岛，凭借智慧和毅力在孤岛上生存了二十八年的传奇经历。作品歌颂了人类面对困境时的勇气与创造力，是英国文学史上的重要作品。"},
    {"title": "安徒生童话", "author": "安徒生",
     "intro": "《安徒生童话》由丹麦作家安徒生创作，是世界文学宝库中的瑰宝。其中包括《卖火柴的小女孩》《丑小鸭》《海的女儿》《皇帝的新装》等经典故事。作品以优美的语言和丰富的想象，既有浪漫的童话色彩，又蕴含深刻的社会关怀，陪伴了无数孩子的成长。"},
]

VIDEO_BOOKS = [
    {"title": "西游记", "file": "videos/1.mp4"},
    {"title": "三国演义", "file": "videos/2.mp4"},
    {"title": "红楼梦", "file": "videos/3.mp4"},
]

# ==================== 工具函数 ====================
def find_chinese_font(size):
    """查找可用的中文字体"""
    candidates = [
        '/home/cxdz/jupyter/assets/simfang.ttf',
        '/home/cxdz/jupyter/assets/simhei.ttf',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    ]
    for path in candidates:
        if os.path.exists(path):
            return pygame.font.Font(path, size)
    return pygame.font.SysFont('simhei,microsoft yahei,pingfang sc,noto sans cjk sc,wenquanyi zen hei', size)


def wrap_text(text, font, max_width):
    """中文文本自动换行"""
    lines = []
    for paragraph in text.split('\n'):
        current = ''
        for char in paragraph:
            test = current + char
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = char
        lines.append(current)
    return lines


def draw_wrapped_text(surface, text, font, color, x, y, max_width, line_spacing=None):
    """绘制自动换行文本，返回结束y坐标"""
    lines = wrap_text(text, font, max_width)
    if line_spacing is None:
        line_spacing = font.get_linesize()
    for line in lines:
        surface.blit(font.render(line, True, color), (x, y))
        y += line_spacing
    return y


def wheel(pos):
    """RGB色环函数"""
    pos = pos % 256
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)


def lighten(color, amount=30):
    return tuple(min(255, c + amount) for c in color)


def draw_gradient(surface, top_color, bot_color):
    """绘制垂直渐变背景"""
    w, h = surface.get_size()
    for y in range(h):
        ratio = y / max(h - 1, 1)
        r = int(top_color[0] + (bot_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bot_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bot_color[2] - top_color[2]) * ratio)
        pygame.draw.line(surface, (r, g, b), (0, y), (w, y))


def draw_panel(surface, rect, fill_color=C_PANEL, radius=16):
    """绘制带圆角阴影的面板"""
    shadow_rect = rect.move(4, 6)
    pygame.draw.rect(surface, (20, 15, 25), shadow_rect, border_radius=radius)
    pygame.draw.rect(surface, fill_color, rect, border_radius=radius)


def draw_button(surface, rect, text, font, color, text_color=(255, 255, 255), hover=False, radius=12):
    """绘制圆角按钮"""
    btn_color = lighten(color, 25) if hover else color
    pygame.draw.rect(surface, btn_color, rect, border_radius=radius)
    pygame.draw.rect(surface, lighten(btn_color, 40), rect, 2, border_radius=radius)
    text_surf = font.render(text, True, text_color)
    text_rect = text_surf.get_rect(center=rect.center)
    surface.blit(text_surf, text_rect)


def setup_logging():
    """初始化日志：控制台+文件双输出

    遵循项目工程约定：
    - 日志目录 logs/，文件名格式 智慧阅读角_YYYYMMDD.log
    - 追加模式（'a'）而非覆盖，同一天多次运行累积保留
    - 每次启动写入分隔标记，便于区分多次运行

    另外处理好搭AI派终端的两个日志显示问题：
    (a) 终端把 stderr 流全标成「[错误]」→ 把 stderr 重定向到 logger.warning，
        避免第三方库（color_block_detector/PIL/ESP32/V3 SDK）往 stderr 写的
        正常 INFO 信息被错标成红色错误。
    (b) 第三方库/本程序 logger 与 print 混用导致日志重复 → logger.propagate=False
        阻止向上冒泡到 root logger；本程序一律用 logger，不再额外 print。
    """
    os.makedirs('logs', exist_ok=True)
    log_filename = os.path.join(
        'logs', '智慧阅读角_%s.log' % datetime.now().strftime('%Y%m%d'))
    logger = logging.getLogger('SmartReading')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False  # 关键：禁止冒泡到 root logger，避免重复输出
    fmt = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    # 文件 handler 用追加模式，DEBUG 级别全量记录
    fh = logging.FileHandler(log_filename, mode='a', encoding='utf-8')
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    # 控制台 handler：INFO 级别，走 stdout（而非默认 stderr），避免终端打「[错误]」标
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    # --- stderr → logger 重定向 ---
    # 第三方库（color_block_detector / PIL / ESP32 / voice_api / V3 SDK 内部）
    # 喜欢往 stderr 写普通提示，终端会统一前缀「[错误]」误导用户。
    # 这里把 sys.stderr 替换成写往 logger.warning 的 Writer，既保留信息又消除红字。
    class _StderrToLogger(object):
        def __init__(self, lg):
            self._lg = lg
            self._buf = ''

        def write(self, s):
            self._buf += s
            while '\n' in self._buf:
                line, self._buf = self._buf.split('\n', 1)
                line = line.rstrip('\r')
                if line:
                    # 过滤常见已知噪音：纯空行、color_block_detector 的 INFO 行
                    if line.startswith('INFO:color_block_detector') or \
                       line.startswith('I:SmartReading'):
                        self._lg.info(line)
                    elif line.startswith('[错误]'):
                        # 终端前置标签已在内容里，降级成 warning 不要重复吓用户
                        self._lg.warning(line)
                    else:
                        self._lg.warning(line)

        def flush(self):
            if self._buf:
                self.write('\n')
    try:
        sys.stderr = _StderrToLogger(logger)
    except Exception:
        pass

    logger.info('=' * 60)
    logger.info('======== %s 运行开始 ========', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info('智慧阅读角程序启动，日志文件: %s', log_filename)
    logger.info('=' * 60)
    return logger


# ==================== RGB灯效管理器 ====================
class LightManager:
    def __init__(self, board, pin, num_leds=11, board_lock=None):
        self.board = board
        self.pin = pin
        self.num = num_leds
        self.mode = 'welcome'
        self.running = True
        self.step = 0
        self._lock = threading.Lock()
        # board_lock 用于串行化对 ESP32 串口的访问，避免与 PIR 读取并发冲突
        self._board_lock = board_lock
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.thread.start()

    def set_mode(self, mode):
        with self._lock:
            self.mode = mode

    def _loop(self):
        while self.running:
            try:
                with self._lock:
                    mode = self.mode
                # board_lock 串行化串口访问，避免与 PIR 读取线程并发导致超时
                if self._board_lock is not None:
                    with self._board_lock:
                        self._render(mode)
                else:
                    self._render(mode)
                self.step += 1
            except Exception:
                # 串口偶发超时属正常，忽略本次，下次重试
                pass
            time.sleep(0.05)

    def _render(self, mode):
        if mode == 'off':
            self.board.ws2812Write(self.pin, 255, 0, 0, 0)
            time.sleep(0.1)
            return

        if mode == 'welcome':
            # 暖色波动呼吸灯
            breath = (math.sin(self.step * 0.1) + 1) / 2
            breath2 = (math.sin(self.step * 0.04) + 1) / 2
            r = int(60 + 140 * breath + 30 * breath2)
            g = int(25 + 80 * breath + 20 * breath2)
            b = int(10 + 35 * breath + 10 * breath2)
            for i in range(self.num):
                wave = math.sin((self.step * 0.05) + i * 0.5) * 20
                self.board.ws2812Write(self.pin, i,
                                       max(0, min(255, r + int(wave))),
                                       max(0, min(255, g + int(wave * 0.5))),
                                       max(0, min(255, b + int(wave * 0.2))))

        elif mode == 'menu':
            # 动态彩虹流光 + 闪烁点缀
            for i in range(self.num):
                color = wheel((self.step * 4 + i * 25) % 256)
                sparkle = 1 + 0.3 * math.sin(self.step * 0.2 + i)
                r, g, b = [min(255, int(c * sparkle)) for c in color]
                self.board.ws2812Write(self.pin, i, r, g, b)

        elif mode == 'library':
            # 暖色阅读灯：渐层波动 + 轻微脉动
            pulse = (math.sin(self.step * 0.06) + 1) / 2
            for i in range(self.num):
                off = math.sin(self.step * 0.03 + i * 0.8) * 15
                r = int(150 + 40 * pulse + off)
                g = int(90 + 30 * pulse + off * 0.6)
                b = int(25 + 15 * pulse + off * 0.3)
                self.board.ws2812Write(self.pin, i,
                                       max(0, min(255, r)),
                                       max(0, min(255, g)),
                                       max(0, min(255, b)))

        elif mode == 'videos':
            # 紫色影院：七彩渐变流动 + 脉冲
            for i in range(self.num):
                color = wheel((self.step * 3 + i * 22 + 160) % 256)
                pulse = 0.85 + 0.15 * math.sin(self.step * 0.15 + i * 0.7)
                r, g, b = [int(c * pulse) for c in color]
                g = max(0, g - 20)
                self.board.ws2812Write(self.pin, i, r, g, b)

        elif mode == 'guide':
            # 青色科技追逐灯（双向流动 + 拖尾）
            pos1 = (self.step // 2) % self.num
            pos2 = (self.step // 4 + 5) % self.num
            for i in range(self.num):
                d1 = min(abs(i - pos1), self.num - abs(i - pos1))
                d2 = min(abs(i - pos2), self.num - abs(i - pos2))
                b1 = max(0, 255 - d1 * 40)
                g1 = max(0, 200 - d1 * 35)
                r1 = max(0, 30 - d1 * 5)
                b2 = max(0, 120 - d2 * 25)
                g2 = max(0, 80 - d2 * 18)
                self.board.ws2812Write(self.pin, i,
                                       max(r1, 0),
                                       max(0, min(255, g1 + g2)),
                                       max(0, min(255, b1 + b2)))

        elif mode == 'speaking':
            # 绿色快速脉动 + 彩色呼吸（正在播报）
            pulse = (math.sin(self.step * 0.3) + 1) / 2
            sub = (math.sin(self.step * 0.12) + 1) / 2
            r = int(0 + 50 * pulse + 20 * sub)
            g = int(100 + 140 * pulse + 30 * sub)
            b = int(30 + 80 * pulse + 30 * sub)
            for i in range(self.num):
                wave = math.sin(self.step * 0.25 + i * 0.6) * 30
                self.board.ws2812Write(self.pin, i,
                                       max(0, min(255, r + int(wave * 0.4))),
                                       max(0, min(255, g + int(wave))),
                                       max(0, min(255, b + int(wave * 0.6))))

        elif mode == 'recognizing':
            # 黄色呼吸闪烁 + 扫描线（识别中）
            on = (math.sin(self.step * 0.4) + 1) / 2
            for i in range(self.num):
                scan = ((self.step // 2 + i) % self.num) < 2
                boost = 50 if scan else 0
                r = int(50 + 180 * on + boost)
                g = int(50 + 180 * on + boost)
                b = int(10 + 30 * on)
                self.board.ws2812Write(self.pin, i,
                                       max(0, min(255, r)),
                                       max(0, min(255, g)),
                                       max(0, min(255, b)))

        elif mode == 'recording':
            # 红色快速心跳 + 白色闪点（录音中）
            pulse = (math.sin(self.step * 0.45) + 1) / 2
            sharp = max(0, math.sin(self.step * 0.8))
            for i in range(self.num):
                twinkle = max(0, math.sin(self.step * 0.3 + i * 1.2))
                r = int(80 + 150 * pulse + 60 * sharp + 20 * twinkle)
                g = int(10 + 30 * pulse + 40 * sharp)
                b = int(10 + 25 * pulse + 40 * sharp)
                self.board.ws2812Write(self.pin, i,
                                       max(0, min(255, r)),
                                       max(0, min(255, g)),
                                       max(0, min(255, b)))

    def stop(self):
        self.running = False
        try:
            # 仅在 board 对象有 ws2812Write 能力且 device 属性存在时才真正写入
            # （扩展板 start() 失败时 board 对象可能缺少 device 属性）
            if (self.board is not None
                    and hasattr(self.board, 'ws2812Write')
                    and hasattr(self.board, 'device')):
                if self._board_lock is not None:
                    with self._board_lock:
                        self.board.ws2812Write(self.pin, 255, 0, 0, 0)
                else:
                    self.board.ws2812Write(self.pin, 255, 0, 0, 0)
        except Exception:
            pass


# ==================== 主应用 ====================
class SmartReadingApp:
    # 状态常量
    S_INIT = 'init'
    S_WELCOME = 'welcome'
    S_MENU = 'menu'
    S_LIBRARY = 'library'
    S_VIDEOS = 'videos'
    S_VIDEO_PLAY = 'video_play'
    S_GUIDE = 'guide'

    def __init__(self):
        self.state = self.S_INIT
        self.running = True
        self.clock = pygame.time.Clock()
        self.logger = None

        # 硬件
        self.board = None
        self._board_connected = False  # 扩展板连接状态标记：True 表示 start() 成功且 ws2812Init 已调用
        self.lights = None

        # 语音/AI
        self.voice_api = None
        self.player = None
        self.recorder = None
        self.vision_system = None
        self.ocr = None
        self.camera_ok = False
        self.mixer_ok = False

        # 状态数据
        self.selected_book = None
        self.is_speaking = False
        self.menu_enter_time = 0
        self.welcome_played = False
        self.last_speaking_book = None
        self.auth_ok = True

        # 智能导读状态
        self.guide_ocr_text = ''
        self.guide_result = '请点击"识别文字"按钮识别书名，或按住"按住说话"按钮进行语音对话。'
        self.guide_recording = False
        self.guide_processing = False
        self.guide_record_start_time = 0
        self.conversation_history = []

        # 视频播放
        self.video_cap = None
        self.video_thread = None
        self._library_blocked_hint = ''  # 播报中点击其他书时的临时提示
        self.video_stop_event = threading.Event()
        self.video_finished = threading.Event()
        self.video_frame_queue = queue.Queue(maxsize=3)
        self._cached_video_surf = None

        # 摄像头后台采集
        self._camera_lock = threading.Lock()
        self._latest_frame = None
        self._camera_thread = None
        self._camera_thread_running = False
        self._camera_initializing = False
        self._camera_init_thread = None  # 摄像头初始化后台线程引用，用于 cleanup 时等待其结束
        # OCR识别期间暂停摄像头采集的标志（避免vision_system资源竞争导致卡死）
        self._camera_paused = False

        # 启动初始化
        self._init_done = False
        self._init_error = ''
        self._init_stage = '正在加载...'

        # 字体
        self.font_title = None
        self.font_large = None
        self.font_med = None
        self.font_btn = None
        self.font_small = None
        self.font_author = None

        # 鼠标状态
        self.mouse_pos = (0, 0)

        # 线程锁
        self._lock = threading.Lock()
        # board_lock 串行化对 ESP32 串口的访问（LED 写入 + PIR 读取共用），
        # 避免并发访问导致"读取引脚超时"或返回错误值
        self._board_lock = threading.Lock()

        # PIR 后台轮询线程（主线程只读缓存值，避免串口 I/O 阻塞主循环）
        self._pir_detected = False
        self._pir_lock = threading.Lock()
        self._pir_thread = None
        self._pir_thread_running = False

        # 背景缓存
        self._bg_surface = None
        # 智能导读预览帧缓存（OCR期间显示静态帧）
        self._guide_preview_surf = None

        # 界面元素rect缓存
        self._exit_rect = None
        self._menu_cards = []
        self._menu_return_rect = None
        self._lib_return_rect = None
        self._book_buttons = []
        self._vid_return_rect = None
        self._video_cards = []
        self._vid_stop_rect = None
        self._guide_return_rect = None
        self._ocr_btn = None
        self._voice_btn = None
        self._auth_rect = None

    # ====== 初始化 ======
    def init_pygame(self):
        # 先初始化日志，后续所有步骤均可记录
        self.logger = setup_logging()
        # Rockchip 兼容：Pygame 分段初始化，不调用 pygame.init()
        # 原因：pygame.init() 会一次性 init 所有子模块（joystick/CDROM/mixer 等），
        # 在 Rockchip 平台上 joystick 等子模块驱动缺失会导致段错误。
        # mixer 用 pre_init 设置参数后再 init（pre_init 必须在 mixer.init 之前）。
        pygame.display.init()
        pygame.font.init()
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            self.mixer_ok = True
        except Exception as e:
            self.logger.warning('pygame.mixer初始化失败(视频将无声音): %s', e)
        self.window = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption('智慧阅读角')
        self.font_title = find_chinese_font(90)
        self.font_large = find_chinese_font(64)
        self.font_med = find_chinese_font(42)
        self.font_btn = find_chinese_font(36)
        self.font_small = find_chinese_font(28)
        self.font_author = find_chinese_font(34)
        self.logger.info('Pygame窗口初始化完成 (1920x1080), mixer=%s', self.mixer_ok)
        # 预渲染背景渐变表面（避免每帧重绘1080条线导致主循环卡顿、点击丢失）
        self._bg_surface = pygame.Surface((WINDOW_W, WINDOW_H))
        draw_gradient(self._bg_surface, C_BG_TOP, C_BG_BOT)
        self.logger.info('背景渐变表面已缓存')

    def init_hardware(self):
        if not _ESP32_AVAILABLE:
            msg = '警告：ESP32 模块导入失败（%s），硬件功能不可用' % _ESP32_ERROR
            if self.logger:
                self.logger.warning(msg)
            return False
        try:
            self.board = ESP32()
        except Exception as e:
            msg = '警告：ESP32 实例化异常（%s），硬件功能不可用' % e
            if self.logger:
                self.logger.warning(msg)
            return False
        if not self.board.start():
            msg = '警告：扩展板连接异常，硬件功能不可用'
            if self.logger:
                self.logger.warning(msg)
            return False
        self.board.ws2812Init(RGB_PIN, NUM_LEDS)
        # board_lock 传给 LightManager，使 LED 写入与 PIR 读取串行化
        self.lights = LightManager(self.board, RGB_PIN, NUM_LEDS,
                                   board_lock=self._board_lock)
        self.lights.start()
        # 启动 PIR 后台轮询线程（主线程不再直接访问串口读 PIR）
        self._start_pir_thread()
        self._board_connected = True  # 标记扩展板连接成功，后续 cleanup 才操作硬件
        if self.logger:
            self.logger.info('扩展板连接成功，RGB灯带已启动 (11灯珠, pin=2)')
        return True

    def init_vision_system(self):
        if not _VISION_SYSTEM_AVAILABLE:
            if self.logger:
                self.logger.error('camera_vision_system_v3 导入失败: %s', _VISION_SYSTEM_ERROR)
            return
        if not _TEXT_RECOGNITION_AVAILABLE:
            if self.logger:
                self.logger.error('text_recognition 导入失败: %s（OCR功能不可用）', _TEXT_RECOGNITION_ERROR)
        try:
            self.vision_system = create_vision_system_v3(
                camera_id=-1, width=1280, height=720,
                enable_basic=False, enable_advanced=False
            )
            if _TEXT_RECOGNITION_AVAILABLE:
                self.ocr = _TextRecognizer()
            if self.logger:
                self.logger.info('视觉系统初始化成功，OCR=%s',
                                 _TEXT_RECOGNITION_AVAILABLE and '可用' or '不可用')
        except Exception as e:
            if self.logger:
                self.logger.error('视觉系统初始化失败: %s', e)

    def init_voice(self):
        if not _VOICE_API_AVAILABLE or not _AUDIO_PLAYER_AVAILABLE or not _AUDIO_RECORDER_AVAILABLE:
            err = []
            if not _VOICE_API_AVAILABLE:
                err.append('voice_api: %s' % _VOICE_API_ERROR)
            if not _AUDIO_PLAYER_AVAILABLE:
                err.append('audio_player: %s' % _AUDIO_PLAYER_ERROR)
            if not _AUDIO_RECORDER_AVAILABLE:
                err.append('audio_recorder: %s' % _AUDIO_RECORDER_ERROR)
            if self.logger:
                self.logger.error('语音AI模块导入失败: %s', '; '.join(err))
            return
        try:
            self.voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
            self.voice_api.get_token(VOICE_USERNAME, VOICE_PASSWORD)
            self.player = AudioPlayer()
            self.recorder = AudioRecorder(sample_rate=16000, channels=1)
            self.recorder.set_output_dir('recordings')
            if self.logger:
                self.logger.info('语音AI初始化成功')
        except Exception as e:
            if self.logger:
                self.logger.error('语音AI初始化失败: %s', e)

    def init_camera_open(self):
        try:
            if not self.running:
                # 用户已退出，不再尝试打开摄像头（避免刚打开就被cleanup释放，
                # 下次再启动时出现设备忙）
                return
            if self.vision_system.open_camera():
                if not self.running:
                    # open_camera() 期间用户退出了：立即关闭摄像头，不启动采集线程
                    try:
                        self.vision_system.cleanup()
                    except Exception:
                        pass
                    self.camera_ok = False
                    return
                self.camera_ok = True
                if self.logger:
                    self.logger.info('摄像头初始化成功')
                self._start_camera_thread()
            else:
                if self.running:
                    if self.logger:
                        self.logger.warning('警告：摄像头打开失败')
        except Exception as e:
            if self.logger and self.running:
                self.logger.error('摄像头初始化异常: %s', e)

    def set_light(self, mode):
        if self.lights:
            self.lights.set_mode(mode)

    def _stop_speaking(self):
        """立即停止正在播放的语音（用于返回按钮等需要打断的场景）"""
        with self._lock:
            was_speaking = self.is_speaking
            self.is_speaking = False
        if was_speaking:
            if self.logger:
                self.logger.info('打断语音播放')
            if self.player:
                try:
                    self.player.stop()
                except Exception:
                    pass
            if self.mixer_ok:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass

    # ====== 摄像头后台采集线程 ======
    def _start_camera_thread(self):
        if self._camera_thread is not None and self._camera_thread.is_alive():
            return
        self._camera_thread_running = True
        self._camera_thread = threading.Thread(target=self._camera_capture_worker, daemon=True)
        self._camera_thread.start()
        if self.logger:
            self.logger.info('摄像头后台采集线程已启动')

    def _stop_camera_thread(self):
        self._camera_thread_running = False
        if self._camera_thread is not None:
            try:
                if self._camera_thread.is_alive():
                    self._camera_thread.join(timeout=2.0)
            except Exception:
                pass
            self._camera_thread = None
        if self.logger:
            self.logger.info('摄像头后台采集线程已停止')

    def _camera_capture_worker(self):
        while self._camera_thread_running and self.running:
            try:
                # OCR识别期间暂停采集，避免vision_system资源竞争导致卡死
                if self._camera_paused:
                    time.sleep(0.05)
                    continue
                if self.vision_system and self.camera_ok:
                    # capture_frame 可能阻塞，必须在锁外执行
                    # 否则OCR线程和主线程draw_guide拿不到锁会卡死
                    # 注意：本项目用独立 TextRecognizer 做 OCR，不依赖 vision_system
                    # 的检测结果，因此不再调用 result_accessor.refresh_results()
                    # （refresh_results 是为 get_*_detection 结果服务的，此处冗余）
                    frame = self.vision_system.capture_frame()
                    # 帧有效性校验：3维 shape + mean 过滤全黑/全白脏帧
                    # 用 frame.mean() 而非 gray.std()，避免 ARM 上灰度转换+标准差的高开销
                    if (frame is not None and hasattr(frame, 'shape')
                            and len(frame.shape) == 3 and frame.size > 0):
                        try:
                            m = frame.mean()
                            valid = 5 <= m <= 250
                        except Exception:
                            valid = True
                        if valid:
                            # 只有赋值复制时才加锁，锁持有时间极短
                            with self._camera_lock:
                                self._latest_frame = frame.copy()
            except Exception as _e:
                if self.logger:
                    self.logger.warning('摄像头采集线程异常: %s', _e)
            time.sleep(1.0 / 15)

    # ====== 语音操作（异步线程）======
    def speak_async(self, text, light_mode='speaking', restore_mode=None):
        if not self.voice_api:
            if self.logger:
                self.logger.warning('语音AI未初始化，无法播报')
            return

        def worker():
            with self._lock:
                self.is_speaking = True
            self.set_light(light_mode)
            if self.logger:
                self.logger.info('开始语音合成 (长度=%d字符)', len(text))
            try:
                audio_data = self.voice_api.tts_synthesize(text, 'recordings/tts_output.wav')
                if audio_data is not None:
                    self.player.play_file('recordings/tts_output.wav')
                    if self.logger:
                        self.logger.info('语音合成+播放完成')
            except Exception as e:
                if self.logger:
                    self.logger.error('语音合成失败: %s', e)
            finally:
                with self._lock:
                    self.is_speaking = False
                if restore_mode:
                    self.set_light(restore_mode)

        threading.Thread(target=worker, daemon=True).start()

    def match_book(self, text):
        """从文本中匹配图书（书名或作者）"""
        if not text:
            return None
        for book in BOOKS:
            if book['title'] in text or book['author'] in text:
                return book
        return None

    def ocr_recognize_async(self):
        """异步OCR识别 — 使用后台线程采集的共享帧"""
        if self._camera_initializing:
            with self._lock:
                self.guide_result = '摄像头正在启动中，请稍候再试。'
            return
        if not self.camera_ok or not self.ocr:
            with self._lock:
                self.guide_result = '摄像头或OCR未就绪，无法识别'
            return
        with self._lock:
            if self.guide_processing:
                return
            self.guide_processing = True
            self.guide_result = '正在识别中...'
        # 在主线程中快速抓取一帧快照（锁持有时间极短），传给OCR线程。
        # 这样OCR线程不再访问_latest_frame，与摄像头采集线程完全解耦。
        # 不暂停摄像头采集：capture_frame是I/O操作会释放GIL，让主线程有
        # 机会运行；暂停反而使PaddleOCR长时间独占GIL导致界面卡死。
        with self._camera_lock:
            frame_snapshot = self._latest_frame.copy() if self._latest_frame is not None else None
        self.set_light('recognizing')
        if self.logger:
            self.logger.info('OCR识别线程启动 (帧尺寸=%s)',
                             str(frame_snapshot.shape) if frame_snapshot is not None else 'None')

        def worker(frame):
            ocr_result = {'done': False, 'result': None, 'error': None}
            def ocr_run():
                try:
                    if frame is None:
                        ocr_result['error'] = '无法获取摄像头画面，请检查摄像头连接'
                        return
                    # 缩小帧尺寸再送OCR：1280x720帧太大，PaddleOCR推理时长时间
                    # 占用GIL会导致主线程(pygame循环)被饿死而界面卡死。
                    # 缩放到宽度640（与官方范例《文字识别播报器》一致），推理速度
                    # 提升数倍，GIL占用时间大幅缩短，主线程得以正常运行。
                    h, w = frame.shape[:2]
                    if w > 640:
                        frame_small = cv2.resize(frame, (640, int(h * 640 / w)))
                    else:
                        frame_small = frame
                    if self.logger:
                        self.logger.info('OCR: 开始文字识别 (原始=%dx%d, 送检=%dx%d)',
                                         w, h, frame_small.shape[1], frame_small.shape[0])
                    res = self.ocr.recognize_text(frame_small, confidence_threshold=0.5)
                    ocr_result['result'] = res
                except Exception as e:
                    ocr_result['error'] = e
                finally:
                    ocr_result['done'] = True

            ocr_thread = threading.Thread(target=ocr_run, daemon=True)
            ocr_thread.start()
            # 最多等待15秒，超时则放弃识别（避免recognize_text永久阻塞导致卡死）
            ocr_thread.join(timeout=15.0)
            try:
                if not ocr_result['done']:
                    # OCR超时
                    if self.logger:
                        self.logger.error('OCR识别超时(15秒)，强制结束')
                    with self._lock:
                        self.guide_result = '识别超时，请重试或检查摄像头连接。'
                    with self._lock:
                        self.guide_processing = False
                    self.set_light('guide')
                    return
                if ocr_result['error'] is not None:
                    raise ocr_result['error']
                result = ocr_result['result']
                if self.logger:
                    self.logger.info('OCR: 识别完成 success=%s', result.get('success') if result else 'None')
                if result and result['success'] and result['text'].strip():
                    text = result['text'].strip()
                    if self.logger:
                        self.logger.info('OCR识别到文字: %s', text)
                    with self._lock:
                        self.guide_ocr_text = text
                    matched = self.match_book(text)
                    if matched:
                        intro = f"识别到图书《{matched['title']}》。{matched['intro']}"
                        with self._lock:
                            self.guide_result = intro
                            self.conversation_history.append(('系统', f"识别到：《{matched['title']}》"))
                        self.speak_async(intro, restore_mode='guide')
                    else:
                        with self._lock:
                            self.guide_result = f"识别到文字：{text}\n\n这不是馆藏图书，请重新对准书名进行识别。"
                            self.conversation_history.append(('系统', '未识别到馆藏图书'))
                        self.speak_async('识别到的内容不是馆藏图书，请重新对准书名进行识别。', restore_mode='guide')
                else:
                    msg = '未能识别到文字，请重新对准书名进行识别。'
                    with self._lock:
                        self.guide_result = msg
                    self.speak_async(msg, restore_mode='guide')
            except Exception as e:
                if self.logger:
                    self.logger.exception('OCR识别异常: %s', e)
                with self._lock:
                    self.guide_result = f'识别出错: {e}'
            finally:
                with self._lock:
                    self.guide_processing = False
                self.set_light('guide')
                if self.logger:
                    self.logger.info('OCR识别线程结束')

        threading.Thread(target=worker, args=(frame_snapshot,), daemon=True).start()

    def voice_converse_async(self):
        """处理已录制的语音：识别→匹配图书/LLM→播报"""
        if not self.voice_api:
            with self._lock:
                self.guide_result = '语音AI未初始化，无法处理'
            return
        with self._lock:
            if self.guide_processing:
                return
            self.guide_processing = True
        self.set_light('recognizing')

        def worker():
            try:
                audio_file = 'recordings/guide_voice.wav'
                if not os.path.exists(audio_file):
                    with self._lock:
                        self.guide_result = '录音文件不存在，请重试'
                    return
                file_size = os.path.getsize(audio_file)
                if file_size < 1000:
                    if self.logger:
                        self.logger.warning('录音文件过小(%d字节)，视为无效', file_size)
                    msg = '录音内容太短，请按住按钮重新说话。'
                    with self._lock:
                        self.guide_result = msg
                    self.speak_async(msg, restore_mode='guide')
                    return
                if self.logger:
                    self.logger.info('语音对话线程启动，音频文件: %s  存在=%s  大小=%d',
                                     audio_file, os.path.exists(audio_file), file_size)
                text = self.voice_api.voice_recognition(audio_file)
                if self.logger:
                    self.logger.info('ASR识别结果: %s', text)
                with self._lock:
                    self.guide_ocr_text = text
                    self.conversation_history.append(('读者', text))

                if not text or not text.strip():
                    msg = '未检测到有效语音内容，请重新按住按钮说话。'
                    with self._lock:
                        self.guide_result = msg
                        self.conversation_history.append(('系统', '未检测到有效语音'))
                    self.speak_async(msg, restore_mode='guide')
                    return

                matched = self.match_book(text)
                if matched:
                    intro = f"关于《{matched['title']}》：{matched['intro']}"
                    with self._lock:
                        self.guide_result = intro
                        self.conversation_history.append(('系统', f"为您介绍《{matched['title']}》"))
                    self.speak_async(intro, restore_mode='guide')
                else:
                    book_keywords = ['书', '作者', '作家', '图书', '名著', '小说', '诗人', '文学', '童话', '诗']
                    if any(kw in text for kw in book_keywords):
                        with self._lock:
                            self.guide_result = '正在思考中...'
                        answer = self.voice_api.llm_chat(text)
                        if self.logger:
                            self.logger.info('LLM回答长度: %d', len(answer) if answer else 0)
                        if answer and len(answer) > 200:
                            answer = answer[:200]
                        with self._lock:
                            self.guide_result = answer or '暂时无法获取回答'
                            self.conversation_history.append(('系统', '智能回答'))
                        self.speak_async(answer, restore_mode='guide')
                    else:
                        msg = '未检测到与图书相关的有效信息，请重新说一下您想了解的图书或作家。'
                        with self._lock:
                            self.guide_result = msg
                            self.conversation_history.append(('系统', '未检测到图书信息'))
                        self.speak_async(msg, restore_mode='guide')
            except Exception as e:
                if self.logger:
                    self.logger.exception('语音对话异常: %s', e)
                with self._lock:
                    self.guide_result = f'处理出错: {e}'
            finally:
                with self._lock:
                    self.guide_processing = False
                self.set_light('guide')
                if self.logger:
                    self.logger.info('语音对话线程结束')

        threading.Thread(target=worker, daemon=True).start()

    # ====== 背景绘制 ======
    def draw_background(self):
        self.window.blit(self._bg_surface, (0, 0))

    # ====== 加载屏（启动时显示）======
    def draw_init(self):
        self.draw_background()
        cx, cy = WINDOW_W // 2, WINDOW_H // 2
        title = self.font_large.render('智慧阅读角', True, C_PRIMARY)
        self.window.blit(title, (cx - title.get_width() // 2, cy - 120))
        sub = self.font_med.render('Smart Reading Corner', True, C_TEXT_LIGHT)
        self.window.blit(sub, (cx - sub.get_width() // 2, cy - 50))
        now = time.time()
        pulse = (math.sin(now * 4) + 1) / 2
        dot_y = cy + 40
        for i in range(3):
            alpha = max(0.3, 1.0 - abs(pulse - i * 0.5) * 0.8)
            r = int(255 * alpha)
            pygame.draw.circle(self.window, (r, r, r), (cx - 30 + i * 30, dot_y), 12)
        stage = self._init_stage or '正在加载...'
        stage_surf = self.font_small.render(stage, True, C_TEXT_GRAY)
        self.window.blit(stage_surf, (cx - stage_surf.get_width() // 2, cy + 80))
        if self._init_error:
            err = self.font_small.render(f'初始化异常: {self._init_error}', True, C_BTN_RETURN)
            self.window.blit(err, (cx - err.get_width() // 2, cy + 120))

    # ====== 用户名密码未填提示屏 ======
    def draw_auth_error(self):
        self.draw_background()
        cx, cy = WINDOW_W // 2, WINDOW_H // 2
        # 标题
        title = self.font_large.render('语音AI账号未配置', True, C_BTN_RETURN)
        self.window.blit(title, (cx - title.get_width() // 2, cy - 320))
        # 说明文字（从标题下方开始，向下逐行排列）
        lines = [
            '请在程序源码中填写语音AI的用户名和密码：',
            '',
            "VOICE_USERNAME = '你的好好搭搭账号'",
            "VOICE_PASSWORD = '你的好好搭搭密码'",
        ]
        y = cy - 210
        for line in lines:
            s = self.font_med.render(line, True, C_TEXT_LIGHT)
            self.window.blit(s, (cx - s.get_width() // 2, y))
            y += 55
        # 提示文字
        hint = self.font_med.render('填写后重新运行程序即可。', True, C_PRIMARY)
        self.window.blit(hint, (cx - hint.get_width() // 2, y + 20))
        # 退出按钮（在最下方，与文字留出充足间距）
        self._exit_rect = pygame.Rect(cx - 120, cy + 180, 240, 70)
        hover = self._exit_rect.collidepoint(self.mouse_pos)
        draw_button(self.window, self._exit_rect, '退出程序', self.font_btn, C_BTN_RETURN, hover=hover)

    # ====== 各界面绘制 ======
    def draw_welcome(self):
        self.draw_background()
        cx, cy = WINDOW_W // 2, WINDOW_H // 2

        # 退出按钮（右上角）
        self._exit_rect = pygame.Rect(WINDOW_W - 230, 30, 170, 60)
        hover = self._exit_rect.collidepoint(self.mouse_pos)
        draw_button(self.window, self._exit_rect, '退出程序', self.font_btn, C_BTN_RETURN, hover=hover)

        # 装饰横线
        pygame.draw.line(self.window, C_PRIMARY_DARK, (cx - 350, cy - 200), (cx + 350, cy - 200), 2)

        # 主标题（带阴影）
        title_text = '欢迎来到智慧阅读角'
        shadow = self.font_title.render(title_text, True, (20, 15, 10))
        title = self.font_title.render(title_text, True, C_PRIMARY)
        self.window.blit(shadow, (cx - title.get_width() // 2 + 3, cy - 120 + 3))
        self.window.blit(title, (cx - title.get_width() // 2, cy - 120))

        # 副标题
        sub = self.font_large.render('享受阅读时光', True, C_TEXT_LIGHT)
        self.window.blit(sub, (cx - sub.get_width() // 2, cy + 10))

        # 装饰横线
        pygame.draw.line(self.window, C_PRIMARY, (cx - 350, cy + 100), (cx + 350, cy + 100), 3)

        # PIR状态提示
        pir_val = self.check_pir()
        if pir_val == 1:
            status_text = '● 检测到有人，正在进入...'
            status_color = C_ACCENT_GREEN
        else:
            status_text = '● 等待人体感应器检测...'
            status_color = C_TEXT_GRAY
        status = self.font_small.render(status_text, True, status_color)
        self.window.blit(status, (cx - status.get_width() // 2, cy + 140))

        # 功能简介
        intro_lines = ['馆藏图书 · 语音介绍', '图书视频 · 生动呈现', '智能导读 · AI对话']
        for i, line in enumerate(intro_lines):
            s = self.font_small.render(line, True, C_TEXT_GRAY)
            self.window.blit(s, (cx - s.get_width() // 2, cy + 200 + i * 40))

    def draw_menu(self):
        self.draw_background()
        cx = WINDOW_W // 2

        # 标题
        title = self.font_large.render('请选择您需要的功能', True, C_TEXT_LIGHT)
        self.window.blit(title, (cx - title.get_width() // 2, 80))
        pygame.draw.line(self.window, C_PRIMARY, (cx - 300, 160), (cx + 300, 160), 3)

        # 三个功能卡片
        card_w, card_h = 460, 560
        gap = 60
        total_w = card_w * 3 + gap * 2
        start_x = (WINDOW_W - total_w) // 2
        card_y = 220

        functions = [
            {'name': '馆藏图书', 'desc': '浏览馆藏\n语音介绍', 'color': C_PRIMARY, 'icon_char': '书'},
            {'name': '图书视频', 'desc': '名著视频\n生动呈现', 'color': C_ACCENT_PURPLE, 'icon_char': '影'},
            {'name': '智能导读', 'desc': 'AI识别\n智能对话', 'color': C_ACCENT_CYAN, 'icon_char': '识'},
        ]

        self._menu_cards = []
        for i, func in enumerate(functions):
            x = start_x + i * (card_w + gap)
            rect = pygame.Rect(x, card_y, card_w, card_h)
            hover = rect.collidepoint(self.mouse_pos)
            self._menu_cards.append((rect, i))

            shadow_rect = rect.move(5, 8)
            pygame.draw.rect(self.window, (20, 15, 25), shadow_rect, border_radius=20)
            card_color = lighten(func['color'], 20) if hover else func['color']
            pygame.draw.rect(self.window, card_color, rect, border_radius=20)
            pygame.draw.rect(self.window, lighten(card_color, 50), rect, 3, border_radius=20)

            icon_cy = rect.y + 140
            pygame.draw.circle(self.window, lighten(card_color, 40), (rect.centerx, icon_cy), 80)
            pygame.draw.circle(self.window, (255, 255, 255), (rect.centerx, icon_cy), 80, 3)
            icon_text = self.font_title.render(func['icon_char'], True, (255, 255, 255))
            self.window.blit(icon_text, (rect.centerx - icon_text.get_width() // 2,
                                         icon_cy - icon_text.get_height() // 2))

            name_surf = self.font_large.render(func['name'], True, (255, 255, 255))
            self.window.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 280))

            for j, line in enumerate(func['desc'].split('\n')):
                desc_surf = self.font_med.render(line, True, lighten(card_color, 60))
                self.window.blit(desc_surf, (rect.centerx - desc_surf.get_width() // 2, rect.y + 380 + j * 55))

        # 返回首页按钮（居中，大按钮）
        self._menu_return_rect = pygame.Rect(WINDOW_W // 2 - 180, WINDOW_H - 110, 360, 75)
        hover = self._menu_return_rect.collidepoint(self.mouse_pos)
        draw_button(self.window, self._menu_return_rect, '返回首页', self.font_med, C_BTN_RETURN, hover=hover)

        # 倒计时提示
        elapsed = time.time() - self.menu_enter_time
        remaining = max(0, MENU_TIMEOUT - int(elapsed))
        timer_text = f'无人操作 {remaining} 秒后自动返回欢迎界面'
        timer_color = C_ACCENT_GREEN if remaining > 10 else C_BTN_RETURN
        timer_surf = self.font_small.render(timer_text, True, timer_color)
        self.window.blit(timer_surf, (cx - timer_surf.get_width() // 2, WINDOW_H - 30))

    def draw_library(self):
        self.draw_background()

        # 顶部标题栏
        pygame.draw.rect(self.window, (40, 35, 55), (0, 0, WINDOW_W, 80))
        title = self.font_large.render('馆藏图书', True, C_PRIMARY)
        self.window.blit(title, (40, 10))

        # 返回按钮
        self._lib_return_rect = pygame.Rect(WINDOW_W - 200, 15, 150, 55)
        hover = self._lib_return_rect.collidepoint(self.mouse_pos)
        draw_button(self.window, self._lib_return_rect, '返回', self.font_btn, C_BTN_RETURN, hover=hover)

        # 左侧书单面板
        left_panel = pygame.Rect(30, 110, 620, WINDOW_H - 150)
        draw_panel(self.window, left_panel)
        list_title = self.font_med.render('图书列表', True, C_TEXT_DARK)
        self.window.blit(list_title, (left_panel.x + 20, left_panel.y + 15))
        pygame.draw.line(self.window, C_PRIMARY,
                         (left_panel.x + 20, left_panel.y + 65),
                         (left_panel.right - 20, left_panel.y + 65), 2)

        # 书名按钮（放大高度避免书名作者重叠）
        self._book_buttons = []
        btn_y = left_panel.y + 85
        for i, book in enumerate(BOOKS):
            btn_rect = pygame.Rect(left_panel.x + 20, btn_y, left_panel.width - 40, 90)
            hover = btn_rect.collidepoint(self.mouse_pos)
            selected = (self.selected_book and self.selected_book['title'] == book['title'])

            if selected:
                bg = C_PRIMARY
                tc = (255, 255, 255)
                ac = (255, 230, 200)
            elif hover:
                bg = (230, 220, 205)
                tc = C_TEXT_DARK
                ac = C_TEXT_GRAY
            else:
                bg = (235, 228, 215)
                tc = C_TEXT_DARK
                ac = C_TEXT_GRAY

            pygame.draw.rect(self.window, bg, btn_rect, border_radius=10)
            pygame.draw.rect(self.window, C_PRIMARY_DARK, btn_rect, 2, border_radius=10)

            name_surf = self.font_med.render(f"《{book['title']}》", True, tc)
            self.window.blit(name_surf, (btn_rect.x + 20, btn_rect.y + 10))
            author_surf = self.font_author.render(f"作者：{book['author']}", True, ac)
            self.window.blit(author_surf, (btn_rect.x + 20, btn_rect.y + 54))

            self._book_buttons.append((btn_rect, i))
            btn_y += 100

        # 右侧介绍面板
        right_panel = pygame.Rect(680, 110, WINDOW_W - 710, WINDOW_H - 150)
        draw_panel(self.window, right_panel)

        if self.selected_book:
            book = self.selected_book
            title_surf = self.font_large.render(f"《{book['title']}》", True, C_PRIMARY_DARK)
            self.window.blit(title_surf, (right_panel.x + 30, right_panel.y + 25))
            author_surf = self.font_med.render(f"作者：{book['author']}", True, C_TEXT_GRAY)
            self.window.blit(author_surf, (right_panel.x + 30, right_panel.y + 95))
            pygame.draw.line(self.window, C_PRIMARY,
                             (right_panel.x + 30, right_panel.y + 155),
                             (right_panel.right - 30, right_panel.y + 155), 2)
            draw_wrapped_text(self.window, book['intro'], self.font_med, C_TEXT_DARK,
                              right_panel.x + 30, right_panel.y + 180,
                              right_panel.width - 60)

            with self._lock:
                speaking = self.is_speaking
            if speaking:
                status = self.font_small.render('● 正在为您介绍...', True, C_ACCENT_GREEN)
                self.window.blit(status, (right_panel.right - 220, right_panel.y + 30))
            # 播报中点击其他书的禁止提示（红色醒目标识）
            if self._library_blocked_hint:
                hint_rect = pygame.Rect(right_panel.x + 30, right_panel.bottom - 60,
                                        right_panel.width - 60, 45)
                pygame.draw.rect(self.window, (250, 225, 225), hint_rect, border_radius=8)
                pygame.draw.rect(self.window, C_BTN_RETURN, hint_rect, 2, border_radius=8)
                hint_surf = self.font_small.render(self._library_blocked_hint, True, C_BTN_RETURN)
                self.window.blit(hint_surf, (hint_rect.x + 15, hint_rect.y + 6))
        else:
            hint = self.font_large.render('请点击书名，我来为你介绍', True, C_TEXT_GRAY)
            self.window.blit(hint, (right_panel.centerx - hint.get_width() // 2,
                                    right_panel.centery - hint.get_height() // 2))

    def draw_videos(self):
        self.draw_background()

        # 顶部标题栏
        pygame.draw.rect(self.window, (40, 35, 55), (0, 0, WINDOW_W, 80))
        title = self.font_large.render('图书视频', True, C_ACCENT_PURPLE)
        self.window.blit(title, (40, 10))

        # 返回按钮
        self._vid_return_rect = pygame.Rect(WINDOW_W - 200, 15, 150, 55)
        hover = self._vid_return_rect.collidepoint(self.mouse_pos)
        draw_button(self.window, self._vid_return_rect, '返回', self.font_btn, C_BTN_RETURN, hover=hover)

        # 三个视频卡片
        card_w, card_h = 480, 640
        gap = 50
        total_w = card_w * 3 + gap * 2
        start_x = (WINDOW_W - total_w) // 2
        card_y = 130

        self._video_cards = []
        for i, vb in enumerate(VIDEO_BOOKS):
            x = start_x + i * (card_w + gap)
            rect = pygame.Rect(x, card_y, card_w, card_h)
            hover = rect.collidepoint(self.mouse_pos)
            self._video_cards.append((rect, i))

            shadow_rect = rect.move(5, 8)
            pygame.draw.rect(self.window, (20, 15, 25), shadow_rect, border_radius=20)
            color = lighten(C_ACCENT_PURPLE, 20) if hover else C_ACCENT_PURPLE
            pygame.draw.rect(self.window, color, rect, border_radius=20)
            pygame.draw.rect(self.window, lighten(color, 50), rect, 3, border_radius=20)

            icon_cx = rect.centerx
            icon_cy = rect.y + 230
            pygame.draw.circle(self.window, (255, 255, 255), (icon_cx, icon_cy), 75)
            pygame.draw.circle(self.window, lighten(color, 30), (icon_cx, icon_cy), 75, 3)
            pygame.draw.polygon(self.window, color,
                                [(icon_cx - 22, icon_cy - 32),
                                 (icon_cx - 22, icon_cy + 32),
                                 (icon_cx + 35, icon_cy)])

            name_surf = self.font_large.render(f"《{vb['title']}》", True, (255, 255, 255))
            self.window.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 360))

            hint = self.font_med.render('点击播放视频', True, lighten(color, 60))
            self.window.blit(hint, (rect.centerx - hint.get_width() // 2, rect.y + 450))

            if not os.path.exists(vb['file']):
                warn = self.font_small.render('⚠ 视频文件不存在', True, (255, 200, 100))
                self.window.blit(warn, (rect.centerx - warn.get_width() // 2, rect.y + 520))

    def draw_video_play(self):
        self.draw_background()

        # 视频画面区域
        video_rect = pygame.Rect(60, 40, WINDOW_W - 120, WINDOW_H - 160)
        pygame.draw.rect(self.window, (0, 0, 0), video_rect, border_radius=12)
        pygame.draw.rect(self.window, C_PRIMARY, video_rect, 3, border_radius=12)

        # 从队列取帧（不阻塞）
        try:
            frame = self.video_frame_queue.get_nowait()
            self._cached_video_surf = frame
        except queue.Empty:
            pass

        if self._cached_video_surf is not None:
            self.window.blit(self._cached_video_surf, (video_rect.x + 3, video_rect.y + 3))

        # 停止按钮（放大，居中）
        self._vid_stop_rect = pygame.Rect(WINDOW_W // 2 - 180, WINDOW_H - 95, 360, 75)
        hover = self._vid_stop_rect.collidepoint(self.mouse_pos)
        draw_button(self.window, self._vid_stop_rect, '停止播放', self.font_med, C_BTN_RETURN, hover=hover)

    def draw_guide(self):
        self.draw_background()

        # 顶部标题栏
        pygame.draw.rect(self.window, (40, 35, 55), (0, 0, WINDOW_W, 80))
        title = self.font_large.render('智能导读', True, C_ACCENT_CYAN)
        self.window.blit(title, (40, 10))

        # 返回按钮
        self._guide_return_rect = pygame.Rect(WINDOW_W - 200, 15, 150, 55)
        hover = self._guide_return_rect.collidepoint(self.mouse_pos)
        draw_button(self.window, self._guide_return_rect, '返回', self.font_btn, C_BTN_RETURN, hover=hover)

        # 左侧：摄像头预览
        cam_panel = pygame.Rect(30, 110, 800, 520)
        draw_panel(self.window, cam_panel)
        cam_title = self.font_med.render('摄像头预览', True, C_TEXT_DARK)
        self.window.blit(cam_title, (cam_panel.x + 20, cam_panel.y + 10))

        preview_rect = pygame.Rect(cam_panel.x + 20, cam_panel.y + 60, 760, 440)
        pygame.draw.rect(self.window, (20, 20, 30), preview_rect, border_radius=8)

        if self.camera_ok:
            with self._lock:
                processing = self.guide_processing
            try:
                if processing:
                    # OCR识别中：不进行cv2操作，避免与OCR内部的cv2调用竞争导致画面卡死
                    # 显示最后一帧的静态画面（如果有缓存）
                    if hasattr(self, '_guide_preview_surf') and self._guide_preview_surf is not None:
                        self.window.blit(self._guide_preview_surf, preview_rect.topleft)
                    else:
                        tip = self.font_med.render('正在识别中，请稍候...', True, C_ACCENT_CYAN)
                        self.window.blit(tip, (preview_rect.centerx - tip.get_width() // 2,
                                               preview_rect.centery - tip.get_height() // 2))
                else:
                    # 直接读取后台线程采集的最新帧（不阻塞主循环）
                    with self._camera_lock:
                        frame = self._latest_frame.copy() if self._latest_frame is not None else None
                    if frame is not None:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frame_rgb = cv2.resize(frame_rgb, (preview_rect.width, preview_rect.height))
                        surf = pygame.image.frombuffer(frame_rgb.tobytes(),
                                                       (preview_rect.width, preview_rect.height), 'RGB')
                        # 缓存最后一帧用于识别期间显示
                        self._guide_preview_surf = surf.copy()
                        self.window.blit(surf, preview_rect.topleft)
            except:
                pass
        else:
            if self._camera_initializing:
                err_text = '摄像头正在启动，请稍候...'
                err_color = C_ACCENT_CYAN
            else:
                err_text = '摄像头未连接'
                err_color = C_BTN_RETURN
            err = self.font_med.render(err_text, True, err_color)
            self.window.blit(err, (preview_rect.centerx - err.get_width() // 2,
                                   preview_rect.centery - err.get_height() // 2))

        pygame.draw.rect(self.window, C_ACCENT_CYAN, preview_rect, 2, border_radius=8)

        # 识别按钮
        self._ocr_btn = pygame.Rect(cam_panel.x + 20, cam_panel.bottom + 20, 360, 70)
        ocr_hover = self._ocr_btn.collidepoint(self.mouse_pos)
        with self._lock:
            processing = self.guide_processing
        btn_text = '识别中...' if processing else '识别文字'
        draw_button(self.window, self._ocr_btn, btn_text, self.font_btn, C_ACCENT_GREEN, hover=ocr_hover)

        # 对话按钮（按住说话）
        self._voice_btn = pygame.Rect(cam_panel.x + 400, cam_panel.bottom + 20, 380, 70)
        voice_hover = self._voice_btn.collidepoint(self.mouse_pos)
        with self._lock:
            recording = self.guide_recording
        vbtn_text = '● 松开结束' if recording else '按住说话'
        vbtn_color = C_BTN_RETURN if recording else C_ACCENT_BLUE
        draw_button(self.window, self._voice_btn, vbtn_text, self.font_btn, vbtn_color, hover=voice_hover)

        # 右侧：结果面板
        result_panel = pygame.Rect(860, 110, WINDOW_W - 890, WINDOW_H - 150)
        draw_panel(self.window, result_panel)

        res_title = self.font_med.render('识别结果 / 对话', True, C_TEXT_DARK)
        self.window.blit(res_title, (result_panel.x + 20, result_panel.y + 10))
        pygame.draw.line(self.window, C_ACCENT_CYAN,
                         (result_panel.x + 20, result_panel.y + 55),
                         (result_panel.right - 20, result_panel.y + 55), 2)

        with self._lock:
            result_text = self.guide_result
            ocr_text = self.guide_ocr_text
            history = list(self.conversation_history[-6:])

        y = result_panel.y + 75
        if ocr_text:
            label = self.font_small.render(f'识别文字：{ocr_text}', True, C_ACCENT_BLUE)
            self.window.blit(label, (result_panel.x + 20, y))
            y += 40

        if result_text:
            y = draw_wrapped_text(self.window, result_text, self.font_small, C_TEXT_DARK,
                                  result_panel.x + 20, y, result_panel.width - 40, 36)

        # 对话历史
        if history:
            y += 20
            if y < result_panel.bottom - 60:
                pygame.draw.line(self.window, C_TEXT_GRAY,
                                 (result_panel.x + 20, y),
                                 (result_panel.right - 20, y), 1)
                y += 15
                hist_title = self.font_small.render('对话记录：', True, C_TEXT_GRAY)
                self.window.blit(hist_title, (result_panel.x + 20, y))
                y += 35
                for role, text in history:
                    if y > result_panel.bottom - 40:
                        break
                    color = C_ACCENT_BLUE if role == '读者' else C_ACCENT_GREEN
                    role_surf = self.font_small.render(f'[{role}]', True, color)
                    self.window.blit(role_surf, (result_panel.x + 20, y))
                    # [系统]和文字之间留出间距
                    y = draw_wrapped_text(self.window, text, self.font_small, C_TEXT_DARK,
                                          result_panel.x + 100, y, result_panel.width - 120, 32)
                    y += 10

        # 操作提示
        hint = self.font_small.render('点击"识别文字"识别书名 | 按住"按住说话"进行语音对话', True, C_TEXT_GRAY)
        self.window.blit(hint, (30, WINDOW_H - 45))

    # ====== 视频播放控制 ======
    def _start_video(self, video_path):
        if not os.path.exists(video_path):
            if self.logger:
                self.logger.warning('视频文件不存在: %s', video_path)
            return
        # 先确保之前的视频已停止
        self._stop_video_internal(blocking=False)
        self.video_finished.clear()
        self.video_stop_event.clear()
        # 清空队列
        try:
            while not self.video_frame_queue.empty():
                self.video_frame_queue.get_nowait()
        except:
            pass
        self._cached_video_surf = None

        self.video_cap = cv2.VideoCapture(video_path)
        if not self.video_cap.isOpened():
            if self.logger:
                self.logger.error('无法打开视频: %s', video_path)
            self.video_cap = None
            return

        # 查找音频文件
        audio_path = os.path.splitext(video_path)[0] + '_audio.wav'
        if self.mixer_ok and os.path.exists(audio_path):
            try:
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
                if self.logger:
                    self.logger.info('视频音频开始播放: %s', audio_path)
            except Exception as e:
                if self.logger:
                    self.logger.warning('视频音频加载失败: %s', e)

        if self.logger:
            self.logger.info('开始播放视频: %s', video_path)
        self.state = self.S_VIDEO_PLAY
        self.set_light('videos')
        # 启动视频播放线程
        self.video_thread = threading.Thread(target=self._video_thread_func, args=(video_path,), daemon=True)
        self.video_thread.start()
        if self.logger:
            self.logger.info('视频播放线程启动: %s', video_path)

    def _video_thread_func(self, video_path):
        """视频播放线程：读取帧并放入队列"""
        cap = self.video_cap
        if cap is None:
            return
        try:
            while not self.video_stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    # 视频播放完毕
                    if self.logger:
                        self.logger.info('视频自然播放完毕')
                    self.video_finished.set()
                    break
                try:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_rgb = cv2.resize(frame_rgb, (WINDOW_W - 126, WINDOW_H - 166))
                    surf = pygame.image.frombuffer(frame_rgb.tobytes(),
                                                   (WINDOW_W - 126, WINDOW_H - 166), 'RGB')
                    # 非阻塞放入队列，如果队列满则丢弃旧帧
                    try:
                        self.video_frame_queue.put_nowait(surf)
                    except queue.Full:
                        try:
                            self.video_frame_queue.get_nowait()
                            self.video_frame_queue.put_nowait(surf)
                        except Exception:
                            pass
                except Exception as _e:
                    if self.logger:
                        self.logger.debug('视频帧处理异常: %s', _e)
                time.sleep(1.0 / 30)
        except Exception as _e:
            if self.logger:
                self.logger.warning('视频播放线程异常: %s', _e)
        finally:
            try:
                if cap is not None:
                    cap.release()
            except:
                pass
            if self.logger:
                self.logger.info('视频播放线程结束')

    def _stop_video_internal(self, blocking=False):
        """内部停止视频线程与资源（不带状态切换）
        blocking=False（默认）：只发停止信号，不join线程，避免阻塞主循环导致点击丢失
        blocking=True：等待线程结束（仅在cleanup时使用）
        """
        try:
            self.video_stop_event.set()
        except:
            pass
        if blocking and self.video_thread is not None:
            try:
                if self.video_thread.is_alive():
                    self.video_thread.join(timeout=2.0)
            except:
                pass
            self.video_thread = None
        # 停止音频
        if self.mixer_ok:
            try:
                pygame.mixer.music.stop()
            except:
                pass
        # 残留队列清空
        try:
            while not self.video_frame_queue.empty():
                self.video_frame_queue.get_nowait()
        except:
            pass
        # 注意：不在此处调用video_cap.release()！
        # worker线程的finally块已负责release。主线程与worker线程同时操作同一cap
        # 会导致OpenCV内部锁死或crash。
        self.video_cap = None
        if hasattr(self, '_cached_video_surf'):
            try:
                delattr(self, '_cached_video_surf')
            except:
                pass
        self._cached_video_surf = None

    def _stop_video(self):
        """用户停止视频 → 返回图书视频界面"""
        if self.logger:
            self.logger.info('用户停止视频播放')
        self._stop_video_internal(blocking=False)
        self.state = self.S_VIDEOS
        self.set_light('videos')

    # ====== 事件处理 ======
    def handle_events(self):
        for event in pygame.event.get():
            if not self.running:
                break
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type == pygame.MOUSEMOTION:
                self.mouse_pos = event.pos
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.mouse_pos = event.pos
                if event.button == 1:
                    self.handle_click(event.pos)
            if event.type == pygame.MOUSEBUTTONUP:
                self.mouse_pos = event.pos
                if event.button == 1:
                    self.handle_mouse_up(event.pos)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and self.state == self.S_VIDEO_PLAY:
                    self._stop_video()
                elif event.key == pygame.K_ESCAPE:
                    if self.state == self.S_INIT:
                        self.running = False
                    elif self.state == self.S_VIDEO_PLAY:
                        self._stop_video()
                    elif self.state in (self.S_LIBRARY, self.S_VIDEOS, self.S_GUIDE):
                        self._stop_speaking()
                        self.state = self.S_MENU
                        self.menu_enter_time = time.time()
                        self.set_light('menu')
                    elif self.state == self.S_MENU:
                        self._stop_speaking()
                        self.state = self.S_WELCOME
                        with self._lock:
                            self.welcome_played = False
                        self.set_light('welcome')

    def handle_click(self, pos):
        if self.state == self.S_WELCOME:
            if self._exit_rect and self._exit_rect.collidepoint(pos):
                if self.logger:
                    self.logger.info('用户点击欢迎屏右上角【退出程序】按钮')
                self.running = False
                return

        elif self.state == self.S_MENU:
            # 返回首页按钮
            if self._menu_return_rect is not None:
                if self._menu_return_rect.collidepoint(pos):
                    self._stop_speaking()
                    self.state = self.S_WELCOME
                    with self._lock:
                        self.welcome_played = False
                    self.set_light('welcome')
                    if self.logger:
                        self.logger.info('功能选择界面→返回首页（用户点击返回首页按钮）')
                    return
            for rect, idx in self._menu_cards:
                if rect.collidepoint(pos):
                    if idx == 0:
                        if self.logger:
                            self.logger.info('进入功能：馆藏图书')
                        self.state = self.S_LIBRARY
                        self.selected_book = None
                        self.set_light('library')
                    elif idx == 1:
                        if self.logger:
                            self.logger.info('进入功能：图书视频')
                        self.state = self.S_VIDEOS
                        self.set_light('videos')
                    elif idx == 2:
                        if self.logger:
                            self.logger.info('进入功能：智能导读')
                        self.state = self.S_GUIDE
                        self.set_light('guide')
                    return

        elif self.state == self.S_LIBRARY:
            if self._lib_return_rect and self._lib_return_rect.collidepoint(pos):
                if self.logger:
                    self.logger.info('从【馆藏图书】返回功能选择界面')
                self._stop_speaking()
                self.state = self.S_MENU
                self.menu_enter_time = time.time()
                self.set_light('menu')
                self.last_speaking_book = None
                return
            for rect, idx in self._book_buttons:
                if rect.collidepoint(pos):
                    # 正在播报中禁止切换
                    with self._lock:
                        speaking = self.is_speaking
                    if speaking:
                        if self.logger:
                            self.logger.info('正在播报中，点击图书《%s》已禁止（介绍结束前不可切换）',
                                             BOOKS[idx]['title'])
                        # 右侧面板显示提示（临时提示不修改原始数据）
                        self._library_blocked_hint = f"正在为您介绍《{self.last_speaking_book or '图书'}》，介绍结束前不可切换，请稍候..."
                        return
                    # 清除之前的禁止提示
                    self._library_blocked_hint = ''
                    self.selected_book = BOOKS[idx]
                    self.last_speaking_book = BOOKS[idx]['title']
                    intro = f"为您介绍《{BOOKS[idx]['title']}》。{BOOKS[idx]['intro']}"
                    if self.logger:
                        self.logger.info('点击图书《%s》，开始语音介绍', BOOKS[idx]['title'])
                    self.speak_async(intro, restore_mode='library')
                    return

        elif self.state == self.S_VIDEOS:
            if self._vid_return_rect and self._vid_return_rect.collidepoint(pos):
                if self.logger:
                    self.logger.info('从【图书视频】返回功能选择界面')
                self._stop_speaking()
                self.state = self.S_MENU
                self.menu_enter_time = time.time()
                self.set_light('menu')
                return
            for rect, idx in self._video_cards:
                if rect.collidepoint(pos):
                    vb = VIDEO_BOOKS[idx]
                    if self.logger:
                        self.logger.info('选择播放图书视频：%s (%s)', vb['title'], vb['file'])
                    self._start_video(vb['file'])
                    return

        elif self.state == self.S_VIDEO_PLAY:
            if self._vid_stop_rect and self._vid_stop_rect.collidepoint(pos):
                self._stop_video()

        elif self.state == self.S_GUIDE:
            if self._guide_return_rect and self._guide_return_rect.collidepoint(pos):
                if self.logger:
                    self.logger.info('从【智能导读】返回功能选择界面')
                self._stop_speaking()
                with self._lock:
                    was_recording = self.guide_recording
                    self.guide_recording = False
                    self.guide_processing = False
                if was_recording:
                    try:
                        self.recorder.stop_recording()
                    except:
                        pass
                self.state = self.S_MENU
                self.menu_enter_time = time.time()
                self.set_light('menu')
                return
            if self._ocr_btn and self._ocr_btn.collidepoint(pos):
                # 注意：ocr_recognize_async内部会获取self._lock，
                # 不能在with self._lock块内调用，否则死锁（threading.Lock不可重入）
                with self._lock:
                    processing = self.guide_processing
                if not processing:
                    if self.logger:
                        self.logger.info('点击OCR识别按钮')
                    self.ocr_recognize_async()
                return
            if self._voice_btn and self._voice_btn.collidepoint(pos):
                with self._lock:
                    if not self.guide_processing and not self.guide_recording:
                        self.guide_recording = True
                        self.guide_record_start_time = time.time()
                        self.set_light('recording')
                        if self.logger:
                            self.logger.info('开始按住说话录音')
                        try:
                            self.recorder.start_recording(device=None)
                        except:
                            pass
                return

    def handle_mouse_up(self, pos):
        if self.state == self.S_GUIDE:
            with self._lock:
                was_recording = self.guide_recording
                record_start = self.guide_record_start_time
            if was_recording:
                with self._lock:
                    self.guide_recording = False
                duration = time.time() - record_start if record_start else 0
                try:
                    audio_data = self.recorder.stop_recording()
                    if self.logger:
                        try:
                            dtype_str = str(audio_data.dtype) if hasattr(audio_data, 'dtype') else '?'
                            shape_str = str(audio_data.shape) if hasattr(audio_data, 'shape') else '?'
                            has_data = (audio_data is not None) and (
                                (hasattr(audio_data, '__len__') and len(audio_data) > 0)
                                or (hasattr(audio_data, 'size') and getattr(audio_data, 'size') > 0)
                            )
                            self.logger.info('录音结束, 返回类型=%s, dtype_shape=(%s, %s), has_data=%s',
                                             type(audio_data).__name__, dtype_str, shape_str, has_data)
                        except:
                            pass
                    # 1. 空/无效判断
                    if audio_data is None or duration < 0.3:
                        with self._lock:
                            self.guide_result = '录音时间太短，请按住按钮说话。'
                        self.set_light('guide')
                        return
                    # 2. 长度检查
                    try:
                        if isinstance(audio_data, np.ndarray):
                            audio_len = audio_data.size
                        elif hasattr(audio_data, '__len__'):
                            audio_len = len(audio_data)
                        else:
                            audio_len = 0
                    except:
                        audio_len = 0
                    if audio_len == 0:
                        with self._lock:
                            self.guide_result = '录音为空，请按住按钮说话。'
                        self.set_light('guide')
                        return
                    # 3. 先删旧文件
                    out_file = 'recordings/guide_voice.wav'
                    try:
                        if os.path.exists(out_file):
                            os.remove(out_file)
                    except:
                        pass
                    # 4. 用wave直接写出（不依赖save_audio返回值）
                    try:
                        if isinstance(audio_data, np.ndarray):
                            # 把float32 [-1,1] 转成16位PCM
                            arr = np.array(audio_data, dtype=np.float32)
                            if arr.ndim > 1:
                                arr = arr.reshape(-1)
                            n_ch = 1
                            sr = int(getattr(self.recorder, 'sample_rate', 16000))
                            # 限幅
                            np.clip(arr, -1.0, 1.0, out=arr)
                            pcm16 = (arr * 32767.0).astype(np.int16)
                            with wave.open(out_file, 'wb') as wf:
                                wf.setnchannels(n_ch)
                                wf.setsampwidth(2)
                                wf.setframerate(sr)
                                wf.writeframes(pcm16.tobytes())
                            if self.logger:
                                fsize = os.path.getsize(out_file)
                                self.logger.info(
                                    'numpy音频已用wave写出: %s (大小%d字节, %dHz, %dch, %d采样点)',
                                    out_file, fsize, sr, n_ch, len(pcm16))
                        else:
                            # 非numpy：先尝试save_audio，失败再return
                            saved_path = self.recorder.save_audio(audio_data, out_file)
                            if saved_path is None or not os.path.exists(out_file):
                                raise RuntimeError('AudioRecorder.save_audio 返回 None 或未写出文件')
                            if self.logger:
                                fsize = os.path.getsize(out_file)
                                self.logger.info('AudioRecorder.save_audio 写出: %s (%d字节)', out_file, fsize)
                    except Exception as save_e:
                        if self.logger:
                            self.logger.exception('写出wav失败: %s', save_e)
                        raise
                    # 5. 最终文件校验
                    if not os.path.exists(out_file) or os.path.getsize(out_file) < 100:
                        with self._lock:
                            self.guide_result = '录音保存失败，请重试。'
                        self.set_light('guide')
                        return
                    if self.logger:
                        self.logger.info('最终识别文件: %s', out_file)
                    self.voice_converse_async()
                except Exception as e:
                    if self.logger:
                        self.logger.exception('录音处理失败: %s', e)
                    with self._lock:
                        self.guide_result = f'录音处理失败: {e}'
                    self.set_light('guide')

    # ====== PIR传感器检查 ======
    def _start_pir_thread(self):
        """启动 PIR 后台轮询线程。
        主线程（含 update_state 和 draw_welcome）只读取缓存值 _pir_detected，
        不再直接调用 board.digitalRead，避免串口 I/O 阻塞主循环，
        同时与 LightManager 共享 _board_lock 串行化串口访问。
        """
        if self._pir_thread is not None and self._pir_thread.is_alive():
            return
        self._pir_thread_running = True
        self._pir_thread = threading.Thread(target=self._pir_loop, daemon=True)
        self._pir_thread.start()
        if self.logger:
            self.logger.info('PIR 后台轮询线程已启动')

    def _stop_pir_thread(self):
        self._pir_thread_running = False
        if self._pir_thread is not None:
            try:
                if self._pir_thread.is_alive():
                    self._pir_thread.join(timeout=1.0)
            except:
                pass
            self._pir_thread = None

    def _pir_loop(self):
        """后台轮询 PIR 引脚（每 0.2 秒一次），加 _board_lock 避免与 LED 写入冲突"""
        while self._pir_thread_running and self.running:
            try:
                if self.board is not None:
                    with self._board_lock:
                        val = self.board.digitalRead(PIR_PIN)
                    with self._pir_lock:
                        self._pir_detected = (val == 1)
            except Exception:
                # 串口偶发超时属正常，忽略本次，下次重试
                pass
            time.sleep(0.2)

    def check_pir(self):
        """主线程读取最近一次 PIR 检测结果（非阻塞，不访问串口）"""
        with self._pir_lock:
            return 1 if self._pir_detected else 0

    def update_state(self):
        # 视频自然播完 → 自动返回图书视频界面
        if self.state == self.S_VIDEO_PLAY and self.video_finished.is_set():
            if self.logger:
                self.logger.info('视频自然播完，自动返回图书视频界面')
            self._stop_video_internal(blocking=False)
            self.state = self.S_VIDEOS
            self.set_light('videos')
            return

        # 仅在欢迎屏幕检测 PIR，并播放欢迎语；其他界面不检测、不播放
        if self.state == self.S_WELCOME:
            pir = self.check_pir()
            if pir == 1:
                # 先在锁内检查并更新状态，speak_async 移到锁外调用
                # （speak_async 内部启动新线程获取 self._lock，不能在持锁时调用）
                with self._lock:
                    need_play = not self.welcome_played
                    if need_play:
                        self.welcome_played = True
                if need_play:
                    if self.logger:
                        self.logger.info('PIR检测到人，播放欢迎语')
                    self.speak_async('欢迎来到智慧阅读角，开始享受你的阅读时光吧',
                                     restore_mode='menu')
                    # 播放欢迎语的同时进入功能选择界面
                    self.state = self.S_MENU
                    self.menu_enter_time = time.time()
                    self.set_light('menu')
                    if self.logger:
                        self.logger.info('进入功能选择界面（由欢迎屏PIR触发）')

        elif self.state == self.S_MENU:
            pir = self.check_pir()
            if pir == 1:
                self.menu_enter_time = time.time()
            else:
                if time.time() - self.menu_enter_time > MENU_TIMEOUT:
                    if self.logger:
                        self.logger.info('功能选择界面超时无人，自动返回欢迎屏')
                    self.state = self.S_WELCOME
                    with self._lock:
                        self.welcome_played = False
                    self.set_light('welcome')

    # ====== 渲染 ======
    def render(self):
        if self.state == self.S_INIT:
            self.draw_init()
        elif self.state == self.S_WELCOME:
            self.draw_welcome()
        elif self.state == self.S_MENU:
            self.draw_menu()
        elif self.state == self.S_LIBRARY:
            self.draw_library()
        elif self.state == self.S_VIDEOS:
            self.draw_videos()
        elif self.state == self.S_VIDEO_PLAY:
            self.draw_video_play()
        elif self.state == self.S_GUIDE:
            self.draw_guide()
        pygame.display.flip()

    # ====== 清理 ======
    def cleanup(self):
        if self.logger:
            self.logger.info('正在清理资源...')

        # ---- 第一步：先标记 self.running=False，通知所有后台线程主动退出 ----
        # （主循环正常退出时 running 已经是 False，但防御式置位不影响）
        self.running = False

        try:
            self._stop_video_internal(blocking=True)
        except Exception as _e:
            if self.logger:
                self.logger.warning('停止视频异常: %s', _e)

        # ---- 关键：等待摄像头初始化后台线程结束（最多等5秒）----
        # 原因：如果用户在 open_camera() 阻塞期间退出，_camera_init_thread 还在跑；
        # 如果不等它结束就做 vision_system.cleanup，会出现：
        #   1) "摄像头采集线程已停止" → "摄像头打开失败" 这种日志顺序错乱
        #   2) vision_system 刚释放完 init_camera_open 又在另一个线程里用它
        if self._camera_init_thread is not None:
            try:
                if self._camera_init_thread.is_alive():
                    if self.logger:
                        self.logger.info('等待摄像头初始化线程结束...')
                    self._camera_init_thread.join(timeout=5.0)
            except Exception as _e:
                if self.logger:
                    self.logger.warning('等待摄像头初始化线程异常: %s', _e)
            finally:
                self._camera_init_thread = None

        try:
            self._stop_camera_thread()
        except Exception as _e:
            if self.logger:
                self.logger.warning('停止摄像头线程异常: %s', _e)
        try:
            self._stop_pir_thread()
        except Exception as _e:
            if self.logger:
                self.logger.warning('停止PIR线程异常: %s', _e)
        if self.lights:
            self.lights.stop()
        # 视觉系统清理：本项目未启动 threaded_system.start_background_detection
        # （只用 open_camera + capture_frame），因此 cleanup 不需要 stop_background_detection
        if self.vision_system:
            try:
                self.vision_system.cleanup()
                if self.logger:
                    self.logger.info('视觉系统资源已释放')
            except Exception as _e:
                if self.logger:
                    self.logger.warning('视觉系统清理异常: %s', _e)
        if self.ocr:
            try:
                self.ocr.cleanup()
            except Exception as _e:
                if self.logger:
                    self.logger.warning('OCR清理异常: %s', _e)
        if self.player:
            try:
                self.player.cleanup()
            except Exception as _e:
                if self.logger:
                    self.logger.warning('player清理异常: %s', _e)
        # 灯带关闭双重保护：仅在 _board_connected=True（start+ws2812Init都成功）且 board 对象
        # 具备 device 属性时才写入，避免扩展板未连接/连接失败场景触发 AttributeError
        if self._board_connected and self.board is not None and hasattr(self.board, 'device'):
            try:
                self.board.ws2812Write(RGB_PIN, 255, 0, 0, 0)
            except Exception as _e:
                if self.logger:
                    self.logger.warning('关闭RGB灯带异常: %s', _e)
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        # mixer 在 init_pygame 中初始化，退出时统一 quit
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        pygame.quit()
        if self.logger:
            self.logger.info('资源清理完成')
            self.logger.info('=' * 60)
            self.logger.info('智慧阅读角程序正常结束')
            self.logger.info('=' * 60)
            # 显式关闭并移除 logging handlers，确保日志 flush 到磁盘
            for h in list(self.logger.handlers):
                try:
                    h.flush()
                    h.close()
                except Exception:
                    pass
                self.logger.removeHandler(h)

    # ====== 主循环 ======
    def run(self):
        os.makedirs('recordings', exist_ok=True)
        self.init_pygame()

        # 校验用户名密码（未填就弹出提示并锁定，不运行其他功能）
        if not VOICE_USERNAME or not VOICE_PASSWORD or \
                VOICE_USERNAME in ('用户名', '', None) or VOICE_PASSWORD in ('密码', '', None):
            self.auth_ok = False
            if self.logger:
                self.logger.warning('VOICE_USERNAME/VOICE_PASSWORD 未填写，程序进入提示锁定模式')
            try:
                while self.running:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            self.running = False
                        elif event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1:
                                if self._exit_rect and self._exit_rect.collidepoint(event.pos):
                                    self.running = False
                    self.draw_auth_error()
                    pygame.display.flip()
                    self.clock.tick(20)
            finally:
                self.cleanup()
            return

        # ====== 主线程初始化（硬件/视觉/语音都很快；且ESP32使用signal必须在主线程）======
        self._init_stage = '正在连接硬件...'
        self.draw_init()
        pygame.display.flip()
        pygame.event.pump()

        try:
            self.init_hardware()
            self._init_stage = '正在初始化视觉系统...'
            self.draw_init()
            pygame.display.flip()
            pygame.event.pump()
            self.init_vision_system()
            self._init_stage = '正在初始化语音AI...'
            self.draw_init()
            pygame.display.flip()
            pygame.event.pump()
            self.init_voice()
        except Exception as e:
            self._init_error = str(e)
            if self.logger:
                self.logger.error('主线程初始化异常: %s', e)

        # ====== 摄像头初始化放后台线程（最慢，不阻塞主循环，PIR可立即工作）======
        self._camera_initializing = True
        self._camera_init_thread = threading.Thread(target=self._init_camera_background, daemon=True)
        self._camera_init_thread.start()

        self.set_light('welcome')
        self.state = self.S_WELCOME
        if self.logger:
            self.logger.info('进入欢迎屏（摄像头正在后台启动）')

        # 主循环
        try:
            while self.running:
                self.handle_events()
                if not self.running:
                    break
                self.update_state()
                self.render()
                self.clock.tick(30)
        except KeyboardInterrupt:
            if self.logger:
                self.logger.info('用户按Ctrl+C中断程序')
        except Exception as e:
            if self.logger:
                self.logger.exception('主循环发生异常: %s', e)
            else:
                import traceback
                traceback.print_exc()
        finally:
            self.cleanup()

    def _init_camera_background(self):
        """后台初始化摄像头（最慢的步骤，放后台不阻塞主循环和PIR检测）

        注意：用户可能在摄像头初始化过程中退出程序（self.running=False），
        必须在每个关键节点检查 self.running，避免：
        1. 用户已退出但 open_camera() 还在阻塞，cleanup 结束后才打印"打开失败"
        2. open_camera() 刚成功，正要启动采集线程，但 cleanup 已释放 vision_system
        """
        try:
            # 入口检查：用户已经退出，直接跳过
            if not self.running:
                return
            self._init_stage = '正在启动摄像头...'
            # 再次检查 running：open_camera() 可能阻塞几秒，
            # 如果用户在这期间退出（running 变 False），init_camera_open 内部也会提前返回
            if self.running:
                self.init_camera_open()
        except Exception as e:
            if self.logger and self.running:
                self.logger.error('摄像头后台初始化异常: %s', e)
        finally:
            self._camera_initializing = False
            if self.logger:
                if self.running:
                    self.logger.info('摄像头后台初始化流程结束 (camera_ok=%s)', self.camera_ok)
                else:
                    # 用户已退出：不要打印"camera_ok=False"的误导性日志
                    # （摄像头初始化被用户打断，不是真的打开失败）
                    self.logger.info('摄像头后台初始化流程已中止（用户退出）(camera_ok=%s)', self.camera_ok)


# ==================== 入口 ====================
if __name__ == '__main__':
    app = SmartReadingApp()
    app.run()
