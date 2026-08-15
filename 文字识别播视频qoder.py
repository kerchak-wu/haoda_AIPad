# -*- coding: utf-8 -*-
"""
============================================================
文字识别触发视频播放程序（好搭AI派）— 科技风 1920x1080
============================================================

功能说明：
  1. 打开摄像头，实时进行文字识别（OCR）
  2. 识别到「好搭智眼」→ 自动播放 videos/hdzy.mp4
  3. 识别到「芦丁鸡」→ 自动播放 videos/ldj.mp4
  4. 识别到「信息科技实验板」→ 自动播放 videos/syb.mp4
  5. 识别界面右上角提供「退出程序」按钮，点击后程序退出
  6. 视频播放界面提供「暂停/继续」按钮（点击暂停后按钮变为继续，
     再点击继续恢复播放）和「停止」按钮
  7. 视频自然播放结束或点击「停止」后，自动返回识别界面
  8. 视频声音直接来自 mp4 内嵌音轨（无需单独音频文件）：
     播放前用 ffmpeg 将音轨提取为临时 wav，与画面同步播放，
     暂停/继续/停止时声音同步动作；若 ffmpeg 不可用则静音播放画面
  9. 性能优化：
     - 摄像头采用「纯 cv2 独占模式」+ 独立采集线程（30fps 流畅预览），
       不经过视觉系统 V3（其全托管模式仅 6~7fps）
     - OCR 识别推理在独立后台线程连续进行（引擎空闲即提交最新画面），
       并对识别帧做宽度压缩以加快速度，界面刷新不被阻塞
     - 启动时先显示启动画面，OCR 引擎在主线程加载
       （必须先于其他 SDK 模块导入，避免 PaddleOCR 的 utils 包冲突）
 10. 重复触发防护（避免「停止后自动再播一次」）：
     - 播放开始/结束时置位/清除 ocr_pause 标志，OCR 后台线程
       丢弃排队中/识别中的画面，并清空已产生的识别结果
     - 每个识别结果带产生时间戳，返回识别界面后只接受晚于
       本次播放结束时刻的新结果，播放前遗留的陈旧结果一律丢弃

文件放置要求：
  - 本程序与 videos 文件夹放在同一目录（好搭AI派项目文件夹）
  - videos 文件夹内需包含：hdzy.mp4、ldj.mp4、syb.mp4
  - 需要先在好搭Block中加载官方扩展库：OCR文字识别、Pygame游戏模块
    （本程序不再使用摄像头视觉系统V3）

运行环境：好搭AI派（Ubuntu + Python 3）
============================================================
"""

import os
# Rockchip 平台兼容性补丁：强制 libGL 使用软件渲染，避免 GPU 驱动崩溃
# 必须在 ALL import 之前设置（包括 text_recognition、pygame、cv2），
# 否则 PaddleOCR 加载时就已触发 Mali GPU 硬件 DRI 驱动崩溃
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

# !!! text_recognition 必须在所有其他库之前导入 !!!
# 原因：ppocr_system 依赖 utils.operators，若先导入 cv2/pygame，
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
import subprocess
import tempfile
import datetime as _datetime
from queue import Queue, Empty

# 导入顺序：先 pygame 再 cv2（Rockchip 平台兼容性要求）
import pygame
import cv2

# Pygame 分段初始化（不调用 pygame.init()，避免与摄像头驱动冲突）
pygame.display.init()
pygame.font.init()
# mixer 需用于视频内嵌音轨播放，单独初始化并容错（Rockchip 平台音频驱动可能崩溃）
try:
    pygame.mixer.init()
except Exception as _e:
    print('pygame.mixer 初始化失败，视频音轨播放功能不可用:', _e)


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
    '文字识别播视频qoder_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
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

# ==================== 配置参数 ====================
WINDOW_W, WINDOW_H = 1920, 1080         # 窗口大小（1920x1080）
PREVIEW_W, PREVIEW_H = 1280, 720         # 摄像头预览区域大小
RETRIGGER_DELAY = 3                      # 视频播放结束后，多久内不重复触发（秒）
OCR_FRAME_MAX_W = 800                    # 送入识别的帧最大宽度（压缩后识别更快）
AUDIO_ENABLED = True                     # 是否播放视频内嵌音轨

# 摄像头设备候选列表（按顺序探测，使用第一个能出画面的设备）
CAMERA_DEVICES = ['/dev/video41', '/dev/video40', '/dev/video42', 0, 1, 2]

# 中文字体路径（按顺序查找，使用第一个存在的字体）
FONT_PATHS = [
    '/home/cxdz/jupyter/assets/PingFang_Medium.ttf',
    '/home/cxdz/jupyter/assets/simfang.ttf',
    '/home/cxdz/jupyter/assets/simhei.ttf',
    '/home/cxdz/jupyter/assets/msyh.ttc',
    '/home/cxdz/jupyter/assets/WenQuanWeiMiHei.ttf',
]

