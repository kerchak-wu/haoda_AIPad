# -*- coding: utf-8 -*-
"""
物体识别播报程序 - 好搭AI派
==========================
功能说明：
  1. USB外接摄像头实时采集画面（由视觉系统 open_camera + capture_frame 管理）
  2. 点击「播报」按钮，识别当前画面中的物体并语音播报
     - 识别到已学习物体 → 播报"这是{物体名称}"
     - 未识别到 / 未学习过的物体 → 播报"物体未学习"
  3. 语音合成使用 VoiceAPI（与唐诗宋词朗读器相同的语音 AI）
  4. 界面显示摄像头画面、识别结果、置信度和已学习物体列表
  5. 语音音频缓存到 recordings/ 目录，重复播报无需再次合成

硬件接线：
  - USB外接摄像头(/dev/video41 或 /dev/video40)
  - 好搭AI派扩展板(ESP32)
  注意：好搭AI派右下角开关需拨到左侧以启用外设接口。

依赖库：
  pygame, cv2(opencv, 仅用于图像格式转换), numpy, ESP32,
  camera_vision_system_v3(好搭AI派自带),
  audio_player, voice_api(好搭AI派自带)

参考范例：
  - 范例代码 5.12 物体识别（result_accessor 获取结果）
  - 范例代码 4.语音AI 1.语音合成（VoiceAPI + tts_synthesize）
  - 范例代码 3.音频处理 2.音频播放（AudioPlayer）
  - 唐诗宋词朗读器.py（语音合成与播放流程）
  - 人脸识别灯效.py（视觉系统 open_camera + capture_frame + 后台检测线程模式）
  - 物体学习.py（object_records.json 格式）

重要约束：
  - 物体识别必须 open_camera + start_background_detection，
    由 result_accessor.refresh_results() 轮询识别结果。
  - 不使用 cv2 VideoCapture，必须用 vision_system.capture_frame() 获取帧
    用于界面显示，避免与视觉系统的 V4L2 设备冲突。
  - 采集线程 0.05s 睡眠（≈20fps），frame_lock 保护 raw_frame 读写。
"""

import os
import json
import time
import threading
import sys

# Rockchip 平台兼容性补丁：强制 libGL 软件渲染，避免 Mali GPU 驱动加载失败
# 必须在 import pygame 之前设置
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

import pygame
import cv2
import numpy as np

from ESP32 import *
from camera_vision_system_v3 import create_vision_system_v3
from audio_player import AudioPlayer
from voice_api import VoiceAPI


# ===================== 日志输出（控制台 + 文件）=====================
# 把所有 print 输出同时写入 logs/ 目录下的日志文件，方便在好搭AI派上导出排查
# 注意：
#   1. 日志统一存到 logs/ 文件夹，避免散落在项目根目录
#   2. 文件名含程序名+日期，不会覆盖上次的日志
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
    '物体识别播报_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
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

# 摄像头配置（视觉系统内部使用）
CAMERA_W, CAMERA_H = 1280, 720
CAM_DISP_W, CAM_DISP_H = 880, 660

# 物体记录文件（由 物体学习.py 生成，与 V3 SDK 的 object_database/ 目录统一管理）
OBJECT_DATA_DIR = 'object_database'
_os.makedirs(OBJECT_DATA_DIR, exist_ok=True)
OBJECT_DATA_FILE = _os.path.join(OBJECT_DATA_DIR, 'object_records.json')

