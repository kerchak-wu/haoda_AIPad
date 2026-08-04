# -*- coding: utf-8 -*-
"""
人脸表情识别系统 - 好搭AI派程序
=====================================
功能说明：
  1. 调用百度智能云人脸识别 API，识别 USB 摄像头画面中的人脸表情
  2. 界面 1920x1080，科技感深色主题
  3. 实时显示摄像头画面（后台抓帧 + scale 缩放，降低延迟）
  4. OpenCV Haar 级联分类器实时绘制人脸框（本地推理，无延迟）
  5. 百度 AI 每隔约 1.5 秒检测一次表情/情绪/年龄/性别/眼镜
  6. 右侧面板展示识别结果（表情类型、概率进度条、附加信息）
  7. 退出按钮 + ESC 快捷键

硬件依赖：
  - USB 外接摄像头（好搭AI派 USB 接口）
  - 需联网（百度智能云在线 API）

第三方库：
  - baidu-aip（百度 AI SDK）
  - opencv-python
  - camera_vision_system_v3（好搭AI派视觉 SDK）

参考范例：
  - 范例代码 8.pygame 10.音乐播放-按钮（按钮事件模式）
  - 本地参考：文字识别播报器.py（camera_vision_system_v3 + 后台线程抓帧 + Pygame 显示）
"""

import os
# 强制 libGL 使用软件渲染，避免 rockchip 平台 GPU 驱动加载失败
# 必须在 import cv2 / pygame 之前设置
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

import time
import base64
import threading

# 导入顺序很关键：必须先 import pygame，再 import cv2
# 在 rockchip 平台上，cv2 先导入会尝试初始化 OpenGL 上下文，
# 加载 rockchip GPU 驱动失败导致 "failed to create dri screen" 崩溃。
# pygame 先导入让 SDL 接管视频子系统，cv2 不会再重复初始化 OpenGL。
# 参照本地可正常运行的 人脸识别播放视频.py 的导入顺序。
import pygame
import cv2
import numpy as np
from aip import AipFace
from camera_vision_system_v3 import create_vision_system_v3

# ===================== 配置 =====================
WIDTH, HEIGHT = 1920, 1080

# 百度智能云认证信息
BAIDU_APP_ID = ''
BAIDU_API_KEY = ''
BAIDU_SECRET_KEY = ''

# 表情检测间隔（秒）
# 5 秒间隔确保 API 调用期间帧抓取线程有足够 CPU 时间片，
# 避免因 GIL 占用导致 SDK 摄像头读取超时触发重连
DETECT_INTERVAL = 5.0

# 摄像头参数（与 vision_system 初始化一致）
CAMERA_W, CAMERA_H = 640, 480

# 字体路径（参照《好搭AI派可用字体列表.txt》及本地范例）
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'
FONT_REG_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'

# ---- 界面配色（科技感深色主题） ----
BG_TOP = (10, 14, 30)
BG_BOTTOM = (4, 6, 18)
PANEL_COLOR = (16, 22, 44)
PANEL_BORDER = (0, 160, 210)
TITLE_COLOR = (0, 229, 255)
SUBTLE_COLOR = (120, 150, 190)
TEXT_COLOR = (230, 240, 250)
TEXT_DIM = (140, 160, 190)
ACCENT_CYAN = (0, 229, 255)
ACCENT_ORANGE = (255, 170, 60)
ACCENT_GREEN = (0, 255, 136)
ACCENT_YELLOW = (255, 200, 60)
ACCENT_RED = (255, 80, 90)
ACCENT_PURPLE = (180, 120, 255)
BTN_EXIT_COLOR = (90, 90, 110)
BTN_EXIT_HOVER = (200, 70, 80)
STATUS_READY = ACCENT_GREEN
STATUS_BUSY = ACCENT_YELLOW
STATUS_ERROR = ACCENT_RED

# 表情 -> 中文 + 主题色
EXPRESSION_MAP = {
    'none': ('无表情', TEXT_DIM),
    'smile': ('微笑', ACCENT_GREEN),
    'laugh': ('大笑', ACCENT_YELLOW),
}

