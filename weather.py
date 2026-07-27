# -*- coding: utf-8 -*-
"""
天气预报程序 - 好搭AI派
- 窗口尺寸 1920 x 1080
- 屏幕上选择不同城市，显示所选城市的实时天气和7天预报
- 天气信息框背景随天气情况渐变（晴/阴/雨/雪/雷/雾各有专属配色）
- 右上角提供单独的「退出程序」按钮
- 数据源：Open-Meteo（免费、无需密钥）

UI 风格参考仓库中的音乐播放器 / 红色文化交互展示程序：
  - 半透明深色遮罩保证文字可读性
  - 自定义 Button 类，支持 hover
  - 纯白文字 + 高亮色（ACCENT 蓝）
"""
import os
import sys
import math
import json
import ssl
import time
import urllib.request
import urllib.parse
from datetime import datetime

import pygame

# ============ 配置 ============
WIDTH, HEIGHT = 1920, 1080
FONT_PATH = '/home/cxdz/jupyter/assets/simfang.ttf'   # 好搭AI派内置中文字体

# 颜色
WHITE = (255, 255, 255)
TEXT_COLOR = (255, 255, 255)
ACCENT = (86, 196, 255)
GOLD = (255, 210, 90)
PANEL_DARK = (0, 0, 0, 140)                # 通用半透明深色面板
BTN_NORMAL = (255, 255, 255, 55)
BTN_HOVER = (86, 196, 255, 180)
BTN_SELECTED = (255, 210, 90, 230)
EXIT_RED = (235, 87, 87)
BTN_EXIT_NORMAL = (160, 40, 40, 100)
BTN_EXIT_HOVER = (235, 87, 87, 220)

# 城市列表（中文名 + 查询关键词）
CITIES = [
    {'name': '北京',   'q': 'Beijing'},
    {'name': '上海',   'q': 'Shanghai'},
    {'name': '广州',   'q': 'Guangzhou'},
    {'name': '深圳',   'q': 'Shenzhen'},
    {'name': '成都',   'q': 'Chengdu'},
    {'name': '杭州',   'q': 'Hangzhou'},
    {'name': '哈尔滨', 'q': 'Harbin'},
    {'name': '三亚',   'q': 'Sanya'},
]

# 全屏背景渐变（上色、下色）- 较深，保证白色文字清晰
SCREEN_THEMES = {
    'clear-day':   ((30, 80, 150),   (90, 150, 220)),
    'clear-night': ((10, 15, 40),    (30, 40, 80)),
    'cloudy':      ((55, 65, 90),    (110, 125, 150)),
    'rain':        ((30, 45, 70),    (60, 80, 110)),
    'snow':        ((70, 90, 130),   (140, 165, 200)),
    'thunder':     ((20, 22, 40),    (45, 48, 75)),
    'fog':         ((60, 65, 80),    (110, 115, 130)),
}

# 天气信息卡片渐变（上色、下色）- 与该天气类型呼应，区分度强
CARD_THEMES = {
    'clear-day':   ((255, 180, 60),  (255, 120, 50)),     # 阳光金橙
    'clear-night': ((40, 50, 110),   (20, 25, 60)),       # 夜空深蓝
    'cloudy':      ((160, 170, 190), (110, 120, 145)),    # 灰云
    'rain':        ((70, 110, 180),  (40, 70, 130)),      # 雨蓝
    'snow':        ((200, 225, 250), (150, 180, 220)),    # 雪青
    'thunder':     ((90, 70, 160),   (50, 40, 100)),      # 雷紫
    'fog':         ((180, 185, 200), (130, 135, 155)),    # 雾灰
}

