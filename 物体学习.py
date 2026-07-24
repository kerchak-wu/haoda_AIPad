# -*- coding: utf-8 -*-
"""
物体学习与识别程序（自包含版本，不依赖好搭 AI 派专有 SDK）
================================================================
参考：github.com/kerchak-wu/haoda_AIPad （好搭 AI 派范例 11.物体识别学习 / 12.物体识别）
      以及 人脸学习.py 的工程结构与界面实现。

技术方案：
  - 外接摄像头采集：OpenCV VideoCapture
  - 物体特征：OpenCV ORB 特征点检测 + 描述子（二进制描述子，自带旋转/尺度不变性）
  - 物体识别：ORB 描述子匹配（BFMatcher + 汉明距离 + 绝对距离阈值）+ RANSAC 单应性矩阵定位
  - 界面：pygame，窗口 1920 x 1080，摄像头画面直接整合到主窗口
  - 数据持久化：
      object_data/object_db.json          —— 物体库 {id: {name, created_at, samples, roi_size, ...}}
      object_data/descriptors/<id>_<n>.npy —— ORB 描述子（uint8, N×32）
      object_data/keypoints/<id>_<n>.npy   —— 特征点坐标（float32, N×2，roi_size 坐标系）
      object_data/images/<id>_<n>.png      —— 学习时保存的 ROI 样本图（PNG 无损）

核心特性：
  1. 学习物体：输入名称 -> 采集多帧 -> 提取中心 ROI 的 ORB 特征 -> 分配物体 ID -> 保存
  2. 物体识别：实时提取整帧 ORB 特征并与库中各类物体匹配，匹配数超过阈值即识别成功
  3. 查看物体库：弹窗分页查看所有物体的 ID、名称、登记时间、样本数
  4. 删除物体：列表中点击「删除」可移除库中已有信息（含二次确认）
  5. 程序关闭后，其他程序可直接 import 本模块调用物体数据实现识别

识别原理：
  ORB（Oriented FAST and Rotated BRIEF）是 OpenCV 内置的快速特征检测/描述算法，
  对物体的纹理细节具有旋转不变性与一定的尺度不变性。学习时从画面中心 ROI 提取
  ORB 特征并保存；识别时从整帧提取特征，用 BFMatcher 汉明距离 + 绝对距离阈值
  （MATCH_DIST_THRESHOLD）筛选优质匹配，再用 RANSAC 单应性矩阵做几何一致性验证，
  三重准则同时满足才判定识别成功：
    1. 优质匹配数 >= GOOD_MATCH_THRESHOLD（排除特征点过少的随机匹配）
    2. RANSAC 内点数 >= MIN_INLIERS（排除偶然匹配数量够但分布零散的情况）
    3. RANSAC 内点比例 >= MIN_INLIER_RATIO（排除 good 数高但一致性差的误匹配）
  满足后用 RANSAC 单应性矩阵投影 ROI 边角得到物体在画面中的位置框。
  匹配采用绝对距离阈值而非 Lowe 比率测试：物体学习通常采集多帧静止物体，特征高度
  相似，比率测试会因次近邻距离≈最近邻距离而失效；绝对距离阈值对多样本更鲁棒，
  误匹配由 RANSAC 几何一致性进一步过滤。
  适用于具有丰富纹理的物体（如带图案的卡片、标签、包装盒、玩具等）；纯色无纹理
  物体特征点稀少，识别效果会下降。

其他程序调用示例：
    from 物体学习 import ObjectEngine, get_object_name, load_object_database, list_known_objects

    # 方式一：直接调用引擎做识别（推荐）
    engine = ObjectEngine()
    engine.load()
    for box, obj_id, name, conf in engine.recognize(frame):
        print(obj_id, name, conf)

    # 方式二：根据物体 ID 查名称
    name = get_object_name(obj_id)       # 未登记返回 None
    db = load_object_database()          # 获取整个物体库
    all_objs = list_known_objects()      # [(id, name), ...]
"""

import os
import sys
import json
import time
import datetime
import threading

import numpy as np

# GUI 依赖（仅使用 ObjectEngine 做识别时可有可无；运行主程序必须安装）
try:
    import pygame
except Exception:  # pragma: no cover
    pygame = None

# ===========================================================================
# 配置
# ===========================================================================
WIDTH, HEIGHT = 1920, 1080

# 外接摄像头节点：固定为 /dev/video41（优先）或 /dev/video40
CAMERA_ID = -1  # 保留兼容，已不影响实际探测
CAMERA_W, CAMERA_H = 1280, 720

# 摄像头画面在主窗口中的显示尺寸
CAM_DISP_W, CAM_DISP_H = 1100, 520

BG_IMAGE = os.path.join("images", "1.jpg")

# 物体数据目录与文件
OBJECT_DATA_DIR = "object_data"
OBJECT_DB_FILE = os.path.join(OBJECT_DATA_DIR, "object_db.json")
DESC_DIR = os.path.join(OBJECT_DATA_DIR, "descriptors")
KP_DIR = os.path.join(OBJECT_DATA_DIR, "keypoints")
OBJ_IMG_DIR = os.path.join(OBJECT_DATA_DIR, "images")

# 识别参数
GOOD_MATCH_THRESHOLD = 40      # 优质匹配数阈值，越大越严格（真实物通常 200+，无关画面 <20）
MATCH_DIST_THRESHOLD = 50      # ORB 汉明距离阈值，小于此值视为优质匹配（经验值 50）
MIN_INLIERS = 12               # RANSAC 最小内点数，低于此值视为误匹配（真实物通常 40+）
MIN_INLIER_RATIO = 0.15        # RANSAC 内点比例阈值（inliers/good），低于此值视为误匹配
DEDUP_DISTANCE = 24            # 描述子去重距离，小于此值视为重复特征（多帧学习去冗余）
ORB_FEATURES = 800             # 每帧提取的 ORB 特征点上限

