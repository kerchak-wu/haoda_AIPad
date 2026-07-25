# -*- coding: utf-8 -*-
"""
好搭AI派字体展示程序

功能：
  - 扫描 /home/cxdz/jupyter/assets/ 目录下的所有字体文件
  - 左侧显示字体列表，右侧预览选中字体的效果
  - 支持自定义预览文本
  - 支持调整字体大小
  - 显示字体文件名和类型

资源：
  字体目录：/home/cxdz/jupyter/assets/
"""

import os
import sys
import pygame

# ---------- 配置 ----------
WIDTH, HEIGHT = 1920, 1080
FONT_DIRS = [
    "/home/cxdz/jupyter/assets",
    "/usr/share/fonts/truetype",
    "/usr/share/fonts",
]
BG_IMAGE = os.path.join("images", "1.jpg")
SUPPORTED_FORMATS = (".ttf", ".ttc", ".otf", ".fon")

# 颜色
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)
ACCENT = (86, 196, 255)
ACCENT_DARK = (40, 130, 190)
GOLD = (255, 210, 90)
BTN_NORMAL = (255, 255, 255, 60)
BTN_HOVER = (86, 196, 255, 180)
BTN_SELECTED = (86, 196, 255, 200)
PANEL_COLOR = (0, 0, 0, 130)
PANEL_LIGHT = (30, 40, 60, 180)
EXIT_RED = (235, 87, 87)

# 默认预览文本
DEFAULT_PREVIEW_TEXT = "好搭AI派 字体展示 Hello World 123"


def scan_fonts():
    """扫描字体目录，返回字体文件路径列表"""
    fonts = []
    seen = set()
    for font_dir in FONT_DIRS:
        if not os.path.isdir(font_dir):
            continue
        for root, dirs, files in os.walk(font_dir):
            for f in sorted(files):
                if f.lower().endswith(SUPPORTED_FORMATS):
                    full_path = os.path.join(root, f)
                    if f not in seen:
                        seen.add(f)
                        fonts.append((f, full_path))
    return fonts


def get_font_type(filename):
    """根据扩展名获取字体类型描述"""
    ext = os.path.splitext(filename)[1].lower()
    types = {
        ".ttf": "TrueType",
        ".ttc": "TrueType Collection",
        ".otf": "OpenType",
        ".fon": "Bitmap Font",
    }
    return types.get(ext, "Unknown")


def safe_load_font(path, size):
    """安全加载字体，失败返回None"""
    try:
        return pygame.font.Font(path, size)
    except Exception:
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
        pygame.draw.rect(btn_surf, color, btn_surf.get_rect(), border_radius=12)
        pygame.draw.rect(btn_surf, ACCENT, btn_surf.get_rect(), 2, border_radius=12)
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


def draw_text_with_shadow(surface, text, font, color, shadow_color, pos, anchor="topleft"):
    shadow_surf = font.render(text, True, shadow_color)
    text_surf = font.render(text, True, color)
    rect = text_surf.get_rect(**{anchor: pos})
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            surface.blit(shadow_surf, (rect.x + dx, rect.y + dy))
    surface.blit(text_surf, rect)
    return rect


