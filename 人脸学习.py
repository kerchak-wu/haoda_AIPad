# -*- coding: utf-8 -*-
"""
人脸学习与识别程序
- 窗口尺寸 1920 x 1080
- 使用外接摄像头（camera_id=-1）学习并识别人脸
- 摄像头画面直接整合到主窗口中（不再弹出独立预览窗口）
- 两种模式：
  1. 学习人脸：输入姓名 -> 点击「开始学习」 -> 系统自动分配人脸ID -> 保存到 face_data/face_db.json
  2. 人脸识别：实时识别摄像头中的人脸，按已保存的 ID 匹配出姓名与置信度
- 人脸数据库保存在 face_data/face_db.json，方便其他程序调用
- 背景使用 images/1.jpg
- 参考范例：5.AI视觉算法\\08.人脸学习1.hd、09.人脸学习2.hd、10.人脸识别.hd

新增功能：
  - 摄像头窗口整合到主程序窗口（后台线程采集，不卡顿）
  - 「查看人脸库」按钮：弹窗查看已有人脸库的所有详细信息（ID、姓名、登记时间）
  - 删除功能：在右侧人脸列表中点击「删除」按钮可移除人脸库中的已有信息

其他程序调用示例（直接 import 本模块即可）：
    from face_recognition_app import get_face_name, load_face_database, list_known_faces
    name = get_face_name(face_id)      # 根据人脸ID获取姓名，未登记返回 None
    db  = load_face_database()         # 获取整个人脸库 {id: {"name":..., "created_at":...}}
    all_faces = list_known_faces()     # 获取 [(id, name), ...] 列表
"""

import os
import json
import time
import datetime
import threading
import pygame

# ---------- 配置 ----------
WIDTH, HEIGHT = 1920, 1080
CAMERA_ID = -1               # 外接摄像头（-1 自动选择；如不正确可改为 0/1/2 指定具体摄像头）
CAMERA_W, CAMERA_H = 1280, 720
BG_IMAGE = os.path.join("images", "1.jpg")

FACE_DB_DIR = "face_data"
FACE_DB_FILE = os.path.join(FACE_DB_DIR, "face_db.json")

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


# ---------- 人脸数据库（供其他程序调用） ----------
def load_face_database(path=FACE_DB_FILE):
    """加载人脸数据库，返回 {face_id(str): {"name":..., "created_at":...}} 字典"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("faces", {})
    except Exception:
        return {}


def save_face_database(faces, path=FACE_DB_FILE):
    """保存人脸数据库"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"faces": faces}, f, ensure_ascii=False, indent=2)


def get_face_name(face_id, path=FACE_DB_FILE):
    """根据人脸ID获取姓名，未登记返回 None。其他程序可直接调用此函数"""
    faces = load_face_database(path)
    info = faces.get(str(face_id))
    return info["name"] if info else None


def list_known_faces(path=FACE_DB_FILE):
    """返回所有已知人脸列表 [(face_id, name), ...]"""
    faces = load_face_database(path)
    return [(fid, info["name"]) for fid, info in faces.items()]


def extract_face_id(result):
    """从 learn_new_face() 的返回值中提取人脸ID（兼容 int / dict / 字符串）"""
    if result is None:
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, dict):
        for key in ("id", "face_id", "ID", "Id"):
            if key in result:
                try:
                    return int(result[key])
                except (TypeError, ValueError):
                    return result[key]
    if isinstance(result, str):
        try:
            return int(result)
        except ValueError:
            return None
    return None


# ---------- 通用工具 ----------
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
    surf = font.render(text, True, color)
    rect = surf.get_rect(**{anchor: pos})
    surface.blit(surf, rect)
    return rect


def draw_panel(surface, x, y, w, h, fill=PANEL_COLOR, border=ACCENT, radius=12, border_w=2):
    """绘制半透明面板"""
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill(fill)
    surface.blit(panel, (x, y))
    pygame.draw.rect(surface, border, (x, y, w, h), border_w, border_radius=radius)


class Button:
    """通用按钮"""

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


