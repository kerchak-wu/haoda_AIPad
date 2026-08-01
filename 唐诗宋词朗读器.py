# -*- coding: utf-8 -*-
"""
唐诗宋词朗读器 - 好搭AI派程序
=====================================
功能说明：
  1. 列表显示 5 首经典唐诗 + 5 首经典宋词
  2. 鼠标点击名称 -> 屏幕显示该诗词全文
  3. 点击「朗读」按钮 -> 语音合成并播放全文
  4. IO1 按键 -> 依次切换下一首
  5. IO2 按键 -> 朗读当前选中的诗词
  6. IO3 RGB 灯带(4 颗灯珠) -> 朗读时根据诗词意境显示炫酷灯光
  7. IO8 舵机 -> 选中不同诗词时转动到对应角度
  8. 提供「退出」按钮

硬件接线：
  - IO1 (GPIO_IO_01)  单按键模块(切换下一首)
  - IO2 (GPIO_IO_02)  单按键模块(朗读当前)
  - IO3 (GPIO_IO_03)  WS2812 RGB 灯带(4 灯)
  - IO8 (GPIO_IO_08)  灰色舵机
  注意：好搭AI派右下角开关需拨到左侧以启用外设接口。

参考范例：
  - 范例代码 2.扩展模块使用 4.RGB灯
  - 范例代码 2.扩展模块使用 5.舵机
  - 范例代码 2.扩展模块使用 7.按键控制灯光
  - 范例代码 3.音频处理 2.音频播放
  - 范例代码 4.语音AI 1.语音合成
  - 范例代码 8.pygame 10.音乐播放-按钮
"""

import os
import math
import time
import threading
import pygame
from ESP32 import *
from audio_player import AudioPlayer
from voice_api import VoiceAPI

# ===================== 配置 =====================
WIDTH, HEIGHT = 1920, 1080
# 字体参考《好搭AI派可用字体列表.txt》
FONT_PATH       = '/home/cxdz/jupyter/assets/PingFang_Regular.ttf'   # 常规
FONT_BOLD_PATH  = '/home/cxdz/jupyter/assets/PingFang_Bold.ttf'      # 粗体(标题/按钮)
FONT_KAI_PATH   = '/home/cxdz/jupyter/assets/simkai.ttf'             # 楷体(诗词正文)
BG_IMAGE = os.path.join('images', '1.jpg')   # 背景图片

# 引脚定义
BTN_NEXT_PIN = GPIO_IO_01   # IO1 切换下一首
BTN_READ_PIN = GPIO_IO_02   # IO2 朗读当前
LED_PIN      = GPIO_IO_03   # IO3 RGB灯带
SERVO_PIN    = GPIO_IO_08   # IO8 舵机

LED_COUNT = 4

# 语音 AI 认证 —— 请替换为自己经过认证的好好搭搭账号
VOICE_USERNAME = 'username'
VOICE_PASSWORD = 'password'

# ---- 界面配色 ----
BG_TOP        = (28, 22, 58)
BG_BOTTOM     = (8, 8, 28)
PANEL_COLOR   = (24, 22, 56)
PANEL_BORDER  = (90, 80, 160)
TITLE_COLOR   = (255, 215, 100)
TANG_COLOR    = (255, 170, 90)
SONG_COLOR    = (140, 200, 255)
TEXT_COLOR    = (245, 240, 225)
SUBTLE_COLOR  = (160, 160, 190)
HIGHLIGHT     = (255, 220, 80)
ITEM_NORMAL   = (40, 38, 80)
ITEM_HOVER    = (70, 65, 130)
ITEM_SELECTED = (95, 75, 175)
BTN_COLOR     = (70, 110, 200)
BTN_HOVER     = (110, 155, 240)
READ_COLOR    = (200, 70, 70)
READ_HOVER    = (240, 110, 110)
EXIT_COLOR    = (110, 110, 120)
EXIT_HOVER    = (190, 70, 70)
REFRESH_COLOR = (0, 180, 160)
REFRESH_HOVER = (40, 220, 200)
STATUS_OK     = (120, 220, 140)
STATUS_BUSY   = (255, 200, 80)