# 情绪 -> 中文 + 主题色
EMOTION_MAP = {
    'angry': ('愤怒', ACCENT_RED),
    'disgust': ('厌恶', (160, 200, 80)),
    'fear': ('恐惧', ACCENT_PURPLE),
    'happy': ('开心', ACCENT_GREEN),
    'sad': ('悲伤', (100, 160, 255)),
    'surprise': ('惊讶', ACCENT_ORANGE),
    'neutral': ('中性', TEXT_DIM),
}

# 眼镜 -> 中文
GLASSES_MAP = {
    'none': '无眼镜',
    'common': '普通眼镜',
    'sun': '太阳镜',
}

# 性别 -> 中文
GENDER_MAP = {
    'male': '男',
    'female': '女',
}


# ===================== 视觉系统初始化（参照文字识别播报器.py） =====================
# 使用 camera_vision_system_v3（好搭AI派 SDK），兼容 rockchip 平台。
# cv2.VideoCapture 直接操作 V4L2 设备会与 SDL2 冲突导致 "Bad file descriptor"。
vision_system = create_vision_system_v3(
    camera_id=-1, width=640, height=480,
    enable_basic=False, enable_advanced=False
)
print("视觉系统初始化完成（camera_id=-1 自动检测）")

camera_ok = False  # 在 ExpressionApp.__init__() 中 vision_system.open_camera() 后更新


# ===================== 百度 AI 客户端 =====================
baidu_client = AipFace(BAIDU_APP_ID, BAIDU_API_KEY, BAIDU_SECRET_KEY)
print("百度人脸识别客户端已初始化（APP_ID=%s）" % BAIDU_APP_ID)


# ===================== OpenCV 人脸检测器（用于实时画框） =====================
face_cascade = None
try:
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        face_cascade = None
        print("警告：Haar 级联分类器加载为空，将不绘制人脸框")
    else:
        print("OpenCV 人脸检测器已加载")
except Exception as e:
    print("警告：无法加载 Haar 级联分类器:", e)
    face_cascade = None


# ===================== 全局状态 =====================
# 百度 API 检测结果
latest_expression = None
latest_emotion = None
latest_age = None
latest_gender = None
latest_glasses = None
latest_face_prob = None
face_num = 0

# 检测状态
is_detecting = False
detect_error = None
last_detect_time = 0.0
status_message = '初始化中...'
status_color = STATUS_BUSY

# 线程控制
detection_running = True
frame_capture_running = True

# 全局帧缓冲（后台抓帧线程写入，检测线程和主循环读取）
_latest_bgr = None
_frame_lock = threading.Lock()

# 摄像头状态
camera_ever_success = False       # 摄像头是否曾经成功读到过帧


# ===================== 后台帧抓取线程（参照文字识别播报器.py） =====================
def frame_capture_worker():
    """后台线程：持续调用 vision_system.capture_frame() 抓帧做缓冲。

    参照文字识别播报器.py 的 _frame_capture_worker：
      - 必须先 refresh_results，否则 capture_frame 可能返回 None
      - capture_frame 非阻塞读取后台缓冲帧，不会卡住主循环
    """
    global _latest_bgr, camera_ever_success

    while frame_capture_running:
        if not camera_ok:
            time.sleep(0.2)
            continue
        try:
            vision_system.result_accessor.refresh_results()
            frame = vision_system.capture_frame()
            if frame is not None:
                with _frame_lock:
                    _latest_bgr = frame
                camera_ever_success = True
        except Exception:
            pass
        time.sleep(0.01)  # 必须与文字识别播报器保持一致，SDK 期望高频调用 capture_frame


