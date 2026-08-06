# -*- coding: utf-8 -*-
"""
人脸表情识别程序 - 好搭AI派
============================
功能说明：
  1. USB外接摄像头实时采集画面（cv2 VideoCapture）
  2. 后台线程定期调用百度智能云人脸识别 API，识别画面中人脸的情绪
  3. 界面显示摄像头画面、当前主情绪、人脸数量、概率与历史统计
  4. 情绪类型（百度 emotion 字段，七种基本情绪）：
     angry(愤怒) disgust(厌恶) fear(恐惧)
     happy(高兴) sad(悲伤) surprise(惊讶) neutral(中性)

硬件接线：
  - USB外接摄像头(/dev/video41 或 /dev/video40)
  - 好搭AI派扩展板(ESP32)
  注意：好搭AI派右下角开关需拨到左侧以启用外设接口。

依赖库：
  pygame, cv2(opencv), numpy, baidu-aip, ESP32

参考范例：
  - 范例代码 7.opencv（cv2 VideoCapture 用法）
  - 人脸学习.py（摄像头探测 / 后台采集线程 / Pygame 界面布局）
  - 手势控制RGB灯带.py（摄像头探测逻辑）

百度智能云配置：
  APP_ID / API_KEY / SECRET_KEY 在下方配置区填写。
  使用 AipFace.detect(image, 'BASE64', {face_field:'emotion'}) 识别情绪。
"""

import os
import sys
import time
import signal
import base64
import threading

import pygame
import cv2
import numpy as np

from aip import AipFace
from ESP32 import *


# ===================== 日志输出（控制台 + 文件）=====================
# 把所有 print 输出同时写入 logs/ 目录下的日志文件，方便在好搭AI派上导出排查
# 注意：
#   1. 日志统一存到 logs/ 文件夹，避免散落在项目根目录
#   2. 文件名含程序名+日期时间，不会覆盖上次的日志
#   3. 用追加模式 'a'，同一程序多次运行追加到当天日志
#   4. 用块缓冲(buffering=-1)而非行缓冲，避免识别线程高频写日志阻塞主循环
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
    '人脸表情识别_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
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
# 百度智能云凭证：请在此处填写您自己的 APP_ID / API_KEY / SECRET_KEY
# 申请地址：https://console.bce.baidu.com/ai/#/ai/face/index
APP_ID = '在此填写 APP_ID'
API_KEY = '在此填写 API_KEY'
SECRET_KEY = '在此填写 SECRET_KEY'

WIDTH, HEIGHT = 1920, 1080

# 字体路径（好搭AI派系统字体）
FONT_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'

# 摄像头配置
CAMERA_W, CAMERA_H = 640, 480
CAM_DISP_W, CAM_DISP_H = 880, 660

# 百度 API 调用间隔（秒）：默认 QPS 限制为 2，间隔 1.5s 比较安全
API_INTERVAL = 1.5

# 表情类型映射（百度返回 type -> 中文 + 颜色）
EXPRESSION_NAMES = {
    'angry':    '愤怒',
    'disgust':  '厌恶',
    'fear':     '恐惧',
    'happy':    '高兴',
    'sad':      '悲伤',
    'surprise': '惊讶',
    'neutral':  '中性',
}
EXPRESSION_COLORS = {
    'angry':    (220, 60, 60),    # 红
    'disgust':  (120, 80, 40),    # 棕绿
    'fear':     (140, 80, 180),   # 紫
    'happy':    (255, 200, 50),   # 金黄
    'sad':      (70, 130, 220),   # 蓝
    'surprise': (255, 140, 0),    # 橙
    'neutral':  (120, 130, 150),  # 灰蓝
    'unknown':  (160, 160, 160),
}

# 表情符号（用于大字显示装饰）
EXPRESSION_EMOJI = {
    'angry':    '눈_눈',
    'disgust':  '×_×',
    'fear':     '(°△°)',
    'happy':    '◕‿◕',
    'sad':      '(╥_╥)',
    'surprise': '(O_O)!',
    'neutral':  '•́ ₒ •̀',
    'unknown':  '?_?',
}

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
DETECT_COLOR = (60, 130, 255)
DETECT_HOVER = (80, 150, 255)


# ===================== 硬件初始化 =====================
# 严格参照范例代码：ESP32 初始化 + 异常处理
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        print('ESP32 扩展板初始化完成')
    except Exception as e:
        print('扩展板异常:', e)


# ===================== 百度智能云客户端 =====================
face_client = AipFace(APP_ID, API_KEY, SECRET_KEY)
print('百度智能云 AipFace 客户端已创建')


