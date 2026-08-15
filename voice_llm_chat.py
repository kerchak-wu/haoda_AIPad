# -*- coding: utf-8 -*-
"""
语音大模型对话程序
- 窗口尺寸 1920 x 1080
- 按住界面下方圆形按钮录音，松开后自动完成：
  语音识别 -> 大模型对话 -> 语音合成 -> 播报
- 参考范例：4.语音AI\\7.按键大模型对话.hd
- 背景使用 images/1.jpg
- 运行前请修改下方的 USERNAME / PASSWORD 为你的好搭AI派账号
"""

import os
import threading
# Rockchip 平台兼容性补丁：必须在 import pygame 之前设置
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
import pygame
from voice_api import VoiceAPI
from audio_player import AudioPlayer
from audio_recorder import AudioRecorder

# ---------- 配置 ----------
WIDTH, HEIGHT = 1920, 1080
BG_IMAGE = os.path.join("images", "1.jpg")
RECORDINGS_DIR = "recordings"
RECORD_FILENAME = "voice_chat.wav"
ANSWER_FILENAME = "answer.wav"

# 好搭AI派账号 —— 请手动修改为你的用户名和密码
USERNAME = "username"
PASSWORD = "password"

VOICE_API_URL = "http://www.haohaodada.com/project/voiceAI/ApiZNBW.php"

# 颜色
WHITE = (255, 255, 255)
TEXT_COLOR = (255, 255, 255)
ACCENT = (86, 196, 255)
BTN_NORMAL = (255, 255, 255, 60)
BTN_HOVER = (86, 196, 255, 180)
BTN_RECORD = (235, 87, 87, 200)
BTN_RECORD_HOVER = (255, 120, 120, 230)
BTN_RECORDING = (255, 60, 60, 240)
BTN_DISABLED = (120, 120, 120, 180)
PANEL_COLOR = (0, 0, 0, 130)

# 状态
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_RECOGNIZING = "recognizing"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"
STATE_ERROR = "error"

STATE_TEXT = {
    STATE_IDLE: "空闲 - 按住下方按钮开始说话",
    STATE_RECORDING: "录音中... 松开按钮结束",
    STATE_RECOGNIZING: "语音识别中...",
    STATE_THINKING: "大模型思考中...",
    STATE_SPEAKING: "正在播报回答...",
    STATE_ERROR: "出现错误，请重试",
}


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


def wrap_text(text, font, max_width):
    """按像素宽度换行（支持中英文）"""
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


class Button:
    def __init__(self, rect, text, font, color=BTN_NORMAL, hover_color=BTN_HOVER,
                 text_color=TEXT_COLOR):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.hovered = False

    def update(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        color = self.hover_color if self.hovered else self.color
        btn_surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, color, btn_surf.get_rect(), border_radius=14)
        pygame.draw.rect(btn_surf, ACCENT, btn_surf.get_rect(), 2, border_radius=14)
        surface.blit(btn_surf, self.rect.topleft)
        text_surf = self.font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)


