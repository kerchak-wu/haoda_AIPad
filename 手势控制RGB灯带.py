# -*- coding: utf-8 -*-
"""
手势控制RGB灯带 - 好搭AI派程序
=====================================
功能说明：
  1. USB外接摄像头实时识别手势
  2. 根据不同手势，IO1 RGB灯带(4灯珠)显示不同灯效
  3. 1920x1080界面显示摄像头画面、手势识别结果和灯效名称
  4. 界面提供退出程序按钮

硬件接线：
  - IO1 (GPIO_IO_01)  WS2812 RGB灯带(4灯珠)
  - USB外接摄像头(/dev/video40 或 /dev/video41)
  注意：好搭AI派右下角开关需拨到左侧以启用外设接口。
  注意：连接WS2812灯带需要额外连接上拉扩展模块。

手势与灯效对应：
  握拳       → 红色火焰    (热情似火)
  张开手掌   → 彩虹流光    (五彩缤纷)
  大拇指朝上 → 绿色呼吸    (生机盎然)
  胜利V      → 紫色流光    (神秘优雅)
  食指指向   → 蓝色追逐    (指引方向)
  OK捏合     → 粉色心跳    (爱心传递)
  ILoveYou   → 金色闪烁    (闪耀光芒)
  无手势     → 灯光关闭    (等待手势)

依赖库：
  pygame, cv2(opencv), numpy, mediapipe, ESP32(好搭AI派自带)
  其中 mediapipe 需用户自行安装（用户已确认安装）

参考范例：
  - 范例代码 2.扩展模块使用 4.RGB灯
  - 范例代码 8.pygame 10.音乐播放-按钮
  - 人脸识别播放视频.py（摄像头打开逻辑）
  - 唐诗宋词朗读器.py（界面与灯效实现）
"""

import os
import math
import time
import signal
import threading

import pygame
import cv2
import numpy as np
import mediapipe as mp

from ESP32 import *


# ===================== 配置 =====================
WIDTH, HEIGHT = 1920, 1080

# 字体路径（好搭AI派系统字体）
FONT_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'

# 引脚定义
LED_PIN = GPIO_IO_01   # IO1 RGB灯带
LED_COUNT = 4          # 4颗灯珠

# 摄像头配置
CAMERA_W, CAMERA_H = 640, 480
CAM_DISP_W, CAM_DISP_H = 1080, 810

# 手势识别参数
MAX_NUM_HANDS = 1
MIN_DETECTION_CONFIDENCE = 0.6
MIN_TRACKING_CONFIDENCE = 0.5
CONFIRM_FRAMES = 3   # 连续确认帧数，防抖

# ---- 界面配色（浅色系，符合用户偏好）----
BG_TOP = (135, 206, 235)       # 天空蓝
BG_BOTTOM = (220, 240, 255)    # 浅蓝白
PANEL_COLOR = (255, 255, 255)  # 白色面板
PANEL_BORDER = (100, 149, 237) # 矢车菊蓝
TITLE_COLOR = (25, 60, 130)    # 深蓝
TEXT_COLOR = (50, 50, 60)      # 深灰
SUBTLE_COLOR = (120, 130, 150) # 灰色
ACCENT_COLOR = (255, 140, 0)   # 橙色
SUCCESS_COLOR = (60, 180, 80)  # 绿色
ERROR_COLOR = (220, 80, 80)    # 红色
EXIT_COLOR = (220, 80, 80)
EXIT_HOVER = (255, 100, 100)

# ---- 手势-灯效映射 ----
GESTURE_MAP = {
    'fist':      {'name': '握拳',       'effect': '红色火焰', 'desc': '热情似火', 'color': (255, 60, 30)},
    'open_palm': {'name': '张开手掌',   'effect': '彩虹流光', 'desc': '五彩缤纷', 'color': (255, 100, 200)},
    'thumb_up':  {'name': '大拇指朝上', 'effect': '绿色呼吸', 'desc': '生机盎然', 'color': (60, 200, 100)},
    'victory':   {'name': '胜利V',      'effect': '紫色流光', 'desc': '神秘优雅', 'color': (160, 80, 220)},
    'point_up':  {'name': '食指指向',   'effect': '蓝色追逐', 'desc': '指引方向', 'color': (60, 130, 255)},
    'ok':        {'name': 'OK捏合',     'effect': '粉色心跳', 'desc': '爱心传递', 'color': (255, 130, 180)},
    'iloveyou':  {'name': 'ILoveYou',   'effect': '金色闪烁', 'desc': '闪耀光芒', 'color': (255, 200, 50)},
    'none':      {'name': '无手势',     'effect': '灯光关闭', 'desc': '等待手势', 'color': (150, 150, 150)},
}


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
    except:
        pass