# ---------- 主程序 ----------
def main():
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

    # 背景图片
    background = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print(f"背景加载失败: {e}")

    # ----- 初始化视觉系统（外接摄像头） -----
    import cv2
    import numpy as np
    from camera_vision_system_v3 import create_vision_system_v3

    print("视觉系统初始化中...")
    vision_system = create_vision_system_v3(
        camera_id=CAMERA_ID, width=CAMERA_W, height=CAMERA_H,
        enable_basic=False, enable_advanced=False)
    camera_ok = vision_system.open_camera()
    if not camera_ok:
        print("❌ 摄像头打开失败，请检查外接摄像头连接（可修改 CAMERA_ID 指定摄像头编号）")
    else:
        print("✅ 外接摄像头已打开")
    vision_system.detection_config.enable_face_recognition = True
    vision_system._init_detectors()
    print("face_recognition 算法已启用")
    vision_system.threaded_system.start_background_detection(show_preview=False)
    print("摄像头画面已整合到主窗口")

    # ----- 人脸数据库 -----
    faces = load_face_database()

    # ============================================================
    # 布局参数
    # ============================================================
    # 顶部
    TITLE_Y = 12
    EXIT_BTN_Y = 12
    MODE_BTN_Y = 75

    # 左侧面板：摄像头 + 下方提示/历史
    panel_x, panel_y = 60, 145
    panel_w, panel_h = 1180, 850          # 145 - 995

    # 摄像头画面（放大）
    cam_disp_w, cam_disp_h = 1100, 520
    cam_x = panel_x + 40                   # 100
    cam_y = panel_y + 105                  # 250 → 画面 250-770

    # 摄像头下方区域（操作提示 / 识别历史）
    below_cam_y = cam_y + cam_disp_h + 20  # 790
    below_cam_h = panel_y + panel_h - below_cam_y - 15  # 190

    # 右侧上方面板（姓名输入/学习 或 识别结果）
    rtop_x, rtop_y = 1280, 145
    rtop_w, rtop_h = 580, 240             # 145 - 385

    # 查看人脸库按钮
    view_btn_y = 400                       # 400 - 455

    # 右侧人脸库面板（缩小）
    side_x, side_y = 1280, 470
    side_w, side_h = 580, 525             # 470 - 995

    # 底部
    TOAST_Y = 1005
    HINT_Y = 1055

    # ============================================================
    # 状态变量
    # ============================================================
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
    DETAIL_PAGE_SIZE = 8

    delete_confirm_id = None
    delete_status = ""
    delete_status_color = DIM_TEXT
    delete_status_timer = 0

    face_list_scroll = 0

    # ============================================================
    # 摄像头后台采集线程
    # ============================================================
    latest_cam_surface = None
    cam_surface_lock = threading.Lock()
    cam_thread_running = True
    cam_error_logged = False

    def cvframe_to_surface(frame):
        if frame is None:
            return None
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_transposed = np.transpose(frame_rgb, (1, 0, 2))
            surface = pygame.surfarray.make_surface(frame_transposed)
            return pygame.transform.smoothscale(surface, (cam_disp_w, cam_disp_h))
        except Exception:
            return None

    def camera_capture_loop():
        nonlocal cam_error_logged, latest_cam_surface
        while cam_thread_running:
            if not camera_ok:
                time.sleep(0.2)
                continue
            try:
                frame = vision_system.capture_frame()
                surface = cvframe_to_surface(frame)
                if surface is not None:
                    with cam_surface_lock:
                        latest_cam_surface = surface
                    cam_error_logged = False
                else:
                    if not cam_error_logged:
                        print("摄像头画面为空，可能正在初始化...")
                        cam_error_logged = True
            except Exception as e:
                if not cam_error_logged:
                    print(f"摄像头画面采集异常: {e}")
                    cam_error_logged = True
            time.sleep(0.04)

    cam_thread = threading.Thread(target=camera_capture_loop, daemon=True)
    cam_thread.start()

    # ============================================================
    # 人脸学习
    # ============================================================
    def start_learn():
        nonlocal learning, learn_status, learn_status_color, faces
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
        learn_status = "正在学习人脸，请正对摄像头..."
        learn_status_color = WARN

        def worker():
            nonlocal learning, learn_status, learn_status_color, faces
            try:
                result = vision_system.learn_new_face()
                face_id = extract_face_id(result)
                if face_id is None:
                    learn_status = f"学习失败，未获取到ID。返回信息：{result}"
                    learn_status_color = ERROR
                else:
                    fid = str(face_id)
                    faces[fid] = {
                        "name": name,
                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    save_face_database(faces)
                    learn_status = f"✅ 学习成功！ID={face_id}  姓名={name}"
                    learn_status_color = SUCCESS
                    print(f"人脸学习成功：ID={face_id} 姓名={name} -> {FACE_DB_FILE}")
            except Exception as e:
                learn_status = f"学习异常：{e}"
                learn_status_color = ERROR
            finally:
                with learn_lock:
                    learning = False

        threading.Thread(target=worker, daemon=True).start()

    # ============================================================
    # 删除人脸
    # ============================================================
    def delete_face(face_id):
        nonlocal faces, delete_status, delete_status_color, delete_status_timer
        fid = str(face_id)
        if fid in faces:
            name = faces[fid].get("name", "")
            del faces[fid]
            save_face_database(faces)
            delete_status = f"✅ 已删除：ID={face_id}  姓名={name}"
            delete_status_color = SUCCESS
            delete_status_timer = 180
            print(f"人脸已删除：ID={face_id} 姓名={name}")
        else:
            delete_status = f"未找到 ID={face_id} 的人脸"
            delete_status_color = ERROR
            delete_status_timer = 180

    # ============================================================
    # 按钮定义
    # ============================================================
    btn_learn_mode = Button((640, MODE_BTN_Y, 260, 52), "学习人脸", font_btn)
    btn_recog_mode = Button((1000, MODE_BTN_Y, 260, 52), "人脸识别", font_btn)
    btn_start_learn = Button((rtop_x + 20, rtop_y + 155, rtop_w - 40, 50), "开始学习人脸", font_btn,
                             color=(86, 196, 255, 120), hover_color=(86, 196, 255, 220))
    btn_exit = Button((1740, EXIT_BTN_Y, 140, 48), "退出程序", font_exit,
                      color=(235, 87, 87, 120), hover_color=(235, 87, 87, 220))
    btn_view_faces = Button((side_x, view_btn_y, side_w, 50), "查看人脸库详细信息", font_btn,
                            color=(130, 255, 170, 120), hover_color=(130, 255, 170, 220))

    # 弹窗按钮
    btn_close_detail = Button((WIDTH // 2 + 500, 160, 100, 48), "关闭", font_btn,
                              color=(235, 87, 87, 120), hover_color=(235, 87, 87, 220))
    btn_detail_prev = Button((WIDTH // 2 - 150, HEIGHT - 100, 130, 48), "上一页", font_btn)
    btn_detail_next = Button((WIDTH // 2 + 20, HEIGHT - 100, 130, 48), "下一页", font_btn)

    # 删除确认按钮
    btn_confirm_delete = Button((WIDTH // 2 - 210, HEIGHT // 2 + 40, 180, 55), "确认删除", font_btn,
                                color=(235, 87, 87, 150), hover_color=(235, 87, 87, 220))
    btn_cancel_delete = Button((WIDTH // 2 + 30, HEIGHT // 2 + 40, 180, 55), "取消", font_btn)

    # 输入框
    input_rect = pygame.Rect(rtop_x + 20, rtop_y + 80, rtop_w - 40, 50)

    # 动态删除按钮区域列表
    delete_btn_rects = []

    # ============================================================
    # 主循环
    # ============================================================
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
                            all_items = list(faces.items())
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
                        items_count = len(faces)
                        list_top = side_y + 90
                        list_h = side_h - 90 - 25
                        entry_h = 50
                        max_visible = list_h // entry_h
                        max_scroll = max(0, items_count - max_visible)
                        face_list_scroll = min(max_scroll, face_list_scroll + 1)

        # ----- 识别处理 -----
        if (mode == MODE_RECOGNIZE and camera_ok
                and not show_face_detail and delete_confirm_id is None):
            try:
                vision_system.result_accessor.refresh_results()
                if recog_cooldown > 0:
                    recog_cooldown -= 1
                if vision_system.result_accessor.get_face_count() > 0:
                    face_id = vision_system.result_accessor.get_face_id()
                    try:
                        confidence = round(vision_system.result_accessor.get_face_confidence(), 3)
                    except Exception:
                        confidence = None
                    if (recog_cooldown == 0) or (face_id != last_recog_id):
                        name = get_face_name(face_id) if face_id is not None else None
                        time_str = datetime.datetime.now().strftime("%H:%M:%S")
                        recog_history.append((time_str, face_id, name, confidence))
                        if len(recog_history) > 20:
                            recog_history.pop(0)
                        last_recog_id = face_id
                        recog_cooldown = RECOG_COOLDOWN_FRAMES
            except Exception as e:
                print(f"识别异常: {e}")

        if delete_status_timer > 0:
            delete_status_timer -= 1

        # ============================================================
        # 绘制
        # ============================================================
        if background:
            screen.blit(background, (0, 0))
        else:
            screen.fill((20, 24, 34))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 90))
        screen.blit(overlay, (0, 0))

        # ----- 标题（上移） -----
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

        # ============================================================
        # 左侧面板：摄像头 + 下方提示/历史
        # ============================================================
        draw_panel(screen, panel_x, panel_y, panel_w, panel_h)

        # 面板标题
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

        # ----- 摄像头画面 -----
        with cam_surface_lock:
            cam_surface = latest_cam_surface

        # 状态指示
        status_text = "● 已连接" if camera_ok else "○ 未连接"
        status_color = SUCCESS if camera_ok else ERROR
        draw_text(screen, status_text, font_small, status_color,
                  (panel_x + panel_w - 30, panel_y + 25), anchor="topright")

        if cam_surface:
            screen.blit(cam_surface, (cam_x, cam_y))
        else:
            placeholder = pygame.Surface((cam_disp_w, cam_disp_h))
            placeholder.fill((30, 30, 40))
            screen.blit(placeholder, (cam_x, cam_y))
            ph_text = "摄像头未打开" if not camera_ok else "画面加载中..."
            draw_text(screen, ph_text, font_msg, DIM_TEXT,
                      (cam_x + cam_disp_w // 2, cam_y + cam_disp_h // 2), anchor="center")

        pygame.draw.rect(screen, ACCENT, (cam_x, cam_y, cam_disp_w, cam_disp_h), 2, border_radius=8)

        # 识别模式检测指示
        if mode == MODE_RECOGNIZE and camera_ok:
            try:
                face_count = vision_system.result_accessor.get_face_count()
                if face_count > 0:
                    draw_text(screen, "● 检测到人脸", font_small, SUCCESS,
                              (cam_x + 12, cam_y + 12), anchor="topleft")
            except Exception:
                pass

        # ----- 摄像头下方：操作提示 / 识别历史 -----
        if mode == MODE_LEARN:
            draw_text(screen, "操作提示", font_label, ACCENT,
                      (panel_x + 30, below_cam_y), anchor="topleft")
            tips = [
                "1. 在右侧输入框输入姓名",
                "2. 点击「开始学习人脸」或按回车键",
                "3. 学习时请正对摄像头保持不动",
                "4. 学习成功后自动保存至 face_db.json",
                "5. 其他程序可 import get_face_name 调用",
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
                label = name if name else "未知"
                color = SUCCESS if name else WARN
                line = f"[{t_str}]  ID={fid}  {label}  置信度={conf}"
                draw_text(screen, line, font_small, color,
                          (panel_x + 50, below_cam_y + 35 + i * line_h))
                i += 1
            if not recog_history:
                draw_text(screen, "（暂无识别记录）", font_small, DIM_TEXT,
                          (panel_x + 50, below_cam_y + 35), anchor="topleft")

        # ============================================================
        # 右侧上方面板：姓名输入/学习 或 识别结果
        # ============================================================
        draw_panel(screen, rtop_x, rtop_y, rtop_w, rtop_h)

        if mode == MODE_LEARN:
            draw_text(screen, "学习控件", font_subtitle, ACCENT,
                      (rtop_x + 20, rtop_y + 15), anchor="topleft")

            # 姓名标签 + 输入框
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

            # 开始学习按钮
            btn_start_learn.enabled = not learning
            btn_start_learn.text = "学习中..." if learning else "开始学习人脸"
            btn_start_learn.update(mouse_pos)
            btn_start_learn.draw(screen)

            # 状态信息
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
                    result_line = f"识别到：{name}"
                    result_color = SUCCESS
                else:
                    result_line = "未知人脸" if fid is not None else "未检测到"
                    result_color = WARN
                draw_text(screen, result_line, font_big_result, result_color,
                          (rtop_cx, rtop_y + 70), anchor="center")
                detail = f"人脸ID：{fid}    置信度：{conf}"
                draw_text(screen, detail, font_msg, DIM_TEXT,
                          (rtop_cx, rtop_y + 130), anchor="center")
                draw_text(screen, f"时间：{t_str}", font_small, DIM_TEXT,
                          (rtop_cx, rtop_y + 165), anchor="center")

        # ============================================================
        # 查看人脸库按钮（在人脸库上方）
        # ============================================================
        btn_view_faces.update(mouse_pos)
        btn_view_faces.draw(screen)

        # ============================================================
        # 右侧人脸库面板（缩小）
        # ============================================================
        delete_btn_rects = []
        draw_panel(screen, side_x, side_y, side_w, side_h)

        draw_text(screen, "已保存人脸库", font_subtitle, ACCENT,
                  (side_x + 20, side_y + 12), anchor="topleft")
        draw_text(screen, f"共 {len(faces)} 人  |  点击「删除」移除  |  滚轮滚动",
                  font_small, DIM_TEXT, (side_x + 20, side_y + 52), anchor="topleft")

        list_top = side_y + 85
        list_h = side_h - 85 - 25
        entry_h = 50
        max_visible = list_h // entry_h
        items = list(faces.items())

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

            line = f"ID {fid}  :  {info['name']}"
            draw_text(screen, line, font_msg, TEXT_COLOR,
                      (side_x + 20, entry_y + 4))
            draw_text(screen, info.get("created_at", ""), font_small, DIM_TEXT,
                      (side_x + 20, entry_y + 28))

            # 删除按钮
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
            scroll_info = f"{start_idx + 1}-{end_idx} / {len(items)}"
            draw_text(screen, scroll_info, font_small, DIM_TEXT,
                      (side_x + side_w - 20, side_y + side_h - 20), anchor="topright")

        # ----- 删除操作提示 -----
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
        draw_text(screen, hint, font_small, DIM_TEXT,
                  (WIDTH // 2, HINT_Y), anchor="center")

        # ============================================================
        # 查看人脸库详细信息弹窗
        # ============================================================
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

            draw_text(screen, "人脸库详细信息", font_title, TEXT_COLOR,
                      (modal_x + 40, modal_y + 20), anchor="topleft")
            draw_text(screen, f"共 {len(faces)} 人    数据文件：{FACE_DB_FILE}",
                      font_small, DIM_TEXT,
                      (modal_x + 40, modal_y + 75), anchor="topleft")

            btn_close_detail.update(mouse_pos)
            btn_close_detail.draw(screen)

            all_items = list(faces.items())
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
                draw_text(screen, f"人脸 ID：{fid}", font_label, ACCENT,
                          (modal_x + 40, ey + 8), anchor="topleft")
                draw_text(screen, f"姓名：{info.get('name', '')}", font_label, TEXT_COLOR,
                          (modal_x + 300, ey + 8), anchor="topleft")
                draw_text(screen, f"登记时间：{info.get('created_at', '')}",
                          font_small, DIM_TEXT,
                          (modal_x + 40, ey + 42), anchor="topleft")

            if not all_items:
                draw_text(screen, "人脸库为空，请先学习人脸", font_big_result, DIM_TEXT,
                          (modal_x + modal_w // 2, modal_y + modal_h // 2), anchor="center")

            draw_text(screen, f"第 {detail_page + 1} / {total_pages} 页", font_small, DIM_TEXT,
                      (WIDTH // 2, HEIGHT - 115), anchor="center")
            btn_detail_prev.enabled = detail_page > 0
            btn_detail_next.enabled = detail_page < total_pages - 1
            btn_detail_prev.update(mouse_pos)
            btn_detail_prev.draw(screen)
            btn_detail_next.update(mouse_pos)
            btn_detail_next.draw(screen)

        # ============================================================
        # 删除确认弹窗
        # ============================================================
        if delete_confirm_id is not None:
            dialog_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            dialog_overlay.fill((0, 0, 0, 180))
            screen.blit(dialog_overlay, (0, 0))

            dlg_w, dlg_h = 520, 240
            dlg_x = WIDTH // 2 - dlg_w // 2
            dlg_y = HEIGHT // 2 - dlg_h // 2
            dlg_panel = pygame.Surface((dlg_w, dlg_h), pygame.SRCALPHA)
            dlg_panel.fill((45, 35, 40, 245))
            screen.blit(dlg_panel, (dlg_x, dlg_y))
            pygame.draw.rect(screen, EXIT_RED, (dlg_x, dlg_y, dlg_w, dlg_h), 3, border_radius=12)

            face_name = faces.get(str(delete_confirm_id), {}).get("name", "")
            draw_text(screen, "确认删除？", font_subtitle, EXIT_RED,
                      (WIDTH // 2, dlg_y + 25), anchor="midtop")
            draw_text(screen, f"将删除：ID={delete_confirm_id}  姓名={face_name}",
                      font_msg, TEXT_COLOR,
                      (WIDTH // 2, dlg_y + 85), anchor="center")
            draw_text(screen, "（仅删除姓名关联，不影响视觉系统内部数据）",
                      font_small, DIM_TEXT,
                      (WIDTH // 2, dlg_y + 125), anchor="center")

            btn_confirm_delete.update(mouse_pos)
            btn_confirm_delete.draw(screen)
            btn_cancel_delete.update(mouse_pos)
            btn_cancel_delete.draw(screen)

        pygame.display.flip()
        clock.tick(30)

    # ----- 清理资源 -----
    cam_thread_running = False
    time.sleep(0.1)
    try:
        vision_system.cleanup()
        print("视觉系统资源已清理")
    except Exception:
        pass
    pygame.quit()


if __name__ == "__main__":
    main()
