# -*- coding: utf-8 -*-
"""
人脸学习程序 - 好搭AI派
======================
功能说明：
  1. USB外接摄像头实时采集画面（cv2）
  2. 输入姓名标签，将当前画面注册为人脸样本
  3. 界面显示摄像头画面、学习状态和已学习人脸列表
  4. 人脸记录持久化到 JSON 文件，重启后自动加载
  5. 可选择删除已学习的人脸记录
  6. 提供 FaceLearner 类，可供其他程序导入调用

硬件接线：
  - USB外接摄像头(/dev/video41 或 /dev/video40)
  - 好搭AI派扩展板(ESP32)
  注意：好搭AI派右下角开关需拨到左侧以启用外设接口。

依赖库：
  pygame, cv2(opencv), numpy, ESP32, camera_vision_system_v3(好搭AI派自带)

参考范例：
  - 范例代码 5.9 人脸学习2（通过图片/帧学习，不需要 open_camera）
  - 手势控制RGB灯带.py（摄像头探测与多线程模式）

模块调用示例：
  from 人脸学习 import FaceLearner
  learner = FaceLearner()
  learner.learn_from_image('images/face.jpg', '张三')
  learner.learn_from_frame(frame, '李四')
  faces = learner.get_learned_faces()
  learner.delete_face(0)
  learner.close()
"""

import json
import time
import signal
import threading

import pygame
import cv2
import numpy as np

from ESP32 import *
from camera_vision_system_v3 import create_vision_system_v3


# ===================== 配置 =====================
WIDTH, HEIGHT = 1920, 1080

# 字体路径（好搭AI派系统字体）
FONT_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'

# 摄像头配置
CAMERA_W, CAMERA_H = 640, 480
CAM_DISP_W, CAM_DISP_H = 800, 600

# 人脸记录持久化文件
FACE_DATA_FILE = 'face_records.json'

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
LEARN_COLOR = (60, 130, 255)
LEARN_HOVER = (80, 150, 255)
DEL_COLOR = (220, 80, 80)
DEL_HOVER = (255, 100, 100)
INPUT_BG = (240, 248, 255)
INPUT_BORDER = (100, 149, 237)
INPUT_ACTIVE_BORDER = (60, 130, 255)


# ===================== 硬件初始化 =====================
# 严格参照范例代码：ESP32 初始化 + 异常处理
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")


# ===================== 摄像头打开 =====================
# 参考手势控制RGB灯带.py 的摄像头探测逻辑：MJPG + 超时 + 雪花检测
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


