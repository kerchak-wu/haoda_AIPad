# -*- coding: utf-8 -*-
"""
人数实时统计程序 - 好搭AI派
============================
功能说明：
  1. 视觉系统摄像头实时统计画面内的人数（当前现有人数）
  2. 实时显示：当前人数、历史峰值、运行时长
  3. 提供最近 10 条人数变化记录（增加/减少，带时间戳）
  4. 支持一键重置峰值与变化记录
  5. 无论有人进出，始终反映画面中真实的人数

技术方案：
  使用目标检测算法（object_detection），统计画面中类别为 "person/人" 的目标数量。
  该算法直接数出画面里现有人数，与人流计数的"进入/离开累计"无关，结果准确。

硬件接线：
  - USB 外接摄像头接在扩展板 USB 口上（由视觉系统管理，不要再用 cv2.VideoCapture）
  - 好搭AI派扩展板(ESP32)（本程序不控制外设，但扩展板异常会导致摄像头不可用，需保持初始化）

依赖库：
  pygame, cv2(opencv, 仅用于图像格式转换), numpy, ESP32, camera_vision_system_v3(好搭AI派自带)
  以上均为环境自带库，无需额外安装。

参考范例：
  - 好搭AI派范例代码 5.AI视觉算法 17.目标检测（get_object_detection_count/class_name）
  - 人脸识别灯效.py（全托管模式架构、日志、采集线程、UI 布局）

重要说明：
  1. 目标检测属于"连续检测"，必须使用全托管模式（V3 管理摄像头），禁用 cv2.VideoCapture
  2. 目标检测不知道"谁是谁"（无身份识别），只统计人数，不区分个体
  3. 现有人数 = 画面中类别为 person/人的目标数量，实时反映在场人数
"""

import os
# 强制 libGL 使用软件渲染，避免 rockchip 平台 GPU 驱动加载失败
# 参考方案第 7 章 Rockchip 平台兼容性补丁
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

import sys
import time
import threading
import datetime as _datetime

import pygame
import cv2
import numpy as np

from ESP32 import *
from camera_vision_system_v3 import create_vision_system_v3


# ===================== 日志输出（控制台 + 文件）=====================
# 参照人脸识别灯效.py 的日志方案：logs/ 目录、程序名_YYYYMMDD.log、追加模式、块缓冲
import os as _os
_LOG_DIR = 'logs'
if not _os.path.exists(_LOG_DIR):
    try:
        _os.makedirs(_LOG_DIR)
    except Exception:
        pass