# ===================== 物体名称英文/拼音 → 中文映射 =====================
# 好搭AI派不支持中文输入，物体学习时只能用英文/拼音命名；
# 此映射表用于播报时将英文/拼音名转换为汉语普通话进行 TTS 合成。
# 用户可在下方自行补充映射（key 用小写，查找时自动转小写匹配）。
OBJECT_NAME_CN_MAP = {
    # 拼音 → 中文
    'shuibei':   '水杯',
    'shouji':    '手机',
    'diannao':   '电脑',
    'shuben':    '书本',
    'shu':       '书',
    'bijiben':   '笔记本',
    'maozi':     '帽子',
    'xiezi':     '鞋子',
    'yizi':      '椅子',
    'zhuozi':    '桌子',
    'lifangti':  '立方体',
    'qiuchi':    '球',
    'qiu':       '球',
    'pingguo':   '苹果',
    'xiangjiao': '香蕉',
    'juzi':      '橘子',
    'beizi':     '杯子',
    'hezi':      '盒子',
    'yuekongqi': '遥控器',
    'jianpan':   '键盘',
    'shubiao':   '鼠标',
    'chabei':    '茶杯',
    'heiping':   '黑屏',
    'pingmu':    '屏幕',
    'shoubiao':  '手表',
    'naozhong':  '闹钟',
    'taiqi':     '台旗',
    'dengpao':   '灯泡',
    'chezhang':  '车模',
    'wanju':     '玩具',
    'zhi':       '纸',
    'zhixiang':  '纸箱',
    'suliao':    '塑料',
    'pizi':      '瓶子',
    'pingzi':    '瓶子',
    'kuangzi':   '框子',
    'mokua':     '模块',
    'shexiangtou': '摄像头',
    'dianchi':   '电池',
    'chongdianbao': '充电宝',
    # 英文 → 中文
    'cup':     '水杯',
    'glass':   '玻璃杯',
    'bottle':  '瓶子',
    'book':    '书本',
    'phone':   '手机',
    'mouse':   '鼠标',
    'keyboard':'键盘',
    'monitor': '显示器',
    'pen':     '钢笔',
    'pencil':  '铅笔',
    'box':     '盒子',
    'cube':    '立方体',
    'ball':    '球',
    'apple':   '苹果',
    'banana':  '香蕉',
    'orange':  '橙子',
    'chair':   '椅子',
    'table':   '桌子',
    'desk':    '书桌',
    'hat':     '帽子',
    'shoe':    '鞋子',
    'clock':   '时钟',
    'watch':   '手表',
    'lamp':    '台灯',
    'bulb':    '灯泡',
    'car':     '玩具车',
    'toy':     '玩具',
    'card':    '卡片',
    'key':     '钥匙',
    'remote':  '遥控器',
    'scissors':'剪刀',
    'ruler':   '尺子',
    'eraser':  '橡皮',
    'stapler': '订书机',
    'fan':     '风扇',
    'plug':    '插头',
    'cable':   '数据线',
    'charger': '充电器',
}


def to_chinese(name):
    """将英文/拼音物体名转换为中文名用于播报

    查找策略：
      1. 优先精确匹配（不区分大小写）
      2. 未找到时原样返回（TTS 也能朗读英文，只是按字母/单词发音）
    """
    if not name:
        return name
    key = name.strip().lower()
    return OBJECT_NAME_CN_MAP.get(key, name)

# 语音音频缓存目录
AUDIO_CACHE_DIR = 'recordings'

# 语音 AI 认证 —— 请替换为自己经过认证的好好搭搭账号
VOICE_USERNAME = 'username'
VOICE_PASSWORD = 'password'

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
PLAY_COLOR = (60, 180, 80)      # 播报按钮绿色
PLAY_HOVER = (80, 200, 100)
DISABLED_COLOR = (160, 160, 170)


# ===================== 硬件初始化 =====================
# 严格参照范例代码：ESP32 初始化 + 异常处理
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")


# ===================== 语音 AI 认证（参照唐诗宋词朗读器）=====================
# 确保音频缓存目录存在
if not os.path.exists(AUDIO_CACHE_DIR):
    try:
        os.makedirs(AUDIO_CACHE_DIR)
    except Exception as e:
        print('创建音频缓存目录失败:', e)

player = AudioPlayer()
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token(VOICE_USERNAME, VOICE_PASSWORD)
if not token_result:
    print('语音 AI 认证失败，请检查账号密码（VOICE_USERNAME / VOICE_PASSWORD）')
else:
    print('语音 AI 认证成功')