# WMO 天气代码 -> (中文描述, 主题类型)
WMO = {
    0:  ('晴',      'clear-day'),
    1:  ('晴间多云', 'clear-day'),
    2:  ('多云',    'cloudy'),
    3:  ('阴',      'cloudy'),
    45: ('有雾',    'fog'),
    48: ('雾凇',    'fog'),
    51: ('小毛毛雨', 'rain'),
    53: ('毛毛雨',   'rain'),
    55: ('大毛毛雨', 'rain'),
    56: ('冻毛毛雨', 'rain'),
    57: ('冻雨',    'rain'),
    61: ('小雨',    'rain'),
    63: ('中雨',    'rain'),
    65: ('大雨',    'rain'),
    66: ('冻小雨',  'rain'),
    67: ('冻大雨',  'rain'),
    71: ('小雪',    'snow'),
    73: ('中雪',    'snow'),
    75: ('大雪',    'snow'),
    77: ('米雪',    'snow'),
    80: ('小阵雨',  'rain'),
    81: ('阵雨',    'rain'),
    82: ('强阵雨',  'thunder'),
    85: ('阵雪',    'snow'),
    86: ('强阵雪',  'snow'),
    95: ('雷暴',    'thunder'),
    96: ('雷暴冰雹', 'thunder'),
    99: ('强雷暴',   'thunder'),
}


# ============ 数据获取 ============
def code_info(code, is_day):
    """根据 WMO 代码返回 (描述, 主题类型)"""
    text, cls = WMO.get(code, ('未知', 'cloudy'))
    if cls == 'clear-day' and not is_day:
        cls = 'clear-night'
    return text, cls


