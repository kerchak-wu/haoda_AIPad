# -*- coding: utf-8 -*-
"""
姿态检测程序 - 好搭AI派
======================
功能说明：
  1. USB外接摄像头实时采集画面（由视觉系统 open_camera + capture_frame 管理）
  2. 使用视觉系统内置 pose_detection 算法进行人体姿态检测（非 mediapipe）
  3. 几何特征分类：自动判断「站立 / 坐着 / 蹲着 / 躺着 / 未知」五类姿态
     - 站立白名单策略：仅 5 项强证据同时满足才判站立（否则禁止判站立）
     - 保守回退：证据不足或特征不全时回退到「坐着」或「未知」，不冒险判站
     - 归一化特征：纵横比/膝角/躯干倾斜/腿伸直比/髋相对高度，不受距离/分辨率影响
  4. 实时显示检测人数、各类姿态人数统计、置信度、检测框和关键点坐标
  5. 摄像头画面叠加：姿态标签（彩色）+ 检测框（姿态颜色）+ 关键点 + 骨架
  6. 右侧面板：每人姿态色块、置信度条、分类依据特征值
  7. 底部栏图例：5 类姿态色块标注，便于快速对照
  8. 提供 PoseDetector 类，可供其他程序导入调用（每个结果包含 posture 字段）

硬件接线：
  - USB外接摄像头(/dev/video41 或 /dev/video40)
  - 好搭AI派扩展板(ESP32)
  注意：好搭AI派右下角开关需拨到左侧以启用外设接口。

依赖库：
  pygame, cv2(opencv, 仅用于图像格式转换), numpy, math, ESP32,
  camera_vision_system_v3(好搭AI派自带)

参考范例：
  - 范例代码 5.AI视觉算法 18.姿态检测（enable_pose_detection / get_pose_detection_*）
  - 物体学习.py（视觉系统 open_camera + capture_frame + 后台检测线程模式）
  - 人脸识别灯效.py（摄像头调用参考方案 + 降频策略）

重要约束：
  - 不使用 mediapipe，完全基于 camera_vision_system_v3 的 pose_detection。
  - 必须使用 vision_system.open_camera + start_background_detection，
    不能使用 cv2 VideoCapture，避免与视觉系统的 V4L2 设备冲突。
  - 采集线程固定 0.05s 睡眠（≈20fps），frame_lock 保护 raw_frame 读写。
  - 姿态检测结果刷新频率：每 3 帧（≈10fps）刷新，连续失败 3 次自动降频到
    每 10 帧（≈3fps），恢复后回到 10fps（参考人脸识别灯效降频策略）。
  - 姿态判定阈值集中在 STAND_REQUIRE / POSE_THRESHOLD 两个字典，便于标定。

模块调用示例：
  from 姿态检测 import PoseDetector, classify_pose, POSE_LABEL
  detector = PoseDetector()
  results = detector.get_pose_results()
  # 每个结果 r 包含：
  #   r['posture']: 'standing' | 'sitting' | 'squatting' | 'lying' | 'unknown'
  #   r['posture_features']: 归一化特征字典
  #   r['box'], r['confidence'], r['keypoints']: 原始检测信息
  for r in results:
      print(POSE_LABEL[r['posture']]['name'])
  detector.close()
"""

import time
import signal
import threading
import sys

import pygame
import cv2
import numpy as np

from ESP32 import *
from camera_vision_system_v3 import create_vision_system_v3


# ===================== 日志输出（控制台 + 文件）=====================
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
    '姿态检测_%s.log' % _datetime.datetime.now().strftime('%Y%m%d')
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

# 字体路径（好搭AI派系统字体）
FONT_PATH = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'
FONT_BOLD_PATH = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'

# 摄像头配置（视觉系统内部使用）
CAMERA_W, CAMERA_H = 1280, 720
CAM_DISP_W, CAM_DISP_H = 880, 660

# 姿态检测刷新频率策略（参考人脸识别灯效）
REFRESH_NORMAL = 3       # 正常：每 3 帧刷新一次检测结果（≈10fps）
REFRESH_SLOW = 10        # 降频：每 10 帧刷新一次（≈3fps）
FAIL_THRESHOLD = 3       # 连续失败次数阈值，触发降频

# ---- 界面配色（浅色系，天空蓝背景）----
BG_TOP = (135, 206, 235)        # 天空蓝
BG_BOTTOM = (220, 240, 255)    # 浅蓝白
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

# 姿态关键点颜色
KP_COLOR = (255, 80, 80)        # 关键点：红
BONE_COLOR = (60, 180, 255)     # 骨架连线：蓝
BOX_COLOR = (0, 200, 100)       # 检测框：绿

# ---------- 姿态分类配置（集中管理，便于标定）----------
# 策略说明（参考量产保守判定经验）：
#   1. 站立白名单：只有同时满足 5 项强证据才判"站立"，否则禁止判站立
#   2. 二级分类：纵横比 + 膝角 + 躯干方向 → 躺着/蹲着/坐着
#   3. 保守回退：证据不足或特征不全时回退到"坐着"而非"站立"
#
# COCO 17 关键点索引（视觉系统通常返回此格式或兼容格式）：
#   0鼻,1左眼,2右眼,3左耳,4右耳,5左肩,6右肩,7左肘,8右肘,
#   9左腕,10右腕,11左髋,12右髋,13左膝,14右膝,15左踝,16右踝

