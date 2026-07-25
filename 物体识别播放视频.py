# -*- coding: utf-8 -*-
"""
物体识别触发视频播放程序
================================================================
参考：物体学习.py（ObjectEngine 引擎）与 人脸识别播放视频.py 的视频播放逻辑

功能：
  实时识别摄像头画面中的物体，识别到指定物体后自动播放对应视频：
    识别到 card （卡片）  → 播放 1.mp4
    识别到 book （书本）  → 播放 2.mp4
    识别到 cup  （杯子）  → 播放 3.mp4

  - 视频在主窗口内播放（OpenCV 解码 + pygame 显示），音频用 ffplay 后台播放
  - 视频播放结束或按 ESC 返回识别模式
  - 同一物体播放后不会立即重复触发，需离开画面再出现才会再次播放

前置条件：
  1. 已通过 物体学习.py 学习登记了 card / book / cup 三个物体
     （姓名可用拼音或中文，程序自动匹配，不区分大小写）
  2. 当前目录下存在 1.mp4 / 2.mp4 / 3.mp4 视频文件（放在 videos/ 目录）
  3. 摄像头节点为 /dev/video41 或 /dev/video40（可在 open_camera 修改）

运行：
  python3 物体识别播放视频.py
"""

import os
import sys
import time
import signal
import threading
import subprocess

import pygame
import cv2
import numpy as np

from 物体学习 import (
    ObjectEngine,
    GOOD_MATCH_THRESHOLD,
    find_chinese_font,
    draw_text,
    Button,
)

# ===========================================================================
# 配置
# ===========================================================================
WIDTH, HEIGHT = 1920, 1080
BG_IMAGE = os.path.join("images", "1.jpg")

# 视频文件所在目录
VIDEO_DIR = "videos"

# 物体名称 -> 视频文件 映射（拼音 / 中文 均可，匹配时不区分大小写）
# 文件会从 VIDEO_DIR 目录下查找
OBJECT_VIDEO_MAP = {
    "card": "1.mp4",
    "卡片": "1.mp4",
    "book": "2.mp4",
    "书本": "2.mp4",
    "cup":  "3.mp4",
    "杯子": "3.mp4",
}

# 摄像头
CAMERA_W, CAMERA_H = 1280, 720
CAM_DISP_W, CAM_DISP_H = 1100, 520

# 识别 / 触发参数
RECOG_THRESHOLD = GOOD_MATCH_THRESHOLD   # 与 物体学习.py 一致（优质匹配数阈值）
CONFIRM_FRAMES = 3                       # 连续命中多少帧才触发，避免误触

# 模式
MODE_RECOGNIZE = "recognize"
MODE_VIDEO = "video"

# 颜色
TEXT_COLOR = (255, 255, 255)
DIM_TEXT = (200, 200, 200)
ACCENT = (86, 196, 255)
SUCCESS = (130, 255, 170)
WARN = (255, 200, 120)
ERROR = (255, 120, 120)
OBJ_BOX_KNOWN = (130, 255, 170)
OBJ_BOX_UNKNOWN = (255, 200, 120)
OBJ_BOX_OTHER = (180, 180, 180)


# ===========================================================================
# 摄像头打开（复用 物体学习.py 的探测逻辑：MJPG + 超时 + 雪花检测）
# ===========================================================================
class _CameraProbeTimeout(Exception):
    """探测摄像头时 SIGALRM 超时（用于打断卡在 select() 的 V4L2 设备）。"""
    pass


def _is_valid_frame(frame):
    """判断帧是否为有效画面（非空、非全黑、非雪花噪声）。"""
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
        # 直接用设备节点路径打开，避免把整数 cid 当成 V4L2 索引导致越界
        # （系统设备列表通常只有 32 项，cid=41 会被判为索引越界）
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
    # 摄像头固定为 /dev/video41（优先）或 /dev/video40
    for cid in (41, 40):
        print("  探测 /dev/video{} ...".format(cid))
        cap = _try_open_camera(cid)
        if cap is not None:
            print("摄像头使用编号：{} (/dev/video{})".format(cid, cid))
            return cap
    return None


# ===========================================================================
# 工具
# ===========================================================================
def lookup_video(name):
    """根据识别到的物体名称查找对应视频文件，找不到返回 None。

    返回的路径为 VIDEO_DIR 下的完整相对路径（如 videos/1.mp4）。
    """
    if not name:
        return None
    key = name.strip().lower()
    fname = OBJECT_VIDEO_MAP.get(key)
    if not fname:
        return None
    return os.path.join(VIDEO_DIR, fname)


