# -*- coding: utf-8 -*-
"""
实时翻译 - 好搭AI派
功能：按住屏幕按钮说话（中文或英文），松开后自动完成：
     语音识别 -> 中英互译 -> 语音合成播报，原文与译文以对话气泡显示在屏幕上
硬件：无外设（仅板载麦克风 / 扬声器）
依赖：voice_api / audio_recorder / audio_player / pygame-ce
界面：1920x1080 窗口，浅色对话气泡风格；底部提示置于按钮上方安全区，避免显示不全
"""

import os
import sys
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'

# 官方库位于设备 /home/cxdz/jupyter/lib（管理器运行时由 PYTHONPATH 提供，
# SSH 直启时缺该变量，这里显式补上以保证任何方式启动均可运行）
_LIB_DIR = '/home/cxdz/jupyter/lib'
if os.path.isdir(_LIB_DIR) and _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import datetime
import re
import threading
import hashlib

import pygame
pygame.display.init()
pygame.font.init()
try:
    pygame.mixer.init()
except pygame.error:
    pass

from voice_api import VoiceAPI
from audio_recorder import AudioRecorder
from audio_player import AudioPlayer

# ===== 日志标准模式（追加写 + 块缓冲 + stdout 分路）=====
_LOG_DIR = 'logs'
if not os.path.exists(_LOG_DIR):
    os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(
    _LOG_DIR,
    '实时翻译_%s.log' % datetime.datetime.now().strftime('%Y%m%d')
)