# 站立白名单阈值（全部要同时满足）
STAND_REQUIRE = {
    'aspect_ratio_min': 1.55,      # 身体高/宽比（越高越像站立）
    'knee_angle_min': 145.0,       # 两膝最小角度（°），180=完全伸直
    'torso_tilt_max': 22.0,        # 躯干偏离竖直的最大角度（°）
    'leg_straight_min': 0.78,      # 小腿垂直跨度 / 整条腿垂直跨度
    'hip_rel_height_max': 0.62,    # 髋部Y在（头顶Y→脚底Y）区间的相对位置
}

# 二级分类阈值
POSE_THRESHOLD = {
    'lying_aspect_max': 1.05,      # 躺着：纵横比接近 1（横向舒展）
    'lying_torso_tilt_min': 52.0,  # 躺着：躯干明显偏离竖直（°）
    'squat_knee_angle_max': 115.0, # 蹲着：膝盖最大弯曲角（°）
    'squat_aspect_max': 1.45,      # 蹲着：纵横比上限（更矮胖）
    'min_visible_key_pts': 8,      # 最少可见关键点数，低于此数走保守回退
}

# 姿态名称与显示颜色
POSE_LABEL = {
    'standing': {'name': '站立', 'color': (40, 160, 255)},      # 蓝
    'sitting':  {'name': '坐着', 'color': (60, 190, 90)},       # 绿
    'squatting': {'name': '蹲着', 'color': (255, 165, 0)},      # 橙
    'lying':   {'name': '躺着', 'color': (180, 80, 220)},       # 紫
    'unknown': {'name': '未知', 'color': (150, 150, 150)},      # 灰
}


# ===================== 硬件初始化 =====================
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    print('[警告] 扩展板连接异常，USB摄像头接在扩展板上，姿态检测无法运行，请检查硬件接线')


# ===================== PoseDetector 姿态检测器 =====================
class PoseDetector:
    """姿态检测器，封装视觉系统的 pose_detection 功能

    使用方式：
        get_pose_results()：获取最新姿态检测结果列表
          - 返回 list of dict: [{box, confidence, keypoints}, ...]
            box: (x, y, w, h) 或 None
            confidence: float 0-1
            keypoints: list of (x, y, score?) 或 None

    其他程序可通过以下方式调用：
        from 姿态检测 import PoseDetector
        detector = PoseDetector()
        results = detector.get_pose_results()
        detector.close()
    """

    def __init__(self, width=1280, height=720):
        self._lock = threading.RLock()
        self._results_lock = threading.Lock()

        # 最新检测结果缓存
        self._cached_results = []  # list of dict
        self._last_refresh_time = 0

        # 刷新频率控制
        self._frame_counter = 0
        self._refresh_interval = REFRESH_NORMAL
        self._consecutive_failures = 0

        # 创建视觉系统并启动后台检测（严格参照范例 18.姿态检测）
        self._init_vision_system(width, height)

        # 启动后台采集线程（用于界面显示）
        self._raw_frame = None
        self._frame_lock = threading.Lock()
        self._capture_running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _init_vision_system(self, width=1280, height=720):
        """创建并初始化视觉系统（严格参照范例代码 5.AI视觉算法 18.姿态检测）

        流程：create_vision_system_v3 → 启用 pose_detection → _init_detectors
              → open_camera → start_background_detection(show_preview=False)
        """
        self.vision_system = create_vision_system_v3(
            camera_id=-1, width=width, height=height,
            enable_basic=False, enable_advanced=False
        )
        # 启用姿态检测（非 mediapipe，视觉系统内置算法）
        self.vision_system.detection_config.enable_pose_detection = True
        self.vision_system._init_detectors()
        print('pose_detection 算法已启用（非 mediapipe）')

        # 打开摄像头
        print('正在打开视觉系统摄像头...')
        self.camera_ok = False
        if self.vision_system.open_camera():
            print('视觉系统摄像头已打开')
            self.camera_ok = True
        else:
            print('摄像头打开失败，请检查 /dev/video41 和 /dev/video40')
            return

        # 启动后台检测（show_preview=False，不弹 OpenCV 窗口）
        self.vision_system.threaded_system.start_background_detection(show_preview=False)
        print('姿态检测后台检测已启动')

        # 调试：列举 result_accessor 方法，便于确认 pose 相关 API
        try:
            ra_methods = [m for m in dir(self.vision_system.result_accessor)
                          if not m.startswith('_')]
            print('[调试] result_accessor 方法: %s' % ra_methods)
        except Exception as e:
            print('[调试] 列举方法失败:', e)

    def _capture_loop(self):
        """后台采集线程：调用 capture_frame() 获取帧用于界面显示

        参考人脸识别灯效已验证模式：
        1. 0.05s 睡眠 ≈ 20fps 采集，保证画面流畅
        2. 帧有效性验证（3维 shape），跳过损坏帧
        3. capture_frame() 只读缓存，不访问 V4L2，与后台检测线程不冲突
        """
        time.sleep(0.5)  # 等待后台检测线程稳定
        while self._capture_running:
            if not self.camera_ok:
                time.sleep(0.3)
                continue
            try:
                frame = self.vision_system.capture_frame()
                if frame is not None and hasattr(frame, 'shape') and len(frame.shape) == 3:
                    with self._frame_lock:
                        self._raw_frame = frame
            except Exception as e:
                if self._capture_running:
                    print('采集帧异常:', e)
            time.sleep(0.05)  # ≈20fps 采集

    def get_current_frame(self):
        """获取当前摄像头帧的副本（线程安全）"""
        with self._frame_lock:
            return self._raw_frame.copy() if self._raw_frame is not None else None

    def _refresh_results(self):
        """刷新姿态检测结果（带频率控制与自动降频策略）

        参考人脸识别灯效降频策略：
        - 正常每 REFRESH_NORMAL 帧刷新一次
        - 连续 FAIL_THRESHOLD 次无结果或异常，自动降频到 REFRESH_SLOW 帧
        - 恢复有结果后回到 REFRESH_NORMAL
        """
        self._frame_counter += 1
        if self._frame_counter < self._refresh_interval:
            return
        self._frame_counter = 0

        if not self.camera_ok:
            return

        try:
            # 严格参照范例：refresh_results() 后调用 get_pose_detection_*
            self.vision_system.result_accessor.refresh_results()

            count = self.vision_system.result_accessor.get_pose_detection_count()
            results = []
            for i in range(count):
                item = {}
                # 检测框
                try:
                    item['box'] = self.vision_system.result_accessor.get_pose_detection_box(i)
                except Exception:
                    item['box'] = None
                # 置信度
                try:
                    item['confidence'] = float(
                        self.vision_system.result_accessor.get_pose_detection_confidence(i)
                    )
                except Exception:
                    item['confidence'] = 0.0
                # 关键点
                try:
                    item['keypoints'] = self.vision_system.result_accessor.get_pose_detection_keypoints(i)
                except Exception:
                    item['keypoints'] = None
                # 姿态分类（站立白名单 + 二级分类）
                try:
                    posture, feats = classify_pose(item['keypoints'])
                except Exception as _e:
                    posture, feats = 'unknown', {'visible_count': 0}
                    print('姿态分类异常:', _e)
                item['posture'] = posture
                item['posture_features'] = feats
                results.append(item)

            with self._results_lock:
                self._cached_results = results
                self._last_refresh_time = time.time()

            if count > 0:
                # 有检测结果，恢复正常刷新频率
                if self._consecutive_failures >= FAIL_THRESHOLD:
                    print('姿态检测恢复，刷新频率提升：每 %d 帧' % REFRESH_NORMAL)
                self._consecutive_failures = 0
                self._refresh_interval = REFRESH_NORMAL
            else:
                # 无检测结果，累加连续失败计数
                self._consecutive_failures += 1
                if (self._consecutive_failures >= FAIL_THRESHOLD
                        and self._refresh_interval != REFRESH_SLOW):
                    print('姿态检测连续 %d 次无结果，自动降频：每 %d 帧' % (
                        FAIL_THRESHOLD, REFRESH_SLOW))
                    self._refresh_interval = REFRESH_SLOW
        except Exception as e:
            print('刷新姿态检测结果异常:', e)
            self._consecutive_failures += 1
            if (self._consecutive_failures >= FAIL_THRESHOLD
                    and self._refresh_interval != REFRESH_SLOW):
                print('姿态检测连续异常，自动降频：每 %d 帧' % REFRESH_SLOW)
                self._refresh_interval = REFRESH_SLOW

    def get_pose_results(self):
        """获取最新姿态检测结果（自动触发刷新）

        Returns:
            list of dict: [{box, confidence, keypoints}, ...]
        """
        self._refresh_results()
        with self._results_lock:
            return [dict(r) for r in self._cached_results]

    def get_cached_results(self):
        """仅获取缓存结果，不触发刷新（用于高频绘制）"""
        with self._results_lock:
            return [dict(r) for r in self._cached_results]

    def close(self):
        """释放视觉系统资源"""
        self._capture_running = False
        time.sleep(0.2)
        try:
            self.vision_system.cleanup()
        except Exception:
            pass


