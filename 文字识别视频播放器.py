# -*- coding: utf-8 -*-
"""
好搭AI派 - 外接摄像头文字识别与视频播放系统
=============================================
功能：
  1. 摄像头实时文字识别（OCR）
  2. 识别到"好搭智眼" → 播放 videos/1.mp4
  3. 识别到"芦丁鸡孵化箱" → 播放 videos/2.mp4
  4. 识别到"信息科技实验板" → 播放 videos/3.mp4
  5. 视频播放时支持暂停/继续/停止按钮

架构：纯 cv2 独占模式 + 双线程分离
  - 采集线程：无限循环 cap.read() 刷新 raw_frame（30fps）
  - 主线程：取最新帧做 OCR 和 UI 绘制

前置条件：
  - 视频文件放入 videos/ 文件夹（好搭智眼.mp4 等）
  - 音频文件放入 videos/ 文件夹（好搭智眼.mp3 等，与视频同名）
  - 外接USB摄像头已连接
  - 好搭AI派右下角开关拨到左侧（外设模式）
"""

import os
import sys
import threading
import subprocess
import tempfile
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

import pygame
import cv2
import time
import numpy as np
from text_recognition import TextRecognizer

# ============ 配置区 ============
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FONT_PATH = '/home/cxdz/jupyter/assets/simfang.ttf'

# 摄像头预览区域
PREVIEW_X = 60
PREVIEW_Y = 140
PREVIEW_W = 960
PREVIEW_H = 700

# 文字识别关键词 → 视频文件映射
VIDEO_MAP = {
    "好搭智眼":     "videos/1.mp4",
    "芦丁鸡孵化箱": "videos/2.mp4",
    "信息科技实验板": "videos/3.mp4",
}

OCR_INTERVAL = 2.0
CAMERA_DEVICES = ["/dev/video41", "/dev/video40"]

# 科技感配色
COLOR_BG        = (10, 12, 28)    # 深空蓝黑
COLOR_CYAN      = (0, 200, 255)   # 青色主色
COLOR_CYAN_DIM  = (0, 120, 180)   # 暗青
COLOR_CYAN_GLOW = (0, 230, 255)   # 亮青
COLOR_GREEN     = (0, 220, 120)   # 绿色
COLOR_RED       = (220, 50, 50)   # 红色
COLOR_ORANGE    = (255, 180, 50)  # 橙色
COLOR_TEXT      = (220, 230, 240) # 文字色
COLOR_TEXT_DIM  = (120, 140, 160) # 灰文字
COLOR_PANEL     = (16, 20, 42)    # 面板底色
COLOR_BORDER    = (30, 60, 100)   # 面板边框


def _detect_camera():
    """自动检测可用的摄像头设备"""
    for dev in CAMERA_DEVICES:
        cap = cv2.VideoCapture()
        try:
            if cap.open(dev):
                ret, _ = cap.read()
                if ret:
                    cap.release()
                    print(f"检测到摄像头: {dev}")
                    return dev
        except Exception:
            pass
        cap.release()
    return None


class CameraCapture:
    """摄像头采集线程：独立循环读取，双缓冲避免卡主线程"""

    def __init__(self, device):
        self.device = device
        self.frame = None
        self.running = False
        self.thread = None
        self._lock = threading.Lock()
        self._ready = threading.Event()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        return self

    def wait_ready(self, timeout=3.0):
        return self._ready.wait(timeout=timeout)

    def _capture_loop(self):
        cap = cv2.VideoCapture()
        cap.open(self.device)
        if not cap.isOpened():
            print(f"错误：无法打开摄像头 {self.device}")
            self.running = False
            return
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc('M', 'J', 'P', 'G'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        for _ in range(5):
            ret, f = cap.read()
            if ret and f is not None and f.size > 0:
                with self._lock:
                    self.frame = f
                self._ready.set()
                break
            time.sleep(0.05)
        while self.running:
            ret, f = cap.read()
            if ret:
                with self._lock:
                    self.frame = f
            else:
                time.sleep(0.01)
        cap.release()

    def get_frame(self):
        with self._lock:
            if self.frame is not None:
                return self.frame.copy()
            return None

    def is_ready(self):
        return self._ready.is_set()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)