# ===================== 摄像头打开 =====================
# 参考人脸学习.py / 手势控制RGB灯带.py 的摄像头探测逻辑：MJPG + 超时 + 雪花检测
class _CameraProbeTimeout(Exception):
    """探测摄像头时 SIGALRM 超时"""
    pass


def _is_valid_frame(frame):
    """判断帧是否为有效画面（非空、非全黑、非雪花噪声）"""
    if frame is None or frame.size == 0:
        return False
    try:
        std_orig = float(frame.std())
        if std_orig < 5:
            return False
        small = cv2.resize(frame, (32, 32), interpolation=cv2.INTER_AREA)
        std_small = float(small.std())
        if std_orig > 20 and std_small / std_orig < 0.2:
            return False
        return True
    except Exception:
        return False


def _try_open_camera(cid, timeout=4):
    cap = None
    use_alarm = (hasattr(signal, "SIGALRM")
                 and threading.current_thread() is threading.main_thread())
    old_handler = None
    if use_alarm:
        def _alarm(signum, frame):
            raise _CameraProbeTimeout()
        old_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(timeout)
    try:
        device_path = "/dev/video{}".format(cid)
        cap = cv2.VideoCapture(device_path)
        if cap is None or not cap.isOpened():
            return None
        try:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        except Exception:
            pass
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_H)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for _ in range(20):
            ok, frame = cap.read()
            if ok and _is_valid_frame(frame):
                return cap
        try:
            cap.release()
        except Exception:
            pass
        return None
    except _CameraProbeTimeout:
        print("  /dev/video{} 探测超时，跳过".format(cid))
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        return None
    finally:
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


def open_camera():
    """打开USB外接摄像头，固定探测 /dev/video41 和 /dev/video40"""
    for cid in (41, 40):
        print("  探测 /dev/video{} ...".format(cid))
        cap = _try_open_camera(cid)
        if cap is not None:
            print("摄像头使用编号：{} (/dev/video{})".format(cid, cid))
            return cap
    return None


