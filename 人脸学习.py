# -*- coding: utf-8 -*-
"""
人脸学习与识别程序（自包含版本，不依赖好搭 AI 派专有 SDK）
================================================================
参考：github.com/kerchak-wu/haoda_AIPad （好搭 AI 派范例 08.人脸学习1 / 09.人脸学习2 / 10.人脸识别）

技术方案：
  - 外接摄像头采集：OpenCV VideoCapture
  - 人脸检测：OpenCV Haar 级联 (haarcascade_frontalface_default.xml)
  - 人脸识别：OpenCV LBPH 人脸识别器（opencv-contrib-python 自带）
  - 界面：pygame，窗口 1920 x 1080，摄像头画面直接整合到主窗口
  - 数据持久化：
      face_data/face_db.json     —— 人脸库 {id: {name, created_at, samples}}
      face_data/face_model.yml   —— LBPH 训练好的识别模型
      face_data/images/<id>_<n>.jpg —— 学习时保存的人脸样本图

核心特性：
  1. 学习人脸：输入姓名 -> 采集多帧 -> 自动分配人脸 ID -> 保存样本与模型
  2. 人脸识别：实时检测并识别人脸，画面上直接框出人脸并显示姓名/置信度
  3. 查看人脸库：弹窗分页查看所有人脸的 ID、姓名、登记时间、样本数
  4. 删除人脸：列表中点击「删除」可移除人脸库中已有信息（含二次确认）
  5. 程序关闭后，其他程序可直接 import 本模块调用人脸数据实现识别

其他程序调用示例：
    from 人脸学习 import FaceEngine, get_face_name, load_face_database, list_known_faces

    # 方式一：直接调用已训练好的引擎做识别（推荐）
    engine = FaceEngine()
    engine.load()
    for box, face_id, name, conf in engine.recognize(frame):
        print(face_id, name, conf)

    # 方式二：根据人脸 ID 查姓名
    name = get_face_name(face_id)        # 未登记返回 None
    db = load_face_database()            # 获取整个人脸库
    all_faces = list_known_faces()       # [(id, name), ...]
"""

import os
import sys
import json
import time
import datetime
import threading

# GUI 依赖（仅使用 FaceEngine 做识别时可有可无；运行主程序必须安装）
try:
    import pygame
except Exception:  # pragma: no cover
    pygame = None

# ===========================================================================
# 配置
# ===========================================================================
WIDTH, HEIGHT = 1920, 1080

# 外接摄像头节点：固定为 /dev/video41（优先）或 /dev/video40，不再扫描其他节点
CAMERA_ID = -1  # 保留兼容，已不影响实际探测（实际探测逻辑见 open_camera）
CAMERA_W, CAMERA_H = 1280, 720

# 摄像头画面在主窗口中的显示尺寸
CAM_DISP_W, CAM_DISP_H = 1100, 520

BG_IMAGE = os.path.join("images", "1.jpg")

# 人脸数据目录与文件
FACE_DATA_DIR = "face_data"
FACE_DB_FILE = os.path.join(FACE_DATA_DIR, "face_db.json")
FACE_MODEL_FILE = os.path.join(FACE_DATA_DIR, "face_model.yml")
FACE_IMG_DIR = os.path.join(FACE_DATA_DIR, "images")

# 识别参数
RECOG_THRESHOLD = 75.0        # LBPH 距离阈值，越小越严格（0=完美匹配）
LEARN_SAMPLES = 15            # 学习时采集的人脸样本帧数
LEARN_DURATION = 1.8          # 学习采集时长（秒）
FACE_SIZE = 200               # 样本归一化尺寸（像素）

# 模式
MODE_LEARN = "learn"
MODE_RECOGNIZE = "recognize"

# 颜色
WHITE = (255, 255, 255)
TEXT_COLOR = (255, 255, 255)
DIM_TEXT = (200, 200, 200)
ACCENT = (86, 196, 255)
ACCENT_DARK = (40, 130, 190)
BTN_NORMAL = (255, 255, 255, 60)
BTN_HOVER = (86, 196, 255, 180)
PANEL_COLOR = (0, 0, 0, 130)
INPUT_BG = (0, 0, 0, 150)
SUCCESS = (130, 255, 170)
WARN = (255, 200, 120)
ERROR = (255, 120, 120)
EXIT_RED = (235, 87, 87)
FACE_BOX_COLOR = (86, 196, 255)
FACE_BOX_KNOWN = (130, 255, 170)
FACE_BOX_UNKNOWN = (255, 200, 120)


def _now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class _CameraProbeTimeout(Exception):
    """探测摄像头时 SIGALRM 超时（用于打断卡在 select() 的 V4L2 设备）。"""
    pass