# ===================== 已学习物体记录加载 =====================
def load_learned_objects():
    """从 object_records.json 加载已学习的物体名称列表（由 物体学习.py 生成）"""
    try:
        with open(OBJECT_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        names = [item['name'] for item in data]
        print('已加载 %d 个已学习物体类别' % len(names))
        return names
    except FileNotFoundError:
        print('无物体记录文件，请先运行 物体学习.py 学习物体')
        return []
    except Exception as e:
        print('加载物体记录失败:', e)
        return []


learned_object_names = load_learned_objects()


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
            c = DISABLED_COLOR
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


# ===================== 物体识别播报应用 =====================
class ObjectRecognizeApp:
    """物体识别播报 Pygame 界面应用

    摄像头完全由视觉系统管理（open_camera + capture_frame），
    不使用 cv2 VideoCapture，避免设备冲突。
    识别流程严格参照范例代码 5.12。
    语音合成流程严格参照唐诗宋词朗读器。
    """

    TITLE_H = 130
    FOOTER_H = 110

    def __init__(self):
        # Rockchip 平台兼容性补丁：分段初始化（不调用 pygame.init()）
        # 保留 mixer 用于 TTS 音频播放，跳过 joystick/CDROM 等不必要模块
        pygame.display.init()
        pygame.font.init()
        pygame.mixer.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('物体识别播报')
        self.clock = pygame.time.Clock()

        # 字体（适配 1920×1080：标题64、副标题32、列表项30、按钮34）
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 64)
        self.font_sub = pygame.font.Font(FONT_PATH, 32)
        self.font_item = pygame.font.Font(FONT_PATH, 30)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_small = pygame.font.Font(FONT_PATH, 24)
        self.font_status = pygame.font.Font(FONT_PATH, 26)
        self.font_result = pygame.font.Font(FONT_BOLD_PATH, 44)
        self.font_conf = pygame.font.Font(FONT_PATH, 28)

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

        # 播报按钮（右侧面板顶部，大按钮方便点击）
        self.btn_play = Button((ix, self.info_rect.y + 70, iw, 90),
                               '🔊  播报识别结果', PLAY_COLOR, PLAY_HOVER)

        # 退出按钮（右上角标题栏内，固定 240×70）
        self.btn_exit = Button((WIDTH - 280, 30, 240, 70),
                               '退出程序', EXIT_COLOR, EXIT_HOVER)

        # 初始化视觉系统（识别流程）
        print('正在初始化物体识别系统...')
        self._init_vision_system()

        # 状态
        self.running = True
        self.raw_frame = None
        self.frame_lock = threading.Lock()
        self.capture_running = True

        # 识别结果
        self.last_class_name = None
        self.last_confidence = 0.0
        self.last_recognized = False  # 上次是否识别到已学习物体

        # 播报状态
        self.is_speaking = False
        self.status_msg = '请对准物体后点击「播报识别结果」'
        self.status_color = SUBTLE_COLOR

        # 启动后台采集线程
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _init_vision_system(self):
        """创建并初始化视觉系统（严格参照范例代码 5.12）

        流程：create_vision_system_v3 → 启用 object_recognition → _init_detectors
              → open_camera → start_background_detection(show_preview=False)
        """
        self.vision_system = create_vision_system_v3(
            camera_id=-1, width=CAMERA_W, height=CAMERA_H,
            enable_basic=False, enable_advanced=False
        )
        self.vision_system.detection_config.enable_object_recognition = True
        self.vision_system._init_detectors()
        print('object_recognition 算法已启用')

        # 打开摄像头（严格参照范例 5.12）
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

    def _capture_loop(self):
        """后台采集线程：调用 capture_frame() 获取帧用于界面显示

        关键改进（参考人脸识别灯效.py 已验证模式）：
        1. 0.05s 睡眠 ≈ 20fps 采集，保证画面流畅
        2. 帧有效性验证，跳过损坏帧
        3. capture_frame() 只读缓存，不访问 V4L2，与后台检测线程不冲突
        """
        # 启动后等待 0.5s 让后台检测线程先稳定
        time.sleep(0.5)
        while self.capture_running:
            if not self.camera_ok:
                time.sleep(0.3)
                continue
            try:
                frame = self.vision_system.capture_frame()
                if frame is not None and hasattr(frame, 'shape') and len(frame.shape) == 3:
                    with self.frame_lock:
                        self.raw_frame = frame
            except Exception as e:
                if self.capture_running:
                    print('采集帧异常:', e)
            # 0.05s 睡眠 ≈ 20fps 采集，capture_frame() 只读缓存不访问 V4L2，与后台检测线程不冲突
            time.sleep(0.05)

    def get_current_frame(self):
        """获取当前摄像头帧的副本（线程安全）"""
        with self.frame_lock:
            return self.raw_frame.copy() if self.raw_frame is not None else None

    def set_status(self, msg, color=SUBTLE_COLOR):
        self.status_msg = msg
        self.status_color = color

    # ===================== 识别与播报 =====================
    def recognize_current(self):
        """识别当前画面中的物体（严格参照范例代码 5.12 + API 分析报告 5.9）

        范例 5.12 的调用方式：
            result_accessor.refresh_results()
            class_name = result_accessor.get_object_recognition_class_name()
            confidence = result_accessor.get_object_recognition_confidence()

        本程序在范例基础上增加 success 判断（API 报告 5.9 提供）：
            success = result_accessor.get_object_recognition_success()
        success 为 True 才表示成功匹配到已学习物体，比单纯判断 class_name 更可靠。

        注意：CompleteDetectionResultAccessor 没有 get_object_recognition_count 方法，
        api-reference.md 中的 count 调用是错误的，以范例代码为准。

        Returns:
            (class_name, confidence, recognized):
                recognized=True  → 识别到已学习物体，class_name 为名称
                recognized=False → 未识别到 / 未学习，class_name 可能 None
        """
        try:
            self.vision_system.result_accessor.refresh_results()
            # 严格参照范例 5.12 + API 报告 5.9：
            # 用 success 判断是否成功匹配，再读 class_name/confidence
            success = self.vision_system.result_accessor.get_object_recognition_success()
            class_name = self.vision_system.result_accessor.get_object_recognition_class_name()
            confidence = self.vision_system.result_accessor.get_object_recognition_confidence()
            try:
                confidence = round(float(confidence), 3)
            except Exception:
                confidence = 0.0

            # success=False 或 class_name 无效 → 未识别到物体
            if not success or not class_name or class_name in ('None', '未知', 'unknown', ''):
                return None, confidence, False

            # 校验是否为已学习的物体（双重确认，避免视觉系统返回其他类别）
            if learned_object_names and class_name not in learned_object_names:
                print('[识别] 视觉系统返回类别 [%s] 不在已学习列表中' % class_name)
                return class_name, confidence, False

            return class_name, confidence, True
        except Exception as e:
            print('识别异常:', e)
            return None, 0.0, False

    def handle_play(self):
        """处理播报按钮点击"""
        if self.is_speaking:
            return
        if not self.camera_ok:
            self.set_status('摄像头未就绪，无法识别', ERROR_COLOR)
            return

        self.set_status('正在识别...', ACCENT_COLOR)
        class_name, confidence, recognized = self.recognize_current()

        # 保存识别结果用于界面显示
        self.last_class_name = class_name
        self.last_confidence = confidence
        self.last_recognized = recognized

        if recognized:
            # 用中文播报：英文/拼音名 → 中文（未映射则原样朗读）
            cn_name = to_chinese(class_name)
            text = '这是%s' % cn_name
            if cn_name != class_name:
                self.set_status('识别到：%s → %s（置信度 %s）' % (
                    class_name, cn_name, confidence), SUCCESS_COLOR)
                print('[播报] %s -> %s（置信度 %s）' % (class_name, cn_name, confidence))
            else:
                self.set_status('识别到：%s（置信度 %s）' % (class_name, confidence),
                                SUCCESS_COLOR)
                print('[播报] %s（置信度 %s）' % (class_name, confidence))
        else:
            text = '物体未学习'
            if class_name:
                self.set_status('未学习物体（检测到 %s，置信度 %s）' % (class_name, confidence),
                                ACCENT_COLOR)
            else:
                self.set_status('未识别到物体', ACCENT_COLOR)
            print('[播报] 物体未学习')

        # 异步合成并播放语音（避免阻塞主循环）
        threading.Thread(target=self._speak_async, args=(text,), daemon=True).start()

    def _speak_async(self, text):
        """异步语音合成与播放（参照唐诗宋词朗读器）

        1. 音频缓存：相同文本只合成一次，后续直接播放
        2. TTS 合成到文件，再用 pygame.mixer 播放
        """
        self.is_speaking = True
        try:
            # 缓存路径：用文本的哈希作为文件名，避免特殊字符问题
            safe_name = str(abs(hash(text))) + '.wav'
            audio_path = os.path.join(AUDIO_CACHE_DIR, safe_name)

            if not os.path.exists(audio_path):
                print('[语音] 正在合成: %s' % text)
                audio_data = voice_api.tts_synthesize(text, audio_path)
                if not audio_data:
                    print('[语音] 合成失败: %s' % text)
                    self.set_status('语音合成失败', ERROR_COLOR)
                    return
                print('[语音] 合成完成: %s' % audio_path)
            else:
                print('[语音] 使用缓存: %s' % audio_path)

            # 播放（参照唐诗宋词朗读器的 pygame.mixer 模式）
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.set_volume(0.9)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        except Exception as e:
            print('[语音] 播放异常:', e)
            self.set_status('语音播放异常', ERROR_COLOR)
        finally:
            self.is_speaking = False

    # ===================== 绘制 =====================
    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('物体识别播报', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 25))
        sub = self.font_sub.render(
            'USB摄像头实时识别  ·  点击播报按钮语音播报  ·  已学习物体播报"这是…"',
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

        status = '● 已连接' if self.camera_ok else '○ 未连接'
        sc = SUCCESS_COLOR if self.camera_ok else ERROR_COLOR
        st = self.font_small.render(status, True, sc)
        self.screen.blit(st, (self.cam_rect.right - st.get_width() - 20,
                              self.cam_rect.y + 20))

        frame = self.get_current_frame()
        if frame is not None:
            surf = cvframe_to_surface(frame, CAM_DISP_W, CAM_DISP_H)
            if surf is not None:
                cam_x = self.cam_rect.x + (self.cam_rect.w - CAM_DISP_W) // 2
                cam_y = self.cam_rect.y + 60
                self.screen.blit(surf, (cam_x, cam_y))
        else:
            hint_text = '摄像头未连接' if not self.camera_ok else '等待画面...'
            hint_color = ERROR_COLOR if not self.camera_ok else SUBTLE_COLOR
            hint = self.font_sub.render(hint_text, True, hint_color)
            self.screen.blit(hint, (self.cam_rect.centerx - hint.get_width() // 2,
                                    self.cam_rect.centery - hint.get_height() // 2))

        res = self.font_small.render('%d × %d' % (CAMERA_W, CAMERA_H), True, SUBTLE_COLOR)
        self.screen.blit(res, (self.cam_rect.right - res.get_width() - 20,
                               self.cam_rect.bottom - 30))

    def draw_info_panel(self):
        """绘制右侧信息面板：播报按钮 + 识别结果 + 已学习列表"""
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 30
        x_end = self.info_rect.right - 30
        y = self.info_rect.y + 20

        # ---- 播报按钮标题 ----
        head = self.font_sub.render('语音播报', True, TITLE_COLOR)
        self.screen.blit(head, (x, y))

        # 播报按钮
        self.btn_play.enabled = (not self.is_speaking) and self.camera_ok
        self.btn_play.draw(self.screen, self.font_btn)

        # ---- 状态消息 ----
        y = self.btn_play.rect.bottom + 20
        status_surf = self.font_status.render(self.status_msg, True, self.status_color)
        max_w = x_end - x
        if status_surf.get_width() > max_w:
            status_surf = self.font_small.render(self.status_msg, True, self.status_color)
        self.screen.blit(status_surf, (x, y))

        # ---- 识别结果展示 ----
        y += 45
        head2 = self.font_sub.render('识别结果', True, TITLE_COLOR)
        self.screen.blit(head2, (x, y))
        y += 45

        if self.last_class_name is None and not self.last_recognized:
            # 未识别
            if self.last_class_name is None and self.status_msg.startswith('未识别'):
                result_text = '未识别到物体'
                result_color = SUBTLE_COLOR
            else:
                result_text = '等待识别...'
                result_color = SUBTLE_COLOR
        elif self.last_recognized:
            # 显示中文名（下方标注英文/拼音标识）
            cn = to_chinese(self.last_class_name)
            result_text = '这是 %s' % cn
            result_color = SUCCESS_COLOR
        else:
            result_text = '物体未学习'
            result_color = ACCENT_COLOR

        result_surf = self.font_result.render(result_text, True, result_color)
        self.screen.blit(result_surf, (x, y))
        y += 55

        # 英文/拼音标识（识别到且映射成功时显示）
        if self.last_recognized:
            cn = to_chinese(self.last_class_name)
            if cn != self.last_class_name:
                tag_text = '标识：%s' % self.last_class_name
                tag_surf = self.font_conf.render(tag_text, True, SUBTLE_COLOR)
                self.screen.blit(tag_surf, (x, y))
                y += 35

        # 置信度
        if self.last_class_name is not None:
            conf_text = '置信度：%s' % self.last_confidence
            conf_surf = self.font_conf.render(conf_text, True, ACCENT_COLOR)
            self.screen.blit(conf_surf, (x, y))

        # 分隔线
        y += 50
        pygame.draw.line(self.screen, PANEL_BORDER,
                         (x, y), (x_end, y), 2)
        y += 25

        # ---- 已学习物体列表 ----
        head3 = self.font_sub.render('已学习物体（%d 个类别）' % len(learned_object_names),
                                     True, TITLE_COLOR)
        self.screen.blit(head3, (x, y))
        y += 45

        list_bottom = self.info_rect.bottom - 20
        if not learned_object_names:
            hint = self.font_item.render('暂无学习记录，请先运行 物体学习.py', True, SUBTLE_COLOR)
            self.screen.blit(hint, (x, y))
        else:
            for i, name in enumerate(learned_object_names):
                if y + 40 > list_bottom:
                    more = self.font_small.render(
                        '...共 %d 个类别' % len(learned_object_names), True, SUBTLE_COLOR)
                    self.screen.blit(more, (x, y))
                    break

                num = self.font_small.render('%d.' % (i + 1), True, SUBTLE_COLOR)
                self.screen.blit(num, (x, y + 5))

                # 高亮当前识别到的物体
                is_match = (self.last_recognized and name == self.last_class_name)
                name_color = SUCCESS_COLOR if is_match else TEXT_COLOR
                name_surf = self.font_item.render(name, True, name_color)
                self.screen.blit(name_surf, (x + 40, y))

                # 中文名对照（映射成功时显示）
                cn = to_chinese(name)
                if cn != name:
                    cn_surf = self.font_small.render('→ %s' % cn, True, SUBTLE_COLOR)
                    self.screen.blit(cn_surf, (x + 40 + name_surf.get_width() + 15, y + 8))

                if is_match:
                    tag_x = x + 40 + name_surf.get_width() + 15
                    if cn != name:
                        # 已占用位置显示中文名，当前识别标记放下一行
                        tag_x = x + 40 + name_surf.get_width() + 15 + \
                                self.font_small.size('→ %s' % cn)[0] + 15
                    tag = self.font_small.render('← 当前', True, SUCCESS_COLOR)
                    self.screen.blit(tag, (tag_x, y + 8))

                y += 40

    def draw_footer(self):
        """绘制底部栏"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        hint = self.font_small.render(
            'ESC 退出  ·  点击「播报识别结果」或按空格键识别并播报  ·  语音首次合成较慢，之后使用缓存',
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
                    elif self.btn_play.clicked(event.pos):
                        self.handle_play()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_SPACE:
                        self.handle_play()

            self.btn_play.update(mouse_pos)
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
        self.capture_running = False
        time.sleep(0.2)
        try:
            self.vision_system.cleanup()
        except Exception:
            pass
        pygame.quit()
        try:
            _debug_log_fp.close()
        except Exception:
            pass


# ===================== 入口 =====================
if __name__ == '__main__':
    app = ObjectRecognizeApp()
    app.run()