def fetch_json(url):
    """发起 HTTPS 请求，返回 JSON"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'haohaodada-weather/1.0'})
    with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
        return json.loads(r.read().decode('utf-8'))


def geocode(query):
    """根据城市名查询经纬度"""
    url = ('https://geocoding-api.open-meteo.com/v1/search?name='
           + urllib.parse.quote(query) + '&count=1&language=zh&format=json')
    j = fetch_json(url)
    return j['results'][0] if j.get('results') else None


def get_weather(lat, lon):
    """根据经纬度获取完整天气数据"""
    url = (f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}'
           '&current=temperature_2m,relative_humidity_2m,apparent_temperature,'
           'is_day,weather_code,wind_speed_10m,wind_direction_10m,pressure_msl'
           '&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset'
           '&timezone=auto&forecast_days=7')
    return fetch_json(url)


def wind_dir(deg):
    dirs = ['北', '东北偏北', '东北', '东北偏东', '东', '东南偏东', '东南', '东南偏南',
            '南', '西南偏南', '西南', '西南偏西', '西', '西北偏西', '西北', '西北偏北']
    return dirs[round(deg / 22.5) % 16]


# ============ 字体 ============
def find_chinese_font():
    """优先使用好搭AI派内置字体，再回退到系统候选字体"""
    if os.path.exists(FONT_PATH):
        return FONT_PATH
    candidates = [
        "simhei", "microsoftyahei", "msyh", "pingfang",
        "notosanscjksc", "notosanscjk", "wenquanyimicrohei",
        "wqymicrohei", "stheiti", "arialunicodems",
        "simfang",
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


def make_font(font_name, size, bold=False):
    if font_name and (font_name.startswith("/") or "\\" in font_name or
                      (len(font_name) > 2 and font_name[1] == ":")):
        try:
            f = pygame.font.Font(font_name, size)
            f.set_bold(bold)
            return f
        except Exception:
            pass
    try:
        return pygame.font.SysFont(font_name, size, bold=bold)
    except Exception:
        return pygame.font.Font(None, size)


# ============ 天气图标绘制 ============
def draw_icon(surf, cls, cx, cy, size, is_day=True):
    """在 surf 上绘制天气图标，中心 (cx, cy)，大小 size"""
    r = size // 2

    if cls == 'clear-day':
        sun = (255, 210, 70)
        pygame.draw.circle(surf, sun, (cx, cy), r - 6)
        pygame.draw.circle(surf, (255, 240, 150), (cx, cy), r - 6, 3)
        for i in range(12):
            a = math.radians(i * 30)
            x1 = int(cx + math.cos(a) * (r - 2))
            y1 = int(cy + math.sin(a) * (r - 2))
            x2 = int(cx + math.cos(a) * (r + 8))
            y2 = int(cy + math.sin(a) * (r + 8))
            pygame.draw.line(surf, sun, (x1, y1), (x2, y2), 5)

    elif cls == 'clear-night':
        moon = (245, 245, 220)
        pygame.draw.circle(surf, moon, (cx, cy), r - 6)
        # 阴影形成新月
        pygame.draw.circle(surf, (40, 50, 90), (cx + 10, cy - 4), r - 10)
        # 小星星
        for (sx, sy) in [(cx - r, cy - r), (cx + r - 4, cy + r), (cx - r + 4, cy + r - 4)]:
            pygame.draw.circle(surf, (255, 255, 200), (sx, sy), 3)

    elif cls == 'cloudy':
        cloud = (250, 250, 255)
        pygame.draw.circle(surf, cloud, (cx - r // 2, cy + r // 4), r // 2 + 4)
        pygame.draw.circle(surf, cloud, (cx + r // 2, cy + r // 4), r // 2 + 4)
        pygame.draw.circle(surf, cloud, (cx, cy), int(r * 0.7))
        if is_day:
            pygame.draw.circle(surf, (255, 200, 60), (cx + r // 2, cy - r // 3), r // 3)

    elif cls == 'rain':
        cloud = (190, 200, 220)
        pygame.draw.circle(surf, cloud, (cx - r // 2, cy - 4), r // 2 + 4)
        pygame.draw.circle(surf, cloud, (cx + r // 2, cy - 4), r // 2 + 4)
        pygame.draw.circle(surf, cloud, (cx, cy - r // 4), int(r * 0.7))
        for i in range(4):
            xx = cx - r // 2 + i * (r // 3)
            yy = cy + r // 2 + 6
            pygame.draw.line(surf, (90, 180, 255),
                             (xx, yy), (xx - 5, yy + r // 2), 4)

    elif cls == 'snow':
        cloud = (225, 230, 245)
        pygame.draw.circle(surf, cloud, (cx - r // 2, cy - 4), r // 2 + 4)
        pygame.draw.circle(surf, cloud, (cx + r // 2, cy - 4), r // 2 + 4)
        pygame.draw.circle(surf, cloud, (cx, cy - r // 4), int(r * 0.7))
        for i in range(3):
            xx = cx - r // 2 + i * (r // 2)
            yy = cy + r // 2 + 10
            for k in range(3):
                a = math.radians(k * 60)
                x2 = int(xx + math.cos(a) * 7)
                y2 = int(yy + math.sin(a) * 7)
                x3 = int(xx - math.cos(a) * 7)
                y3 = int(yy - math.sin(a) * 7)
                pygame.draw.line(surf, (255, 255, 255), (x2, y2), (x3, y3), 2)

    elif cls == 'thunder':
        cloud = (100, 105, 130)
        pygame.draw.circle(surf, cloud, (cx - r // 2, cy - r // 4), r // 2 + 4)
        pygame.draw.circle(surf, cloud, (cx + r // 2, cy - r // 4), r // 2 + 4)
        pygame.draw.circle(surf, cloud, (cx, cy - r // 2), int(r * 0.7))
        # 闪电
        pts = [(cx - 7, cy + r // 4),
               (cx - 14, cy + r // 2),
               (cx - 2, cy + r // 2),
               (cx - 9, cy + r),
               (cx + 12, cy + r // 3),
               (cx + 3, cy + r // 3),
               (cx + 9, cy + r // 4)]
        pygame.draw.polygon(surf, (255, 225, 80), pts)
        pygame.draw.polygon(surf, (255, 180, 0), pts, 2)

    elif cls == 'fog':
        for i in range(5):
            yy = cy - r // 2 + i * (r // 3)
            pygame.draw.line(surf, (210, 210, 225),
                             (cx - r + 4, yy), (cx + r - 4, yy), 5)


# ============ UI 绘制辅助 ============
def lerp_color(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def draw_v_gradient(surf, top, bottom, rect=None):
    """在指定矩形内画纵向渐变（直接绘制到 surf）"""
    if rect is None:
        x, y, w, h = 0, 0, surf.get_width(), surf.get_height()
    else:
        x, y, w, h = rect
    for i in range(h):
        t = i / max(1, h - 1)
        c = lerp_color(top, bottom, t)
        pygame.draw.line(surf, c, (x, y + i), (x + w - 1, y + i))


def draw_gradient_panel(surf, top_color, bottom_color, rect, radius=20, border_color=None, alpha=255):
    """绘制带渐变背景的圆角面板（带 alpha 通道）"""
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    # 渐变填充
    for i in range(rect.h):
        t = i / max(1, rect.h - 1)
        c = lerp_color(top_color, bottom_color, t)
        a = int(alpha)
        pygame.draw.line(panel, (c[0], c[1], c[2], a), (0, i), (rect.w - 1, i))
    # 圆角 mask：先画一个圆角白色形状，再用它做 mask
    mask = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    panel.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if border_color:
        pygame.draw.rect(panel, border_color, panel.get_rect(), 2, border_radius=radius)
    surf.blit(panel, rect.topleft)


def draw_text(surface, text, font, color, pos, anchor="topleft"):
    surf = font.render(text, True, color)
    rect = surf.get_rect(**{anchor: pos})
    surface.blit(surf, rect)
    return rect


# ============ Button 类（参考仓库其他项目） ============
class Button:
    def __init__(self, rect, text, action, font,
                 color=BTN_NORMAL, hover_color=BTN_HOVER,
                 text_color=TEXT_COLOR, selected=False, border_color=ACCENT):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.selected = selected
        self.hovered = False
        self.enabled = True
        self.border_color = border_color

    def update(self, mouse_pos):
        self.hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        if not self.enabled:
            color = (80, 80, 80, 120)
        elif self.selected:
            color = BTN_SELECTED
            border_c = GOLD
        elif self.hovered:
            color = self.hover_color
            border_c = self.border_color
        else:
            color = self.color
            border_c = self.border_color

        btn_surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, color, btn_surf.get_rect(), border_radius=18)
        pygame.draw.rect(btn_surf, border_c, btn_surf.get_rect(), 2, border_radius=18)
        surface.blit(btn_surf, self.rect.topleft)

        text_surf = self.font.render(self.text, True,
                                     (40, 30, 0) if self.selected else self.text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def click(self, pos):
        if self.enabled and self.rect.collidepoint(pos):
            self.action()
            return True
        return False


# ============ 主程序 ============
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption('天气预报 - 好搭AI派')
    clock = pygame.time.Clock()

    font_name = find_chinese_font()
    font_title    = make_font(font_name, 72, bold=True)
    font_city     = make_font(font_name, 56, bold=True)
    font_temp     = make_font(font_name, 150, bold=True)
    font_desc     = make_font(font_name, 44, bold=True)
    font_norm     = make_font(font_name, 36, bold=True)
    font_small    = make_font(font_name, 28, bold=True)
    font_tiny     = make_font(font_name, 24, bold=True)
    font_btn      = make_font(font_name, 38, bold=True)
    font_exit     = make_font(font_name, 32, bold=True)

    # 状态
    state = {
        'city': None,
        'weather': None,
        'cls': 'clear-day',
        'loading': False,
        'error': None,
        'selected_idx': 0,
    }

    # 城市按钮（底部固定位置，确保不与上方内容重叠）
    btn_w, btn_h = 200, 70
    btn_gap = 22
    total_w = len(CITIES) * btn_w + (len(CITIES) - 1) * btn_gap
    btn_start_x = (WIDTH - total_w) // 2
    btn_y = 920                              # 按钮顶部 y，结束于 990
    city_buttons = []
    for i, c in enumerate(CITIES):
        x = btn_start_x + i * (btn_w + btn_gap)

        def make_action(idx):
            return lambda: load_city(idx)
        b = Button((x, btn_y, btn_w, btn_h), c['name'], make_action(i),
                   font_btn, color=BTN_NORMAL, hover_color=BTN_HOVER)
        b._idx = i
        city_buttons.append(b)

    # 退出按钮（右上角红色）
    exit_btn = Button((WIDTH - 220, 30, 180, 64), '退出程序', sys.exit,
                      font_exit, color=BTN_EXIT_NORMAL, hover_color=BTN_EXIT_HOVER,
                      text_color=WHITE, border_color=EXIT_RED)

    def load_city(idx):
        state['selected_idx'] = idx
        state['loading'] = True
        state['error'] = None
        state['city'] = None
        state['weather'] = None
        try:
            city = geocode(CITIES[idx]['q'])
            if not city:
                state['error'] = '未找到该城市'
                state['loading'] = False
                return
            w = get_weather(city['latitude'], city['longitude'])
            state['city'] = city
            state['weather'] = w
            is_day = w['current']['is_day'] == 1
            _, cls = code_info(w['current']['weather_code'], is_day)
            state['cls'] = cls
        except Exception as e:
            state['error'] = '获取失败：' + str(e)
        finally:
            state['loading'] = False

    # 启动时加载第一个城市
    load_city(0)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if exit_btn.click(ev.pos):
                    pass
                else:
                    for b in city_buttons:
                        if b.click(ev.pos):
                            break

        # ---- 1. 全屏背景渐变（随当前天气类型） ----
        top, bottom = SCREEN_THEMES[state['cls']]
        draw_v_gradient(screen, top, bottom)

        # 半透明深色遮罩，进一步提升文字对比度
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 80))
        screen.blit(overlay, (0, 0))

        # ---- 2. 顶部标题 ----
        draw_text(screen, '天 气 预 报', font_title, TEXT_COLOR,
                  (WIDTH // 2, 25), anchor='midtop')
        now = datetime.now()
        date_str = f'{now.year} 年 {now.month} 月 {now.day} 日  星期{"日一二三四五六"[now.weekday()]}'
        draw_text(screen, date_str, font_norm, (220, 230, 245),
                  (WIDTH // 2, 105), anchor='midtop')

        # ---- 3. 内容区 ----
        if state['loading']:
            draw_text(screen, '正在加载天气数据...', font_desc, TEXT_COLOR,
                      (WIDTH // 2, 460), anchor='center')

        elif state['error']:
            draw_text(screen, '✗ ' + state['error'], font_desc, (255, 120, 120),
                      (WIDTH // 2, 460), anchor='center')
            draw_text(screen, '请检查网络连接后重试', font_small, (255, 220, 220),
                      (WIDTH // 2, 530), anchor='center')

        elif state['weather']:
            w = state['weather']
            cur = w['current']
            is_day = cur['is_day'] == 1
            desc, cls = code_info(cur['weather_code'], is_day)
            card_top, card_bottom = CARD_THEMES[cls]

            # ===== 当前天气大卡（左侧，渐变背景随天气） =====
            card_rect = pygame.Rect(50, 160, 880, 430)
            # 文字颜色根据天气类型自动选择：雪/雾背景较亮时用深色文字
            light_card = cls in ('snow', 'fog', 'clear-day')
            main_text = (40, 40, 60) if light_card else WHITE
            sub_text  = (70, 70, 90) if light_card else (235, 240, 250)
            draw_gradient_panel(screen, card_top, card_bottom, card_rect,
                                radius=28, border_color=WHITE, alpha=240)

            # 城市名
            city_name = state['city']['name']
            draw_text(screen, '● ' + city_name, font_city, main_text, (90, 185))

            # 国家/省份
            admin = state['city'].get('admin1', '')
            country = state['city'].get('country', '')
            sub = ' · '.join([x for x in [admin, country] if x])
            draw_text(screen, sub, font_small, sub_text, (90, 255))

            # 大温度
            temp_str = f'{int(round(cur["temperature_2m"]))}°'
            draw_text(screen, temp_str, font_temp, main_text, (110, 305))
            draw_text(screen, 'C', font_desc, main_text,
                      (110 + font_temp.size(temp_str)[0] + 14, 355))

            # 天气描述 + 体感
            draw_text(screen, desc, font_desc, main_text, (110, 470))
            draw_text(screen, f'体感 {int(round(cur["apparent_temperature"]))}°C',
                      font_small, sub_text, (110, 530))

            # 天气大图标
            draw_icon(screen, cls, 720, 350, 220, is_day)

            # ===== 右侧详情卡片（深色半透明） =====
            metrics = [
                ('湿 度',   f"{cur['relative_humidity_2m']}%"),
                ('风 速',   f"{int(cur['wind_speed_10m'])} km/h"),
                ('风 向',   wind_dir(cur['wind_direction_10m'])),
                ('气 压',   f"{int(cur['pressure_msl'])} hPa"),
                ('日 出',   w['daily']['sunrise'][0][11:16]),
                ('日 落',   w['daily']['sunset'][0][11:16]),
            ]
            mx, my = 970, 160
            mw, mh = 220, 130
            mgap = 20
            for i, (k, v) in enumerate(metrics):
                col = i % 2
                row = i // 2
                rect = pygame.Rect(mx + col * (mw + mgap),
                                   my + row * (mh + mgap), mw, mh)
                # 深色半透明面板
                panel = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.rect(panel, (0, 0, 0, 160), panel.get_rect(),
                                 border_radius=18)
                pygame.draw.rect(panel, ACCENT, panel.get_rect(), 2,
                                 border_radius=18)
                screen.blit(panel, rect.topleft)
                draw_text(screen, k, font_tiny, ACCENT, (rect.x + 22, rect.y + 18))
                draw_text(screen, v, font_norm, WHITE, (rect.x + 22, rect.y + 65))

            # ===== 7天预报（每个卡片背景随该日天气类型渐变） =====
            daily_y = 615
            draw_text(screen, '未 来 7 天 预 报', font_desc, ACCENT,
                      (50, daily_y))

            daily = w['daily']
            day_w = 240
            day_gap = 16
            total_dw = 7 * day_w + 6 * day_gap
            day_start_x = (WIDTH - total_dw) // 2
            for i in range(7):
                dx = day_start_x + i * (day_w + day_gap)
                dy = daily_y + 65
                rect = pygame.Rect(dx, dy, day_w, 180)

                # 该日天气渐变背景
                di_desc, di_cls = code_info(daily['weather_code'][i], True)
                d_top, d_bottom = CARD_THEMES[di_cls]
                d_light = di_cls in ('snow', 'fog', 'clear-day')
                d_text = (40, 40, 60) if d_light else WHITE
                d_sub   = (70, 70, 90) if d_light else (240, 240, 250)
                draw_gradient_panel(screen, d_top, d_bottom, rect,
                                    radius=18, border_color=WHITE, alpha=235)

                # 日期标签
                if i == 0:
                    label = '今 天'
                elif i == 1:
                    label = '明 天'
                else:
                    d = datetime.fromisoformat(daily['time'][i])
                    label = f'{d.month}/{d.day}'
                draw_text(screen, label, font_small, d_sub,
                          (rect.centerx, rect.y + 12), anchor='midtop')

                # 图标
                draw_icon(screen, di_cls, rect.centerx, rect.y + 80, 56, True)

                # 高低温
                tmax = int(round(daily['temperature_2m_max'][i]))
                tmin = int(round(daily['temperature_2m_min'][i]))
                draw_text(screen, f'{tmax}°', font_norm, (255, 230, 130) if not d_light else (200, 60, 30),
                          (rect.centerx, rect.y + 120), anchor='midtop')
                draw_text(screen, f'{tmin}°', font_small, d_sub,
                          (rect.centerx, rect.y + 152), anchor='midtop')

        # ---- 4. 城市按钮栏 ----
        for i, b in enumerate(city_buttons):
            b.selected = (i == state['selected_idx'])
            b.update(mouse_pos)
            b.draw(screen)

        # ---- 5. 退出按钮 ----
        exit_btn.update(mouse_pos)
        exit_btn.draw(screen)

        # ---- 6. 底部提示 ----
        draw_text(screen, '点击下方城市按钮切换  ·  按 ESC 或点击右上角退出按钮关闭',
                  font_tiny, (220, 230, 245), (WIDTH // 2, 1020), anchor='center')

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == '__main__':
    main()