def main():
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        pass

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("语音大模型对话")
    clock = pygame.time.Clock()

    # 字体
    font_name = find_chinese_font()
    font_title = pygame.font.SysFont(font_name, 72, bold=True)
    font_status = pygame.font.SysFont(font_name, 44)
    font_role = pygame.font.SysFont(font_name, 36, bold=True)
    font_msg = pygame.font.SysFont(font_name, 34)
    font_btn = pygame.font.SysFont(font_name, 26, bold=True)
    font_exit = pygame.font.SysFont(font_name, 30, bold=True)
    font_small = pygame.font.SysFont(font_name, 26)

    # 背景图
    background = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print(f"背景加载失败: {e}")

    # 确保 recordings 目录存在
    if not os.path.isdir(RECORDINGS_DIR):
        os.makedirs(RECORDINGS_DIR, exist_ok=True)

    # 初始化语音API（需修改 USERNAME / PASSWORD）
    voice_api = VoiceAPI(VOICE_API_URL)
    token_result = voice_api.get_token(USERNAME, PASSWORD)
    if not token_result:
        print("❌ 认证失败，请检查用户名和密码")
    else:
        print("✅ 认证成功，开始语音大模型对话")

    player = AudioPlayer()
    recorder = AudioRecorder(sample_rate=16000, channels=1)

    # 共享状态
    state = STATE_IDLE
    state_lock = threading.Lock()
    error_msg = ""
    history = []  # [(role, text), ...] role: "user" / "assistant"

    def set_state(new_state, err=""):
        nonlocal state, error_msg
        with state_lock:
            state = new_state
            error_msg = err

    def get_state():
        with state_lock:
            return state

    def add_history(role, text):
        with state_lock:
            history.append((role, text))

    # 录音结束后：识别 -> 大模型 -> 合成 -> 播报（在子线程中执行，避免阻塞界面）
    def process_conversation():
        audio_path = os.path.join(RECORDINGS_DIR, RECORD_FILENAME)

        # 1. 语音识别
        set_state(STATE_RECOGNIZING)
        try:
            recognition_text = voice_api.voice_recognition(audio_path)
        except Exception as e:
            set_state(STATE_ERROR, f"语音识别异常: {e}")
            return
        if not recognition_text:
            set_state(STATE_ERROR, "语音识别失败或未识别到内容")
            return
        add_history("user", recognition_text)

        # 2. 大模型对话
        set_state(STATE_THINKING)
        try:
            llm_answer = voice_api.llm_chat(recognition_text + "，请尽量简短回答")
        except Exception as e:
            set_state(STATE_ERROR, f"大模型调用异常: {e}")
            return
        if not llm_answer:
            set_state(STATE_ERROR, "大模型返回为空")
            return
        add_history("assistant", llm_answer)

        # 3. 语音合成
        set_state(STATE_SPEAKING)
        answer_path = os.path.join(RECORDINGS_DIR, ANSWER_FILENAME)
        try:
            audio_data = voice_api.tts_synthesize(llm_answer, answer_path)
        except Exception as e:
            set_state(STATE_ERROR, f"语音合成异常: {e}")
            return
        if audio_data:
            try:
                player.play_file(answer_path)
            except Exception as e:
                set_state(STATE_ERROR, f"播放异常: {e}")
                return

        set_state(STATE_IDLE)

    # 录音按钮（大圆形，按住说话）
    record_btn_rect = pygame.Rect(0, 0, 140, 140)
    record_btn_rect.center = (WIDTH // 2, HEIGHT - 90)

    # 退出按钮（右上角）
    exit_btn = Button(
        (WIDTH - 180, 40, 140, 60), "退出程序", font_exit,
        color=(235, 87, 87, 120), hover_color=(235, 87, 87, 220),
    )

    recording = False
    record_start_tick = 0
    processing_thread = None

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if exit_btn.rect.collidepoint(event.pos):
                    running = False
                    continue
                # 按下圆形按钮 -> 开始录音（ERROR 状态下点击视为重试）
                if (record_btn_rect.collidepoint(event.pos)
                        and get_state() in (STATE_IDLE, STATE_ERROR) and not recording):
                    recording = True
                    record_start_tick = pygame.time.get_ticks()
                    try:
                        recorder.start_recording(device=None)
                        set_state(STATE_RECORDING)
                    except Exception as e:
                        set_state(STATE_ERROR, f"录音启动失败: {e}")
                        recording = False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                # 松开按钮 -> 结束录音；若录音为空则结束本次对话，等待下次
                if recording:
                    recording = False
                    duration = (pygame.time.get_ticks() - record_start_tick) / 1000.0
                    try:
                        audio_data = recorder.stop_recording()
                        if audio_data is None or duration < 0.3:
                            # 录音为空或时长过短，结束本次对话，回到空闲等待下次
                            set_state(STATE_IDLE)
                        else:
                            file_path = recorder.save_audio(audio_data, filename=RECORD_FILENAME)
                            if file_path:
                                processing_thread = threading.Thread(
                                    target=process_conversation, daemon=True)
                                processing_thread.start()
                            else:
                                set_state(STATE_IDLE)
                    except Exception as e:
                        set_state(STATE_ERROR, f"录音结束异常: {e}")

        # ----- 绘制背景 -----
        if background:
            screen.blit(background, (0, 0))
        else:
            screen.fill((20, 24, 34))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 90))
        screen.blit(overlay, (0, 0))

        cur_state = get_state()

        # ----- 标题 -----
        draw_text(screen, "语音大模型对话", font_title, TEXT_COLOR,
                  (WIDTH // 2, 70), anchor="midtop")

        # ----- 状态显示 -----
        status_color = ACCENT
        if cur_state == STATE_RECORDING:
            status_color = (255, 120, 120)
        elif cur_state == STATE_ERROR:
            status_color = (255, 150, 150)
        elif cur_state == STATE_SPEAKING:
            status_color = (130, 255, 170)
        elif cur_state in (STATE_RECOGNIZING, STATE_THINKING):
            status_color = (255, 220, 130)

        status_text = STATE_TEXT.get(cur_state, "")
        if cur_state == STATE_ERROR and error_msg:
            status_text = error_msg
        draw_text(screen, status_text, font_status, status_color,
                  (WIDTH // 2, 215), anchor="center")

        # ----- 对话记录面板 -----
        panel_x = 160
        panel_y = 285
        panel_w = WIDTH - 320
        panel_h = HEIGHT - 285 - 220
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill(PANEL_COLOR)
        screen.blit(panel, (panel_x, panel_y))
        pygame.draw.rect(screen, ACCENT, (panel_x, panel_y, panel_w, panel_h), 2, border_radius=12)

        draw_text(screen, "对话记录", font_role, ACCENT,
                  (panel_x + 24, panel_y + 16), anchor="topleft")

        # 渲染历史（最新在底部，向上排布）
        with state_lock:
            history_snapshot = list(history)
        if history_snapshot:
            content_w = panel_w - 80
            # 把每条记录拆成多行
            rendered = []  # (role, line_text)
            for role, text in reversed(history_snapshot):
                lines = wrap_text(text, font_msg, content_w - 60)
                for ln in reversed(lines):
                    rendered.append((role, ln))
                rendered.append(("gap", ""))
            y = panel_y + panel_h - 26
            top_limit = panel_y + 70
            for role, ln in rendered:
                if role == "gap":
                    y -= 18
                    continue
                color = ACCENT if role == "user" else (150, 255, 180)
                label = "我：" if role == "user" else "AI："
                ts = font_msg.render(label + ln, True, color)
                y -= ts.get_height() + 8
                if y < top_limit:
                    break
                screen.blit(ts, (panel_x + 40, y))
        else:
            draw_text(screen, "按住下方圆形按钮说话，松开后将自动识别并与大模型对话",
                      font_msg, (200, 200, 200),
                      (WIDTH // 2, panel_y + panel_h // 2), anchor="center")

        # ----- 录音按钮（圆形）-----
        btn_center = record_btn_rect.center
        btn_radius = record_btn_rect.width // 2
        hovering = record_btn_rect.collidepoint(mouse_pos)

        if cur_state == STATE_RECORDING:
            btn_color = BTN_RECORDING
            btn_label = ["录音中", "松开结束"]
            # 脉冲外圈
            pulse = abs((pygame.time.get_ticks() // 8) % 80 - 40)
            glow_surf = pygame.Surface((record_btn_rect.width + 80, record_btn_rect.height + 80),
                                       pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 60, 60, 60),
                               (glow_surf.get_width() // 2, glow_surf.get_height() // 2),
                               btn_radius + 10 + pulse // 4)
            screen.blit(glow_surf, glow_surf.get_rect(center=btn_center))
        elif cur_state == STATE_ERROR:
            btn_color = BTN_RECORD_HOVER if hovering else BTN_RECORD
            btn_label = ["点击重试"]
        elif cur_state == STATE_IDLE:
            btn_color = BTN_RECORD_HOVER if hovering else BTN_RECORD
            btn_label = ["按住说话"]
        else:
            btn_color = BTN_DISABLED
            btn_label = ["处理中"]

        btn_surf = pygame.Surface((record_btn_rect.width, record_btn_rect.height), pygame.SRCALPHA)
        pygame.draw.circle(btn_surf, btn_color, (btn_radius, btn_radius), btn_radius)
        pygame.draw.circle(btn_surf, (255, 255, 255, 200), (btn_radius, btn_radius), btn_radius, 3)
        screen.blit(btn_surf, record_btn_rect.topleft)

        # 按钮文字（多行居中）
        total_h = sum(font_btn.size(l)[1] for l in btn_label) + 10 * (len(btn_label) - 1)
        ly = btn_center[1] - total_h // 2
        for l in btn_label:
            ts = font_btn.render(l, True, WHITE)
            screen.blit(ts, ts.get_rect(center=(btn_center[0], ly + ts.get_height() // 2)))
            ly += ts.get_height() + 10

        # 按钮下方提示
        if cur_state == STATE_IDLE or cur_state == STATE_RECORDING:
            hint = "按住按钮说话，松开自动识别并对话 | ESC 退出"
        else:
            hint = "请等待当前对话完成..."
        draw_text(screen, hint, font_small, (200, 200, 200),
                  (WIDTH // 2, record_btn_rect.top - 24), anchor="center")

        # ----- 退出按钮 -----
        exit_btn.update(mouse_pos)
        exit_btn.draw(screen)

        pygame.display.flip()
        clock.tick(60)

    # 退出前等待处理线程
    if processing_thread and processing_thread.is_alive():
        processing_thread.join(timeout=2)
    try:
        player.cleanup()
    except Exception:
        pass
    pygame.quit()


if __name__ == "__main__":
    main()
