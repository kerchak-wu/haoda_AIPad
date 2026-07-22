# -*- coding: utf-8 -*-
"""
音乐播放器程序
- 窗口尺寸 1920 x 1080
- 播放 recordings 文件夹下的音乐文件
- 背景使用 images/1.jpg
- 提供退出程序按钮

布局（自上而下）：
  标题 -> 当前曲目 -> 「播放列表」大标题 -> 播放列表面板 -> 时间轴/进度条 -> 功能键 -> 快捷键提示
"""

import os
import sys
import pygame

# ---------- 配置 ----------
WIDTH, HEIGHT = 1920, 1080
MUSIC_DIR = "recordings"
BG_IMAGE = os.path.join("images", "1.jpg")
SUPPORTED_FORMATS = (".mp3", ".wav", ".ogg", ".flac")

# 颜色
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)
ACCENT = (86, 196, 255)
ACCENT_DARK = (40, 130, 190)
BTN_NORMAL = (255, 255, 255, 60)
BTN_HOVER = (86, 196, 255, 180)
PANEL_COLOR = (0, 0, 0, 130)
EXIT_RED = (235, 87, 87)


def load_music_list():
    """扫描 recordings 文件夹下的音乐文件"""
    if not os.path.isdir(MUSIC_DIR):
        return []
    files = []
    for f in sorted(os.listdir(MUSIC_DIR)):
        if f.lower().endswith(SUPPORTED_FORMATS):
            files.append(f)
    return files


def find_chinese_font():
    """寻找系统中可用的中文字体"""
    candidates = [
        "simhei", "microsoftyahei", "msyh", "pingfang",
        "notosanscjksc", "notosanscjk", "wenquanyimicrohei",
        "wqymicrohei", "stheiti", "arialunicodems",
    ]
    available = pygame.font.get_fonts()
    for name in candidates:
        if name in available:
            return name
    # 直接尝试常见字体路径
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


class Button:
    """通用按钮"""

    def __init__(self, rect, text, action, font, color=BTN_NORMAL,
                 hover_color=BTN_HOVER, text_color=TEXT_COLOR):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
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
        pygame.draw.rect(btn_surf, color, btn_surf.get_rect(), border_radius=14)
        pygame.draw.rect(btn_surf, ACCENT, btn_surf.get_rect(), 2, border_radius=14)
        surface.blit(btn_surf, self.rect.topleft)

        text_surf = self.font.render(self.text, True, self.text_color if self.enabled else (150, 150, 150))
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def click(self, pos):
        if self.enabled and self.rect.collidepoint(pos):
            self.action()
            return True
        return False


def draw_text(surface, text, font, color, pos, anchor="topleft"):
    surf = font.render(text, True, color)
    rect = surf.get_rect(**{anchor: pos})
    surface.blit(surf, rect)
    return rect