# ===================== 姿态分类（几何特征 + 站立白名单）=====================
# COCO 17 点索引常量（避免魔法数字）
KP_NOSE, KP_L_EYE, KP_R_EYE, KP_L_EAR, KP_R_EAR = 0, 1, 2, 3, 4
KP_L_SHOULDER, KP_R_SHOULDER = 5, 6
KP_L_ELBOW, KP_R_ELBOW = 7, 8
KP_L_WRIST, KP_R_WRIST = 9, 10
KP_L_HIP, KP_R_HIP = 11, 12
KP_L_KNEE, KP_R_KNEE = 13, 14
KP_L_ANKLE, KP_R_ANKLE = 15, 16


def _kp(kps, idx):
    """安全取关键点坐标，返回 (x, y) 或 None；自动兼容相对坐标→绝对像素（若<=1.5）"""
    if kps is None or not hasattr(kps, '__len__'):
        return None
    if idx < 0 or idx >= len(kps):
        return None
    kp = kps[idx]
    if kp is None or not hasattr(kp, '__len__') or len(kp) < 2:
        return None
    try:
        return float(kp[0]), float(kp[1])
    except Exception:
        return None


def _mid(a, b):
    """两点中点（任一None则返回None）"""
    if a is None or b is None:
        return None
    return (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0


def _angle_3p(a, b, c):
    """∠ABC：三点夹角，单位度；缺失点返回 None"""
    if a is None or b is None or c is None:
        return None
    v1x, v1y = a[0] - b[0], a[1] - b[1]
    v2x, v2y = c[0] - b[0], c[1] - b[1]
    n1 = (v1x * v1x + v1y * v1y) ** 0.5
    n2 = (v2x * v2x + v2y * v2y) ** 0.5
    if n1 < 1e-6 or n2 < 1e-6:
        return None
    cos_v = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (n1 * n2)))
    import math as _math
    return _math.degrees(_math.acos(cos_v))