class OCRVideoPlayer:
    """文字识别视频播放器"""

    def __init__(self):
        # ----- Pygame 分段初始化 -----
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("好搭AI派 - 文字识别视频播放")

        # ----- 字体 -----
        self.font_large = pygame.font.Font(FONT_PATH, 52)
        self.font_medium = pygame.font.Font(FONT_PATH, 40)
        self.font_small = pygame.font.Font(FONT_PATH, 30)
        self.font_hint = pygame.font.Font(FONT_PATH, 26)

        # ----- 启动界面 -----
        self._show_loading("系统启动中")

        # ----- 摄像头 -----
        self._show_loading("正在检测摄像头")
        cam_device = _detect_camera()
        if cam_device:
            self.camera = CameraCapture(cam_device).start()
            self._show_loading("正在等待摄像头画面")
            if self.camera.wait_ready(timeout=3.0):
                print("摄像头画面已就绪")
        else:
            print("警告：未检测到可用摄像头")
            self.camera = None

        # ----- OCR 识别器 -----
        self._show_loading("正在加载 OCR 模型")
        self.ocr = TextRecognizer()

        # ----- 状态变量 -----
        self.is_playing_video = False
        self.is_paused = False
        self.video_cap = None
        self.last_video_frame = None
        self.last_ocr_time = 0
        self.last_text = ""
        self.audio_initialized = False
        self.audio_temp_path = None

        # ----- 按钮区域 -----
        btn_y = SCREEN_HEIGHT - 130
        self.pause_btn = pygame.Rect(SCREEN_WIDTH // 2 - 220, btn_y, 180, 75)
        self.stop_btn  = pygame.Rect(SCREEN_WIDTH // 2 + 40,  btn_y, 180, 75)
        self.exit_btn  = pygame.Rect(SCREEN_WIDTH - 150, 20, 120, 55)

        print("系统初始化完成，进入识别模式")

    # ================================================================
    #  加载画面
    # ================================================================
    def _show_loading(self, text):
        self.screen.fill(COLOR_BG)
        # 加载动画装饰
        for i in range(3):
            x = SCREEN_WIDTH // 2 - 80 + i * 80
            y = SCREEN_HEIGHT // 2 + 40
            pygame.draw.circle(self.screen, COLOR_CYAN_DIM, (x, y), 6)
            pygame.draw.circle(self.screen, COLOR_CYAN, (x, y), 4, 1)
        hint = self.font_medium.render(text, True, COLOR_TEXT)
        self.screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2,
                                SCREEN_HEIGHT // 2 - 30))
        pygame.display.flip()

    # ================================================================
    #  绘制装饰工具
    # ================================================================
    def _draw_panel(self, rect, color=COLOR_PANEL, border_color=COLOR_BORDER):
        """绘制科技感面板"""
        pygame.draw.rect(self.screen, color, rect, border_radius=6)
        pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=6)
        # 左上角装饰小方块
        corner = pygame.Rect(rect.x + 6, rect.y + 6, 8, 8)
        pygame.draw.rect(self.screen, COLOR_CYAN_DIM, corner, border_radius=2)
        # 右上角
        corner2 = pygame.Rect(rect.right - 14, rect.y + 6, 8, 8)
        pygame.draw.rect(self.screen, COLOR_CYAN_DIM, corner2, border_radius=2)

    def _draw_glow_button(self, rect, text, color, glow=True):
        """绘制发光按钮"""
        if glow:
            # 外发光
            glow_rect = rect.inflate(8, 8)
            pygame.draw.rect(self.screen, (*color[:3], 40), glow_rect, border_radius=10)
        pygame.draw.rect(self.screen, color, rect, border_radius=6)
        # 内边框亮线
        inner = rect.inflate(-4, -4)
        c = (min(color[0] + 60, 255), min(color[1] + 60, 255), min(color[2] + 60, 255))
        pygame.draw.rect(self.screen, c, inner, 1, border_radius=5)
        font = pygame.font.Font(FONT_PATH, 38)
        surf = font.render(text, True, (255, 255, 255))
        r = surf.get_rect(center=rect.center)
        self.screen.blit(surf, r)

    # ================================================================
    #  主循环
    # ================================================================
    def run(self):
        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_click(event.pos)

            if self.is_playing_video:
                self._update_video()
            else:
                self._update_recognition()

            pygame.display.flip()
            clock.tick(30)
        self._cleanup()

    # ================================================================
    #  事件处理
    # ================================================================
    def _handle_click(self, pos):
        if self.exit_btn.collidepoint(pos):
            self._cleanup()
            sys.exit(0)
        if self.is_playing_video:
            if self.pause_btn.collidepoint(pos):
                self._toggle_pause()
            elif self.stop_btn.collidepoint(pos):
                self._stop_video()

    def _toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass
        else:
            try:
                pygame.mixer.music.unpause()
            except Exception:
                pass
        print("视频已暂停" if self.is_paused else "视频继续播放")

    def _stop_video(self):
        self.is_playing_video = False
        self.is_paused = False
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None
        if self.audio_initialized:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except Exception:
                pass
            self.audio_initialized = False
        # 删除临时音频文件
        if self.audio_temp_path:
            try:
                os.unlink(self.audio_temp_path)
            except Exception:
                pass
            self.audio_temp_path = None
        print("视频已停止，返回识别模式")

    def _play_video(self, video_path):
        self._stop_video()
        cap = cv2.VideoCapture()
        cap.open(video_path)
        if not cap.isOpened():
            print(f"无法打开视频文件: {video_path}")
            return
        self.video_cap = cap
        self.is_playing_video = True
        print(f"开始播放视频: {video_path}")

        # 用 ffmpeg 提取音频到临时 WAV 文件，再通过 pygame 播放
        try:
            # 创建临时 WAV 文件
            tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            self.audio_temp_path = tmp.name
            tmp.close()
            # 提取音频
            subprocess.run(
                ['ffmpeg', '-i', video_path, '-vn',
                 '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2',
                 '-y', self.audio_temp_path],
                capture_output=True, timeout=15
            )
            # 播放 WAV
            pygame.mixer.init()
            pygame.mixer.music.load(self.audio_temp_path)
            pygame.mixer.music.play()
            self.audio_initialized = True
            print("音频已启动（ffmpeg + WAV）")
        except Exception as e:
            print(f"音频加载失败（视频将无声播放）: {e}")
            self.audio_initialized = False

    # ================================================================
    #  视频播放模式
    # ================================================================
    def _update_video(self):
        if self.is_paused:
            self._draw_video_ui()
            return
        ret, frame = self.video_cap.read()
        if not ret:
            self._stop_video()
            return
        self.last_video_frame = frame
        self._draw_video_ui(frame)

    def _draw_video_ui(self, frame=None):
        self.screen.fill(COLOR_BG)
        # 暂停时显示最后一帧
        if frame is None:
            frame = self.last_video_frame
        if frame is not None:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            fh, fw = frame_rgb.shape[:2]
            scale = min(SCREEN_WIDTH / fw, (SCREEN_HEIGHT - 160) / fh)
            new_w, new_h = int(fw * scale), int(fh * scale)
            frame_resized = cv2.resize(frame_rgb, (new_w, new_h))
            surface = pygame.surfarray.make_surface(frame_resized.swapaxes(0, 1))
            ox = (SCREEN_WIDTH - new_w) // 2
            oy = ((SCREEN_HEIGHT - 160) - new_h) // 2
            self.screen.blit(surface, (ox, oy))

        # 底部控制栏半透明背景
        bar = pygame.Rect(0, SCREEN_HEIGHT - 155, SCREEN_WIDTH, 155)
        bar_surf = pygame.Surface((SCREEN_WIDTH, 155), pygame.SRCALPHA)
        bar_surf.fill((10, 12, 28, 200))
        self.screen.blit(bar_surf, (0, SCREEN_HEIGHT - 155))
        pygame.draw.line(self.screen, COLOR_BORDER, (0, SCREEN_HEIGHT - 155),
                         (SCREEN_WIDTH, SCREEN_HEIGHT - 155), 2)

        # 按钮（暂停/继续 + 停止）
        pause_label = "继续" if self.is_paused else "暂停"
        pause_color = COLOR_GREEN if self.is_paused else COLOR_CYAN
        self._draw_glow_button(self.pause_btn, pause_label, pause_color)
        self._draw_glow_button(self.stop_btn, "停止", COLOR_RED)

    # ================================================================
    #  文字识别模式（科技感UI）
    # ================================================================
    def _update_recognition(self):
        raw_frame = self.camera.get_frame() if self.camera else None
        self.screen.fill(COLOR_BG)

        # ---- 顶部标题栏 ----
        title_bar = pygame.Rect(0, 0, SCREEN_WIDTH, 80)
        pygame.draw.rect(self.screen, (14, 16, 34), title_bar)
        pygame.draw.line(self.screen, COLOR_CYAN_DIM, (0, 80), (SCREEN_WIDTH, 80), 2)
        # 标题文字
        title = self.font_large.render("文字识别系统 · 好搭AI派", True, COLOR_CYAN)
        self.screen.blit(title, (40, 18))
        # 状态指示点
        if raw_frame is not None:
            pygame.draw.circle(self.screen, COLOR_GREEN, (SCREEN_WIDTH - 350, 40), 7)
            status_text = "CAMERA OK"
        else:
            pygame.draw.circle(self.screen, COLOR_RED, (SCREEN_WIDTH - 350, 40), 7)
            status_text = "CAMERA --"
        st = self.font_hint.render(status_text, True, COLOR_TEXT_DIM)
        self.screen.blit(st, (SCREEN_WIDTH - 330, 28))

        # ---- 退出按钮（右上角，在标题栏内）----
        self._draw_glow_button(self.exit_btn, "退出", COLOR_RED, glow=False)

        # ---- 左侧：摄像头预览面板 ----
        panel_rect = pygame.Rect(PREVIEW_X - 10, PREVIEW_Y - 10, PREVIEW_W + 20, PREVIEW_H + 20)
        self._draw_panel(panel_rect)

        if raw_frame is not None:
            preview = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2RGB)
            preview = cv2.resize(preview, (PREVIEW_W, PREVIEW_H))
            surface = pygame.surfarray.make_surface(preview.swapaxes(0, 1))
            self.screen.blit(surface, (PREVIEW_X, PREVIEW_Y))
            # 青色边框
            pygame.draw.rect(self.screen, COLOR_CYAN,
                             (PREVIEW_X - 2, PREVIEW_Y - 2, PREVIEW_W + 4, PREVIEW_H + 4), 2)
            # 角落扫描线装饰
            for corner in [(PREVIEW_X, PREVIEW_Y), (PREVIEW_X + PREVIEW_W - 20, PREVIEW_Y),
                           (PREVIEW_X, PREVIEW_Y + PREVIEW_H - 20),
                           (PREVIEW_X + PREVIEW_W - 20, PREVIEW_Y + PREVIEW_H - 20)]:
                pygame.draw.rect(self.screen, COLOR_CYAN_GLOW,
                                 (*corner, 20, 3))
            # 底部标签
            cam_label = self.font_hint.render("CAMERA FEED", True, COLOR_CYAN_DIM)
            self.screen.blit(cam_label, (PREVIEW_X + 10, PREVIEW_Y + PREVIEW_H + 8))
        else:
            pygame.draw.rect(self.screen, (20, 22, 45),
                             (PREVIEW_X, PREVIEW_Y, PREVIEW_W, PREVIEW_H))
            if self.camera is None:
                msg = "未检测到摄像头，请检查连接"
            else:
                msg = "摄像头画面加载中..."
            no_cam = self.font_hint.render(msg, True, COLOR_TEXT_DIM)
            self.screen.blit(no_cam, (PREVIEW_X + PREVIEW_W // 2 - no_cam.get_width() // 2,
                                      PREVIEW_Y + PREVIEW_H // 2 - 15))

        # ---- 右侧：信息面板 ----
        info_x = PREVIEW_X + PREVIEW_W + 60
        info_y = PREVIEW_Y + 10
        max_w = SCREEN_WIDTH - info_x - 40

        # 提示文字
        hint = self.font_hint.render("请将待识别文字对准摄像头区域", True, COLOR_TEXT_DIM)
        self.screen.blit(hint, (info_x, info_y))

        # 定时 OCR
        now = time.time()
        if now - self.last_ocr_time >= OCR_INTERVAL and raw_frame is not None:
            self.last_ocr_time = now
            self._do_ocr(raw_frame)

        # 识别结果面板
        result_rect = pygame.Rect(info_x, info_y + 50, max_w, 180)
        self._draw_panel(result_rect)

        if self.last_text:
            # 识别到的文字
            label = self.font_hint.render("识别结果", True, COLOR_CYAN_DIM)
            self.screen.blit(label, (info_x + 20, info_y + 65))

            text_surf = self.font_medium.render(self.last_text, True, COLOR_CYAN_GLOW)
            if text_surf.get_width() > max_w - 40:
                text_surf = self.font_small.render(self.last_text, True, COLOR_CYAN_GLOW)
            self.screen.blit(text_surf, (info_x + 20, info_y + 105))

            # 匹配状态
            for keyword in VIDEO_MAP:
                if keyword in self.last_text:
                    match = self.font_hint.render(
                        f"▸ 匹配关键词: {keyword}", True, COLOR_ORANGE
                    )
                    self.screen.blit(match, (info_x + 20, info_y + 155))
                    break
            else:
                no_match = self.font_hint.render("等待匹配关键词...", True, COLOR_TEXT_DIM)
                self.screen.blit(no_match, (info_x + 20, info_y + 155))
        else:
            waiting = self.font_hint.render("等待识别...", True, COLOR_TEXT_DIM)
            self.screen.blit(waiting, (info_x + 20, info_y + 100))

        # 关键词列表面板
        kw_rect = pygame.Rect(info_x, info_y + 260, max_w, 200)
        self._draw_panel(kw_rect)
        kw_title = self.font_hint.render("可识别关键词", True, COLOR_CYAN_DIM)
        self.screen.blit(kw_title, (info_x + 20, info_y + 275))
        for i, (kw, video_path) in enumerate(VIDEO_MAP.items()):
            # 序号圆点
            dot_x = info_x + 25
            dot_y = info_y + 320 + i * 45
            pygame.draw.circle(self.screen, COLOR_CYAN, (dot_x, dot_y), 4)
            kw_surf = self.font_small.render(f"「{kw}」  →  {video_path}",
                                             True, COLOR_TEXT)
            self.screen.blit(kw_surf, (dot_x + 18, dot_y - 14))

        # ---- 底部状态栏 ----
        status_bar = pygame.Rect(0, SCREEN_HEIGHT - 40, SCREEN_WIDTH, 40)
        pygame.draw.rect(self.screen, (14, 16, 34), status_bar)
        pygame.draw.line(self.screen, COLOR_BORDER, (0, SCREEN_HEIGHT - 40),
                         (SCREEN_WIDTH, SCREEN_HEIGHT - 40), 2)
        sys_info = self.font_hint.render(
            f"SYSTEM READY  |  OCR: {OCR_INTERVAL}s  |  RES: {SCREEN_WIDTH}x{SCREEN_HEIGHT}",
            True, COLOR_TEXT_DIM)
        self.screen.blit(sys_info, (20, SCREEN_HEIGHT - 32))

    def _do_ocr(self, frame):
        result = self.ocr.recognize_text(frame, confidence_threshold=0.5)
        if not result["success"]:
            return
        text = result["text"].strip()
        self.last_text = text
        print(f"识别到文字: {text}")
        for keyword, data in VIDEO_MAP.items():
            if keyword in text:
                print(f"匹配关键词: {keyword}")
                self._play_video(data)
                break

    # ================================================================
    #  资源清理
    # ================================================================
    def _cleanup(self):
        self._stop_video()
        if self.camera:
            self.camera.stop()
        if self.ocr:
            self.ocr.cleanup()
        pygame.quit()
        print("系统资源已清理")


# ================================================================
#  入口
# ================================================================
if __name__ == "__main__":
    player = OCRVideoPlayer()
    player.run()