# ===================== 诗词数据 =====================
# 诗词数据池：每批 5 唐诗 + 5 宋词，点击「刷新」按钮在批次间循环切换
# 每首诗词附带 effect 字段，用于 RGB 灯带选择不同意境的灯光效果
POEM_BATCHES = [
    # 第 1 批
    [
        {'type': '唐', 'title': '静夜思', 'author': '李白',
         'content': '床前明月光，疑是地上霜。\n举头望明月，低头思故乡。',
         'effect': 'moonlight'},
        {'type': '唐', 'title': '春晓', 'author': '孟浩然',
         'content': '春眠不觉晓，处处闻啼鸟。\n夜来风雨声，花落知多少。',
         'effect': 'spring'},
        {'type': '唐', 'title': '登鹳雀楼', 'author': '王之涣',
         'content': '白日依山尽，黄河入海流。\n欲穷千里目，更上一层楼。',
         'effect': 'sunset'},
        {'type': '唐', 'title': '望庐山瀑布', 'author': '李白',
         'content': '日照香炉生紫烟，遥看瀑布挂前川。\n飞流直下三千尺，疑是银河落九天。',
         'effect': 'waterfall'},
        {'type': '唐', 'title': '江雪', 'author': '柳宗元',
         'content': '千山鸟飞绝，万径人踪灭。\n孤舟蓑笠翁，独钓寒江雪。',
         'effect': 'snow'},
        {'type': '宋', 'title': '水调歌头', 'author': '苏轼',
         'content': '明月几时有？把酒问青天。\n不知天上宫阙，今夕是何年。\n我欲乘风归去，又恐琼楼玉宇，高处不胜寒。\n起舞弄清影，何似在人间。\n转朱阁，低绮户，照无眠。\n不应有恨，何事长向别时圆？\n人有悲欢离合，月有阴晴圆缺，此事古难全。\n但愿人长久，千里共婵娟。',
         'effect': 'moonFull'},
        {'type': '宋', 'title': '念奴娇·赤壁怀古', 'author': '苏轼',
         'content': '大江东去，浪淘尽，千古风流人物。\n故垒西边，人道是，三国周郎赤壁。\n乱石穿空，惊涛拍岸，卷起千堆雪。\n江山如画，一时多少豪杰。\n遥想公瑾当年，小乔初嫁了，雄姿英发。\n羽扇纶巾，谈笑间，樯橹灰飞烟灭。\n故国神游，多情应笑我，早生华发。\n人生如梦，一尊还酹江月。',
         'effect': 'heroic'},
        {'type': '宋', 'title': '苏幕遮', 'author': '范仲淹',
         'content': '碧云天，黄叶地，秋色连波，波上寒烟翠。\n山映斜阳天接水，芳草无情，更在斜阳外。\n黯乡魂，追旅思，夜夜除非，好梦留人睡。\n明月楼高休独倚，酒入愁肠，化作相思泪。',
         'effect': 'autumn'},
        {'type': '宋', 'title': '声声慢', 'author': '李清照',
         'content': '寻寻觅觅，冷冷清清，凄凄惨惨戚戚。\n乍暖还寒时候，最难将息。\n三杯两盏淡酒，怎敌他、晚来风急？\n雁过也，正伤心，却是旧时相识。\n满地黄花堆积，憔悴损，如今有谁堪摘？\n守着窗儿，独自怎生得黑？\n梧桐更兼细雨，到黄昏、点点滴滴。\n这次第，怎一个愁字了得！',
         'effect': 'sorrow'},
        {'type': '宋', 'title': '满江红', 'author': '岳飞',
         'content': '怒发冲冠，凭栏处、潇潇雨歇。\n抬望眼，仰天长啸，壮怀激烈。\n三十功名尘与土，八千里路云和月。\n莫等闲，白了少年头，空悲切。\n靖康耻，犹未雪。臣子恨，何时灭！\n驾长车，踏破贺兰山缺。\n壮志饥餐胡虏肉，笑谈渴饮匈奴血。\n待从头、收拾旧山河，朝天阙。',
         'effect': 'passion'},
    ],
    # 第 2 批
    [
        {'type': '唐', 'title': '咏鹅', 'author': '骆宾王',
         'content': '鹅，鹅，鹅，\n曲项向天歌。\n白毛浮绿水，\n红掌拨清波。',
         'effect': 'spring'},
        {'type': '唐', 'title': '悯农', 'author': '李绅',
         'content': '锄禾日当午，汗滴禾下土。\n谁知盘中餐，粒粒皆辛苦。',
         'effect': 'sunset'},
        {'type': '唐', 'title': '枫桥夜泊', 'author': '张继',
         'content': '月落乌啼霜满天，江枫渔火对愁眠。\n姑苏城外寒山寺，夜半钟声到客船。',
         'effect': 'moonlight'},
        {'type': '唐', 'title': '出塞', 'author': '王昌龄',
         'content': '秦时明月汉时关，万里长征人未还。\n但使龙城飞将在，不教胡马度阴山。',
         'effect': 'heroic'},
        {'type': '唐', 'title': '早发白帝城', 'author': '李白',
         'content': '朝辞白帝彩云间，千里江陵一日还。\n两岸猿声啼不住，轻舟已过万重山。',
         'effect': 'waterfall'},
        {'type': '宋', 'title': '如梦令', 'author': '李清照',
         'content': '昨夜雨疏风骤，浓睡不消残酒。\n试问卷帘人，却道海棠依旧。\n知否，知否？应是绿肥红瘦。',
         'effect': 'autumn'},
        {'type': '宋', 'title': '雨霖铃', 'author': '柳永',
         'content': '寒蝉凄切，对长亭晚，骤雨初歇。\n都门帐饮无绪，留恋处，兰舟催发。\n执手相看泪眼，竟无语凝噎。\n念去去，千里烟波，暮霭沉沉楚天阔。\n多情自古伤离别，更那堪，冷落清秋节！\n今宵酒醒何处？杨柳岸，晓风残月。\n此去经年，应是良辰好景虚设。\n便纵有千种风情，更与何人说？',
         'effect': 'sorrow'},
        {'type': '宋', 'title': '青玉案·元夕', 'author': '辛弃疾',
         'content': '东风夜放花千树，更吹落、星如雨。\n宝马雕车香满路。\n凤箫声动，玉壶光转，一夜鱼龙舞。\n蛾儿雪柳黄金缕，笑语盈盈暗香去。\n众里寻他千百度，蓦然回首，那人却在，灯火阑珊处。',
         'effect': 'passion'},
        {'type': '宋', 'title': '卜算子·咏梅', 'author': '陆游',
         'content': '驿外断桥边，寂寞开无主。\n已是黄昏独自愁，更著风和雨。\n无意苦争春，一任群芳妒。\n零落成泥碾作尘，只有香如故。',
         'effect': 'snow'},
        {'type': '宋', 'title': '虞美人', 'author': '李煜',
         'content': '春花秋月何时了？往事知多少。\n小楼昨夜又东风，故国不堪回首月明中。\n雕栏玉砌应犹在，只是朱颜改。\n问君能有几多愁？恰似一江春水向东流。',
         'effect': 'moonFull'},
    ],
]

