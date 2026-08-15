# -*- coding: utf-8 -*-
"""
文字识别播报系统 - 好搭AI派程序
=====================================
功能说明：
  1. 界面 1920x1080，实时显示摄像头画面
  2. 点击「识别」按钮 -> OCR 识别当前画面文字 -> 在结果区显示 -> 语音合成并播报
  3. 点击「停止播报」按钮 -> 停止当前语音播放
  4. 点击「退出」按钮 -> 退出程序
  5. 界面排布合理，科技感深色主题

硬件依赖：
  - USB 外接摄像头（接在 ESP32 扩展板 USB 口）
  - 需联网（语音 AI 在线合成）

OCR 后端：使用官方 text_recognition.TextRecognizer（依赖 ppocr_system / PaddleOCR）

参考范例：
  - 范例代码 5.AI视觉算法 21.实时文字识别（摄像头+OCR+TTS）
  - 范例代码 4.语音AI 1.语音合成
  - 范例代码 3.音频处理 2.音频播放
  - 范例代码 8.pygame 10.音乐播放-按钮
  - 本地参考：唐诗宋词朗读器.py（界面风格、线程化播报、可中断播放）
"""

import os
# 强制 libGL 使用软件渲染，避免 rockchip 平台 GPU 驱动加载失败
# 必须在 ALL import 之前设置（包括 text_recognition、pygame、cv2），
# 否则 PaddleOCR 加载时就已触发 Mali GPU 硬件 DRI 驱动崩溃
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

# !!! text_recognition 必须在所有其他库之前导入 !!!
# 原因：ppocr_system 依赖 utils.operators，若先导入 cv2/pygame/camera_vision_system_v3，
# 它们会将 utils 注册为非包模块，导致 ppocr_system 报 'utils' is not a package
try:
    from text_recognition import TextRecognizer as _TextRecognizer
    _TEXT_RECOGNITION_AVAILABLE = True
    _TEXT_RECOGNITION_ERROR = None
except Exception as _e:
    _TEXT_RECOGNITION_AVAILABLE = False
    _TEXT_RECOGNITION_ERROR = _e

import sys
import time
import threading
import datetime as _datetime

# 导入顺序：先 pygame 再 cv2（rockchip 平台兼容性要求）
import pygame
import cv2
from voice_api import VoiceAPI
from audio_player import AudioPlayer


# ===================== 日志输出（控制台 + 文件）=====================
# 参照人脸识别灯效.py / 人数实时统计.py 的日志方案：
# logs/ 目录、程序名_YYYYMMDD.log、追加模式、块缓冲
_LOG_DIR = 'logs'
if not os.path.exists(_LOG_DIR):
    try:
        os.makedirs(_LOG_DIR)
    except Exception:
        pass
_LOG_FILE = os.path.join(
    _LOG_DIR,
    '文字识别播报器_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
)
_debug_log_fp = open(_LOG_FILE, 'a', encoding='utf-8', buffering=-1)
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

# 字体参考《好搭AI派可用字体列表.txt》
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'
FONT_REG_PATH  = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'
FONT_KAI_PATH  = '/home/cxdz/jupyter/assets/simkai.ttf'

# 语音 AI 认证 —— 请替换为自己经过认证的好好搭搭账号
VOICE_USERNAME = 'username'
VOICE_PASSWORD = 'password'

# OCR 置信度阈值
OCR_CONFIDENCE = 0.5