# ===================== 百度表情检测（后台线程） =====================
def detection_worker():
    """后台线程：每隔 DETECT_INTERVAL 秒调用百度 API 检测表情"""
    global latest_expression, latest_emotion, latest_age, latest_gender
    global latest_glasses, latest_face_prob, face_num
    global is_detecting, detect_error, last_detect_time, status_message, status_color

    while detection_running:
        if time.time() - last_detect_time < DETECT_INTERVAL:
            time.sleep(0.1)
            continue

        # 从全局帧缓冲读取最新帧
        with _frame_lock:
            frame = _latest_bgr
        if frame is not None:
            frame = frame.copy()

        if frame is None:
            time.sleep(0.1)
            continue

        is_detecting = True
        status_message = '正在识别表情...'
        status_color = STATUS_BUSY

        try:
            # 缩小图片再编码，减少 CPU 占用和传输数据量（百度 API 接受小图）
            # 640x480 -> 160x120，编码时间减少约 16 倍
            small_frame = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
            time.sleep(0.05)  # 释放 GIL，让帧抓取线程有机会运行
            # JPEG 质量降到 60，进一步减少编码时间和数据量
            _, buffer = cv2.imencode('.jpg', small_frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            time.sleep(0.05)  # 释放 GIL
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            time.sleep(0.05)  # 释放 GIL，确保网络请求前帧抓取线程能运行

            # 调用百度人脸检测 API
            result = baidu_client.detect(
                image_base64, 'BASE64',
                {
                    'face_field': 'expression,emotion,gender,age,glasses',
                    'max_face_num': 1,
                    'face_type': 'LIVE'
                }
            )

            last_detect_time = time.time()

            if result is None:
                detect_error = 'API 返回为空'
                status_message = '识别失败：无返回'
                status_color = STATUS_ERROR
                continue

            error_code = result.get('error_code', -1)
            if error_code != 0:
                error_msg = result.get('error_msg', '未知错误')
                detect_error = '[%s] %s' % (error_code, error_msg)
                # 222202/222203 = 未检测到人脸，不算错误
                if error_code in (222202, 222203):
                    _clear_face_result()
                    status_message = '未检测到人脸'
                    status_color = TEXT_DIM
                    detect_error = None
                else:
                    status_message = '识别错误: %s' % error_msg
                    status_color = STATUS_ERROR
                continue

            # 解析检测结果
            result_data = result.get('result', {})
            face_num = result_data.get('face_num', 0)
            face_list = result_data.get('face_list', [])

            if face_list:
                face = face_list[0]
                latest_expression = face.get('expression')
                latest_emotion = face.get('emotion')
                latest_age = face.get('age')
                latest_gender = face.get('gender')
                latest_glasses = face.get('glasses')
                latest_face_prob = face.get('face_probability')
                detect_error = None

                expr_text = _get_expression_text()
                status_message = '识别成功：%s' % expr_text
                status_color = STATUS_READY
            else:
                _clear_face_result()
                status_message = '未检测到人脸'
                status_color = TEXT_DIM

        except Exception as e:
            detect_error = str(e)
            status_message = '识别异常: %s' % str(e)[:40]
            status_color = STATUS_ERROR
            last_detect_time = time.time()
        finally:
            is_detecting = False


def _clear_face_result():
    """清空人脸检测结果"""
    global latest_expression, latest_emotion, latest_age, latest_gender
    global latest_glasses, latest_face_prob, face_num
    latest_expression = None
    latest_emotion = None
    latest_age = None
    latest_gender = None
    latest_glasses = None
    latest_face_prob = None
    face_num = 0


def _get_expression_text():
    """获取当前表情中文文本"""
    if latest_expression and latest_expression.get('type'):
        expr_type = latest_expression['type']
        return EXPRESSION_MAP.get(expr_type, ('未知', TEXT_DIM))[0]
    return '未知'


# 后台线程对象（在 ExpressionApp.run() 中启动，确保 pygame 先初始化）
frame_thread = None
detect_thread = None


# ===================== Pygame 界面 =====================
def make_gradient_bg(width, height, top, bottom):
    """生成垂直渐变背景（用 numpy 向量化，比逐行绘制快 100 倍）"""
    # 生成每行的颜色插值
    ratios = np.linspace(0, 1, height, dtype=np.float32).reshape(-1, 1)
    top_arr = np.array(top, dtype=np.float32).reshape(1, 3)
    bottom_arr = np.array(bottom, dtype=np.float32).reshape(1, 3)
    colors = (top_arr + (bottom_arr - top_arr) * ratios)  # (height, 3)
    # 扩展到 (height, width, 3)
    img = np.tile(colors[:, np.newaxis, :], (1, width, 1)).astype(np.uint8)
    # numpy (h, w, 3) -> pygame Surface
    return pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))