# 当前显示的诗词列表(初始为第 1 批)
POEMS = POEM_BATCHES[0]
current_batch = 0   # 当前批次序号


# ===================== 硬件初始化 =====================
# 严格参照范例代码：ESP32 初始化 + 异常处理
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    # RGB 灯带初始化(单独 try，避免异常连带影响舵机)
    try:
        board.ws2812Init((LED_PIN), LED_COUNT)
        board.ws2812Write((LED_PIN), 255, 0, 0, 0)   # 初始熄灭
        print('RGB灯带初始化完成：IO3')
    except Exception as e:
        print('RGB灯带初始化异常:', e)

    # 舵机初始化(单独 try)
    try:
        board.servo((SERVO_PIN), 0)                    # 舵机回零位
        time.sleep(0.5)
        print('舵机初始化完成：IO8，已归零到 0°')
    except Exception as e:
        print('舵机初始化异常:', e)

    print('硬件初始化完成：按键(IO1/IO2) + RGB灯带(IO3) + 舵机(IO8)')

# 音频播放器 + 语音 AI
player = AudioPlayer()
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token(VOICE_USERNAME, VOICE_PASSWORD)
if not token_result:
    print('语音 AI 认证失败，请检查账号密码')
else:
    print('语音 AI 认证成功')


# ===================== 全局状态 =====================
current_index = 0          # 当前选中诗词序号
is_reading = False         # 是否正在朗读
stop_requested = False     # 是否请求停止朗读
status_message = '就绪'
status_color = STATUS_OK

led_thread = None
led_running = False
current_effect = None   # 当前灯效名称(None 表示关闭)
led_frame = 0           # 灯效帧计数

# 按键边沿检测 (上次状态)
btn_next_last = 0
btn_read_last = 0


# ===================== RGB 灯带效果 =====================
# 参照范例 2.扩展模块使用 4.RGB灯 的 wheel 函数与 ws2812Write 调用方式
def wheel(pos):
    """生成 0-255 位置的彩虹颜色，参照 RGB 灯范例"""
    if pos < 0 or pos > 255:
        pos %= 256
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)