def led_off():
    """熄灭所有灯珠"""
    try:
        board.ws2812Write((LED_PIN), 255, 0, 0, 0)
    except:
        pass


# 全局灯效状态
current_effect = 'none'
led_frame = 0


def update_led_frame():
    """在主循环中按帧更新灯效(单线程，与范例调用风格一致)"""
    global led_frame
    if current_effect == 'none':
        return
    t = led_frame
    try:
        if current_effect == 'fist':
            # 红色火焰跳动
            for i in range(LED_COUNT):
                g = int(50 + 100 * (math.sin((t + i * 20) * 0.2) + 1) * 0.5)
                board.ws2812Write((LED_PIN), i, 255, g, 20)

        elif current_effect == 'open_palm':
            # 彩虹流光
            for i in range(LED_COUNT):
                pos = (t * 3 + i * 60) % 256
                c = wheel(pos)
                board.ws2812Write((LED_PIN), i, c[0], c[1], c[2])

        elif current_effect == 'thumb_up':
            # 绿色呼吸
            b = (math.sin(t * 0.1) + 1) * 0.5
            g = int(100 + 155 * b)
            led_set_all(30, g, 60)

        elif current_effect == 'victory':
            # 紫色流光
            for i in range(LED_COUNT):
                pos = (t * 4 + i * 50) % 256
                if pos < 128:
                    board.ws2812Write((LED_PIN), i, 120 + pos, 30, 200)
                else:
                    board.ws2812Write((LED_PIN), i, 160, 50, 220)

        elif current_effect == 'point_up':
            # 蓝色追逐
            for i in range(LED_COUNT):
                pos = (t + i * 30) % 60
                v = 255 if pos < 20 else (100 if pos < 40 else 40)
                board.ws2812Write((LED_PIN), i, 30, 80, v)

        elif current_effect == 'ok':
            # 粉色心跳
            b = (math.sin(t * 0.15) + 1) * 0.5
            r = int(200 + 55 * b)
            g = int(80 + 50 * b)
            led_set_all(r, g, 150)

        elif current_effect == 'iloveyou':
            # 金色闪烁
            for i in range(LED_COUNT):
                if (t + i * 10) % 40 < 20:
                    board.ws2812Write((LED_PIN), i, 255, 200, 30)
                else:
                    board.ws2812Write((LED_PIN), i, 100, 80, 10)

        led_frame += 1
    except:
        pass


def set_led_effect(effect_name):
    """切换灯效"""
    global current_effect, led_frame
    current_effect = effect_name
    led_frame = 0
    if effect_name == 'none':
        led_off()


# ===================== 摄像头打开 =====================
# 参考人脸识别播放视频.py 的摄像头探测逻辑：MJPG + 超时 + 雪花检测
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


# ===================== 手势识别 =====================
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=MAX_NUM_HANDS,
    min_detection_confidence=MIN_DETECTION_CONFIDENCE,
    min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
)


def is_finger_extended(landmarks, tip_idx, mcp_idx):
    """判断四指是否伸直：指尖到手腕距离 > 指根到手腕距离
    此方法对食指/中指/无名指/小指有效，不适用于大拇指。"""
    wrist = landmarks[0]
    tip = landmarks[tip_idx]
    mcp = landmarks[mcp_idx]
    tip_dist = math.hypot(tip.x - wrist.x, tip.y - wrist.y)
    mcp_dist = math.hypot(mcp.x - wrist.x, mcp.y - wrist.y)
    return tip_dist > mcp_dist


def is_thumb_extended(landmarks):
    """大拇指是否伸直/张开。
    用「拇指尖到食指根距离 / 手掌宽度」的归一化比值判断：
      - 握拳时拇指搭在食指上，比值小（< 0.4）
      - 拇指张开/朝上时，比值大（> 0.7）
    手掌宽度取食指根(5)到小指根(17)的距离，与手的方向无关。"""
    palm_width = math.hypot(landmarks[5].x - landmarks[17].x,
                            landmarks[5].y - landmarks[17].y)
    if palm_width < 1e-6:
        return False
    tip_to_index = math.hypot(landmarks[4].x - landmarks[5].x,
                              landmarks[4].y - landmarks[5].y)
    ratio = tip_to_index / palm_width
    return ratio > 0.6