class Button:
    """通用圆角按钮（参照文字识别播报器.py）"""

    def __init__(self, rect, text, color, hover_color, text_color=TEXT_COLOR):
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
            c = (50, 52, 68)
        btn = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn, c, btn.get_rect(), border_radius=14)
        border_c = (255, 255, 255, 200) if self.hovered else (120, 200, 230, 150)
        pygame.draw.rect(btn, border_c, btn.get_rect(), 2, border_radius=14)
        surf.blit(btn, self.rect.topleft)
        label = font.render(self.text, True, self.text_color)
        lr = label.get_rect(center=self.rect.center)
        surf.blit(label, lr)

    def clicked(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


class ExpressionApp:
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
        # （参照人脸识别播放视频.py）
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('人脸表情识别系统')
        self.clock = pygame.time.Clock()

        # 字体
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 52)
        self.font_sub = pygame.font.Font(FONT_REG_PATH, 24)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_label = pygame.font.Font(FONT_BOLD_PATH, 28)
        self.font_small = pygame.font.Font(FONT_REG_PATH, 22)
        self.font_status = pygame.font.Font(FONT_BOLD_PATH, 26)
        self.font_expr = pygame.font.Font(FONT_BOLD_PATH, 72)
        self.font_emotion = pygame.font.Font(FONT_BOLD_PATH, 42)
        self.font_info = pygame.font.Font(FONT_REG_PATH, 30)
        self.font_prob = pygame.font.Font(FONT_BOLD_PATH, 24)

        # 背景：优先加载 images/1.jpg，失败则回退渐变背景
        # convert() 转为屏幕像素格式，大幅加速后续 blit
        try:
            bg_raw = pygame.image.load(os.path.join('images', '1.jpg'))
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception:
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # 预创建面板 Surface（避免每帧重复创建，大幅降低 CPU 占用）
        self.cam_panel_surf = pygame.Surface(
            (self.CAM_PANEL_W, self.CAM_PANEL_H), pygame.SRCALPHA).convert_alpha()
        pygame.draw.rect(self.cam_panel_surf, (*PANEL_COLOR, 220),
                         self.cam_panel_surf.get_rect(), border_radius=16)
        self.result_panel_surf = pygame.Surface(
            (self.RESULT_W, self.RESULT_H), pygame.SRCALPHA).convert_alpha()
        pygame.draw.rect(self.result_panel_surf, (*PANEL_COLOR, 220),
                         self.result_panel_surf.get_rect(), border_radius=16)

        self.running = True
        self.current_frame = None

        # 退出按钮
        btn_y = HEIGHT - self.FOOTER_H + 38
        self.btn_exit = Button(
            (WIDTH - 264, btn_y, 240, 70),
            '退出', BTN_EXIT_COLOR, BTN_EXIT_HOVER
        )

        # Haar 级联检测节流（每 N 帧检测一次，降低 CPU 占用）
        self._haar_frame_count = 0
        self._haar_faces = []

        # 摄像头打开 + 后台检测（参照文字识别播报器.py）
        global camera_ok
        if vision_system.open_camera():
            camera_ok = True
            print("摄像头已打开（自动检测模式）")
        else:
            camera_ok = False
            print("警告：摄像头打开失败，请检查硬件连接")
        # 启动后台检测，不显示 OpenCV 预览窗口（画面由 Pygame 显示）
        vision_system.threaded_system.start_background_detection(show_preview=False)
        print("摄像头后台检测已启动")

    # ---------- 摄像头帧获取与转换 ----------
    def grab_frame(self):
        """从全局帧缓冲读取最新帧并转为 Surface（非阻塞）"""
        with _frame_lock:
            frame = _latest_bgr
        if frame is None:
            return None
        self.current_frame = frame
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]
            # frombuffer 比 surfarray.make_surface 快，减少延迟
            surf = pygame.image.frombuffer(frame_rgb.tobytes(), (w, h), 'RGB')
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

    def detect_faces_haar(self, frame):
        """OpenCV Haar 级联分类器检测人脸（本地推理，无延迟）"""
        if face_cascade is None or frame is None:
            return []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60)
            )
            return faces
        except Exception:
            return []

    # ---------- 绘制 ----------
    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (0, 10, 30, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))
        pygame.draw.line(self.screen, ACCENT_CYAN, (0, self.TITLE_H), (WIDTH, self.TITLE_H), 2)
        pygame.draw.line(self.screen, (0, 100, 130), (0, self.TITLE_H + 2), (WIDTH, self.TITLE_H + 2), 1)

        title = self.font_title.render('人脸表情识别系统', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 18))

        sub = self.font_sub.render(
            'FACE  EXPRESSION  RECOGNITION   |   百度智能云  ->  USB摄像头  ->  实时表情分析',
            True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 76))

    def draw_corner_brackets(self, x, y, w, h):
        """在摄像头画面四角绘制科技感瞄准框"""
        blen = 30
        c = ACCENT_CYAN
        t = 3
        pygame.draw.line(self.screen, c, (x, y), (x + blen, y), t)
        pygame.draw.line(self.screen, c, (x, y), (x, y + blen), t)
        pygame.draw.line(self.screen, c, (x + w, y), (x + w - blen, y), t)
        pygame.draw.line(self.screen, c, (x + w, y), (x + w, y + blen), t)
        pygame.draw.line(self.screen, c, (x, y + h), (x + blen, y + h), t)
        pygame.draw.line(self.screen, c, (x, y + h), (x, y + h - blen), t)
        pygame.draw.line(self.screen, c, (x + w, y + h), (x + w - blen, y + h), t)
        pygame.draw.line(self.screen, c, (x + w, y + h), (x + w, y + h - blen), t)

    def draw_camera_panel(self):
        """绘制摄像头画面区域"""
        panel_rect = pygame.Rect(self.CAM_PANEL_X, self.CAM_PANEL_Y,
                                 self.CAM_PANEL_W, self.CAM_PANEL_H)

        # 使用预创建的面板 Surface（避免每帧重复创建）
        self.screen.blit(self.cam_panel_surf, panel_rect.topleft)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel_rect, 2, border_radius=16)

        label = self.font_label.render('摄像头实时画面', True, ACCENT_CYAN)
        self.screen.blit(label, (panel_rect.x + 24, panel_rect.y + 18))

        res_text = self.font_small.render('%d x %d' % (CAMERA_W, CAMERA_H), True, TEXT_DIM)
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

            # Haar 人脸检测（每 10 帧检测一次，降低 CPU 占用）
            self._haar_frame_count += 1
            if self._haar_frame_count % 10 == 0:
                self._haar_faces = self.detect_faces_haar(self.current_frame)

            # 绘制人脸框
            for (fx, fy, fw, fh) in self._haar_faces:
                rx = ox + int(fx * scale_factor)
                ry = oy + int(fy * scale_factor)
                rw = int(fw * scale_factor)
                rh = int(fh * scale_factor)

                # 根据表情选择框颜色
                box_color = ACCENT_CYAN
                if latest_expression and latest_expression.get('type'):
                    expr_type = latest_expression['type']
                    if expr_type in EXPRESSION_MAP:
                        box_color = EXPRESSION_MAP[expr_type][1]

                pygame.draw.rect(self.screen, box_color, (rx, ry, rw, rh), 3, border_radius=6)

                # 人脸框上方标签
                expr_label = _get_expression_text()
                tag = self.font_small.render(expr_label, True, (0, 0, 0))
                tag_bg_w = tag.get_width() + 16
                tag_bg_h = tag.get_height() + 6
                tag_bg = pygame.Surface((tag_bg_w, tag_bg_h), pygame.SRCALPHA)
                tag_bg.fill((box_color[0], box_color[1], box_color[2], 220))
                tag_y = max(oy, ry - tag_bg_h)
                self.screen.blit(tag_bg, (rx, tag_y))
                self.screen.blit(tag, (rx + 8, tag_y + 3))

            # 检测中扫描动画
            if is_detecting:
                scan_y = int(time.time() * 200) % sh
                line_y = oy + scan_y
                pygame.draw.line(self.screen, ACCENT_CYAN, (ox, line_y), (ox + sw, line_y), 2)
                glow = pygame.Surface((sw, 20), pygame.SRCALPHA)
                pygame.draw.rect(glow, (0, 229, 255, 50), glow.get_rect())
                self.screen.blit(glow, (ox, line_y - 10))
        else:
            if not camera_ok:
                hint = self.font_label.render(
                    '摄像头未打开，请检查 USB 摄像头连接', True, STATUS_ERROR)
            else:
                hint = self.font_label.render('摄像头启动中...', True, ACCENT_CYAN)
            self.screen.blit(hint, (panel_rect.centerx - hint.get_width() // 2,
                                    panel_rect.centery - hint.get_height() // 2))

    def draw_progress_bar(self, x, y, w, h, ratio, color):
        """绘制圆角进度条"""
        ratio = max(0.0, min(1.0, ratio))
        pygame.draw.rect(self.screen, (40, 50, 70), (x, y, w, h), border_radius=h // 2)
        fill_w = int(w * ratio)
        if fill_w > 0:
            pygame.draw.rect(self.screen, color, (x, y, fill_w, h), border_radius=h // 2)

    def draw_result_panel(self):
        """绘制右侧表情识别结果区域"""
        global status_message, status_color
        panel_rect = pygame.Rect(self.RESULT_X, self.RESULT_Y, self.RESULT_W, self.RESULT_H)

        # 使用预创建的面板 Surface（避免每帧重复创建）
        self.screen.blit(self.result_panel_surf, panel_rect.topleft)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel_rect, 2, border_radius=16)

        label = self.font_label.render('识别结果', True, ACCENT_CYAN)
        self.screen.blit(label, (panel_rect.x + 24, panel_rect.y + 18))

        # 状态指示灯
        dot_x = panel_rect.right - 30
        dot_y = panel_rect.y + 32
        pygame.draw.circle(self.screen, status_color, (dot_x, dot_y), 8)
        glow_surf = pygame.Surface((30, 30), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*status_color, 80), (15, 15), 14)
        self.screen.blit(glow_surf, (dot_x - 15, dot_y - 15))

        sep_y = panel_rect.y + 60
        pygame.draw.line(self.screen, PANEL_BORDER,
                         (panel_rect.x + 20, sep_y), (panel_rect.right - 20, sep_y), 1)

        content_x = panel_rect.x + 30
        content_w = panel_rect.w - 60
        cy = sep_y + 24

        # ---- 表情（主结果） ----
        section_label = self.font_small.render('表 情', True, TEXT_DIM)
        self.screen.blit(section_label, (content_x, cy))
        cy += 32

        if latest_expression and latest_expression.get('type'):
            expr_type = latest_expression['type']
            expr_cn, expr_color = EXPRESSION_MAP.get(expr_type, ('未知', TEXT_DIM))
            prob = latest_expression.get('probability', 0)

            expr_surf = self.font_expr.render(expr_cn, True, expr_color)
            self.screen.blit(expr_surf, (content_x, cy))
            cy += 88

            prob_label = self.font_prob.render('置信度  %.1f%%' % (prob * 100), True, TEXT_COLOR)
            self.screen.blit(prob_label, (content_x, cy))
            cy += 32
            self.draw_progress_bar(content_x, cy, content_w, 18, prob, expr_color)
            cy += 36
        else:
            hint = self.font_emotion.render('等待检测...', True, TEXT_DIM)
            self.screen.blit(hint, (content_x, cy))
            cy += 56

        # ---- 情绪 ----
        cy += 8
        section_label = self.font_small.render('情 绪', True, TEXT_DIM)
        self.screen.blit(section_label, (content_x, cy))
        cy += 32

        if latest_emotion and latest_emotion.get('type'):
            emo_type = latest_emotion['type']
            emo_cn, emo_color = EMOTION_MAP.get(emo_type, ('未知', TEXT_DIM))
            emo_prob = latest_emotion.get('probability', 0)

            emo_surf = self.font_emotion.render(emo_cn, True, emo_color)
            self.screen.blit(emo_surf, (content_x, cy))
            cy += 52

            self.draw_progress_bar(content_x, cy, content_w, 16, emo_prob, emo_color)
            cy += 30
        else:
            hint = self.font_info.render('--', True, TEXT_DIM)
            self.screen.blit(hint, (content_x, cy))
            cy += 40

        # ---- 附加信息 ----
        cy += 12
        pygame.draw.line(self.screen, PANEL_BORDER,
                         (panel_rect.x + 20, cy), (panel_rect.right - 20, cy), 1)
        cy += 16

        info_items = []
        if latest_age is not None:
            info_items.append(('年龄', str(latest_age) + ' 岁'))
        if latest_gender and latest_gender.get('type'):
            gender_cn = GENDER_MAP.get(latest_gender['type'], latest_gender['type'])
            info_items.append(('性别', gender_cn))
        if latest_glasses and latest_glasses.get('type'):
            glasses_cn = GLASSES_MAP.get(latest_glasses['type'], latest_glasses['type'])
            info_items.append(('眼镜', glasses_cn))
        if latest_face_prob is not None:
            info_items.append(('人脸置信度', '%.1f%%' % (latest_face_prob * 100)))

        for label_text, value_text in info_items:
            lbl = self.font_info.render(label_text, True, TEXT_DIM)
            val = self.font_info.render(value_text, True, TEXT_COLOR)
            self.screen.blit(lbl, (content_x, cy))
            val_x = panel_rect.right - 30 - val.get_width()
            self.screen.blit(val, (val_x, cy))
            cy += 38

        # ---- 底部状态 ----
        cy = panel_rect.bottom - 80
        if detect_error:
            err_surf = self.font_small.render(detect_error[:30], True, STATUS_ERROR)
            self.screen.blit(err_surf, (content_x, cy))
            cy += 26

        if last_detect_time > 0:
            elapsed = time.time() - last_detect_time
            time_text = self.font_small.render(
                '上次检测: %.1fs 前' % elapsed, True, TEXT_DIM)
        else:
            time_text = self.font_small.render('尚未检测', True, TEXT_DIM)
        self.screen.blit(time_text, (content_x, cy))

        interval_text = self.font_small.render(
            '间隔: %.1fs' % DETECT_INTERVAL, True, TEXT_DIM)
        self.screen.blit(interval_text,
                         (panel_rect.right - 30 - interval_text.get_width(), cy))

    def draw_footer(self, mouse_pos):
        """绘制底部按钮栏"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (0, 10, 30, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))
        pygame.draw.line(self.screen, ACCENT_CYAN,
                         (0, HEIGHT - self.FOOTER_H), (WIDTH, HEIGHT - self.FOOTER_H), 2)

        self.btn_exit.update(mouse_pos)
        self.btn_exit.draw(self.screen, self.font_btn)

        # 状态文字
        status = self.font_status.render(status_message, True, status_color)
        self.screen.blit(status, (24, HEIGHT - self.FOOTER_H + 58))

        # 人脸数量
        if face_num > 0:
            face_text = self.font_small.render(
                '检测到 %d 张人脸' % face_num, True, ACCENT_CYAN)
            self.screen.blit(face_text, (24, HEIGHT - self.FOOTER_H + 95))

        # 操作提示
        hint = self.font_small.render(
            'ESC = 退出    程序自动每 %.1f 秒识别一次表情' % DETECT_INTERVAL,
            True, TEXT_DIM)
        self.screen.blit(hint, (560, HEIGHT - self.FOOTER_H + 95))

    # ---------- 事件处理 ----------
    def handle_click(self, pos):
        if self.btn_exit.clicked(pos):
            self.running = False

    # ---------- 主循环 ----------
    def run(self):
        global detection_running, frame_capture_running
        global frame_thread, detect_thread

        # 在 pygame 初始化完成后启动后台线程，避免 cv2 与 pygame 资源冲突
        frame_thread = threading.Thread(target=frame_capture_worker, daemon=True)
        frame_thread.start()
        detect_thread = threading.Thread(target=detection_worker, daemon=True)
        detect_thread.start()

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
                self.draw_title()
                self.draw_camera_panel()
                self.draw_result_panel()
                self.draw_footer(mouse_pos)

                pygame.display.flip()
            except Exception as e:
                print("绘制异常: {}".format(e))
                import traceback
                traceback.print_exc()

            self.clock.tick(30)

        # ---- 退出清理 ----
        frame_capture_running = False
        detection_running = False
        if frame_thread is not None:
            frame_thread.join(timeout=2)
        if detect_thread is not None:
            detect_thread.join(timeout=2)
        try:
            vision_system.close_camera()
            print("摄像头已释放")
        except Exception:
            pass
        pygame.quit()
        print('程序已退出')


# ===================== 入口 =====================
if __name__ == '__main__':
    app = ExpressionApp()
    app.run()