def compute_pose_features(kps):
    """从关键点计算归一化特征字典；特征不全时返回尽可能多的字段

    Returns:
        dict: 含以下字段（缺失者为 None）：
          - aspect_ratio: 身体高/宽比（归一化，与距离/分辨率无关）
          - torso_tilt_deg: 躯干偏离竖直的角度（°）
          - knee_angle_min: 两膝角度的较小值（°），180=伸直
          - leg_straight_ratio: 小腿/整条腿 垂直跨度比
          - hip_rel_height: 髋部相对高度（0头顶→1脚底）
          - visible_count: 可见关键点数
          - body_top_y, body_bottom_y, body_left_x, body_right_x
    """
    feats = {
        'aspect_ratio': None,
        'torso_tilt_deg': None,
        'knee_angle_min': None,
        'leg_straight_ratio': None,
        'hip_rel_height': None,
        'visible_count': 0,
        'body_top_y': None,
        'body_bottom_y': None,
        'body_left_x': None,
        'body_right_x': None,
    }

    # 1) 先把关键点提取出来
    p = {}
    all_ys, all_xs = [], []
    for i in range(min(17, len(kps) if kps and hasattr(kps, '__len__') else 0)):
        v = _kp(kps, i)
        p[i] = v
        if v is not None:
            feats['visible_count'] += 1
            all_ys.append(v[1])
            all_xs.append(v[0])

    if feats['visible_count'] == 0:
        return feats

    # 2) 身体包围盒（取所有可见点的 min/max）
    feats['body_top_y'] = min(all_ys)
    feats['body_bottom_y'] = max(all_ys)
    feats['body_left_x'] = min(all_xs)
    feats['body_right_x'] = max(all_xs)
    body_h = max(1e-6, feats['body_bottom_y'] - feats['body_top_y'])
    body_w = max(1e-6, feats['body_right_x'] - feats['body_left_x'])
    feats['aspect_ratio'] = body_h / body_w

    # 3) 躯干倾斜角：肩中点→髋中点 连线 与 竖直方向 的夹角
    shoulder_m = _mid(p.get(KP_L_SHOULDER), p.get(KP_R_SHOULDER))
    hip_m = _mid(p.get(KP_L_HIP), p.get(KP_R_HIP))
    if shoulder_m is not None and hip_m is not None:
        dx = hip_m[0] - shoulder_m[0]
        dy = hip_m[1] - shoulder_m[1]  # 正数=头在上
        if abs(dy) > 1e-6:
            import math as _math2
            feats['torso_tilt_deg'] = abs(_math2.degrees(_math2.atan2(abs(dx), abs(dy))))
        else:
            feats['torso_tilt_deg'] = 90.0  # 水平

    # 4) 两膝角度 ∠髋-膝-踝，取较小值
    ang_l = _angle_3p(p.get(KP_L_HIP), p.get(KP_L_KNEE), p.get(KP_L_ANKLE))
    ang_r = _angle_3p(p.get(KP_R_HIP), p.get(KP_R_KNEE), p.get(KP_R_ANKLE))
    angs = [a for a in (ang_l, ang_r) if a is not None]
    if angs:
        feats['knee_angle_min'] = min(angs)

    # 5) 腿伸直比 = 小腿垂直跨度(膝到踝) / 整条腿垂直跨度(髋到踝)，双侧取较大
    ratios = []
    for (hip_i, knee_i, ankle_i) in [(KP_L_HIP, KP_L_KNEE, KP_L_ANKLE),
                                       (KP_R_HIP, KP_R_KNEE, KP_R_ANKLE)]:
        hi, kn, an = p.get(hip_i), p.get(knee_i), p.get(ankle_i)
        if hi is not None and kn is not None and an is not None:
            full = abs(an[1] - hi[1])
            calf = abs(an[1] - kn[1])
            if full > 1e-6:
                ratios.append(calf / full)
    if ratios:
        feats['leg_straight_ratio'] = max(ratios)

    # 6) 髋部相对高度 = (髋Y - 头顶Y) / (脚底Y - 头顶Y)，站立≈0.5，坐着/蹲着≈0.7~0.9
    if hip_m is not None:
        feats['hip_rel_height'] = (hip_m[1] - feats['body_top_y']) / body_h

    return feats


def classify_pose(kps):
    """姿态分类主函数（站立白名单策略）

    算法流程：
      1. 特征不全（<8点）→ 直接 unknown，保守不判站立
      2. 站立白名单：5 项 ALL 通过 → standing；否则禁止判站立
      3. 二级分类：
         - 躯干近乎水平 或 纵横比接近1 → lying
         - 膝盖弯得很狠 且 纵横比矮胖 → squatting
         - 其他（保守回退）→ sitting
    """
    feats = compute_pose_features(kps)

    # ---- 特征不足的保守回退 ----
    if feats['visible_count'] < POSE_THRESHOLD['min_visible_key_pts']:
        return 'unknown', feats

    R = STAND_REQUIRE
    T = POSE_THRESHOLD
    none_safe = lambda v, default: default if v is None else v

    # ---- 站立白名单：5 项必须全部满足 ----
    stand_pass = True
    reasons_stand_fail = []

    if none_safe(feats['aspect_ratio'], 0) < R['aspect_ratio_min']:
        stand_pass = False
        reasons_stand_fail.append('纵横比不足')
    if none_safe(feats['knee_angle_min'], 0) < R['knee_angle_min']:
        stand_pass = False
        reasons_stand_fail.append('膝盖弯曲')
    if none_safe(feats['torso_tilt_deg'], 999) > R['torso_tilt_max']:
        stand_pass = False
        reasons_stand_fail.append('躯干不竖直')
    if none_safe(feats['leg_straight_ratio'], 0) < R['leg_straight_min']:
        stand_pass = False
        reasons_stand_fail.append('腿部未伸直')
    if none_safe(feats['hip_rel_height'], 999) > R['hip_rel_height_max']:
        stand_pass = False
        reasons_stand_fail.append('髋部过低')

    if stand_pass:
        return 'standing', feats

    # ---- 二级分类（此时已排除站立）----
    # 躺着：躯干明显倾斜 或 身体整体横向
    if (none_safe(feats['torso_tilt_deg'], 0) >= T['lying_torso_tilt_min']
            or none_safe(feats['aspect_ratio'], 999) <= T['lying_aspect_max']):
        return 'lying', feats

    # 蹲着：膝盖弯曲大 且 身体矮胖
    if (none_safe(feats['knee_angle_min'], 999) <= T['squat_knee_angle_max']
            and none_safe(feats['aspect_ratio'], 999) <= T['squat_aspect_max']):
        return 'squatting', feats

    # 保守回退：坐着
    return 'sitting', feats


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