def recognize_gesture(landmarks):
    """根据 21 个关键点识别手势"""
    # 大拇指单独用归一化比值法判断，避免握拳时误判为伸直
    thumb = is_thumb_extended(landmarks)
    index = is_finger_extended(landmarks, 8, 5)
    middle = is_finger_extended(landmarks, 12, 9)
    ring = is_finger_extended(landmarks, 16, 13)
    pinky = is_finger_extended(landmarks, 20, 17)

    # 大拇指与食指尖距离（归一化坐标）
    thumb_index_dist = math.hypot(landmarks[4].x - landmarks[8].x,
                                  landmarks[4].y - landmarks[8].y)

    # OK/捏合：大拇指和食指尖距离很近，其他三指伸直
    if thumb_index_dist < 0.08 and middle and ring and pinky:
        return 'ok'

    # 大拇指朝上：四指全弯 + 拇指伸直（必须在握拳之前判断，否则被握拳拦截）
    if thumb and not index and not middle and not ring and not pinky:
        return 'thumb_up'

    # 握拳：四指全弯（走到这里说明拇指也是弯曲的）
    if not index and not middle and not ring and not pinky:
        return 'fist'

    # 张开手掌：四指都伸直
    if index and middle and ring and pinky:
        return 'open_palm'

    # 胜利V：食指和中指伸直
    if index and middle and not ring and not pinky:
        return 'victory'

    # 食指指向：只有食指伸直
    if index and not middle and not ring and not pinky:
        return 'point_up'

    # ILoveYou：大拇指、食指、小拇指伸直
    if thumb and index and not middle and not ring and pinky:
        return 'iloveyou'

    return 'none'


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
    """RGB 帧 -> pygame Surface，并缩放到指定尺寸"""
    if frame is None:
        return None
    try:
        transposed = np.transpose(frame, (1, 0, 2))
        surf = pygame.surfarray.make_surface(transposed)
        # convert() 与显示格式一致，大幅提升后续 blit 速度
        return pygame.transform.smoothscale(surf, (target_w, target_h)).convert()
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

    def update(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surf, font):
        c = self.hover_color if self.hovered else self.color
        btn = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn, c, btn.get_rect(), border_radius=14)
        pygame.draw.rect(btn, (255, 255, 255, 200), btn.get_rect(), 2, border_radius=14)
        surf.blit(btn, self.rect.topleft)
        label = font.render(self.text, True, self.text_color)
        lr = label.get_rect(center=self.rect.center)
        surf.blit(label, lr)

    def clicked(self, pos):
        return self.rect.collidepoint(pos)


