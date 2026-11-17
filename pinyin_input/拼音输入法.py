# -*- coding: utf-8 -*-
"""
拼音输入法 - 好搭AI派
功能：离线拼音输入独立应用（软键盘 + USB 键盘 + 语音输入 + 手机辅助页二维码）
硬件：无摄像头；录音用板载麦克风（AudioRecorder）；手机辅助页走局域网 HTTP
依赖：pygame-ce 2.5.2、qrcode+PIL（二维码）、pinyin_engine/input_panel/voice_input/phone_bridge
窗口：1280x780 非全屏（用户指定），浅色天空蓝主题
语音凭据：保存在本程序目录（设备）下的 credentials.py，仓库与本地同步副本不保存
"""

import os
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'  # 必须在所有 import 之前

import datetime
import sys
import threading

# 官方库（voice_api/audio_recorder）在设备上的位置：管理器经 PYTHONPATH 提供，
# SSH 直接启动时需显式补充（路径不存在时无副作用）
_LIB_DIR = '/home/cxdz/jupyter/lib'
if os.path.isdir(_LIB_DIR) and _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

# 程序自目录定位：无论从哪里启动（管理器/SSH），data/ logs/ recordings/
# 都生成在本程序所在文件夹内，不污染 user/ 根目录
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
os.chdir(_APP_DIR)

import pygame
pygame.display.init()
pygame.font.init()

from input_panel import PinyinInputPanel, load_font, COL_WHITE, COL_TEXT_MUTED
from voice_input import VoiceInput
from phone_bridge import PhoneBridge

# ===== 日志标准模式（追加写 + 块缓冲 + stdout 分路）=====
_LOG_DIR = 'logs'
if not os.path.exists(_LOG_DIR):
    os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(
    _LOG_DIR,
    '拼音输入法_%s.log' % datetime.datetime.now().strftime('%Y%m%d')
)


