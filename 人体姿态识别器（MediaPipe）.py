# -*- coding: utf-8 -*-
"""
人体姿态识别系统 - 好搭AI派程序（MediaPipe 方案）
=====================================
功能说明：
  1. 基于 Google MediaPipe Pose 识别 USB 摄像头画面中的人体姿态
  2. 界面 1920x1080，浅蓝科技感主题
  3. 实时显示摄像头画面（采集线程 + 识别线程分离，避免画面延迟）
  4. 在画面上叠加 33 个关键点与骨架连线（MediaPipe Pose 格式）
  5. 右侧面板展示姿态信息（检测状态、置信度、关键点数、简单姿态判断）
  6. 退出按钮 + ESC 快捷键

硬件依赖：
  - USB 外接摄像头（接在 ESP32 扩展板 USB 口）

第三方库：
  - opencv-python
  - numpy
  - mediapipe（已安装，由手势控制RGB灯带程序验证）

参考范例：
  - 本地参考：手势控制RGB灯带.py（cv2.VideoCapture + mediapipe + 双线程模式）
    复用其摄像头探测、雪花检测、SIGALRM 超时、采集/识别线程分离结构
"""

import os
# 强制 libGL 使用软件渲染，避免 rockchip 平台 GPU 驱动加载失败
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

import sys
import math
import time
import signal
import threading
import datetime as _datetime

# 导入顺序：先 pygame 再 cv2（rockchip 平台兼容性要求）
import pygame
import cv2
import numpy as np
import mediapipe as mp


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
    '人体姿态识别器_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
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

# 摄像头参数
CAMERA_W, CAMERA_H = 640, 480

# 字体路径（参照手势控制RGB灯带.py）
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'
FONT_REG_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'

# MediaPipe Pose 参数
MODEL_COMPLEXITY = 1            # 0=Lite(快) 1=Full(平衡) 2=Heavy(准但慢)
MIN_DETECTION_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5

# ---- 界面配色（浅蓝科技感主题） ----
BG_TOP = (135, 206, 250)        # 浅天蓝
BG_BOTTOM = (70, 130, 200)      # 稍深的蓝
PANEL_COLOR = (255, 255, 255)   # 白色面板
PANEL_ALPHA = 235
PANEL_BORDER = (0, 150, 200)    # 青色边框
TITLE_COLOR = (20, 50, 100)     # 深蓝标题
SUBTLE_COLOR = (80, 110, 150)   # 灰蓝副标题
TEXT_COLOR = (30, 50, 80)       # 深灰蓝正文
TEXT_DIM = (110, 130, 160)      # 灰蓝次要文字
ACCENT_CYAN = (0, 170, 210)     # 青色
ACCENT_ORANGE = (255, 140, 50)  # 橙色
ACCENT_GREEN = (0, 170, 90)     # 绿色
ACCENT_PURPLE = (140, 80, 220)  # 紫色
ACCENT_YELLOW = (240, 180, 40)  # 黄色
ACCENT_RED = (230, 70, 80)      # 红色
ACCENT_PINK = (230, 90, 160)    # 粉色
BTN_EXIT_COLOR = (120, 130, 145)
BTN_EXIT_HOVER = (220, 70, 80)
STATUS_READY = ACCENT_GREEN
STATUS_BUSY = ACCENT_ORANGE
STATUS_ERROR = ACCENT_RED

# ---- MediaPipe Pose 33 关键点 → COCO 17 关键点映射 ----
# MediaPipe 33 点索引 → COCO 17 点索引
# COCO 17: 0鼻 1左眼 2右眼 3左耳 4右耳 5左肩 6右肩 7左肘 8右肘
#          9左腕 10右腕 11左髋 12右髋 13左膝 14右膝 15左踝 16右踝
# MediaPipe: 0鼻 2左眼 5右眼 7左耳 8右耳 11左肩 12右肩 13左肘 14右肘
#            15左腕 16右腕 23左髋 24右髋 25左膝 26右膝 27左踝 28右踝
MP_TO_COCO = {
    0: 0, 2: 1, 5: 2, 7: 3, 8: 4,
    11: 5, 12: 6, 13: 7, 14: 8, 15: 9, 16: 10,
    23: 11, 24: 12, 25: 13, 26: 14, 27: 15, 28: 16,
}