# ===================== 主程序 =====================
class GestureApp:
    TITLE_H = 130
    FOOTER_H = 120

    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('手势控制RGB灯带')
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 56)
        self.font_sub = pygame.font.Font(FONT_PATH, 28)
        self.font_gesture = pygame.font.Font(FONT_BOLD_PATH, 56)
        self.font_effect = pygame.font.Font(FONT_BOLD_PATH, 36)
        self.font_desc = pygame.font.Font(FONT_PATH, 26)
        self.font_item = pygame.font.Font(FONT_PATH, 26)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 32)
        self.font_small = pygame.font.Font(FONT_PATH, 22)

        # 背景：优先加载 images/1.jpg，失败回退渐变
        try:
            bg_raw = pygame.image.load('images/1.jpg')
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print('背景图片加载失败，使用渐变背景:', e)
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # 布局
        self.cam_rect = pygame.Rect(40, self.TITLE_H + 20, CAM_DISP_W, CAM_DISP_H)
        self.info_rect = pygame.Rect(self.cam_rect.right + 30, self.TITLE_H + 20,
                                     WIDTH - self.cam_rect.right - 30 - 40,
                                     HEIGHT - self.TITLE_H - 20 - self.FOOTER_H)

        # 退出按钮（底部右侧）
        self.btn_exit = Button((WIDTH - 260, HEIGHT - 95, 200, 70),
                               '退出程序', EXIT_COLOR, EXIT_HOVER)

        # 打开摄像头
        print('外接摄像头打开中...')
        self.cap = open_camera()
        self.camera_ok = self.cap is not None and self.cap.isOpened()
        if self.camera_ok:
            print('外接摄像头已打开')
        else:
            print('摄像头打开失败，请检查 /dev/video41 和 /dev/video40')

        # 状态
        self.running = True
        self.raw_frame = None        # 采集线程写入的最新原始帧(BGR)
        self.latest_frame = None     # 识别线程写入的最新处理帧(RGB,已绘制关键点)
        self.latest_gesture = 'none'
        self.frame_lock = threading.Lock()
        self.cam_thread_running = True
        self.current_gesture = 'none'
        self.pending_gesture = 'none'
        self.pending_count = 0

        # 分离采集与识别线程：
        #   采集线程只快速 read()，避免 V4L2 内核缓冲区积压旧帧导致画面延迟；
        #   识别线程取最新帧做 mediapipe 处理，处理不过来就跳过中间帧(自动降帧)。
        threading.Thread(target=self.camera_capture_loop, daemon=True).start()
        threading.Thread(target=self.gesture_recognition_loop, daemon=True).start()

    def camera_capture_loop(self):
        """后台线程：仅快速读取摄像头帧，不做任何处理，保证画面实时"""
        fail = 0
        while self.cam_thread_running:
            if not self.camera_ok or self.cap is None:
                time.sleep(0.2)
                continue
            try:
                ok, frame = self.cap.read()
                if ok and frame is not None:
                    # 总是覆盖旧帧，丢弃积压帧
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

    def gesture_recognition_loop(self):
        """后台线程：取最新帧做手势识别+绘制关键点，不阻塞采集线程"""
        while self.cam_thread_running:
            with self.frame_lock:
                frame = self.raw_frame
            if frame is None:
                time.sleep(0.02)
                continue
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb)
                gesture = 'none'
                if results.multi_hand_landmarks:
                    # 在 RGB 帧上绘制手部关键点和连接线
                    mp_drawing.draw_landmarks(
                        rgb,
                        results.multi_hand_landmarks[0],
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style())
                    gesture = recognize_gesture(results.multi_hand_landmarks[0].landmark)
                with self.frame_lock:
                    self.latest_frame = rgb
                    self.latest_gesture = gesture
            except Exception as e:
                if self.cam_thread_running:
                    print('手势识别异常:', e)
                time.sleep(0.1)

    def update_gesture(self):
        """防抖更新手势：连续 CONFIRM_FRAMES 帧相同才切换"""
        with self.frame_lock:
            g = self.latest_gesture
        if g == self.pending_gesture:
            self.pending_count += 1
        else:
            self.pending_gesture = g
            self.pending_count = 1
        if self.pending_count >= CONFIRM_FRAMES and g != self.current_gesture:
            self.current_gesture = g
            set_led_effect(g)
            info = GESTURE_MAP[g]
            print('手势切换：%s -> 灯效：%s' % (info['name'], info['effect']))

    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('手势控制RGB灯带', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 25))
        sub = self.font_sub.render(
            'USB摄像头识别手势  ·  IO1 RGB灯带(4灯珠)  ·  不同手势对应不同灯效',
            True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 90))

    def draw_camera(self):
        """绘制摄像头画面区域"""
        # 面板背景
        panel = pygame.Surface(self.cam_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.cam_rect.topleft)

        # 标题
        head = self.font_sub.render('摄像头画面', True, TITLE_COLOR)
        self.screen.blit(head, (self.cam_rect.x + 20, self.cam_rect.y + 10))

        # 摄像头状态
        status = '● 已连接' if self.camera_ok else '○ 未连接'
        sc = SUCCESS_COLOR if self.camera_ok else ERROR_COLOR
        st = self.font_small.render(status, True, sc)
        self.screen.blit(st, (self.cam_rect.right - st.get_width() - 20, self.cam_rect.y + 15))

        # 摄像头画面
        with self.frame_lock:
            frame = self.latest_frame
        if frame is not None:
            surf = cvframe_to_surface(frame, CAM_DISP_W - 40, CAM_DISP_H - 70)
            if surf is not None:
                self.screen.blit(surf, (self.cam_rect.x + 20, self.cam_rect.y + 50))
        else:
            hint_text = '摄像头未连接' if not self.camera_ok else '等待画面...'
            hint_color = ERROR_COLOR if not self.camera_ok else SUBTLE_COLOR
            hint = self.font_sub.render(hint_text, True, hint_color)
            self.screen.blit(hint, (self.cam_rect.centerx - hint.get_width() // 2,
                                    self.cam_rect.centery - hint.get_height() // 2))

    def draw_info_panel(self):
        """绘制右侧信息面板：当前手势 + 灯效 + 对照表"""
        # 面板背景
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 30
        y = self.info_rect.y + 15

        # ---- 当前手势 ----
        head = self.font_sub.render('当前手势', True, TITLE_COLOR)
        self.screen.blit(head, (x, y))
        y += 40

        g = GESTURE_MAP[self.current_gesture]
        # 手势名称（大字，带颜色）
        gesture_text = self.font_gesture.render(g['name'], True, g['color'])
        self.screen.blit(gesture_text, (x, y))
        y += 75

        # 灯效名称
        effect_label = self.font_effect.render('灯效：' + g['effect'], True, TEXT_COLOR)
        self.screen.blit(effect_label, (x, y))
        y += 48

        # 灯效说明
        desc_text = self.font_desc.render(g['desc'], True, SUBTLE_COLOR)
        self.screen.blit(desc_text, (x, y))
        y += 40

        # 分隔线
        pygame.draw.line(self.screen, PANEL_BORDER,
                         (x, y), (self.info_rect.right - 30, y), 2)
        y += 20

        # ---- 手势 · 灯效对照表 ----
        head2 = self.font_sub.render('手势 · 灯效对照表', True, TITLE_COLOR)
        self.screen.blit(head2, (x, y))
        y += 40

        for key in ['fist', 'open_palm', 'thumb_up', 'victory',
                     'point_up', 'ok', 'iloveyou', 'none']:
            item = GESTURE_MAP[key]
            is_current = (key == self.current_gesture)

            # 当前选中项高亮背景
            if is_current:
                highlight = pygame.Surface((self.info_rect.w - 60, 52), pygame.SRCALPHA)
                pygame.draw.rect(highlight, (*item['color'], 60),
                                 highlight.get_rect(), border_radius=10)
                pygame.draw.rect(highlight, item['color'],
                                 highlight.get_rect(), 2, border_radius=10)
                self.screen.blit(highlight, (self.info_rect.x + 30, y - 4))

            # 色块
            pygame.draw.rect(self.screen, item['color'],
                             (x + 10, y + 6, 28, 28), border_radius=6)

            # 手势名称
            name_surf = self.font_item.render(item['name'], True, TEXT_COLOR)
            self.screen.blit(name_surf, (x + 55, y))

            # 灯效名称（右侧）
            effect_surf = self.font_item.render(item['effect'], True, item['color'])
            self.screen.blit(effect_surf, (self.info_rect.right - 30 - effect_surf.get_width(), y))

            y += 52

    def draw_footer(self, mouse_pos):
        """绘制底部栏：退出按钮 + 提示信息"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        # 退出按钮
        self.btn_exit.update(mouse_pos)
        self.btn_exit.draw(self.screen, self.font_btn)

        # 提示信息
        hint = self.font_small.render(
            'ESC 或点击「退出程序」退出  ·  将手对准摄像头做出手势  ·  连续%d帧确认手势' % CONFIRM_FRAMES,
            True, SUBTLE_COLOR)
        self.screen.blit(hint, (40, HEIGHT - 50))

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
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False

            # 更新手势（防抖）
            self.update_gesture()

            # 按帧更新 RGB 灯效
            update_led_frame()

            # 绘制界面
            self.screen.blit(self.bg, (0, 0))
            self.draw_title()
            self.draw_camera()
            self.draw_info_panel()
            self.draw_footer(mouse_pos)

            pygame.display.flip()
            self.clock.tick(30)

        # 退出清理
        self.cam_thread_running = False
        time.sleep(0.2)
        try:
            if self.cap is not None:
                self.cap.release()
        except:
            pass
        try:
            hands.close()
        except:
            pass
        led_off()
        pygame.quit()


# ===================== 入口 =====================
if __name__ == '__main__':
    app = GestureApp()
    app.run()