# 识别文字 → 视频文件 映射表
VIDEO_MAP = {
    '好搭智眼': 'videos/hdzy.mp4',
    '芦丁鸡': 'videos/ldj.mp4',
    '信息科技实验板': 'videos/syb.mp4',
}

# ==================== 科技风配色 ====================
COLOR_BG = (8, 12, 24)               # 深空蓝黑背景
COLOR_GRID = (18, 28, 50)            # 网格线
COLOR_PANEL = (13, 21, 38)           # 面板底色
COLOR_TERMINAL = (5, 10, 20)         # 终端框底色
COLOR_CYAN = (0, 229, 255)           # 主色：电光青
COLOR_CYAN_DIM = (0, 140, 200)       # 暗青
COLOR_TEXT = (225, 245, 255)         # 主文字
COLOR_DIM = (125, 155, 180)          # 次要文字
COLOR_GREEN = (0, 255, 140)          # 成功/在线
COLOR_RED = (255, 70, 90)            # 退出/告警
COLOR_ORANGE = (255, 170, 60)        # 停止/加载中


def load_font(size):
    """加载中文字体，按候选路径逐个尝试"""
    for path in FONT_PATHS:
        if os.path.exists(path):
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


# ==================== 科技风绘制工具 ====================

# 网格背景 Surface 缓存（静态画面，无需每帧重绘 25 条线）
_GRID_SURFACE = None


def draw_grid(window):
    """绘制淡网格背景（缓存优化：首次绘制后复用 Surface，背景透明）"""
    global _GRID_SURFACE
    if _GRID_SURFACE is None:
        # SRCALPHA 透明背景 Surface，仅包含网格线，可叠加到任意背景上
        _GRID_SURFACE = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        for x in range(0, WINDOW_W, 120):
            pygame.draw.line(_GRID_SURFACE, COLOR_GRID, (x, 0), (x, WINDOW_H), 1)
        for y in range(0, WINDOW_H, 120):
            pygame.draw.line(_GRID_SURFACE, COLOR_GRID, (0, y), (WINDOW_W, y), 1)
        _GRID_SURFACE = _GRID_SURFACE.convert_alpha()
    window.blit(_GRID_SURFACE, (0, 0))


def draw_tech_corners(window, rect, color, length=22, width=3):
    """在矩形四角绘制 L 形科技边框角标"""
    x, y, w, h = rect
    # 左上
    pygame.draw.line(window, color, (x, y + length), (x, y), width)
    pygame.draw.line(window, color, (x, y), (x + length, y), width)
    # 右上
    pygame.draw.line(window, color, (x + w - length, y), (x + w, y), width)
    pygame.draw.line(window, color, (x + w, y), (x + w, y + length), width)
    # 左下
    pygame.draw.line(window, color, (x, y + h - length), (x, y + h), width)
    pygame.draw.line(window, color, (x, y + h), (x + length, y + h), width)
    # 右下
    pygame.draw.line(window, color, (x + w - length, y + h), (x + w, y + h), width)
    pygame.draw.line(window, color, (x + w, y + h - length), (x + w, y + h), width)


def draw_tech_panel(window, rect, border_color=COLOR_CYAN_DIM, fill=COLOR_PANEL):
    """绘制带细边框和角标的科技面板"""
    pygame.draw.rect(window, fill, rect)
    pygame.draw.rect(window, border_color, rect, 1)
    draw_tech_corners(window, rect, border_color)


# 文字 Surface 缓存：避免每帧重复 font.render（ARM 上 TrueType 光栅化开销极大）
# 注意：OCR 识别结果每帧变化，需限制缓存大小防止内存无限增长
_TEXT_SURFACE_CACHE = {}
_TEXT_CACHE_MAX = 200   # 最大缓存条目数


def _get_text_surface(font, text, color):
    """获取（或创建并缓存）文字 Surface，key=(font_id, text, color)"""
    font_id = id(font)
    key = (font_id, text, color)
    surf = _TEXT_SURFACE_CACHE.get(key)
    if surf is None:
        # 必须用 convert_alpha() 保留 alpha 通道（font.render 产生抗锯齿半透明边缘）
        # 用 convert() 会丢失 alpha，导致文字不显示或带黑色方块
        surf = font.render(text, True, color).convert_alpha()
        # 缓存溢出时清空（简单策略：识别结果频繁变化，旧条目无复用价值）
        if len(_TEXT_SURFACE_CACHE) >= _TEXT_CACHE_MAX:
            _TEXT_SURFACE_CACHE.clear()
        _TEXT_SURFACE_CACHE[key] = surf
    return surf


def draw_text(window, font, text, color, x, y, glow=False):
    """在指定位置绘制文字，glow=True 时带青色辉光效果（缓存优化）"""
    if glow:
        glow_surface = _get_text_surface(font, text, COLOR_CYAN_DIM)
        for dx, dy in ((2, 2), (-2, 2), (2, -2), (-2, -2)):
            window.blit(glow_surface, (x + dx, y + dy))
    text_surface = _get_text_surface(font, text, color)
    window.blit(text_surface, (x, y))


