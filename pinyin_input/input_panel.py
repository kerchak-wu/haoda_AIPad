# -*- coding: utf-8 -*-
"""
input_panel - 好搭AI派 可嵌入 pygame 拼音输入面板组件（三页结构）
页面：键盘（软键盘+候选）/ 语音（按住说话大按钮）/ 手机（二维码+推送状态），
  点面板顶部标签或按 F1/F2/F3 切换；编辑区三页共用。
功能：
  - 中文（离线拼音引擎）/ 英文直输 / 符号面板（自动跟随中英文模式，可「更多」互换）
  - 编辑区多行显示（自动按行高裁剪可见行数，不溢出边框）
  - 三个页面均可使用外接 USB 键盘输入；语音/手机页打拼音时底部出现轻量候选条
  - 语音页：方形「按住说话」大按钮；键盘页功能行仅 空格/回车/清空
  - 手机页显示二维码 + 推送状态
  - 可嵌入任何已初始化 pygame display/font 的程序
嵌入示例：
    from input_panel import PinyinInputPanel, load_font
    panel = PinyinInputPanel(
        pygame.Rect(60, 420, 1160, 600),
        font_path='/home/cxdz/jupyter/assets/msyh.ttc',
        on_commit=my_callback,          # 每次上屏一词回调
        voice_press=start_record,       # 语音按钮按下
        voice_release=stop_record,      # 松开
    )
    panel.set_phone_info('http://192.168.x.x:port', qr_surface)  # 手机页二维码
    # 宿主主循环里：
    panel.handle_event(event)      # True 表示事件被面板消费
    panel.draw(screen)
    text = panel.text              # 随时读取完整编辑内容
    text = panel.take_text()       # 提交：取出文本并清空编辑区
运行环境：Python 3.8+，pygame-ce 2.5.2（与原版 pygame 兼容用法一致）
"""

import os

import pygame

from pinyin_engine import PinyinIME

# ---------- 颜色（浅色天空蓝主题） ----------
COL_BG = (234, 244, 251)          # 面板底 浅蓝
COL_BORDER = (187, 216, 238)      # 边框
COL_TEXT = (23, 50, 77)           # 主文字 深蓝
COL_TEXT_MUTED = (91, 122, 153)   # 次文字
COL_KEY = (255, 255, 255)         # 按键底
COL_KEY_BORDER = (203, 224, 241)
COL_KEY_ACTIVE = (46, 155, 230)   # 按下/强调 蓝
COL_CAND_ACTIVE = (46, 155, 230)
COL_VOICE = (235, 87, 87)         # 语音按钮 红
COL_VOICE_ACTIVE = (210, 50, 50)
COL_OK = (34, 160, 90)            # 成功/已收到 绿
COL_WHITE = (255, 255, 255)

# 设备字体绝对路径（按优先级），Windows 字体兜底便于本地调试
_FONT_CANDIDATES = [
    '/home/cxdz/jupyter/assets/PingFang_Regular.ttf',
    '/home/cxdz/jupyter/assets/msyh.ttc',
    '/home/cxdz/jupyter/assets/simhei.ttf',
    '/home/cxdz/jupyter/assets/WenQuanWeiMiHei.ttf',
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
]

# 符号键盘两页（每页 3 行 x 10 个）：page0 中文全角，page1 英文半角
SYM_PAGES = [
    [
        ['，', '。', '？', '！', '；', '：', '（', '）', '《', '》'],
        ['「', '」', '【', '】', '、', '·', '～', '…', '—', '￥'],
        ['“', '”', '‘', '’', '※', '→', '←', '↑', '↓', '★'],
    ],
    [
        ['~', '!', '@', '#', '$', '%', '^', '&', '*', '('],
        [')', '_', '+', '-', '=', '{', '}', '[', ']', '|'],
        ['\\', ':', ';', '"', "'", '<', '>', ',', '.', '/'],
    ],
]

# 字母键盘三行（'shift'/'return' 为行内功能键；符号/退格在第四功能行）
_ROW1 = list('qwertyuiop')
_ROW2 = list('asdfghjkl')
_ROW3 = ['shift'] + list('zxcvbnm') + ['return']

# 页面标签
_TABS = [('kb', '键盘'), ('voice', '语音'), ('phone', '手机')]