# ===================== FaceLearner 人脸学习器 =====================
# 供其他程序调用的人脸学习接口
class FaceLearner:
    """人脸学习器，封装视觉系统的人脸学习功能

    使用 learn_new_face(frame=...) 传帧方式学习，不需要 open_camera()。

    其他程序可通过以下方式调用：
        from 人脸学习 import FaceLearner
        learner = FaceLearner()
        learner.learn_from_image('images/face.jpg', '张三')
        learner.learn_from_frame(frame, '李四')
        faces = learner.get_learned_faces()
        learner.delete_face(0)
        learner.close()
    """

    def __init__(self, width=1280, height=720):
        self._lock = threading.RLock()
        self._learned_faces = []  # [(name, face_info), ...]

        # 加载持久化记录
        self._load_records()

        # 创建视觉系统（不调用 open_camera，仅用于 learn_new_face）
        self._init_vision_system(width, height)

    def _init_vision_system(self, width=1280, height=720):
        """创建并初始化视觉系统（严格参照范例代码 5.9）

        注意：不调用 open_camera()，因为 learn_new_face(frame=...) 不需要摄像头。
        """
        self.vision_system = create_vision_system_v3(
            camera_id=-1, width=width, height=height,
            enable_basic=False, enable_advanced=False
        )
        self.vision_system.detection_config.enable_face_recognition = True
        self.vision_system._init_detectors()
        print('face_recognition 算法已启用')

    # ---- 持久化 ----
    def _load_records(self):
        """从 JSON 文件加载已学习的人脸记录"""
        try:
            with open(FACE_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with self._lock:
                self._learned_faces = [
                    (item['name'], item['face_info']) for item in data
                ]
            print('已加载 %d 条人脸记录' % len(self._learned_faces))
        except FileNotFoundError:
            print('无人脸记录文件，从零开始')
        except Exception as e:
            print('加载人脸记录失败:', e)

    def _save_records(self):
        """保存人脸记录到 JSON 文件"""
        try:
            with self._lock:
                data = [
                    {'name': name, 'face_info': info}
                    for name, info in self._learned_faces
                ]
            with open(FACE_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print('已保存 %d 条人脸记录' % len(data))
        except Exception as e:
            print('保存人脸记录失败:', e)

    # ---- 学习 ----
    def learn_from_frame(self, frame, name):
        """从 OpenCV 帧(BGR)学习人脸

        Args:
            frame: numpy 数组, BGR 格式（如 cv2.imread 或摄像头读取的帧）
            name:  人脸标签/姓名（应用层维护，不传给视觉系统）

        Returns:
            face_info: 学习结果信息（含 success/face_id/message 字段），失败返回 None
        """
        if frame is None:
            return None
        try:
            # 严格参照范例代码 5.9 的 learn_new_face 调用方式
            face_info = self.vision_system.learn_new_face(frame=frame)
            if not isinstance(face_info, dict):
                print('人脸学习返回异常：%s' % str(face_info))
                return face_info

            face_id = face_info.get('face_id')
            if face_info.get('success', False):
                # 新增成功：入库并持久化
                with self._lock:
                    self._learned_faces.append((name, face_info))
                self._save_records()
                print('人脸学习成功：%s -> %s' % (name, str(face_info)))
            else:
                # success=False 表示该人脸已注册过
                # 检查是否已在本地列表中（可能 JSON 丢失但视觉系统仍有数据）
                existing = self.find_name_by_id(face_id)
                if existing is None:
                    # 本地没有但视觉系统已注册 → 补录到本地列表
                    with self._lock:
                        self._learned_faces.append((name, face_info))
                    self._save_records()
                    print('补录已注册人脸：%s -> %s' % (name, str(face_info)))
                elif existing != name:
                    # 同一 face_id 但姓名不同 → 更新姓名
                    with self._lock:
                        for i, (n, info) in enumerate(self._learned_faces):
                            if isinstance(info, dict) and info.get('face_id') == face_id:
                                self._learned_faces[i] = (name, info)
                                break
                    self._save_records()
                    print('更新人脸姓名：%s -> %s (ID:%s)' % (existing, name, face_id))
                else:
                    print('人脸已注册且已在列表中：%s (ID:%s)' % (name, face_id))
            return face_info
        except Exception as e:
            print('人脸学习异常:', e)
            return None

    def learn_from_image(self, image_path, name):
        """从图片文件学习人脸

        Args:
            image_path: 图片路径（支持 jpg/png/bmp 等）
            name:       人脸标签/姓名

        Returns:
            face_info: 学习结果信息，失败返回 None
        """
        frame = cv2.imread(image_path)
        if frame is None:
            print('无法读取图片:', image_path)
            return None
        return self.learn_from_frame(frame, name)

    # ---- 删除 ----
    def delete_face(self, index):
        """删除指定索引的人脸记录

        注意：仅删除应用层记录（face_records.json），不调用视觉系统的删除接口。
        视觉系统内部的识别模型一旦被 delete_face 破坏，将无法识别任何人脸，
        因此这里只删除应用层映射，视觉系统内部数据予以保留。

        Args:
            index: 人脸记录索引（从 0 开始）

        Returns:
            bool: 删除成功返回 True，索引无效返回 False
        """
        with self._lock:
            if 0 <= index < len(self._learned_faces):
                name, face_info = self._learned_faces.pop(index)
                face_id = face_info.get('face_id') if isinstance(face_info, dict) else None
                self._save_records()
                print('已删除应用层人脸记录：%s (ID:%s)' % (name, face_id))
                print('注意：视觉系统内部数据保留，不影响识别模型')
                return True
            return False

    # ---- 查询 ----
    def get_learned_faces(self):
        """获取已学习的人脸列表

        Returns:
            list of (name, face_info): 每个元素为 (姓名, 学习返回信息)
        """
        with self._lock:
            return list(self._learned_faces)

    def get_face_count(self):
        """获取已学习人脸数量"""
        with self._lock:
            return len(self._learned_faces)

    def find_name_by_id(self, face_id):
        """根据 face_id 查找姓名

        Args:
            face_id: 视觉系统返回的人脸 ID

        Returns:
            str: 姓名字符串，未找到返回 None
        """
        with self._lock:
            for name, info in self._learned_faces:
                if isinstance(info, dict) and info.get('face_id') == face_id:
                    return name
        return None

    # ---- 清理 ----
    def close(self):
        """释放视觉系统资源"""
        try:
            self.vision_system.cleanup()
        except Exception:
            pass


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


class SmallButton:
    """小型按钮，用于列表项的删除等操作"""

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
        pygame.draw.rect(surf, c, self.rect, border_radius=6)
        label = font.render(self.text, True, self.text_color)
        lr = label.get_rect(center=self.rect.center)
        surf.blit(label, lr)

    def clicked(self, pos):
        return self.rect.collidepoint(pos)


class TextInput:
    """简单的文本输入框，支持中英文输入"""

    def __init__(self, rect, font, max_len=30):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.text = ''
        self.active = False
        self.max_len = max_len
        self.cursor_visible = True
        self.cursor_timer = 0

    def set_active(self, pos):
        """点击时激活/失活输入框"""
        self.active = self.rect.collidepoint(pos)

    def handle_key(self, event):
        """处理键盘输入"""
        if event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
        elif event.key == pygame.K_RETURN:
            self.active = False
        elif event.unicode and len(self.text) < self.max_len:
            char = event.unicode
            if char.isprintable():
                self.text += char

    def update(self):
        """更新光标闪烁"""
        self.cursor_timer += 1
        if self.cursor_timer >= 30:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0

    def draw(self, surf):
        bg_color = INPUT_BG if self.active else (250, 250, 250)
        pygame.draw.rect(surf, bg_color, self.rect, border_radius=8)
        border_color = INPUT_ACTIVE_BORDER if self.active else INPUT_BORDER
        pygame.draw.rect(surf, border_color, self.rect, 2, border_radius=8)

        text_surf = self.font.render(self.text, True, TEXT_COLOR)
        text_y = self.rect.centery - text_surf.get_height() // 2
        surf.blit(text_surf, (self.rect.x + 12, text_y))

        if self.active and self.cursor_visible:
            cursor_x = self.rect.x + 12 + text_surf.get_width() + 2
            pygame.draw.line(surf, TEXT_COLOR,
                             (cursor_x, self.rect.y + 8),
                             (cursor_x, self.rect.bottom - 8), 2)

        if not self.text:
            hint = self.font.render('请输入姓名...', True, SUBTLE_COLOR)
            surf.blit(hint, (self.rect.x + 12, text_y))


# ===================== 主程序 =====================
class FaceLearnApp:
    """人脸学习 Pygame 界面应用"""

    TITLE_H = 120
    FOOTER_H = 100

    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('人脸学习')
        self.clock = pygame.time.Clock()

        # 字体
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 56)
        self.font_sub = pygame.font.Font(FONT_PATH, 28)
        self.font_item = pygame.font.Font(FONT_PATH, 28)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 32)
        self.font_small = pygame.font.Font(FONT_PATH, 22)
        self.font_status = pygame.font.Font(FONT_PATH, 24)
        self.font_input = pygame.font.Font(FONT_PATH, 32)
        self.font_del = pygame.font.Font(FONT_PATH, 22)

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

        ix = self.info_rect.x + 30
        iw = self.info_rect.w - 60

        # 姓名输入框
        self.name_input = TextInput(
            (ix, self.info_rect.y + 55, iw, 60),
            self.font_input
        )

        # 学习按钮
        btn_y = self.name_input.rect.bottom + 25
        self.btn_learn = Button((ix, btn_y, iw, 65),
                                '学习人脸', LEARN_COLOR, LEARN_HOVER)

        # 退出按钮（右上角，标题栏内）
        self.btn_exit = Button((WIDTH - 260, 25, 200, 65),
                               '退出程序', EXIT_COLOR, EXIT_HOVER)

        # 初始化人脸学习器（视觉系统初始化在摄像头之前，避免资源冲突）
        print('正在初始化人脸识别系统...')
        self.learner = FaceLearner()

        # 打开摄像头（用于界面显示）
        print('外接摄像头打开中...')
        self.cap = open_camera()
        self.camera_ok = self.cap is not None and self.cap.isOpened()
        if self.camera_ok:
            print('外接摄像头已打开')
        else:
            print('摄像头打开失败，请检查 /dev/video41 和 /dev/video40')

        # 状态
        self.running = True
        self.raw_frame = None
        self.frame_lock = threading.Lock()
        self.cam_thread_running = True
        self.status_msg = '请输入姓名并对准摄像头，然后点击「学习人脸」'
        self.status_color = SUBTLE_COLOR

        # 列表项删除按钮 rect 列表（每帧更新，用于点击检测）
        self.face_delete_rects = []

        # 启动摄像头采集线程（后台线程，避免阻塞主循环）
        threading.Thread(target=self.camera_capture_loop, daemon=True).start()

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

    def set_status(self, msg, color=SUBTLE_COLOR):
        self.status_msg = msg
        self.status_color = color

    def handle_learn(self):
        """处理学习人脸按钮点击"""
        name = self.name_input.text.strip()
        if not name:
            self.set_status('请先输入姓名', ERROR_COLOR)
            return
        frame = self.get_current_frame()
        if frame is None:
            self.set_status('摄像头未就绪，请稍候', ERROR_COLOR)
            return
        self.set_status('正在学习...', ACCENT_COLOR)
        # 在主线程中执行学习（避免多线程并发访问视觉系统）
        result = self.learner.learn_from_frame(frame, name)
        if result is None:
            self.set_status('学习失败，请确保画面中有清晰人脸', ERROR_COLOR)
        elif isinstance(result, dict):
            face_id = result.get('face_id')
            count = self.learner.get_face_count()
            if result.get('success', False):
                self.set_status('学习成功：%s（ID:%s，累计 %d 条）' % (name, face_id, count), SUCCESS_COLOR)
            else:
                # success=False：已注册过，但已补录到本地列表
                self.set_status('已注册：%s（ID:%s，累计 %d 条）' % (name, face_id, count), ACCENT_COLOR)
            self.name_input.text = ''

    def handle_delete_face(self, index):
        """处理删除人脸记录"""
        faces = self.learner.get_learned_faces()
        if 0 <= index < len(faces):
            name = faces[index][0]
            self.learner.delete_face(index)
            self.set_status('已删除：%s（累计 %d 条）' % (name, self.learner.get_face_count()),
                            ACCENT_COLOR)

    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('人脸学习', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 20))
        sub = self.font_sub.render(
            'USB摄像头采集画面  ·  输入姓名后点击学习  ·  可删除记录',
            True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 80))

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

    def draw_info_panel(self):
        """绘制右侧信息面板：姓名输入 + 按钮 + 状态 + 已学习列表"""
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 30
        x_end = self.info_rect.right - 30
        y = self.info_rect.y + 15

        # ---- 姓名输入 ----
        head = self.font_sub.render('姓名标签', True, TITLE_COLOR)
        self.screen.blit(head, (x, y))

        self.name_input.update()
        self.name_input.draw(self.screen)

        # ---- 学习按钮 ----
        self.btn_learn.draw(self.screen, self.font_btn)

        # ---- 状态消息 ----
        y = self.btn_learn.rect.bottom + 20
        status_surf = self.font_status.render(self.status_msg, True, self.status_color)
        max_w = x_end - x
        if status_surf.get_width() > max_w:
            status_surf = self.font_small.render(self.status_msg, True, self.status_color)
        self.screen.blit(status_surf, (x, y))

        # 分隔线
        y += 35
        pygame.draw.line(self.screen, PANEL_BORDER,
                         (x, y), (x_end, y), 2)
        y += 20

        # ---- 已学习人脸列表 ----
        faces = self.learner.get_learned_faces()
        head2 = self.font_sub.render('已学习人脸（%d）' % len(faces), True, TITLE_COLOR)
        self.screen.blit(head2, (x, y))
        y += 45

        list_bottom = self.info_rect.bottom - 20
        self.face_delete_rects = []

        if not faces:
            hint = self.font_item.render('暂无学习记录', True, SUBTLE_COLOR)
            self.screen.blit(hint, (x, y))
        else:
            for i, (name, face_info) in enumerate(faces):
                if y + 55 > list_bottom:
                    more = self.font_small.render(
                        '...共 %d 条记录' % len(faces), True, SUBTLE_COLOR)
                    self.screen.blit(more, (x, y))
                    break

                face_id = face_info.get('face_id', '?') if isinstance(face_info, dict) else '?'

                # 序号
                num = self.font_small.render('%d.' % (i + 1), True, SUBTLE_COLOR)
                self.screen.blit(num, (x, y + 8))

                # 姓名
                name_surf = self.font_item.render(name, True, TEXT_COLOR)
                self.screen.blit(name_surf, (x + 35, y))

                # 人脸 ID
                id_text = 'ID:%s' % face_id
                id_surf = self.font_small.render(id_text, True, ACCENT_COLOR)
                self.screen.blit(id_surf, (x + 35, y + 32))

                # 删除按钮
                del_w, del_h = 65, 36
                del_rect = pygame.Rect(x_end - del_w, y + 8, del_w, del_h)
                del_btn = SmallButton(del_rect, '删除', DEL_COLOR, DEL_HOVER)
                del_btn.update(pygame.mouse.get_pos())
                del_btn.draw(self.screen, self.font_del)
                self.face_delete_rects.append((del_rect, i))

                y += 55

    def draw_footer(self, mouse_pos):
        """绘制底部栏"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        hint = self.font_small.render(
            'ESC 退出  ·  输入姓名后回车或点击「学习人脸」',
            True, SUBTLE_COLOR)
        self.screen.blit(hint, (60, HEIGHT - 45))

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
                    elif self.btn_learn.clicked(event.pos):
                        self.handle_learn()
                    else:
                        # 检测删除按钮点击
                        del_clicked = False
                        for del_rect, face_index in self.face_delete_rects:
                            if del_rect.collidepoint(event.pos):
                                self.handle_delete_face(face_index)
                                del_clicked = True
                                break
                        if not del_clicked:
                            self.name_input.set_active(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif self.name_input.active:
                        if event.key == pygame.K_RETURN:
                            self.handle_learn()
                        else:
                            self.name_input.handle_key(event)
                    elif event.key == pygame.K_RETURN:
                        self.name_input.active = True

            self.btn_learn.update(mouse_pos)
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
        time.sleep(0.2)
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        self.learner.close()
        pygame.quit()


# ===================== 入口 =====================
if __name__ == '__main__':
    app = FaceLearnApp()
    app.run()