def draw_wrap_text(window, font, text, color, x, y, max_width, max_lines=None):
    """绘制自动换行文字；超过 max_lines 行时截断并加省略号，返回结束的 y 坐标"""
    lines = []
    line = ''
    for char in text:
        if line and font.size(line + char)[0] > max_width:
            lines.append(line)
            line = char
        else:
            line += char
    if line:
        lines.append(line)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and font.size(last + '…')[0] > max_width:
            last = last[:-1]
        lines[-1] = last + '…'
    for ln in lines:
        draw_text(window, font, ln, color, x, y)
        y += font.get_height() + 4
    return y


def cv2_to_surface(frame):
    """OpenCV 图像(BGR) 转为 Pygame 表面(RGB)"""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    surface = pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), 'RGB')
    return surface.convert()


def cv2_frame_to_surface_resized(frame, target_w, target_h):
    """将 cv2 帧缩放到目标尺寸并转为 Pygame Surface（ARM 优化）

    性能优化：用 cv2.resize（ARM NEON 加速）替代 pygame.transform.scale（软件渲染），
    在 Rockchip 平台上速度快 3-5 倍。
    """
    h, w = frame.shape[:2]
    if w != target_w or h != target_h:
        frame = cv2.resize(frame, (target_w, target_h))
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return pygame.image.frombuffer(rgb.tobytes(), (target_w, target_h), 'RGB').convert()


def blit_fit(window, surface, rect):
    """将图像等比缩放绘制到指定区域（保持宽高比，居中）"""
    scale = min(rect.w / surface.get_width(), rect.h / surface.get_height())
    new_w = max(1, int(surface.get_width() * scale))
    new_h = max(1, int(surface.get_height() * scale))
    scaled = pygame.transform.scale(surface, (new_w, new_h))
    x = rect.x + (rect.w - new_w) // 2
    y = rect.y + (rect.h - new_h) // 2
    window.blit(scaled, (x, y))


def normalize_text(text):
    """去掉空白字符，方便匹配"""
    return text.replace(' ', '').replace('\n', '').replace('\t', '').replace('\u3000', '')


def match_video(text):
    """在识别文字中查找匹配的视频，返回视频文件名；未匹配返回 None"""
    norm = normalize_text(text)
    for key in VIDEO_MAP:
        if key in norm:
            return VIDEO_MAP[key]
    return None