def wrap_text(text, font, max_width):
    """按像素宽度换行"""
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def main():
    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("好搭AI派 - 字体展示")
    clock = pygame.time.Clock()

    # ---------- 扫描字体 ----------
    font_files = scan_fonts()
    if not font_files:
        print("未找到字体文件，请检查字体目录路径")
        font_files = [("（未找到字体）", "")]

    # ---------- 备用字体（用于UI） ----------
    ui_font_name = None
    ui_font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    # 优先从扫描到的字体中找中文字体
    for fname, fpath in font_files:
        lower = fname.lower()
        if any(k in lower for k in ["simhei", "msyh", "deng", "noto", "wqy", "pingfang"]):
            ui_font_paths.insert(0, fpath)
            break

    for p in ui_font_paths:
        if os.path.exists(p):
            ui_font_name = p
            break

    def make_ui_font(size, bold=False):
        if ui_font_name:
            try:
                f = pygame.font.Font(ui_font_name, size)
                f.set_bold(bold)
                return f
            except Exception:
                pass
        return pygame.font.Font(None, size)

    font_title = make_ui_font(52, bold=True)
    font_subtitle = make_ui_font(28)
    font_list_title = make_ui_font(32, bold=True)
    font_list_item = make_ui_font(24)
    font_list_small = make_ui_font(20)
    font_btn = make_ui_font(26)
    font_btn_small = make_ui_font(22)
    font_info_label = make_ui_font(22, bold=True)
    font_info_value = make_ui_font(22)
    font_preview_label = make_ui_font(28, bold=True)
    font_size_label = make_ui_font(24)
    font_exit = make_ui_font(28, bold=True)

    # ---------- 背景图 ----------
    background = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception:
            background = None

    # ---------- 布局 ----------
    # 左侧：字体列表面板
    list_panel_x = 40
    list_panel_y = 120
    list_panel_w = 480
    list_panel_h = HEIGHT - 200

    # 右侧：预览区域
    preview_x = list_panel_x + list_panel_w + 40
    preview_y = list_panel_y
    preview_w = WIDTH - preview_x - 40
    preview_h = list_panel_h

    # 字体列表滚动
    list_top_pad = 60
    list_item_h = 56
    max_visible = (list_panel_h - list_top_pad - 20) // list_item_h
    scroll_offset = 0

    # 选中的字体索引
    selected_idx = 0

    # 预览设置
    preview_text = DEFAULT_PREVIEW_TEXT
    preview_size = 48
    min_preview_size = 12
    max_preview_size = 120

    # 预览字体缓存
    preview_font_cache = {}

    def get_preview_font(size):
        """获取当前选中字体的指定大小字体对象"""
        nonlocal preview_font_cache
        if not font_files or selected_idx >= len(font_files):
            return make_ui_font(size)
        fpath = font_files[selected_idx][1]
        if not fpath:
            return make_ui_font(size)
        key = (fpath, size)
        if key not in preview_font_cache:
            f = safe_load_font(fpath, size)
            if f is None:
                f = make_ui_font(size)
            preview_font_cache[key] = f
        return preview_font_cache[key]

    # ---------- 按钮 ----------
    # 退出按钮
    exit_btn = Button(
        (WIDTH - 160, 40, 120, 60), "退出", sys.exit,
        font_exit, color=(235, 87, 87, 120),
        hover_color=(235, 87, 87, 220),
        text_color=WHITE,
    )

    # 字体大小调整按钮
    size_btn_y = preview_y + preview_h - 80
    size_btn_w = 80
    size_btn_h = 50
    size_center_x = preview_x + preview_w // 2

    btn_size_down = Button(
        (size_center_x - 180, size_btn_y, size_btn_w, size_btn_h),
        "A-", lambda: change_size(-4), font_btn_small,
    )
    btn_size_up = Button(
        (size_center_x + 100, size_btn_y, size_btn_w, size_btn_h),
        "A+", lambda: change_size(4), font_btn_small,
    )

    # 重置预览文本按钮
    btn_reset_text = Button(
        (preview_x + preview_w - 200, preview_y + 10, 180, 44),
        "重置预览文本", reset_preview_text, font_btn_small,
    )

    buttons = [exit_btn, btn_size_down, btn_size_up, btn_reset_text]

    # ---------- 辅助函数 ----------
    def change_size(delta):
        nonlocal preview_size
        preview_size = max(min_preview_size, min(max_preview_size, preview_size + delta))
        preview_font_cache.clear()

    def reset_preview_text():
        nonlocal preview_text
        preview_text = DEFAULT_PREVIEW_TEXT

    def clamp_scroll():
        nonlocal scroll_offset
        max_scroll = max(0, len(font_files) - max_visible)
        scroll_offset = max(0, min(max_scroll, scroll_offset))

    clamp_scroll()

    # ---------- 文本输入状态 ----------
    text_input_active = False
    input_cursor_visible = True
    cursor_blink_tick = 0

    # 预览文本输入框
    input_box_x = preview_x + 20
    input_box_y = preview_y + 70
    input_box_w = preview_w - 40
    input_box_h = 50
    input_box_rect = pygame.Rect(input_box_x, input_box_y, input_box_w, input_box_h)

    # ---------- 主循环 ----------
    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif text_input_active:
                    if event.key == pygame.K_RETURN:
                        text_input_active = False
                    elif event.key == pygame.K_BACKSPACE:
                        preview_text = preview_text[:-1]
                    else:
                        if event.unicode and event.unicode.isprintable():
                            preview_text += event.unicode
                else:
                    if event.key == pygame.K_UP:
                        if selected_idx > 0:
                            selected_idx -= 1
                            if selected_idx < scroll_offset:
                                scroll_offset = selected_idx
                            preview_font_cache.clear()
                    elif event.key == pygame.K_DOWN:
                        if selected_idx < len(font_files) - 1:
                            selected_idx += 1
                            if selected_idx >= scroll_offset + max_visible:
                                scroll_offset = selected_idx - max_visible + 1
                            preview_font_cache.clear()
                    elif event.key == pygame.K_LEFT:
                        change_size(-4)
                    elif event.key == pygame.K_RIGHT:
                        change_size(4)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    # 检查退出等按钮
                    clicked = False
                    for b in buttons:
                        if b.click(event.pos):
                            clicked = True
                            break
                    if clicked:
                        continue

                    # 检查输入框点击
                    if input_box_rect.collidepoint(event.pos):
                        text_input_active = True
                    else:
                        text_input_active = False

                    # 检查字体列表点击
                    list_rect = pygame.Rect(list_panel_x + 10, list_panel_y + list_top_pad,
                                            list_panel_w - 20, list_panel_h - list_top_pad - 20)
                    if list_rect.collidepoint(event.pos):
                        rel_y = event.pos[1] - (list_panel_y + list_top_pad)
                        idx = scroll_offset + rel_y // list_item_h
                        if 0 <= idx < len(font_files):
                            selected_idx = idx
                            preview_font_cache.clear()
                elif event.button == 4:
                    # 滚轮向上
                    if pygame.Rect(list_panel_x, list_panel_y, list_panel_w, list_panel_h).collidepoint(mouse_pos):
                        scroll_offset = max(0, scroll_offset - 3)
                elif event.button == 5:
                    # 滚轮向下
                    if pygame.Rect(list_panel_x, list_panel_y, list_panel_w, list_panel_h).collidepoint(mouse_pos):
                        scroll_offset += 3
                        clamp_scroll()

        # 光标闪烁
        cursor_blink_tick += 1
        if cursor_blink_tick >= 30:
            cursor_blink_tick = 0
            input_cursor_visible = not input_cursor_visible

        # ====================================================
        # 绘制
        # ====================================================

        # ----- 背景 -----
        if background:
            screen.blit(background, (0, 0))
        else:
            screen.fill((20, 24, 34))

        # 半透明遮罩
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 70))
        screen.blit(overlay, (0, 0))

        # ----- 标题 -----
        draw_text_with_shadow(screen, "好搭AI派 字体展示", font_title, GOLD, (0, 0, 0),
                              (WIDTH // 2, 30), anchor="midtop")
        draw_text(screen, f"共 {len(font_files)} 个字体", font_subtitle, (200, 200, 200),
                  (WIDTH // 2, 90), anchor="midtop")

        # ----- 左侧：字体列表面板 -----
        list_panel = pygame.Surface((list_panel_w, list_panel_h), pygame.SRCALPHA)
        list_panel.fill(PANEL_COLOR)
        screen.blit(list_panel, (list_panel_x, list_panel_y))
        pygame.draw.rect(screen, ACCENT,
                         (list_panel_x, list_panel_y, list_panel_w, list_panel_h),
                         2, border_radius=12)

        # 列表标题
        draw_text(screen, "字体列表", font_list_title, ACCENT,
                  (list_panel_x + 20, list_panel_y + 16), anchor="topleft")
        draw_text(screen, f"{selected_idx + 1}/{len(font_files)}", font_list_small, (180, 180, 180),
                  (list_panel_x + list_panel_w - 20, list_panel_y + 24), anchor="topright")

        # 分割线
        pygame.draw.line(screen, (100, 120, 150),
                         (list_panel_x + 10, list_panel_y + list_top_pad - 10),
                         (list_panel_x + list_panel_w - 10, list_panel_y + list_top_pad - 10), 1)

        # 字体列表项
        list_content_rect = pygame.Rect(list_panel_x + 10, list_panel_y + list_top_pad,
                                        list_panel_w - 20, list_panel_h - list_top_pad - 20)
        # 裁剪区域
        screen.set_clip(list_content_rect)

        for i in range(max_visible):
            idx = scroll_offset + i
            if idx >= len(font_files):
                break
            fname, fpath = font_files[idx]
            item_y = list_panel_y + list_top_pad + i * list_item_h
            item_rect = pygame.Rect(list_panel_x + 15, item_y, list_panel_w - 30, list_item_h - 6)

            # 选中高亮
            if idx == selected_idx:
                sel_surf = pygame.Surface(item_rect.size, pygame.SRCALPHA)
                sel_surf.fill(BTN_SELECTED)
                screen.blit(sel_surf, item_rect.topleft)
                pygame.draw.rect(screen, GOLD, item_rect, 2, border_radius=8)
            else:
                # 悬停效果
                if item_rect.collidepoint(mouse_pos):
                    hover_surf = pygame.Surface(item_rect.size, pygame.SRCALPHA)
                    hover_surf.fill((255, 255, 255, 30))
                    screen.blit(hover_surf, item_rect.topleft)

            # 字体名称（尝试用该字体渲染名称，如果失败则用UI字体）
            display_name = os.path.splitext(fname)[0]
            name_color = WHITE if idx == selected_idx else TEXT_COLOR

            # 尝试用预览字体渲染名称（小尺寸）
            preview_name_font = None
            if fpath:
                try:
                    preview_name_font = pygame.font.Font(fpath, 20)
                except Exception:
                    preview_name_font = font_list_item
            else:
                preview_name_font = font_list_item

            name_surf = preview_name_font.render(display_name, True, name_color)
            # 限制宽度
            max_name_w = list_panel_w - 60
            if name_surf.get_width() > max_name_w:
                # 缩放适应
                scale = max_name_w / name_surf.get_width()
                new_h = int(name_surf.get_height() * scale)
                name_surf = pygame.transform.smoothscale(name_surf, (max_name_w, new_h))
            screen.blit(name_surf, (item_rect.x + 12, item_rect.y + 8))

            # 字体类型（小字）
            ftype = get_font_type(fname)
            type_color = GOLD if idx == selected_idx else (150, 180, 200)
            draw_text(screen, ftype, font_list_small, type_color,
                      (item_rect.x + 12, item_rect.y + item_rect.height - 22), anchor="topleft")

        screen.set_clip(None)

        # 滚动条
        if len(font_files) > max_visible:
            scroll_bar_x = list_panel_x + list_panel_w - 8
            scroll_bar_y = list_panel_y + list_top_pad
            scroll_bar_h = list_panel_h - list_top_pad - 20
            thumb_h = max(30, int(scroll_bar_h * (max_visible / len(font_files))))
            thumb_y = scroll_bar_y + int((scroll_bar_h - thumb_h) * (scroll_offset / (len(font_files) - max_visible)))
            pygame.draw.rect(screen, (100, 120, 150, 100),
                             (scroll_bar_x, scroll_bar_y, 4, scroll_bar_h), border_radius=2)
            pygame.draw.rect(screen, ACCENT,
                             (scroll_bar_x - 2, thumb_y, 8, thumb_h), border_radius=4)

        # ----- 右侧：预览区域 -----
        preview_panel = pygame.Surface((preview_w, preview_h), pygame.SRCALPHA)
        preview_panel.fill(PANEL_LIGHT)
        screen.blit(preview_panel, (preview_x, preview_y))
        pygame.draw.rect(screen, ACCENT,
                         (preview_x, preview_y, preview_w, preview_h),
                         2, border_radius=12)

        # 预览区域标题
        draw_text(screen, "字体预览", font_preview_label, GOLD,
                  (preview_x + 20, preview_y + 16), anchor="topleft")

        # 预览文本输入框
        input_bg = pygame.Surface((input_box_w, input_box_h), pygame.SRCALPHA)
        input_bg.fill((0, 0, 0, 80))
        screen.blit(input_bg, input_box_rect.topleft)
        border_color = GOLD if text_input_active else (100, 130, 160)
        pygame.draw.rect(screen, border_color, input_box_rect, 2, border_radius=8)

        # 输入提示
        if not preview_text:
            draw_text(screen, "点击此处输入自定义预览文本...", font_list_item, (120, 140, 160),
                      (input_box_rect.x + 15, input_box_rect.centery), anchor="midleft")
        else:
            # 计算可见文本（从右向左裁剪，显示最新输入）
            display_text = preview_text
            text_surf = font_list_item.render(display_text, True, WHITE)
            while text_surf.get_width() > input_box_w - 30 and len(display_text) > 0:
                display_text = display_text[1:]
                text_surf = font_list_item.render(display_text, True, WHITE)
            screen.blit(text_surf, (input_box_rect.x + 15, input_box_rect.centery - text_surf.get_height() // 2))

            # 光标
            if text_input_active and input_cursor_visible:
                cursor_x = input_box_rect.x + 15 + text_surf.get_width() + 2
                cursor_y = input_box_rect.y + 10
                cursor_h = input_box_h - 20
                pygame.draw.line(screen, WHITE, (cursor_x, cursor_y), (cursor_x, cursor_y + cursor_h), 2)

        # 当前字体信息
        info_y = input_box_y + input_box_h + 20
        if font_files and selected_idx < len(font_files):
            fname, fpath = font_files[selected_idx]
            ftype = get_font_type(fname)

            draw_text(screen, "字体名称：", font_info_label, ACCENT,
                      (preview_x + 20, info_y), anchor="topleft")
            draw_text(screen, fname, font_info_value, WHITE,
                      (preview_x + 130, info_y), anchor="topleft")

            draw_text(screen, "字体类型：", font_info_label, ACCENT,
                      (preview_x + 20, info_y + 32), anchor="topleft")
            draw_text(screen, ftype, font_info_value, GOLD,
                      (preview_x + 130, info_y + 32), anchor="topleft")

            draw_text(screen, "字体大小：", font_info_label, ACCENT,
                      (preview_x + preview_w // 2, info_y), anchor="topleft")
            draw_text(screen, f"{preview_size}px", font_info_value, GOLD,
                      (preview_x + preview_w // 2 + 110, info_y), anchor="topleft")

        # 预览主区域
        preview_area_top = info_y + 80
        preview_area_bottom = size_btn_y - 20
        preview_area_h = preview_area_bottom - preview_area_top

        # 预览背景框
        preview_area_rect = pygame.Rect(preview_x + 20, preview_area_top,
                                        preview_w - 40, preview_area_h)
        preview_bg = pygame.Surface(preview_area_rect.size, pygame.SRCALPHA)
        preview_bg.fill((255, 255, 255, 15))
        screen.blit(preview_bg, preview_area_rect.topleft)
        pygame.draw.rect(screen, (100, 130, 160), preview_area_rect, 1, border_radius=8)

        # 渲染预览文本（使用选中的字体）
        if preview_text:
            preview_font = get_preview_font(preview_size)
            lines = wrap_text(preview_text, preview_font, preview_w - 80)

            # 垂直居中
            total_h = len(lines) * (preview_size + 10)
            start_y = preview_area_top + (preview_area_h - total_h) // 2

            for i, line in enumerate(lines):
                line_surf = preview_font.render(line, True, WHITE)
                # 阴影
                shadow_surf = preview_font.render(line, True, (0, 0, 0))
                line_x = preview_x + (preview_w - line_surf.get_width()) // 2
                line_y = start_y + i * (preview_size + 10)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        screen.blit(shadow_surf, (line_x + dx, line_y + dy))
                screen.blit(line_surf, (line_x, line_y))
        else:
            draw_text(screen, "（预览文本为空，请在上方输入框输入文字）",
                      font_list_item, (150, 170, 190),
                      (preview_x + preview_w // 2, preview_area_top + preview_area_h // 2),
                      anchor="center")

        # 字体大小控制区
        draw_text(screen, "字体大小", font_size_label, ACCENT,
                  (size_center_x, size_btn_y - 10), anchor="midbottom")

        # 大小滑条
        slider_w = 200
        slider_h = 8
        slider_x = size_center_x - slider_w // 2
        slider_y = size_btn_y + size_btn_h + 15
        pygame.draw.rect(screen, (255, 255, 255, 60),
                         (slider_x, slider_y, slider_w, slider_h), border_radius=4)
        slider_ratio = (preview_size - min_preview_size) / (max_preview_size - min_preview_size)
        fill_w = int(slider_w * slider_ratio)
        pygame.draw.rect(screen, GOLD, (slider_x, slider_y, fill_w, slider_h), border_radius=4)
        # 滑块圆点
        knob_x = slider_x + fill_w
        pygame.draw.circle(screen, WHITE, (knob_x, slider_y + slider_h // 2), 8)
        pygame.draw.circle(screen, GOLD, (knob_x, slider_y + slider_h // 2), 6)

        # ----- 按钮 -----
        for b in buttons:
            b.update(mouse_pos)
            b.draw(screen)

        # ----- 底部快捷键提示 -----
        hint = "快捷键：↑↓ 选择字体 | ← → 调整大小 | 点击输入框编辑预览文本 | ESC 退出"
        draw_text(screen, hint, font_list_small, (180, 180, 180),
                  (WIDTH // 2, HEIGHT - 30), anchor="center")

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