# COCO 17 关键点名称
KEYPOINT_NAMES = [
    '鼻子', '左眼', '右眼', '左耳', '右耳',
    '左肩', '右肩', '左肘', '右肘', '左腕', '右腕',
    '左髋', '右髋', '左膝', '右膝', '左踝', '右踝',
]

# COCO 17 骨架连接（关键点索引对）
SKELETON_CONNECTIONS = [
    (0, 1), (0, 2),       # 鼻子-左眼, 鼻子-右眼
    (1, 3), (2, 4),       # 左眼-左耳, 右眼-右耳
    (5, 6),               # 左肩-右肩
    (5, 7), (7, 9),       # 左肩-左肘, 左肘-左腕
    (6, 8), (8, 10),      # 右肩-右肘, 右肘-右腕
    (5, 11), (6, 12),     # 左肩-左髋, 右肩-右髋
    (11, 12),             # 左髋-右髋
    (11, 13), (13, 15),   # 左髋-左膝, 左膝-左踝
    (12, 14), (14, 16),   # 右髋-右膝, 右膝-右踝
]

# 每条骨架连线的颜色（多色显示，符合用户偏好）
SKELETON_COLORS = [
    ACCENT_CYAN, ACCENT_CYAN,    # 头部
    ACCENT_CYAN, ACCENT_CYAN,
    ACCENT_GREEN,                # 肩
    ACCENT_ORANGE, ACCENT_ORANGE,  # 左臂
    ACCENT_ORANGE, ACCENT_ORANGE,  # 右臂
    ACCENT_GREEN, ACCENT_GREEN,    # 躯干
    ACCENT_GREEN,                  # 髋
    ACCENT_PURPLE, ACCENT_PURPLE,  # 左腿
    ACCENT_PURPLE, ACCENT_PURPLE,  # 右腿
]

# 关键点颜色（按身体部位分组）
KEYPOINT_COLORS = [
    ACCENT_CYAN, ACCENT_CYAN, ACCENT_CYAN, ACCENT_CYAN, ACCENT_CYAN,  # 头部 0-4
    ACCENT_GREEN, ACCENT_GREEN,       # 肩 5-6
    ACCENT_ORANGE, ACCENT_ORANGE,     # 肘 7-8
    ACCENT_ORANGE, ACCENT_ORANGE,     # 腕 9-10
    ACCENT_GREEN, ACCENT_GREEN,       # 髋 11-12
    ACCENT_PURPLE, ACCENT_PURPLE,     # 膝 13-14
    ACCENT_PURPLE, ACCENT_PURPLE,     # 踝 15-16
]


# ===================== 摄像头打开（参考手势控制RGB灯带.py） =====================
class _CameraProbeTimeout(Exception):
    """探测摄像头时 SIGALRM 超时"""
    pass


def _is_valid_frame(frame):
    """判断帧是否为有效画面（非空、非全黑、非全白）

    项目记忆：摄像头采集线程中使用 gray.std() 进行帧检测在 ARM 设备上计算
    开销过大，应改用 gray.mean() 检测全黑/全白帧。
    """
    if frame is None or frame.size == 0:
        return False
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_val = float(gray.mean())
        # 全黑或全白帧视为无效（阈值 10 和 245 经验值）
        if mean_val < 10 or mean_val > 245:
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


# ===================== MediaPipe Pose 初始化 =====================
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=MODEL_COMPLEXITY,
    smooth_landmarks=True,
    min_detection_confidence=MIN_DETECTION_CONFIDENCE,
    min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
)
print("MediaPipe Pose 已初始化（model_complexity=%d）" % MODEL_COMPLEXITY)


# ===================== 姿态估计（基于 COCO 17 关键点） =====================
def extract_coco17(landmarks):
    """从 MediaPipe 33 关键点提取 COCO 17 关键点

    参数: landmarks - mediapipe 33 点归一化坐标列表
    返回: [(x, y, vis), ...] 17 个点，x/y 为归一化坐标(0~1)，vis 为可见度(0~1)
    """
    kps = []
    for mp_idx in [0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16,
                   23, 24, 25, 26, 27, 28]:
        lm = landmarks[mp_idx]
        # mediapipe 的 visibility 表示是否被遮挡，confidence 用它近似
        vis = float(lm.visibility) if hasattr(lm, 'visibility') else 1.0
        kps.append((float(lm.x), float(lm.y), vis))
    return kps