def format_time(seconds):
    if seconds < 0:
        seconds = 0
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def main():
    pygame.init()
    # 音频初始化（失败时仍可运行界面）
    try:
        pygame.mixer.init()
        audio_ok = True
    except pygame.error:
        audio_ok = False

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("音乐播放器")
    clock = pygame.time.Clock()

    # 字体
    font_name = find_chinese_font()
    font_title = pygame.font.SysFont(font_name, 64, bold=True)
    font_list_title = pygame.font.SysFont(font_name, 50, bold=True)   # 播放列表大标题
    font_song = pygame.font.SysFont(font_name, 40)
    font_btn = pygame.font.SysFont(font_name, 34)
    font_small = pygame.font.SysFont(font_name, 26)
    font_exit = pygame.font.SysFont(font_name, 30, bold=True)

    # 背景图
    background = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print(f"背景加载失败: {e}")
            background = None

    # 音乐列表
    music_files = load_music_list()
    current_idx = 0
    playing = False
    # 位置跟踪状态（手动计时，避免依赖 get_pos/get_length 的兼容性问题）
    current_length = 0.0      # 当前曲目总时长（秒）
    play_start_tick = 0       # 上次 play/unpause 时的 pygame 时钟刻度
    paused_pos = 0.0          # 暂停前已累计的播放位置（秒）

    def get_position():
        """返回当前播放位置（秒）"""
        if playing:
            elapsed = (pygame.time.get_ticks() - play_start_tick) / 1000.0
            pos = paused_pos + elapsed
        else:
            pos = paused_pos
        if current_length > 0:
            pos = min(pos, current_length)
        return max(0.0, pos)

    def play_index(idx):
        nonlocal current_idx, playing, current_length, play_start_tick, paused_pos
        if not music_files or not audio_ok:
            return
        idx = idx % len(music_files)
        current_idx = idx
        path = os.path.join(MUSIC_DIR, music_files[idx])
        # 立即停止当前播放，避免切换时旧曲目继续发声
        pygame.mixer.music.stop()
        try:
            # 用 Sound 预读取时长（pygame.mixer.music 没有 get_length）
            try:
                snd = pygame.mixer.Sound(path)
                current_length = snd.get_length()
            except Exception:
                current_length = 0.0
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            play_start_tick = pygame.time.get_ticks()
            paused_pos = 0.0
            playing = True
        except Exception as e:
            print(f"播放失败: {e}")
            playing = False

    def toggle_play():
        nonlocal playing, play_start_tick, paused_pos
        if not music_files or not audio_ok:
            return
        if not pygame.mixer.music.get_busy() and not playing:
            play_index(current_idx)
            return
        if playing:
            pygame.mixer.music.pause()
            paused_pos = get_position()
            playing = False
        else:
            pygame.mixer.music.unpause()
            play_start_tick = pygame.time.get_ticks()
            playing = True

    def next_track():
        if music_files:
            play_index(current_idx + 1)

    def prev_track():
        if music_files:
            play_index(current_idx - 1)

    def stop_track():
        nonlocal playing, paused_pos
        if audio_ok:
            pygame.mixer.music.stop()
        paused_pos = 0.0
        playing = False

    # 音量控制（0-100）
    volume = 70

    def set_volume(v):
        nonlocal volume
        volume = max(0, min(100, int(v)))
        if audio_ok:
            pygame.mixer.music.set_volume(volume / 100.0)

    def volume_up():
        set_volume(volume + 10)

    def volume_down():
        set_volume(volume - 10)

    # 初始化音量
    set_volume(volume)

    # 按钮位置（底部控制栏）：播放控制组 + 音量控制组
    btn_y = HEIGHT - 130
    btn_w, btn_h = 170, 80
    gap = 36
    sep_gap = 90  # 两组之间的分隔间距
    group1_w = btn_w * 4 + gap * 3
    group2_w = btn_w * 2 + gap
    total_w = group1_w + sep_gap + group2_w
    start_x = (WIDTH - total_w) // 2

    btn_prev = Button((start_x, btn_y, btn_w, btn_h), "上一首", prev_track, font_btn)
    btn_play = Button((start_x + (btn_w + gap), btn_y, btn_w, btn_h), "播放", toggle_play, font_btn)
    btn_next = Button((start_x + (btn_w + gap) * 2, btn_y, btn_w, btn_h), "下一首", next_track, font_btn)
    btn_stop = Button((start_x + (btn_w + gap) * 3, btn_y, btn_w, btn_h), "停止", stop_track, font_btn)

    vol_group_x = start_x + group1_w + sep_gap
    btn_vol_down = Button((vol_group_x, btn_y, btn_w, btn_h), "音量 -", volume_down, font_btn)
    btn_vol_up = Button((vol_group_x + (btn_w + gap), btn_y, btn_w, btn_h), "音量 +", volume_up, font_btn)

    # 退出按钮（右上角）
    exit_btn = Button(
        (WIDTH - 180, 40, 140, 60), "退出程序", sys.exit,
        font_exit, color=(235, 87, 87, 120),
        hover_color=(235, 87, 87, 220),
        text_color=WHITE,
    )

    buttons = [btn_prev, btn_play, btn_next, btn_stop, btn_vol_down, btn_vol_up, exit_btn]

    # ---------- 布局常量（自上而下） ----------
    # 标题      y=80
    # 当前曲目  y=180
    # 播放列表大标题 y=250 (font_list_title 50pt)，下边缘约 y=295
    list_title_y = 250
    list_top = 320                 # 列表面板顶部（下移，避免与大标题重叠）
    # 时间轴在播放列表下方、功能键上方
    progress_bar_y = btn_y - 140   # 进度条 y（上移，为音量显示留出空间）
    time_text_y = progress_bar_y + 22
    list_bottom = progress_bar_y - 30   # 列表面板底部，留出与进度条的间距
    line_h = 48
    max_visible = (list_bottom - list_top) // line_h

    # 进度条矩形（每帧重绘时也用同一位置）
    progress_bar_rect = pygame.Rect(160, progress_bar_y, WIDTH - 320, 14)

    # 进度条拖动状态
    dragging_progress = False

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # 检查进度条点击
                if progress_bar_rect.collidepoint(event.pos):
                    if music_files and audio_ok and current_length > 0:
                        ratio = (event.pos[0] - progress_bar_rect.x) / progress_bar_rect.width
                        ratio = max(0, min(1, ratio))
                        target = ratio * current_length
                        pygame.mixer.music.play(start=target)
                        play_start_tick = pygame.time.get_ticks()
                        paused_pos = target
                        playing = True
                        dragging_progress = True
                else:
                    for b in buttons:
                        if b.click(event.pos):
                            break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                dragging_progress = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    toggle_play()
                elif event.key == pygame.K_RIGHT:
                    next_track()
                elif event.key == pygame.K_LEFT:
                    prev_track()
                elif event.key == pygame.K_UP:
                    volume_up()
                elif event.key == pygame.K_DOWN:
                    volume_down()

        # ----- 绘制背景 -----
        if background:
            screen.blit(background, (0, 0))
        else:
            screen.fill((20, 24, 34))

        # 半透明遮罩，提升文字可读性
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 90))
        screen.blit(overlay, (0, 0))

        # ----- 标题 -----
        draw_text(screen, "♪ 音乐播放器", font_title, TEXT_COLOR, (WIDTH // 2, 80), anchor="midtop")

        # ----- 当前曲目信息 -----
        if music_files:
            name = os.path.splitext(music_files[current_idx])[0]
            draw_text(screen, f"正在播放：{name}", font_song, ACCENT,
                      (WIDTH // 2, 180), anchor="center")
        else:
            msg = f"未找到音乐文件，请将音乐放入 {MUSIC_DIR}/ 文件夹"
            draw_text(screen, msg, font_song, (255, 200, 120),
                      (WIDTH // 2, 180), anchor="center")
            if not audio_ok:
                draw_text(screen, "（音频模块初始化失败，无法播放声音）",
                          font_small, (255, 150, 150), (WIDTH // 2, 230), anchor="center")

        # ----- 播放列表大标题 -----
        draw_text(screen, "播放列表", font_list_title, ACCENT,
                  (WIDTH // 2, list_title_y), anchor="midtop")

        # ----- 播放列表面板 -----
        list_panel = pygame.Surface((WIDTH - 320, list_bottom - list_top), pygame.SRCALPHA)
        list_panel.fill((0, 0, 0, 120))
        screen.blit(list_panel, (160, list_top))

        if music_files:
            for i in range(min(max_visible, len(music_files))):
                name = music_files[i]
                display = f"{i + 1}. {name}"
                color = ACCENT if i == current_idx else TEXT_COLOR
                draw_text(screen, display, font_small, color,
                          (190, list_top + 10 + i * line_h), anchor="topleft")
        else:
            draw_text(screen, "（列表为空）", font_small, (200, 200, 200),
                      (WIDTH // 2, list_top + 20), anchor="center")

        # ----- 时间轴 / 进度条（播放列表下方、功能键上方） -----
        pygame.draw.rect(screen, (255, 255, 255, 60), progress_bar_rect, border_radius=7)

        progress_ratio = 0
        if music_files and audio_ok and current_length > 0:
            pos = get_position()
            progress_ratio = min(1, pos / current_length)
            # 时间文字（左侧已播、右侧总时长）
            draw_text(screen, format_time(pos), font_small, TEXT_COLOR,
                      (progress_bar_rect.x, time_text_y), anchor="topleft")
            draw_text(screen, format_time(current_length), font_small, TEXT_COLOR,
                      (progress_bar_rect.right, time_text_y), anchor="topright")

        if progress_ratio > 0:
            fill_rect = pygame.Rect(progress_bar_rect.x, progress_bar_rect.y,
                                     int(progress_bar_rect.width * progress_ratio),
                                     progress_bar_rect.height)
            pygame.draw.rect(screen, ACCENT, fill_rect, border_radius=7)

        # ----- 音量显示（进度条下方、功能键上方） -----
        vol_bar_w = 360
        vol_bar_h = 16
        vol_bar_x = (WIDTH - vol_bar_w) // 2
        vol_bar_y = btn_y - 52
        vol_cy = vol_bar_y + vol_bar_h // 2
        vol_bar_rect = pygame.Rect(vol_bar_x, vol_bar_y, vol_bar_w, vol_bar_h)
        # 左侧「音量」标签
        draw_text(screen, "音量", font_small, (200, 200, 200),
                  (vol_bar_rect.x - 16, vol_cy), anchor="midright")
        # 音量条背景
        pygame.draw.rect(screen, (255, 255, 255, 60), vol_bar_rect, border_radius=8)
        # 音量条填充
        vol_fill_w = int(vol_bar_w * (volume / 100.0))
        if vol_fill_w > 0:
            vol_fill = pygame.Rect(vol_bar_x, vol_bar_y, vol_fill_w, vol_bar_h)
            pygame.draw.rect(screen, ACCENT, vol_fill, border_radius=8)
        # 右侧百分比
        draw_text(screen, f"{volume}%", font_small, TEXT_COLOR,
                  (vol_bar_rect.right + 16, vol_cy), anchor="midleft")

        # ----- 按钮 -----
        # 更新播放按钮文本
        btn_play.text = "暂停" if playing else "播放"
        for b in buttons:
            b.update(mouse_pos)
            b.draw(screen)

        # ----- 提示信息 -----
        hint = "快捷键：空格 播放/暂停 | ← → 切换曲目 | ↑ ↓ 调节音量 | ESC 退出"
        draw_text(screen, hint, font_small, (200, 200, 200),
                  (WIDTH // 2, HEIGHT - 30), anchor="center")

        # 自动播放下一首
        if playing and music_files and audio_ok:
            if not pygame.mixer.music.get_busy() and not dragging_progress:
                next_track()

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