def load_font(size, bold=False, font_path=None):
    """加载中文字体：设备绝对路径优先，找不到时逐个回退"""
    path = font_path
    if path is None:
        for p in _FONT_CANDIDATES:
            if os.path.exists(p):
                path = p
                break
    if path and os.path.exists(path):
        font = pygame.font.Font(path, size)
    else:
        name = None
        for cand in ('msyh', 'simhei', 'pingfang', 'notosanscjk'):
            if cand in pygame.font.get_fonts():
                name = cand
                break
        font = pygame.font.SysFont(name, size, bold=bold)
    font.set_bold(bold)
    return font


class _Key(object):
    """软键盘按键"""
    __slots__ = ('code', 'label', 'rect')

    def __init__(self, code, label, rect):
        self.code = code
        self.label = label
        self.rect = rect


class PinyinInputPanel(object):
    """拼音输入面板组件（三页）。宿主程序只需调用
    handle_event / draw / text / take_text / set_phone_info。"""

    def __init__(self, rect, font_path=None, fonts=None, engine=None,
                 on_commit=None, voice_press=None, voice_release=None,
                 soft_keyboard=True, max_lines=8):
        self.rect = pygame.Rect(rect)
        self.font_path = font_path
        self.on_commit = on_commit
        self.voice_press_cb = voice_press
        self.voice_release_cb = voice_release
        self.soft_keyboard = soft_keyboard
        self.max_lines = max_lines
        # 字体
        if fonts:
            self.f_text = fonts.get('text') or load_font(28, font_path=font_path)
            self.f_cand = fonts.get('cand') or load_font(26, font_path=font_path)
            self.f_key = fonts.get('key') or load_font(26, font_path=font_path)
            self.f_label = fonts.get('label') or load_font(22, font_path=font_path)
        else:
            self.f_text = load_font(28, font_path=font_path)
            self.f_cand = load_font(26, font_path=font_path)
            self.f_key = load_font(26, font_path=font_path)
            self.f_label = load_font(22, font_path=font_path)
        # 引擎
        self.engine = engine if engine is not None else PinyinIME()
        # 状态
        self.page = 'kb'               # 'kb' / 'voice' / 'phone'
        self.mode_cn = True            # True 中文 / False 英文（字母输入模式）
        self._sym_mode = False         # True 符号面板（键盘页内）
        self._sym_page = 0             # 0 中文全角 / 1 英文半角（进面板时自动跟随 mode_cn）
        self._text_lines = ['']        # 编辑区文本（多行）
        self.candidates = []
        self._cand_offset = 0          # 候选翻页偏移（每页 9 个）
        self.pressed_key = None
        self.voice_active = False      # 语音录音中（宿主也可外部置位）
        self.voice_status = ''         # 语音页状态文字（宿主可写）
        self.phone_url = None          # 手机页地址（宿主 set_phone_info）
        self.qr_surface = None         # 手机页二维码
        self.phone_status = ''         # 手机页状态文字（宿主可写）
        self.on_submit_cb = None       # 「提交」按钮回调（宿主设置，如 panel.take_text）
        self._last_cand_raw = ''
        self._build_keys()

    # ---------- 公开 API ----------

    @property
    def text(self):
        return '\n'.join(self._text_lines)

    def take_text(self):
        """提交：返回当前编辑区全部文本并清空（供宿主程序提交输入内容）"""
        text = self.text
        self.clear_text()
        return text

    def set_text(self, text):
        """整体替换编辑区内容"""
        self._text_lines = text.split('\n') if text else ['']
        self._trim_lines()

    def append_text(self, text):
        """追加文本到编辑区末尾"""
        if not text:
            return
        self._text_lines[-1] += text
        self._trim_lines()

    def clear_text(self):
        self._text_lines = ['']
        self.engine.reset_all()

    def set_phone_info(self, url, qr_surface=None):
        """设置手机页显示的地址与二维码表面"""
        self.phone_url = url
        self.qr_surface = qr_surface

    def toggle_mode(self):
        """中/英切换；切换时清空拼音输入，符号页自动跟随"""
        self.mode_cn = not self.mode_cn
        self.engine.reset_input()
        self.candidates = []
        if self._sym_mode:
            self._sym_page = 0 if self.mode_cn else 1

    def show_symbols(self, show=True):
        """打开/关闭符号面板（进入时自动选中当前语言对应的符号页）"""
        self._sym_mode = bool(show)
        if show:
            self._sym_page = 0 if self.mode_cn else 1
        self.engine.reset_input()
        self.candidates = []

    def refresh_candidates(self):
        raw = self.engine.input
        if self.mode_cn and raw and raw != self._last_cand_raw:
            self.candidates = self.engine.candidates(90)   # 10 页 x 9 个，覆盖生僻字
            self._cand_offset = 0
            self._last_cand_raw = raw
        elif not raw:
            self.candidates = []
            self._cand_offset = 0
            self._last_cand_raw = ''

    # ---------- 事件处理 ----------

    def handle_event(self, event):
        """处理 pygame 事件；返回 True 表示事件被面板消费"""
        if event.type == pygame.KEYDOWN:
            handled = self._handle_keydown(event)
            if handled:
                self.refresh_candidates()
            return handled
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            key = self._key_at(event.pos)
            if key is not None:
                self.pressed_key = key
                if key.code == 'voice' and self.voice_press_cb:
                    self.voice_active = True
                    self.voice_press_cb()
                return True
            # 候选点击（键盘页）
            if self.page == 'kb' and self.mode_cn and self.candidates:
                idx = self._candidate_at(event.pos)
                if idx is not None:
                    self._commit_word(idx)
                    return True
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            key = self.pressed_key
            self.pressed_key = None
            if key is None:
                return False
            if key.code == 'voice':
                self.voice_active = False
                if self.voice_release_cb:
                    self.voice_release_cb()
                return True
            if key.rect.collidepoint(event.pos):
                self._activate_key(key.code)
            return True
        return False

    def _handle_keydown(self, event):
        """USB 键盘输入（三个页面均可输入，编辑区共用）"""
        key = event.key
        if key == pygame.K_ESCAPE:
            return False  # 退出等交宿主处理
        if self._sym_mode and self.page == 'kb':
            # 符号面板模式下：USB 键盘只保留退格/空格/回车
            if key == pygame.K_BACKSPACE:
                self._edit_backspace()
                return True
            if key == pygame.K_SPACE:
                self.append_text(' ')
                return True
            if key == pygame.K_RETURN or key == pygame.K_KP_ENTER:
                self._text_lines.append('')
                self._trim_lines()
                return True
            return False
        if pygame.K_1 <= key <= pygame.K_9:
            idx = key - pygame.K_1
            if self.mode_cn and self.candidates:
                word_idx = self._cand_offset + idx
                if word_idx < len(self.candidates):
                    self._commit_word(word_idx)
                    return True
            self.append_text(chr(key - pygame.K_1 + ord('1')))
            return True
        if pygame.K_a <= key <= pygame.K_z:
            ch = chr(key)
            if self.mode_cn:
                self.engine.push_keys(ch)
            else:
                self.append_text(ch if not event.mod & pygame.KMOD_SHIFT
                                 else ch.upper())
            return True
        if key == pygame.K_BACKSPACE:
            self._edit_backspace()
            return True
        if key == pygame.K_SPACE:
            if self.page == 'kb' and self.mode_cn and self.candidates:
                self._commit_word(0)
            else:
                self.append_text(' ')
            return True
        if key == pygame.K_RETURN or key == pygame.K_KP_ENTER:
            if self.page == 'kb' and self.mode_cn and self.engine.input:
                raw = self.engine.input
                self.engine.reset_input()
                self.append_text(raw)
            else:
                self._text_lines.append('')
                self._trim_lines()
            return True
        # 中文标点直输映射
        if self.mode_cn and event.unicode:
            punct = {'.': '。', ',': '，', '?': '？', '!': '！',
                     ';': '；', ':': '：', '(': '（', ')': '）'}
            u = event.unicode
            if u in punct:
                self.append_text(punct[u])
                return True
            if u in '，。？！；：（）「」、':
                self.append_text(u)
                return True
        # 英文标点直输
        if not self.mode_cn and event.unicode:
            self.append_text(event.unicode)
            return True
        return False

    def _edit_backspace(self):
        """退格：键盘页先删拼音字母，拼音删完再删已上屏文字；其他页直接删文字"""
        if (self.page == 'kb' and self.mode_cn and not self._sym_mode
                and self.engine.input):
            self.engine.pop_key()
        else:
            line = self._text_lines[-1]
            if line:
                self._text_lines[-1] = line[:-1]
            elif len(self._text_lines) > 1:
                self._text_lines.pop()

    # ---------- 内部：按键 ----------

    def _activate_key(self, code):
        if code == 'voice':
            return  # 按住语义，在 MOUSEBUTTONDOWN/UP 中处理
        if code in ('tab_kb', 'tab_voice', 'tab_phone'):
            self.page = code[4:]
        elif code == 'cand_prev':
            self._cand_offset = max(0, self._cand_offset - 9)
        elif code == 'cand_next':
            if self._cand_offset + 9 < len(self.candidates):
                self._cand_offset += 9
        elif code == 'submit':
            if self.on_submit_cb:
                try:
                    self.on_submit_cb()
                except Exception:
                    pass
        elif code == 'shift':
            self.toggle_mode()
        elif code == 'sym':
            self.show_symbols(True)
        elif code == 'sym_letter':
            self.show_symbols(False)
        elif code == 'sym_more':
            self._sym_page = (self._sym_page + 1) % len(SYM_PAGES)
        elif code == 'backspace':
            self._edit_backspace()
        elif code == 'space':
            if self._sym_mode:
                self.append_text(' ')
            elif self.mode_cn and self.candidates:
                self._commit_word(0)
            else:
                self.append_text(' ')
        elif code == 'return':
            if self.mode_cn and not self._sym_mode and self.engine.input:
                raw = self.engine.input
                self.engine.reset_input()
                self.append_text(raw)
            else:
                self._text_lines.append('')
                self._trim_lines()
        elif code == 'clear':
            self.clear_text()
        elif code.startswith('sym:'):
            self.append_text(code[4:])
        elif code.startswith('char:') or (len(code) == 1 and code.isalpha()):
            ch = code[-1]
            if self.mode_cn:
                self.engine.push_keys(ch)
            else:
                self.append_text(ch)
        self.refresh_candidates()

    def _commit_word(self, idx):
        word = self.engine.choose(idx)
        if word:
            self.append_text(word)
            self.candidates = []
            self._last_cand_raw = ''
            if self.on_commit:
                try:
                    self.on_commit(word)
                except Exception:
                    pass

    def _trim_lines(self):
        if len(self._text_lines) > self.max_lines:
            self._text_lines = self._text_lines[-self.max_lines:]

    # ---------- 内部：布局 ----------

    def _layout_metrics(self):
        """(pad, 编辑区高, 标签行高, 候选栏高)"""
        pad = 10
        edit_h = 150
        tab_h = 44
        cand_h = 60
        return pad, edit_h, tab_h, cand_h

    def _content_top(self):
        """标签行以下内容区的起始 y"""
        x, y, w, h = self.rect
        pad, edit_h, tab_h, _c = self._layout_metrics()
        return y + pad + edit_h + tab_h + 6

    def _sym_rows(self):
        return SYM_PAGES[self._sym_page]

    def _build_keys(self):
        """根据当前 rect / 页面 / 模式计算所有按键矩形"""
        self.keys = []
        x, y, w, h = self.rect
        pad, edit_h, tab_h, cand_h = self._layout_metrics()
        if not self.soft_keyboard:
            return
        gap = 8
        # ----- 页面标签行（三页共用）-----
        tab_y = y + pad + edit_h + 4
        tw = (w - 2 * pad - 2 * 8) / 3.0
        for i, (pid, label) in enumerate(_TABS):
            rect = pygame.Rect(int(x + pad + i * (tw + 8)), tab_y,
                               int(tw), tab_h)
            self.keys.append(_Key('tab_%s' % pid, label, rect))
        # ----- 各页内容 -----
        if self.page == 'voice':
            # 语音页：提交（左）+ 按住说话（右），两个同尺寸方形，底边对齐
            area_top = self._content_top()
            area_bottom = y + h - pad - 64  # 底部留出轻量候选条
            side = min(150, area_bottom - area_top - 20)
            total = side * 2 + 60
            left_x = x + (w - total) // 2
            bottom = area_bottom - 10
            srect = pygame.Rect(int(left_x), int(bottom - side), side, side)
            self.keys.append(_Key('submit', '提交', srect))
            vrect = pygame.Rect(int(left_x + side + 60), int(bottom - side),
                                side, side)
            self.keys.append(_Key('voice', '按住说话', vrect))
            return
        if self.page == 'phone':
            # 手机页：二维码（左，大）+ 提交按钮（右，矩形），底边对齐
            area_top = self._content_top()
            area_bottom = y + h - pad - 64
            sw, sh = 240, 130
            srect = pygame.Rect(0, 0, sw, sh)
            srect.bottomright = (int(x + w - pad - 10), int(area_bottom - 10))
            self.keys.append(_Key('submit', '提交', srect))
            return
        # ----- 键盘页：候选栏 + 字母/符号键盘 -----
        kb_top = self._content_top() + cand_h + 6
        kb_h = y + h - pad - kb_top
        n_rows = 4
        row_h = (kb_h - gap * (n_rows - 1)) / float(n_rows)
        key_h = min(row_h, 92)
        row_y = [kb_top + r * (row_h + gap) for r in range(n_rows)]

        def build_function_row():
            """第四行：符号 | 空格 | 清空 | 退格 | 提交"""
            order = [('sym', '符号', 0.13), ('space', '空格', 0.32),
                     ('clear', '清空', 0.15), ('backspace', '退格', 0.15),
                     ('submit', '提交', 0.25)]
            usable = w - 2 * pad - gap * 4
            cx = x + pad
            for code, label, fr in order:
                kw = int(usable * fr)
                rect = pygame.Rect(int(cx), int(row_y[3] + (row_h - key_h) / 2),
                                   kw, int(key_h))
                self.keys.append(_Key(code, label, rect))
                cx += kw + gap

        if self._sym_mode:
            rows = self._sym_rows()
            for r in range(3):
                row_yk = row_y[r] + (row_h - key_h) / 2
                cols = rows[r] if r < 2 else None
                if cols:
                    cw = (w - 2 * pad - gap * (len(cols) - 1)) / float(len(cols))
                    for c, ch in enumerate(cols):
                        rect = pygame.Rect(int(x + pad + c * (cw + gap)),
                                           int(row_yk), int(cw), int(key_h))
                        self.keys.append(_Key('sym:%s' % ch, ch, rect))
                else:
                    names = [('sym_letter', '字母'), ('sym_more', '更多'),
                             ('backspace', '退格')]
                    cw = (w - 2 * pad - gap * 2) / 3.0
                    for c, (code, label) in enumerate(names):
                        rect = pygame.Rect(int(x + pad + c * (cw + gap)),
                                           int(row_yk), int(cw), int(key_h))
                        self.keys.append(_Key(code, label, rect))
            build_function_row()
        else:
            rows = (_ROW1, _ROW2, _ROW3)
            labels3 = {'shift': '中/EN', 'return': '回车'}
            for r, row in enumerate(rows):
                n = len(row)
                key_w = (w - 2 * pad - gap * (n - 1)) / float(n)
                key_w = min(key_w, 118)
                row_w = key_w * n + gap * (n - 1)
                start_x = x + (w - row_w) / 2
                row_yk = row_y[r] + (row_h - key_h) / 2
                for c, ch in enumerate(row):
                    rect = pygame.Rect(int(start_x + c * (key_w + gap)),
                                       int(row_yk), int(key_w), int(key_h))
                    label = labels3.get(ch, ch)
                    self.keys.append(_Key(ch, label, rect))
            build_function_row()
        # 候选点击区矩形（键盘页）：◀ 在最左、▶ 在最右（大按钮），x/y 页码紧邻 ▶ 左侧
        cand_y = y + pad + edit_h + tab_h + 6
        self._cand_rects = []
        page_btn_w = 72
        btn_h = min(cand_h, 52)
        by = cand_y + (cand_h - btn_h) // 2
        prev_rect = pygame.Rect(int(x + pad), int(by), page_btn_w, btn_h)
        next_rect = pygame.Rect(int(x + w - pad - page_btn_w), int(by),
                                page_btn_w, btn_h)
        self.keys.append(_Key('cand_prev', '◀', prev_rect))
        self.keys.append(_Key('cand_next', '▶', next_rect))
        # 页码指示预留带（▶ 左侧 74px），词槽避开
        words_left = x + pad + page_btn_w + gap
        words_right = next_rect.x - gap - 74
        words_w = words_right - words_left
        cw = (words_w - gap * 8) / 9.0
        for i in range(9):
            self._cand_rects.append(
                pygame.Rect(int(words_left + i * (cw + gap)), int(cand_y),
                            int(cw), int(cand_h)))

    def _key_at(self, pos):
        for k in self.keys:
            if k.rect.collidepoint(pos):
                return k
        return None

    def _candidate_at(self, pos):
        for i, r in enumerate(self._cand_rects):
            if r.collidepoint(pos) and i < len(self.candidates):
                return i
        return None

    # ---------- 绘制 ----------

    def draw(self, surface):
        self.refresh_candidates()
        self._build_keys()
        x, y, w, h = self.rect
        pad, edit_h, tab_h, cand_h = self._layout_metrics()
        # 面板底
        pygame.draw.rect(surface, COL_BG, self.rect, border_radius=16)
        pygame.draw.rect(surface, COL_BORDER, self.rect, 2, border_radius=16)
        # 编辑区（三页共用）
        edit_rect = pygame.Rect(x + pad, y + pad, w - 2 * pad, edit_h)
        pygame.draw.rect(surface, COL_WHITE, edit_rect, border_radius=12)
        pygame.draw.rect(surface, COL_KEY_BORDER, edit_rect, 2, border_radius=12)
        self._draw_edit(surface, edit_rect)
        # 页面按键（标签 + 当前页按键）
        for k in self.keys:
            self._draw_key(surface, k)
        if self.page == 'kb':
            cand_rect = pygame.Rect(x + pad,
                                    y + pad + edit_h + tab_h + 6,
                                    w - 2 * pad, cand_h)
            self._draw_candidates(surface, cand_rect)
        elif self.page == 'voice':
            self._draw_voice_page(surface)
            self._draw_compact_cand(surface)
        elif self.page == 'phone':
            self._draw_phone_page(surface)
            self._draw_compact_cand(surface)

    def _draw_compact_cand(self, surface):
        """语音页/手机页底部的轻量候选条：正在打拼音时才出现"""
        if not (self.mode_cn and self.engine.input):
            return
        x, y, w, h = self.rect
        rect = pygame.Rect(x + 10, y + h - 54, w - 20, 44)
        pygame.draw.rect(surface, COL_WHITE, rect, border_radius=10)
        pygame.draw.rect(surface, COL_KEY_BORDER, rect, 2, border_radius=10)
        cx = rect.x + 12
        raw_ts = self.f_label.render('拼音: ' + self.engine.input, True,
                                     COL_TEXT_MUTED)
        surface.blit(raw_ts, (cx, rect.y + (rect.h - raw_ts.get_height()) // 2))
        cx += raw_ts.get_width() + 16
        page = self.candidates[self._cand_offset:self._cand_offset + 6]
        for i, word in enumerate(page):
            num = self.f_label.render('%d' % (i + 1), True, COL_TEXT_MUTED)
            ts = self.f_cand.render(word, True,
                                    COL_CAND_ACTIVE if i == 0 else COL_TEXT)
            surface.blit(num, (cx, rect.y + (rect.h - num.get_height()) // 2 + 2))
            cx += num.get_width() + 4
            surface.blit(ts, (cx, rect.y + (rect.h - ts.get_height()) // 2))
            cx += ts.get_width() + 14
            if cx > rect.right - 60:
                break

    def _draw_edit(self, surface, rect):
        """多行文本：按行高裁剪可见行数，超出只显示最近几行，不溢出边框"""
        max_w = rect.w - 28
        line_h = self.f_text.get_height() + 4
        lines = []
        for raw in self._text_lines:
            cur = ''
            for ch in raw:
                if self.f_text.size(cur + ch)[0] > max_w:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
            lines.append(cur)
        # 可见行数 = 内容区能放下的行数
        visible = max(1, int((rect.h - 20) // line_h))
        show = lines[-visible:]
        ty = rect.bottom - 12 - len(show) * line_h
        for i, ln in enumerate(show):
            ts = self.f_text.render(ln, True, COL_TEXT)
            surface.blit(ts, (rect.x + 14, ty + i * line_h))
        # 光标
        if pygame.time.get_ticks() // 500 % 2 == 0:
            last = show[-1] if show else ''
            cx = rect.x + 14 + self.f_text.size(last)[0]
            cy = ty + (len(show) - 1) * line_h
            if cx < rect.right - 10:
                pygame.draw.rect(surface, COL_KEY_ACTIVE,
                                 (cx, cy + 2, 3, self.f_text.get_height() - 4))
        # 当前拼音串（编辑区右下角小字提示）
        if (self.page == 'kb' and self.mode_cn and not self._sym_mode
                and self.engine.input):
            ts = self.f_label.render('拼音: ' + self.engine.input, True, COL_TEXT_MUTED)
            surface.blit(ts, (rect.right - ts.get_width() - 10, rect.y + 6))

    def _draw_candidates(self, surface, rect):
        if self._sym_mode:
            page_name = '中文符号' if self._sym_page == 0 else '英文符号'
            ts = self.f_label.render('符号面板 · %s（点「更多」互换）' % page_name,
                                     True, COL_TEXT_MUTED)
            surface.blit(ts, (rect.x + 14, rect.y + (rect.h - ts.get_height()) // 2))
            return
        raw = self.engine.input if self.mode_cn else ''
        if not self.mode_cn:
            ts = self.f_label.render('英文模式', True, COL_TEXT_MUTED)
            surface.blit(ts, (rect.x + 12, rect.y + 8))
            return
        if raw and not self.candidates:
            ts = self.f_cand.render(raw, True, COL_TEXT_MUTED)
            surface.blit(ts, (rect.x + 16, rect.y + (rect.h - ts.get_height()) // 2))
        # 当前页 9 个候选（数字键序号按页内位置）
        page = self.candidates[self._cand_offset:self._cand_offset + 9]
        for i, word in enumerate(page):
            r = self._cand_rects[i]
            color = COL_CAND_ACTIVE if (i == 0 and self._cand_offset == 0) else COL_TEXT
            ts = self.f_cand.render(word, True, color)
            num = self.f_label.render('%d' % (i + 1), True, COL_TEXT_MUTED)
            total = num.get_width() + 6 + ts.get_width()
            bx = r.x + (r.w - total) // 2
            by = r.y + (r.h - ts.get_height()) // 2
            surface.blit(num, (bx, by + 4))
            surface.blit(ts, (bx + num.get_width() + 6, by))
        # 页码提示（紧邻 ▶ 左侧，避开词槽）
        if len(self.candidates) > 9:
            total_pages = (len(self.candidates) + 8) // 9
            cur_page = self._cand_offset // 9 + 1
            ts = self.f_label.render('%d/%d' % (cur_page, total_pages), True,
                                     COL_TEXT_MUTED)
            surface.blit(ts, (rect.right - 72 - 14 - ts.get_width(),
                              rect.y + (rect.h - ts.get_height()) // 2))

    def _draw_btn_3d(self, surface, rect, body, border, pressed, radius=12):
        """立体按键：底部投影 + 顶边高光；按下时下移贴底，无投影"""
        dark = tuple(max(0, int(c * 0.72)) for c in border)
        if pressed:
            r = rect.move(0, 2)
            pygame.draw.rect(surface, body, r, border_radius=radius)
            pygame.draw.rect(surface, border, r, 2, border_radius=radius)
        else:
            pygame.draw.rect(surface, dark, rect.move(0, 3), border_radius=radius)
            pygame.draw.rect(surface, body, rect, border_radius=radius)
            pygame.draw.rect(surface, border, rect, 2, border_radius=radius)
            pygame.draw.line(surface, COL_WHITE,
                             (rect.x + radius // 2, rect.y + 2),
                             (rect.right - radius // 2, rect.y + 2), 2)

    def _draw_voice_page(self, surface):
        """语音页：状态文字（上）+ 提交（左）+ 按住说话（右），双方形底边对齐"""
        key = None
        for k in self.keys:
            if k.code == 'voice':
                key = k
                break
        if key is None:
            return
        rect = key.rect
        color = COL_VOICE_ACTIVE if self.voice_active else COL_VOICE
        pressed = self.pressed_key is key
        # 录音中：脉冲外圈，明显反馈按住状态
        if self.voice_active:
            cx, cy = rect.center
            phase = (pygame.time.get_ticks() // 120) % 4
            grow = (phase + 1) * 6
            pulse = pygame.Surface((rect.w + grow * 2 + 20,
                                    rect.h + grow * 2 + 20), pygame.SRCALPHA)
            pygame.draw.rect(pulse, (235, 87, 87, 90),
                             pulse.get_rect(), border_radius=16)
            surface.blit(pulse, pulse.get_rect(center=(cx, cy)).topleft)
        self._draw_btn_3d(surface, rect, color, COL_WHITE,
                          pressed or self.voice_active)
        label = '松开' if self.voice_active else '按住说话'
        ts = self.f_key.render(label, True, COL_WHITE)
        surface.blit(ts, ts.get_rect(center=rect.center))
        # 状态文字（按钮上方居中）
        x, y, w, h = self.rect
        if self.voice_status:
            ts3 = self.f_label.render(self.voice_status, True,
                                      COL_OK if '就绪' in self.voice_status
                                      else COL_KEY_ACTIVE)
            surface.blit(ts3, ts3.get_rect(midtop=(x + w // 2,
                                                   self._content_top() + 8)))

    def _draw_phone_page(self, surface):
        """手机页：大二维码（左，底边对齐）+ 地址说明（右上对齐）+ 提交（右，矩形）"""
        x, y, w, h = self.rect
        pad, edit_h, tab_h, _c = self._layout_metrics()
        top = self._content_top()
        area_bottom = y + h - pad - 64
        # 二维码：大，底边与提交按钮对齐
        qr_top = top + 20
        qr_size = 0
        if self.qr_surface is not None:
            qr_size = min(300, area_bottom - top - 30)
            qr = pygame.transform.scale(self.qr_surface,
                                        (int(qr_size), int(qr_size)))
            box = pygame.Rect(0, 0, int(qr_size), int(qr_size))
            box.bottomleft = (int(x + pad + 20), int(area_bottom - 10))
            qr_top = box.top - 8
            bg = box.inflate(16, 16)
            pygame.draw.rect(surface, COL_WHITE, bg, border_radius=10)
            pygame.draw.rect(surface, COL_KEY_BORDER, bg, 2, border_radius=10)
            surface.blit(qr, box.topleft)
            tx = bg.right + 30
        else:
            tx = x + pad + 20
            qr_top = top + 20
        ty = qr_top  # 地址行与二维码上边对齐
        if self.phone_url:
            ts = self.f_cand.render('手机辅助页地址：', True, COL_TEXT_MUTED)
            surface.blit(ts, (tx, ty))
            ts2 = self.f_cand.render(self.phone_url, True, COL_KEY_ACTIVE)
            surface.blit(ts2, (tx, ty + 34))
            ts3 = self.f_label.render('手机扫码打开，打字后点「发送到设备」即出现在上方编辑区',
                                      True, COL_TEXT_MUTED)
            surface.blit(ts3, (tx, ty + 76))
        if self.phone_status:
            ts4 = self.f_label.render(self.phone_status, True, COL_OK
                                      if '已收到' in self.phone_status else COL_TEXT_MUTED)
            surface.blit(ts4, (tx, ty + 112))

    def _draw_key(self, surface, key):
        code = key.code
        pressed = self.pressed_key is key
        rect = key.rect
        # 页面标签
        if code in ('tab_kb', 'tab_voice', 'tab_phone'):
            active = (self.page == code[4:])
            body = COL_KEY_ACTIVE if active else COL_KEY
            border = COL_KEY_ACTIVE if active else COL_KEY_BORDER
            self._draw_btn_3d(surface, rect, body, border, pressed, radius=10)
            ts = self.f_key.render(key.label, True,
                                   COL_WHITE if active else COL_TEXT)
            surface.blit(ts, ts.get_rect(center=rect.center))
            return
        if code == 'voice':
            # 方形语音按钮（语音页大按钮专用）
            color = COL_VOICE_ACTIVE if (self.voice_active or pressed) else COL_VOICE
            self._draw_btn_3d(surface, rect, color, COL_WHITE, pressed)
            label = '松开' if self.voice_active else '按住说话'
            ts = self.f_key.render(label, True, COL_WHITE)
            surface.blit(ts, ts.get_rect(center=rect.center))
            return
        if code == 'submit':
            # 提交按钮（绿色）
            color = COL_KEY_ACTIVE if pressed else COL_OK
            self._draw_btn_3d(surface, rect, color, COL_OK, pressed)
            ts = self.f_key.render('提交', True, COL_WHITE)
            surface.blit(ts, ts.get_rect(center=rect.center))
            return
        if code in ('cand_prev', 'cand_next'):
            # 候选翻页键：三角形箭头（字体无 ◀▶ 字形也能显示），无页可翻时弱化
            dim = (code == 'cand_next' and self._cand_offset + 9 >= len(self.candidates)) \
                  or (code == 'cand_prev' and self._cand_offset == 0)
            body = COL_KEY if not dim else COL_BG
            border = COL_KEY_BORDER if not dim else COL_BORDER
            self._draw_btn_3d(surface, rect, body, border, pressed, radius=10)
            cx, cy = rect.center
            tri_color = COL_TEXT if not dim else COL_TEXT_MUTED
            if code == 'cand_prev':
                pts = [(cx + 7, cy - 10), (cx + 7, cy + 10), (cx - 9, cy)]
            else:
                pts = [(cx - 7, cy - 10), (cx - 7, cy + 10), (cx + 9, cy)]
            pygame.draw.polygon(surface, tri_color, pts)
            return
        active = pressed or (code == 'shift' and not self.mode_cn
                             and not self._sym_mode)
        body = COL_KEY_ACTIVE if active else COL_KEY
        border = COL_KEY_ACTIVE if active else COL_KEY_BORDER
        self._draw_btn_3d(surface, rect, body, border, pressed)
        tcolor = COL_WHITE if active else COL_TEXT
        ts = self.f_key.render(key.label, True, tcolor)
        surface.blit(ts, ts.get_rect(center=rect.center))