# 学习参数
LEARN_SAMPLES = 15             # 学习时采集的样本帧数
LEARN_DURATION = 1.8           # 学习采集时长（秒）
LEARN_ROI_FRAC = 0.60          # 学习 ROI 占画面比例（中心 60%）
OBJ_SIZE = 360                 # ROI 归一化尺寸（像素，特征点坐标系统一）

# 识别处理：整帧降采样宽度，加快 ORB 提取并使尺度与学习 ROI 更接近
RECOG_PROC_W = 640

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
OBJ_BOX_KNOWN = (130, 255, 170)
OBJ_BOX_UNKNOWN = (255, 200, 120)
GUIDE_COLOR = (86, 196, 255)


def _now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class _CameraProbeTimeout(Exception):
    """探测摄像头时 SIGALRM 超时（用于打断卡在 select() 的 V4L2 设备）。"""
    pass


# ===========================================================================
# 物体引擎（核心：检测 / 学习 / 识别 / 持久化）
# ===========================================================================
class ObjectEngine:
    """基于 OpenCV ORB 特征匹配的自包含物体识别引擎。

    物体数据保存到磁盘（JSON 数据库 + 描述子/特征点 npy + 样本图），程序关闭后
    其他程序可重新加载用于识别。
    """

    def __init__(self, data_dir=OBJECT_DATA_DIR, threshold=GOOD_MATCH_THRESHOLD):
        import cv2  # noqa: F401  确保导入
        self.cv2 = cv2
        self.data_dir = data_dir
        self.db_path = os.path.join(data_dir, "object_db.json")
        self.desc_dir = os.path.join(data_dir, "descriptors")
        self.kp_dir = os.path.join(data_dir, "keypoints")
        self.img_dir = os.path.join(data_dir, "images")
        self.threshold = threshold
        self.db = {}                 # {"id": {"name", "created_at", "samples", "desc_files", "kp_files", "sample_images"}}
        self._detector = None
        self._matcher = None
        self._index = {}             # {id: {"desc": np.array, "kp": np.array}}
        self._lock = threading.RLock()
        self._init_detector()
        self._init_matcher()
        self.load()

    # ---------- 初始化 ----------
    def _init_detector(self):
        cv2 = self.cv2
        try:
            self._detector = cv2.ORB_create(nfeatures=ORB_FEATURES, scaleFactor=1.2, nlevels=8)
        except Exception:
            try:
                self._detector = cv2.ORB_create(nfeatures=ORB_FEATURES)
            except Exception:
                self._detector = None

    def _init_matcher(self):
        cv2 = self.cv2
        # ORB 是二进制描述子，使用汉明距离；crossCheck=False 配合 match() + 绝对距离阈值
        try:
            self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        except Exception:
            self._matcher = None

    # ---------- 加载 / 保存 ----------
    def load(self):
        """加载物体库 JSON 并重建内存索引；若无数据则空库运行。"""
        with self._lock:
            self.db = {}
            if os.path.exists(self.db_path):
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.db = data.get("objects", {})
                except Exception:
                    self.db = {}
            self._rebuild_index_locked()

    def _save_db_locked(self):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump({"objects": self.db}, f, ensure_ascii=False, indent=2)

    # ---------- 内存索引重建 ----------
    def _rebuild_index_locked(self):
        """把每类物体的所有样本描述子/特征点拼接成单数组，并去除高度重复的描述子。

        多帧学习静止物体时，各帧特征高度相似，直接拼接会导致库内大量冗余描述子，
        既拖慢匹配又增加与无关画面的随机匹配概率。去重逻辑：用 BFMatcher 对合并后
        的描述子做 knnMatch(k=2)，每个描述子的次近邻（最近邻是自身）距离若小于
        DEDUP_DISTANCE，则视为重复并删除其一。
        """
        cv2 = self.cv2
        self._index = {}
        for fid, info in self.db.items():
            all_desc = []
            all_kp = []
            desc_files = info.get("desc_files", [])
            kp_files = info.get("kp_files", [])
            for p_desc, p_kp in zip(desc_files, kp_files):
                if not (os.path.exists(p_desc) and os.path.exists(p_kp)):
                    continue
                try:
                    desc = np.load(p_desc)
                    kp = np.load(p_kp)
                except Exception:
                    continue
                if desc is None or len(desc) == 0 or kp is None or len(kp) == 0:
                    continue
                if desc.shape[0] != kp.shape[0]:
                    continue
                all_desc.append(desc)
                all_kp.append(kp)
            if not all_desc:
                continue
            desc_arr = np.concatenate(all_desc, axis=0)
            kp_arr = np.concatenate(all_kp, axis=0)
            # 去重：多帧静止物体特征高度相似，删除与已有描述子距离过近的副本
            desc_arr, kp_arr = self._dedup_descriptors(desc_arr, kp_arr)
            if len(desc_arr) == 0:
                continue
            # roi_size 为学习 ROI 缩放后的尺寸 (w, h)，用于 RANSAC 投影边角
            rs = info.get("roi_size")
            if not rs or len(rs) != 2:
                rs = [OBJ_SIZE, OBJ_SIZE]
            self._index[fid] = {
                "desc": desc_arr,
                "kp": kp_arr,
                "roi_size": (int(rs[0]), int(rs[1])),
            }

    def _dedup_descriptors(self, desc, kp):
        """去除高度相似的描述子，返回去重后的 (desc, kp)。

        用 BFMatcher.knnMatch(k=2) 在描述子集合内部找最近邻：每个描述子的最近邻是
        自身（距离 0），次近邻是最近的其它描述子。若次近邻距离 < DEDUP_DISTANCE，
        说明存在重复，保留先出现的那一个。
        """
        cv2 = self.cv2
        n = len(desc)
        if n < 2 or self._matcher is None:
            return desc, kp
        try:
            matches = self._matcher.knnMatch(desc, desc, k=2)
        except Exception:
            return desc, kp
        keep = []
        removed = set()
        for i, pair in enumerate(matches):
            if i in removed:
                continue
            keep.append(i)
            if len(pair) < 2:
                continue
            nn = pair[1]  # 次近邻（最近邻是自身）
            if nn.distance < DEDUP_DISTANCE:
                removed.add(nn.trainIdx)  # 标记重复项删除
        return desc[keep], kp[keep]

    # ---------- 特征提取（学习用：中心 ROI） ----------
    def _extract_roi_features(self, frame):
        """从画面中心 ROI 提取 ORB 特征（保持纵横比缩放，与识别时坐标系一致）。

        Returns:
            (desc, kp_pts, roi_img, roi_rect, roi_size)
            - desc: np.array (N, 32) uint8，无特征时为 None
            - kp_pts: np.array (N, 2) float32，特征点坐标（roi_size 坐标系）
            - roi_img: ROI 保持纵横比缩放后的 BGR 图像（用于保存样本图）
            - roi_rect: (x, y, w, h) 原始帧坐标系中的 ROI 矩形
            - roi_size: (w, h) 缩放后 ROI 图像的尺寸（较长边为 OBJ_SIZE）

        说明：学习 ROI 缩放必须保持纵横比，与识别时整帧按宽度 RECOG_PROC_W
        等比缩放的逻辑一致，否则特征点相对位置会发生形变导致匹配失败。
        """
        cv2 = self.cv2
        if frame is None or self._detector is None:
            return None, None, None, None, None
        h, w = frame.shape[:2]
        roi_w = int(w * LEARN_ROI_FRAC)
        roi_h = int(h * LEARN_ROI_FRAC)
        rx = (w - roi_w) // 2
        ry = (h - roi_h) // 2
        roi = frame[ry:ry + roi_h, rx:rx + roi_w]
        # 保持纵横比：较长边缩放到 OBJ_SIZE，另一边按比例
        if roi_w >= roi_h:
            out_w = OBJ_SIZE
            out_h = max(1, int(round(roi_h * OBJ_SIZE / float(roi_w))))
        else:
            out_h = OBJ_SIZE
            out_w = max(1, int(round(roi_w * OBJ_SIZE / float(roi_h))))
        roi_img = cv2.resize(roi, (out_w, out_h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
        kp, desc = self._detector.detectAndCompute(gray, None)
        if desc is None or len(desc) == 0:
            return None, None, roi_img, (rx, ry, roi_w, roi_h), (out_w, out_h)
        kp_pts = np.array([k.pt for k in kp], dtype=np.float32)
        return desc, kp_pts, roi_img, (rx, ry, roi_w, roi_h), (out_w, out_h)

    @staticmethod
    def learn_roi_rect(frame_w, frame_h):
        """计算学习 ROI 在原始帧中的矩形（供界面绘制引导框使用）。"""
        rw = int(frame_w * LEARN_ROI_FRAC)
        rh = int(frame_h * LEARN_ROI_FRAC)
        return ((frame_w - rw) // 2, (frame_h - rh) // 2, rw, rh)

    # ---------- 学习 ----------
    def learn_object(self, frames, name):
        """从多帧图像学习一个新物体，分配新 ID 并保存。

        Args:
            frames: 图像帧列表（BGR ndarray）
            name:   物体名称
        Returns:
            新分配的物体 ID（int），若无有效特征返回 None
        """
        with self._lock:
            descs, kps, imgs = [], [], []
            roi_size = None  # (w, h) 缩放后 ROI 尺寸，所有帧应一致，取首个有效帧
            for frame in frames:
                if frame is None:
                    continue
                desc, kp_pts, roi_img, _, rs = self._extract_roi_features(frame)
                if desc is not None and len(desc) > 0:
                    descs.append(desc)
                    kps.append(kp_pts)
                    if roi_img is not None:
                        imgs.append(roi_img)
                    if roi_size is None and rs is not None:
                        roi_size = rs
            if not descs:
                return None

            new_id = self._next_id_locked()
            fid = str(new_id)
            os.makedirs(self.desc_dir, exist_ok=True)
            os.makedirs(self.kp_dir, exist_ok=True)
            os.makedirs(self.img_dir, exist_ok=True)
            desc_files, kp_files, sample_images = [], [], []
            for i, (desc, kp_pts) in enumerate(zip(descs, kps)):
                dp = os.path.join(self.desc_dir, "{}_{}.npy".format(new_id, i))
                kp_path = os.path.join(self.kp_dir, "{}_{}.npy".format(new_id, i))
                try:
                    np.save(dp, desc)
                    np.save(kp_path, kp_pts)
                except Exception as e:
                    print("样本保存失败: {}".format(e))
                    continue
                desc_files.append(dp)
                kp_files.append(kp_path)
                img_path = os.path.join(self.img_dir, "{}_{}.png".format(new_id, i))
                if i < len(imgs) and self.cv2.imwrite(img_path, imgs[i]):
                    sample_images.append(img_path)
            if not desc_files:
                return None
            if roi_size is None:
                roi_size = (OBJ_SIZE, OBJ_SIZE)
            self.db[fid] = {
                "name": name,
                "created_at": _now_str(),
                "samples": len(desc_files),
                "desc_files": desc_files,
                "kp_files": kp_files,
                "sample_images": sample_images,
                "roi_size": [int(roi_size[0]), int(roi_size[1])],
            }
            self._save_db_locked()
            self._rebuild_index_locked()
            return new_id

    def _next_id_locked(self):
        ids = [int(k) for k in self.db.keys() if str(k).isdigit()]
        return (max(ids) + 1) if ids else 1

    # ---------- 识别 ----------
    def _compute_box(self, frame_shape, good_matches, kp_q, cat_kp, roi_size):
        """根据优质匹配计算物体在帧中的位置框。

        优先用 RANSAC 单应性矩阵投影学习 ROI 边角得到精确框；
        退化时回退到优质匹配特征点的包围盒。
        roi_size: 学习 ROI 缩放后的尺寸 (w, h)，用于投影边角。
        """
        cv2 = self.cv2
        h, w = frame_shape[:2]
        rw, rh = roi_size
        n = len(good_matches)
        if n >= 8:
            src = np.float32([cat_kp[m.trainIdx] for m in good_matches]).reshape(-1, 1, 2)
            dst = np.float32([kp_q[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            try:
                M, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            except Exception:
                M, mask = None, None
            if M is not None and mask is not None and int(mask.sum()) >= 6:
                roi_corners = np.float32(
                    [[0, 0], [rw, 0], [rw, rh], [0, rh]]
                ).reshape(-1, 1, 2)
                try:
                    projected = cv2.perspectiveTransform(roi_corners, M)
                except Exception:
                    projected = None
                if projected is not None:
                    xs = projected[:, 0, 0]
                    ys = projected[:, 0, 1]
                    x1 = int(max(0, min(xs)))
                    y1 = int(max(0, min(ys)))
                    x2 = int(min(w, max(xs)))
                    y2 = int(min(h, max(ys)))
                    if x2 - x1 > 15 and y2 - y1 > 15:
                        return (x1, y1, x2 - x1, y2 - y1)
        if n > 0:
            pts = np.float32([kp_q[m.queryIdx].pt for m in good_matches])
            xs, ys = pts[:, 0], pts[:, 1]
            x1 = int(max(0, xs.min()))
            y1 = int(max(0, ys.min()))
            x2 = int(min(w, xs.max()))
            y2 = int(min(h, ys.max()))
            return (x1, y1, max(1, x2 - x1), max(1, y2 - y1))
        return None

    def recognize(self, frame):
        """识别 frame 中最匹配的物体。

        Returns:
            [(box, object_id, name, confidence), ...]（取优质匹配最多的那一个物体）
            - 已识别：object_id=int, name=str, confidence=0~1 浮点
            - 未识别：返回空列表

        匹配策略：用 BFMatcher.match() 取每个查询描述子的最近邻，再以绝对汉明距离
        阈值 MATCH_DIST_THRESHOLD 过滤。相比 Lowe 比率测试，绝对距离阈值对「多帧
        学习导致的特征重复」更鲁棒（比率测试在样本高度相似时会因次近邻距离≈最近
        邻距离而失效）。误匹配由后续 RANSAC 单应性矩阵的几何一致性进一步过滤：
        要求优质匹配数 >= GOOD_MATCH_THRESHOLD，且 RANSAC 内点数 >= MIN_INLIERS、
        内点比例 >= MIN_INLIER_RATIO，三者同时满足才判定为识别成功。
        """
        cv2 = self.cv2
        with self._lock:
            results = []
            if self._detector is None or self._matcher is None or frame is None or not self._index:
                return results
            h0, w0 = frame.shape[:2]
            # 整帧降采样：加快 ORB 提取并使物体尺度与学习 ROI 更接近
            scale = RECOG_PROC_W / float(w0) if w0 > 0 else 1.0
            proc_w = RECOG_PROC_W
            proc_h = max(1, int(h0 * scale))
            small = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            kp_q, desc_q = self._detector.detectAndCompute(gray, None)
            if desc_q is None or len(desc_q) < 5:
                return results

            best = None  # (good_count, inlier_count, fid, good_matches)
            for fid, idx in self._index.items():
                desc_t = idx["desc"]
                if desc_t is None or len(desc_t) < 5:
                    continue
                try:
                    matches = self._matcher.match(desc_q, desc_t)
                except Exception:
                    continue
                good = [m for m in matches if m.distance < MATCH_DIST_THRESHOLD]
                if len(good) < self.threshold:
                    continue
                # RANSAC 几何验证：计算优质匹配中与单应性矩阵一致的内点数
                inlier_count = 0
                if len(good) >= 8:
                    src = np.float32([idx['kp'][m.trainIdx] for m in good]).reshape(-1, 1, 2)
                    dst = np.float32([kp_q[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                    try:
                        M, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
                    except Exception:
                        M, mask = None, None
                    if mask is not None:
                        inlier_count = int(mask.sum())
                # 优先选 good 数多且 inlier 多的物体
                if (best is None or
                    len(good) > best[0] or
                    (len(good) == best[0] and inlier_count > best[1])):
                    best = (len(good), inlier_count, fid, good)

            if best is not None:
                good_count, inlier_count, fid, good = best
                # 即使 good 数达标，inlier 过少或比例过低也视为误匹配
                inlier_ratio = inlier_count / float(good_count) if good_count > 0 else 0.0
                if inlier_count < MIN_INLIERS or inlier_ratio < MIN_INLIER_RATIO:
                    return results
                idx = self._index[fid]
                cat_kp = idx["kp"]
                roi_size = idx.get("roi_size", (OBJ_SIZE, OBJ_SIZE))
                box_small = self._compute_box((proc_h, proc_w), good, kp_q, cat_kp, roi_size)
                if box_small is not None:
                    # 还原到原始帧坐标
                    x, y, bw, bh = box_small
                    box = (int(round(x / scale)),
                           int(round(y / scale)),
                           max(1, int(round(bw / scale))),
                           max(1, int(round(bh / scale))))
                else:
                    box = None
                name = self.db[fid]["name"]
                # 置信度：优质匹配数相对于阈值线性映射，封顶 1.0
                conf = min(1.0, good_count / float(self.threshold * 2.5))
                results.append((box, int(fid), name, round(conf, 3)))
            return results

    # ---------- 删除 ----------
    def delete_object(self, obj_id):
        """删除指定 ID 的物体（含样本数据并重建索引）。返回是否删除成功。"""
        with self._lock:
            fid = str(obj_id)
            if fid not in self.db:
                return False
            info = self.db[fid]
            for p in (info.get("desc_files", []) + info.get("kp_files", [])
                      + info.get("sample_images", [])):
                try:
                    os.remove(p)
                except Exception:
                    pass
            del self.db[fid]
            self._save_db_locked()
            self._rebuild_index_locked()
            return True

    # ---------- 查询 ----------
    def get_name(self, obj_id):
        with self._lock:
            info = self.db.get(str(obj_id))
            return info["name"] if info else None

    def list_objects(self):
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
def load_object_database(path=OBJECT_DB_FILE):
    """加载物体数据库，返回 {object_id(str): {name, created_at, samples, ...}}。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("objects", {})
    except Exception:
        return {}


def get_object_name(obj_id, path=OBJECT_DB_FILE):
    """根据物体 ID 获取名称，未登记返回 None。"""
    objs = load_object_database(path)
    info = objs.get(str(obj_id))
    return info["name"] if info else None


def list_known_objects(path=OBJECT_DB_FILE):
    """返回所有已知物体列表 [(object_id, name), ...]。"""
    objs = load_object_database(path)
    items = [(int(k), v["name"]) for k, v in objs.items() if str(k).isdigit()]
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
# 摄像头打开（MJPG + 超时 + 雪花检测）
# ===========================================================================
def _is_valid_frame(frame):
    """判断帧是否为有效画面（非空、非全黑、非雪花噪声）。

    雪花/随机噪声的特点：用 INTER_AREA 下采样后，相邻噪声相互抵消，
    标准差急剧下降；真实画面有空间结构，下采样后保持高标准差。
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
    """尝试以 MJPG 格式打开指定编号的摄像头并验证可读到有效帧。"""
    import cv2
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
    """摄像头固定为 /dev/video41（优先）或 /dev/video40。"""
    import cv2  # noqa: F401  确保模块级 cv2 可用
    for cid in (41, 40):
        print("  探测 /dev/video{} ...".format(cid))
        cap = _try_open(cid)
        if cap is not None:
            print("摄像头使用编号：{} (/dev/video{})".format(cid, cid))
            return cap
    return None


# ===========================================================================
# 主程序
# ===========================================================================
def main():
    global pygame, cv2
    import pygame
    import cv2
    import signal

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("物体学习与识别系统")
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

    # ----- 初始化物体引擎 -----
    print("物体引擎初始化中...")
    engine = ObjectEngine()
    print("物体库已加载：共 {} 个物体".format(engine.count()))

    # ----- 打开摄像头 -----
    print("外接摄像头打开中...")
    cap = open_camera()
    camera_ok = cap is not None and cap.isOpened()
    if camera_ok:
        print("外接摄像头已打开")
    else:
        print("摄像头打开失败，请检查 /dev/video41 和 /dev/video40 是否存在且未被占用")

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

    show_obj_detail = False
    detail_page = 0

    delete_confirm_id = None
    delete_status = ""
    delete_status_color = DIM_TEXT
    delete_status_timer = 0

    obj_list_scroll = 0
    force_refresh_list = False

    # =============================================================
    # 摄像头后台采集线程
    # =============================================================
    latest_frame = None
    frame_lock = threading.Lock()
    cam_thread_running = True

    # 识别后台线程结果
    latest_recog = []          # [(box, obj_id, name, conf), ...]
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
        """后台识别物体，结果供主循环绘制。"""
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
    # 物体学习
    # =============================================================
    def start_learn():
        nonlocal learning, learn_status, learn_status_color
        name = name_input.strip()
        if not name:
            learn_status = "请先输入物体名称"
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
        learn_status = "正在学习物体，请将物体放在画面中央保持不动..."
        learn_status_color = WARN

        def worker():
            nonlocal learning, learn_status, learn_status_color
            try:
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
                obj_id = engine.learn_object(frames, name)
                if obj_id is None:
                    learn_status = "学习失败，未提取到有效特征，请将带纹理的物体放在引导框内重试"
                    learn_status_color = ERROR
                else:
                    learn_status = "学习成功！ID={}  名称={}".format(obj_id, name)
                    learn_status_color = SUCCESS
                    print("物体学习成功：ID={} 名称={}".format(obj_id, name))
            except Exception as e:
                learn_status = "学习异常：{}".format(e)
                learn_status_color = ERROR
            finally:
                with learn_lock:
                    learning = False

        threading.Thread(target=worker, daemon=True).start()

    # =============================================================
    # 删除物体
    # =============================================================
    def delete_object(obj_id):
        nonlocal delete_status, delete_status_color, delete_status_timer, force_refresh_list
        name = engine.get_name(obj_id)
        ok = engine.delete_object(obj_id)
        if ok:
            delete_status = "已删除：ID={}  名称={}".format(obj_id, name)
            delete_status_color = SUCCESS
            print("物体已删除：ID={} 名称={}".format(obj_id, name))
        else:
            delete_status = "未找到 ID={} 的物体".format(obj_id)
            delete_status_color = ERROR
        delete_status_timer = 180
        force_refresh_list = True

    # =============================================================
    # 按钮定义
    # =============================================================
    btn_learn_mode = Button((640, MODE_BTN_Y, 260, 52), "学习物体", font_btn)
    btn_recog_mode = Button((1000, MODE_BTN_Y, 260, 52), "物体识别", font_btn)
    btn_start_learn = Button((rtop_x + 20, rtop_y + 155, rtop_w - 40, 50), "开始学习物体", font_btn,
                             color=(86, 196, 255, 120), hover_color=(86, 196, 255, 220))
    btn_exit = Button((1740, EXIT_BTN_Y, 140, 48), "退出程序", font_exit,
                      color=(235, 87, 87, 120), hover_color=(235, 87, 87, 220))
    btn_view_objs = Button((side_x, view_btn_y, side_w, 50), "查看物体库详细信息", font_btn,
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
                    elif show_obj_detail:
                        show_obj_detail = False
                    else:
                        running = False
                elif (input_active and mode == MODE_LEARN
                      and not show_obj_detail and delete_confirm_id is None):
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
                            delete_object(delete_confirm_id)
                            delete_confirm_id = None
                        elif btn_cancel_delete.rect.collidepoint(event.pos):
                            delete_confirm_id = None
                        continue

                    if show_obj_detail:
                        if btn_close_detail.rect.collidepoint(event.pos):
                            show_obj_detail = False
                        elif btn_detail_prev.rect.collidepoint(event.pos) and btn_detail_prev.enabled:
                            detail_page = max(0, detail_page - 1)
                        elif btn_detail_next.rect.collidepoint(event.pos) and btn_detail_next.enabled:
                            all_items = engine.list_objects()
                            max_pages = max(0, (len(all_items) - 1) // DETAIL_PAGE_SIZE)
                            detail_page = min(max_pages, detail_page + 1)
                        continue

                    if btn_exit.rect.collidepoint(event.pos):
                        running = False
                        continue
                    if btn_view_objs.rect.collidepoint(event.pos):
                        show_obj_detail = True
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
                        obj_list_scroll = max(0, obj_list_scroll - 1)
                elif event.button == 5:
                    if side_x <= mouse_pos[0] <= side_x + side_w and side_y <= mouse_pos[1] <= side_y + side_h:
                        items_count = engine.count()
                        list_top = side_y + 90
                        list_h = side_h - 90 - 25
                        entry_h = 50
                        max_visible = list_h // entry_h
                        max_scroll = max(0, items_count - max_visible)
                        obj_list_scroll = min(max_scroll, obj_list_scroll + 1)

        # ----- 识别历史记录 -----
        if mode == MODE_RECOGNIZE and camera_ok:
            with recog_lock:
                recog_results = list(latest_recog)
            if recog_cooldown > 0:
                recog_cooldown -= 1
            if recog_results:
                box, obj_id, name, conf = recog_results[0]
                if recog_cooldown == 0 or obj_id != last_recog_id:
                    time_str = datetime.datetime.now().strftime("%H:%M:%S")
                    recog_history.append((time_str, obj_id, name, conf))
                    if len(recog_history) > 20:
                        recog_history.pop(0)
                    last_recog_id = obj_id
                    recog_cooldown = RECOG_COOLDOWN_FRAMES

        if delete_status_timer > 0:
            delete_status_timer -= 1

        if force_refresh_list:
            force_refresh_list = False
            obj_list_scroll = 0

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
        draw_text(screen, "物体学习与识别系统", font_title, TEXT_COLOR,
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
            draw_text(screen, "学习物体 — 摄像头画面", font_subtitle, ACCENT,
                      (panel_x + 30, panel_y + 20), anchor="topleft")
            draw_text(screen, "输入名称后点击「开始学习物体」，将带纹理物体放在引导框内完成学习",
                      font_small, DIM_TEXT, (panel_x + 30, panel_y + 60), anchor="topleft")
        else:
            draw_text(screen, "物体识别 — 摄像头画面", font_subtitle, ACCENT,
                      (panel_x + 30, panel_y + 20), anchor="topleft")
            draw_text(screen, "将已登记的物体对准摄像头，系统将实时识别并框出位置",
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

        # 学习模式：绘制中心 ROI 引导框
        if mode == MODE_LEARN and cam_surface is not None:
            guide_rw = int(CAM_DISP_W * LEARN_ROI_FRAC)
            guide_rh = int(CAM_DISP_H * LEARN_ROI_FRAC)
            guide_rx = cam_x + (CAM_DISP_W - guide_rw) // 2
            guide_ry = cam_y + (CAM_DISP_H - guide_rh) // 2
            # 虚线效果：用多段短线绘制
            dash_len = 12
            gap_len = 8
            for seg_x in range(guide_rx, guide_rx + guide_rw, dash_len + gap_len):
                pygame.draw.line(screen, GUIDE_COLOR,
                                 (seg_x, guide_ry),
                                 (min(seg_x + dash_len, guide_rx + guide_rw), guide_ry), 3)
                pygame.draw.line(screen, GUIDE_COLOR,
                                 (seg_x, guide_ry + guide_rh),
                                 (min(seg_x + dash_len, guide_rx + guide_rw), guide_ry + guide_rh), 3)
            for seg_y in range(guide_ry, guide_ry + guide_rh, dash_len + gap_len):
                pygame.draw.line(screen, GUIDE_COLOR,
                                 (guide_rx, seg_y),
                                 (guide_rx, min(seg_y + dash_len, guide_ry + guide_rh)), 3)
                pygame.draw.line(screen, GUIDE_COLOR,
                                 (guide_rx + guide_rw, seg_y),
                                 (guide_rx + guide_rw, min(seg_y + dash_len, guide_ry + guide_rh)), 3)
            # 四角强调
            corner_len = 18
            for cx, cy, dx, dy in [
                (guide_rx, guide_ry, 1, 1),
                (guide_rx + guide_rw, guide_ry, -1, 1),
                (guide_rx, guide_ry + guide_rh, 1, -1),
                (guide_rx + guide_rw, guide_ry + guide_rh, -1, -1),
            ]:
                pygame.draw.line(screen, ACCENT, (cx, cy), (cx + dx * corner_len, cy), 4)
                pygame.draw.line(screen, ACCENT, (cx, cy), (cx, cy + dy * corner_len), 4)
            draw_text(screen, "将物体放在此区域内", font_small, GUIDE_COLOR,
                      (guide_rx + guide_rw // 2, guide_ry - 22), anchor="center")

        # 识别模式：在摄像头画面上绘制物体框与名称
        if mode == MODE_RECOGNIZE and camera_ok and cam_surface is not None and frame is not None:
            with recog_lock:
                recog_results = list(latest_recog)
            sx = CAM_DISP_W / float(frame.shape[1])
            sy = CAM_DISP_H / float(frame.shape[0])
            for (bx, by, bw, bh), obj_id, name, conf in recog_results:
                if bx is None:
                    continue
                rx = cam_x + int(bx * sx)
                ry = cam_y + int(by * sy)
                rw = int(bw * sx)
                rh = int(bh * sy)
                color = OBJ_BOX_KNOWN if name else OBJ_BOX_UNKNOWN
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
                draw_text(screen, "● 识别到物体", font_small, SUCCESS,
                          (cam_x + 12, cam_y + 12), anchor="topleft")

        # ----- 摄像头下方：操作提示 / 识别历史 -----
        if mode == MODE_LEARN:
            draw_text(screen, "操作提示", font_label, ACCENT,
                      (panel_x + 30, below_cam_y), anchor="topleft")
            tips = [
                "1. 在右侧输入框输入物体名称",
                "2. 点击「开始学习物体」或按回车键",
                "3. 将带纹理的物体放在蓝色引导框内保持不动",
                "4. 学习成功后自动保存特征与样本到 object_data/",
                "5. 其他程序可 from 物体学习 import ObjectEngine 调用",
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
                t_str, oid, name, conf = recog_history[idx]
                if name:
                    color = SUCCESS
                    line = "[{}]  ID={}  {}  置信度={:.0%}".format(t_str, oid, name, conf)
                else:
                    color = WARN
                    line = "[{}]  未识别物体".format(t_str)
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
            draw_text(screen, "名称：", font_label, TEXT_COLOR,
                      (rtop_x + 20, rtop_y + 50), anchor="topleft")

            input_surf = pygame.Surface(input_rect.size, pygame.SRCALPHA)
            input_surf.fill(INPUT_BG)
            screen.blit(input_surf, input_rect.topleft)
            border_color = ACCENT if input_active else (255, 255, 255, 80)
            pygame.draw.rect(screen, border_color, input_rect, 2, border_radius=10)
            show_text = name_input if name_input else ("请输入物体名称..." if not input_active else "")
            input_color = TEXT_COLOR if name_input else DIM_TEXT
            draw_text(screen, show_text, font_input, input_color,
                      (input_rect.x + 12, input_rect.centery), anchor="midleft")
            if input_active and (pygame.time.get_ticks() // 500) % 2 == 0:
                tw = font_input.size(name_input)[0]
                cx = input_rect.x + 12 + tw + 2
                pygame.draw.line(screen, WHITE, (cx, input_rect.y + 10),
                                 (cx, input_rect.bottom - 10), 2)

            btn_start_learn.enabled = not learning
            btn_start_learn.text = "学习中..." if learning else "开始学习物体"
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
                draw_text(screen, "等待识别物体...", font_big_result, DIM_TEXT,
                          (rtop_cx, rtop_y + 75), anchor="center")
            else:
                t_str, oid, name, conf = recog_history[-1]
                if name:
                    result_line = "识别到：{}".format(name)
                    result_color = SUCCESS
                else:
                    result_line = "未识别物体"
                    result_color = WARN
                draw_text(screen, result_line, font_big_result, result_color,
                          (rtop_cx, rtop_y + 70), anchor="center")
                if name:
                    detail = "物体ID：{}    置信度：{:.0%}".format(oid, conf)
                else:
                    detail = "未在物体库中匹配到"
                draw_text(screen, detail, font_msg, DIM_TEXT,
                          (rtop_cx, rtop_y + 130), anchor="center")
                draw_text(screen, "时间：{}".format(t_str), font_small, DIM_TEXT,
                          (rtop_cx, rtop_y + 165), anchor="center")

        # =============================================================
        # 查看物体库按钮
        # =============================================================
        btn_view_objs.update(mouse_pos)
        btn_view_objs.draw(screen)

        # =============================================================
        # 右侧物体库面板
        # =============================================================
        delete_btn_rects = []
        draw_panel(screen, side_x, side_y, side_w, side_h)

        draw_text(screen, "已保存物体库", font_subtitle, ACCENT,
                  (side_x + 20, side_y + 12), anchor="topleft")
        draw_text(screen, "共 {} 个  |  点击「删除」移除  |  滚轮滚动".format(engine.count()),
                  font_small, DIM_TEXT, (side_x + 20, side_y + 52), anchor="topleft")

        list_top = side_y + 85
        list_h = side_h - 85 - 25
        entry_h = 50
        max_visible = list_h // entry_h
        items = engine.list_objects()

        max_scroll = max(0, len(items) - max_visible)
        if obj_list_scroll > max_scroll:
            obj_list_scroll = max_scroll

        start_idx = obj_list_scroll
        end_idx = min(start_idx + max_visible, len(items))

        for i in range(start_idx, end_idx):
            oid, info = items[i]
            entry_y = list_top + (i - start_idx) * entry_h
            if (i - start_idx) % 2 == 0:
                entry_bg = pygame.Surface((side_w - 30, entry_h - 4), pygame.SRCALPHA)
                entry_bg.fill((255, 255, 255, 15))
                screen.blit(entry_bg, (side_x + 15, entry_y))

            line = "ID {}  :  {}".format(oid, info["name"])
            draw_text(screen, line, font_msg, TEXT_COLOR, (side_x + 20, entry_y + 4))
            sample_n = info.get("samples", len(info.get("desc_files", [])))
            draw_text(screen, "{}  |  样本 {}".format(info.get("created_at", ""), sample_n),
                      font_small, DIM_TEXT, (side_x + 20, entry_y + 28))

            del_rect = pygame.Rect(side_x + side_w - 100, entry_y + 9, 80, 30)
            delete_btn_rects.append((oid, del_rect))
            del_hovered = del_rect.collidepoint(mouse_pos)
            del_color = (235, 87, 87, 200) if del_hovered else (235, 87, 87, 100)
            del_surf = pygame.Surface(del_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(del_surf, del_color, del_surf.get_rect(), border_radius=8)
            pygame.draw.rect(del_surf, EXIT_RED, del_surf.get_rect(), 2, border_radius=8)
            screen.blit(del_surf, del_rect.topleft)
            del_text = font_small.render("删除", True, WHITE)
            screen.blit(del_text, del_text.get_rect(center=del_rect.center))

        if not items:
            draw_text(screen, "（尚无物体，请先学习）", font_small, DIM_TEXT,
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
        hint = "ESC 退出 | 摄像头画面已整合到主窗口 | 鼠标滚轮可滚动物体库列表"
        draw_text(screen, hint, font_small, DIM_TEXT, (WIDTH // 2, HINT_Y), anchor="center")

        # =============================================================
        # 查看物体库详细信息弹窗
        # =============================================================
        if show_obj_detail:
            modal_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            modal_overlay.fill((0, 0, 0, 180))
            screen.blit(modal_overlay, (0, 0))

            modal_x, modal_y = WIDTH // 2 - 600, 130
            modal_w, modal_h = 1200, 820
            modal_panel = pygame.Surface((modal_w, modal_h), pygame.SRCALPHA)
            modal_panel.fill((30, 35, 50, 245))
            screen.blit(modal_panel, (modal_x, modal_y))
            pygame.draw.rect(screen, ACCENT, (modal_x, modal_y, modal_w, modal_h), 3, border_radius=12)

            all_items = engine.list_objects()
            draw_text(screen, "物体库详细信息", font_title, TEXT_COLOR,
                      (modal_x + 40, modal_y + 20), anchor="topleft")
            draw_text(screen, "共 {} 个    数据文件：{}".format(len(all_items), OBJECT_DB_FILE),
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
            for i, (oid, info) in enumerate(page_items):
                ey = entry_start_y + i * detail_entry_h
                if i > 0:
                    pygame.draw.line(screen, (255, 255, 255, 40),
                                     (modal_x + 40, ey), (modal_x + modal_w - 40, ey), 1)
                draw_text(screen, "物体 ID：{}".format(oid), font_label, ACCENT,
                          (modal_x + 40, ey + 8), anchor="topleft")
                draw_text(screen, "名称：{}".format(info.get("name", "")), font_label, TEXT_COLOR,
                          (modal_x + 300, ey + 8), anchor="topleft")
                draw_text(screen, "登记时间：{}    样本数：{}".format(
                    info.get("created_at", ""), info.get("samples", len(info.get("desc_files", [])))),
                    font_small, DIM_TEXT, (modal_x + 40, ey + 42), anchor="topleft")

            if not all_items:
                draw_text(screen, "物体库为空，请先学习物体", font_big_result, DIM_TEXT,
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

            obj_name = engine.get_name(delete_confirm_id) or ""
            draw_text(screen, "确认删除？", font_subtitle, EXIT_RED,
                      (WIDTH // 2, dlg_y + 25), anchor="midtop")
            draw_text(screen, "将删除：ID={}  名称={}".format(delete_confirm_id, obj_name),
                      font_msg, TEXT_COLOR, (WIDTH // 2, dlg_y + 90), anchor="center")
            draw_text(screen, "将同时删除其特征数据与样本图并重建识别索引",
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
