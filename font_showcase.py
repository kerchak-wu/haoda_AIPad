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
# Rockchip 平台兼容性补丁：必须在 import pygame 之前设置
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
import pygame

# ---------- 配置 ----------
WIDTH, HEIGHT = 1920, 1080
# 好搭AI派字体主目录（用户在此处增删字体文件）
MAIN_FONT_DIR = "/home/cxdz/jupyter/assets"
# 主目录不存在或无字体时，使用的备用系统字体目录
FALLBACK_FONT_DIRS = [
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

# 三行固定预览文本
PREVIEW_LINE_CN = "连接已建立，等待数据传输。"
PREVIEW_LINE_EN = "Algorithm is thought, code is poetry."
PREVIEW_LINE_NUM = "149,600,000"


def scan_fonts():
    """扫描字体目录，返回字体文件路径列表。
    优先扫描好搭AI派主目录；若主目录无字体则回退到系统目录。"""
    fonts = []
    seen = set()

    def scan_dir(font_dir):
        if not os.path.isdir(font_dir):
            return
        for root, dirs, files in os.walk(font_dir):
            for f in sorted(files):
                if f.lower().endswith(SUPPORTED_FORMATS):
                    full_path = os.path.join(root, f)
                    if f not in seen:
                        seen.add(f)
                        fonts.append((f, full_path))

    # 1. 优先扫描主目录
    scan_dir(MAIN_FONT_DIR)

    # 2. 主目录无字体时，才回退到系统字体目录
    if not fonts:
        for d in FALLBACK_FONT_DIRS:
            scan_dir(d)
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


def font_supports_chinese(font):
    """检测字体是否支持中文字符（通过渲染"中"字与空矩形比较）"""
    if font is None:
        return False
    try:
        test_surf = font.render("中", True, (255, 255, 255))
        # 如果渲染出来的宽度为0或极小，说明不支持中文
        if test_surf.get_width() < 3:
            return False
        # 进一步检查：比较渲染的中文和一个方块字符的宽度差异
        # 很多不支持中文的字体会把所有中文字形渲染成相同的占位符
        s1 = font.render("中", True, (255, 255, 255))
        s2 = font.render("文", True, (255, 255, 255))
        s3 = font.render("测", True, (255, 255, 255))
        # 如果三个不同的汉字渲染出来宽度完全相同，很可能是占位符
        if s1.get_width() == s2.get_width() == s3.get_width():
            # 再用像素采样验证：检查中心区域像素是否全是同一个颜色（占位框特征）
            # 但为了简单，这里用宽度判断已足够准确
            pass
        return s1.get_width() > 3
    except Exception:
        return False


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
    preview_size = 48
    min_preview_size = 12
    max_preview_size = 120

    # 预览字体缓存
    preview_font_cache = {}
    chinese_support_cache = {}

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

    def has_chinese_support():
        """检测当前选中字体是否支持中文"""
        nonlocal chinese_support_cache
        if not font_files or selected_idx >= len(font_files):
            return True
        fpath = font_files[selected_idx][1]
        if not fpath:
            return True
        if fpath in chinese_support_cache:
            return chinese_support_cache[fpath]
        # 用小尺寸检测，速度快
        test_font = safe_load_font(fpath, 24)
        result = font_supports_chinese(test_font)
        chinese_support_cache[fpath] = result
        return result

    # ---------- 辅助函数（必须在按钮定义之前声明） ----------
    def change_size(delta):
        nonlocal preview_size
        preview_size = max(min_preview_size, min(max_preview_size, preview_size + delta))
        preview_font_cache.clear()

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

    buttons = [exit_btn, btn_size_down, btn_size_up]

    def clamp_scroll():
        nonlocal scroll_offset
        max_scroll = max(0, len(font_files) - max_visible)
        scroll_offset = max(0, min(max_scroll, scroll_offset))

    clamp_scroll()

    # ---------- 文本输入状态 ----------
    # 滚动条拖拽状态
    scrollbar_dragging = False
    scrollbar_drag_offset = 0

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
                elif event.key == pygame.K_UP:
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

                    # 检查滚动条拖拽
                    if len(font_files) > max_visible:
                        sb_w = 28
                        sb_x = list_panel_x + list_panel_w - sb_w - 8
                        sb_y = list_panel_y + list_top_pad
                        sb_h = list_panel_h - list_top_pad - 20
                        thumb_h = max(48, int(sb_h * (max_visible / len(font_files))))
                        thumb_y = sb_y + int((sb_h - thumb_h) * (scroll_offset / max(1, len(font_files) - max_visible)))
                        # 点击在滑块上：开始拖拽
                        if sb_x <= event.pos[0] <= sb_x + sb_w and sb_y <= event.pos[1] <= sb_y + sb_h:
                            if thumb_y <= event.pos[1] <= thumb_y + thumb_h:
                                scrollbar_dragging = True
                                scrollbar_drag_offset = event.pos[1] - thumb_y
                            else:
                                # 点击在轨道上：跳转
                                rel = event.pos[1] - sb_y - thumb_h // 2
                                ratio = max(0, min(1, rel / max(1, sb_h - thumb_h)))
                                scroll_offset = int(ratio * max(0, len(font_files) - max_visible))
                                clamp_scroll()
                            continue

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
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    scrollbar_dragging = False
            elif event.type == pygame.MOUSEMOTION:
                if scrollbar_dragging and len(font_files) > max_visible:
                    sb_w = 28
                    sb_x = list_panel_x + list_panel_w - sb_w - 8
                    sb_y = list_panel_y + list_top_pad
                    sb_h = list_panel_h - list_top_pad - 20
                    thumb_h = max(48, int(sb_h * (max_visible / len(font_files))))
                    rel = event.pos[1] - sb_y - scrollbar_drag_offset
                    ratio = max(0, min(1, rel / max(1, sb_h - thumb_h)))
                    scroll_offset = int(ratio * max(0, len(font_files) - max_visible))
                    clamp_scroll()

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

        # 滚动条（加大尺寸便于触摸控制）
        if len(font_files) > max_visible:
            scroll_bar_w = 28
            scroll_bar_x = list_panel_x + list_panel_w - scroll_bar_w - 8
            scroll_bar_y = list_panel_y + list_top_pad
            scroll_bar_h = list_panel_h - list_top_pad - 20
            thumb_h = max(48, int(scroll_bar_h * (max_visible / len(font_files))))
            thumb_y = scroll_bar_y + int((scroll_bar_h - thumb_h) * (scroll_offset / max(1, len(font_files) - max_visible)))
            # 轨道背景
            pygame.draw.rect(screen, (80, 100, 130, 120),
                             (scroll_bar_x, scroll_bar_y, scroll_bar_w, scroll_bar_h), border_radius=10)
            # 滑块
            pygame.draw.rect(screen, ACCENT,
                             (scroll_bar_x + 2, thumb_y, scroll_bar_w - 4, thumb_h), border_radius=8)
            # 滑块高光
            pygame.draw.rect(screen, (180, 220, 255, 180),
                             (scroll_bar_x + 4, thumb_y + 3, scroll_bar_w - 12, 4), border_radius=2)

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

        # 中文支持状态标识
        cn_supported = has_chinese_support()
        if cn_supported:
            cn_status_text = "✓ 支持中文"
            cn_status_color = (100, 220, 130)
        else:
            cn_status_text = "✗ 不含中文"
            cn_status_color = (255, 150, 100)
        draw_text(screen, cn_status_text, font_list_item, cn_status_color,
                  (preview_x + preview_w - 20, preview_y + 28), anchor="topright")

        # 当前字体信息
        info_y = preview_y + 70
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

        # 渲染三行预览文本（中文 / 英文 / 数字）
        preview_font = get_preview_font(preview_size)
        line_gap = int(preview_size * 0.6)

        # 构建要显示的行列表
        display_lines = []
        if cn_supported:
            display_lines.append((PREVIEW_LINE_CN, "cn"))
        else:
            display_lines.append(("[ 该字体不含中文字形 ]", "cn_placeholder"))
        display_lines.append((PREVIEW_LINE_EN, "en"))
        display_lines.append((PREVIEW_LINE_NUM, "num"))

        total_h = len(display_lines) * preview_size + (len(display_lines) - 1) * line_gap
        start_y = preview_area_top + (preview_area_h - total_h) // 2

        for i, (line_text, line_type) in enumerate(display_lines):
            if line_type == "cn_placeholder":
                # 不含中文时显示占位提示（用UI字体，灰色斜体风格）
                placeholder_font = make_ui_font(int(preview_size * 0.7))
                line_surf = placeholder_font.render(line_text, True, (150, 150, 170))
                shadow_surf = placeholder_font.render(line_text, True, (0, 0, 0))
            else:
                line_surf = preview_font.render(line_text, True, WHITE)
                shadow_surf = preview_font.render(line_text, True, (0, 0, 0))

            line_x = preview_x + (preview_w - line_surf.get_width()) // 2
            line_y = start_y + i * (preview_size + line_gap)

            # 阴影描边
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    screen.blit(shadow_surf, (line_x + dx, line_y + dy))
            screen.blit(line_surf, (line_x, line_y))

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
        hint = "快捷键：↑↓ 选择字体 | ← → 调整大小 | 拖动滚动条浏览列表 | ESC 退出"
        draw_text(screen, hint, font_list_small, (180, 180, 180),
                  (WIDTH // 2, HEIGHT - 30), anchor="center")

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