# ---- 界面配色（科技感深色主题） ----
BG_TOP        = (10, 14, 30)
BG_BOTTOM     = (4, 6, 18)
PANEL_COLOR   = (16, 22, 44)
PANEL_BORDER  = (0, 160, 210)
TITLE_COLOR   = (0, 229, 255)
SUBTLE_COLOR  = (120, 150, 190)
TEXT_COLOR    = (230, 240, 250)
TEXT_DIM      = (140, 160, 190)
ACCENT_CYAN   = (0, 229, 255)
ACCENT_ORANGE = (255, 170, 60)
ACCENT_RED    = (255, 80, 90)
BTN_RECOG_COLOR  = (0, 140, 200)
BTN_RECOG_HOVER  = (0, 190, 255)
BTN_STOP_COLOR   = (140, 80, 160)
BTN_STOP_HOVER   = (190, 120, 220)
BTN_EXIT_COLOR   = (90, 90, 110)
BTN_EXIT_HOVER   = (200, 70, 80)
STATUS_READY     = (0, 255, 136)
STATUS_BUSY      = (255, 200, 60)
STATUS_ERROR     = (255, 80, 90)


# ===================== 摄像头（纯 cv2 模式）+ OCR + 语音AI 初始化 =====================
# 初始化顺序：
#   1. OCR（TextRecognizer）—— 必须在其他设备操作前初始化，避免 utils 模块冲突
#   2. VoiceAPI / get_token / AudioPlayer
#   3. 摄像头 cv2.VideoCapture 打开（最后，独占 USB 总线）
#
# 摄像头打开策略：改用纯 cv2 模式，显式指定 cv2.CAP_V4L2 后端，直接打开
# /dev/video{N} 字符串路径，完全绕过 OpenCV FFMPEG 后端。
# 问题背景：FFMPEG 后端的设备列表仅 32 项，camera_id >= 32（如 40/41/42）即使
# /dev/videoN 节点存在也会触发 "Camera index out of range" 错误，每次失败约
# 耗 4~6 秒，然后 SDK 内部再回退，导致启动极慢。V4L2 后端无 32 项限制，毫秒级完成。
#
# 候选顺序按用户建议：先 42，再 41，最后 40。每个候选都先检查节点存在，再用
# CAP_V4L2 后端实际 open + read 验证，跳过"节点存在但不是视频捕获设备（元
# 数据节点）"的情况。
def _open_cv2_camera(target_width=640, target_height=480):
    """按 42 → 41 → 40 顺序打开 cv2.VideoCapture（CAP_V4L2 后端，跳过 FFMPEG）。
    返回 (cv2.VideoCapture, device_path)，失败返回 (None, '')。
    """
    candidates = (42, 41, 40)
    import numpy as np
    for cid in candidates:
        path = '/dev/video%d' % cid
        if not os.path.exists(path):
            print('摄像头候选：%s（节点不存在，跳过）' % path)
            continue
        print('摄像头候选：%s（尝试打开…）' % path)
        try:
            cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        except Exception as _e:
            print('  cv2.VideoCapture(%s) 异常：%s' % (path, _e))
            continue
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            print('  cv2.VideoCapture(%s) isOpened=False，跳过' % path)
            continue
        # 设置分辨率（先设置再读帧，保证输出尺寸一致）
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_height)
        # 最多读 5 次验证帧有效性（参考范例的帧验证，用 mean 代替 std 省 CPU）
        frame_ok = False
        for _ in range(5):
            ret, frame = cap.read()
            if (not ret) or frame is None:
                time.sleep(0.02)
                continue
            if not isinstance(frame, np.ndarray) or frame.ndim != 3:
                time.sleep(0.02)
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            m = float(gray.mean())
            # 排除全黑/全白雪花帧（全黑 mean<2，全白 mean>253）
            if 2.0 < m < 253.0:
                frame_ok = True
                break
            time.sleep(0.02)
        if not frame_ok:
            try:
                cap.release()
            except Exception:
                pass
            print('  cv2.VideoCapture(%s) 帧有效性验证失败，跳过' % path)
            continue
        print('✓ 摄像头已打开：%s（分辨率 %dx%d，CAP_V4L2 后端）' % (
            path, target_width, target_height))
        return cap, path
    print('警告：42/41/40 三个候选均无法以 V4L2 后端打开，请检查硬件连接')
    return None, ''


