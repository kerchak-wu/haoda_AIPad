# -*- coding: utf-8 -*-
"""
天气信息展示程序（好搭AI派）
- 窗口尺寸 1920 x 1080
- 在屏幕上选择不同城市，显示所选城市的实时天气信息
- 数据来源：Open-Meteo 免费天气 API（无需密钥）
- 界面：左侧城市选择卡片 + 中间主天气卡片（随天气变化的渐变天空、
        太阳/云/雨/雪等过程化动画） + 右侧指标详情 + 五日预报
- 右上角「退出程序」按钮，ESC 也可退出

布局（自左而右）：
  标题条 -> 左：城市列表 -> 中：主天气卡片 -> 右：指标 + 五日预报
"""

import os
import sys
import json
import math
import threading
import urllib.request
import urllib.parse
import time

import pygame

# ---------- 配置 ----------
WIDTH, HEIGHT = 1920, 1080
BG_IMAGE = os.path.join("images", "1.jpg")   # 可选背景，缺失则用渐变
TIMEOUT = 10                                 # 网络请求超时（秒）
AUTO_REFRESH_SEC = 600                       # 自动刷新间隔（秒）

# 城市列表：(显示名, 纬度, 经度, 时区)
CITIES = [
    ("北京",   39.9042, 116.4074, "Asia/Shanghai"),
    ("上海",   31.2304, 121.4737, "Asia/Shanghai"),
    ("广州",   23.1291, 113.2644, "Asia/Shanghai"),
    ("深圳",   22.5431, 114.0579, "Asia/Shanghai"),
    ("成都",   30.5728, 104.0668, "Asia/Shanghai"),
    ("杭州",   30.2741, 120.1551, "Asia/Shanghai"),
    ("西安",   34.3416, 108.9398, "Asia/Shanghai"),
    ("哈尔滨", 45.8038, 126.5350, "Asia/Shanghai"),
    ("拉萨",   29.6500,  91.1000, "Asia/Shanghai"),
    ("香港",   22.3193, 114.1694, "Asia/Hong_Kong"),
]

# ---------- 颜色 ----------
WHITE = (255, 255, 255)
TEXT_COLOR = (255, 255, 255)
SUB_TEXT = (220, 228, 236)
ACCENT = (86, 196, 255)           # 主强调色（蓝）
ACCENT_DARK = (40, 130, 190)
GOLD = (255, 210, 90)
WARN = (255, 170, 90)
ERR_RED = (255, 130, 130)

PANEL_COLOR = (0, 0, 0, 110)      # 半透明面板
BTN_NORMAL = (255, 255, 255, 40)
BTN_HOVER = (86, 196, 255, 150)
BTN_SELECTED = (86, 196, 255, 90)
BTN_EXIT_NORMAL = (180, 50, 50, 70)
BTN_EXIT_HOVER = (235, 87, 87, 160)
EXIT_RED = (235, 87, 87)


# ============================================================
# Open-Meteo 天气数据
# ============================================================
# WMO weather_code -> (中文描述, 图标类别)
WMO = {
    0:  ("晴",      "sun"),
    1:  ("大致晴",   "sun"),
    2:  ("局部多云", "partly"),
    3:  ("阴",      "cloud"),
    45: ("有雾",    "fog"),
    48: ("雾凇",    "fog"),
    51: ("毛毛雨",   "drizzle"),
    53: ("毛毛雨",   "drizzle"),
    55: ("毛毛雨",   "drizzle"),
    56: ("冻毛毛雨", "drizzle"),
    57: ("冻毛毛雨", "drizzle"),
    61: ("小雨",    "rain"),
    63: ("中雨",    "rain"),
    65: ("大雨",    "rain"),
    66: ("冻雨",    "rain"),
    67: ("冻雨",    "rain"),
    71: ("小雪",    "snow"),
    73: ("中雪",    "snow"),
    75: ("大雪",    "snow"),
    77: ("米雪",    "snow"),
    80: ("阵雨",    "rain"),
    81: ("阵雨",    "rain"),
    82: ("强阵雨",   "rain"),
    85: ("阵雪",    "snow"),
    86: ("强阵雪",   "snow"),
    95: ("雷暴",    "thunder"),
    96: ("雷暴伴冰雹", "thunder"),
    99: ("雷暴伴冰雹", "thunder"),
}