def led_set_all(r, g, b):
    """点亮全部灯珠为同一颜色"""
    try:
        for i in range(LED_COUNT):
            board.ws2812Write((LED_PIN), i, r, g, b)
    except:
        pass


def led_off():
    """熄灭所有灯珠"""
    try:
        board.ws2812Write((LED_PIN), 255, 0, 0, 0)
    except:
        pass


def update_led_frame():
    """在主循环中按帧更新灯效(单线程，与范例调用风格一致)"""
    global led_frame
    if current_effect is None:
        return
    t = led_frame
    try:
        if current_effect == 'moonlight':
            # 静夜思：冷月白蓝呼吸
            b = (math.sin(t * 0.10) + 1) * 0.5
            r = int(110 + 90 * b)
            g = int(140 + 90 * b)
            bl = int(210 + 45 * b)
            led_set_all(r, g, bl)

        elif current_effect == 'spring':
            # 春晓：粉绿春色流动
            for i in range(LED_COUNT):
                pos = (t + i * 60) % 256
                c = wheel(pos)
                board.ws2812Write((LED_PIN), i, c[0], c[1] // 2 + 80, c[2])

        elif current_effect == 'sunset':
            # 登鹳雀楼：夕阳红橙追逐
            for i in range(LED_COUNT):
                pos = (t * 5 + i * 40) % 256
                if pos < 128:
                    board.ws2812Write((LED_PIN), i, 255, 100 + pos, 30)
                else:
                    board.ws2812Write((LED_PIN), i, 200, 70, 20)

        elif current_effect == 'waterfall':
            # 望庐山瀑布：白蓝流光
            for i in range(LED_COUNT):
                pos = (t + i * 30) % 60
                v = 255 if pos < 20 else (160 if pos < 40 else 80)
                board.ws2812Write((LED_PIN), i, v, v, 255)

        elif current_effect == 'snow':
            # 江雪：冷白闪烁
            for i in range(LED_COUNT):
                if (t + i * 15) % 80 < 40:
                    board.ws2812Write((LED_PIN), i, 220, 230, 255)
                else:
                    board.ws2812Write((LED_PIN), i, 70, 95, 160)

        elif current_effect == 'moonFull':
            # 水调歌头：银月呼吸
            b = int(180 + 75 * (math.sin(t * 0.08) + 1) * 0.5)
            led_set_all(200, 220, b)

        elif current_effect == 'heroic':
            # 念奴娇：红金火焰跳
            for i in range(LED_COUNT):
                g = int(100 + 110 * (math.sin((t + i * 20) * 0.15) + 1) * 0.5)
                board.ws2812Write((LED_PIN), i, 255, g, 20)

        elif current_effect == 'autumn':
            # 苏幕遮：秋色黄粉绿轮转
            palette = [(220, 180, 60), (200, 100, 80), (120, 180, 80), (180, 140, 60)]
            idx = (t // 20) % LED_COUNT
            for i in range(LED_COUNT):
                c = palette[(i + idx) % len(palette)]
                board.ws2812Write((LED_PIN), i, c[0], c[1], c[2])

        elif current_effect == 'sorrow':
            # 声声慢：暗紫低吟
            b = int(40 + 30 * (math.sin(t * 0.05) + 1) * 0.5)
            led_set_all(50, 20, 60 + b)

        elif current_effect == 'passion':
            # 满江红：血红金光涌
            for i in range(LED_COUNT):
                pos = (t * 10 + i * 60) % 256
                if pos < 128:
                    board.ws2812Write((LED_PIN), i, 255, 50, 30)
                else:
                    board.ws2812Write((LED_PIN), i, 220, 150, 30)
        else:
            led_set_all(80, 80, 120)

        led_frame += 1
    except:
        pass


def start_led_effect(effect_name):
    """启动某种灯效(设置当前灯效名，由主循环按帧驱动)"""
    global current_effect, led_frame
    current_effect = effect_name
    led_frame = 0


def stop_led_effect():
    """停止灯效并熄灭"""
    global current_effect, led_frame
    current_effect = None
    led_frame = 0
    led_off()


# ===================== 舵机控制 =====================
def servo_to_index(idx):
    """根据诗词序号转动舵机 (10 首均分 0~180 度)"""
    angle = int(idx * 180 / (len(POEMS) - 1))
    print('[舵机] 切换到第 %d 首 -> IO8 角度 %d°' % (idx, angle))
    try:
        board.servo((SERVO_PIN), angle)
        time.sleep(0.3)   # 给舵机转动到位的时间
    except Exception as e:
        print('[舵机] 控制异常:', e)


# ===================== 语音朗读 =====================
def get_poem_audio_path(idx):
    """获取某首诗词对应的本地音频缓存路径"""
    return 'recordings/poem_%d.wav' % idx


def read_poem_async(idx):
    """异步朗读指定诗词：先 TTS 合成(有缓存)，再播放，并启动灯效"""
    global is_reading, status_message, status_color, stop_requested
    if is_reading:
        return
    is_reading = True
    stop_requested = False
    status_message = '正在朗读…'
    status_color = STATUS_BUSY

    def worker():
        global is_reading, status_message, status_color
        try:
            poem = POEMS[idx]
            text = poem['title'] + '，' + poem['author'] + '。' + poem['content'].replace('\n', '')
            audio_path = get_poem_audio_path(idx)
            if not os.path.exists(audio_path):
                status_message = '语音合成中…'
                if stop_requested:
                    return
                audio_data = voice_api.tts_synthesize(text, audio_path)
                if not audio_data:
                    status_message = '语音合成失败'
                    status_color = STATUS_BUSY
                    is_reading = False
                    return
            if stop_requested:
                is_reading = False
                status_message = '已停止'
                status_color = STATUS_OK
                return
            start_led_effect(poem['effect'])
            status_message = '朗读中：' + poem['title']
            # 使用非阻塞播放，主循环中轮询 stop_requested 实现停止
            play_audio_interruptible(audio_path)
        except Exception as e:
            print('朗读异常:', e)
            status_message = '朗读异常'
        finally:
            stop_led_effect()
            is_reading = False
            if status_message != '已停止':
                status_message = '就绪'
                status_color = STATUS_OK

    threading.Thread(target=worker, daemon=True).start()


def play_audio_interruptible(audio_path):
    """非阻塞播放音频，支持被 stop_requested 中断"""
    global stop_requested
    try:
        # AudioPlayer 的 play_file 默认阻塞；这里用 pygame.mixer 实现可中断播放
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.set_volume(0.9)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if stop_requested:
                pygame.mixer.music.stop()
                break
            time.sleep(0.1)
    except Exception as e:
        print('播放异常:', e)


def stop_reading():
    """停止当前朗读与灯效"""
    global is_reading, status_message, status_color, stop_requested
    if not is_reading:
        return
    stop_requested = True
    try:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
    except:
        pass
    stop_led_effect()
    is_reading = False
    status_message = '已停止'
    status_color = STATUS_OK


# ===================== Pygame 界面 =====================
def make_gradient_bg(width, height, top, bottom):
    """生成垂直渐变背景"""
    surf = pygame.Surface((width, height))
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        pygame.draw.line(surf, (r, g, b), (0, y), (width, y))
    return surf


def draw_round_rect(surf, color, rect, radius=12, width=0):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


class Button:
    """通用圆角按钮"""

    def __init__(self, rect, text, color, hover_color, text_color=TEXT_COLOR):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.hovered = False
        self.enabled = True

    def update(self, mouse_pos):
        self.hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def draw(self, surf, font):
        c = self.hover_color if self.hovered else self.color
        if not self.enabled:
            c = (60, 60, 70)
        btn = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn, c, btn.get_rect(), border_radius=14)
        # 白色边框提升可见性
        pygame.draw.rect(btn, (255, 255, 255, 180), btn.get_rect(), 2, border_radius=14)
        surf.blit(btn, self.rect.topleft)
        label = font.render(self.text, True, self.text_color)
        lr = label.get_rect(center=self.rect.center)
        surf.blit(label, lr)

    def clicked(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


class PoemApp:
    LIST_W = 580
    TITLE_H = 140
    FOOTER_H = 140

    def __init__(self):
        pygame.init()
        pygame.font.init()
        pygame.mixer.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('唐诗宋词朗读器')
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.Font(FONT_BOLD_PATH, 64)
        self.font_sub   = pygame.font.Font(FONT_PATH, 26)
        self.font_item  = pygame.font.Font(FONT_BOLD_PATH, 34)
        self.font_auth  = pygame.font.Font(FONT_PATH, 24)
        self.font_poem  = pygame.font.Font(FONT_KAI_PATH, 40)   # 楷体显示诗词
        self.font_btn   = pygame.font.Font(FONT_BOLD_PATH, 36)
        self.font_small = pygame.font.Font(FONT_PATH, 24)
        self.font_badge = pygame.font.Font(FONT_BOLD_PATH, 26)

        # 加载背景图片，缩放至窗口尺寸
        try:
            bg_raw = pygame.image.load(BG_IMAGE)
            self.bg = pygame.transform.smoothscale(bg_raw, (WIDTH, HEIGHT))
        except Exception as e:
            print('背景图片加载失败，使用渐变背景:', e)
            self.bg = make_gradient_bg(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM)
        self.running = True

        # 列表条目区域
        self.list_rect = pygame.Rect(24, self.TITLE_H + 20,
                                     self.LIST_W, HEIGHT - self.TITLE_H - self.FOOTER_H - 40)
        self.item_rects = []
        self._build_item_rects()

        # 详情区域
        self.detail_rect = pygame.Rect(self.LIST_W + 48, self.TITLE_H + 20,
                                       WIDTH - self.LIST_W - 72,
                                       HEIGHT - self.TITLE_H - self.FOOTER_H - 40)

        # 按钮(朗读 / 停止 / 刷新 / 退出)
        btn_y = HEIGHT - self.FOOTER_H + 40
        btn_h = 72
        btn_gap = 28
        btn_x = self.LIST_W + 48
        self.btn_read  = Button((btn_x, btn_y, 180, btn_h), '朗读', READ_COLOR, READ_HOVER)
        btn_x += 180 + btn_gap
        self.btn_stop  = Button((btn_x, btn_y, 180, btn_h), '停止', BTN_COLOR, BTN_HOVER)
        btn_x += 180 + btn_gap
        self.btn_refresh = Button((btn_x, btn_y, 240, btn_h), '换一批', REFRESH_COLOR, REFRESH_HOVER)
        self.btn_exit = Button((WIDTH - 220, btn_y, 180, btn_h), '退出', EXIT_COLOR, EXIT_HOVER)

        # 初始选中并驱动硬件
        self.select_poem(0, drive_hardware=False)
        servo_to_index(0)

    def _build_item_rects(self):
        self.item_rects = []
        x = self.list_rect.x + 14
        y = self.list_rect.y + 40   # 顶部留给「唐诗·五首」分组小标题
        w = self.list_rect.w - 28
        h = 56                      # 标题与作者同行，行高减小
        gap = 8
        for idx in range(len(POEMS)):
            # 在第 6 项(宋词第一首)前留出宋词小标题的位置
            if idx == 5:
                y += 32
            self.item_rects.append(pygame.Rect(x, y, w, h))
            y += h + gap

    # ---------- 交互 ----------
    def select_poem(self, idx, drive_hardware=True):
        """切换选中诗词"""
        global current_index
        idx = idx % len(POEMS)
        current_index = idx
        if drive_hardware:
            servo_to_index(idx)

    def handle_click(self, pos):
        if self.btn_read.clicked(pos):
            self.on_read()
            return
        if self.btn_stop.clicked(pos):
            self.on_stop()
            return
        if self.btn_refresh.clicked(pos):
            self.on_refresh()
            return
        if self.btn_exit.clicked(pos):
            self.running = False
            return
        for i, r in enumerate(self.item_rects):
            if r.collidepoint(pos):
                self.select_poem(i)
                return

    def on_stop(self):
        stop_reading()

    def on_read(self):
        read_poem_async(current_index)

    def on_refresh(self):
        """切换到下一批诗词(5 唐 + 5 宋)，并复位选中与硬件"""
        global POEMS, current_batch, current_index
        # 先停止当前朗读与灯效
        stop_reading()
        current_batch = (current_batch + 1) % len(POEM_BATCHES)
        POEMS = POEM_BATCHES[current_batch]
        print('[换一批] 切换到第 %d/%d 批诗词' % (current_batch + 1, len(POEM_BATCHES)))
        # 重建列表项矩形并复位
        self._build_item_rects()
        self.select_poem(0, drive_hardware=False)
        servo_to_index(0)

    # ---------- 按键扫描 (P0 / P1) ----------
    # 参照范例 2.扩展模块使用 7.按键控制灯光 的边沿检测写法
    def scan_buttons(self):
        global btn_next_last, btn_read_last
        try:
            v_next = board.digitalRead((BTN_NEXT_PIN))
            v_read = board.digitalRead((BTN_READ_PIN))
        except:
            return

        # 上升沿触发 (松开变按下)
        if v_next == 1 and btn_next_last == 0:
            self.select_poem(current_index + 1)
            time.sleep(0.02)
        btn_next_last = v_next

        if v_read == 1 and btn_read_last == 0:
            self.on_read()
            time.sleep(0.02)
        btn_read_last = v_read

    # ---------- 绘制 ----------
    def draw_title(self):
        # 顶部半透明遮罩，让标题文字在图片背景上清晰可见
        mask = pygame.Surface((WIDTH, self.TITLE_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (0, 0, 0, 120), mask.get_rect())
        self.screen.blit(mask, (0, 0))

        title = self.font_title.render('唐诗宋词朗读器', True, TITLE_COLOR)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 28))
        sub = self.font_sub.render(
            'IO1 切换下一首    IO2 朗读当前    点击名称查看全文    朗读 / 停止 / 换一批 / 退出',
            True, SUBTLE_COLOR)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 100))

    def draw_list(self, mouse_pos):
        # 面板背景(带半透明，便于阅读文字)
        panel = pygame.Surface(self.list_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 210), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.list_rect.topleft)

        # 分组小标题(绘制在面板顶部)
        head = self.font_sub.render('唐诗 · 五首', True, TANG_COLOR)
        self.screen.blit(head, (self.list_rect.x + 18, self.list_rect.y + 10))
        song_head = self.font_sub.render('宋词 · 五首', True, SONG_COLOR)

        for i, poem in enumerate(POEMS):
            r = self.item_rects[i]
            hover = r.collidepoint(mouse_pos)
            if i == current_index:
                color = ITEM_SELECTED
                border = HIGHLIGHT
            elif hover:
                color = ITEM_HOVER
                border = (130, 120, 200)
            else:
                color = ITEM_NORMAL
                border = None

            item = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(item, color, item.get_rect(), border_radius=10)
            if border:
                pygame.draw.rect(item, border, item.get_rect(), 2, border_radius=10)
            self.screen.blit(item, r.topleft)

            # 类型徽标(左侧)
            badge_color = TANG_COLOR if poem['type'] == '唐' else SONG_COLOR
            badge_rect = pygame.Rect(r.x + 12, r.y + 14, 44, 36)
            pygame.draw.rect(self.screen, badge_color, badge_rect, border_radius=6)
            badge_text = self.font_badge.render(poem['type'], True, (30, 20, 40))
            self.screen.blit(badge_text, (badge_rect.centerx - badge_text.get_width() // 2,
                                          badge_rect.centery - badge_text.get_height() // 2))

            # 标题 + 作者 放在同一行：标题在前，作者紧跟其后
            title_surf = self.font_item.render(poem['title'], True, TEXT_COLOR)
            author_surf = self.font_auth.render('  — ' + poem['author'], True, SUBTLE_COLOR)

            # 计算垂直居中位置
            title_y = r.centery - title_surf.get_height() // 2
            author_y = r.centery - author_surf.get_height() // 2

            # 先绘制标题，限制最大宽度
            text_x = r.x + 66
            max_title_w = r.w - 80
            if title_surf.get_width() > max_title_w:
                new_w = max_title_w
                new_h = int(title_surf.get_height() * new_w / title_surf.get_width())
                title_surf = pygame.transform.smoothscale(title_surf, (new_w, new_h))
                title_y = r.centery - new_h // 2
            self.screen.blit(title_surf, (text_x, title_y))

            # 作者紧跟标题右侧；若超出选择框则省略作者
            author_x = text_x + title_surf.get_width() + 8
            if author_x + author_surf.get_width() <= r.right - 12:
                self.screen.blit(author_surf, (author_x, author_y))

            # 在第 6 项(宋词第一首)上方显示宋词小标题
            if i == 5:
                self.screen.blit(song_head, (self.list_rect.x + 18, r.y - 32))

    def draw_detail(self):
        # 面板背景
        panel = pygame.Surface(self.detail_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL_COLOR, 210), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 2, border_radius=18)
        self.screen.blit(panel, self.detail_rect.topleft)

        poem = POEMS[current_index]
        pad = 40
        x = self.detail_rect.x + pad
        y = self.detail_rect.y + pad
        max_text_w = self.detail_rect.w - pad * 2 - 20   # 正文最大宽度，防溢出

        # 标题(限制宽度)
        title = self.font_poem.render(poem['title'], True, TITLE_COLOR)
        if title.get_width() > max_text_w:
            title = pygame.transform.smoothscale(
                title, (max_text_w, int(title.get_height() * max_text_w / title.get_width())))
        self.screen.blit(title, (x, y))

        # 作者 + 类型
        meta = self.font_auth.render(
            '【%s】  %s' % ('唐诗' if poem['type'] == '唐' else '宋词', poem['author']),
            True, SUBTLE_COLOR)
        self.screen.blit(meta, (x, y + title.get_height() + 6))

        # 分隔线
        sep_y = y + title.get_height() + 44
        pygame.draw.line(self.screen, PANEL_BORDER,
                         (x, sep_y), (self.detail_rect.right - pad, sep_y), 1)

        # 正文(逐行绘制，超宽时缩放；底部预留状态信息位置)
        text_y = sep_y + 24
        bottom_limit = self.detail_rect.bottom - pad - 36
        line_gap = 12
        for line in poem['content'].split('\n'):
            line_surf = self.font_poem.render(line, True, TEXT_COLOR)
            if line_surf.get_width() > max_text_w:
                new_h = int(line_surf.get_height() * max_text_w / line_surf.get_width())
                line_surf = pygame.transform.smoothscale(line_surf, (max_text_w, new_h))
            # 若超出面板底部，则停止绘制(防溢出)
            if text_y + line_surf.get_height() > bottom_limit:
                ell = self.font_small.render('……(正文过长，已截断)', True, SUBTLE_COLOR)
                self.screen.blit(ell, (x + 10, bottom_limit))
                break
            self.screen.blit(line_surf, (x + 10, text_y))
            text_y += line_surf.get_height() + line_gap

        # 舵机角度 + 批次提示
        angle = int(current_index * 180 / (len(POEMS) - 1))
        info_text = '舵机: %d°    灯效: %s    第%d/%d批' % (
            angle, poem['effect'], current_batch + 1, len(POEM_BATCHES))
        info = self.font_small.render(info_text, True, SUBTLE_COLOR)
        self.screen.blit(info, (x, self.detail_rect.bottom - pad - 8))

    def draw_footer(self, mouse_pos):
        # 底部半透明遮罩
        mask = pygame.Surface((WIDTH, self.FOOTER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (0, 0, 0, 120), mask.get_rect())
        self.screen.blit(mask, (0, HEIGHT - self.FOOTER_H))

        # 朗读 / 停止 / 刷新 / 退出 按钮
        self.btn_read.update(mouse_pos)
        self.btn_stop.update(mouse_pos)
        self.btn_refresh.update(mouse_pos)
        self.btn_exit.update(mouse_pos)
        # 未在朗读时禁用停止按钮；朗读中禁用刷新按钮避免音频状态混乱
        self.btn_stop.enabled = is_reading
        self.btn_refresh.enabled = not is_reading
        self.btn_read.draw(self.screen, self.font_btn)
        self.btn_stop.draw(self.screen, self.font_btn)
        self.btn_refresh.draw(self.screen, self.font_btn)
        self.btn_exit.draw(self.screen, self.font_btn)

        # 状态文字(放在刷新按钮右侧)
        status = self.font_small.render(status_message, True, status_color)
        self.screen.blit(status, (self.btn_refresh.rect.right + 40,
                                  self.btn_refresh.rect.centery - status.get_height() // 2))

        # 选中提示
        cur = POEMS[current_index]
        info = self.font_small.render(
            '当前: %s · %s' % (cur['title'], cur['author']),
            True, TEXT_COLOR)
        self.screen.blit(info, (40, HEIGHT - self.FOOTER_H + 50))

    def run(self):
        while self.running:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.handle_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_DOWN or event.key == pygame.K_RIGHT:
                        self.select_poem(current_index + 1)
                    elif event.key == pygame.K_UP or event.key == pygame.K_LEFT:
                        self.select_poem(current_index - 1)
                    elif event.key == pygame.K_SPACE:
                        self.on_read()

            # 扫描硬件按键
            self.scan_buttons()

            # 按帧更新 RGB 灯效(单线程，与范例调用风格一致)
            update_led_frame()

            # 绘制
            self.screen.blit(self.bg, (0, 0))
            self.draw_title()
            self.draw_list(mouse_pos)
            self.draw_detail()
            self.draw_footer(mouse_pos)

            pygame.display.flip()
            self.clock.tick(30)

        # 退出清理
        stop_led_effect()
        try:
            led_off()
        except:
            pass
        pygame.quit()


# ===================== 入口 =====================
if __name__ == '__main__':
    app = PoemApp()
    app.run()