# ---- OCR 初始化（必须在摄像头打开之前初始化完成）----
# text_recognition 已在文件最顶部导入（避免 utils 模块名冲突）
# 使用官方 text_recognition.TextRecognizer（依赖 ppocr_system / PaddleOCR）
ocr_recognizer = None
if _TEXT_RECOGNITION_AVAILABLE:
    try:
        ocr_recognizer = _TextRecognizer()
        print('OCR 后端：PaddleOCR（官方 text_recognition）')
    except Exception as e:
        print('TextRecognizer 实例化失败:', e)
else:
    print('官方 text_recognition 导入失败:', _TEXT_RECOGNITION_ERROR)

# ---- 语音 AI + 音频播放器 ----
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token(VOICE_USERNAME, VOICE_PASSWORD)
player = AudioPlayer()

if not token_result:
    print('语音 AI 认证失败，请检查账号密码')
else:
    print('语音 AI 认证成功')

# ---- 摄像头打开（纯 cv2 模式，显式 CAP_V4L2 后端，跳过 FFMPEG，毫秒级完成）----
_cv2_cap, _camera_path = _open_cv2_camera(640, 480)
if _cv2_cap is None:
    print('警告：摄像头打开失败，请检查硬件连接（/dev/video42, /dev/video41, /dev/video40）')
else:
    print('cv2 摄像头采集就绪，画面将在 Pygame 界面中显示')


def ocr_recognize(frame, confidence_threshold=OCR_CONFIDENCE):
    """OCR 识别函数（严格参照范例 5.21）。
    返回官方 TextRecognizer 结果结构：{"success": bool, "text": str}
    """
    if frame is None or ocr_recognizer is None:
        return {"success": False, "text": ""}
    try:
        return ocr_recognizer.recognize_text(frame, confidence_threshold=confidence_threshold)
    except Exception as e:
        print('[OCR] 识别异常:', e)
        return {"success": False, "text": ""}


def ocr_cleanup():
    """清理 OCR 资源"""
    if ocr_recognizer is not None:
        try:
            ocr_recognizer.cleanup()
        except:
            pass


# ===================== 全局状态 =====================
recognized_text = ''          # 当前识别到的文字
is_recognizing = False        # 是否正在识别
is_playing = False            # 是否正在播报
stop_requested = False        # 是否请求停止播报
status_message = '就绪'
status_color = STATUS_READY
scan_active = False           # 是否正在播放扫描动画


# ===================== 识别与播报（线程化，参照唐诗宋词朗读器模式） =====================
def recognize_and_play_async(frame):
    """异步执行：OCR 识别 -> 显示文字 -> TTS 合成 -> 播报"""
    global is_recognizing, is_playing, recognized_text
    global status_message, status_color, stop_requested, scan_active

    if is_recognizing or is_playing:
        return

    is_recognizing = True
    stop_requested = False
    scan_active = True
    status_message = '正在识别文字…'
    status_color = STATUS_BUSY

    def worker():
        global is_recognizing, is_playing, recognized_text
        global status_message, status_color, stop_requested, scan_active

        try:
            # ---- OCR 识别 ----
            if frame is None:
                status_message = '未获取到画面'
                status_color = STATUS_ERROR
                return

            ocr_result = ocr_recognize(frame, confidence_threshold=OCR_CONFIDENCE)

            if stop_requested:
                status_message = '已停止'
                status_color = STATUS_READY
                return

            if ocr_result["success"] and ocr_result["text"].strip():
                text = ocr_result["text"].strip()
                recognized_text = text
                print('[OCR] 识别结果：' + text)
                status_message = '识别完成，正在合成语音…'
            else:
                recognized_text = '（未识别到文字）'
                status_message = '未识别到文字'
                status_color = ACCENT_ORANGE
                return

            # ---- TTS 语音合成 ----
            if stop_requested:
                status_message = '已停止'
                status_color = STATUS_READY
                return

            audio_path = 'recordings/ocr_result.wav'
            audio_data = voice_api.tts_synthesize(recognized_text, audio_path)
            if not audio_data:
                status_message = '语音合成失败'
                status_color = STATUS_ERROR
                return

            if stop_requested:
                status_message = '已停止'
                status_color = STATUS_READY
                return

            # ---- 语音播报 ----
            is_recognizing = False
            is_playing = True
            scan_active = False
            status_message = '正在播报…'
            status_color = STATUS_BUSY
            play_audio_interruptible(audio_path)

        except Exception as e:
            print('识别播报异常:', e)
            status_message = '识别异常'
            status_color = STATUS_ERROR
        finally:
            is_recognizing = False
            is_playing = False
            scan_active = False
            if status_message not in ('已停止',):
                status_message = '就绪'
                status_color = STATUS_READY

    threading.Thread(target=worker, daemon=True).start()