class _Logger:
    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log = open(file_path, 'a', buffering=-1, encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()


sys.stdout = _Logger(_LOG_FILE)
sys.stderr = sys.stdout

print('=' * 60)
print('实时翻译 启动于 %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print('日志文件: %s' % _LOG_FILE)
print('=' * 60)

# ===== 配置 =====
WIDTH, HEIGHT = 1920, 1080
VOICE_API_URL = "http://www.haohaodada.com/project/voiceAI/ApiZNBW.php"
VOICE_USERNAME = ''   # 凭据只保存在好搭AI派设备上的程序副本中，本地文件禁止写入（登录前请在设备副本中填写）
VOICE_PASSWORD = ''

RECORDINGS_DIR = 'recordings'
RECORD_FILENAME = 'translate_record.wav'   # 录音临时文件（每次覆盖）
FONT_PATH = '/home/cxdz/jupyter/assets/msyh.ttc'

MIN_RECORD_SEC = 0.5        # 短于该时长的录音直接丢弃
BUBBLE_MAX_W = 1100         # 气泡内文字最大宽度

# ===== 配色（浅色天空蓝主题）=====
BG_TOP = (228, 243, 255)
BG_BOTTOM = (198, 228, 252)
TITLE_COLOR = (36, 88, 158)
SRC_BUBBLE_BG = (255, 255, 255)          # 原文气泡：白
SRC_BUBBLE_BORDER = (168, 198, 226)
SRC_TEXT = (62, 64, 72)
DST_BUBBLE_BG = (206, 233, 252)          # 译文气泡：浅蓝
DST_BUBBLE_BORDER = (86, 164, 255)
DST_TEXT = (18, 84, 160)
TAG_ZH = (232, 120, 56)                  # 中文标签：橙
TAG_EN = (58, 130, 220)                  # 英文标签：蓝
HINT_COLOR = (96, 120, 148)
BTN_IDLE = (242, 112, 100)               # 按住说话按钮：珊瑚红
BTN_IDLE_HOVER = (248, 128, 116)
BTN_RECORDING = (232, 66, 56)
BTN_DISABLED = (150, 158, 170)
BTN_SPEAKING = (66, 186, 130)
WHITE = (255, 255, 255)

# ===== 状态 =====
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_RECOGNIZING = "recognizing"
STATE_TRANSLATING = "translating"
STATE_SPEAKING = "speaking"
STATE_ERROR = "error"

STATE_TEXT = {
    STATE_IDLE: "空闲 - 按住下方按钮说话",
    STATE_RECORDING: "录音中... 松开按钮结束",
    STATE_RECOGNIZING: "语音识别中...",
    STATE_TRANSLATING: "翻译中...",
    STATE_SPEAKING: "正在播报译文...",
    STATE_ERROR: "出现错误，请重试",
}

# TTS 发音修正表：实测（2026-11-04）该 TTS 引擎会把 in/is/be 按字母拼读，
# 替换为同音写法后正常按词发音（句中时长缩短 0.19~0.46s）。
# 仅对送 TTS 的英文播报文本做整词替换，屏幕显示文本不受影响。
_TTS_FIX_MAP = [('in', 'inn'), ('is', 'iss'), ('be', 'bee')]

_re_han = re.compile(u'[\u4e00-\u9fff]')


def has_chinese(text):
    """判断文本是否含中文字符 → 决定翻译方向"""
    return _re_han.search(text) is not None


def tts_pronunciation_fix(text):
    for orig, fixed in _TTS_FIX_MAP:
        text = re.sub(r'\b%s\b' % orig, fixed, text, flags=re.IGNORECASE)
    return text


def wrap_text(text, font, max_width):
    """按像素宽度换行：英文优先按空格断词，中文/无空格文本按字符断行"""
    lines = []
    for para in text.split('\n'):
        current = ''
        for word in para.split(' '):
            trial = word if not current else current + ' ' + word
            if font.size(trial)[0] <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
            if font.size(word)[0] <= max_width:
                current = word
            else:
                # 单个词整行放不下（中文整句 / 无空格长串）→ 按字符切
                chunk = ''
                for ch in word:
                    t2 = chunk + ch
                    if font.size(t2)[0] <= max_width:
                        chunk = t2
                    else:
                        lines.append(chunk)
                        chunk = ch
                current = chunk
        if current:
            lines.append(current)
    return lines


def draw_text(surface, text, font, color, pos, anchor="topleft"):
    surf = font.render(text, True, color)
    rect = surf.get_rect(**{anchor: pos})
    surface.blit(surf, rect)
    return rect


def make_gradient_bg(w, h, top, bottom):
    """生成上下渐变背景"""
    bg = pygame.Surface((w, h))
    for y in range(h):
        t = y / float(h - 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
        pygame.draw.line(bg, color, (0, y), (w, y))
    return bg.convert()


def load_font(size, bold=False):
    """加载设备字体，失败时回退系统字体"""
    try:
        if os.path.exists(FONT_PATH):
            return pygame.font.Font(FONT_PATH, size)
    except Exception as e:
        print('加载设备字体失败: %s' % e)
    name = None
    for cand in ("microsoftyahei", "simhei", "notosanscjk", "wenquanyimicrohei"):
        if cand in pygame.font.get_fonts():
            name = cand
            break
    return pygame.font.SysFont(name, size, bold=bold)


def main():
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("实时翻译（中英互译）")
    clock = pygame.time.Clock()

    # 字体
    font_title = load_font(56, bold=True)
    font_tag = load_font(30, bold=True)
    font_msg = load_font(38)
    font_status = load_font(36, bold=True)
    font_btn = load_font(34, bold=True)
    font_small = load_font(26)

    background = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM)

    # 标题双向箭头图标（⇄ 字符在设备字体中缺字形，改用 icons/swap.png），
    # 加载失败时标题绘制会回退为自绘箭头图形
    swap_icon = None
    icon_path = os.path.join('icons', 'swap.png')
    if os.path.exists(icon_path):
        try:
            swap_icon = pygame.image.load(icon_path).convert_alpha()
        except Exception as e:
            print('加载图标失败: %s' % e)
    if swap_icon is not None:
        probe = font_title.render(u'中', True, TITLE_COLOR)
        icon_size = max(32, probe.get_height() - 18)
        swap_icon = pygame.transform.scale(swap_icon, (icon_size, icon_size))

    # recordings 目录
    if not os.path.isdir(RECORDINGS_DIR):
        os.makedirs(RECORDINGS_DIR, exist_ok=True)

    # 语音 API 初始化
    voice_api = VoiceAPI(VOICE_API_URL)
    token_ok = False
    try:
        token_ok = bool(voice_api.get_token(VOICE_USERNAME, VOICE_PASSWORD))
    except Exception as e:
        print('认证异常: %s' % e)
    print('语音AI认证: %s' % ('成功' if token_ok else '失败，请检查账号密码'))
    if not token_ok:
        print('警告：认证失败，语音功能可能不可用')

    player = AudioPlayer()
    recorder = AudioRecorder(sample_rate=16000, channels=1)

    # 共享状态
    state_lock = threading.Lock()
    state = {"value": STATE_IDLE, "error": ""}
    history = []   # 每项 dict(kind='src'|'dst', text=..., lang='中文'|'English')

    def set_state(new_state, err=""):
        with state_lock:
            state["value"] = new_state
            state["error"] = err

    def get_state():
        with state_lock:
            return state["value"], state["error"]

    def add_history(kind, text, lang):
        with state_lock:
            history.append({"kind": kind, "text": text, "lang": lang})

    def relogin():
        """token 失效时重新登录一次（无 refresh_token，只能重取）"""
        try:
            return bool(voice_api.get_token(VOICE_USERNAME, VOICE_PASSWORD))
        except Exception:
            return False

    def llm_translate(prompt, text):
        # 实测（2026-11-04）：llm_chat + 中文翻译指令可正确翻译；
        # llm_chat_znbw_2025 是专用提示模型，不遵循翻译指令，不能用于翻译
        res = None
        try:
            res = voice_api.llm_chat(prompt + text)
        except Exception as e:
            print('LLM翻译异常: %s' % e)
        if not res or not str(res).strip():
            if relogin():
                try:
                    res = voice_api.llm_chat(prompt + text)
                except Exception as e:
                    print('LLM翻译重试异常: %s' % e)
        return res

    def do_translate(text):
        """中→英用官方翻译接口，英→中用 LLM。返回 (译文, 目标语言)"""
        if has_chinese(text):
            res = None
            try:
                res = voice_api.translate_english(text)
            except Exception as e:
                print('translate_english异常: %s' % e)
            if not res or not str(res).strip():
                res = llm_translate(u'把下面这句中文翻译成英文，只输出英文译文，不要解释和引号：', text)
            return res, 'English'
        else:
            res = llm_translate(u'把下面这句英文翻译成中文，只输出中文译文，不要解释和引号：', text)
            return res, '中文'

    def tts_get_audio(text):
        """TTS 带缓存。返回 wav 文件路径或 bytes，失败返回 None"""
        h = hashlib.md5(text.encode('utf-8')).hexdigest()
        path = os.path.join(RECORDINGS_DIR, 'tts_%s.wav' % h)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        try:
            data = voice_api.tts_synthesize(text, path)
        except Exception as e:
            print('TTS异常: %s' % e)
            return None
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        if data:
            return data
        return None

    def process_translation():
        """子线程：识别 -> 翻译 -> 合成 -> 播报"""
        rec_path = os.path.join(RECORDINGS_DIR, RECORD_FILENAME)

        # 1. 语音识别（只接受文件路径，录音已提前落盘）
        set_state(STATE_RECOGNIZING)
        try:
            text = voice_api.voice_recognition(rec_path)
        except Exception as e:
            set_state(STATE_ERROR, u'语音识别异常: %s' % e)
            return
        if not text or not str(text).strip():
            set_state(STATE_ERROR, u'未识别到内容，请靠近麦克风重试')
            return
        text = str(text).strip()
        src_lang = '中文' if has_chinese(text) else 'English'
        print('识别结果(%s): %s' % (src_lang, text))
        add_history('src', text, src_lang)

        # 2. 翻译
        set_state(STATE_TRANSLATING)
        try:
            translated, dst_lang = do_translate(text)
        except Exception as e:
            set_state(STATE_ERROR, u'翻译异常: %s' % e)
            return
        translated = str(translated).strip() if translated else ''
        if not translated:
            set_state(STATE_ERROR, u'翻译结果为空，请重试')
            return
        print('译文(%s): %s' % (dst_lang, translated))
        add_history('dst', translated, dst_lang)

        # 3. 语音合成 + 播报（英文译文先做发音修正，屏幕显示仍用 translated）
        set_state(STATE_SPEAKING)
        speak_text = translated
        if dst_lang == 'English':
            speak_text = tts_pronunciation_fix(translated)
            if speak_text != translated:
                print('播报发音修正: %s' % speak_text)
        audio = tts_get_audio(speak_text)
        if audio is None:
            print('TTS失败，跳过播报')
            set_state(STATE_IDLE)
            return
        try:
            if isinstance(audio, bytes):
                player.play_audio(audio)
            else:
                player.play_file(audio)
        except Exception as e:
            set_state(STATE_ERROR, u'播放异常: %s' % e)
            return
        set_state(STATE_IDLE)

    # ===== UI 元素 =====
    exit_btn_rect = pygame.Rect(WIDTH - 190, 30, 150, 60)
    record_btn_rect = pygame.Rect(WIDTH - 270, HEIGHT - 240, 170, 170)  # 方形按钮，右侧

    content_top = 140
    content_bottom = record_btn_rect.top - 30   # 气泡区上界截止到按钮上方，避免与提示/按钮重叠
    content_left = 90
    content_right = WIDTH - 90

    processing_thread = None
    recording = False
    record_start_tick = 0

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        cur_state, cur_error = get_state()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if exit_btn_rect.collidepoint(event.pos):
                    running = False
                    continue
                if (record_btn_rect.collidepoint(event.pos)
                        and cur_state in (STATE_IDLE, STATE_ERROR) and not recording):
                    recording = True
                    record_start_tick = pygame.time.get_ticks()
                    try:
                        recorder.start_recording(device=None)
                        set_state(STATE_RECORDING)
                    except Exception as e:
                        set_state(STATE_ERROR, u'录音启动失败: %s' % e)
                        recording = False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if recording:
                    recording = False
                    duration = (pygame.time.get_ticks() - record_start_tick) / 1000.0
                    try:
                        audio_data = recorder.stop_recording()
                        if audio_data is None or duration < MIN_RECORD_SEC:
                            set_state(STATE_IDLE)
                        else:
                            file_path = recorder.save_audio(audio_data, filename=RECORD_FILENAME)
                            if file_path:
                                processing_thread = threading.Thread(
                                    target=process_translation, daemon=True)
                                processing_thread.start()
                            else:
                                set_state(STATE_ERROR, u'录音保存失败')
                    except Exception as e:
                        set_state(STATE_ERROR, u'录音结束异常: %s' % e)

        # ----- 背景 -----
        screen.blit(background, (0, 0))

        # ----- 标题栏（"实时翻译（中 [图标] 英）" 图文混排）-----
        ls = font_title.render(u"实时翻译（中", True, TITLE_COLOR)
        rs = font_title.render(u"英）", True, TITLE_COLOR)
        gap = 14
        icon_w = swap_icon.get_width() if swap_icon else ls.get_height() - 18
        total_w = ls.get_width() + gap + icon_w + gap + rs.get_width()
        tx = (WIDTH - total_w) // 2
        ty = 36
        screen.blit(ls, (tx, ty))
        ay = ty + ls.get_height() // 2
        if swap_icon:
            screen.blit(swap_icon, (tx + ls.get_width() + gap, ay - icon_w // 2))
        else:
            ax = tx + ls.get_width() + gap
            pygame.draw.line(screen, TITLE_COLOR, (ax + 6, ay), (ax + icon_w - 6, ay), 5)
            pygame.draw.polygon(screen, TITLE_COLOR,
                                [(ax, ay), (ax + 14, ay - 8), (ax + 14, ay + 8)])
            pygame.draw.polygon(screen, TITLE_COLOR,
                                [(ax + icon_w, ay), (ax + icon_w - 14, ay - 8),
                                 (ax + icon_w - 14, ay + 8)])
        screen.blit(rs, (tx + ls.get_width() + gap + icon_w + gap, ty))

        # 退出按钮
        exit_hover = exit_btn_rect.collidepoint(mouse_pos)
        ex_surf = pygame.Surface(exit_btn_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(ex_surf, (240, 120, 110, 230) if exit_hover else (255, 255, 255, 200),
                         ex_surf.get_rect(), border_radius=14)
        pygame.draw.rect(ex_surf, (232, 100, 90), ex_surf.get_rect(), 2, border_radius=14)
        screen.blit(ex_surf, exit_btn_rect.topleft)
        ex_text = font_small.render(u"退出", True, (200, 60, 50))
        screen.blit(ex_text, ex_text.get_rect(center=exit_btn_rect.center))

        # ----- 对话气泡区（每条消息一个完整气泡，原文左 / 译文右）-----
        with state_lock:
            history_snapshot = list(history)

        bubble_pad = 22
        tag_h = font_tag.get_height()
        msg_h = font_msg.get_height()
        line_pitch = msg_h + 10
        max_tw = BUBBLE_MAX_W - bubble_pad * 2

        # 组装消息块：(kind, lang, lines, bubble_w, block_h)
        blocks = []
        for item in history_snapshot:
            lines = wrap_text(item['text'], font_msg, max_tw)
            if not lines:
                continue
            text_w = max(font_msg.size(ln)[0] for ln in lines)
            bubble_w = min(text_w + bubble_pad * 2, BUBBLE_MAX_W)
            block_h = tag_h + 10 + len(lines) * line_pitch + 18
            blocks.append((item['kind'], item['lang'], lines, bubble_w, block_h))

        # 自底向上渲染，最新消息在最下方（原文靠右 / 译文靠左，聊天气泡惯例）
        y = content_bottom
        for kind, lang, lines, bubble_w, block_h in reversed(blocks):
            block_top = y - block_h
            if block_top < content_top:
                break
            is_src = (kind == 'src')
            bx = (content_right - bubble_w) if is_src else content_left
            bg_color = SRC_BUBBLE_BG if is_src else DST_BUBBLE_BG
            border_color = SRC_BUBBLE_BORDER if is_src else DST_BUBBLE_BORDER

            bubble = pygame.Surface((bubble_w, block_h), pygame.SRCALPHA)
            pygame.draw.rect(bubble, bg_color, bubble.get_rect(), border_radius=18)
            pygame.draw.rect(bubble, border_color, bubble.get_rect(), 2, border_radius=18)
            screen.blit(bubble, (bx, block_top))

            # 标签：原文/译文 + 语言（原文标签右上对齐，译文标签左上对齐）
            tag = u"原文 · %s" % lang if is_src else u"译文 · %s" % lang
            tag_color = TAG_ZH if lang == '中文' else TAG_EN
            tag_surf = font_tag.render(tag, True, tag_color)
            if is_src:
                tag_pos = (bx + bubble_w - bubble_pad - tag_surf.get_width(), block_top + 10)
            else:
                tag_pos = (bx + bubble_pad, block_top + 10)
            screen.blit(tag_surf, tag_pos)

            # 文本行
            ty2 = block_top + 10 + tag_h + 10
            text_color = SRC_TEXT if is_src else DST_TEXT
            for ln in lines:
                ts = font_msg.render(ln, True, text_color)
                screen.blit(ts, (bx + bubble_pad, ty2))
                ty2 += line_pitch
            y = block_top - 24   # 块间距

        if not blocks:
            mid_y = (content_top + content_bottom) // 2
            draw_text(screen, u"还没有翻译记录", font_msg, (120, 140, 165),
                      (WIDTH // 2, mid_y - 30), anchor="center")
            draw_text(screen, u"按住下方按钮，说一句中文或英文试试", font_msg, (120, 140, 165),
                      (WIDTH // 2, mid_y + 30), anchor="center")

        # ----- 状态提示与底部提示（左侧，与右侧按钮同一水平位置）-----
        status_color = (90, 130, 180)
        if cur_state == STATE_RECORDING:
            status_color = (220, 70, 60)
        elif cur_state == STATE_ERROR:
            status_color = (214, 88, 76)
        elif cur_state == STATE_SPEAKING:
            status_color = (52, 168, 116)
        elif cur_state in (STATE_RECOGNIZING, STATE_TRANSLATING):
            status_color = (222, 150, 40)

        status_text = cur_error if (cur_state == STATE_ERROR and cur_error) \
            else STATE_TEXT.get(cur_state, "")
        draw_text(screen, status_text, font_status, status_color,
                  (content_left, record_btn_rect.y + 40), anchor="topleft")

        if cur_state in (STATE_IDLE, STATE_RECORDING):
            hint = u"按住按钮说中文或英文，松开自动翻译并播报 | ESC 退出"
        else:
            hint = u"请等待当前翻译完成..."
        draw_text(screen, hint, font_small, HINT_COLOR,
                  (content_left, record_btn_rect.y + 104), anchor="topleft")

        # ----- 按住说话按钮（方形圆角）-----
        btn_center = record_btn_rect.center
        hovering = record_btn_rect.collidepoint(mouse_pos)

        if cur_state == STATE_RECORDING:
            btn_color = BTN_RECORDING
            btn_label = [u"松开", u"翻译"]
            pulse = abs((pygame.time.get_ticks() // 8) % 80 - 40)
            glow = pygame.Surface((record_btn_rect.width + 90, record_btn_rect.height + 90),
                                  pygame.SRCALPHA)
            pygame.draw.rect(glow, (232, 66, 56, 55), glow.get_rect(), border_radius=36)
            glow = pygame.transform.smoothscale(
                glow,
                (int(glow.get_width() * (1.0 + pulse / 200.0)),
                 int(glow.get_height() * (1.0 + pulse / 200.0))))
            screen.blit(glow, glow.get_rect(center=btn_center))
        elif cur_state == STATE_ERROR:
            btn_color = BTN_IDLE_HOVER if hovering else BTN_IDLE
            btn_label = [u"再试一次"]
        elif cur_state == STATE_IDLE:
            btn_color = BTN_IDLE_HOVER if hovering else BTN_IDLE
            btn_label = [u"按住", u"说话"]
        elif cur_state == STATE_SPEAKING:
            btn_color = BTN_SPEAKING
            btn_label = [u"播报中"]
        else:
            btn_color = BTN_DISABLED
            btn_label = [u"处理中"]

        btn_surf = pygame.Surface(record_btn_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, btn_color, btn_surf.get_rect(), border_radius=30)
        pygame.draw.rect(btn_surf, (255, 255, 255, 210), btn_surf.get_rect(), 4, border_radius=30)
        screen.blit(btn_surf, record_btn_rect.topleft)

        total_h = sum(font_btn.size(l)[1] for l in btn_label) + 8 * (len(btn_label) - 1)
        ly = btn_center[1] - total_h // 2
        for l in btn_label:
            ts = font_btn.render(l, True, WHITE)
            screen.blit(ts, ts.get_rect(center=(btn_center[0], ly + ts.get_height() // 2)))
            ly += ts.get_height() + 8

        pygame.display.flip()
        clock.tick(60)

    # 退出清理
    if processing_thread and processing_thread.is_alive():
        processing_thread.join(timeout=3)
    try:
        player.cleanup()
    except Exception:
        pass
    pygame.display.quit()
    print('程序结束')


if __name__ == '__main__':
    main()