# ===================== 表情识别器 =====================
class ExpressionDetector:
    """封装百度智能云人脸情绪识别调用（线程安全）

    调用流程：cv2 帧 -> base64 -> AipFace.detect(image,'BASE64',{face_field:'emotion'})
    返回示例：
        {'face_num':1, 'face_list':[{'emotion':{'type':'happy','probability':0.97}}]}

    emotion 字段支持七种基本情绪（基于 FACS 面部动作编码系统）：
        angry(愤怒) disgust(厌恶) fear(恐惧)
        happy(高兴) sad(悲伤) surprise(惊讶) neutral(中性)
    """

    def __init__(self, client):
        self.client = client
        self._lock = threading.Lock()
        # 最近一次识别结果（解析后）
        self.last_result = None
        self.last_error = None
        self.last_call_time = 0.0
        self.call_count = 0
        # 历史统计：每次成功调用统计一次主情绪
        self.stats = {
            'angry': 0, 'disgust': 0, 'fear': 0,
            'happy': 0, 'sad': 0, 'surprise': 0, 'neutral': 0,
            'no_face': 0, 'error': 0,
        }

    def detect(self, frame):
        """识别一帧的人脸情绪，返回解析结果 dict 或 None"""
        if frame is None:
            return None
        try:
            # BGR -> jpg -> base64
            ok, encoded = cv2.imencode('.jpg', frame,
                                       [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                with self._lock:
                    self.last_error = '图像编码失败'
                    self.stats['error'] += 1
                return None
            image_base64 = base64.b64encode(encoded).decode()

            options = {
                'face_field': 'emotion',
                'max_face_num': 5,
            }
            result = self.client.detect(image_base64, 'BASE64', options)

            with self._lock:
                self.call_count += 1
                self.last_call_time = time.time()

                if not isinstance(result, dict):
                    self.last_error = '返回格式异常'
                    self.stats['error'] += 1
                    self.last_result = None
                    return None

                if result.get('error_code', -1) != 0:
                    self.last_error = '{}:{}'.format(
                        result.get('error_code'), result.get('error_msg', '未知错误'))
                    self.stats['error'] += 1
                    self.last_result = None
                    return None

                # 解析成功
                self.last_error = None
                r = result.get('result') or {}
                face_num = r.get('face_num', 0)
                face_list = r.get('face_list') or []

                expressions = []
                for f in face_list:
                    e = f.get('emotion') or {}
                    expressions.append({
                        'type': e.get('type', 'unknown'),
                        'probability': float(e.get('probability', 0.0)),
                    })

                # 统计主情绪（取第一张人脸的情绪）
                if face_num == 0:
                    self.stats['no_face'] += 1
                else:
                    main = expressions[0]['type'] if expressions else 'unknown'
                    if main in self.stats:
                        self.stats[main] += 1
                    else:
                        self.stats['error'] += 1

                self.last_result = {
                    'face_num': face_num,
                    'expressions': expressions,
                }
                return dict(self.last_result)
        except Exception as e:
            with self._lock:
                self.last_error = str(e)
                self.stats['error'] += 1
                self.last_result = None
            return None

    def get_state(self):
        """获取当前状态快照（线程安全）"""
        with self._lock:
            return {
                'result': dict(self.last_result) if self.last_result else None,
                'error': self.last_error,
                'call_count': self.call_count,
                'last_call_time': self.last_call_time,
                'stats': dict(self.stats),
            }


# ===================== Pygame 辅助 =====================
def make_gradient_bg(width, height, top, bottom):
    """纵向渐变背景"""
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
class ExpressionApp:
    """人脸表情识别 Pygame 界面应用"""

    TITLE_H = 130
    FOOTER_H = 110

    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('人脸表情识别 - 百度智能云')
        self.clock = pygame.time.Clock()

        # 字体（适配 1920×1080）
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 64)
        self.font_sub = pygame.font.Font(FONT_PATH, 32)
        self.font_item = pygame.font.Font(FONT_PATH, 30)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_small = pygame.font.Font(FONT_PATH, 24)
        self.font_big = pygame.font.Font(FONT_BOLD_PATH, 56)
        self.font_super = pygame.font.Font(FONT_BOLD_PATH, 96)

        # 背景：优先加载图片，失败回退渐变
        try:
            bg_raw = pygame.image.load('images/1.jpg')
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception:
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # 布局
        self.cam_rect = pygame.Rect(60, self.TITLE_H + 20,
                                    CAM_DISP_W + 40, CAM_DISP_H + 70)
        self.info_rect = pygame.Rect(self.cam_rect.right + 40, self.TITLE_H + 20,
                                     WIDTH - self.cam_rect.right - 40 - 60,
                                     HEIGHT - self.TITLE_H - 20 - self.FOOTER_H)

        # 退出按钮（右上角，标题栏内）
        self.btn_exit = Button((WIDTH - 280, 30, 240, 70),
                               '退出程序', EXIT_COLOR, EXIT_HOVER)

        # 表情识别器
        print('正在创建表情识别器...')
        self.detector = ExpressionDetector(face_client)

        # 摄像头打开（cv2，严格参照范例）
        print('外接摄像头打开中...')
        self.cap = open_camera()
        self.camera_ok = self.cap is not None and self.cap.isOpened()
        if self.camera_ok:
            print('外接摄像头已打开')
        else:
            print('摄像头打开失败，请检查 /dev/video41 和 /dev/video40')

        # 摄像头采集线程状态
        self.running = True
        self.raw_frame = None
        self.frame_lock = threading.Lock()
        self.cam_thread_running = True
        self.cam_fail = 0

        # 表情识别线程状态
        self.detect_thread_running = True
        self.detect_busy = False   # API 调用中
        self.detect_enabled = True  # 是否自动识别（可暂停）

        # 启动后台采集线程（避免阻塞主循环）
        threading.Thread(target=self.camera_capture_loop, daemon=True).start()
        # 启动表情识别线程（定期调用百度 API）
        threading.Thread(target=self.expression_detect_loop, daemon=True).start()

        print('程序启动完成，开始表情识别')

    # ---------- 摄像头采集线程 ----------
    def camera_capture_loop(self):
        """后台线程：快速读取摄像头帧，保证画面实时

        线程只负责 read() 并覆盖旧帧，不做任何处理，
        避免 V4L2 内核缓冲区积压旧帧导致画面延迟。
        """
        fail = 0
        while self.cam_thread_running:
            if not self.camera_ok or self.cap is None:
                time.sleep(0.2)
                continue
            try:
                ok, frame = self.cap.read()
                if ok and frame is not None:
                    with self.frame_lock:
                        self.raw_frame = frame
                    fail = 0
                else:
                    fail += 1
                    if fail > 5:
                        time.sleep(0.05)
            except Exception as e:
                if self.cam_thread_running:
                    print('摄像头采集异常:', e)
                fail += 1
                time.sleep(0.05)

    def get_current_frame(self):
        """获取当前摄像头帧的副本（线程安全）"""
        with self.frame_lock:
            return self.raw_frame.copy() if self.raw_frame is not None else None

    # ---------- 表情识别线程 ----------
    def expression_detect_loop(self):
        """后台线程：定期取最新帧调用百度智能云识别表情

        调用频率受 API_INTERVAL 限制（默认 1.5s），避免超过 QPS 限制。
        """
        # 首帧等待画面稳定
        time.sleep(1.0)
        while self.detect_thread_running:
            if not self.detect_enabled:
                time.sleep(0.2)
                continue
            frame = self.get_current_frame()
            if frame is None:
                time.sleep(0.2)
                continue

            self.detect_busy = True
            t0 = time.time()
            try:
                self.detector.detect(frame)
            except Exception as e:
                print('表情识别线程异常:', e)
            dt = time.time() - t0
            self.detect_busy = False

            # 保证两次调用间隔不少于 API_INTERVAL
            wait = API_INTERVAL - dt
            if wait > 0:
                time.sleep(wait)

    # ---------- 绘制 ----------
    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('人脸表情识别', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 20))
        sub = self.font_sub.render(
            'USB摄像头采集  ·  百度智能云AipFace  ·  emotion 七种基本情绪识别',
            True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 85))

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

        # 识别状态角标（左下角）
        state = self.detector.get_state()
        if self.detect_busy:
            badge = self.font_small.render('● 识别中...', True, ACCENT_COLOR)
        elif state['error']:
            badge = self.font_small.render('● 识别异常', True, ERROR_COLOR)
        elif not self.detect_enabled:
            badge = self.font_small.render('● 已暂停', True, SUBTLE_COLOR)
        else:
            badge = self.font_small.render('● 等待识别', True, SUCCESS_COLOR)
        self.screen.blit(badge, (self.cam_rect.x + 20, self.cam_rect.bottom - 25))

    def draw_info_panel(self):
        """绘制右侧信息面板：当前表情 + 人脸信息 + 统计 + 说明"""
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 30
        x_end = self.info_rect.right - 30
        y = self.info_rect.y + 20

        state = self.detector.get_state()
        result = state['result']
        stats = state['stats']

        # ---- 当前主表情大字区 ----
        head = self.font_sub.render('当前表情', True, TITLE_COLOR)
        self.screen.blit(head, (x, y))
        y += 45

        # 表情卡片
        card_h = 150
        card = pygame.Rect(x, y, x_end - x, card_h)
        pygame.draw.rect(self.screen, (245, 250, 255), card, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_BORDER, card, 2, border_radius=14)

        if result and result['face_num'] > 0 and result['expressions']:
            main_expr = result['expressions'][0]['type']
            prob = result['expressions'][0]['probability']
            name = EXPRESSION_NAMES.get(main_expr, '未知')
            color = EXPRESSION_COLORS.get(main_expr, EXPRESSION_COLORS['unknown'])
            emoji = EXPRESSION_EMOJI.get(main_expr, EXPRESSION_EMOJI['unknown'])

            big = self.font_super.render(name, True, color)
            self.screen.blit(big, (card.centerx - big.get_width() // 2, card.y + 12))

            em = self.font_small.render(emoji, True, color)
            self.screen.blit(em, (card.centerx - em.get_width() // 2, card.bottom - 28))

            prob_txt = self.font_small.render('概率 %.0f%%' % (prob * 100), True, SUBTLE_COLOR)
            self.screen.blit(prob_txt, (card.right - prob_txt.get_width() - 15,
                                        card.y + 10))
        else:
            tip = '未识别到人脸' if (result and result['face_num'] == 0) else '等待识别...'
            tip_color = SUBTLE_COLOR if not state['error'] else ERROR_COLOR
            ts = self.font_big.render(tip, True, tip_color)
            self.screen.blit(ts, (card.centerx - ts.get_width() // 2,
                                  card.centery - ts.get_height() // 2))

        y = card.bottom + 15

        # ---- 人脸数量 ----
        if result:
            face_num_txt = self.font_item.render(
                '检测到人脸：%d 张' % result['face_num'], True, TEXT_COLOR)
            self.screen.blit(face_num_txt, (x, y))
        else:
            face_num_txt = self.font_item.render('检测到人脸：0 张', True, SUBTLE_COLOR)
            self.screen.blit(face_num_txt, (x, y))
        y += 32

        # 全部表情列表（最多 5 张）
        if result and result['expressions']:
            for i, e in enumerate(result['expressions'][:5]):
                name = EXPRESSION_NAMES.get(e['type'], '未知')
                color = EXPRESSION_COLORS.get(e['type'], EXPRESSION_COLORS['unknown'])
                line = self.font_small.render(
                    '  人脸%d：%s  (%.0f%%)' % (i + 1, name, e['probability'] * 100),
                    True, color)
                self.screen.blit(line, (x, y))
                y += 24

        y += 6
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 12

        # ---- 历史统计 ----
        head2 = self.font_sub.render('历史统计', True, TITLE_COLOR)
        self.screen.blit(head2, (x, y))
        y += 40

        total = max(1, sum(stats.values()))
        stat_items = [
            ('愤怒', stats['angry'], EXPRESSION_COLORS['angry']),
            ('厌恶', stats['disgust'], EXPRESSION_COLORS['disgust']),
            ('恐惧', stats['fear'], EXPRESSION_COLORS['fear']),
            ('高兴', stats['happy'], EXPRESSION_COLORS['happy']),
            ('悲伤', stats['sad'], EXPRESSION_COLORS['sad']),
            ('惊讶', stats['surprise'], EXPRESSION_COLORS['surprise']),
            ('中性', stats['neutral'], EXPRESSION_COLORS['neutral']),
            ('无人脸', stats['no_face'], SUBTLE_COLOR),
            ('异常', stats['error'], ERROR_COLOR),
        ]
        for name, cnt, color in stat_items:
            # 颜色方块
            pygame.draw.rect(self.screen, color, (x, y + 4, 18, 18), border_radius=4)
            label = self.font_small.render(name, True, TEXT_COLOR)
            self.screen.blit(label, (x + 26, y + 2))
            # 数量
            cnt_txt = self.font_small.render('%d' % cnt, True, TEXT_COLOR)
            self.screen.blit(cnt_txt, (x_end - cnt_txt.get_width(), y + 2))
            # 进度条
            bar_x = x + 26 + 80
            bar_w = x_end - bar_x - 60
            if bar_w > 0:
                pygame.draw.rect(self.screen, (230, 235, 245),
                                 (bar_x, y + 8, bar_w, 10), border_radius=5)
                fill_w = int(bar_w * cnt / total)
                if fill_w > 0:
                    pygame.draw.rect(self.screen, color,
                                     (bar_x, y + 8, fill_w, 10), border_radius=5)
            y += 30

        y += 8
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 12

        # ---- API 调用信息 ----
        head3 = self.font_sub.render('API 调用', True, TITLE_COLOR)
        self.screen.blit(head3, (x, y))
        y += 32

        # 一行状态：调用次数 + 状态
        status_str = '识别中' if self.detect_busy else (
            '异常' if state['error'] else '空闲')
        line1 = self.font_small.render(
            '调用：%d 次  ·  间隔 %.1fs  ·  %s' % (
                state['call_count'], API_INTERVAL, status_str),
            True, TEXT_COLOR)
        self.screen.blit(line1, (x, y))
        y += 24

        if state['last_call_time'] > 0:
            line2 = self.font_small.render(
                '上次调用：%s' % time.strftime('%H:%M:%S',
                                              time.localtime(state['last_call_time'])),
                True, SUBTLE_COLOR)
            self.screen.blit(line2, (x, y))
            y += 24

        if state['error']:
            err_txt = self.font_small.render(
                '错误：%s' % state['error'][:40], True, ERROR_COLOR)
            self.screen.blit(err_txt, (x, y))
            y += 24

    def draw_footer(self, mouse_pos):
        """绘制底部栏：操作提示"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        mask.fill((255, 255, 255, 150))
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        tips = [
            'ESC / 点击右上角按钮：退出程序',
            '空格键：暂停/继续自动识别',
            '当前状态：%s' % ('自动识别中' if self.detect_enabled else '已暂停'),
        ]
        x = 60
        y = HEIGHT - self.FOOTER_H + 30
        for tip in tips:
            txt = self.font_small.render(tip, True, SUBTLE_COLOR)
            self.screen.blit(txt, (x, y))
            x += txt.get_width() + 60

    # ---------- 主循环 ----------
    def run(self):
        while self.running:
            mouse_pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.btn_exit.clicked(event.pos):
                        self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_SPACE:
                        self.detect_enabled = not self.detect_enabled
                        print('自动识别：%s' % ('开启' if self.detect_enabled else '暂停'))

            self.btn_exit.update(mouse_pos)

            self.screen.blit(self.bg, (0, 0))
            self.draw_title()
            self.draw_camera()
            self.draw_info_panel()
            self.draw_footer(mouse_pos)

            pygame.display.flip()
            self.clock.tick(30)

        # 退出清理
        self.cam_thread_running = False
        self.detect_thread_running = False
        time.sleep(0.3)
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        pygame.quit()
        try:
            _debug_log_fp.close()
        except Exception:
            pass


# ===================== 入口 =====================
if __name__ == '__main__':
    app = ExpressionApp()
    app.run()