def weather_text(code):
    return WMO.get(code, ("未知", "sun"))[0]


def weather_icon(code):
    return WMO.get(code, ("未知", "sun"))[1]


def fetch_weather(lat, lon, tz, timeout=TIMEOUT):
    """请求 Open-Meteo 实时 + 五日预报。返回 dict 或抛异常。"""
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": ("temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "is_day,weather_code,wind_speed_10m,wind_direction_10m,"
                    "surface_pressure"),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": tz,
        "forecast_days": 5,
    })
    url = "https://api.open-meteo.com/v1/forecast?" + params
    req = urllib.request.Request(url, headers={"User-Agent": "HaodaAIPad-Weather/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data


def parse_weather(data):
    """把 API 返回整理成绘制所需的精简结构。"""
    cur = data.get("current", {})
    daily = data.get("daily", {})
    code = cur.get("weather_code", 0)
    is_day = cur.get("is_day", 1) == 1

    return {
        "city_time": cur.get("time", ""),
        "temp": round(cur.get("temperature_2m", 0)),
        "feels": round(cur.get("apparent_temperature", 0)),
        "humidity": round(cur.get("relative_humidity_2m", 0)),
        "wind_speed": round(cur.get("wind_speed_10m", 0)),
        "wind_deg": round(cur.get("wind_direction_10m", 0)),
        "pressure": round(cur.get("surface_pressure", 0)),
        "code": code,
        "text": weather_text(code),
        "icon": weather_icon(code),
        "is_day": is_day,
        "daily": list(zip(
            daily.get("time", []),
            [weather_text(c) for c in daily.get("weather_code", [])],
            [round(t) for t in daily.get("temperature_2m_max", [])],
            [round(t) for t in daily.get("temperature_2m_min", [])],
            [round(p) for p in daily.get("precipitation_probability_max", [])],
        )),
    }


def wind_dir_text(deg):
    """风向角度 -> 中文方位"""
    dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    return dirs[int(((deg + 22.5) % 360) // 45)]


# ============================================================
# 通用工具
# ============================================================
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
        "/home/cxdz/jupyter/assets/simhei.ttf",   # 好搭AI派设备字体
        "/home/cxdz/jupyter/assets/msyh.ttc",
        "/home/cxdz/jupyter/assets/simfang.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
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


def draw_text(surface, text, font, color, pos, anchor="topleft"):
    surf = font.render(text, True, color)
    rect = surf.get_rect(**{anchor: pos})
    surface.blit(surf, rect)
    return rect


def draw_text_outline(surface, text, font, color, pos, anchor="topleft", outline=(0, 0, 0)):
    """带描边的文字，保证在任意背景下清晰"""
    surf = font.render(text, True, color)
    shadow = font.render(text, True, outline)
    rect = surf.get_rect(**{anchor: pos})
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            surface.blit(shadow, (rect.x + dx, rect.y + dy))
    surface.blit(surf, rect)
    return rect


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)),
            int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def draw_round_rect(surface, color, rect, radius, width=0):
    rect = pygame.Rect(rect)   # 兼容 (x,y,w,h) 元组
    if len(color) == 4:
        # 带 alpha：画到临时 Surface 再 blit
        s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(s, color, s.get_rect(), width=width, border_radius=radius)
        surface.blit(s, rect.topleft)
    else:
        pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)


# ============================================================
# 按钮
# ============================================================
class Button:
    """通用按钮（可作城市卡片）"""

    def __init__(self, rect, text, action, font,
                 color=BTN_NORMAL, hover_color=BTN_HOVER,
                 selected_color=BTN_SELECTED, text_color=TEXT_COLOR,
                 sub_font=None, sub_text=""):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.font = font
        self.sub_font = sub_font
        self.sub_text = sub_text
        self.color = color
        self.hover_color = hover_color
        self.selected_color = selected_color
        self.text_color = text_color
        self.hovered = False
        self.selected = False
        self.enabled = True

    def update(self, mouse_pos):
        self.hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        if self.selected:
            color = self.selected_color
        elif self.hovered:
            color = self.hover_color
        else:
            color = self.color

        draw_round_rect(surface, color, self.rect, 18, width=0)
        border = GOLD if (self.selected or self.hovered) else (255, 255, 255, 55)
        draw_round_rect(surface, border, self.rect, 18, width=2)

        draw_text_outline(surface, self.text, self.font, self.text_color,
                          (self.rect.centerx, self.rect.centery), anchor="center")
        if self.sub_font and self.sub_text:
            draw_text(surface, self.sub_text, self.sub_font, SUB_TEXT,
                      (self.rect.centerx, self.rect.bottom - 22), anchor="midtop")

    def click(self, pos):
        if self.enabled and self.rect.collidepoint(pos):
            self.action()
            return True
        return False


# ============================================================
# 天气数据管理（后台线程拉取，避免阻塞主循环）
# ============================================================
class WeatherManager:
    """后台线程拉取天气，主线程只读缓存，保证界面始终流畅。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._weather = None          # 最新天气数据
        self._status = "idle"         # idle / loading / ok / error
        self._error = ""
        self._last_city = -1
        self._last_ok_tick = 0        # 上次成功时刻（pygame 毫秒）
        self._thread = None

    def request(self, city_index):
        """请求某个城市的天气（在后台线程执行）"""
        name, lat, lon, tz = CITIES[city_index]
        with self._lock:
            self._last_city = city_index
            self._status = "loading"
            self._error = ""
        # 启动后台线程（守护线程，随主进程退出）
        self._thread = threading.Thread(
            target=self._fetch, args=(city_index, lat, lon, tz), daemon=True)
        self._thread.start()

    def _fetch(self, city_index, lat, lon, tz):
        try:
            data = fetch_weather(lat, lon, tz)
            parsed = parse_weather(data)
            with self._lock:
                # 只在仍是最新的请求时才更新（避免旧请求覆盖新请求）
                if self._last_city == city_index:
                    self._weather = parsed
                    self._status = "ok"
                    self._last_ok_tick = pygame.time.get_ticks()
        except Exception as e:
            with self._lock:
                if self._last_city == city_index:
                    self._status = "error"
                    self._error = str(e)[:60]

    def snapshot(self):
        with self._lock:
            return {
                "weather": self._weather,
                "status": self._status,
                "error": self._error,
                "last_city": self._last_city,
                "last_ok_tick": self._last_ok_tick,
            }


# ============================================================
# 天气动画绘制（过程化，无需图片资源）
# ============================================================
class WeatherScene:
    """根据天气类型与昼夜，绘制动态天空背景与天气图标动画。"""

    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.t = 0
        # 雨滴/雪花粒子
        self._drops = []
        self._init_drops()

    def _init_drops(self):
        import random
        w, h = self.rect.width, self.rect.height
        self._drops = []
        for _ in range(140):
            self._drops.append({
                "x": random.uniform(0, w),
                "y": random.uniform(0, h),
                "len": random.uniform(12, 26),
                "speed": random.uniform(7, 14),
                "drift": random.uniform(-2, 2),
            })

    def sky_colors(self, icon, is_day):
        """返回 (顶端色, 底端色)，用于渐变天空"""
        if not is_day:
            return (20, 26, 56), (10, 14, 32)
        if icon == "sun":
            return (110, 180, 245), (190, 225, 250)
        if icon == "partly":
            return (120, 170, 215), (200, 215, 230)
        if icon in ("cloud", "fog"):
            return (130, 140, 155), (185, 190, 200)
        if icon in ("drizzle", "rain"):
            return (85, 100, 125), (135, 145, 165)
        if icon == "snow":
            return (150, 170, 200), (210, 220, 235)
        if icon == "thunder":
            return (70, 72, 95), (115, 118, 140)
        return (110, 180, 245), (190, 225, 250)

    def update(self):
        self.t += 1

    def draw(self, surface, icon, is_day):
        rect = self.rect
        # 渐变天空
        top, bottom = self.sky_colors(icon, is_day)
        bands = 40
        band_h = rect.height / bands
        for i in range(bands):
            c = lerp_color(top, bottom, i / (bands - 1))
            pygame.draw.rect(surface, c,
                             (rect.x, rect.y + int(i * band_h),
                              rect.width, int(band_h) + 1))

        # 按类型绘制天气元素
        if icon == "sun":
            self._draw_sun(surface, rect, is_day)
        if icon in ("sun", "partly"):
            self._draw_sun(surface, rect, is_day, small=(icon == "partly"))
        if icon in ("partly", "cloud", "fog", "rain", "drizzle", "thunder"):
            self._draw_clouds(surface, rect, is_day, dark=(icon in ("rain", "drizzle", "thunder")))
        if icon == "fog":
            self._draw_fog(surface, rect)
        if icon in ("rain", "drizzle"):
            self._draw_rain(surface, rect, light=(icon == "drizzle"))
        if icon == "snow":
            self._draw_snow(surface, rect)
        if icon == "thunder":
            self._draw_thunder(surface, rect)

    # ---- 太阳 ----
    def _draw_sun(self, surface, rect, is_day, small=False):
        import random
        random.seed(42)
        if small:
            cx, cy = rect.right - 150, rect.y + 110
            r = 55
        else:
            cx, cy = rect.centerx + 30, rect.y + 130
            r = 80
        color = (255, 220, 90) if is_day else (220, 225, 240)
        # 光芒
        rays = 12
        ang0 = self.t * 0.012
        for i in range(rays):
            a = ang0 + i * (2 * math.pi / rays)
            inner = r + 14
            outer = r + 42 + 10 * math.sin(self.t * 0.05 + i)
            x1, y1 = cx + math.cos(a) * inner, cy + math.sin(a) * inner
            x2, y2 = cx + math.cos(a) * outer, cy + math.sin(a) * outer
            pygame.draw.line(surface, color, (x1, y1), (x2, y2), 5)
        # 外发光
        glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        for gr, ga in [(r + 40, 30), (r + 26, 55), (r + 14, 90)]:
            pygame.draw.circle(glow, (*color, ga), (r * 2, r * 2), gr)
        surface.blit(glow, (cx - r * 2, cy - r * 2))
        pygame.draw.circle(surface, color, (cx, cy), r)
        pygame.draw.circle(surface, lerp_color(color, (255, 255, 255), 0.4),
                           (cx, cy), int(r * 0.7))

    # ---- 云 ----
    def _draw_clouds(self, surface, rect, is_day, dark=False):
        base = (245, 248, 252) if not dark else (90, 96, 112)
        shadow = (210, 214, 224) if not dark else (60, 66, 82)
        # 两朵云缓慢漂移
        w = rect.width
        for k, (y_off, scale, speed) in enumerate([(40, 1.1, 0.35),
                                                    (150, 0.8, 0.55)]):
            shift = (self.t * speed) % (w + 300) - 150
            cx = rect.x + int(shift) + 240
            cy = rect.y + 120 + y_off
            self._blob(surface, cx, cy, scale, base, shadow)

    def _blob(self, surface, cx, cy, scale, color, shadow_color):
        r = int(46 * scale)
        # 用多个圆组合成云朵形状
        offs = [(-r, 0), (-int(r * 0.4), -int(r * 0.5)), (int(r * 0.5), -int(r * 0.45)),
                (r, 0), (0, 0)]
        # 下沿阴影
        for dx, dy in offs:
            pygame.draw.circle(surface, shadow_color, (cx + dx, cy + dy + 6), r)
        for dx, dy in offs:
            pygame.draw.circle(surface, color, (cx + dx, cy + dy), r)

    # ---- 雾 ----
    def _draw_fog(self, surface, rect):
        for i in range(4):
            y = rect.y + 90 + i * 50
            alpha = 60
            band = pygame.Surface((rect.width, 40), pygame.SRCALPHA)
            shift = (self.t * (0.4 + i * 0.15)) % rect.width
            pygame.draw.ellipse(band, (235, 238, 244, alpha), band.get_rect())
            surface.blit(band, (rect.x + int(shift) - 100, y))
            surface.blit(band, (rect.x + int(shift) - 100 - rect.width, y))

    # ---- 雨 ----
    def _draw_rain(self, surface, rect, light=False):
        for d in self._drops:
            d["y"] += d["speed"]
            d["x"] += d["drift"]
            if d["y"] > rect.height:
                d["y"] = -d["len"]
                d["x"] = d["x"] % rect.width
            x = rect.x + d["x"]
            y = rect.y + d["y"]
            col = (190, 210, 235) if light else (170, 200, 230)
            pygame.draw.line(surface, col, (x, y), (x + d["drift"], y + d["len"]), 2)

    # ---- 雪 ----
    def _draw_snow(self, surface, rect):
        import random
        random.seed(7)
        for d in self._drops:
            d["y"] += d["speed"] * 0.45
            d["x"] += d["drift"] + math.sin(self.t * 0.04 + d["y"] * 0.05) * 0.6
            if d["y"] > rect.height:
                d["y"] = -d["len"]
            pygame.draw.circle(surface, (250, 252, 255),
                               (int(rect.x + d["x"] % rect.width),
                                int(rect.y + d["y"])), 3)

    # ---- 闪电 ----
    def _draw_thunder(self, surface, rect):
        # 约每 90 帧闪一次
        phase = self.t % 90
        if phase < 8:
            flash = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 80 if phase < 4 else 40))
            surface.blit(flash, rect.topleft)
        if 4 < phase < 16:
            cx = rect.centerx + 60
            cy = rect.y + 80
            pts = [(cx, cy), (cx - 18, cy + 60), (cx + 6, cy + 60),
                   (cx - 14, cy + 130), (cx + 16, cy + 60), (cx + 2, cy + 60)]
            pygame.draw.lines(surface, (255, 240, 120), False, pts, 5)


# ============================================================
# 主程序
# ============================================================
def main():
    pygame.init()
    try:
        pygame.mixer.init()
        audio_ok = True
    except pygame.error:
        audio_ok = False

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("天气信息")
    clock = pygame.time.Clock()

    # 字体
    font_name = find_chinese_font()
    font_title = make_font(font_name, 56, bold=True)
    font_city = make_font(font_name, 40, bold=True)
    font_city_sub = make_font(font_name, 24)
    font_temp = make_font(font_name, 130, bold=True)
    font_deg = make_font(font_name, 56, bold=True)
    font_cond = make_font(font_name, 48, bold=True)
    font_detail_label = make_font(font_name, 26)
    font_detail_value = make_font(font_name, 40, bold=True)
    font_daily = make_font(font_name, 30, bold=True)
    font_daily_small = make_font(font_name, 24)
    font_small = make_font(font_name, 26)
    font_status = make_font(font_name, 30)
    font_exit = make_font(font_name, 30, bold=True)

    # 可选背景图
    background = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print(f"背景加载失败: {e}")
            background = None

    # ---------- 布局 ----------
    title_h = 90
    left_x, left_y = 40, title_h + 30
    left_w = 360
    left_h = HEIGHT - left_y - 40
    city_btn_h = 84
    city_gap = 14
    # 列表可滚动
    city_scroll = 0
    city_max_visible = (left_h - 60) // (city_btn_h + city_gap)  # 预留刷新按钮空间

    mid_x = left_x + left_w + 30
    mid_w = 820
    mid_y = left_y
    mid_h = left_h

    right_x = mid_x + mid_w + 30
    right_w = WIDTH - right_x - 40
    right_y = left_y
    right_h = left_h

    # 天气动画场景（位于主卡片内）
    scene_rect = (mid_x + 20, mid_y + 20, mid_w - 40, 360)
    scene = WeatherScene(scene_rect)

    # 城市按钮 + 退出 / 刷新按钮
    mgr = WeatherManager()
    current_city = 0

    def select_city(idx):
        nonlocal current_city
        current_city = idx
        mgr.request(idx)
        for i, b in enumerate(city_buttons):
            b.selected = (i == idx)

    city_buttons = []
    for i, (name, lat, lon, _tz) in enumerate(CITIES):
        b = Button(
            (left_x, left_y + i * (city_btn_h + city_gap), left_w, city_btn_h),
            name,
            lambda idx=i: select_city(idx),
            font_city,
            sub_font=font_city_sub,
            sub_text=f"{lat:.2f}, {lon:.2f}",
        )
        city_buttons.append(b)

    def manual_refresh():
        mgr.request(current_city)

    refresh_btn = Button(
        (left_x, HEIGHT - 60 - 40, left_w, 60), "刷新当前城市", manual_refresh, font_status,
        color=BTN_NORMAL, hover_color=BTN_HOVER, text_color=WHITE,
    )

    exit_btn = Button(
        (WIDTH - 200, 25, 160, 56), "退出程序", sys.exit, font_exit,
        color=BTN_EXIT_NORMAL, hover_color=BTN_EXIT_HOVER, text_color=WHITE,
    )

    # 首次请求
    select_city(0)

    # ---------- 主循环 ----------
    running = True
    last_auto_refresh = pygame.time.get_ticks()
    while running:
        mouse_pos = pygame.mouse.get_pos()
        snap = mgr.snapshot()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_UP:
                    city_scroll = max(0, city_scroll - 1)
                elif event.key == pygame.K_DOWN:
                    max_scroll = max(0, len(CITIES) - city_max_visible)
                    city_scroll = min(max_scroll, city_scroll + 1)
                elif event.key == pygame.K_r:
                    manual_refresh()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # 城市列表滚轮区点击
                list_rect = pygame.Rect(left_x, left_y, left_w,
                                        city_max_visible * (city_btn_h + city_gap))
                if list_rect.collidepoint(event.pos):
                    rel_y = event.pos[1] - left_y
                    idx = city_scroll + rel_y // (city_btn_h + city_gap)
                    if 0 <= idx < len(CITIES):
                        select_city(idx)
                elif refresh_btn.click(event.pos):
                    pass
                else:
                    exit_btn.click(event.pos)
            elif event.type == pygame.MOUSEWHEEL:
                if pygame.Rect(left_x, left_y, left_w, left_h).collidepoint(mouse_pos):
                    max_scroll = max(0, len(CITIES) - city_max_visible)
                    if event.y > 0:
                        city_scroll = max(0, city_scroll - 1)
                    elif event.y < 0:
                        city_scroll = min(max_scroll, city_scroll + 1)

        # 自动刷新
        now = pygame.time.get_ticks()
        if (snap["status"] in ("ok", "error") and
                now - last_auto_refresh > AUTO_REFRESH_SEC * 1000):
            last_auto_refresh = now
            manual_refresh()

        # ================= 绘制 =================
        # 背景
        if background:
            screen.blit(background, (0, 0))
        else:
            screen.fill((18, 24, 38))
        # 整体半透明遮罩，提升可读性
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))

        # 标题条
        title_bar = pygame.Surface((WIDTH, title_h), pygame.SRCALPHA)
        title_bar.fill((0, 0, 0, 150))
        screen.blit(title_bar, (0, 0))
        draw_text_outline(screen, "☀ 天气信息", font_title, WHITE, (40, 45), anchor="midleft")
        draw_text(screen, "实时天气 · 数据来源 Open-Meteo", font_small, SUB_TEXT,
                  (WIDTH - 240, 45), anchor="midright")

        # ---- 左：城市列表面板 ----
        draw_round_rect(screen, PANEL_COLOR, (left_x, left_y, left_w, left_h), 20, width=0)
        draw_round_rect(screen, (255, 255, 255, 45), (left_x, left_y, left_w, left_h), 20, width=2)
        draw_text_outline(screen, "选择城市", font_city, ACCENT,
                          (left_x + 24, left_y + 14), anchor="topleft")

        # 裁剪城市列表区域，超出部分不绘制
        prev_clip = screen.get_clip()
        list_clip = pygame.Rect(left_x, left_y + 60, left_w,
                                city_max_visible * (city_btn_h + city_gap))
        screen.set_clip(list_clip)
        for i in range(len(CITIES)):
            b = city_buttons[i]
            # 临时移动按钮位置以实现滚动
            orig_y = b.rect.y
            b.rect.y = left_y + (i - city_scroll) * (city_btn_h + city_gap)
            b.update(mouse_pos)
            if b.rect.bottom >= left_y + 60 and b.rect.y < list_clip.bottom:
                b.draw(screen)
            b.rect.y = orig_y
        screen.set_clip(prev_clip)

        # 滚动条提示
        max_scroll = max(0, len(CITIES) - city_max_visible)
        if max_scroll > 0:
            track_x = left_x + left_w - 12
            track_y = left_y + 60
            track_h = city_max_visible * (city_btn_h + city_gap)
            pygame.draw.rect(screen, (255, 255, 255, 40),
                             (track_x, track_y, 6, track_h), border_radius=3)
            thumb_h = max(30, track_h * city_max_visible / len(CITIES))
            thumb_y = track_y + (track_h - thumb_h) * (city_scroll / max_scroll)
            pygame.draw.rect(screen, ACCENT,
                             (track_x, int(thumb_y), 6, int(thumb_h)), border_radius=3)

        # 刷新按钮
        if snap["status"] == "loading":
            refresh_btn.text = "刷新中..."
        else:
            refresh_btn.text = "刷新当前城市"
        refresh_btn.update(mouse_pos)
        refresh_btn.draw(screen)

        # ---- 中：主天气卡片 ----
        draw_round_rect(screen, PANEL_COLOR, (mid_x, mid_y, mid_w, mid_h), 24, width=0)
        draw_round_rect(screen, (255, 255, 255, 45), (mid_x, mid_y, mid_w, mid_h), 24, width=2)

        w = snap["weather"]
        if snap["status"] == "loading" and w is None:
            # 首次加载：转圈动画
            draw_text(screen, "正在获取天气数据...", font_status, WARN,
                      (mid_x + mid_w // 2, mid_y + mid_h // 2), anchor="center")
            cx, cy = mid_x + mid_w // 2, mid_y + mid_h // 2 + 70
            ang = -pygame.time.get_ticks() * 0.01
            for i in range(10):
                a = ang + i * (2 * math.pi / 10)
                alpha = int(255 * (i / 10))
                col = (86, 196, 255)
                px = cx + math.cos(a) * 26
                py = cy + math.sin(a) * 26
                pygame.draw.circle(screen, col, (int(px), int(py)), 6)
        elif snap["status"] == "error" and w is None:
            draw_text(screen, "获取天气失败", font_cond, ERR_RED,
                      (mid_x + mid_w // 2, mid_y + 200), anchor="center")
            draw_text(screen, snap["error"] or "请检查网络连接", font_status, SUB_TEXT,
                      (mid_x + mid_w // 2, mid_y + 280), anchor="center")
            draw_text(screen, "点击「刷新当前城市」重试", font_small, ACCENT,
                      (mid_x + mid_w // 2, mid_y + 330), anchor="center")
        elif w is not None:
            # 天气动画场景（白天/夜晚 + 天气类型决定颜色）
            scene.update()
            scene.draw(screen, w["icon"], w["is_day"])

            # 动画底部渐隐过渡到面板
            fade = pygame.Surface((mid_w - 40, 60), pygame.SRCALPHA)
            for fy in range(60):
                a = int(255 * (fy / 60) * 0.85)
                pygame.draw.line(fade, (0, 0, 0, a), (0, fy), (mid_w - 40, fy))
            screen.blit(fade, (mid_x + 20, mid_y + 20 + 300))

            # 城市名 + 本地时间
            draw_text_outline(screen, CITIES[current_city][0], font_title, WHITE,
                              (mid_x + 30, mid_y + 30), anchor="topleft")
            local_time = (w["city_time"] or "").replace("T", " ")
            if local_time:
                draw_text(screen, f"当地时间 {local_time}", font_small, SUB_TEXT,
                          (mid_x + 30, mid_y + 96), anchor="topleft")

            # 天气描述
            draw_text_outline(screen, w["text"], font_cond, WHITE,
                              (mid_x + 30, mid_y + 150), anchor="topleft")

            # 大温度
            temp_y = mid_y + 430
            temp_str = str(w["temp"])
            ts = font_temp.render(temp_str, True, WHITE)
            deg = font_deg.render("°C", True, WHITE)
            tx = mid_x + 40
            screen.blit(ts, (tx, temp_y))
            screen.blit(deg, (tx + ts.get_width() + 6, temp_y + 18))
            draw_text(screen, f"体感 {w['feels']}°C", font_status, SUB_TEXT,
                      (tx, temp_y + 150), anchor="topleft")

        # ---- 右：详情指标 + 五日预报 ----
        draw_round_rect(screen, PANEL_COLOR, (right_x, right_y, right_w, right_h), 24, width=0)
        draw_round_rect(screen, (255, 255, 255, 45), (right_x, right_y, right_w, right_h), 24, width=2)

        draw_text_outline(screen, "天气详情", font_city, ACCENT,
                          (right_x + 24, right_y + 14), anchor="topleft")

        if w is not None:
            # 指标网格（2 列）
            metrics = [
                ("湿度",     f"{w['humidity']}%"),
                ("风速",     f"{w['wind_speed']} km/h"),
                ("风向",     wind_dir_text(w["wind_deg"])),
                ("气压",     f"{w['pressure']} hPa"),
            ]
            grid_top = right_y + 80
            cell_w = (right_w - 48 - 20) // 2
            cell_h = 100
            for i, (label, value) in enumerate(metrics):
                col = i % 2
                row = i // 2
                cx = right_x + 24 + col * (cell_w + 20)
                cy = grid_top + row * (cell_h + 20)
                draw_round_rect(screen, (255, 255, 255, 25),
                                (cx, cy, cell_w, cell_h), 16, width=0)
                draw_text(screen, label, font_detail_label, SUB_TEXT,
                          (cx + 18, cy + 14), anchor="topleft")
                draw_text_outline(screen, value, font_detail_value, WHITE,
                                  (cx + 18, cy + 48), anchor="topleft")

            # 五日预报
            fc_top = grid_top + 2 * (cell_h + 20) + 20
            draw_text_outline(screen, "未来五日预报", font_daily_small, ACCENT,
                              (right_x + 24, fc_top), anchor="topleft")
            fc_y = fc_top + 40
            row_h = (right_y + right_h - 30 - fc_y) // max(1, len(w["daily"]))
            for i, (date, txt, tmax, tmin, pop) in enumerate(w["daily"]):
                ry = fc_y + i * row_h
                if ry + row_h > right_y + right_h - 10:
                    break
                # 日期（取 月-日）
                md = date[5:] if len(date) >= 10 else date
                draw_text(screen, md, font_daily_small, WHITE,
                          (right_x + 24, ry + row_h // 2), anchor="midleft")
                draw_text(screen, txt, font_daily_small, SUB_TEXT,
                          (right_x + 140, ry + row_h // 2), anchor="midleft")
                # 降水概率
                draw_text(screen, f"💧{pop}%", font_daily_small, ACCENT,
                          (right_x + 280, ry + row_h // 2), anchor="midleft")
                # 温度：低（冷色）— 高（暖色）
                low_s = font_daily_small.render(f"{tmin}°", True, (150, 200, 255))
                high_s = font_daily_small.render(f"{tmax}°", True, (255, 200, 120))
                screen.blit(high_s, (right_x + right_w - 24 - low_s.get_width() - 12 - high_s.get_width(),
                                     ry + row_h // 2 - high_s.get_height() // 2))
                screen.blit(low_s, (right_x + right_w - 24 - low_s.get_width(),
                                    ry + row_h // 2 - low_s.get_height() // 2))
                # 分隔线
                if i < len(w["daily"]) - 1:
                    pygame.draw.line(screen, (255, 255, 255, 30),
                                     (right_x + 24, ry + row_h - 1),
                                     (right_x + right_w - 24, ry + row_h - 1), 1)
        else:
            draw_text(screen, "等待天气数据...", font_status, SUB_TEXT,
                      (right_x + right_w // 2, right_y + right_h // 2), anchor="center")

        # 退出按钮
        exit_btn.update(mouse_pos)
        exit_btn.draw(screen)

        # 底部提示
        hint = "提示：点击左侧城市切换 | ↑↓ 或滚轮滚动列表 | R 刷新 | ESC 退出"
        draw_text(screen, hint, font_small, (190, 200, 215),
                  (WIDTH // 2, HEIGHT - 18), anchor="center")

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
