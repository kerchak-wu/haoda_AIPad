# -*- coding: utf-8 -*-
# ============================================================
# 好搭AI派：文字识别触发视频播放（科技感界面版 1920x1080）
# ------------------------------------------------------------
# 功能说明：
#   1. 摄像头持续进行文字识别（OCR）
#   2. 识别到 "好搭智眼"        -> 播放 videos/hdzy.mp4（同步播放 recordings/hdzy.mp3）
#      识别到 "芦丁鸡"          -> 播放 videos/ldj.mp4（同步播放 recordings/ldj.mp3）
#      识别到 "信息科技实验板"  -> 播放 videos/syb.mp4（同步播放 recordings/syb.mp3）
#   3. 识别界面：居中摄像头画面（不占满）+ 左右信息面板 + 底部识别栏 +【退出程序】按钮
#   4. 视频播放界面：居中视频画面（不占满）+ 进度条 +【暂停/继续】【停止】按钮，暂停/继续与声音联动
#
# 使用前提：
#   - hdzy.mp4 / ldj.mp4 / syb.mp4 放入 videos 文件夹
#   - 声音播放：优先使用 recordings 下同名音轨（hdzy.mp3 / hdzy.wav 等）；
#     没有同名音轨时，程序自动用 ffmpeg 从视频文件提取音轨（缓存为 recordings/xxx_tmp.wav），
#     直接播放视频自带的声音；若 ffmpeg 不可用则无声播放，不影响程序运行
#   - 摄像头已连接，好搭AI派右下角开关拨到左侧
#   - 本程序不涉及 ESP32 扩展板外设，无需导入 ESP32 模块
#
# 注意事项：
#   - 若设备出现音频驱动与摄像头冲突导致崩溃，可注释掉 play_video 中
#     "音频同步播放" 部分（pygame.mixer 相关代码），改为无声播放
# ============================================================
import os
# Rockchip 平台兼容性补丁：强制 libGL 软件渲染，避免 GPU 驱动崩溃
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

import pygame
import cv2
import time
import threading

from text_recognition import TextRecognizer
from camera_vision_system_v3 import create_vision_system_v3

# ---------------- 配置参数 ----------------
# 关键词 -> 视频文件 -> 音频文件
VIDEO_MAP = [
    ('好搭智眼', 'videos/hdzy.mp4', 'recordings/hdzy.mp3'),
    ('芦丁鸡', 'videos/ldj.mp4', 'recordings/ldj.mp3'),
    ('信息科技实验板', 'videos/syb.mp4', 'recordings/syb.mp3'),
]

FONT_PATH = '/home/cxdz/jupyter/assets/simhei.ttf'
WINDOW_W = 1920
WINDOW_H = 1080
FPS = 30          # 识别界面刷新率
FPS_VIDEO = 25    # 视频播放帧率（如卡顿可调低）

# 摄像头画面显示区域（16:9，居中，不占满）
CAM_W, CAM_H = 1280, 720
CAM_X = (WINDOW_W - CAM_W) // 2
CAM_Y = 140

# 左右信息面板
PANEL_L = (40, 140, 240, 720)
PANEL_R = (WINDOW_W - 280, 140, 240, 720)

# 视频画面显示区域（不占满，四周留空）
VIDEO_AREA = (160, 100, 1600, 800)