def find_ffplay():
    """查找系统中的 ffplay 可执行文件，找不到返回 None。"""
    for name in ("ffplay", "ffplay.exe"):
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if not d:
                continue
            p = os.path.join(d, name)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def cvframe_to_surface(frame, target_w, target_h):
    """OpenCV BGR 帧 -> pygame Surface，并缩放到指定尺寸。"""
    if frame is None:
        return None
    try:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        transposed = np.transpose(rgb, (1, 0, 2))
        surf = pygame.surfarray.make_surface(transposed)
        return pygame.transform.smoothscale(surf, (target_w, target_h))
    except Exception:
        return None


def fit_surface(surf, max_w, max_h):
    """等比缩放 Surface 使其尽量填满 max_w×max_h 区域。"""
    sw, sh = surf.get_size()
    if sw <= 0 or sh <= 0:
        return surf
    scale = min(max_w / sw, max_h / sh)
    new_w = max(1, int(sw * scale))
    new_h = max(1, int(sh * scale))
    return pygame.transform.smoothscale(surf, (new_w, new_h))


# ===========================================================================
# 主程序
# ===========================================================================
def main():
    # 只初始化 display + font，不调用 pygame.init()，避免 pygame.mixer 占用音频设备
    # 导致 ffplay 无法播放视频声音
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("物体识别触发视频播放")
    clock = pygame.time.Clock()

    font_name = find_chinese_font()
    font_title = pygame.font.SysFont(font_name, 48, bold=True)
    font_subtitle = pygame.font.SysFont(font_name, 32, bold=True)
    font_msg = pygame.font.SysFont(font_name, 26)
    font_small = pygame.font.SysFont(font_name, 22)
    font_exit = pygame.font.SysFont(font_name, 24, bold=True)
    font_big = pygame.font.SysFont(font_name, 42, bold=True)
    font_box = pygame.font.SysFont(font_name, 24, bold=True)

    # 背景图
    background = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print("背景加载失败: {}".format(e))

    # ----- 物体引擎 -----
    print("物体引擎初始化中...")
    engine = ObjectEngine(threshold=RECOG_THRESHOLD)
    print("物体库已加载：共 {} 个物体".format(engine.count()))
    for oid, info in engine.list_objects():
        print("  ID={}  名称={}".format(oid, info.get("name")))

    # 检查视频文件
    print("检查视频文件（目录 {}）：".format(VIDEO_DIR))
    for vf in sorted(set(OBJECT_VIDEO_MAP.values())):
        full = os.path.join(VIDEO_DIR, vf)
        print("  {} : {}".format(full, "存在" if os.path.isfile(full) else "缺失"))

    ffplay = find_ffplay()
    if ffplay:
        print("音频播放器：ffplay ({})".format(ffplay))
    else:
        print("未找到 ffplay，视频将静音播放（如需声音请安装 ffmpeg）")

    # ----- 摄像头 -----
    print("外接摄像头打开中...")
    cap = open_camera()
    camera_ok = cap is not None and cap.isOpened()
    if camera_ok:
        print("外接摄像头已打开")
    else:
        print("摄像头打开失败，请检查 /dev/video41 和 /dev/video40")

    # =============================================================
    # 状态变量
    # =============================================================
    mode = MODE_RECOGNIZE

    latest_frame = None
    frame_lock = threading.Lock()
    cam_thread_running = True

    latest_recog = []
    recog_lock = threading.Lock()
    recog_thread_running = True

    # 触发逻辑状态
    confirm_name = None
    confirm_count = 0
    last_played_name = None     # 刚播放过的物体；其在画面中时不重复触发
    last_status = "等待识别物体..."
    last_status_color = DIM_TEXT
    recog_cooldown_until = 0.0  # 从视频切回识别后的冷却时间戳，期间不触发播放

    # 视频播放状态
    video_cap = None
    video_name = None           # 触发的物体名称
    video_file_name = None      # 视频文件名
    audio_proc = None

    btn_exit = Button((1650, 12, 240, 90), "退出程序", font_exit,
                      color=(235, 87, 87, 150), hover_color=(235, 87, 87, 230))
    btn_stop_video = Button((WIDTH // 2 - 220, HEIGHT - 120, 440, 100),
                            "停止播放 返回识别", font_exit,
                            color=(235, 87, 87, 150),
                            hover_color=(235, 87, 87, 230))

    # =============================================================
    # 后台线程：摄像头采集 + 物体识别
    # =============================================================
    def camera_capture_loop():
        nonlocal latest_frame
        fail = 0
        was_paused = False
        while cam_thread_running:
            if not camera_ok or cap is None:
                time.sleep(0.2)
                continue
            # 视频播放时暂停摄像头采集，避免无意义的 V4L2 ioctl 调用
            # 触发 "bad file descriptor" 警告，同时节省 CPU
            if mode == MODE_VIDEO:
                was_paused = True
                time.sleep(0.1)
                continue
            # 恢复采集时清空摄像头驱动缓冲区里积压的旧帧
            # 用时间窗口持续 grab（只取不解码，速度快），确保排空暂停期间
            # 积压的所有帧，固定次数可能不够（暂停几秒可能积压几百帧）
            if was_paused:
                was_paused = False
                clear_deadline = time.time() + 0.4
                while time.time() < clear_deadline:
                    try:
                        if not cap.grab():
                            break
                    except Exception:
                        break
                with frame_lock:
                    latest_frame = None
            try:
                # cap.read() 在 V4L2 阻塞模式下本身会等待下一帧，
                # 不需要额外 sleep；sleep 反而让采集跟不上摄像头推帧速度，
                # 导致内核 buffer 积压、画面滞后
                ok, frame = cap.read()
                if ok and _is_valid_frame(frame):
                    with frame_lock:
                        latest_frame = frame
                    fail = 0
                else:
                    fail += 1
                    if fail > 5:
                        time.sleep(0.1)
            except Exception as e:
                fail += 1
                if fail == 1:
                    print("摄像头采集异常: {}".format(e))
                time.sleep(0.05)

    def recognition_loop():
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

    threading.Thread(target=camera_capture_loop, daemon=True).start()
    threading.Thread(target=recognition_loop, daemon=True).start()

    # =============================================================
    # 视频播放控制
    # =============================================================
    def start_video(path, name):
        nonlocal mode, video_cap, video_name, video_file_name, audio_proc
        nonlocal last_status, last_status_color, confirm_name, confirm_count
        nonlocal last_played_name
        if not os.path.isfile(path):
            last_status = "视频文件不存在：{}".format(path)
            last_status_color = ERROR
            print(last_status)
            return
        vcap = cv2.VideoCapture(path)
        if vcap is None or not vcap.isOpened():
            last_status = "视频打开失败：{}".format(path)
            last_status_color = ERROR
            print(last_status)
            try:
                vcap.release()
            except Exception:
                pass
            return
        video_cap = vcap
        video_name = name
        video_file_name = os.path.basename(path)
        last_played_name = name
        confirm_name = None
        confirm_count = 0
        # 音频：ffplay 后台静默播放（无窗口），失败则静音
        # 注意：ffplay 不使用 -i 参数（那是 ffmpeg 语法），输入文件为位置参数
        audio_proc = None
        if ffplay:
            try:
                audio_proc = subprocess.Popen(
                    [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print("ffplay 启动失败：{}".format(e))
                audio_proc = None
        mode = MODE_VIDEO
        last_status = "正在播放：{} （识别到 {}）".format(video_file_name, name)
        last_status_color = SUCCESS
        print("触发视频播放：{} <- {}".format(path, name))
        # 清掉旧的识别结果，避免返回识别模式后物体框还停留在暂停前的位置
        with recog_lock:
            latest_recog = []

    def stop_video():
        nonlocal mode, video_cap, video_name, video_file_name, audio_proc
        nonlocal last_status, last_status_color, confirm_name, confirm_count
        nonlocal recog_cooldown_until
        # 停止音频
        if audio_proc is not None:
            try:
                audio_proc.terminate()
                try:
                    audio_proc.wait(timeout=1)
                except Exception:
                    try:
                        audio_proc.kill()
                    except Exception:
                        pass
            except Exception:
                pass
            audio_proc = None
        # 释放视频
        if video_cap is not None:
            try:
                video_cap.release()
            except Exception:
                pass
            video_cap = None
        video_name = None
        video_file_name = None
        confirm_name = None
        confirm_count = 0
        mode = MODE_RECOGNIZE
        # 设置 1.2 秒冷却：切回识别后摄像头缓冲区清空 + 画面稳定期间不触发播放，
        # 避免残留帧导致误触发
        recog_cooldown_until = time.time() + 1.2
        last_status = "播放结束，返回识别模式（稳定中...）"
        last_status_color = DIM_TEXT
        # 清掉旧的识别结果
        with recog_lock:
            latest_recog = []
        # 注意：last_played_name 保留，直到该物体离开画面才清除，避免立即重复触发

    # =============================================================
    # 主循环
    # =============================================================
    video_surf = None
    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if mode == MODE_VIDEO:
                        stop_video()
                    else:
                        running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_exit.rect.collidepoint(event.pos):
                    running = False
                elif mode == MODE_VIDEO and btn_stop_video.rect.collidepoint(event.pos):
                    stop_video()

        video_surf = None

        # =============================================================
        # 视频模式：读取视频帧
        # =============================================================
        if mode == MODE_VIDEO and video_cap is not None:
            ok, vframe = video_cap.read()
            if ok and vframe is not None and vframe.size > 0:
                try:
                    rgb = cv2.cvtColor(vframe, cv2.COLOR_BGR2RGB)
                    transposed = np.transpose(rgb, (1, 0, 2))
                    surf = pygame.surfarray.make_surface(transposed)
                    # 视频区域：顶部留 110px 给标题/状态栏/退出按钮，底部留 140px 给停止按钮
                    video_surf = fit_surface(surf, WIDTH - 40, HEIGHT - 110 - 140)
                except Exception:
                    video_surf = None
            else:
                # 视频播放结束
                stop_video()

        # =============================================================
        # 识别模式：触发判定
        # =============================================================
        if mode == MODE_RECOGNIZE:
            with recog_lock:
                recog_results = list(latest_recog)

            # 冷却期内不触发播放，只显示状态（切回识别后摄像头缓冲区清空 + 画面稳定）
            in_cooldown = time.time() < recog_cooldown_until

            # 已识别且映射了视频的物体
            matched = [(b, oid, n, c) for (b, oid, n, c) in recog_results
                       if n and lookup_video(n)]
            # 排除刚播放过、仍在画面中的物体
            triggerable = [m for m in matched if m[2] != last_played_name]

            if in_cooldown:
                # 冷却期：重置确认计数，不触发
                confirm_name = None
                confirm_count = 0
                if last_played_name is not None and matched:
                    last_status = "{} 刚播放过，离开画面后可重新触发".format(last_played_name)
                else:
                    last_status = "返回识别模式，稳定中..."
                last_status_color = DIM_TEXT
            elif triggerable:
                # 选画面中物体框面积最大的那个作为触发目标，减少背景小匹配误触
                box, oid, name, conf = max(triggerable,
                                            key=lambda r: (r[0][2] * r[0][3]) if r[0] else 0)
                if name == confirm_name:
                    confirm_count += 1
                else:
                    confirm_name = name
                    confirm_count = 1
                if confirm_count >= CONFIRM_FRAMES:
                    start_video(lookup_video(name), name)
                else:
                    last_status = "识别到 {}，确认中 ({}/{})...".format(
                        name, confirm_count, CONFIRM_FRAMES)
                    last_status_color = WARN
            elif matched:
                # 只有刚播放过的物体在画面中
                confirm_name = None
                confirm_count = 0
                last_status = "{} 刚播放过，离开画面后可重新触发".format(last_played_name)
                last_status_color = DIM_TEXT
            else:
                confirm_name = None
                confirm_count = 0
                # 刚播放过的物体已离开画面，解除抑制
                if last_played_name is not None:
                    last_played_name = None
                if recog_results:
                    last_status = "检测到物体，但未匹配到 card/book/cup"
                    last_status_color = DIM_TEXT
                else:
                    last_status = "等待识别物体..."
                    last_status_color = DIM_TEXT

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

        # 标题
        draw_text(screen, "物体识别触发视频播放", font_title, TEXT_COLOR,
                  (WIDTH // 2, 12), anchor="midtop")

        if mode == MODE_VIDEO:
            # ----- 视频播放界面 -----
            top_bar = 110
            pygame.draw.rect(screen, (0, 0, 0), (0, top_bar, WIDTH, HEIGHT - top_bar))
            if video_surf is not None:
                # 视频居中在顶部状态栏和底部按钮之间的区域
                area_h = HEIGHT - top_bar - 140
                rect = video_surf.get_rect(
                    center=(WIDTH // 2, top_bar + area_h // 2))
                screen.blit(video_surf, rect)
            # 顶部状态栏
            bar = pygame.Surface((WIDTH, 100), pygame.SRCALPHA)
            bar.fill((0, 0, 0, 180))
            screen.blit(bar, (0, 0))
            draw_text(screen,
                      "正在播放：{} （识别到 {}）".format(
                          video_file_name or "", video_name or ""),
                      font_msg, SUCCESS, (20, 50), anchor="midleft")
        else:
            # ----- 识别界面 -----
            draw_text(screen,
                      "实时识别中 — 将已登记的物体对准摄像头，识别到 card/book/cup 自动播放视频",
                      font_small, DIM_TEXT, (WIDTH // 2, 70), anchor="midtop")

            cam_x = (WIDTH - CAM_DISP_W) // 2
            cam_y = 110

            with frame_lock:
                frame = latest_frame
            cam_surf = cvframe_to_surface(frame, CAM_DISP_W, CAM_DISP_H) if frame is not None else None
            if cam_surf:
                screen.blit(cam_surf, (cam_x, cam_y))
            else:
                ph = pygame.Surface((CAM_DISP_W, CAM_DISP_H))
                ph.fill((30, 30, 40))
                screen.blit(ph, (cam_x, cam_y))
                if not camera_ok:
                    draw_text(screen, "摄像头未打开，请检查 /dev/video41 与 /dev/video40",
                              font_msg, ERROR,
                              (cam_x + CAM_DISP_W // 2, cam_y + CAM_DISP_H // 2),
                              anchor="center")
                else:
                    draw_text(screen, "画面加载中...", font_msg, DIM_TEXT,
                              (cam_x + CAM_DISP_W // 2, cam_y + CAM_DISP_H // 2),
                              anchor="center")
            pygame.draw.rect(screen, ACCENT,
                             (cam_x, cam_y, CAM_DISP_W, CAM_DISP_H), 2, border_radius=8)

            # 物体框
            if cam_surf is not None and frame is not None:
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
                    mapped = bool(name and lookup_video(name))
                    if not name:
                        color = OBJ_BOX_UNKNOWN
                    elif mapped:
                        color = OBJ_BOX_KNOWN
                    else:
                        color = OBJ_BOX_OTHER
                    pygame.draw.rect(screen, color, (rx, ry, rw, rh), 3, border_radius=6)
                    if name and mapped:
                        tag = "{} -> {}".format(name, os.path.basename(lookup_video(name)))
                    elif name:
                        tag = name
                    else:
                        tag = "未知"
                    lbl = font_box.render(tag, True, (0, 0, 0))
                    bgw = lbl.get_width() + 16
                    bgh = lbl.get_height() + 6
                    bgs = pygame.Surface((bgw, bgh), pygame.SRCALPHA)
                    bgs.fill((color[0], color[1], color[2], 220))
                    bgy = max(cam_y, ry - bgh)
                    screen.blit(bgs, (rx, bgy))
                    screen.blit(lbl, (rx + 8, bgy + 3))

            # 状态显示
            status_y = cam_y + CAM_DISP_H + 30
            draw_text(screen, last_status, font_big, last_status_color,
                      (WIDTH // 2, status_y), anchor="center")

            # 触发规则提示
            draw_text(screen, "触发规则：card -> 1.mp4    book -> 2.mp4    cup -> 3.mp4",
                      font_msg, ACCENT, (WIDTH // 2, status_y + 70), anchor="center")
            draw_text(screen, "ESC 退出  |  视频播放中按 ESC 返回识别",
                      font_small, DIM_TEXT, (WIDTH // 2, HEIGHT - 30), anchor="center")

        # ----- 按钮统一最后绘制，确保不被视频/状态栏遮挡 -----
        if mode == MODE_VIDEO:
            btn_stop_video.update(mouse_pos)
            btn_stop_video.draw(screen)
        btn_exit.update(mouse_pos)
        btn_exit.draw(screen)

        pygame.display.flip()
        clock.tick(30)

    # ----- 清理资源 -----
    cam_thread_running = False
    recog_thread_running = False
    time.sleep(0.15)
    if video_cap is not None:
        try:
            video_cap.release()
        except Exception:
            pass
    if audio_proc is not None:
        try:
            audio_proc.terminate()
        except Exception:
            pass
    if cap is not None:
        try:
            cap.release()
            print("摄像头已释放")
        except Exception:
            pass
    pygame.quit()


if __name__ == "__main__":
    main()