def estimate_pose(kps):
    """根据关键点简单判断姿态（粗略估计）

    参数: kps - [(x, y, vis), ...] 17 个点，归一化坐标
    返回: (姿态文本, 颜色)
    """
    if len(kps) < 5:
        return ('检测中', TEXT_DIM)

    try:
        def y(i):
            return kps[i][1] if i < len(kps) else None

        def visible(i):
            return i < len(kps) and kps[i][2] > 0.3

        # 判断举手：手腕高于肩膀（y 值更小，归一化坐标）
        left_hand_up = False
        right_hand_up = False
        if visible(9) and visible(5) and y(9) is not None and y(5) is not None:
            left_hand_up = y(9) < y(5) - 0.05
        if visible(10) and visible(6) and y(10) is not None and y(6) is not None:
            right_hand_up = y(10) < y(6) - 0.05

        if left_hand_up and right_hand_up:
            return ('双手举起', ACCENT_ORANGE)
        if left_hand_up:
            return ('左手举起', ACCENT_YELLOW)
        if right_hand_up:
            return ('右手举起', ACCENT_YELLOW)

        # 判断站立 / 坐着（粗略，用归一化坐标的差值）
        if visible(11) and visible(15) and y(11) is not None and y(15) is not None:
            leg_len = abs(y(15) - y(11))
            if leg_len > 0.25:
                return ('站立', ACCENT_GREEN)
            elif leg_len < 0.12:
                return ('坐着 / 蹲下', ACCENT_PURPLE)

        return ('已检测到人体', ACCENT_CYAN)
    except Exception:
        return ('已检测到人体', ACCENT_CYAN)


# ===================== Pygame 界面工具 =====================
def make_gradient_bg(width, height, top, bottom):
    """生成垂直渐变背景（用 numpy 向量化，比逐行绘制快 100 倍）"""
    ratios = np.linspace(0, 1, height, dtype=np.float32).reshape(-1, 1)
    top_arr = np.array(top, dtype=np.float32).reshape(1, 3)
    bottom_arr = np.array(bottom, dtype=np.float32).reshape(1, 3)
    colors = (top_arr + (bottom_arr - top_arr) * ratios)
    img = np.tile(colors[:, np.newaxis, :], (1, width, 1)).astype(np.uint8)
    return pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))


