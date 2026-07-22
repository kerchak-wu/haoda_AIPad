# -*- coding: utf-8 -*-
"""
音乐播放器程序
- 窗口尺寸 1920 x 1080
- 播放 recordings 文件夹下的音乐文件
- 背景使用 images/1.jpg
- 提供退出程序按钮
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

    # 播放控制
    def play_index(idx):
        nonlocal current_idx, playing
        if not music_files or not audio_ok:
            return
        idx = idx % len(music_files)
        current_idx = idx
        path = os.path.join(MUSIC_DIR, music_files[idx])
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            playing = True
        except Exception as e:
            print(f"播放失败: {e}")
            playing = False

    def toggle_play():
        nonlocal playing
        if not music_files or not audio_ok:
            return
        if not pygame.mixer.music.get_busy() and not playing:
            play_index(current_idx)
            return
        if playing:
            pygame.mixer.music.pause()
            playing = False
        else:
            pygame.mixer.music.unpause()
            playing = True

    def next_track():
        if music_files:
            play_index(current_idx + 1)

    def prev_track():
        if music_files:
            play_index(current_idx - 1)

    def stop_track():
        nonlocal playing
        if audio_ok:
            pygame.mixer.music.stop()
        playing = False

    # 按钮位置（底部控制栏）
    btn_y = HEIGHT - 130
    btn_w, btn_h = 180, 80
    gap = 40
    total_w = btn_w * 4 + gap * 3
    start_x = (WIDTH - total_w) // 2

    btn_prev = Button((start_x, btn_y, btn_w, btn_h), "上一首", prev_track, font_btn)
    btn_play = Button((start_x + (btn_w + gap), btn_y, btn_w, btn_h), "播放", toggle_play, font_btn)
    btn_next = Button((start_x + (btn_w + gap) * 2, btn_y, btn_w, btn_h), "下一首", next_track, font_btn)
    btn_stop = Button((start_x + (btn_w + gap) * 3, btn_y, btn_w, btn_h), "停止", stop_track, font_btn)

    # 退出按钮（右上角）
    exit_btn = Button(
        (WIDTH - 180, 40, 140, 60), "退出程序", sys.exit,
        font_exit, color=(235, 87, 87, 120),
        hover_color=(235, 87, 87, 220),
        text_color=WHITE,
    )

    buttons = [btn_prev, btn_play, btn_next, btn_stop, exit_btn]

    # 播放列表显示范围
    list_top = 280
    list_bottom = btn_y - 40
    line_h = 50
    max_visible = (list_bottom - list_top) // line_h

    # 进度条拖动状态
    dragging_progress = False

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        mouse_click = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_click = True
                # 检查进度条点击
                if progress_bar_rect.collidepoint(event.pos):
                    if music_files and audio_ok:
                        ratio = (event.pos[0] - progress_bar_rect.x) / progress_bar_rect.width
                        ratio = max(0, min(1, ratio))
                        if pygame.mixer.music.get_length() > 0:
                            pygame.mixer.music.play(start=ratio * pygame.mixer.music.get_length())
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

        # ----- 进度条 -----
        progress_bar_rect = pygame.Rect(160, 240, WIDTH - 320, 14)
        pygame.draw.rect(screen, (255, 255, 255, 60), progress_bar_rect, border_radius=7)

        progress_ratio = 0
        if music_files and audio_ok:
            length = pygame.mixer.music.get_length()
            pos = pygame.mixer.music.get_pos() / 1000.0
            if length > 0 and pos >= 0:
                progress_ratio = min(1, pos / length)
                # 时间文字
                draw_text(screen, format_time(pos), font_small, TEXT_COLOR,
                          (progress_bar_rect.x, 250), anchor="topleft")
                draw_text(screen, format_time(length), font_small, TEXT_COLOR,
                          (progress_bar_rect.right, 250), anchor="topright")

        if progress_ratio > 0:
            fill_rect = pygame.Rect(progress_bar_rect.x, progress_bar_rect.y,
                                    int(progress_bar_rect.width * progress_ratio),
                                    progress_bar_rect.height)
            pygame.draw.rect(screen, ACCENT, fill_rect, border_radius=7)

        # ----- 播放列表 -----
        list_panel = pygame.Surface((WIDTH - 320, list_bottom - list_top), pygame.SRCALPHA)
        list_panel.fill((0, 0, 0, 120))
        screen.blit(list_panel, (160, list_top))

        draw_text(screen, "播放列表", font_btn, ACCENT, (180, list_top - 50), anchor="topleft")

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

        # ----- 按钮 -----
        # 更新播放按钮文本
        btn_play.text = "暂停" if playing else "播放"
        for b in buttons:
            b.update(mouse_pos)
            b.draw(screen)

        # ----- 提示信息 -----
        hint = "快捷键：空格 播放/暂停 | ← → 切换曲目 | ESC 退出"
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