def fmt_time(seconds):
    """秒数格式化为 mm:ss"""
    seconds = max(0, int(seconds))
    return '%02d:%02d' % (seconds // 60, seconds % 60)


# ==================== OCR（主线程加载，后台线程推理） ====================

def init_ocr():
    """在主线程加载 OCR 识别引擎并返回识别器对象

    注意：text_recognition 已在文件开头最先导入（ppocr_system utils
    冲突规避），本函数仅创建识别器实例。
    """
    if not _TEXT_RECOGNITION_AVAILABLE:
        raise RuntimeError('text_recognition 模块导入失败：%s' % _TEXT_RECOGNITION_ERROR)
    return _TextRecognizer()


def prepare_ocr_frame(frame):
    """压缩识别帧宽度，加快识别速度（大号文字卡片足够）"""
    w = frame.shape[1]
    if w > OCR_FRAME_MAX_W:
        scale = OCR_FRAME_MAX_W * 1.0 / w
        return cv2.resize(frame, (OCR_FRAME_MAX_W, int(frame.shape[0] * scale)))
    return frame


def ocr_worker(stop_event, pause_event, lock, queue, result, state, recognizer):
    """后台文字识别线程：持续处理待识别帧（识别器在主线程创建）

    播放视频期间 pause_event 置位：丢弃排队中/识别中的画面，
    不写入任何识别结果，避免播放结束后残留结果导致重复触发。
    """
    state['ready'] = True
    print('OCR引擎已就绪')
    try:
        while not stop_event.is_set():
            try:
                frame = queue.get(timeout=0.2)
            except Empty:
                continue
            if pause_event.is_set():   # 播放视频期间：丢弃画面
                continue
            try:
                ocr_result = recognizer.recognize_text(frame, confidence_threshold=0.5)
            except Exception:
                import traceback
                print('文字识别异常：' + traceback.format_exc())
                continue
            if pause_event.is_set():   # 识别期间进入了播放状态：丢弃结果
                continue
            if ocr_result['success']:
                with lock:
                    result['text'] = ocr_result['text']
                    result['time'] = time.time()   # 结果产生时间戳
                    result['new'] = True
    finally:
        try:
            recognizer.cleanup()
        except Exception:
            pass


# ==================== 摄像头（纯 cv2 独占模式 + 采集线程） ====================

def _is_valid_frame(frame):
    """简单校验画面有效性（排除全黑/全白帧）

    项目记忆：摄像头采集线程中使用 gray.std() 进行帧检测在 ARM 设备上
    计算开销过大，应改用 gray.mean() 检测全黑/全白帧。
    """
    if frame is None:
        return False
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean = gray.mean()
    return 10 < mean < 245


def open_camera_device():
    """探测并打开摄像头，返回 cv2.VideoCapture 对象；失败返回 None"""
    for dev in CAMERA_DEVICES:
        cap = cv2.VideoCapture(dev)
        if not cap.isOpened():
            cap.release()
            continue
        # 尽量设置 MJPG 高帧率模式 + 1280x720
        try:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            # 关键：设置缓冲区为 1 帧，避免驱动内部缓冲堆积导致画面滞后
            # V4L2 后端默认缓冲 3-5 帧，这是摄像头预览"滞后"的最常见根因
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        # 验证能读到有效画面
        for _ in range(5):
            ret, frame = cap.read()
            if ret and _is_valid_frame(frame):
                print('摄像头已打开：' + str(dev))
                return cap
            time.sleep(0.05)
        cap.release()
    return None


class CameraThread:
    """摄像头采集线程：持续读取画面，主线程随时取最新帧"""

    def __init__(self, cap):
        self.cap = cap
        self.lock = threading.Lock()
        self.frame = None
        self.last_update = 0
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while self.running:
            # 关键：先 grab() 清空驱动内部缓冲区的陈旧帧，再 retrieve() 取最新帧
            # 即使 CAP_PROP_BUFFERSIZE=1 不生效，这也能保证拿到的是最新画面，
            # 彻底消除"画面滞后几秒"的问题（V4L2 默认缓冲 3-5 帧）
            # 限制最多丢弃 5 帧，防止某些后端 grab() 一直返回 True 导致死循环
            discard_count = 0
            while discard_count < 5 and self.cap.grab():
                discard_count += 1
            ret, frame = self.cap.retrieve()
            if not ret:
                # retrieve 失败时回退到 read
                ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.frame = frame
                    self.last_update = time.time()
            # 短暂休眠避免 CPU 占满；cap.grab 阻塞等待新帧时本身不耗 CPU
            time.sleep(0.02)

    def start(self):
        self.thread.start()

    def get_frame(self):
        """获取最新一帧（返回副本，避免与采集线程竞争）"""
        with self.lock:
            frame = self.frame
        return frame.copy() if frame is not None else None

    def is_alive(self, now):
        """最近 3 秒内是否仍能取到画面"""
        return (now - self.last_update) < 3

    def stop(self):
        self.running = False
        self.thread.join(timeout=1.0)
        self.cap.release()


# ==================== 音频（视频内嵌音轨） ====================

def extract_audio(video_file):
    """用 ffmpeg 从视频中提取音轨为临时 wav 文件，成功返回 wav 路径，失败返回 None"""
    wav_path = os.path.join(tempfile.gettempdir(),
                            os.path.splitext(os.path.basename(video_file))[0] + '_audio.wav')
    try:
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', video_file, '-vn',
             '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', wav_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if result.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
            return wav_path
    except Exception as e:
        print('音轨提取异常：' + str(e))
    return None


def audio_start(video_file):
    """播放视频内嵌音轨；失败时返回 False（视频将静音播放）"""
    if not AUDIO_ENABLED:
        return False
    # mixer 已在程序启动时初始化；若初始化失败则静音播放
    if pygame.mixer.get_init() is None:
        print('pygame.mixer 未初始化，本次静音播放画面')
        return False
    try:
        # 优先：ffmpeg 提取音轨后播放（支持暂停/继续）
        wav_path = extract_audio(video_file)
        if wav_path:
            pygame.mixer.music.load(wav_path)
            pygame.mixer.music.play()
            return True
        # 兜底：直接尝试加载 mp4（个别环境 SDL 可直接解码）
        try:
            pygame.mixer.music.load(video_file)
            pygame.mixer.music.play()
            return True
        except Exception:
            print('警告：无法播放视频内嵌音轨（请确认系统已安装 ffmpeg），本次静音播放画面')
    except Exception as e:
        print('音频初始化失败，本次静音播放画面：' + str(e))
    return False


def audio_pause():
    """暂停声音"""
    try:
        if pygame.mixer.get_init() is not None:
            pygame.mixer.music.pause()
    except Exception:
        pass


def audio_resume():
    """继续声音"""
    try:
        if pygame.mixer.get_init() is not None:
            pygame.mixer.music.unpause()
    except Exception:
        pass


def audio_stop():
    """停止声音并卸载音轨资源（释放内存，避免播放结束后 mixer 持续占用 RAM）"""
    try:
        if pygame.mixer.get_init() is not None:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()   # 关键：释放已加载的 wav 数据
    except Exception:
        pass


# ==================== 按钮控件 ====================

class Button:
    """科技风按钮：深色底 + 霓虹描边 + 四角角标"""

    def __init__(self, x, y, w, h, text, font, accent_color, text_color=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.font = font
        self.accent_color = accent_color
        self.text_color = text_color if text_color is not None else COLOR_TEXT
        self.text = text

    def is_clicked(self, pos):
        return self.rect.collidepoint(pos)

    def draw(self, window):
        inner = self.rect.inflate(-10, -10)
        pygame.draw.rect(window, (10, 18, 34), inner, border_radius=6)
        pygame.draw.rect(window, self.accent_color, inner, 2, border_radius=6)
        draw_tech_corners(window, self.rect, self.accent_color, length=16, width=3)
        # 使用文字缓存（按钮文字「暂停/继续/停止/退出程序」每帧重复，缓存命中率 100%）
        text_surface = _get_text_surface(self.font, self.text, self.text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        window.blit(text_surface, text_rect)


# ==================== 主程序 ====================

def main():
    window = pygame.display.set_mode(size=(WINDOW_W, WINDOW_H), flags=0, depth=0)
    pygame.display.set_caption('文字识别触发视频播放 · TECH SYSTEM')
    clock = pygame.time.Clock()

    font_title = load_font(54)
    font_normal = load_font(34)
    font_small = load_font(26)
    font_button = load_font(38)
    font_status = load_font(24)

    # ---------- 启动画面（在耗时初始化前先显示） ----------
    window.fill(COLOR_BG)
    draw_grid(window)
    draw_text(window, font_title, '文字识别 · 视频点播', COLOR_CYAN, 40, 28, glow=True)
    draw_text(window, font_status, 'TEXT RECOGNITION VIDEO SYSTEM', COLOR_DIM, 42, 100)
    draw_text(window, font_normal, 'SYSTEM BOOTING ...', COLOR_CYAN, 800, 430, glow=True)
    draw_text(window, font_status, '正在加载 OCR 识别引擎与摄像头，请稍候', COLOR_DIM, 700, 520)
    pygame.display.flip()

    # ---------- 加载 OCR 识别引擎（主线程，且必须先于其他SDK模块） ----------
    ocr_recognizer = None
    ocr_ok = False
    try:
        ocr_recognizer = init_ocr()
        ocr_ok = True
        print('OCR引擎加载完成')
    except Exception:
        import traceback
        print('OCR引擎加载失败：' + traceback.format_exc())

    # ---------- 打开摄像头（纯 cv2 独占模式 + 采集线程） ----------
    cam_thread = None
    cap = open_camera_device()
    if cap is not None:
        cam_thread = CameraThread(cap)
        cam_thread.start()
    camera_ok = cam_thread is not None

    # ---------- 后台 OCR 识别线程（识别器已就绪，只做推理） ----------
    result_lock = threading.Lock()
    ocr_result = {'text': '', 'new': False, 'time': 0}   # time=结果产生时间戳（新鲜度校验用）
    ocr_state = {'ready': False, 'error': ''}
    ocr_queue = Queue(maxsize=1)
    ocr_stop = threading.Event()
    ocr_pause = threading.Event()        # 播放视频期间置位，OCR 丢弃画面
    ocr_thread = None
    if ocr_ok:
        ocr_thread = threading.Thread(target=ocr_worker,
                                      args=(ocr_stop, ocr_pause, result_lock, ocr_queue,
                                            ocr_result, ocr_state, ocr_recognizer),
                                      daemon=True)
        ocr_thread.start()
    else:
        ocr_state['error'] = 'OCR引擎加载失败'

    # ---------- 界面按钮 ----------
    btn_exit = Button(WINDOW_W - 330, 22, 260, 78, '退出程序', font_button, COLOR_RED)
    btn_pause = Button(720, 960, 240, 90, '暂停', font_button, COLOR_GREEN)
    btn_stop = Button(990, 960, 240, 90, '停止', font_button, COLOR_ORANGE)

    # ---------- 运行状态 ----------
    state = 'recognize'        # recognize=识别界面  play=播放界面
    vd = None                  # 视频对象
    playing_name = ''          # 正在播放的视频文件名（含路径）
    paused = False             # 是否暂停
    last_surface = None        # 最近一帧视频画面
    next_frame_time = 0        # 下一帧播放时间
    video_fps = 25             # 视频帧率
    video_duration = 0         # 视频总时长（秒）
    play_resume_time = 0       # 本次持续播放的起点时间
    play_elapsed = 0           # 已播放时长（不含暂停）
    audio_playing = False      # 音轨是否已启动
    recognized_text = '等待识别结果...'
    last_finish_time = 0       # 视频播放结束/停止的时间（防重复触发）
    running = True
    # 摄像头预览 Surface 缓存：仅在帧更新时重新转换，避免每轮循环重复 cvtColor+convert
    cam_surface = None         # 缓存的摄像头预览 Surface
    last_cam_ts = 0            # 上次转换时摄像头帧的时间戳

    def get_elapsed():
        """当前已播放时长（暂停期间不计时）"""
        if paused:
            return play_elapsed
        return play_elapsed + (time.time() - play_resume_time)

    def back_to_recognize():
        """停止播放，返回识别界面"""
        nonlocal state, vd, paused, playing_name, last_surface, audio_playing, recognized_text
        nonlocal cam_surface, last_cam_ts
        audio_stop()
        audio_playing = False
        if vd is not None:
            vd.release()
            vd = None
        state = 'recognize'
        paused = False
        playing_name = ''
        last_surface = None
        # 清空摄像头预览缓存，强制下次渲染重新转换（避免播放后用到陈旧 Surface）
        cam_surface = None
        last_cam_ts = 0
        # 强制回收视频帧 Surface 对象（避免大尺寸画面堆积导致内存压力）
        # 播放期间产生的视频帧 Surface 在 ARM 设备上不会立即被 GC 回收，
        # 累积的内存占用会让摄像头预览渲染变慢（"播放返回后滞后"的根因）
        import gc
        gc.collect()
        # 恢复 OCR：清空可能遗留的识别结果，重置显示文字
        ocr_pause.clear()
        with result_lock:
            ocr_result['new'] = False
            ocr_result['text'] = ''
            ocr_result['time'] = 0
        recognized_text = '等待识别结果...'

    def start_play(video_file):
        """开始播放指定视频（画面 + 内嵌音轨）"""
        nonlocal vd, state, paused, playing_name, video_fps, video_duration, next_frame_time, audio_playing, play_elapsed, play_resume_time
        # 暂停 OCR：丢弃排队中/识别中的画面并清空遗留结果，
        # 避免播放结束后残留关键字结果导致重复触发
        ocr_pause.set()
        try:
            ocr_queue.get_nowait()
        except Empty:
            pass
        with result_lock:
            ocr_result['new'] = False
            ocr_result['text'] = ''
            ocr_result['time'] = 0
        vd = cv2.VideoCapture()
        vd.open(video_file)
        if not vd.isOpened():
            print('无法打开视频：' + video_file)
            vd.release()
            vd = None
            ocr_pause.clear()   # 打开失败则恢复OCR，避免识别一直暂停
            return
        fps = vd.get(cv2.CAP_PROP_FPS)
        video_fps = fps if (fps and fps > 0 and fps == fps) else 25
        frame_count = vd.get(cv2.CAP_PROP_FRAME_COUNT)
        video_duration = frame_count / video_fps if (frame_count and frame_count > 0) else 0
        state = 'play'
        playing_name = video_file
        paused = False
        btn_pause.text = '暂停'
        next_frame_time = time.time()
        play_elapsed = 0
        play_resume_time = time.time()
        print('开始播放：' + video_file)
        audio_playing = audio_start(video_file)

    while running:
        now = time.time()

        # ==================== 事件处理 ====================
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                if state == 'recognize':
                    if btn_exit.is_clicked(pos):
                        print('点击退出程序')
                        running = False
                else:  # 播放界面
                    if btn_pause.is_clicked(pos):
                        if paused:  # 继续
                            paused = False
                            btn_pause.text = '暂停'
                            play_resume_time = time.time()
                            audio_resume()
                            print('视频继续播放')
                        else:  # 暂停
                            paused = True
                            btn_pause.text = '继续'
                            play_elapsed = play_elapsed + (time.time() - play_resume_time)
                            audio_pause()
                            print('视频已暂停')
                    elif btn_stop.is_clicked(pos):
                        print('点击停止，返回识别界面')
                        back_to_recognize()
                        last_finish_time = time.time()

        # ==================== 绘制界面 ====================
        if state == 'recognize':
            window.fill(COLOR_BG)
            draw_grid(window)
            # ---------------- 识别界面 ----------------
            # 标题区（紧凑：标题与副标题同行，退出按钮在右上角不与面板重叠）
            draw_text(window, font_title, '文字识别 · 视频点播', COLOR_CYAN, 40, 24, glow=True)
            draw_text(window, font_status, 'TEXT RECOGNITION VIDEO SYSTEM', COLOR_DIM, 620, 58)

            # 左侧：摄像头预览（科技边框，标签内嵌在顶部条上）
            # 框高 = 画面区高(PREVIEW_H) + 顶部状态条40px，整体占满主区域
            preview_rect = pygame.Rect(40, 112, PREVIEW_W, PREVIEW_H + 40)
            feed_rect = pygame.Rect(preview_rect.x + 12, preview_rect.y + 48,
                                    preview_rect.w - 24, preview_rect.h - 60)

            # 获取最新摄像头画面（采集线程缓存，不阻塞）
            # 性能优化：仅在摄像头帧更新时执行 resize+cvtColor+convert（约 20fps），
            # 其余循环迭代直接复用缓存的 cam_surface，避免 50fps 重复转换
            cam_ts_now = cam_thread.last_update if camera_ok else 0
            frame = None
            if camera_ok and cam_ts_now != last_cam_ts:
                frame = cam_thread.get_frame()
                last_cam_ts = cam_ts_now
                if frame is not None:
                    try:
                        # 直接缩放到 feed_rect 尺寸（ARM NEON 加速），
                        # 后续 blit 无需再调用 pygame.transform.scale
                        cam_surface = cv2_frame_to_surface_resized(
                            frame, feed_rect.w, feed_rect.h)
                    except Exception:
                        pass

            # 连续识别：OCR 引擎空闲（队列空）就提交最新画面（仅在新帧到来时提交）
            if (frame is not None and ocr_state['ready']
                    and now - last_finish_time >= RETRIGGER_DELAY):
                try:
                    ocr_queue.get_nowait()   # 丢弃尚未处理的旧画面
                except Empty:
                    pass
                ocr_queue.put(prepare_ocr_frame(frame))

            # 处理后台识别结果（新鲜度校验：只接受本次返回识别界面之后
            # 产生的新结果；播放前遗留的陈旧结果即使漏网也会被时间戳拒绝，
            # 彻底杜绝「停止后自动再播一次」）
            need_start = None
            with result_lock:
                if ocr_result['new']:
                    ocr_result['new'] = False
                    if ocr_result['time'] >= last_finish_time:
                        recognized_text = ocr_result['text']
                        print('识别结果：' + recognized_text)
                        need_start = match_video(recognized_text)
                    else:
                        print('丢弃播放前遗留的陈旧识别结果')
            if need_start:
                print('识别到目标文字，开始播放视频')
                start_play(need_start)

            draw_tech_panel(window, preview_rect, COLOR_CYAN_DIM)
            bar_rect = pygame.Rect(preview_rect.x, preview_rect.y, preview_rect.w, 40)
            pygame.draw.rect(window, (10, 18, 34), bar_rect)
            pygame.draw.line(window, COLOR_CYAN_DIM, bar_rect.bottomleft, bar_rect.bottomright, 1)
            draw_text(window, font_status, '■ CAMERA FEED', COLOR_CYAN, preview_rect.x + 16, preview_rect.y + 8)
            draw_text(window, font_status, 'TEXT OCR · LIVE', COLOR_DIM, preview_rect.right - 210, preview_rect.y + 8)
            # feed_rect 已在上方定义（与 cam_surface 尺寸严格一致）
            # 直接 blit 预缩放好的 cam_surface，跳过 pygame.transform.scale
            if cam_surface is not None:
                window.blit(cam_surface, (feed_rect.x, feed_rect.y))
            else:
                draw_text(window, font_normal, '摄像头未连接或未打开', COLOR_DIM,
                          feed_rect.centerx - 170, feed_rect.centery - 24)

            # 右侧：识别结果 + 触发规则面板（与预览框等高）
            panel_rect = pygame.Rect(1350, 112, 530, PREVIEW_H + 40)
            draw_tech_panel(window, panel_rect, COLOR_CYAN_DIM)

            draw_text(window, font_normal, '识别结果', COLOR_CYAN, panel_rect.x + 24, panel_rect.y + 28, glow=True)
            terminal_rect = pygame.Rect(panel_rect.x + 24, panel_rect.y + 84, panel_rect.w - 48, 232)
            pygame.draw.rect(window, COLOR_TERMINAL, terminal_rect)
            pygame.draw.rect(window, COLOR_CYAN_DIM, terminal_rect, 1)
            if cam_surface is None:
                draw_text(window, font_small, '> 等待摄像头画面...', COLOR_DIM, terminal_rect.x + 16, terminal_rect.y + 14)
            elif not ocr_state['ready']:
                draw_text(window, font_small, '> OCR引擎加载中...', COLOR_DIM, terminal_rect.x + 16, terminal_rect.y + 14)
            else:
                draw_wrap_text(window, font_small, '> ' + recognized_text, COLOR_TEXT,
                               terminal_rect.x + 16, terminal_rect.y + 14,
                               terminal_rect.w - 32, max_lines=5)

            draw_text(window, font_normal, '触发规则', COLOR_CYAN, panel_rect.x + 24, panel_rect.y + 368, glow=True)
            hint_y = panel_rect.y + 430
            for key, video in VIDEO_MAP.items():
                draw_text(window, font_small, '▸ 「' + key + '」 → ' + video.split('/')[-1],
                          COLOR_DIM, panel_rect.x + 24, hint_y)
                hint_y += 58

            # 面板底部：分隔线 + 提示
            pygame.draw.line(window, COLOR_GRID,
                             (panel_rect.x + 24, panel_rect.y + 680),
                             (panel_rect.x + panel_rect.w - 24, panel_rect.y + 680), 1)
            draw_text(window, font_status, '识别到以上关键字将自动播放对应视频', COLOR_DIM,
                      panel_rect.x + 24, panel_rect.y + 704)

            # 底部状态条
            cam_online = camera_ok and cam_thread.is_alive(now)
            cam_text = '● 摄像头：在线' if cam_online else '● 摄像头：离线'
            cam_color = COLOR_GREEN if cam_online else COLOR_RED
            draw_text(window, font_status, cam_text, cam_color, 40, 908)
            if ocr_state['ready']:
                draw_text(window, font_status, '● OCR引擎：运行中', COLOR_GREEN, 360, 908)
            elif ocr_state['error']:
                draw_text(window, font_status, '● OCR引擎：加载失败', COLOR_RED, 360, 908)
            else:
                draw_text(window, font_status, '● OCR引擎：加载中...', COLOR_ORANGE, 360, 908)
            draw_text(window, font_status, '● 识别模式：实时', COLOR_DIM, 720, 908)
            draw_text(window, font_status, '● 声音：' + ('视频内嵌音轨' if AUDIO_ENABLED else '关闭'),
                      COLOR_DIM, 1080, 908)
            draw_text(window, font_status, '● 系统：正常', COLOR_GREEN, 1440, 908)

            # 底部操作提示与版本信息（填充底部空间，整体更均衡）
            draw_text(window, font_status, '提示：将「好搭智眼」「芦丁鸡」「信息科技实验板」字样对准摄像头，识别成功将自动播放',
                      COLOR_DIM, 40, 980)
            draw_text(window, font_status, '好搭AI派 · 文字识别视频点播系统', COLOR_DIM, 40, 1048)
            draw_text(window, font_status, 'TECH SYSTEM v2.0', COLOR_CYAN_DIM, 1660, 1048)

            # 退出程序按钮（右上角，与面板保持间距）
            btn_exit.draw(window)

        else:
            # ---------------- 播放界面 ----------------
            # 播放界面直接填充黑色（跳过 COLOR_BG + 网格线，减少软件渲染开销）
            window.fill((0, 0, 0))

            # 视频画面区域（上方大区域）
            video_rect = pygame.Rect(0, 0, WINDOW_W, WINDOW_H - 120)
            fit_rect = video_rect.inflate(-30, -30)

            # 读取视频帧（暂停时不读取新帧）
            if vd is not None and not paused and now >= next_frame_time:
                ret, frame = vd.read()
                if not ret:
                    print('视频播放结束，返回识别界面')
                    back_to_recognize()
                    last_finish_time = time.time()
                else:
                    next_frame_time = now + 1.0 / video_fps
                    try:
                        # 性能优化：用 cv2.resize 预缩放到目标尺寸（ARM NEON 加速），
                        # 后续直接 blit 即可，避免每帧调用 pygame.transform.scale
                        scale = min(fit_rect.w / frame.shape[1],
                                    fit_rect.h / frame.shape[0])
                        new_w = max(1, int(frame.shape[1] * scale))
                        new_h = max(1, int(frame.shape[0] * scale))
                        resized = cv2.resize(frame, (new_w, new_h))
                        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                        last_surface = pygame.image.frombuffer(
                            rgb.tobytes(), (new_w, new_h), 'RGB').convert()
                    except Exception:
                        pass

            # 直接 blit 预缩放好的视频帧（无需每帧 pygame.transform.scale 重复缩放）
            if last_surface is not None:
                x = fit_rect.x + (fit_rect.w - last_surface.get_width()) // 2
                y = fit_rect.y + (fit_rect.h - last_surface.get_height()) // 2
                window.blit(last_surface, (x, y))

            draw_tech_corners(window, pygame.Rect(30, 30, WINDOW_W - 60, WINDOW_H - 180),
                              COLOR_CYAN_DIM, length=26, width=3)
            draw_text(window, font_status, '▶ NOW PLAYING : ' + playing_name.split('/')[-1],
                      COLOR_CYAN, 60, 48, glow=True)

            # 进度条
            elapsed = get_elapsed()
            progress = (elapsed / video_duration) if video_duration > 0 else 0
            progress = max(0.0, min(1.0, progress))
            bar_rect = pygame.Rect(60, WINDOW_H - 160, WINDOW_W - 120, 6)
            pygame.draw.rect(window, (30, 45, 70), bar_rect)
            pygame.draw.rect(window, COLOR_CYAN,
                             pygame.Rect(bar_rect.x, bar_rect.y, int(bar_rect.w * progress), bar_rect.h))
            draw_text(window, font_status, fmt_time(elapsed) + ' / ' + fmt_time(video_duration),
                      COLOR_DIM, 60, WINDOW_H - 145)
            pause_state = '已暂停' if paused else '播放中'
            pause_color = COLOR_ORANGE if paused else COLOR_GREEN
            draw_text(window, font_status, '状态：' + pause_state, pause_color, 300, WINDOW_H - 145)

            # 暂停/继续、停止按钮（下方控制栏）
            btn_pause.draw(window)
            btn_stop.draw(window)

        pygame.display.flip()
        clock.tick(30)   # 限制主循环帧率 30fps，减少软件渲染开销

    # ==================== 退出清理 ====================
    ocr_stop.set()
    if ocr_thread is not None:
        ocr_thread.join(timeout=1.0)
    audio_stop()
    if vd is not None:
        vd.release()
    if cam_thread is not None:
        cam_thread.stop()
    pygame.quit()
    print('程序已退出')
    try:
        _debug_log_fp.close()
    except Exception:
        pass


if __name__ == '__main__':
    main()