class _Logger(object):
    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log = open(file_path, 'a', buffering=-1, encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()  # 逐行落盘，避免块缓冲导致日志延迟

    def flush(self):
        self.terminal.flush()
        self.log.flush()


sys.stdout = _Logger(_LOG_FILE)
sys.stderr = sys.stdout

print('=' * 60)
print('拼音输入法 启动于 %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print('日志文件: %s' % _LOG_FILE)
print('=' * 60)

# ===== 配置 =====
WIDTH, HEIGHT = 1280, 820

# 界面配色（浅色天空蓝）
COL_SKY = (225, 240, 250)         # 窗口背景 天空蓝
COL_TITLE = (23, 50, 77)
COL_ACCENT = (46, 155, 230)
COL_OK = (34, 160, 90)
COL_WARN = (235, 140, 40)

# 标题字体（楷体优先，等线兜底；与正文 msyh 区分）
_TITLE_FONT_CANDIDATES = [
    '/home/cxdz/jupyter/assets/simkai.ttf',
    '/home/cxdz/jupyter/assets/Dengb.ttf',
    'C:/Windows/Fonts/SIMKAI.TTF',
    'C:/Windows/Fonts/simkai.ttf',
]


def load_title_font(size):
    for p in _TITLE_FONT_CANDIDATES:
        if os.path.exists(p):
            return pygame.font.Font(p, size)
    return load_font(size, bold=True)


def make_qr_surface(url, box_size=4):
    """生成二维码 pygame 表面；qrcode/PIL 不可用时返回 None"""
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=box_size, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image().convert('RGB')
        return pygame.image.frombuffer(img.tobytes(), img.size, 'RGB')
    except Exception as e:
        print('二维码生成失败（仅显示文字地址）: %s' % e)
        return None


def main():
    # ----- 字体 -----
    f_title = load_title_font(40)
    f_status = load_font(24)
    f_hint = load_font(22)

    # ----- 窗口 -----
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption('拼音输入法 - 好搭AI派')
    clock = pygame.time.Clock()

    def on_commit(word):
        print('上屏: %s' % word)

    panel_rect = pygame.Rect(60, 110, WIDTH - 120, HEIGHT - 110 - 44)
    panel = PinyinInputPanel(panel_rect, on_commit=on_commit)

    # ----- 语音输入（凭据从设备 credentials.py 读取）-----
    voice = VoiceInput()

    def voice_press():
        if not voice.is_available():
            set_status('语音不可用：请在程序目录创建 credentials.py（用户名/密码）', COL_WARN)
            panel.voice_status = '语音不可用：请先配置凭据'
            return
        try:
            voice.start_record()
            panel.voice_active = True
            panel.voice_status = '录音中... 松开结束'
            set_status('录音中... 松开结束', COL_ACCENT)
        except Exception as e:
            panel.voice_active = False
            panel.voice_status = '录音启动失败: %s' % e
            set_status('录音启动失败: %s' % e, COL_WARN)

    def voice_release():
        panel.voice_active = False
        if not voice.is_available():
            return
        panel.voice_status = '语音识别中...'
        set_status('语音识别中...', COL_ACCENT)
        t = threading.Thread(target=_voice_process, daemon=True)
        t.start()

    # 把语音按钮的按住/松开回调接到面板上（语音页大按钮 + 键盘页小按钮共用）
    panel.voice_press_cb = voice_press
    panel.voice_release_cb = voice_release

    def _voice_process():
        text = voice.stop_and_recognize()
        if text:
            panel.append_text(text)
            panel.voice_status = '识别结果: %s' % text
            set_status('语音: %s' % text, COL_OK)
        else:
            panel.voice_status = '语音识别失败或未说话'
            set_status('语音识别失败或未说话', COL_WARN)

    # ----- 手机辅助页（随机端口）+ 二维码（手机页大图）-----
    bridge = PhoneBridge()
    bridge_ok = bridge.start()
    if bridge_ok:
        print('手机辅助页: %s' % bridge.url)
        qr_big = make_qr_surface(bridge.url, box_size=8)
        panel.set_phone_info(bridge.url, qr_big)
        panel.phone_status = '等待手机扫码推送...'
    else:
        panel.phone_status = '服务启动失败'
        print('手机辅助页启动失败（随机端口分配异常），不影响拼音输入')

    def set_status(text, color=COL_TEXT_MUTED):
        # 状态就近显示在对应页面（语音页/手机页），此处仅记录日志
        print('[状态] %s' % text)

    if voice.is_available():
        panel.voice_status = '语音已就绪'
    else:
        panel.voice_status = '语音未配置凭据'

    def do_submit():
        """提交（面板各页功能行「提交」按钮回调）：取出全部文字并清空"""
        text = panel.take_text()
        if text.strip():
            clip = ''
            try:
                pygame.scrap.init()
                pygame.scrap.put_text(text)
                clip = '，已复制到剪贴板'
            except Exception:
                pass
            set_status('已提交 %d 字%s' % (len(text), clip))
            print('提交文本: %r' % text)
        else:
            set_status('编辑区为空，未提交')

    panel.on_submit_cb = do_submit

    # ----- 退出按钮 -----
    exit_rect = pygame.Rect(WIDTH - 150, 22, 110, 56)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # 触摸诊断：记录每次按下的屏幕坐标（定位触摸映射问题后可移除）
                print('[触点] pos=%s' % (event.pos,))
                if exit_rect.collidepoint(event.pos):
                    running = False
                    continue
            panel.handle_event(event)

        # 手机推送轮询（手机端发送 = 覆盖设备编辑区，手机框内已含设备全文，不会重复）
        phone_text = bridge.get_text() if bridge_ok else None
        if phone_text:
            panel.set_text(phone_text)
            panel.phone_status = '已同步手机内容'
        if bridge_ok:
            bridge.set_current_text(panel.text)

        # ----- 绘制（顶栏仅 标题+退出；提交在各页功能行最右）-----
        screen.fill(COL_SKY)
        ts = f_title.render('拼音输入法', True, COL_TITLE)
        screen.blit(ts, (60, 24))
        # 退出按钮（立体感：投影 + 顶边高光）
        pygame.draw.rect(screen, (170, 55, 55), exit_rect.move(0, 3),
                         border_radius=14)
        pygame.draw.rect(screen, (235, 87, 87), exit_rect, border_radius=14)
        pygame.draw.line(screen, COL_WHITE,
                         (exit_rect.x + 8, exit_rect.y + 2),
                         (exit_rect.right - 8, exit_rect.y + 2), 2)
        et = f_status.render('退出', True, COL_WHITE)
        screen.blit(et, et.get_rect(center=exit_rect.center))
        # 输入面板
        panel.draw(screen)
        # 底部提示（左对齐）
        hint = f_hint.render(
            '点面板标签切换三页 | 三页均可USB键盘输入 | 空格选词 | 数字1-9选候选 | ◀▶候选翻页 | 「提交」取出全部文字 | ESC退出',
            True, COL_TEXT_MUTED)
        screen.blit(hint, (60, HEIGHT - 34))

        pygame.display.flip()
        clock.tick(30)

    # ----- 清理 -----
    try:
        bridge.stop()
    except Exception:
        pass
    panel.engine.save_user_freq()
    pygame.display.quit()
    print('拼音输入法 结束')


if __name__ == '__main__':
    main()