def play_audio_interruptible(audio_path):
    """非阻塞播放音频，支持被 stop_requested 中断（参照唐诗宋词朗读器）"""
    global stop_requested
    try:
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.set_volume(0.9)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if stop_requested:
                pygame.mixer.music.stop()
                break
            time.sleep(0.1)
    except Exception as e:
        print('播放异常:', e)


def stop_playback():
    """停止当前播报"""
    global is_recognizing, is_playing, status_message, status_color, stop_requested, scan_active
    stop_requested = True
    try:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
    except:
        pass
    is_recognizing = False
    is_playing = False
    scan_active = False
    status_message = '已停止'
    status_color = STATUS_READY


# ===================== Pygame 界面 =====================
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


class Button:
    """通用圆角按钮（参照唐诗宋词朗读器）"""

    def __init__(self, rect, text, color, hover_color, text_color=TEXT_COLOR, icon=''):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.icon = icon
        self.hovered = False
        self.enabled = True

    def update(self, mouse_pos):
        self.hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def draw(self, surf, font):
        c = self.hover_color if self.hovered else self.color
        if not self.enabled:
            c = (50, 52, 68)
        btn = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn, c, btn.get_rect(), border_radius=14)
        # 科技感发光边框
        border_c = (255, 255, 255, 200) if self.hovered else (120, 200, 230, 150)
        pygame.draw.rect(btn, border_c, btn.get_rect(), 2, border_radius=14)
        surf.blit(btn, self.rect.topleft)
        label = font.render(self.icon + self.text, True, self.text_color)
        lr = label.get_rect(center=self.rect.center)
        surf.blit(label, lr)

    def clicked(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


class OCRApp:
    TITLE_H = 110
    FOOTER_H = 140

    # 摄像头面板
    CAM_PANEL_X = 24
    CAM_PANEL_Y = 124
    CAM_PANEL_W = 1280
    CAM_PANEL_H = 800

    # 结果面板
    RESULT_X = 1320
    RESULT_Y = 124
    RESULT_W = 576
    RESULT_H = 800

    def __init__(self):
        # 分段初始化（不调用 pygame.init()），避免 pygame.mixer 导致原生崩溃
        # 参考方案第 7 章 Rockchip 平台兼容性补丁
        pygame.display.init()
        pygame.font.init()
        # mixer 需用于语音播报，单独初始化并容错（Rockchip 平台音频驱动可能崩溃）
        try:
            pygame.mixer.init()
        except Exception as e:
            print('pygame.mixer 初始化失败，语音播报功能不可用:', e)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('文字识别播报系统')
        self.clock = pygame.time.Clock()

        # 字体
        self.font_title    = pygame.font.Font(FONT_BOLD_PATH, 52)
        self.font_sub      = pygame.font.Font(FONT_REG_PATH, 24)
        self.font_btn      = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_result   = pygame.font.Font(FONT_KAI_PATH, 36)
        self.font_label    = pygame.font.Font(FONT_BOLD_PATH, 28)
        self.font_small    = pygame.font.Font(FONT_REG_PATH, 22)
        self.font_status   = pygame.font.Font(FONT_BOLD_PATH, 26)

        # 背景：优先加载 images/1.jpg，失败则回退渐变背景
        try:
            bg_raw = pygame.image.load(os.path.join('images', '1.jpg'))
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT))
        except Exception as e:
            print('背景图片加载失败，使用渐变背景:', e)
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM)

        # 确保录音目录存在
        if not os.path.exists('recordings'):
            os.makedirs('recordings')

        self.running = True
        self.current_frame = None   # 当前摄像头帧（OpenCV BGR）

        # 按钮
        # 识别 / 停止播报按钮在底部栏；退出按钮在右上角标题栏内（符合项目记忆）
        btn_y = HEIGHT - self.FOOTER_H + 38
        btn_h = 70
        self.btn_recog = Button((24, btn_y, 240, btn_h), '识别', BTN_RECOG_COLOR, BTN_RECOG_HOVER)
        self.btn_stop  = Button((290, btn_y, 240, btn_h), '停止播报', BTN_STOP_COLOR, BTN_STOP_HOVER)
        # 标题栏高度 110，按钮高度 70，垂直居中 y = (110-70)/2 = 20
        self.btn_exit  = Button((WIDTH - 280, 20, 240, btn_h), '退出', BTN_EXIT_COLOR, BTN_EXIT_HOVER)

        # 扫描线动画
        self.scan_y = 0

        # 后台帧抓取线程（仅做帧缓冲，避免 capture_frame 阻塞主循环）
        self._frame_lock = threading.Lock()
        self._latest_bgr = None        # 后台线程更新的最新 BGR 帧
        self._frame_thread_running = True
        self._frame_thread = threading.Thread(target=self._frame_capture_worker, daemon=True)
        self._frame_thread.start()

    # ---------- 后台帧抓取线程 ----------
    def _frame_capture_worker(self):
        """后台线程：持续抓帧做缓冲，避免 cap.read() 阻塞主循环。纯 cv2 模式。"""
        import numpy as _np
        # 失败计数：连续失败 3 次降频，恢复后回到正常频率
        normal_interval = 0.05   # ≈20 fps
        slow_interval = 0.33     # ≈3 fps（失败时降频，项目记忆要求）
        fail_streak = 0
        while self._frame_thread_running:
            if _cv2_cap is None:
                time.sleep(slow_interval)
                continue
            frame = None
            try:
                ret, f = _cv2_cap.read()
                if ret and f is not None and isinstance(f, _np.ndarray) and f.ndim == 3:
                    frame = f
            except Exception:
                pass
            if frame is not None:
                fail_streak = 0
                with self._frame_lock:
                    self._latest_bgr = frame
            else:
                fail_streak += 1
            # 正常 0.05s，连续失败 3 次降到 0.33s
            interval = slow_interval if fail_streak >= 3 else normal_interval
            time.sleep(interval)

    # ---------- 摄像头帧获取与转换 ----------
    def grab_frame(self):
        """从共享数据读取最新帧并转为 Surface（非阻塞）"""
        with self._frame_lock:
            frame = self._latest_bgr
        if frame is None:
            return None
        # 保存当前帧供 OCR 使用
        self.current_frame = frame
        # BGR -> RGB，转为 Pygame Surface
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]
            surf = pygame.image.frombuffer(frame_rgb.tobytes(), (w, h), 'RGB')
            return surf
        except Exception:
            return None

    def scale_camera_surface(self, surf, target_w, target_h):
        """等比缩放摄像头画面到目标区域（用 scale 替代 smoothscale 提升性能）"""
        sw, sh = surf.get_size()
        scale = min(target_w / sw, target_h / sh)
        new_w = int(sw * scale)
        new_h = int(sh * scale)
        # scale（最近邻）比 smoothscale 快很多，大幅减少卡顿
        return pygame.transform.scale(surf, (new_w, new_h)), new_w, new_h

    # ---------- 绘制 ----------
    def draw_title(self, mouse_pos):
        """绘制顶部标题栏（含右上角退出按钮）"""
        # 半透明遮罩
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (0, 10, 30, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))
        # 底部发光线
        pygame.draw.line(self.screen, ACCENT_CYAN, (0, self.TITLE_H), (WIDTH, self.TITLE_H), 2)
        pygame.draw.line(self.screen, (0, 100, 130), (0, self.TITLE_H + 2), (WIDTH, self.TITLE_H + 2), 1)

        title = self.font_title.render('文字识别播报系统', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 24))

        sub = self.font_sub.render(
            'TEXT  RECOGNITION  &  VOICE  BROADCAST   |   摄像头实时画面  ->  OCR识别  ->  语音播报',
            True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 78))

        # 退出按钮（右上角标题栏内）
        self.btn_exit.update(mouse_pos)
        self.btn_exit.draw(self.screen, self.font_btn)

    def draw_camera_panel(self, mouse_pos):
        """绘制摄像头画面区域"""
        panel_rect = pygame.Rect(self.CAM_PANEL_X, self.CAM_PANEL_Y,
                                 self.CAM_PANEL_W, self.CAM_PANEL_H)

        # 面板背景
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 220), panel.get_rect(), border_radius=16)
        self.screen.blit(panel, panel_rect.topleft)

        # 面板边框
        pygame.draw.rect(self.screen, PANEL_BORDER, panel_rect, 2, border_radius=16)

        # 面板标题
        label = self.font_label.render('摄像头实时画面', True, ACCENT_CYAN)
        self.screen.blit(label, (panel_rect.x + 24, panel_rect.y + 18))

        # 分辨率标注
        res_text = self.font_small.render('640 x 480', True, TEXT_DIM)
        self.screen.blit(res_text, (panel_rect.right - res_text.get_width() - 24, panel_rect.y + 22))

        # ---- 摄像头画面 ----
        cam_inner_x = panel_rect.x + 20
        cam_inner_y = panel_rect.y + 60
        cam_inner_w = panel_rect.w - 40
        cam_inner_h = panel_rect.h - 80

        cam_surf = self.grab_frame()
        if cam_surf is not None:
            scaled, sw, sh = self.scale_camera_surface(cam_surf, cam_inner_w, cam_inner_h)
            # 居中显示
            ox = cam_inner_x + (cam_inner_w - sw) // 2
            oy = cam_inner_y + (cam_inner_h - sh) // 2
            self.screen.blit(scaled, (ox, oy))

            # 绘制科技感四角瞄准框
            self.draw_corner_brackets(ox, oy, sw, sh)

            # 识别中的扫描线动画
            if scan_active or is_recognizing:
                self.scan_y = (self.scan_y + 6) % sh
                line_y = oy + self.scan_y
                # 扫描线本体
                pygame.draw.line(self.screen, ACCENT_CYAN, (ox, line_y), (ox + sw, line_y), 2)
                # 扫描线发光效果
                glow = pygame.Surface((sw, 20), pygame.SRCALPHA)
                pygame.draw.rect(glow, (0, 229, 255, 60), glow.get_rect())
                self.screen.blit(glow, (ox, line_y - 10))
        else:
            # 帧未就绪提示（不做连接状态判定）
            hint = self.font_label.render('摄像头启动中…', True, ACCENT_CYAN)
            self.screen.blit(hint, (panel_rect.centerx - hint.get_width() // 2,
                                    panel_rect.centery - hint.get_height() // 2))

    def draw_corner_brackets(self, x, y, w, h):
        """在摄像头画面四角绘制科技感瞄准框"""
        bracket_len = 30
        bracket_color = ACCENT_CYAN
        thickness = 3
        # 左上
        pygame.draw.line(self.screen, bracket_color, (x, y), (x + bracket_len, y), thickness)
        pygame.draw.line(self.screen, bracket_color, (x, y), (x, y + bracket_len), thickness)
        # 右上
        pygame.draw.line(self.screen, bracket_color, (x + w, y), (x + w - bracket_len, y), thickness)
        pygame.draw.line(self.screen, bracket_color, (x + w, y), (x + w, y + bracket_len), thickness)
        # 左下
        pygame.draw.line(self.screen, bracket_color, (x, y + h), (x + bracket_len, y + h), thickness)
        pygame.draw.line(self.screen, bracket_color, (x, y + h), (x, y + h - bracket_len), thickness)
        # 右下
        pygame.draw.line(self.screen, bracket_color, (x + w, y + h), (x + w - bracket_len, y + h), thickness)
        pygame.draw.line(self.screen, bracket_color, (x + w, y + h), (x + w, y + h - bracket_len), thickness)

    def draw_result_panel(self):
        """绘制右侧识别结果区域"""
        panel_rect = pygame.Rect(self.RESULT_X, self.RESULT_Y, self.RESULT_W, self.RESULT_H)

        # 面板背景
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 220), panel.get_rect(), border_radius=16)
        self.screen.blit(panel, panel_rect.topleft)

        # 面板边框
        pygame.draw.rect(self.screen, PANEL_BORDER, panel_rect, 2, border_radius=16)

        # 面板标题
        label = self.font_label.render('识别结果', True, ACCENT_CYAN)
        self.screen.blit(label, (panel_rect.x + 24, panel_rect.y + 18))

        # 状态指示灯
        dot_x = panel_rect.right - 30
        dot_y = panel_rect.y + 32
        pygame.draw.circle(self.screen, status_color, (dot_x, dot_y), 8)
        # 发光效果
        glow_surf = pygame.Surface((30, 30), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*status_color, 80), (15, 15), 14)
        self.screen.blit(glow_surf, (dot_x - 15, dot_y - 15))

        # 分隔线
        sep_y = panel_rect.y + 60
        pygame.draw.line(self.screen, PANEL_BORDER,
                         (panel_rect.x + 20, sep_y), (panel_rect.right - 20, sep_y), 1)

        # ---- 识别结果文字 ----
        text_x = panel_rect.x + 30
        text_y = sep_y + 28
        max_w = panel_rect.w - 60
        max_h = panel_rect.h - 100

        if is_recognizing and not recognized_text:
            # 识别中动画提示
            dots = '.' * ((int(time.time() * 3) % 3) + 1)
            hint = self.font_result.render('正在识别' + dots, True, ACCENT_CYAN)
            self.screen.blit(hint, (text_x, text_y))
        elif recognized_text:
            # 逐行绘制识别结果，自动换行
            self.draw_wrapped_text(recognized_text, text_x, text_y, max_w, max_h, self.font_result, TEXT_COLOR)
        else:
            hint = self.font_result.render('点击「识别」按钮开始', True, TEXT_DIM)
            self.screen.blit(hint, (text_x, text_y))

        # 底部信息：置信度 + 状态
        info = self.font_small.render(
            '阈值: %.1f' % OCR_CONFIDENCE,
            True, TEXT_DIM)
        self.screen.blit(info, (panel_rect.x + 24, panel_rect.bottom - 56))
        info2 = self.font_small.render('状态: %s' % status_message, True, status_color)
        self.screen.blit(info2, (panel_rect.x + 24, panel_rect.bottom - 30))

    def draw_wrapped_text(self, text, x, y, max_w, max_h, font, color):
        """自动换行绘制长文本"""
        lines = text.split('\n')
        cy = y
        for line in lines:
            if not line.strip():
                cy += font.get_height() // 2
                continue
            # 逐字测量换行
            current = ''
            for ch in line:
                test = current + ch
                if font.size(test)[0] > max_w:
                    if current:
                        surf = font.render(current, True, color)
                        if cy + surf.get_height() > y + max_h:
                            ell = self.font_small.render('……（内容已截断）', True, TEXT_DIM)
                            self.screen.blit(ell, (x, y + max_h - 30))
                            return
                        self.screen.blit(surf, (x, cy))
                        cy += surf.get_height() + 6
                    current = ch
                else:
                    current = test
            if current:
                surf = font.render(current, True, color)
                if cy + surf.get_height() > y + max_h:
                    ell = self.font_small.render('……（内容已截断）', True, TEXT_DIM)
                    self.screen.blit(ell, (x, y + max_h - 30))
                    return
                self.screen.blit(surf, (x, cy))
                cy += surf.get_height() + 6

    def draw_footer(self, mouse_pos):
        """绘制底部按钮栏（退出按钮已移至标题栏右上角）"""
        # 半透明遮罩
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (0, 10, 30, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))
        # 顶部发光线
        pygame.draw.line(self.screen, ACCENT_CYAN,
                         (0, HEIGHT - self.FOOTER_H), (WIDTH, HEIGHT - self.FOOTER_H), 2)

        # 按钮状态更新（退出按钮已在 draw_title 中处理）
        self.btn_recog.update(mouse_pos)
        self.btn_stop.update(mouse_pos)
        # 识别/播报中禁用识别按钮；播报中启用停止按钮
        self.btn_recog.enabled = not is_recognizing and not is_playing
        self.btn_stop.enabled = is_playing or is_recognizing
        self.btn_recog.draw(self.screen, self.font_btn)
        self.btn_stop.draw(self.screen, self.font_btn)

        # 状态文字
        status = self.font_status.render(status_message, True, status_color)
        self.screen.blit(status, (560, HEIGHT - self.FOOTER_H + 58))

        # 操作提示
        hint = self.font_small.render(
            '快捷键:  空格=识别    ESC=退出（或点右上角退出按钮）', True, TEXT_DIM)
        self.screen.blit(hint, (560, HEIGHT - self.FOOTER_H + 95))

    # ---------- 事件处理 ----------
    def handle_click(self, pos):
        if self.btn_recog.clicked(pos):
            self.on_recognize()
        elif self.btn_stop.clicked(pos):
            stop_playback()
        elif self.btn_exit.clicked(pos):
            self.running = False

    def on_recognize(self):
        """触发识别"""
        global recognized_text, stop_requested, status_message, status_color
        if is_recognizing or is_playing:
            return
        if ocr_recognizer is None:
            recognized_text = 'OCR 初始化失败。\n请检查 ppocr_system 依赖后重试。'
            status_message = 'OCR 不可用'
            status_color = STATUS_ERROR
            return
        if self.current_frame is None:
            status_message = '未获取到画面'
            status_color = STATUS_ERROR
            return
        recognized_text = ''
        stop_requested = False
        recognize_and_play_async(self.current_frame.copy())

    # ---------- 主循环 ----------
    def run(self):
        while self.running:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.handle_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_SPACE:
                        self.on_recognize()

            # 绘制
            self.screen.blit(self.bg, (0, 0))
            self.draw_title(mouse_pos)
            self.draw_camera_panel(mouse_pos)
            self.draw_result_panel()
            self.draw_footer(mouse_pos)

            pygame.display.flip()
            self.clock.tick(30)

        # ---- 退出清理 ----
        stop_playback()
        ocr_cleanup()
        # 停止后台抓帧线程
        self._frame_thread_running = False
        self._frame_thread.join(timeout=2)
        # 释放 cv2 摄像头设备（纯 cv2 模式，无 vision_system）
        global _cv2_cap
        if _cv2_cap is not None:
            try:
                _cv2_cap.release()
            except Exception:
                pass
            _cv2_cap = None
            print('cv2 摄像头已释放')
        try:
            player.cleanup()
        except Exception:
            pass
        pygame.quit()
        print('程序已退出')
        try:
            _debug_log_fp.close()
        except Exception:
            pass


# ===================== 入口 =====================
if __name__ == '__main__':
    app = OCRApp()
    app.run()