# ===========================================================================
# 人脸引擎（核心：检测 / 学习 / 识别 / 持久化）
# ===========================================================================
class FaceEngine:
    """基于 OpenCV Haar 检测 + LBPH 识别的自包含人脸引擎。

    人脸数据保存到磁盘（JSON 数据库 + LBPH 模型 + 样本图），程序关闭后
    其他程序可重新加载用于识别。
    """

    def __init__(self, data_dir=FACE_DATA_DIR, threshold=RECOG_THRESHOLD):
        import cv2  # noqa: F401  确保导入
        self.cv2 = cv2
        self.data_dir = data_dir
        self.db_path = os.path.join(data_dir, "face_db.json")
        self.model_path = os.path.join(data_dir, "face_model.yml")
        self.img_dir = os.path.join(data_dir, "images")
        self.threshold = threshold
        self.db = {}                 # {"id": {"name":..., "created_at":..., "samples":[...]}}
        self.recognizer = None
        self._cascade = None
        self._lock = threading.RLock()
        self._init_cascade()
        self._init_recognizer()
        self.load()

    # ---------- 初始化 ----------
    def _init_cascade(self):
        cv2 = self.cv2
        # 优先使用随项目附带的级联文件（与脚本同级 cascades/ 目录），保证自包含可运行
        script_dir = os.path.dirname(os.path.abspath(__file__))
        bundled = [
            os.path.join(script_dir, "cascades", "haarcascade_frontalface_default.xml"),
            os.path.join(script_dir, "cascades", "haarcascade_frontalface_alt2.xml"),
            os.path.join("cascades", "haarcascade_frontalface_default.xml"),
            os.path.join("cascades", "haarcascade_frontalface_alt2.xml"),
        ]
        sdk = []
        try:
            sdk = [
                os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"),
                os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_alt2.xml"),
            ]
        except Exception:
            pass
        system_paths = [
            "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
            "/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        ]
        for p in bundled + sdk + system_paths:
            try:
                if not os.path.exists(p):
                    continue
                cascade = cv2.CascadeClassifier(p)
                if not cascade.empty():
                    self._cascade = cascade
                    return
            except Exception:
                continue
        self._cascade = None

    def _init_recognizer(self):
        cv2 = self.cv2
        if hasattr(cv2, "face") and hasattr(cv2.face, "LBPHFaceRecognizer_create"):
            try:
                self.recognizer = cv2.face.LBPHFaceRecognizer_create(
                    radius=1, neighbors=8, grid_x=8, grid_y=8)
            except Exception:
                self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        else:
            self.recognizer = None

    # ---------- 加载 / 保存 ----------
    def load(self):
        """加载人脸库 JSON 与已训练模型；若无模型则根据样本重训练。"""
        with self._lock:
            self.db = {}
            if os.path.exists(self.db_path):
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.db = data.get("faces", {})
                except Exception:
                    self.db = {}
            # 模型加载
            loaded = False
            if self.recognizer is not None and os.path.exists(self.model_path):
                try:
                    self.recognizer.read(self.model_path)
                    loaded = True
                except Exception:
                    loaded = False
            if not loaded:
                self._retrain_locked()

    def _save_db_locked(self):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump({"faces": self.db}, f, ensure_ascii=False, indent=2)

    # ---------- 检测 ----------
    def detect_faces(self, frame):
        """检测人脸，返回 [(x, y, w, h), ...]（坐标基于原始 frame）。"""
        cv2 = self.cv2
        if frame is None or self._cascade is None:
            return []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = self._cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
            return [tuple(b) for b in faces]
        except Exception:
            return []

    def _extract_face(self, frame, box):
        cv2 = self.cv2
        x, y, w, h = box
        x, y = max(0, x), max(0, y)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face = gray[y:y + h, x:x + w]
        if face.size == 0:
            return None
        return cv2.resize(face, (FACE_SIZE, FACE_SIZE))

    # ---------- 学习 ----------
    def learn_face(self, frames, name):
        """从多帧图像学习一张新人脸，分配新 ID 并重训练。

        Args:
            frames: 图像帧列表（BGR ndarray）
            name:   姓名
        Returns:
            新分配的人脸 ID（int），若无有效人脸返回 None
        """
        with self._lock:
            samples = []
            for frame in frames:
                if frame is None:
                    continue
                boxes = self.detect_faces(frame)
                if not boxes:
                    continue
                # 取最大人脸
                box = max(boxes, key=lambda b: b[2] * b[3])
                face = self._extract_face(frame, box)
                if face is not None:
                    samples.append(face)
            if not samples:
                return None

            new_id = self._next_id_locked()
            fid = str(new_id)
            os.makedirs(self.img_dir, exist_ok=True)
            paths = []
            for i, s in enumerate(samples):
                # 使用 PNG 无损格式保存样本，避免 JPEG 压缩丢失人脸细节影响识别精度
                p = os.path.join(self.img_dir, "{}_{}.png".format(new_id, i))
                if self.cv2.imwrite(p, s):
                    paths.append(p)
            self.db[fid] = {
                "name": name,
                "created_at": _now_str(),
                "samples": paths,
            }
            self._save_db_locked()
            self._retrain_locked()
            return new_id

    def _next_id_locked(self):
        ids = [int(k) for k in self.db.keys() if str(k).isdigit()]
        return (max(ids) + 1) if ids else 1

    # ---------- 重训练 ----------
    def _retrain_locked(self):
        cv2 = self.cv2
        if self.recognizer is None:
            return
        import numpy as np
        images, labels = [], []
        for fid, info in self.db.items():
            for p in info.get("samples", []):
                if os.path.exists(p):
                    img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        images.append(img)
                        labels.append(int(fid))
        if images:
            self.recognizer.train(images, np.array(labels))
            try:
                self.recognizer.write(self.model_path)
            except Exception as e:
                print("模型保存失败: {}".format(e))
        else:
            if os.path.exists(self.model_path):
                try:
                    os.remove(self.model_path)
                except Exception:
                    pass

    # ---------- 识别 ----------
    def recognize(self, frame):
        """识别 frame 中所有人脸。

        Returns:
            [(box, face_id, name, confidence), ...]
            - 已识别：face_id=int, name=str, confidence=0~1 浮点
            - 未识别：face_id=None, name=None, confidence=None
        """
        with self._lock:
            results = []
            if self.recognizer is None or frame is None:
                return results
            boxes = self.detect_faces(frame)
            for box in boxes:
                face = self._extract_face(frame, box)
                if face is None:
                    continue
                label, dist = self.recognizer.predict(face)
                if label >= 0 and dist < self.threshold and str(label) in self.db:
                    name = self.db[str(label)]["name"]
                    conf = max(0.0, min(1.0, 1.0 - dist / self.threshold))
                    results.append((box, label, name, round(conf, 3)))
                else:
                    results.append((box, None, None, None))
            return results

    # ---------- 删除 ----------
    def delete_face(self, face_id):
        """删除指定 ID 的人脸（含样本图与模型重训练）。返回是否删除成功。"""
        with self._lock:
            fid = str(face_id)
            if fid not in self.db:
                return False
            for p in self.db[fid].get("samples", []):
                try:
                    os.remove(p)
                except Exception:
                    pass
            del self.db[fid]
            self._save_db_locked()
            self._retrain_locked()
            return True

    # ---------- 查询 ----------
    def get_name(self, face_id):
        with self._lock:
            info = self.db.get(str(face_id))
            return info["name"] if info else None

    def list_faces(self):
        """返回 [(id(int), info(dict)), ...]，按 ID 升序。"""
        with self._lock:
            items = [(int(k), v) for k, v in self.db.items() if str(k).isdigit()]
        items.sort(key=lambda x: x[0])
        return items

    def count(self):
        with self._lock:
            return len(self.db)


# ===========================================================================
# 对外 API（供其他程序直接 import 调用，无需启动界面）
# ===========================================================================
def load_face_database(path=FACE_DB_FILE):
    """加载人脸数据库，返回 {face_id(str): {"name":..., "created_at":..., "samples":[...]}}。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("faces", {})
    except Exception:
        return {}


def get_face_name(face_id, path=FACE_DB_FILE):
    """根据人脸 ID 获取姓名，未登记返回 None。"""
    faces = load_face_database(path)
    info = faces.get(str(face_id))
    return info["name"] if info else None


def list_known_faces(path=FACE_DB_FILE):
    """返回所有已知人脸列表 [(face_id, name), ...]。"""
    faces = load_face_database(path)
    items = [(int(k), v["name"]) for k, v in faces.items() if str(k).isdigit()]
    items.sort(key=lambda x: x[0])
    return items


# ===========================================================================
# GUI 通用工具
# ===========================================================================
def find_chinese_font():
    """寻找系统中可用的中文字体。"""
    import pygame
    candidates = [
        "simhei", "microsoftyahei", "msyh", "pingfang",
        "notosanscjksc", "notosanscjk", "wenquanyimicrohei",
        "wqymicrohei", "stheiti", "arialunicodems",
    ]
    available = pygame.font.get_fonts()
    for name in candidates:
        if name in available:
            return name
    paths = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def draw_text(surface, text, font, color, pos, anchor="topleft"):
    surf = font.render(str(text), True, color)
    rect = surf.get_rect(**{anchor: pos})
    surface.blit(surf, rect)
    return rect


def draw_panel(surface, x, y, w, h, fill=PANEL_COLOR, border=ACCENT, radius=14, border_w=2):
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill(fill)
    surface.blit(panel, (x, y))
    pygame.draw.rect(surface, border, (x, y, w, h), border_w, border_radius=radius)


class Button:
    """通用按钮控件。"""

    def __init__(self, rect, text, font, color=BTN_NORMAL, hover_color=BTN_HOVER,
                 text_color=TEXT_COLOR):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.hovered = False
        self.enabled = True

    def update(self, mouse_pos):
        self.hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        if not self.enabled:
            color = (80, 80, 80, 120)
        elif self.hovered:
            color = self.hover_color
        else:
            color = self.color
        btn_surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, color, btn_surf.get_rect(), border_radius=12)
        pygame.draw.rect(btn_surf, ACCENT, btn_surf.get_rect(), 2, border_radius=12)
        surface.blit(btn_surf, self.rect.topleft)
        text_surf = self.font.render(self.text, True,
                                     self.text_color if self.enabled else (150, 150, 150))
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))


# ===========================================================================
# 主程序
# ===========================================================================
def main():
    global pygame, cv2, np
    import pygame
    import cv2
    import numpy as np
    import signal

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("人脸学习与识别系统")
    clock = pygame.time.Clock()

    font_name = find_chinese_font()
    font_title = pygame.font.SysFont(font_name, 48, bold=True)
    font_subtitle = pygame.font.SysFont(font_name, 32, bold=True)
    font_label = pygame.font.SysFont(font_name, 28)
    font_input = pygame.font.SysFont(font_name, 30)
    font_btn = pygame.font.SysFont(font_name, 26, bold=True)
    font_msg = pygame.font.SysFont(font_name, 26)
    font_small = pygame.font.SysFont(font_name, 22)
    font_exit = pygame.font.SysFont(font_name, 24, bold=True)
    font_big_result = pygame.font.SysFont(font_name, 42, bold=True)
    font_box = pygame.font.SysFont(font_name, 24, bold=True)

    # 背景图片
    background = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print("背景加载失败: {}".format(e))

    # ----- 初始化人脸引擎 -----
    print("人脸引擎初始化中...")
    engine = FaceEngine()
    print("人脸库已加载：共 {} 人".format(engine.count()))

    # ----- 打开摄像头 -----
    def _is_valid_frame(frame):
        """判断帧是否为有效画面（非空、非全黑、非雪花噪声）。

        雪花/随机噪声的特点：用 INTER_AREA 下采样后，相邻噪声相互抵消，
        标准差急剧下降；真实画面有空间结构，下采样后保持高标准差。
        实测：真实画面 r≈0.95，雪花 r≈0.03，阈值 0.2 可清晰区分。
        """
        if frame is None or frame.size == 0:
            return False
        try:
            std_orig = float(frame.std())
            if std_orig < 5:                     # 全黑/全白/空缓冲
                return False
            small = cv2.resize(frame, (32, 32), interpolation=cv2.INTER_AREA)
            std_small = float(small.std())
            if std_orig > 20 and std_small / std_orig < 0.2:   # 雪花噪声
                return False
            return True
        except Exception:
            return False

    def _try_open(cid, timeout=4):
        """尝试以 MJPG 格式打开指定编号的摄像头并验证可读到有效帧。

        加 4 秒超时：部分 V4L2 节点（元数据节点/损坏设备）的 cap.read() 会
        卡在 select() 上，不加超时会阻塞整个启动流程。用 SIGALRM 强制打断。

        MJPG 是绝大多数 USB 摄像头支持的格式；不设置时驱动默认可能用
        不可靠的原始格式，导致 cap.read() 返回成功但帧数据是垃圾（雪花）。
        """
        cap = None
        # signal.alarm 仅在主线程 + POSIX 可用；Windows 退化为无超时
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
            # 直接用设备节点路径打开，避免把整数 cid 当成 V4L2 索引导致越界
            # （系统设备列表通常只有 32 项，cid=41 会被判为索引越界）
            device_path = "/dev/video{}".format(cid)
            cap = cv2.VideoCapture(device_path)
            if cap is None or not cap.isOpened():
                return None
            # 设置 MJPG 编码，解决 USB 摄像头默认格式导致的雪花/绿屏问题
            try:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            except Exception:
                pass
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_H)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # 预热 + 试读校验：前几帧可能是空的，多试几次
            for _ in range(20):
                ok, frame = cap.read()
                if ok and _is_valid_frame(frame):
                    return cap   # 成功，返回给调用方持有
            # 读不到有效帧则视为不可用
            try:
                cap.release()
            except Exception:
                pass
            return None
        except _CameraProbeTimeout:
            print("  /dev/video{} 探测超时（可能是元数据节点或损坏设备），跳过".format(cid))
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
        # 摄像头固定为 /dev/video41（优先）或 /dev/video40，不再扫描其他节点。
        for cid in (41, 40):
            print("  探测 /dev/video{} ...".format(cid))
            cap = _try_open(cid)
            if cap is not None:
                print("摄像头使用编号：{} (/dev/video{})".format(cid, cid))
                return cap
        return None

    print("外接摄像头打开中...")
    cap = open_camera()
    camera_ok = cap is not None and cap.isOpened()
    if camera_ok:
        print("✅ 外接摄像头已打开")
    else:
        print("❌ 摄像头打开失败，请检查 /dev/video41 和 /dev/video40 是否存在且未被占用")

    # =============================================================
    # 布局参数
    # =============================================================
    TITLE_Y = 12
    EXIT_BTN_Y = 12
    MODE_BTN_Y = 75

    panel_x, panel_y = 60, 145
    panel_w, panel_h = 1180, 850

    cam_x = panel_x + 40                    # 100
    cam_y = panel_y + 105                   # 250

    below_cam_y = cam_y + CAM_DISP_H + 20   # 790
    below_cam_h = panel_y + panel_h - below_cam_y - 15

    rtop_x, rtop_y = 1280, 145
    rtop_w, rtop_h = 580, 240

    view_btn_y = 400

    side_x, side_y = 1280, 470
    side_w, side_h = 580, 525

    TOAST_Y = 1005
    HINT_Y = 1055

    DETAIL_PAGE_SIZE = 8

    # =============================================================
    # 状态变量
    # =============================================================
    mode = MODE_LEARN
    name_input = ""
    input_active = False
    learning = False
    learn_lock = threading.Lock()
    learn_status = ""
    learn_status_color = DIM_TEXT

    recog_history = []
    last_recog_id = None
    recog_cooldown = 0
    RECOG_COOLDOWN_FRAMES = 30

    show_face_detail = False
    detail_page = 0

    delete_confirm_id = None
    delete_status = ""
    delete_status_color = DIM_TEXT
    delete_status_timer = 0

    face_list_scroll = 0
    force_refresh_list = False

    # =============================================================
    # 摄像头后台采集线程
    # =============================================================
    latest_frame = None
    frame_lock = threading.Lock()
    cam_thread_running = True

    # 识别后台线程结果
    latest_recog = []          # [(box, face_id, name, conf), ...]
    recog_lock = threading.Lock()
    recog_thread_running = True

    def cvframe_to_surface(frame):
        if frame is None:
            return None
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_transposed = np.transpose(frame_rgb, (1, 0, 2))
            surface = pygame.surfarray.make_surface(frame_transposed)
            return pygame.transform.smoothscale(surface, (CAM_DISP_W, CAM_DISP_H))
        except Exception:
            return None

    def camera_capture_loop():
        nonlocal latest_frame
        fail_count = 0
        while cam_thread_running:
            if not camera_ok or cap is None:
                time.sleep(0.2)
                continue
            try:
                ok, frame = cap.read()
                # 校验有效性（过滤空帧/全黑/雪花噪声）
                if ok and _is_valid_frame(frame):
                    with frame_lock:
                        latest_frame = frame
                    fail_count = 0
                else:
                    fail_count += 1
                    if fail_count > 5:
                        time.sleep(0.1)
            except Exception as e:
                fail_count += 1
                if fail_count == 1:
                    print("摄像头采集异常: {}".format(e))
                time.sleep(0.05)
            time.sleep(0.03)

    def recognition_loop():
        """后台识别人脸，约 10 fps，结果供主循环绘制。"""
        nonlocal latest_recog
        while recog_thread_running:
            if mode != MODE_RECOGNIZE or not camera_ok:
                time.sleep(0.1)
                continue
            with frame_lock:
                frame = latest_frame
            if frame is None:
                time.sleep(0.05)
                continue
            try:
                results = engine.recognize(frame)
                with recog_lock:
                    latest_recog = results
            except Exception as e:
                print("识别异常: {}".format(e))
            time.sleep(0.1)

    cam_thread = threading.Thread(target=camera_capture_loop, daemon=True)
    cam_thread.start()
    recog_thread = threading.Thread(target=recognition_loop, daemon=True)
    recog_thread.start()

    # =============================================================
    # 人脸学习
    # =============================================================
    def start_learn():
        nonlocal learning, learn_status, learn_status_color
        name = name_input.strip()
        if not name:
            learn_status = "请先输入姓名"
            learn_status_color = WARN
            return
        if not camera_ok:
            learn_status = "摄像头未打开，无法学习"
            learn_status_color = ERROR
            return
        with learn_lock:
            if learning:
                return
            learning = True
        learn_status = "正在学习人脸，请正对摄像头保持不动..."
        learn_status_color = WARN

        def worker():
            nonlocal learning, learn_status, learn_status_color
            try:
                # 采集多帧
                frames = []
                t0 = time.time()
                while time.time() - t0 < LEARN_DURATION and len(frames) < LEARN_SAMPLES * 2:
                    with frame_lock:
                        f = latest_frame
                    if f is not None:
                        frames.append(f.copy())
                    time.sleep(LEARN_DURATION / LEARN_SAMPLES)
                if not frames:
                    learn_status = "采集失败，未获取到摄像头画面"
                    learn_status_color = ERROR
                    return
                face_id = engine.learn_face(frames, name)
                if face_id is None:
                    learn_status = "学习失败，未在画面中检测到人脸，请正对摄像头重试"
                    learn_status_color = ERROR
                else:
                    learn_status = "✅ 学习成功！ID={}  姓名={}".format(face_id, name)
                    learn_status_color = SUCCESS
                    print("人脸学习成功：ID={} 姓名={}".format(face_id, name))
            except Exception as e:
                learn_status = "学习异常：{}".format(e)
                learn_status_color = ERROR
            finally:
                with learn_lock:
                    learning = False

        threading.Thread(target=worker, daemon=True).start()

    # =============================================================
    # 删除人脸
    # =============================================================
    def delete_face(face_id):
        nonlocal delete_status, delete_status_color, delete_status_timer, force_refresh_list
        name = engine.get_name(face_id)
        ok = engine.delete_face(face_id)
        if ok:
            delete_status = "✅ 已删除：ID={}  姓名={}".format(face_id, name)
            delete_status_color = SUCCESS
            print("人脸已删除：ID={} 姓名={}".format(face_id, name))
        else:
            delete_status = "未找到 ID={} 的人脸".format(face_id)
            delete_status_color = ERROR
        delete_status_timer = 180
        force_refresh_list = True

    # =============================================================
    # 按钮定义
    # =============================================================
    btn_learn_mode = Button((640, MODE_BTN_Y, 260, 52), "学习人脸", font_btn)
    btn_recog_mode = Button((1000, MODE_BTN_Y, 260, 52), "人脸识别", font_btn)
    btn_start_learn = Button((rtop_x + 20, rtop_y + 155, rtop_w - 40, 50), "开始学习人脸", font_btn,
                             color=(86, 196, 255, 120), hover_color=(86, 196, 255, 220))
    btn_exit = Button((1740, EXIT_BTN_Y, 140, 48), "退出程序", font_exit,
                      color=(235, 87, 87, 120), hover_color=(235, 87, 87, 220))
    btn_view_faces = Button((side_x, view_btn_y, side_w, 50), "查看人脸库详细信息", font_btn,
                            color=(130, 255, 170, 120), hover_color=(130, 255, 170, 220))

    btn_close_detail = Button((WIDTH // 2 + 500, 160, 100, 48), "关闭", font_btn,
                              color=(235, 87, 87, 120), hover_color=(235, 87, 87, 220))
    btn_detail_prev = Button((WIDTH // 2 - 150, HEIGHT - 100, 130, 48), "上一页", font_btn)
    btn_detail_next = Button((WIDTH // 2 + 20, HEIGHT - 100, 130, 48), "下一页", font_btn)

    btn_confirm_delete = Button((WIDTH // 2 - 210, HEIGHT // 2 + 40, 180, 55), "确认删除", font_btn,
                                color=(235, 87, 87, 150), hover_color=(235, 87, 87, 220))
    btn_cancel_delete = Button((WIDTH // 2 + 30, HEIGHT // 2 + 40, 180, 55), "取消", font_btn)

    input_rect = pygame.Rect(rtop_x + 20, rtop_y + 80, rtop_w - 40, 50)
    delete_btn_rects = []

    # =============================================================
    # 主循环
    # =============================================================
    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if delete_confirm_id is not None:
                        delete_confirm_id = None
                    elif show_face_detail:
                        show_face_detail = False
                    else:
                        running = False
                elif (input_active and mode == MODE_LEARN
                      and not show_face_detail and delete_confirm_id is None):
                    if event.key == pygame.K_BACKSPACE:
                        name_input = name_input[:-1]
                    elif event.key == pygame.K_RETURN:
                        input_active = False
                        start_learn()
                    elif event.key == pygame.K_TAB:
                        input_active = False
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable() and len(name_input) < 20:
                            name_input += ch
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if delete_confirm_id is not None:
                        if btn_confirm_delete.rect.collidepoint(event.pos):
                            delete_face(delete_confirm_id)
                            delete_confirm_id = None
                        elif btn_cancel_delete.rect.collidepoint(event.pos):
                            delete_confirm_id = None
                        continue

                    if show_face_detail:
                        if btn_close_detail.rect.collidepoint(event.pos):
                            show_face_detail = False
                        elif btn_detail_prev.rect.collidepoint(event.pos) and btn_detail_prev.enabled:
                            detail_page = max(0, detail_page - 1)
                        elif btn_detail_next.rect.collidepoint(event.pos) and btn_detail_next.enabled:
                            all_items = engine.list_faces()
                            max_pages = max(0, (len(all_items) - 1) // DETAIL_PAGE_SIZE)
                            detail_page = min(max_pages, detail_page + 1)
                        continue

                    if btn_exit.rect.collidepoint(event.pos):
                        running = False
                        continue
                    if btn_view_faces.rect.collidepoint(event.pos):
                        show_face_detail = True
                        detail_page = 0
                        continue
                    if btn_learn_mode.rect.collidepoint(event.pos):
                        mode = MODE_LEARN
                        continue
                    if btn_recog_mode.rect.collidepoint(event.pos):
                        mode = MODE_RECOGNIZE
                        continue

                    clicked_delete = False
                    for fid, rect in delete_btn_rects:
                        if rect.collidepoint(event.pos):
                            delete_confirm_id = fid
                            clicked_delete = True
                            break
                    if clicked_delete:
                        continue

                    if mode == MODE_LEARN:
                        input_active = input_rect.collidepoint(event.pos)
                        if btn_start_learn.rect.collidepoint(event.pos) and not learning:
                            start_learn()
                elif event.button == 4:
                    if side_x <= mouse_pos[0] <= side_x + side_w and side_y <= mouse_pos[1] <= side_y + side_h:
                        face_list_scroll = max(0, face_list_scroll - 1)
                elif event.button == 5:
                    if side_x <= mouse_pos[0] <= side_x + side_w and side_y <= mouse_pos[1] <= side_y + side_h:
                        items_count = engine.count()
                        list_top = side_y + 90
                        list_h = side_h - 90 - 25
                        entry_h = 50
                        max_visible = list_h // entry_h
                        max_scroll = max(0, items_count - max_visible)
                        face_list_scroll = min(max_scroll, face_list_scroll + 1)

        # ----- 识别历史记录 -----
        if mode == MODE_RECOGNIZE and camera_ok:
            with recog_lock:
                recog_results = list(latest_recog)
            if recog_cooldown > 0:
                recog_cooldown -= 1
            # 取最大人脸作为主识别结果
            known = [r for r in recog_results if r[1] is not None]
            if known:
                box, face_id, name, conf = max(known, key=lambda r: r[0][2] * r[0][3])
                if recog_cooldown == 0 or face_id != last_recog_id:
                    time_str = datetime.datetime.now().strftime("%H:%M:%S")
                    recog_history.append((time_str, face_id, name, conf))
                    if len(recog_history) > 20:
                        recog_history.pop(0)
                    last_recog_id = face_id
                    recog_cooldown = RECOG_COOLDOWN_FRAMES
            elif recog_results and recog_cooldown == 0:
                box, face_id, name, conf = recog_results[0]
                time_str = datetime.datetime.now().strftime("%H:%M:%S")
                recog_history.append((time_str, None, None, None))
                if len(recog_history) > 20:
                    recog_history.pop(0)
                last_recog_id = None
                recog_cooldown = RECOG_COOLDOWN_FRAMES

        if delete_status_timer > 0:
            delete_status_timer -= 1

        if force_refresh_list:
            force_refresh_list = False
            face_list_scroll = 0

        # =============================================================
        # 绘制
        # =============================================================
        if background:
            screen.blit(background, (0, 0))
        else:
            screen.fill((20, 24, 34))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 90))
        screen.blit(overlay, (0, 0))

        # ----- 标题 -----
        draw_text(screen, "人脸学习与识别系统", font_title, TEXT_COLOR,
                  (WIDTH // 2, TITLE_Y), anchor="midtop")

        # ----- 退出按钮 -----
        btn_exit.update(mouse_pos)
        btn_exit.draw(screen)

        # ----- 模式按钮 -----
        if mode == MODE_LEARN:
            btn_learn_mode.color = (86, 196, 255, 180)
            btn_recog_mode.color = BTN_NORMAL
        else:
            btn_learn_mode.color = BTN_NORMAL
            btn_recog_mode.color = (86, 196, 255, 180)
        btn_learn_mode.update(mouse_pos)
        btn_learn_mode.draw(screen)
        btn_recog_mode.update(mouse_pos)
        btn_recog_mode.draw(screen)

        # =============================================================
        # 左侧面板：摄像头 + 下方提示/历史
        # =============================================================
        draw_panel(screen, panel_x, panel_y, panel_w, panel_h)

        if mode == MODE_LEARN:
            draw_text(screen, "学习人脸 — 摄像头画面", font_subtitle, ACCENT,
                      (panel_x + 30, panel_y + 20), anchor="topleft")
            draw_text(screen, "输入姓名后点击「开始学习人脸」，正对摄像头完成学习",
                      font_small, DIM_TEXT, (panel_x + 30, panel_y + 60), anchor="topleft")
        else:
            draw_text(screen, "人脸识别 — 摄像头画面", font_subtitle, ACCENT,
                      (panel_x + 30, panel_y + 20), anchor="topleft")
            draw_text(screen, "正对摄像头，系统将实时识别已登记的人脸",
                      font_small, DIM_TEXT, (panel_x + 30, panel_y + 60), anchor="topleft")

        # 摄像头状态指示
        status_text = "● 已连接" if camera_ok else "○ 未连接"
        status_color = SUCCESS if camera_ok else ERROR
        draw_text(screen, status_text, font_small, status_color,
                  (panel_x + panel_w - 30, panel_y + 25), anchor="topright")

        with frame_lock:
            frame = latest_frame

        cam_surface = cvframe_to_surface(frame)
        if cam_surface:
            screen.blit(cam_surface, (cam_x, cam_y))
        else:
            placeholder = pygame.Surface((CAM_DISP_W, CAM_DISP_H))
            placeholder.fill((30, 30, 40))
            screen.blit(placeholder, (cam_x, cam_y))
            if not camera_ok:
                ph_lines = ["摄像头未打开",
                            "请检查 /dev/video41 与 /dev/video40",
                            "确认设备存在且未被其他程序占用"]
                draw_text(screen, ph_lines[0], font_msg, ERROR,
                          (cam_x + CAM_DISP_W // 2, cam_y + CAM_DISP_H // 2 - 36),
                          anchor="center")
                for i, line in enumerate(ph_lines[1:], start=1):
                    draw_text(screen, line, font_small, DIM_TEXT,
                              (cam_x + CAM_DISP_W // 2,
                               cam_y + CAM_DISP_H // 2 - 36 + i * 32),
                              anchor="center")
            else:
                draw_text(screen, "画面加载中...", font_msg, DIM_TEXT,
                          (cam_x + CAM_DISP_W // 2, cam_y + CAM_DISP_H // 2),
                          anchor="center")

        pygame.draw.rect(screen, ACCENT, (cam_x, cam_y, CAM_DISP_W, CAM_DISP_H), 2, border_radius=8)

        # 识别模式：在摄像头画面上绘制人脸框与姓名
        if mode == MODE_RECOGNIZE and camera_ok and cam_surface is not None and frame is not None:
            with recog_lock:
                recog_results = list(latest_recog)
            sx = CAM_DISP_W / float(frame.shape[1])
            sy = CAM_DISP_H / float(frame.shape[0])
            for (bx, by, bw, bh), face_id, name, conf in recog_results:
                rx = cam_x + int(bx * sx)
                ry = cam_y + int(by * sy)
                rw = int(bw * sx)
                rh = int(bh * sy)
                color = FACE_BOX_KNOWN if name else FACE_BOX_UNKNOWN
                pygame.draw.rect(screen, color, (rx, ry, rw, rh), 3, border_radius=6)
                label = "{} ({:.0%})".format(name, conf) if name else "未知"
                lbl_surf = font_box.render(label, True, (0, 0, 0))
                lbl_bg_w = lbl_surf.get_width() + 16
                lbl_bg_h = lbl_surf.get_height() + 6
                lbl_bg = pygame.Surface((lbl_bg_w, lbl_bg_h), pygame.SRCALPHA)
                lbl_bg.fill((color[0], color[1], color[2], 220))
                screen.blit(lbl_bg, (rx, max(cam_y, ry - lbl_bg_h)))
                screen.blit(lbl_surf, (rx + 8, max(cam_y, ry - lbl_bg_h) + 3))
            if recog_results:
                draw_text(screen, "● 检测到 {} 张人脸".format(len(recog_results)), font_small, SUCCESS,
                          (cam_x + 12, cam_y + 12), anchor="topleft")

        # ----- 摄像头下方：操作提示 / 识别历史 -----
        if mode == MODE_LEARN:
            draw_text(screen, "操作提示", font_label, ACCENT,
                      (panel_x + 30, below_cam_y), anchor="topleft")
            tips = [
                "1. 在右侧输入框输入姓名",
                "2. 点击「开始学习人脸」或按回车键",
                "3. 学习时请正对摄像头保持不动",
                "4. 学习成功后自动保存样本与模型到 face_data/",
                "5. 其他程序可 from 人脸学习 import FaceEngine 调用",
            ]
            ty = below_cam_y + 35
            for line in tips:
                draw_text(screen, line, font_small, DIM_TEXT, (panel_x + 50, ty))
                ty += 28
        else:
            draw_text(screen, "识别历史", font_label, ACCENT,
                      (panel_x + 30, below_cam_y), anchor="topleft")
            line_h = 28
            max_lines = below_cam_h // line_h - 1
            start_idx = max(0, len(recog_history) - max_lines)
            i = 0
            for idx in range(start_idx, len(recog_history)):
                t_str, fid, name, conf = recog_history[idx]
                if name:
                    label = name
                    color = SUCCESS
                    line = "[{}]  ID={}  {}  置信度={:.0%}".format(t_str, fid, label, conf)
                else:
                    color = WARN
                    line = "[{}]  未知人脸".format(t_str)
                draw_text(screen, line, font_small, color,
                          (panel_x + 50, below_cam_y + 35 + i * line_h))
                i += 1
            if not recog_history:
                draw_text(screen, "（暂无识别记录）", font_small, DIM_TEXT,
                          (panel_x + 50, below_cam_y + 35), anchor="topleft")

        # =============================================================
        # 右侧上方面板
        # =============================================================
        draw_panel(screen, rtop_x, rtop_y, rtop_w, rtop_h)

        if mode == MODE_LEARN:
            draw_text(screen, "学习控件", font_subtitle, ACCENT,
                      (rtop_x + 20, rtop_y + 15), anchor="topleft")
            draw_text(screen, "姓名：", font_label, TEXT_COLOR,
                      (rtop_x + 20, rtop_y + 50), anchor="topleft")

            input_surf = pygame.Surface(input_rect.size, pygame.SRCALPHA)
            input_surf.fill(INPUT_BG)
            screen.blit(input_surf, input_rect.topleft)
            border_color = ACCENT if input_active else (255, 255, 255, 80)
            pygame.draw.rect(screen, border_color, input_rect, 2, border_radius=10)
            show_text = name_input if name_input else ("请输入姓名..." if not input_active else "")
            input_color = TEXT_COLOR if name_input else DIM_TEXT
            draw_text(screen, show_text, font_input, input_color,
                      (input_rect.x + 12, input_rect.centery), anchor="midleft")
            if input_active and (pygame.time.get_ticks() // 500) % 2 == 0:
                tw = font_input.size(name_input)[0]
                cx = input_rect.x + 12 + tw + 2
                pygame.draw.line(screen, WHITE, (cx, input_rect.y + 10),
                                 (cx, input_rect.bottom - 10), 2)

            btn_start_learn.enabled = not learning
            btn_start_learn.text = "学习中..." if learning else "开始学习人脸"
            btn_start_learn.update(mouse_pos)
            btn_start_learn.draw(screen)

            if learn_status:
                draw_text(screen, learn_status, font_msg, learn_status_color,
                          (rtop_x + 20, rtop_y + 212), anchor="topleft")
        else:
            draw_text(screen, "识别结果", font_subtitle, ACCENT,
                      (rtop_x + 20, rtop_y + 15), anchor="topleft")
            rtop_cx = rtop_x + rtop_w // 2
            if not camera_ok:
                draw_text(screen, "摄像头未打开", font_big_result, ERROR,
                          (rtop_cx, rtop_y + 75), anchor="center")
            elif not recog_history:
                draw_text(screen, "等待识别人脸...", font_big_result, DIM_TEXT,
                          (rtop_cx, rtop_y + 75), anchor="center")
            else:
                t_str, fid, name, conf = recog_history[-1]
                if name:
                    result_line = "识别到：{}".format(name)
                    result_color = SUCCESS
                else:
                    result_line = "未知人脸"
                    result_color = WARN
                draw_text(screen, result_line, font_big_result, result_color,
                          (rtop_cx, rtop_y + 70), anchor="center")
                if name:
                    detail = "人脸ID：{}    置信度：{:.0%}".format(fid, conf)
                else:
                    detail = "未在人脸库中匹配到"
                draw_text(screen, detail, font_msg, DIM_TEXT,
                          (rtop_cx, rtop_y + 130), anchor="center")
                draw_text(screen, "时间：{}".format(t_str), font_small, DIM_TEXT,
                          (rtop_cx, rtop_y + 165), anchor="center")

        # =============================================================
        # 查看人脸库按钮
        # =============================================================
        btn_view_faces.update(mouse_pos)
        btn_view_faces.draw(screen)

        # =============================================================
        # 右侧人脸库面板
        # =============================================================
        delete_btn_rects = []
        draw_panel(screen, side_x, side_y, side_w, side_h)

        draw_text(screen, "已保存人脸库", font_subtitle, ACCENT,
                  (side_x + 20, side_y + 12), anchor="topleft")
        draw_text(screen, "共 {} 人  |  点击「删除」移除  |  滚轮滚动".format(engine.count()),
                  font_small, DIM_TEXT, (side_x + 20, side_y + 52), anchor="topleft")

        list_top = side_y + 85
        list_h = side_h - 85 - 25
        entry_h = 50
        max_visible = list_h // entry_h
        items = engine.list_faces()

        max_scroll = max(0, len(items) - max_visible)
        if face_list_scroll > max_scroll:
            face_list_scroll = max_scroll

        start_idx = face_list_scroll
        end_idx = min(start_idx + max_visible, len(items))

        for i in range(start_idx, end_idx):
            fid, info = items[i]
            entry_y = list_top + (i - start_idx) * entry_h
            if (i - start_idx) % 2 == 0:
                entry_bg = pygame.Surface((side_w - 30, entry_h - 4), pygame.SRCALPHA)
                entry_bg.fill((255, 255, 255, 15))
                screen.blit(entry_bg, (side_x + 15, entry_y))

            line = "ID {}  :  {}".format(fid, info["name"])
            draw_text(screen, line, font_msg, TEXT_COLOR, (side_x + 20, entry_y + 4))
            sample_n = len(info.get("samples", []))
            draw_text(screen, "{}  |  样本 {}".format(info.get("created_at", ""), sample_n),
                      font_small, DIM_TEXT, (side_x + 20, entry_y + 28))

            del_rect = pygame.Rect(side_x + side_w - 100, entry_y + 9, 80, 30)
            delete_btn_rects.append((fid, del_rect))
            del_hovered = del_rect.collidepoint(mouse_pos)
            del_color = (235, 87, 87, 200) if del_hovered else (235, 87, 87, 100)
            del_surf = pygame.Surface(del_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(del_surf, del_color, del_surf.get_rect(), border_radius=8)
            pygame.draw.rect(del_surf, EXIT_RED, del_surf.get_rect(), 2, border_radius=8)
            screen.blit(del_surf, del_rect.topleft)
            del_text = font_small.render("删除", True, WHITE)
            screen.blit(del_text, del_text.get_rect(center=del_rect.center))

        if not items:
            draw_text(screen, "（尚无人脸，请先学习）", font_small, DIM_TEXT,
                      (side_x + 20, list_top), anchor="topleft")

        if len(items) > max_visible:
            scroll_info = "{}-{}/{}".format(start_idx + 1, end_idx, len(items))
            draw_text(screen, scroll_info, font_small, DIM_TEXT,
                      (side_x + side_w - 20, side_y + side_h - 20), anchor="topright")

        # ----- 删除操作 toast 提示 -----
        if delete_status_timer > 0 and delete_status:
            msg_w = font_msg.size(delete_status)[0] + 60
            msg_rect = pygame.Rect(WIDTH // 2 - msg_w // 2, TOAST_Y, msg_w, 38)
            msg_bg = pygame.Surface(msg_rect.size, pygame.SRCALPHA)
            msg_bg.fill((0, 0, 0, 200))
            screen.blit(msg_bg, msg_rect.topleft)
            pygame.draw.rect(screen, delete_status_color, msg_rect, 2, border_radius=8)
            draw_text(screen, delete_status, font_msg, delete_status_color,
                      (WIDTH // 2, TOAST_Y + 19), anchor="center")

        # ----- 底部提示 -----
        hint = "ESC 退出 | 摄像头画面已整合到主窗口 | 鼠标滚轮可滚动人脸库列表"
        draw_text(screen, hint, font_small, DIM_TEXT, (WIDTH // 2, HINT_Y), anchor="center")

        # =============================================================
        # 查看人脸库详细信息弹窗
        # =============================================================
        if show_face_detail:
            modal_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            modal_overlay.fill((0, 0, 0, 180))
            screen.blit(modal_overlay, (0, 0))

            modal_x, modal_y = WIDTH // 2 - 600, 130
            modal_w, modal_h = 1200, 820
            modal_panel = pygame.Surface((modal_w, modal_h), pygame.SRCALPHA)
            modal_panel.fill((30, 35, 50, 245))
            screen.blit(modal_panel, (modal_x, modal_y))
            pygame.draw.rect(screen, ACCENT, (modal_x, modal_y, modal_w, modal_h), 3, border_radius=12)

            all_items = engine.list_faces()
            draw_text(screen, "人脸库详细信息", font_title, TEXT_COLOR,
                      (modal_x + 40, modal_y + 20), anchor="topleft")
            draw_text(screen, "共 {} 人    数据文件：{}".format(len(all_items), FACE_DB_FILE),
                      font_small, DIM_TEXT, (modal_x + 40, modal_y + 75), anchor="topleft")

            btn_close_detail.update(mouse_pos)
            btn_close_detail.draw(screen)

            total_pages = max(1, (len(all_items) + DETAIL_PAGE_SIZE - 1) // DETAIL_PAGE_SIZE)
            if detail_page > total_pages - 1:
                detail_page = total_pages - 1
            page_start = detail_page * DETAIL_PAGE_SIZE
            page_end = min(page_start + DETAIL_PAGE_SIZE, len(all_items))
            page_items = all_items[page_start:page_end]

            entry_start_y = modal_y + 120
            detail_entry_h = 75
            for i, (fid, info) in enumerate(page_items):
                ey = entry_start_y + i * detail_entry_h
                if i > 0:
                    pygame.draw.line(screen, (255, 255, 255, 40),
                                     (modal_x + 40, ey), (modal_x + modal_w - 40, ey), 1)
                draw_text(screen, "人脸 ID：{}".format(fid), font_label, ACCENT,
                          (modal_x + 40, ey + 8), anchor="topleft")
                draw_text(screen, "姓名：{}".format(info.get("name", "")), font_label, TEXT_COLOR,
                          (modal_x + 300, ey + 8), anchor="topleft")
                draw_text(screen, "登记时间：{}    样本数：{}".format(
                    info.get("created_at", ""), len(info.get("samples", []))),
                    font_small, DIM_TEXT, (modal_x + 40, ey + 42), anchor="topleft")

            if not all_items:
                draw_text(screen, "人脸库为空，请先学习人脸", font_big_result, DIM_TEXT,
                          (modal_x + modal_w // 2, modal_y + modal_h // 2), anchor="center")

            draw_text(screen, "第 {} / {} 页".format(detail_page + 1, total_pages), font_small, DIM_TEXT,
                      (WIDTH // 2, HEIGHT - 115), anchor="center")
            btn_detail_prev.enabled = detail_page > 0
            btn_detail_next.enabled = detail_page < total_pages - 1
            btn_detail_prev.update(mouse_pos)
            btn_detail_prev.draw(screen)
            btn_detail_next.update(mouse_pos)
            btn_detail_next.draw(screen)

        # =============================================================
        # 删除确认弹窗
        # =============================================================
        if delete_confirm_id is not None:
            dialog_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            dialog_overlay.fill((0, 0, 0, 180))
            screen.blit(dialog_overlay, (0, 0))

            dlg_w, dlg_h = 560, 260
            dlg_x = WIDTH // 2 - dlg_w // 2
            dlg_y = HEIGHT // 2 - dlg_h // 2
            dlg_panel = pygame.Surface((dlg_w, dlg_h), pygame.SRCALPHA)
            dlg_panel.fill((45, 35, 40, 245))
            screen.blit(dlg_panel, (dlg_x, dlg_y))
            pygame.draw.rect(screen, EXIT_RED, (dlg_x, dlg_y, dlg_w, dlg_h), 3, border_radius=12)

            face_name = engine.get_name(delete_confirm_id) or ""
            draw_text(screen, "确认删除？", font_subtitle, EXIT_RED,
                      (WIDTH // 2, dlg_y + 25), anchor="midtop")
            draw_text(screen, "将删除：ID={}  姓名={}".format(delete_confirm_id, face_name),
                      font_msg, TEXT_COLOR, (WIDTH // 2, dlg_y + 90), anchor="center")
            draw_text(screen, "将同时删除其样本图并重新训练识别模型",
                      font_small, DIM_TEXT, (WIDTH // 2, dlg_y + 130), anchor="center")

            btn_confirm_delete.update(mouse_pos)
            btn_confirm_delete.draw(screen)
            btn_cancel_delete.update(mouse_pos)
            btn_cancel_delete.draw(screen)

        pygame.display.flip()
        clock.tick(30)

    # ----- 清理资源 -----
    cam_thread_running = False
    recog_thread_running = False
    time.sleep(0.15)
    if cap is not None:
        try:
            cap.release()
            print("摄像头已释放")
        except Exception:
            pass
    pygame.quit()


if __name__ == "__main__":
    main()