# 按钮区域 (x, y, 宽, 高)
BTN_EXIT  = (WINDOW_W - 310, 18, 280, 52)                 # 识别界面：退出程序（右上角，标题栏内）
BTN_PAUSE = (WINDOW_W // 2 - 300, 960, 260, 70)            # 视频界面：暂停/继续
BTN_STOP  = (WINDOW_W // 2 + 40, 960, 260, 70)             # 视频界面：停止

# ---------------- 科技感配色 ----------------
COLOR_BG     = (8, 14, 30)        # 深色背景
COLOR_GRID   = (20, 36, 66)       # 网格线
COLOR_PANEL  = (12, 20, 42)       # 面板底色
COLOR_CYAN   = (0, 200, 255)      # 主色调：青
COLOR_BLUE   = (0, 120, 255)
COLOR_GREEN  = (0, 220, 120)
COLOR_RED    = (240, 60, 60)
COLOR_YELLOW = (255, 210, 60)
COLOR_WHITE  = (230, 240, 255)
COLOR_DIM    = (120, 150, 190)

# ---------------- 全局共享状态 ----------------
running = True              # 程序运行标志
in_video = False            # 是否处于视频播放界面
trigger_video = None        # 识别线程触发的视频路径
trigger_audio = None        # 识别线程触发的音频路径
ocr_text_display = '等待识别...'     # 当前识别到的文字
display_frame_cache = None  # 待显示的摄像头帧
frame_version = 0           # 画面版本号（脏帧检测用）

# 全局资源（main 中初始化）
bg_surface = None
font_title = None
font_panel = None
font_ocr = None
font_btn = None
font_small = None


# ==================== 基础工具函数 ====================
def in_rect(x, y, rect):
    """判断点是否在矩形内"""
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def is_hover(rect):
    """鼠标是否悬停在矩形上"""
    mx, my = pygame.mouse.get_pos()
    return in_rect(mx, my, rect)


def cv2_to_pygame_surface(frame, width, height, keep_ratio=False):
    """把 OpenCV 的 BGR 图像帧转换为 Pygame 的 Surface"""
    if frame is None:
        return None
    if keep_ratio:
        fh, fw = frame.shape[:2]
        ratio = min(width / fw, height / fh)
        nw, nh = int(fw * ratio), int(fh * ratio)
        frame = cv2.resize(frame, (nw, nh))
    else:
        frame = cv2.resize(frame, (width, height))
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return pygame.surfarray.make_surface(frame.transpose(1, 0, 2))


def create_background():
    """预渲染科技感背景：深色底 + 网格 + 顶部高光线（只生成一次）"""
    bg = pygame.Surface((WINDOW_W, WINDOW_H))
    bg.fill(COLOR_BG)
    step = 60
    for x in range(0, WINDOW_W, step):
        pygame.draw.line(bg, COLOR_GRID, (x, 0), (x, WINDOW_H), 1)
    for y in range(0, WINDOW_H, step):
        pygame.draw.line(bg, COLOR_GRID, (0, y), (WINDOW_W, y), 1)
    pygame.draw.line(bg, COLOR_CYAN, (0, 88), (WINDOW_W, 88), 2)
    return bg


def draw_corners(window, rect, color, L=16):
    """在矩形四角画科技感角标"""
    x, y, w, h = rect
    pygame.draw.line(window, color, (x, y + L), (x, y), 2)
    pygame.draw.line(window, color, (x, y), (x + L, y), 2)
    pygame.draw.line(window, color, (x + w - L, y), (x + w, y), 2)
    pygame.draw.line(window, color, (x + w, y), (x + w, y + L), 2)
    pygame.draw.line(window, color, (x, y + h - L), (x, y + h), 2)
    pygame.draw.line(window, color, (x, y + h), (x + L, y + h), 2)
    pygame.draw.line(window, color, (x + w - L, y + h), (x + w, y + h - L), 2)
    pygame.draw.line(window, color, (x + w, y + h - L), (x + w, y + h), 2)


def draw_panel(window, rect, title=''):
    """科技感面板：深色底 + 边框 + 四角角标 + 标题"""
    pygame.draw.rect(window, COLOR_PANEL, rect, 0)
    pygame.draw.rect(window, (40, 70, 110), rect, 1)
    pygame.draw.rect(window, (60, 110, 170), rect, 2)
    draw_corners(window, rect, COLOR_CYAN, 16)
    if title:
        t = font_panel.render(title, True, COLOR_CYAN)
        window.blit(t, (rect[0] + 14, rect[1] + 12))


def draw_button(window, font, rect, text, accent, hover=False):
    """科技感按钮：悬停时高亮"""
    x, y, w, h = rect
    if hover:
        bg = (20, 90, 130)
    else:
        bg = (16, 40, 66)
    pygame.draw.rect(window, bg, rect, 0)
    pygame.draw.rect(window, (255, 255, 255) if hover else accent, rect, 3)
    label = font.render(text, True, COLOR_WHITE)
    window.blit(label, (x + (w - label.get_width()) // 2, y + (h - label.get_height()) // 2))


def draw_glow_title(window, text, pos):
    """带发光效果的标题文字"""
    shadow = font_title.render(text, True, (0, 90, 150))
    window.blit(shadow, (pos[0] + 3, pos[1] + 3))
    main = font_title.render(text, True, COLOR_CYAN)
    window.blit(main, pos)


def find_or_extract_audio(video_path, audio_path):
    """获取可播放的音轨文件：
    1) 优先使用 recordings 下的同名音轨（mp3/wav）
    2) 否则用 ffmpeg 从视频文件提取音轨，缓存为 recordings/xxx_tmp.wav
    3) 均失败返回 None（视频无声播放）
    """
    # 候选音轨：recordings/hdzy.mp3、recordings/hdzy.wav
    candidates = []
    if audio_path:
        candidates.append(audio_path)
        stem, ext = os.path.splitext(audio_path)
        if ext.lower() != '.wav':
            candidates.append(stem + '.wav')
    for c in candidates:
        if c and os.path.exists(c):
            print('使用已有音轨：' + c)
            return c

    # 从视频文件提取音轨（只解码音频流，速度快）
    base = os.path.splitext(os.path.basename(video_path))[0]
    tmp_wav = 'recordings/' + base + '_tmp.wav'
    if os.path.exists(tmp_wav):
        print('使用缓存音轨：' + tmp_wav)
        return tmp_wav
    print('正在从视频提取音轨：' + video_path)
    try:
        import subprocess
        result = subprocess.call(
            ['ffmpeg', '-y', '-i', video_path, '-vn',
             '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', tmp_wav],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result == 0 and os.path.exists(tmp_wav):
            print('音轨提取完成：' + tmp_wav)
            return tmp_wav
    except:
        pass
    print('未找到可用音轨，视频将无声播放')
    return None


# ==================== 识别线程 ====================
def ocr_thread(vision_system, ocr_recognizer):
    """识别线程：循环取帧 -> 更新画面缓存 -> OCR 识别 -> 触发视频"""
    global running, in_video, trigger_video, trigger_audio
    global ocr_text_display, display_frame_cache, frame_version
    while running:
        if in_video:
            # 视频播放期间暂停识别，避免重复触发
            time.sleep(0.2)
            continue
        frame = vision_system.capture_frame()
        if frame is None:
            time.sleep(0.2)
            continue
        # 更新显示画面（脏帧版本号 +1，主线程检测到变化才转换）
        display_frame_cache = frame
        frame_version += 1
        try:
            ocr_result = ocr_recognizer.recognize_text(frame, confidence_threshold=0.5)
            if ocr_result["success"]:
                text = ocr_result["text"]
                # 清理空格、换行等干扰字符，提高关键词匹配率
                clean_text = text.replace(' ', '').replace('\r', '').replace('\n', '').replace('\u3000', '')
                ocr_text_display = clean_text
                print('当前识别文字：' + clean_text)
                for keyword, video_path, audio_path in VIDEO_MAP:
                    if keyword in clean_text:
                        trigger_video = video_path
                        trigger_audio = audio_path
                        print('识别到关键词【' + keyword + '】，播放视频：' + video_path)
                        break
        except:
            print('OCR识别出现异常')
        time.sleep(0.3)


# ==================== 识别界面 ====================
def draw_recognition_screen(window, cam_surface, start_time):
    """绘制识别界面：居中摄像头画面 + 左右信息面板 + 底部识别栏 + 退出按钮"""
    global ocr_text_display
    window.blit(bg_surface, (0, 0))

    # ---- 顶部标题栏 ----
    pygame.draw.rect(window, (6, 10, 24), (0, 0, WINDOW_W, 88), 0)
    draw_glow_title(window, '文字识别触发视频播放', (60, 20))
    # 标题右侧状态指示（避开右上角退出按钮）
    pygame.draw.circle(window, COLOR_GREEN, (512, 44), 8, 0)
    pygame.draw.circle(window, (30, 120, 70), (512, 44), 14, 2)
    st = font_small.render('识别中', True, COLOR_GREEN)
    window.blit(st, (534, 32))

    # 右上角退出程序按钮（位于标题栏内，不与其他文字重叠）
    draw_button(window, font_btn, BTN_EXIT, '退出程序', COLOR_RED, is_hover(BTN_EXIT))

    # ---- 摄像头画面（居中 16:9，不占满）----
    if cam_surface is not None:
        window.blit(cam_surface, (CAM_X, CAM_Y))
    else:
        pygame.draw.rect(window, (10, 16, 36), (CAM_X, CAM_Y, CAM_W, CAM_H), 0)
        msg = font_panel.render('摄像头画面加载中...', True, COLOR_DIM)
        window.blit(msg, (CAM_X + (CAM_W - msg.get_width()) // 2, CAM_Y + (CAM_H - msg.get_height()) // 2))
    pygame.draw.rect(window, COLOR_CYAN, (CAM_X, CAM_Y, CAM_W, CAM_H), 2)
    draw_corners(window, (CAM_X, CAM_Y, CAM_W, CAM_H), COLOR_CYAN, 18)

    # ---- 左侧面板：识别目标 ----
    draw_panel(window, PANEL_L, '识别目标')
    for i, (kw, vp, ap) in enumerate(VIDEO_MAP):
        y = PANEL_L[1] + 80 + i * 100
        pygame.draw.circle(window, COLOR_DIM, (PANEL_L[0] + 40, y + 8), 6, 0)
        pygame.draw.circle(window, (60, 90, 130), (PANEL_L[0] + 40, y + 8), 10, 1)
        kw_label = font_small.render(kw, True, COLOR_WHITE)
        window.blit(kw_label, (PANEL_L[0] + 62, y - 12))
        vd_label = font_small.render(os.path.basename(vp), True, COLOR_DIM)
        window.blit(vd_label, (PANEL_L[0] + 62, y + 18))

    # ---- 右侧面板：系统状态 ----
    draw_panel(window, PANEL_R, '系统状态')
    elapsed = int(time.time() - start_time)
    hh, mm, ss = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    lines = [
        '运行时长：%02d:%02d:%02d' % (hh, mm, ss),
        '摄像头：已连接',
        'OCR：运行中',
    ]
    for i, line in enumerate(lines):
        lb = font_small.render(line, True, COLOR_WHITE)
        window.blit(lb, (PANEL_R[0] + 14, PANEL_R[1] + 70 + i * 44))
    tip = font_small.render('提示：', True, COLOR_YELLOW)
    window.blit(tip, (PANEL_R[0] + 14, PANEL_R[1] + 280))
    tip1 = font_small.render('请将文字卡片', True, COLOR_DIM)
    tip2 = font_small.render('对准摄像头', True, COLOR_DIM)
    window.blit(tip1, (PANEL_R[0] + 14, PANEL_R[1] + 320))
    window.blit(tip2, (PANEL_R[0] + 14, PANEL_R[1] + 352))

    # ---- 底部信息栏：识别文字 ----
    bar = (CAM_X, 880, CAM_W, 80)
    draw_panel(window, bar)
    ocr_label = font_ocr.render('识别文字：' + ocr_text_display, True, COLOR_YELLOW)
    window.blit(ocr_label, (bar[0] + 26, bar[1] + 20))
    tip_line = font_small.render('关键词：好搭智眼 / 芦丁鸡 / 信息科技实验板', True, COLOR_DIM)
    window.blit(tip_line, (bar[0] + 26, bar[1] + 50))


# ==================== 视频播放界面 ====================
def play_video(window, video_path, audio_path):
    """视频播放界面：暂停/继续（与声音联动）、停止、进度条，播完自动返回识别界面"""
    global running, in_video, ocr_text_display
    in_video = True
    print('开始播放视频：' + video_path)

    # ---- 加载提示画面（提取音轨或打开视频时避免界面空白）----
    window.blit(bg_surface, (0, 0))
    pygame.draw.rect(window, (6, 10, 24), (0, 0, WINDOW_W, 88), 0)
    draw_glow_title(window, '正在加载视频...', (60, 20))
    tip = font_panel.render('正在准备视频与音轨，请稍候...', True, COLOR_DIM)
    window.blit(tip, (WINDOW_W // 2 - tip.get_width() // 2, WINDOW_H // 2))
    pygame.display.flip()

    vd = cv2.VideoCapture()
    vd.open(video_path)
    if not vd.isOpened():
        print('无法打开视频：' + video_path)
        in_video = False
        return

    # ---- 音频：优先同名音轨，否则自动从视频文件提取音轨播放 ----
    music_ok = False
    wav_path = find_or_extract_audio(video_path, audio_path)
    if wav_path:
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(wav_path)
            pygame.mixer.music.play()
            music_ok = True
            print('音频播放：' + wav_path)
        except:
            print('音频播放失败，视频将无声播放')

    paused = False
    current_frame = None
    total_frames = max(int(vd.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
    area_x, area_y, area_w, area_h = VIDEO_AREA
    clock = pygame.time.Clock()

    while running and in_video:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                in_video = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, y = event.pos
                if in_rect(x, y, BTN_PAUSE):
                    paused = not paused
                    if paused:
                        print('视频已暂停')
                        if music_ok:
                            pygame.mixer.music.pause()
                    else:
                        print('视频继续播放')
                        if music_ok:
                            pygame.mixer.music.unpause()
                elif in_rect(x, y, BTN_STOP):
                    print('视频已停止，返回识别界面')
                    in_video = False

        if not paused:
            ret, grab = vd.read()
            if not ret:
                print('视频播放完成，返回识别界面')
                in_video = False
                break
            current_frame = grab

        # ---- 绘制 ----
        window.blit(bg_surface, (0, 0))

        # 顶部标题栏
        pygame.draw.rect(window, (6, 10, 24), (0, 0, WINDOW_W, 88), 0)
        status = '暂停中' if paused else '播放中'
        draw_glow_title(window, '视频播放：' + os.path.basename(video_path) + '（' + status + '）', (60, 20))
        audio_label = font_small.render('音频：' + ('已同步' if music_ok else '无'), True, COLOR_DIM)
        window.blit(audio_label, (WINDOW_W - 220, 32))

        # 视频画面（保持纵横比，居中于显示区域，不占满）
        if current_frame is not None:
            fh, fw = current_frame.shape[:2]
            ratio = min(area_w / fw, area_h / fh)
            nw, nh = int(fw * ratio), int(fh * ratio)
            frame2 = cv2.resize(current_frame, (nw, nh))
            frame2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2RGB)
            surface = pygame.surfarray.make_surface(frame2.transpose(1, 0, 2))
            sx = area_x + (area_w - nw) // 2
            sy = area_y + (area_h - nh) // 2
            window.blit(surface, (sx, sy))
            pygame.draw.rect(window, COLOR_CYAN, (sx - 2, sy - 2, nw + 4, nh + 4), 2)
            draw_corners(window, (sx - 2, sy - 2, nw + 4, nh + 4), COLOR_CYAN, 18)

        # 播放进度条
        pos_frames = int(vd.get(cv2.CAP_PROP_POS_FRAMES))
        ratio = min(pos_frames / total_frames, 1.0)
        bar = (WINDOW_W // 2 - 550, 910, 1100, 14)
        pygame.draw.rect(window, (30, 50, 80), bar, 0)
        pygame.draw.rect(window, COLOR_CYAN, (bar[0], bar[1], int(bar[2] * ratio), bar[3]), 0)
        pygame.draw.rect(window, (60, 100, 150), bar, 1)
        pct = font_small.render(str(int(ratio * 100)) + '%', True, COLOR_WHITE)
        window.blit(pct, (bar[0] + bar[2] + 24, bar[1] - 4))

        # 按钮（暂停/继续 与 停止）
        if paused:
            draw_button(window, font_btn, BTN_PAUSE, '继续', COLOR_GREEN, is_hover(BTN_PAUSE))
        else:
            draw_button(window, font_btn, BTN_PAUSE, '暂停', COLOR_YELLOW, is_hover(BTN_PAUSE))
        draw_button(window, font_btn, BTN_STOP, '停止', COLOR_RED, is_hover(BTN_STOP))

        pygame.display.flip()
        clock.tick(FPS_VIDEO)

    # ---- 视频结束清理 ----
    if music_ok:
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except:
            pass
    vd.release()
    in_video = False
    ocr_text_display = '等待识别...'
    print('已返回识别界面')


# ==================== 主程序 ====================
def main():
    global running, in_video, trigger_video, trigger_audio
    global ocr_text_display, display_frame_cache, frame_version
    global bg_surface, font_title, font_panel, font_ocr, font_btn, font_small

    # Rockchip 平台兼容性补丁：分段初始化，避免音频驱动与摄像头 V4L2 死锁
    pygame.display.init()
    pygame.font.init()
    window = pygame.display.set_mode(size=(WINDOW_W, WINDOW_H), flags=0, depth=0)
    pygame.display.set_caption('文字识别触发视频播放')
    clock = pygame.time.Clock()

    # 字体与背景
    font_title = pygame.font.Font(FONT_PATH, 44)
    font_panel = pygame.font.Font(FONT_PATH, 26)
    font_ocr = pygame.font.Font(FONT_PATH, 34)
    font_btn = pygame.font.Font(FONT_PATH, 32)
    font_small = pygame.font.Font(FONT_PATH, 22)
    bg_surface = create_background()

    # 初始化视觉系统（全托管模式：V3 管理摄像头，程序通过 capture_frame 取帧）
    vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)
    if vision_system.open_camera():
        print('摄像头已打开')
    else:
        print('摄像头打开失败，请检查摄像头连接')
    vision_system.threaded_system.start_background_detection(show_preview=False)

    # 初始化 OCR 文字识别器
    ocr_recognizer = TextRecognizer()

    # 启动识别线程
    thread = threading.Thread(target=ocr_thread, args=(vision_system, ocr_recognizer), daemon=True)
    thread.start()

    start_time = time.time()
    cam_surface_cache = None
    cam_surface_version = -1

    # ---------------- 主循环 ----------------
    while running:
        # 有视频触发时，进入视频播放界面
        if trigger_video:
            video_path = trigger_video
            audio_path = trigger_audio
            trigger_video = None
            trigger_audio = None
            play_video(window, video_path, audio_path)
            continue

        # ---- 识别界面事件 ----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if in_rect(event.pos[0], event.pos[1], BTN_EXIT):
                    print('点击退出程序')
                    running = False

        # 脏帧检测：画面版本变化时才转换 Surface，避免每帧重复转换导致卡顿
        if frame_version != cam_surface_version:
            cam_surface_cache = cv2_to_pygame_surface(display_frame_cache, CAM_W, CAM_H)
            cam_surface_version = frame_version

        draw_recognition_screen(window, cam_surface_cache, start_time)
        pygame.display.flip()
        clock.tick(FPS)

    # ---------------- 清理资源 ----------------
    running = False
    try:
        vision_system.cleanup()
    except:
        pass
    try:
        ocr_recognizer.cleanup()
    except:
        pass
    pygame.display.quit()
    pygame.font.quit()
    print('程序已退出')


if __name__ == '__main__':
    main()