class Button:
    """通用圆角按钮（参照手势控制RGB灯带.py）"""

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
        c = self.hover_color if self.hovered else self.color
        if not self.enabled:
            c = (180, 185, 195)
        btn = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn, c, btn.get_rect(), border_radius=14)
        border_c = (255, 255, 255, 220) if self.hovered else (255, 255, 255, 150)
        pygame.draw.rect(btn, border_c, btn.get_rect(), 2, border_radius=14)
        surf.blit(btn, self.rect.topleft)
        label = font.render(self.text, True, self.text_color)
        lr = label.get_rect(center=self.rect.center)
        surf.blit(label, lr)

    def clicked(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


# ===================== 主程序 =====================
class PoseApp:
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
        # 只初始化 display + font，不调用 pygame.init()，
        # 避免 pygame.mixer 初始化导致 rockchip 平台原生崩溃
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('人体姿态识别系统')
        self.clock = pygame.time.Clock()

        # 字体
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 52)
        self.font_sub = pygame.font.Font(FONT_REG_PATH, 24)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_label = pygame.font.Font(FONT_BOLD_PATH, 28)
        self.font_small = pygame.font.Font(FONT_REG_PATH, 22)
        self.font_status = pygame.font.Font(FONT_BOLD_PATH, 26)
        self.font_pose = pygame.font.Font(FONT_BOLD_PATH, 64)
        self.font_conf = pygame.font.Font(FONT_BOLD_PATH, 40)
        self.font_info = pygame.font.Font(FONT_REG_PATH, 30)
        self.font_kp = pygame.font.Font(FONT_BOLD_PATH, 24)
        self.font_box = pygame.font.Font(FONT_REG_PATH, 20)

        # 背景：优先加载 images/1.jpg，失败则回退渐变背景
        try:
            bg_raw = pygame.image.load(os.path.join('images', '1.jpg'))
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception:
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # 预创建面板 Surface（避免每帧重复创建，大幅降低 CPU 占用）
        self.cam_panel_surf = pygame.Surface(
            (self.CAM_PANEL_W, self.CAM_PANEL_H), pygame.SRCALPHA).convert_alpha()
        pygame.draw.rect(self.cam_panel_surf, (*PANEL_COLOR, PANEL_ALPHA),
                         self.cam_panel_surf.get_rect(), border_radius=16)
        self.result_panel_surf = pygame.Surface(
            (self.RESULT_W, self.RESULT_H), pygame.SRCALPHA).convert_alpha()
        pygame.draw.rect(self.result_panel_surf, (*PANEL_COLOR, PANEL_ALPHA),
                         self.result_panel_surf.get_rect(), border_radius=16)

        # 预创建关键点光晕 Surface（按颜色分组，避免每帧创建）
        # 之前每帧创建 17 个 20x20 SRCALPHA Surface 是主要 CPU 瓶颈
        self.kp_glow_surfs = {}
        for color in set(KEYPOINT_COLORS):
            g = pygame.Surface((20, 20), pygame.SRCALPHA).convert_alpha()
            pygame.draw.circle(g, (*color, 80), (10, 10), 10)
            self.kp_glow_surfs[color] = g

        # 预创建扫描线 glow Surface
        self.scan_glow_surf = pygame.Surface(
            (CAMERA_W, 16), pygame.SRCALPHA).convert_alpha()
        pygame.draw.rect(self.scan_glow_surf, (0, 170, 210, 40),
                         self.scan_glow_surf.get_rect())

        # 预创建状态指示灯 glow Surface
        self.status_glow_surf = pygame.Surface((30, 30), pygame.SRCALPHA).convert_alpha()

        self.running = True

        # 退出按钮（右上角标题栏内，符合项目记忆：退出按钮必须设在右上角标题栏内）
        # 标题栏高度 110，按钮高度 70，垂直居中 y = (110-70)/2 = 20
        self.btn_exit = Button(
            (WIDTH - 280, 20, 240, 70),
            '退出', BTN_EXIT_COLOR, BTN_EXIT_HOVER
        )

        # ---- 摄像头打开（参考手势控制RGB灯带.py） ----
        print('外接摄像头打开中...')
        self.cap = open_camera()
        self.camera_ok = self.cap is not None and self.cap.isOpened()
        if self.camera_ok:
            print('外接摄像头已打开')
        else:
            print('摄像头打开失败，请检查 /dev/video41 和 /dev/video40')

        # ---- 状态：采集线程写入，主循环读取 ----
        self.raw_frame = None         # 采集线程写入的最新原始帧(BGR)
        self.latest_frame = None      # 识别线程写入的最新处理帧(RGB,已绘制关键点)
        self.frame_lock = threading.Lock()

        # 姿态检测结果（识别线程写入，主循环读取）
        self.latest_pose_detected = False
        self.latest_pose_confidence = 0.0
        self.latest_pose_keypoints = []   # COCO 17 归一化坐标 [(x,y,vis), ...]

        # 状态文字
        self.status_message = '初始化中...'
        self.status_color = STATUS_BUSY

        # 线程控制
        self.cam_thread_running = True

        # 启动采集线程 + 识别线程（参考手势控制RGB灯带.py 的双线程结构）
        threading.Thread(target=self.camera_capture_loop, daemon=True).start()
        threading.Thread(target=self.pose_recognition_loop, daemon=True).start()

    # ===================== 采集线程 =====================
    def camera_capture_loop(self):
        """后台线程：仅快速读取摄像头帧，不做任何处理，保证画面实时

        参考手势控制RGB灯带.py 的 camera_capture_loop：
          - 总是覆盖旧帧，丢弃积压帧，避免 V4L2 内核缓冲区积压旧帧导致画面延迟
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

    # ===================== 识别线程 =====================
    def pose_recognition_loop(self):
        """后台线程：取最新帧做 MediaPipe Pose 识别 + 绘制关键点，不阻塞采集线程

        参考手势控制RGB灯带.py 的 gesture_recognition_loop：
          - 取最新帧做 mediapipe 处理，处理不过来就跳过中间帧(自动降帧)
        """
        while self.cam_thread_running:
            with self.frame_lock:
                frame = self.raw_frame
            if frame is None:
                time.sleep(0.02)
                continue
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = pose.process(rgb)

                detected = False
                confidence = 0.0
                kps_coco17 = []

                if results.pose_landmarks is not None:
                    detected = True
                    # 用鼻子的可见度作为整体置信度参考
                    nose = results.pose_landmarks.landmark[0]
                    confidence = float(nose.visibility) if hasattr(nose, 'visibility') else 0.9
                    kps_coco17 = extract_coco17(results.pose_landmarks.landmark)

                    # 在 RGB 帧上绘制关键点和骨架
                    # 注意：不同 mediapipe 版本的 drawing_styles API 不一致，
                    #       不依赖 get_default_pose_*_style，统一用 None 使用默认样式
                    try:
                        mp_drawing.draw_landmarks(
                            rgb,
                            results.pose_landmarks,
                            mp_pose.POSE_CONNECTIONS,
                            landmark_drawing_spec=mp_drawing.DrawingSpec(
                                color=(0, 170, 210), thickness=2, circle_radius=3),
                            connection_drawing_spec=mp_drawing.DrawingSpec(
                                color=(0, 150, 200), thickness=2))
                    except Exception:
                        # 退回最简模式，只画关键点不画连线
                        mp_drawing.draw_landmarks(
                            rgb, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)

                with self.frame_lock:
                    self.latest_frame = rgb
                    self.latest_pose_detected = detected
                    self.latest_pose_confidence = confidence
                    self.latest_pose_keypoints = kps_coco17

                # 更新状态文字
                if detected:
                    self.status_message = '姿态识别中'
                    self.status_color = STATUS_READY
                else:
                    self.status_message = '等待人体出现...'
                    self.status_color = TEXT_DIM

            except Exception as e:
                if self.cam_thread_running:
                    print('姿态识别异常:', e)
                time.sleep(0.1)

    # ---------- 摄像头帧转 Surface ----------
    def grab_frame(self):
        """从识别线程的最新帧获取 RGB 画面并转为 Surface"""
        with self.frame_lock:
            frame = self.latest_frame
        if frame is None:
            return None
        try:
            h, w = frame.shape[:2]
            # frombuffer 比 surfarray.make_surface 快，减少延迟
            surf = pygame.image.frombuffer(frame.tobytes(), (w, h), 'RGB')
            return surf
        except Exception:
            return None

    def scale_camera_surface(self, surf, target_w, target_h):
        """等比缩放摄像头画面（用 scale 替代 smoothscale 提升性能）"""
        sw, sh = surf.get_size()
        scale = min(target_w / sw, target_h / sh)
        new_w = int(sw * scale)
        new_h = int(sh * scale)
        return pygame.transform.scale(surf, (new_w, new_h)), new_w, new_h, scale

    # ---------- 绘制 ----------
    def draw_title(self, mouse_pos):
        """绘制顶部标题栏（含右上角退出按钮）"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (20, 50, 100, 200), mask.get_rect())
        self.screen.blit(mask, (0, 0))
        pygame.draw.line(self.screen, ACCENT_CYAN, (0, self.TITLE_H), (WIDTH, self.TITLE_H), 2)
        pygame.draw.line(self.screen, (0, 100, 130), (0, self.TITLE_H + 2), (WIDTH, self.TITLE_H + 2), 1)

        title = self.font_title.render('人体姿态识别系统', True, (255, 255, 255))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 18))

        sub = self.font_sub.render(
            'HUMAN  POSE  ESTIMATION   |   USB摄像头  ->  MediaPipe Pose  ->  33关键点实时检测',
            True, (200, 220, 240))
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 76))

        # 退出按钮（右上角标题栏内）
        self.btn_exit.update(mouse_pos)
        self.btn_exit.draw(self.screen, self.font_btn)

    def draw_corner_brackets(self, x, y, w, h, color=ACCENT_CYAN):
        """在摄像头画面四角绘制科技感瞄准框"""
        blen = 30
        t = 3
        pygame.draw.line(self.screen, color, (x, y), (x + blen, y), t)
        pygame.draw.line(self.screen, color, (x, y), (x, y + blen), t)
        pygame.draw.line(self.screen, color, (x + w, y), (x + w - blen, y), t)
        pygame.draw.line(self.screen, color, (x + w, y), (x + w, y + blen), t)
        pygame.draw.line(self.screen, color, (x, y + h), (x + blen, y + h), t)
        pygame.draw.line(self.screen, color, (x, y + h), (x, y + h - blen), t)
        pygame.draw.line(self.screen, color, (x + w, y + h), (x + w - blen, y + h), t)
        pygame.draw.line(self.screen, color, (x + w, y + h), (x + w, y + h - blen), t)

    def draw_skeleton_overlay(self, ox, oy, sw, sh):
        """在视频画面上叠加多色骨架与关键点（补充 mediapipe 默认绘制的单调颜色）

        参数:
          ox, oy: 视频画面在屏幕上的左上角偏移
          sw, sh: 视频画面在屏幕上的显示尺寸
        说明:
          关键点坐标是归一化的(0~1)，需乘以显示尺寸 sw/sh 再加偏移 ox/oy
          mediapipe 已在帧上绘制了默认样式的骨架，这里叠加多色关键点增强视觉效果
        """
        kps = self.latest_pose_keypoints
        if len(kps) == 0:
            return

        # 绘制骨架连线（多色，覆盖 mediapipe 默认的白色连线）
        for idx, (i, j) in enumerate(SKELETON_CONNECTIONS):
            if i < len(kps) and j < len(kps):
                x1, y1, c1 = kps[i]
                x2, y2, c2 = kps[j]
                # 过滤低可见度点
                if c1 < 0.3 or c2 < 0.3:
                    continue
                sx1 = ox + int(x1 * sw)
                sy1 = oy + int(y1 * sh)
                sx2 = ox + int(x2 * sw)
                sy2 = oy + int(y2 * sh)
                color = SKELETON_COLORS[idx] if idx < len(SKELETON_COLORS) else ACCENT_CYAN
                pygame.draw.line(self.screen, color, (sx1, sy1), (sx2, sy2), 4)

        # 绘制关键点圆点（多色，覆盖 mediapipe 默认的白色圆点）
        for i, (kx, ky, kc) in enumerate(kps):
            if kc < 0.3:
                continue
            sx = ox + int(kx * sw)
            sy = oy + int(ky * sh)
            color = KEYPOINT_COLORS[i] if i < len(KEYPOINT_COLORS) else ACCENT_PINK
            # 外圈光晕（使用预创建的 Surface）
            glow = self.kp_glow_surfs.get(color)
            if glow is not None:
                self.screen.blit(glow, (sx - 10, sy - 10))
            # 实心点
            pygame.draw.circle(self.screen, color, (sx, sy), 6)
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), 6, 2)

    def draw_camera_panel(self):
        """绘制摄像头画面区域"""
        panel_rect = pygame.Rect(self.CAM_PANEL_X, self.CAM_PANEL_Y,
                                 self.CAM_PANEL_W, self.CAM_PANEL_H)

        self.screen.blit(self.cam_panel_surf, panel_rect.topleft)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel_rect, 2, border_radius=16)

        label = self.font_label.render('摄像头实时画面', True, ACCENT_CYAN)
        self.screen.blit(label, (panel_rect.x + 24, panel_rect.y + 18))

        res_text = self.font_small.render(
            '%d x %d  |  MediaPipe Pose 33关键点' % (CAMERA_W, CAMERA_H), True, TEXT_DIM)
        self.screen.blit(res_text, (panel_rect.right - res_text.get_width() - 24, panel_rect.y + 22))

        cam_inner_x = panel_rect.x + 20
        cam_inner_y = panel_rect.y + 60
        cam_inner_w = panel_rect.w - 40
        cam_inner_h = panel_rect.h - 80

        cam_surf = self.grab_frame()
        if cam_surf is not None:
            scaled, sw, sh, scale_factor = self.scale_camera_surface(
                cam_surf, cam_inner_w, cam_inner_h)
            ox = cam_inner_x + (cam_inner_w - sw) // 2
            oy = cam_inner_y + (cam_inner_h - sh) // 2
            self.screen.blit(scaled, (ox, oy))

            self.draw_corner_brackets(ox, oy, sw, sh)

            # 叠加多色骨架与关键点（归一化坐标 → 屏幕坐标）
            self.draw_skeleton_overlay(ox, oy, sw, sh)

            # 扫描动画（使用预创建的 glow Surface）
            scan_y = int(time.time() * 180) % sh
            line_y = oy + scan_y
            pygame.draw.line(self.screen, ACCENT_CYAN, (ox, line_y), (ox + sw, line_y), 2)
            self.screen.blit(self.scan_glow_surf, (ox, line_y - 8))
        else:
            if not self.camera_ok:
                hint = self.font_label.render(
                    '摄像头未打开，请检查 USB 摄像头连接', True, STATUS_ERROR)
            else:
                hint = self.font_label.render('摄像头启动中...', True, ACCENT_CYAN)
            self.screen.blit(hint, (panel_rect.centerx - hint.get_width() // 2,
                                    panel_rect.centery - hint.get_height() // 2))

    def draw_progress_bar(self, x, y, w, h, ratio, color):
        """绘制圆角进度条"""
        ratio = max(0.0, min(1.0, ratio))
        pygame.draw.rect(self.screen, (220, 230, 240), (x, y, w, h), border_radius=h // 2)
        fill_w = int(w * ratio)
        if fill_w > 0:
            pygame.draw.rect(self.screen, color, (x, y, fill_w, h), border_radius=h // 2)

    def draw_result_panel(self):
        """绘制右侧姿态识别结果区域"""
        panel_rect = pygame.Rect(self.RESULT_X, self.RESULT_Y, self.RESULT_W, self.RESULT_H)

        self.screen.blit(self.result_panel_surf, panel_rect.topleft)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel_rect, 2, border_radius=16)

        label = self.font_label.render('识别结果', True, ACCENT_CYAN)
        self.screen.blit(label, (panel_rect.x + 24, panel_rect.y + 18))

        # 状态指示灯（使用预创建的 glow Surface）
        dot_x = panel_rect.right - 30
        dot_y = panel_rect.y + 32
        pygame.draw.circle(self.screen, self.status_color, (dot_x, dot_y), 8)
        self.status_glow_surf.fill((0, 0, 0, 0))
        pygame.draw.circle(self.status_glow_surf, (*self.status_color, 80), (15, 15), 14)
        self.screen.blit(self.status_glow_surf, (dot_x - 15, dot_y - 15))

        sep_y = panel_rect.y + 60
        pygame.draw.line(self.screen, (200, 215, 230),
                         (panel_rect.x + 20, sep_y), (panel_rect.right - 20, sep_y), 1)

        content_x = panel_rect.x + 30
        content_w = panel_rect.w - 60
        cy = sep_y + 24

        # ---- 姿态主结果 ----
        section_label = self.font_small.render('当 前 姿 态', True, TEXT_DIM)
        self.screen.blit(section_label, (content_x, cy))
        cy += 36

        if self.latest_pose_detected:
            pose_text, pose_color = estimate_pose(self.latest_pose_keypoints)
            pose_surf = self.font_pose.render(pose_text, True, pose_color)
            self.screen.blit(pose_surf, (content_x, cy))
            cy += 80
        else:
            hint = self.font_conf.render('等待检测...', True, TEXT_DIM)
            self.screen.blit(hint, (content_x, cy))
            cy += 56

        # ---- 置信度 ----
        cy += 8
        section_label = self.font_small.render('置 信 度', True, TEXT_DIM)
        self.screen.blit(section_label, (content_x, cy))
        cy += 32

        conf = self.latest_pose_confidence if self.latest_pose_detected else 0.0
        conf_surf = self.font_conf.render('%.1f%%' % (conf * 100), True, ACCENT_CYAN)
        self.screen.blit(conf_surf, (content_x, cy))
        cy += 50
        self.draw_progress_bar(content_x, cy, content_w, 18, conf, ACCENT_CYAN)
        cy += 36

        # ---- 关键点信息 ----
        cy += 12
        pygame.draw.line(self.screen, (200, 215, 230),
                         (panel_rect.x + 20, cy), (panel_rect.right - 20, cy), 1)
        cy += 16

        # 检测状态
        lbl = self.font_info.render('检测状态', True, TEXT_DIM)
        status_text = '已检测到' if self.latest_pose_detected else '未检测到'
        val = self.font_info.render(status_text, True,
                                    ACCENT_GREEN if self.latest_pose_detected else TEXT_DIM)
        self.screen.blit(lbl, (content_x, cy))
        self.screen.blit(val, (panel_rect.right - 30 - val.get_width(), cy))
        cy += 38

        # 关键点数量
        kp_count = len(self.latest_pose_keypoints)
        lbl = self.font_info.render('关键点数', True, TEXT_DIM)
        val = self.font_info.render('%d / 17' % kp_count, True, ACCENT_GREEN)
        self.screen.blit(lbl, (content_x, cy))
        self.screen.blit(val, (panel_rect.right - 30 - val.get_width(), cy))
        cy += 38

        # ---- 关键点列表 ----
        cy += 12
        pygame.draw.line(self.screen, (200, 215, 230),
                         (panel_rect.x + 20, cy), (panel_rect.right - 20, cy), 1)
        cy += 16

        section_label = self.font_small.render('关 键 点 列 表', True, TEXT_DIM)
        self.screen.blit(section_label, (content_x, cy))
        cy += 28

        if kp_count > 0:
            # 两列显示关键点（归一化坐标转为百分比显示）
            col_w = content_w // 2
            for i in range(min(kp_count, 17)):
                name = KEYPOINT_NAMES[i] if i < len(KEYPOINT_NAMES) else 'KP%d' % i
                kx, ky, kc = self.latest_pose_keypoints[i]
                color = KEYPOINT_COLORS[i] if i < len(KEYPOINT_COLORS) else TEXT_COLOR
                # 只显示高可见度点
                if kc >= 0.3:
                    text = self.font_kp.render(
                        '%s  (%d%%,%d%%)' % (name, int(kx * 100), int(ky * 100)),
                        True, color)
                else:
                    text = self.font_kp.render('%s  --' % name, True, TEXT_DIM)
                col = i % 2
                row = i // 2
                self.screen.blit(text, (content_x + col * col_w, cy + row * 26))
        else:
            hint = self.font_info.render('暂无关键点数据', True, TEXT_DIM)
            self.screen.blit(hint, (content_x, cy))

        # ---- 底部状态 ----
        cy = panel_rect.bottom - 50
        status = self.font_small.render(self.status_message, True, self.status_color)
        self.screen.blit(status, (content_x, cy))

    def draw_footer(self, mouse_pos):
        """绘制底部状态栏（退出按钮已移至标题栏右上角）"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (20, 50, 100, 200), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))
        pygame.draw.line(self.screen, ACCENT_CYAN,
                         (0, HEIGHT - self.FOOTER_H), (WIDTH, HEIGHT - self.FOOTER_H), 2)

        # 状态文字
        status = self.font_status.render(self.status_message, True, self.status_color)
        self.screen.blit(status, (24, HEIGHT - self.FOOTER_H + 58))

        # 检测状态
        if self.latest_pose_detected:
            pose_text = self.font_small.render(
                '已检测到人体姿态', True, ACCENT_CYAN)
            self.screen.blit(pose_text, (24, HEIGHT - self.FOOTER_H + 95))

        # 操作提示
        hint = self.font_small.render(
            'ESC = 退出    |    MediaPipe Pose 实时检测（采集+识别双线程）',
            True, (180, 200, 220))
        self.screen.blit(hint, (560, HEIGHT - self.FOOTER_H + 95))

    # ---------- 事件处理 ----------
    def handle_click(self, pos):
        if self.btn_exit.clicked(pos):
            self.running = False

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

            # 绘制（加异常保护，防止静默崩溃）
            try:
                self.screen.blit(self.bg, (0, 0))
                self.draw_title(mouse_pos)
                self.draw_camera_panel()
                self.draw_result_panel()
                self.draw_footer(mouse_pos)

                pygame.display.flip()
            except Exception as e:
                print("绘制异常: {}".format(e))
                import traceback
                traceback.print_exc()

            self.clock.tick(20)  # 20 FPS，姿态检测不需要高帧率，降低 CPU 占用

        # ---- 退出清理 ----
        self.cam_thread_running = False
        time.sleep(0.3)
        try:
            if self.cap is not None:
                self.cap.release()
            print("摄像头已释放")
        except Exception:
            pass
        try:
            pose.close()
            print("MediaPipe Pose 已关闭")
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
    app = PoseApp()
    app.run()