_LOG_FILE = _os.path.join(
    _LOG_DIR,
    '人数实时统计_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
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

# 字体路径（好搭AI派系统字体，与人脸识别灯效.py 一致）
FONT_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'

# 摄像头配置（采集分辨率须与 create_vision_system_v3 的 width/height 一致）
CAMERA_W, CAMERA_H = 1280, 720
CAM_DISP_W, CAM_DISP_H = 880, 660

# ---- 界面配色（浅色系，与人脸识别灯效.py 一致）----
BG_TOP = (135, 206, 235)        # 天空蓝
BG_BOTTOM = (220, 240, 255)     # 浅蓝白
PANEL_COLOR = (255, 255, 255)   # 白色面板
PANEL_BORDER = (100, 149, 237)  # 矢车菊蓝
TITLE_COLOR = (25, 60, 130)     # 深蓝
TEXT_COLOR = (50, 50, 60)       # 深灰
SUBTLE_COLOR = (120, 130, 150)  # 灰色
ACCENT_COLOR = (255, 140, 0)    # 橙色
SUCCESS_COLOR = (60, 180, 80)   # 绿色（人数增加）
ERROR_COLOR = (220, 80, 80)     # 红色（人数减少）
EXIT_COLOR = (220, 80, 80)
EXIT_HOVER = (255, 100, 100)
RESET_COLOR = (70, 110, 200)
RESET_HOVER = (100, 149, 237)
CURRENT_COLOR = (255, 140, 0)   # 现有人数-橙色突出


# ===================== 硬件初始化 =====================
# 严格参照范例代码：ESP32 初始化 + 异常处理
# 本程序不控制外设，但摄像头接在扩展板 USB 口上，扩展板异常会导致摄像头不可用
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    print('警告：扩展板连接异常，摄像头接在扩展板 USB 口上，摄像头可能不可用')


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
class PeopleCounterApp:
    """人数实时统计 Pygame 界面应用

    摄像头完全由视觉系统管理（open_camera + capture_frame），
    不使用 cv2 VideoCapture，避免设备冲突（全托管模式）。
    检测流程严格参照范例代码 5.17 目标检测。
    """

    TITLE_H = 130
    FOOTER_H = 110

    def __init__(self):
        # 分段初始化（不调用 pygame.init()），避免 pygame.mixer 导致原生崩溃
        # 参考方案第 7 章 Rockchip 平台兼容性补丁
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('人数实时统计')
        self.clock = pygame.time.Clock()

        # 字体（1920x1080 下适度增大，参考人脸识别灯效.py）
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 64)
        self.font_sub = pygame.font.Font(FONT_PATH, 32)
        self.font_item = pygame.font.Font(FONT_PATH, 30)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_small = pygame.font.Font(FONT_PATH, 24)
        self.font_status = pygame.font.Font(FONT_PATH, 26)
        self.font_big = pygame.font.Font(FONT_BOLD_PATH, 56)
        self.font_huge = pygame.font.Font(FONT_BOLD_PATH, 120)  # 当前人数超大字
        self.font_log = pygame.font.Font(FONT_PATH, 26)         # 变化记录

        # 背景
        try:
            bg_raw = pygame.image.load('images/1.jpg')
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception:
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # 布局：摄像头左、统计面板右，两面板等高对齐
        panel_h = HEIGHT - self.TITLE_H - 20 - self.FOOTER_H  # 820
        self.cam_rect = pygame.Rect(60, self.TITLE_H + 20,
                                    CAM_DISP_W + 40, panel_h)
        self.info_rect = pygame.Rect(self.cam_rect.right + 40, self.TITLE_H + 20,
                                     WIDTH - self.cam_rect.right - 40 - 60,
                                     panel_h)

        # 退出按钮（右上角标题栏内，参考人脸识别灯效.py 尺寸）
        self.btn_exit = Button((WIDTH - 280, 30, 240, 70),
                               '退出程序', EXIT_COLOR, EXIT_HOVER)
        # 重置按钮（信息面板顶部右侧）
        self.btn_reset = Button((self.info_rect.right - 220, self.info_rect.y + 18,
                                 200, 56),
                                '重置峰值', RESET_COLOR, RESET_HOVER)

        # 统计状态
        self.peak_current = 0          # 历史峰值现有人数
        self.start_time = time.time()  # 程序运行起始时间
        self.change_log = []           # 人数变化记录 [(time_str, delta, new_count), ...]
        self.last_count = 0            # 上次检测到的人数（用于变化检测）

        # 初始化视觉系统（加载阶段显示进度画面，避免黑屏）
        self._draw_loading_screen('正在初始化视觉系统，请稍候...')
        print('正在初始化视觉系统...')
        self._init_vision_system()

        # 状态
        self.running = True
        self.raw_frame = None
        self.frame_lock = threading.Lock()
        self.capture_fail = 0
        self.status_msg = '正在启动人数统计...'
        self.status_color = SUBTLE_COLOR

        # 当前显示数值
        self.disp_current = 0

        # 启动后台采集线程（固定 0.15s 间隔，给 V4L2 后台检测线程留出缓冲区访问时间）
        self.capture_thread_running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _draw_loading_screen(self, msg):
        """初始化阶段加载画面，避免长时间黑屏

        在 _init_vision_system 各阶段之间调用，分步显示进度。
        同时处理窗口关闭事件，避免初始化期间无法退出。
        """
        self.screen.blit(self.bg, (0, 0))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((255, 255, 255, 200))
        self.screen.blit(overlay, (0, 0))

        text = self.font_title.render(msg, True, TITLE_COLOR)
        self.screen.blit(text, (WIDTH // 2 - text.get_width() // 2,
                                HEIGHT // 2 - 60))
        sub = self.font_sub.render('请稍候...', True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2,
                               HEIGHT // 2 + 20))
        pygame.display.flip()

        # 处理窗口事件，避免初始化期间窗口无响应
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

    def _detect_camera_id(self):
        """按 41、40、42 顺序探测可用的摄像头设备号

        使用 cv2.VideoCapture + 字符串路径 + CAP_V4L2 后端快速预检测，
        毫秒级完成，绕过 FFMPEG 后端越界延迟（int 模式下约 6 秒/次）。
        找到可用设备号后返回 int，供 V3 SDK 的 camera_id 使用。

        检测步骤（每个候选）：
          1. os.path.exists 检查 /dev/videoN 节点
          2. CAP_V4L2 + 字符串路径打开
          3. 最多读 5 帧，用 gray.mean() 验证非全黑/全白
        释放后等待 0.3s 避免设备忙状态（参考方案要求）。

        Returns:
            int: 可用设备号；全部不可用时返回 None
        """
        candidates = [41, 40, 42]
        for cam_id in candidates:
            dev_path = '/dev/video%d' % cam_id
            if not os.path.exists(dev_path):
                print('[摄像头探测] %s 节点不存在，跳过' % dev_path)
                continue
            cap = cv2.VideoCapture(dev_path, cv2.CAP_V4L2)
            if not cap.isOpened():
                print('[摄像头探测] %s 无法打开，跳过' % dev_path)
                cap.release()
                continue
            # 最多读 5 帧验证有效性（mean 比 std 在 ARM 上更快）
            valid = False
            for _ in range(5):
                ret, frame = cap.read()
                if ret and frame is not None and hasattr(frame, 'shape') and len(frame.shape) == 3:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    mean_val = gray.mean()
                    if 5 < mean_val < 250:
                        valid = True
                        break
            cap.release()
            if valid:
                print('[摄像头探测] ✓ %s 可用（ID=%d）' % (dev_path, cam_id))
                # 释放后等待 0.3s 避免设备忙状态
                time.sleep(0.3)
                return cam_id
            else:
                print('[摄像头探测] %s 可打开但无有效帧，跳过' % dev_path)
        return None

    def _init_vision_system(self):
        """初始化视觉系统并打开摄像头（严格参照范例代码 5.17 目标检测）

        关键：不使用 cv2 VideoCapture，摄像头完全由视觉系统管理。
        目标检测属于连续检测，必须使用全托管模式。

        摄像头探测：先按 41、40、42 顺序用 CAP_V4L2+字符串路径快速预检测
        （毫秒级），找到可用设备号后传给 V3 SDK，避免 SDK 用 -1 自动探测
        或传不可用 ID 导致回退浪费。
        注：V3 SDK 内部用 int 调 cv2.VideoCapture(N)，FFMPEG 后端越界
        延迟（~6秒）无法在应用层绕过，但预检测确保只传可用 ID。
        """
        # 阶段 1：探测可用摄像头设备号
        self._draw_loading_screen('正在探测摄像头设备（41/40/42）...')
        print('正在探测摄像头设备...')
        cam_id = self._detect_camera_id()
        if cam_id is None:
            print('未找到可用摄像头设备（41/40/42 均不可用）')
            self.camera_ok = False
            self.vision_system = None
            return

        # 阶段 2：初始化目标检测器
        self._draw_loading_screen('正在初始化目标检测器...')
        self.vision_system = create_vision_system_v3(
            camera_id=cam_id, width=1280, height=720,
            enable_basic=False, enable_advanced=False
        )
        self.vision_system.detection_config.enable_object_detection = True
        self.vision_system._init_detectors()
        print('object_detection 算法已启用')
        # 用于首次检测到目标时打印类别名，确认"人"的实际类别字符串
        self._det_class_logged = False

        # 阶段 3：打开摄像头
        self._draw_loading_screen('正在打开摄像头（ID=%d）...' % cam_id)
        print('正在打开视觉系统摄像头（ID=%d）...' % cam_id)
        if self.vision_system.open_camera():
            print('视觉系统摄像头已打开')
            self.camera_ok = True
        else:
            print('视觉系统摄像头打开失败')
            self.camera_ok = False

        # 阶段 4：启动后台检测（show_preview=False，不弹 OpenCV 窗口）
        if self.camera_ok:
            self._draw_loading_screen('正在启动后台检测...')
            self.vision_system.threaded_system.start_background_detection(show_preview=False)
            print('目标检测后台检测已启动')

    def _capture_loop(self):
        """后台线程：固定间隔采集帧用于界面显示

        参照人脸识别灯效.py：
        1. 固定 0.15s 睡眠（无论成功失败），不紧循环调用
        2. 帧有效性验证，跳过损坏帧
        3. 与主线程的 refresh_results() 不冲突（后者只读缓存，不访问 V4L2）
        """
        time.sleep(0.5)  # 启动后等待 0.5s 让后台检测线程先稳定
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
            time.sleep(0.15)

    def check_counter(self):
        """检查人数（严格参照范例代码 5.17 目标检测）

        在主循环中调用，轮询 result_accessor 获取最新检测结果。
        统计画面中类别为 person/人 的目标数量作为现有人数。
        """
        try:
            self.vision_system.result_accessor.refresh_results()
            person_count = 0
            det_count = self.vision_system.result_accessor.get_object_detection_count()
            if det_count and det_count > 0:
                for i in range(det_count):
                    try:
                        cls = self.vision_system.result_accessor.get_object_detection_class_name(i)
                        if cls is None:
                            continue
                        # 首次打印类别名，便于确认模型实际使用的标签（person / 人）
                        if not self._det_class_logged:
                            print('[调试] 目标检测类别示例: %s' % cls)
                            self._det_class_logged = True
                        # 兼容中英文类别名
                        cls_str = str(cls).lower()
                        if 'person' in cls_str or cls == '人':
                            person_count += 1
                    except Exception:
                        pass

            self.disp_current = person_count

            # 峰值更新
            if self.disp_current > self.peak_current:
                self.peak_current = self.disp_current

            # 人数变化检测：与上次对比，记录增减事件
            if self.disp_current != self.last_count:
                delta = self.disp_current - self.last_count
                # 仅在已初始化（last_count>=0 且非首次启动）时记录
                if self.last_count >= 0 and not self.status_msg.startswith('正在启动'):
                    now_str = _datetime.datetime.now().strftime('%H:%M:%S')
                    self.change_log.insert(0, (now_str, delta, self.disp_current))
                    if delta > 0:
                        print('[变化] +%d 人（当前 %d 人）' % (delta, self.disp_current))
                    else:
                        print('[变化] %d 人（当前 %d 人）' % (delta, self.disp_current))
                    # 仅保留最近 10 条
                    if len(self.change_log) > 10:
                        self.change_log = self.change_log[:10]
                self.last_count = self.disp_current

            # 首次成功检测后更新状态
            if self.status_msg.startswith('正在启动'):
                self.status_msg = '正在统计中...'
                self.status_color = SUCCESS_COLOR
        except Exception as e:
            print('人数检查异常:', e)

    def reset_peak(self):
        """重置历史峰值与变化记录"""
        self.peak_current = self.disp_current
        self.change_log = []
        now_str = _datetime.datetime.now().strftime('%H:%M:%S')
        self.change_log.insert(0, (now_str, 0, self.disp_current))
        print('[重置] 峰值已重置为当前值 %d' % self.disp_current)
        self.status_msg = '峰值已重置'
        self.status_color = ACCENT_COLOR

    def fmt_duration(self):
        """格式化运行时长"""
        secs = int(time.time() - self.start_time)
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        return '%02d:%02d:%02d' % (h, m, s)

    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('人数实时统计', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 18))
        sub = self.font_sub.render(
            '目标检测实时统计  ·  画面内现有人数  ·  运行时长 %s' % self.fmt_duration(),
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

        # 画面下方提示
        tip = self.font_small.render(
            '提示：目标检测统计画面中所有"人"，无论进出均实时反映当前人数',
            True, SUBTLE_COLOR)
        self.screen.blit(tip, (self.cam_rect.x + 20, self.cam_rect.bottom - 55))

    def draw_info_panel(self):
        """绘制右侧统计面板"""
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 30
        x_end = self.info_rect.right - 30
        y = self.info_rect.y + 20

        # ---- 标题 + 重置按钮 ----
        head = self.font_sub.render('实时统计', True, TITLE_COLOR)
        self.screen.blit(head, (x, y + 10))
        self.btn_reset.draw(self.screen, self.font_btn)
        y += 70

        # ---- 当前现有人数（超大字突出显示）----
        cur_label = self.font_item.render('当前现有人数', True, TEXT_COLOR)
        self.screen.blit(cur_label, (x, y))
        y += 36

        cur_text = str(self.disp_current)
        cur_surf = self.font_huge.render(cur_text, True, CURRENT_COLOR)
        # 居中显示
        cx = (x + x_end) // 2
        self.screen.blit(cur_surf, (cx - cur_surf.get_width() // 2, y))
        # 单位"人"
        unit_surf = self.font_big.render('人', True, TEXT_COLOR)
        self.screen.blit(unit_surf, (cx + cur_surf.get_width() // 2 + 15,
                                     y + cur_surf.get_height() - unit_surf.get_height()))
        # 峰值标注
        peak_text = '历史峰值：%d 人' % self.peak_current
        peak_surf = self.font_small.render(peak_text, True, SUBTLE_COLOR)
        self.screen.blit(peak_surf, (cx - peak_surf.get_width() // 2,
                                     y + cur_surf.get_height() + 4))
        y += cur_surf.get_height() + 36

        # 分隔线
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 18

        # ---- 状态消息 ----
        status_surf = self.font_status.render(self.status_msg, True, self.status_color)
        max_w = x_end - x
        if status_surf.get_width() > max_w:
            status_surf = self.font_small.render(self.status_msg, True, self.status_color)
        self.screen.blit(status_surf, (x, y))
        y += 40

        # 分隔线
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 16

        # ---- 人数变化记录（最近 10 条）----
        log_head = self.font_item.render('人数变化记录', True, TITLE_COLOR)
        self.screen.blit(log_head, (x, y))
        y += 34

        list_bottom = self.info_rect.bottom - 20
        if not self.change_log:
            hint = self.font_log.render('暂无变化记录', True, SUBTLE_COLOR)
            self.screen.blit(hint, (x, y))
        else:
            row_h = 30
            for t_str, delta, new_count in self.change_log:
                if y + row_h > list_bottom:
                    break
                if delta > 0:
                    arrow = '↑'
                    msg = '+%d → %d 人' % (delta, new_count)
                    color = SUCCESS_COLOR
                elif delta < 0:
                    arrow = '↓'
                    msg = '%d → %d 人' % (delta, new_count)
                    color = ERROR_COLOR
                else:  # 重置事件
                    arrow = '↻'
                    msg = '峰值已重置（当前 %d 人）' % new_count
                    color = ACCENT_COLOR
                line = '%s  %s  %s' % (t_str, arrow, msg)
                log_surf = self.font_log.render(line, True, color)
                self.screen.blit(log_surf, (x, y))
                y += row_h

    def draw_footer(self, mouse_pos):
        """绘制底部栏"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        hint = self.font_small.render(
            'ESC 退出  ·  画面内自动统计人数  ·  点击"重置峰值"清零历史峰值',
            True, SUBTLE_COLOR)
        self.screen.blit(hint, (40, HEIGHT - self.FOOTER_H // 2 - hint.get_height() // 2))

    def run(self):
        """主循环

        采集线程在后台固定 0.15s 间隔采集帧，主循环只负责：
        1. 事件处理
        2. 人数检查（refresh_results 只读缓存，不访问 V4L2）
        3. 界面绘制
        """
        frame_counter = 0
        while self.running:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.btn_exit.clicked(event.pos):
                        self.running = False
                    elif self.btn_reset.clicked(event.pos):
                        self.reset_peak()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_r:
                        # R 键快捷重置峰值
                        self.reset_peak()

            frame_counter += 1

            # 人数检查：每 15 帧一次（约 2 次/秒），与人脸识别灯效.py 频率一致
            # refresh_results() 只读取后台检测线程的缓存结果，不直接访问 V4L2
            if frame_counter % 15 == 0:
                self.check_counter()

            self.btn_exit.update(mouse_pos)
            self.btn_reset.update(mouse_pos)

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
        # 显式停止后台检测线程（报告 4.1 节：stop_background_detection 在 threaded_system 下）
        try:
            self.vision_system.threaded_system.stop_background_detection()
        except Exception:
            pass
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
    app = PeopleCounterApp()
    app.run()