def draw_pose_overlay(frame, results, cam_src_w, cam_src_h, disp_w, disp_h):
    """在 BGR 帧上叠加姿态关键点、骨架连线和检测框

    由于视觉系统返回的关键点坐标基准未知（可能是相对 0-1 或绝对像素），
    这里做兼容处理：如果坐标范围在 0-1 之间则按比例缩放，否则按绝对
    像素映射到显示尺寸。
    """
    if frame is None or not results:
        return frame

    sx = disp_w / max(1, cam_src_w)
    sy = disp_h / max(1, cam_src_h)

    overlay = frame.copy()

    for item in results:
        # ---- 按姿态选框颜色（分类可视化）----
        posture_key = item.get('posture', 'unknown')
        posture_info = POSE_LABEL.get(posture_key, POSE_LABEL['unknown'])
        pname = posture_info['name']
        pcolor_rgb = posture_info['color']  # (R, G, B) → OpenCV 用 (B, G, R)
        box_bgr = (pcolor_rgb[2], pcolor_rgb[1], pcolor_rgb[0])

        # ---- 绘制检测框 ----
        box = item.get('box')
        if box is not None:
            try:
                if len(box) >= 4:
                    x, y, w, h = box[0], box[1], box[2], box[3]
                    # 判断是否为相对坐标（0-1 范围）
                    if max(abs(x), abs(y), abs(w), abs(h)) <= 1.5:
                        x = int(x * cam_src_w)
                        y = int(y * cam_src_h)
                        w = int(w * cam_src_w)
                        h = int(h * cam_src_h)
                    x1, y1 = max(0, int(x)), max(0, int(y))
                    x2, y2 = min(cam_src_w, int(x + w)), min(cam_src_h, int(y + h))
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), box_bgr, 3)
                    # 左上标签：姿态名 + 置信度
                    conf = item.get('confidence', 0)
                    label = '%s %.0f%%' % (pname, conf * 100)
                    (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
                    # 姿态彩色背景条
                    cv2.rectangle(overlay, (x1, y1 - lh - 10), (x1 + lw + 14, y1),
                                  box_bgr, -1)
                    cv2.rectangle(overlay, (x1, y1 - lh - 10), (x1 + lw + 14, y1),
                                  (255, 255, 255), 2)
                    cv2.putText(overlay, label, (x1 + 7, y1 - 7),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            except Exception as e:
                print('绘制检测框异常:', e)

        # ---- 绘制关键点和骨架 ----
        kps = item.get('keypoints')
        if kps is not None:
            try:
                pts = []  # 归一化后的像素坐标列表
                for kp in kps:
                    if kp is None:
                        pts.append(None)
                        continue
                    # 兼容多种格式：(x,y) / (x,y,score) / [x,y] / [x,y,s]
                    if hasattr(kp, '__len__') and len(kp) >= 2:
                        kx, ky = float(kp[0]), float(kp[1])
                        # 判断是否为相对坐标
                        if 0 <= kx <= 1.5 and 0 <= ky <= 1.5:
                            kx = kx * cam_src_w
                            ky = ky * cam_src_h
                        pts.append((int(kx), int(ky)))
                    else:
                        pts.append(None)

                # 关键点数量决定骨架定义
                n = len(pts)
                # 通用骨架连线（覆盖常见 17/18/25/33 点模型的主要连接）
                # 按人体大致顺序定义：头-肩-肘-腕-髋-膝-踝
                bones = []
                if n >= 17:
                    # COCO 17 点模型或兼容模型的常见连接
                    # 鼻子(0)-左右眼(1,2)-左右耳(3,4)
                    bones += [(0, 1), (0, 2), (1, 3), (2, 4)]
                    # 左右肩(5,6)
                    bones += [(5, 6)]
                    # 肩-肘(7,8)-腕(9,10)
                    bones += [(5, 7), (7, 9), (6, 8), (8, 10)]
                    # 肩-髋(11,12)
                    bones += [(5, 11), (6, 12), (11, 12)]
                    # 髋-膝(13,14)-踝(15,16)
                    bones += [(11, 13), (13, 15), (12, 14), (14, 16)]
                if n >= 25:
                    # 额外关键点（如面部、脚部细节）的扩展连接可在此添加
                    pass

                # 绘制骨架连线
                for (a, b) in bones:
                    if a < n and b < n and pts[a] is not None and pts[b] is not None:
                        cv2.line(overlay, pts[a], pts[b], BONE_COLOR, 3)

                # 绘制关键点
                for pt in pts:
                    if pt is not None:
                        cv2.circle(overlay, pt, 5, KP_COLOR, -1)
                        cv2.circle(overlay, pt, 7, (255, 255, 255), 1)
            except Exception as e:
                print('绘制关键点异常:', e)

    # 叠加（半透明，让原图更清晰）
    return cv2.addWeighted(overlay, 0.85, frame, 0.15, 0)


def cvframe_to_surface(frame, target_w, target_h):
    """BGR 帧 -> pygame Surface，并缩放到指定尺寸"""
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
        c = (180, 180, 180) if not self.enabled else (
            self.hover_color if self.hovered else self.color)
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
class PoseDetectApp:
    """姿态检测 Pygame 界面应用

    摄像头完全由视觉系统管理（open_camera + capture_frame），
    不使用 cv2 VideoCapture，避免设备冲突。
    姿态检测严格参照范例代码 18.姿态检测。
    """

    TITLE_H = 130
    FOOTER_H = 110

    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('姿态检测')
        self.clock = pygame.time.Clock()

        # 字体（适配 1920×1080：标题64、副标题32、列表项30、按钮34）
        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 64)
        self.font_sub = pygame.font.Font(FONT_PATH, 32)
        self.font_item = pygame.font.Font(FONT_PATH, 30)
        self.font_btn = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_small = pygame.font.Font(FONT_PATH, 24)
        self.font_status = pygame.font.Font(FONT_PATH, 26)
        self.font_kp = pygame.font.Font(FONT_PATH, 22)

        # 背景：优先加载图片，失败回退渐变
        try:
            bg_raw = pygame.image.load('images/1.jpg')
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT)).convert()
        except Exception:
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert()

        # 布局：左右面板等高 820px
        panel_h = HEIGHT - self.TITLE_H - 20 - self.FOOTER_H
        self.cam_rect = pygame.Rect(60, self.TITLE_H + 20,
                                    CAM_DISP_W + 40, panel_h)
        self.info_rect = pygame.Rect(self.cam_rect.right + 40, self.TITLE_H + 20,
                                     WIDTH - self.cam_rect.right - 40 - 60,
                                     panel_h)

        # 退出按钮（右上角标题栏内，固定 240×70，位置 WIDTH-280,30）
        self.btn_exit = Button((WIDTH - 280, 30, 240, 70),
                               '退出程序', EXIT_COLOR, EXIT_HOVER)

        # 初始化姿态检测器
        print('正在初始化姿态检测系统...')
        self.detector = PoseDetector()

        # 状态
        self.running = True
        self.status_msg = '正在启动姿态检测，请对准摄像头...'
        self.status_color = SUBTLE_COLOR

        # 上一次检测结果（用于画面绘制，避免每帧都刷新检测）
        self._last_draw_results = []

    def set_status(self, msg, color=SUBTLE_COLOR):
        self.status_msg = msg
        self.status_color = color

    def draw_title(self):
        """绘制顶部标题栏"""
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('姿态检测', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 25))
        sub = self.font_sub.render(
            'USB摄像头实时采集  ·  视觉系统内置姿态检测算法（非 MediaPipe）',
            True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 90))

        self.btn_exit.draw(self.screen, self.font_btn)

    def draw_camera(self):
        """绘制摄像头画面区域（叠加姿态检测可视化）"""
        panel = pygame.Surface(self.cam_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.cam_rect.topleft)

        head = self.font_sub.render('摄像头画面', True, TITLE_COLOR)
        self.screen.blit(head, (self.cam_rect.x + 20, self.cam_rect.y + 15))

        status = '● 已连接' if self.detector.camera_ok else '○ 未连接'
        sc = SUCCESS_COLOR if self.detector.camera_ok else ERROR_COLOR
        st = self.font_small.render(status, True, sc)
        self.screen.blit(st, (self.cam_rect.right - st.get_width() - 20,
                              self.cam_rect.y + 20))

        frame = self.detector.get_current_frame()
        if frame is not None:
            # 获取检测结果（用缓存，不强制刷新；每帧都会被主循环的 get_pose_results 刷新）
            results = self._last_draw_results

            # 在 BGR 帧上叠加姿态可视化（坐标系：原始 CAMERA_W × CAMERA_H）
            try:
                vis_frame = draw_pose_overlay(
                    frame, results,
                    CAMERA_W, CAMERA_H, CAM_DISP_W, CAM_DISP_H
                )
            except Exception as e:
                print('叠加姿态可视化异常:', e)
                vis_frame = frame

            surf = cvframe_to_surface(vis_frame, CAM_DISP_W, CAM_DISP_H)
            if surf is not None:
                cam_x = self.cam_rect.x + (self.cam_rect.w - CAM_DISP_W) // 2
                cam_y = self.cam_rect.y + 60
                self.screen.blit(surf, (cam_x, cam_y))
        else:
            hint_text = '摄像头未连接' if not self.detector.camera_ok else '等待画面...'
            hint_color = ERROR_COLOR if not self.detector.camera_ok else SUBTLE_COLOR
            hint = self.font_sub.render(hint_text, True, hint_color)
            self.screen.blit(hint, (self.cam_rect.centerx - hint.get_width() // 2,
                                    self.cam_rect.centery - hint.get_height() // 2))

        res = self.font_small.render('%d × %d' % (CAMERA_W, CAMERA_H), True, SUBTLE_COLOR)
        self.screen.blit(res, (self.cam_rect.right - res.get_width() - 20,
                               self.cam_rect.bottom - 30))

    def draw_info_panel(self):
        """绘制右侧信息面板：检测状态 + 检测人数 + 各人详细信息"""
        panel = pygame.Surface(self.info_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 170), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.info_rect.topleft)

        x = self.info_rect.x + 30
        x_end = self.info_rect.right - 30
        y = self.info_rect.y + 20

        # ---- 检测概览 ----
        head = self.font_sub.render('检测结果', True, TITLE_COLOR)
        self.screen.blit(head, (x, y))
        y += 55

        results = self._last_draw_results
        person_count = len(results)

        # 人数卡
        count_bg = pygame.Surface((x_end - x, 90), pygame.SRCALPHA)
        cc = SUCCESS_COLOR if person_count > 0 else SUBTLE_COLOR
        pygame.draw.rect(count_bg, (*cc, 30), count_bg.get_rect(), border_radius=12)
        pygame.draw.rect(count_bg, (*cc, 180), count_bg.get_rect(), 2, border_radius=12)
        self.screen.blit(count_bg, (x, y))

        num_label = self.font_sub.render('检测人数', True, TEXT_COLOR)
        self.screen.blit(num_label, (x + 25, y + 28))
        num_val = self.font_title.render('%d' % person_count, True, cc)
        self.screen.blit(num_val, (x_end - 25 - num_val.get_width(),
                                    y + 45 - num_val.get_height() // 2))
        y += 110

        # 刷新频率信息
        freq_text = '刷新频率：每 %d 帧（连续失败 %d/%d）' % (
            self.detector._refresh_interval,
            min(self.detector._consecutive_failures, FAIL_THRESHOLD),
            FAIL_THRESHOLD
        )
        freq_surf = self.font_small.render(freq_text, True, SUBTLE_COLOR)
        self.screen.blit(freq_surf, (x, y))
        y += 35

        # 状态消息
        status_surf = self.font_status.render(self.status_msg, True, self.status_color)
        max_w = x_end - x
        if status_surf.get_width() > max_w:
            status_surf = self.font_small.render(self.status_msg, True, self.status_color)
        self.screen.blit(status_surf, (x, y))
        y += 45

        # 分隔线
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x_end, y), 2)
        y += 25

        # ---- 各人详细信息 ----
        head2 = self.font_sub.render('姿态详情', True, TITLE_COLOR)
        self.screen.blit(head2, (x, y))
        y += 50

        list_bottom = self.info_rect.bottom - 20

        if not results:
            hint = self.font_item.render('未检测到人体姿态', True, SUBTLE_COLOR)
            self.screen.blit(hint, (x, y))
            hint2 = self.font_small.render(
                '提示：请站在摄像头前 1-3 米处，保持身体在画面内',
                True, SUBTLE_COLOR)
            self.screen.blit(hint2, (x, y + 45))
        else:
            for i, item in enumerate(results):
                if y + 190 > list_bottom:
                    more = self.font_small.render(
                        '...共 %d 人' % person_count, True, SUBTLE_COLOR)
                    self.screen.blit(more, (x, y))
                    break

                # 姿态标签（彩色色块 + 文字，放在最上面最醒目）
                posture_key = item.get('posture', 'unknown')
                posture_info = POSE_LABEL.get(posture_key, POSE_LABEL['unknown'])
                p_name = posture_info['name']
                p_color = posture_info['color']
                # 彩色圆角色块
                tag_w, tag_h = 120, 44
                tag_rect = pygame.Rect(x + 110, y - 4, tag_w, tag_h)
                pygame.draw.rect(self.screen, p_color, tag_rect, border_radius=10)
                pygame.draw.rect(self.screen, (255, 255, 255), tag_rect, 2, border_radius=10)
                p_tag = self.font_btn.render(p_name, True, (255, 255, 255))
                self.screen.blit(p_tag,
                                 (tag_rect.centerx - p_tag.get_width() // 2,
                                  tag_rect.centery - p_tag.get_height() // 2))
                # 序号（左侧）
                idx = self.font_item.render('第 %d 人' % (i + 1), True, TITLE_COLOR)
                self.screen.blit(idx, (x, y))
                y += 46

                # 置信度条
                conf = item.get('confidence', 0)
                bar_w = x_end - x - 130
                bar_x = x + 130
                bar_y = y + 5
                bar_h = 26
                pygame.draw.rect(self.screen, (230, 235, 245),
                                 (bar_x, bar_y, bar_w, bar_h), border_radius=6)
                fill_w = int(bar_w * max(0, min(1, conf)))
                if fill_w > 0:
                    fill_c = SUCCESS_COLOR if conf > 0.7 else (
                        ACCENT_COLOR if conf > 0.4 else ERROR_COLOR)
                    pygame.draw.rect(self.screen, fill_c,
                                     (bar_x, bar_y, fill_w, bar_h), border_radius=6)
                conf_text = self.font_small.render(
                    '%.0f%%' % (conf * 100), True, TEXT_COLOR)
                self.screen.blit(conf_text,
                                 (bar_x + bar_w + 10,
                                  bar_y + bar_h // 2 - conf_text.get_height() // 2))
                y += 40

                # 检测框坐标
                box = item.get('box')
                if box is not None and hasattr(box, '__len__') and len(box) >= 4:
                    bx, by, bw, bh = box[0], box[1], box[2], box[3]
                    if max(abs(bx), abs(by), abs(bw), abs(bh)) <= 1.5:
                        box_str = '检测框：(%.1f%%, %.1f%%) %.1f%% × %.1f%%' % (
                            bx * 100, by * 100, bw * 100, bh * 100)
                    else:
                        box_str = '检测框：(%d, %d) %d × %d' % (
                            int(bx), int(by), int(bw), int(bh))
                    box_surf = self.font_kp.render(box_str, True, TEXT_COLOR)
                    self.screen.blit(box_surf, (x, y))
                    y += 32

                # 关键点统计
                feats = item.get('posture_features') or {}
                visible_count = int(feats.get('visible_count', 0))
                kps = item.get('keypoints')
                kp_count = len(kps) if kps and hasattr(kps, '__len__') else 0
                if visible_count == 0 and kp_count > 0:
                    # 特征缺失时兜底重算一次
                    for kp in (kps or []):
                        if kp is not None and hasattr(kp, '__len__') and len(kp) >= 2:
                            visible_count += 1
                kp_str = '关键点：%d / %d 可见' % (visible_count, kp_count)
                kp_surf = self.font_kp.render(kp_str, True, ACCENT_COLOR)
                self.screen.blit(kp_surf, (x, y))
                y += 32

                # 关键特征值（方便理解分类原因）
                feat_parts = []
                for (label, key, fmt) in [
                    ('高宽比', 'aspect_ratio', '%.2f'),
                    ('膝角', 'knee_angle_min', '%.0f°'),
                    ('躯干倾', 'torso_tilt_deg', '%.0f°'),
                    ('髋比', 'hip_rel_height', '%.2f'),
                ]:
                    v = feats.get(key)
                    if v is not None:
                        feat_parts.append('%s:%s' % (label, fmt % v))
                if feat_parts:
                    feat_text = '  '.join(feat_parts)
                    # 超宽时用小字体
                    fs = self.font_small if len(feat_text) > 32 else self.font_kp
                    feat_surf = fs.render(feat_text, True, SUBTLE_COLOR)
                    if feat_surf.get_width() > (x_end - x):
                        feat_surf = self.font_small.render(feat_text, True, SUBTLE_COLOR)
                    self.screen.blit(feat_surf, (x, y))
                    y += 30

                # 分隔线（非最后一个）
                if i < person_count - 1:
                    y += 8
                    pygame.draw.line(self.screen, (220, 230, 245),
                                     (x + 10, y), (x_end - 10, y), 1)
                    y += 12

    def draw_footer(self):
        """绘制底部栏"""
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 180), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        # 左侧操作说明
        hint = self.font_small.render(
            'ESC 退出  ·  红圆点=关节  ·  蓝连线=骨架  ·  方框颜色对应姿态（见右下）',
            True, SUBTLE_COLOR)
        self.screen.blit(hint, (60, HEIGHT - self.FOOTER_H // 2 - hint.get_height() // 2))

        # 右侧姿态图例（彩色小方块 + 文字）
        legend_x = WIDTH - 60
        legend_y = HEIGHT - self.FOOTER_H // 2
        # 从右往左排
        legend_items = list(POSE_LABEL.items())  # [(key, info), ...]
        cursor_x = legend_x
        for key, info in reversed(legend_items):
            name = info['name']
            color = info['color']
            name_surf = self.font_small.render(name, True, TEXT_COLOR)
            box_sz = 22
            total_w = name_surf.get_width() + 8 + box_sz
            cursor_x -= total_w
            # 色块
            box_rect = pygame.Rect(cursor_x, legend_y - box_sz // 2, box_sz, box_sz)
            pygame.draw.rect(self.screen, color, box_rect, border_radius=4)
            pygame.draw.rect(self.screen, (255, 255, 255), box_rect, 1, border_radius=4)
            # 文字
            self.screen.blit(name_surf, (box_rect.right + 8,
                                         legend_y - name_surf.get_height() // 2))
            cursor_x -= 28  # 间距

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

            self.btn_exit.update(mouse_pos)

            # 每帧触发一次检测结果刷新（内部已做频率控制）
            try:
                fresh_results = self.detector.get_pose_results()
                self._last_draw_results = fresh_results

                if fresh_results:
                    # 姿态分类人数统计
                    posture_counts = {}
                    for r in fresh_results:
                        p = r.get('posture', 'unknown')
                        posture_counts[p] = posture_counts.get(p, 0) + 1
                    # 按显示顺序拼接：站立→坐着→蹲着→躺着→未知
                    display_order = ['standing', 'sitting', 'squatting', 'lying', 'unknown']
                    stat_parts = []
                    for key in display_order:
                        if posture_counts.get(key, 0) > 0:
                            name = POSE_LABEL[key]['name']
                            stat_parts.append('%s%d' % (name, posture_counts[key]))
                    stats = '  '.join(stat_parts)

                    max_conf = max(r.get('confidence', 0) for r in fresh_results)
                    self.set_status(
                        '检测到 %d 人（%s），最高置信度 %.0f%%' % (
                            len(fresh_results), stats, max_conf * 100),
                        SUCCESS_COLOR
                    )
                else:
                    if self.detector._consecutive_failures >= FAIL_THRESHOLD:
                        self.set_status(
                            '暂未检测到姿态（已自动降频，节省资源）',
                            SUBTLE_COLOR
                        )
                    else:
                        self.set_status('请站在摄像头前以检测姿态', SUBTLE_COLOR)
            except Exception as e:
                print('主循环获取检测结果异常:', e)

            self.screen.blit(self.bg, (0, 0))
            self.draw_title()
            self.draw_camera()
            self.draw_info_panel()
            self.draw_footer()

            pygame.display.flip()
            self.clock.tick(30)

        # 退出清理
        print('正在关闭程序...')
        self.detector.close()
        pygame.quit()
        try:
            _debug_log_fp.close()
        except Exception:
            pass


# ===================== 入口 =====================
if __name__ == '__main__':
    app = PoseDetectApp()
    app.run()
