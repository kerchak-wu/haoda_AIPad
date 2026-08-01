# -*- coding: utf-8 -*-
"""
城市实时天气与未来预报展示程序 - 好搭AI派
- 使用 Open-Meteo 免费 API (无需注册和 API Key)
- 固定窗口 1920×1080
- 在 images/1.jpg 背景图上叠加天气滤镜和粒子特效
- 展示国内主要城市的实时天气、详细数据及未来5日预报
"""

import os
import sys
import math
import random
import threading
import urllib.request
import json
import pygame
from datetime import datetime

# ---------- 配置 ----------
WIDTH, HEIGHT = 1920, 1080
BG_IMAGE = os.path.join("images", "1.jpg")

# 颜色
WHITE = (255, 255, 255)
ACCENT = (86, 196, 255)
GOLD = (255, 210, 90)
TEMP_HOT = (255, 120, 80)
TEMP_COLD = (120, 180, 255)

# 天气类型
WEATHER_SUNNY = "晴"
WEATHER_CLOUDY = "多云"
WEATHER_OVERCAST = "阴"
WEATHER_LIGHT_RAIN = "小雨"
WEATHER_HEAVY_RAIN = "大雨"
WEATHER_THUNDER = "雷阵雨"
WEATHER_LIGHT_SNOW = "小雪"
WEATHER_HEAVY_SNOW = "大雪"
WEATHER_FOG = "雾"

# 各天气对应的渐变背景色（顶部, 底部）
WEATHER_COLORS = {
    WEATHER_SUNNY:       ((255, 160, 70),  (255, 215, 130)),
    WEATHER_CLOUDY:      ((110, 145, 195), (175, 200, 230)),
    WEATHER_OVERCAST:    ((85, 95, 115),   (135, 145, 165)),
    WEATHER_LIGHT_RAIN:  ((65, 95, 145),   (105, 135, 175)),
    WEATHER_HEAVY_RAIN:  ((45, 65, 105),   (85, 105, 145)),
    WEATHER_THUNDER:     ((55, 55, 85),    (95, 95, 135)),
    WEATHER_LIGHT_SNOW:  ((175, 195, 225), (215, 225, 240)),
    WEATHER_HEAVY_SNOW:  ((145, 165, 205), (195, 210, 235)),
    WEATHER_FOG:         ((155, 155, 165), (195, 195, 205)),
}

# 主要城市配置（名称, 纬度, 经度）- Open-Meteo 基于经纬度查询
CITIES_CONFIG = [
    {"name": "北京",     "lat": 39.90, "lon": 116.40},
    {"name": "上海",     "lat": 31.23, "lon": 121.47},
    {"name": "广州",     "lat": 23.13, "lon": 113.26},
    {"name": "深圳",     "lat": 22.54, "lon": 114.06},
    {"name": "杭州",     "lat": 30.27, "lon": 120.15},
    {"name": "成都",     "lat": 30.57, "lon": 104.07},
    {"name": "武汉",     "lat": 30.59, "lon": 114.31},
    {"name": "西安",     "lat": 34.27, "lon": 108.95},
    {"name": "哈尔滨",   "lat": 45.80, "lon": 126.53},
    {"name": "三亚",     "lat": 18.25, "lon": 109.51},
    {"name": "拉萨",     "lat": 29.65, "lon": 91.13},
    {"name": "乌鲁木齐", "lat": 43.83, "lon": 87.62},
]

CITIES_DATA = {}  # 动态获取的数据缓存

# ============================================================
# 天气 API 获取与解析
# ============================================================
def kmh_to_beaufort_str(speed):
    try:
        speed = float(speed)
    except:
        return "微风"
    if speed < 1: return "微风"
    elif speed < 6: return "1级"
    elif speed < 12: return "2级"
    elif speed < 20: return "3级"
    elif speed < 29: return "4级"
    elif speed < 39: return "5级"
    elif speed < 50: return "6级"
    elif speed < 62: return "7级"
    elif speed < 75: return "8级"
    else: return "9级以上"

def parse_wind_direction(deg):
    try:
        deg = float(deg)
    except:
        deg = 0
    dirs = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
    idx = int(((deg + 22.5) % 360) // 45)
    return dirs[idx]

def parse_weather_code(code):
    try:
        code = int(code)
    except:
        return WEATHER_OVERCAST
    if code == 0: return WEATHER_SUNNY
    elif code in (1, 2): return WEATHER_CLOUDY
    elif code == 3: return WEATHER_OVERCAST
    elif code in (45, 48): return WEATHER_FOG
    elif code in (51, 53, 55, 56, 57): return WEATHER_LIGHT_RAIN
    elif code in (61, 63, 65, 66, 67, 80, 81): return WEATHER_HEAVY_RAIN
    elif code in (82, 95, 96, 99): return WEATHER_THUNDER
    elif code in (71, 73, 75, 77): return WEATHER_LIGHT_SNOW
    elif code in (85, 86): return WEATHER_HEAVY_SNOW
    return WEATHER_CLOUDY

def fetch_data(city):
    lat = city["lat"]
    lon = city["lon"]
    try:
        # 1. 获取天气基础数据
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&hourly=relative_humidity_2m,pressure_msl,visibility,apparent_temperature,uv_index"
            f"&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset"
            f"&timezone=Asia%2FShanghai"
        )
        req = urllib.request.Request(weather_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        # 2. 获取空气质量数据
        aqi_url = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}"
            f"&current=us_aqi&timezone=Asia%2FShanghai"
        )
        req2 = urllib.request.Request(aqi_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            aqi_data = json.loads(resp2.read().decode('utf-8'))

        current = data.get("current_weather", {})
        hourly = data.get("hourly", {})
        daily = data.get("daily", {})
        
        temp = current.get("temperature", 0)
        wspeed = current.get("windspeed", 0)
        wdir = current.get("winddirection", 0)
        wcode = current.get("weathercode", 3)
        
        now_str = current.get("time", "")
        time_list = hourly.get("time", [])
        idx = time_list.index(now_str) if now_str in time_list else 0
        
        humidity = hourly.get("relative_humidity_2m", [0])[idx]
        pressure = hourly.get("pressure_msl", [0])[idx]
        visibility = hourly.get("visibility", [10000])[idx] / 1000.0 
        feel_temp = hourly.get("apparent_temperature", [0])[idx]
        uv_index = hourly.get("uv_index", [0])[idx]
        
        high = daily.get("temperature_2m_max", [0])[0]
        low = daily.get("temperature_2m_min", [0])[0]
        sunrise = daily.get("sunrise", [""])[0][-5:] 
        sunset = daily.get("sunset", [""])[0][-5:]   
        us_aqi = aqi_data.get("current", {}).get("us_aqi", 50)
        
        weather_type = parse_weather_code(wcode)
        wind_dir_str = parse_wind_direction(wdir)
        wind_scale_str = kmh_to_beaufort_str(wspeed)
        wind_str = f"{wind_dir_str}风 {wind_scale_str}" if wind_scale_str != "微风" else "微风"
        
        uv_str = "弱"
        try:
            uv_idx_f = float(uv_index)
            if uv_idx_f >= 8: uv_str = "极强"
            elif uv_idx_f >= 6: uv_str = "强"
            elif uv_idx_f >= 3: uv_str = "中"
        except:
            pass
        
        q_str = "优"
        try:
            aqi_f = float(us_aqi)
            if aqi_f > 150: q_str = "中度污染"
            elif aqi_f > 100: q_str = "轻度污染"
            elif aqi_f > 50: q_str = "良"
        except:
            pass
            
        # 提取未来5天预报
        forecast_list = []
        d_time = daily.get("time", [])
        d_code = daily.get("weathercode", [])
        d_max = daily.get("temperature_2m_max", [])
        d_min = daily.get("temperature_2m_min", [])
        
        for i in range(min(5, len(d_time))):
            dt = datetime.strptime(d_time[i], "%Y-%m-%d")
            week = ["周一","周二","周三","周四","周五","周六","周日"][dt.weekday()]
            forecast_list.append({
                "date": f"{dt.month}/{dt.day}",
                "week": "今日" if i == 0 else ("明日" if i == 1 else week),
                "weather": parse_weather_code(d_code[i] if i < len(d_code) else 3),
                "high": round(d_max[i] if i < len(d_max) else 0),
                "low": round(d_min[i] if i < len(d_min) else 0),
            })
            
        return {
            "name": city["name"],
            "temp": round(temp),
            "weather": weather_type,
            "humidity": round(humidity),
            "wind": wind_str,
            "aqi": int(us_aqi) if us_aqi else 50,
            "quality": q_str,
            "feel": round(feel_temp),
            "visibility": round(visibility, 1),
            "pressure": round(pressure),
            "uv": uv_str,
            "sunrise": sunrise,
            "sunset": sunset,
            "high": round(high),
            "low": round(low),
            "forecast": forecast_list,
            "status": "ok"
        }
    except Exception as e:
        print(f"获取天气失败 ({city.get('name')}):", e)
        return {
            "name": city.get("name"),
            "status": "error",
            "error_msg": str(e)
        }

def fetch_and_update(city):
    data = fetch_data(city)
    CITIES_DATA[city["name"]] = data


# ============================================================
# 工具函数与绘制
# ============================================================
def find_chinese_font():
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
        "/home/cxdz/jupyter/assets/simhei.ttf",
        "/home/cxdz/jupyter/assets/msyh.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def make_font(font_name, size, bold=False):
    if font_name and (font_name.startswith("/") or "\\" in font_name
                      or (len(font_name) > 2 and font_name[1] == ":")):
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

def draw_text(surface, text, font, color, pos, anchor="topleft", shadow=True):
    surf = font.render(text, True, color)
    rect = surf.get_rect(**{anchor: pos})
    if shadow:
        shadow_surf = font.render(text, True, (0, 0, 0))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            surface.blit(shadow_surf, (rect.x + dx, rect.y + dy))
    surface.blit(surf, rect)
    return rect

def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

# 天气图标绘制
def draw_sunny_icon(surface, center, radius, color=(255, 220, 100)):
    cx, cy = center
    for i in range(12):
        angle = i * math.pi / 6
        x1 = cx + math.cos(angle) * (radius + 8)
        y1 = cy + math.sin(angle) * (radius + 8)
        x2 = cx + math.cos(angle) * (radius + 20)
        y2 = cy + math.sin(angle) * (radius + 20)
        pygame.draw.line(surface, color, (x1, y1), (x2, y2), 3)
    pygame.draw.circle(surface, color, center, radius)
    pygame.draw.circle(surface, (255, 250, 200), center, radius - 4)
    pygame.draw.circle(surface, (255, 180, 50), center, radius, 2)

def draw_cloud_icon(surface, center, size, color=(240, 240, 250), outline=(180, 180, 200)):
    cx, cy = center
    r = size // 2
    pygame.draw.circle(surface, color, (cx - r, cy + 5), r - 5)
    pygame.draw.circle(surface, color, (cx + r, cy + 5), r - 5)
    pygame.draw.circle(surface, color, (cx, cy - 10), r)
    pygame.draw.rect(surface, color, (cx - r - 5, cy - 5, (r + 5) * 2, r + 10))
    pygame.draw.circle(surface, outline, (cx - r, cy + 5), r - 5, 2)
    pygame.draw.circle(surface, outline, (cx + r, cy + 5), r - 5, 2)
    pygame.draw.circle(surface, outline, (cx, cy - 10), r, 2)
    pygame.draw.rect(surface, outline, (cx - r - 5, cy - 5, (r + 5) * 2, r + 10), 2)

def draw_rain_icon(surface, center, size, color=(120, 180, 240)):
    cx, cy = center
    draw_cloud_icon(surface, (cx, cy - 25), size, (200, 210, 230), (140, 150, 180))
    for i in range(4):
        x = cx - size + i * size // 2
        for j in range(2):
            y_start = cy + 5 + j * 18
            pygame.draw.line(surface, color, (x, y_start), (x - 5, y_start + 12), 3)

def draw_snow_icon(surface, center, size, color=(240, 250, 255)):
    cx, cy = center
    draw_cloud_icon(surface, (cx, cy - 25), size, (220, 230, 245), (160, 175, 200))
    for i in range(4):
        x = cx - size + i * size // 2
        for j in range(2):
            y = cy + 12 + j * 18
            pygame.draw.circle(surface, color, (x, y), 4)

def draw_thunder_icon(surface, center, size):
    cx, cy = center
    draw_cloud_icon(surface, (cx, cy - 25), size, (110, 110, 140), (70, 70, 100))
    pts = [(cx-5, cy+5), (cx+12, cy+5), (cx, cy+22), (cx+10, cy+22), (cx-5, cy+38), (cx+3, cy+28), (cx-8, cy+28)]
    pygame.draw.polygon(surface, (255, 230, 80), pts)
    pygame.draw.polygon(surface, (200, 170, 0), pts, 2)

def draw_fog_icon(surface, center, size, color=(220, 220, 235)):
    cx, cy = center
    for i in range(3):
        y = cy - 20 + i * 18
        offset = (i % 2) * 15
        pygame.draw.line(surface, color, (cx - size + offset, y), (cx + size - offset, y), 8)

def draw_weather_icon(surface, weather, center, size=80):
    if weather == WEATHER_SUNNY:
        draw_sunny_icon(surface, center, size)
    elif weather == WEATHER_CLOUDY:
        draw_cloud_icon(surface, center, size, (245, 245, 255), (190, 195, 210))
    elif weather == WEATHER_OVERCAST:
        draw_cloud_icon(surface, center, size, (180, 185, 200), (120, 125, 140))
    elif weather in (WEATHER_LIGHT_RAIN, WEATHER_HEAVY_RAIN):
        draw_rain_icon(surface, center, size)
    elif weather == WEATHER_THUNDER:
        draw_thunder_icon(surface, center, size)
    elif weather in (WEATHER_LIGHT_SNOW, WEATHER_HEAVY_SNOW):
        draw_snow_icon(surface, center, size)
    elif weather == WEATHER_FOG:
        draw_fog_icon(surface, center, size)


# ============================================================
# UI 组件
# ============================================================
class CityButton:
    def __init__(self, rect, name, font, idx):
        self.rect = pygame.Rect(rect)
        self.name = name
        self.font = font
        self.idx = idx
        self.hovered = False
        self.selected = False

    def update(self, mouse_pos, selected_idx):
        self.hovered = self.rect.collidepoint(mouse_pos)
        self.selected = (self.idx == selected_idx)

    def draw(self, surface):
        if self.selected:
            color, border = (86, 196, 255, 200), GOLD
        elif self.hovered:
            color, border = (255, 255, 255, 80), (255, 255, 255, 180)
        else:
            color, border = (0, 0, 0, 90), (255, 255, 255, 60)
        btn_surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, color, btn_surf.get_rect(), border_radius=14)
        pygame.draw.rect(btn_surf, border, btn_surf.get_rect(), 2, border_radius=14)
        surface.blit(btn_surf, self.rect.topleft)
        text_surf = self.font.render(self.name, True, WHITE)
        shadow_surf = self.font.render(self.name, True, (0, 0, 0))
        text_rect = text_surf.get_rect(center=self.rect.center)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            surface.blit(shadow_surf, (text_rect.x + dx, text_rect.y + dy))
        surface.blit(text_surf, text_rect)

    def is_clicked(self, pos):
        return self.rect.collidepoint(pos)

class Button:
    def __init__(self, rect, text, action, font, color=(235, 87, 87, 120), hover_color=(235, 87, 87, 220)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.hovered = False

    def update(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        color = self.hover_color if self.hovered else self.color
        btn_surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, color, btn_surf.get_rect(), border_radius=12)
        pygame.draw.rect(btn_surf, ACCENT, btn_surf.get_rect(), 2, border_radius=12)
        surface.blit(btn_surf, self.rect.topleft)
        text_surf = self.font.render(self.text, True, WHITE)
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))

    def click(self, pos):
        if self.rect.collidepoint(pos):
            self.action()
            return True
        return False

class ParticleSystem:
    def __init__(self):
        self.particles = []
        self.weather = None

    def init(self, weather):
        if self.weather == weather: return
        self.weather = weather
        self.particles = []
        if weather in (WEATHER_LIGHT_RAIN, WEATHER_HEAVY_RAIN, WEATHER_THUNDER):
            count = 150 if weather == WEATHER_LIGHT_RAIN else 280
            for _ in range(count):
                self.particles.append({"x": random.uniform(0, WIDTH), "y": random.uniform(0, HEIGHT), "vy": random.randint(9, 14), "vx": -2, "len": random.randint(15, 25), "type": "rain"})
        elif weather in (WEATHER_LIGHT_SNOW, WEATHER_HEAVY_SNOW):
            count = 80 if weather == WEATHER_LIGHT_SNOW else 150
            for _ in range(count):
                self.particles.append({"x": random.uniform(0, WIDTH), "y": random.uniform(0, HEIGHT), "vy": random.uniform(1, 2.5), "vx": random.uniform(-0.5, 0.5), "size": random.randint(3, 6), "phase": random.uniform(0, math.pi * 2), "type": "snow"})
        elif weather == WEATHER_FOG:
            for _ in range(25):
                self.particles.append({"x": random.uniform(0, WIDTH), "y": random.uniform(0, HEIGHT), "r": random.randint(80, 160), "alpha": random.randint(20, 50), "vx": random.uniform(-0.4, 0.4), "type": "fog"})

    def update_and_draw(self, surface):
        for p in self.particles:
            if p["type"] == "rain":
                p["x"] += p["vx"]; p["y"] += p["vy"]
                if p["y"] > HEIGHT:
                    p["y"] = -p["len"]; p["x"] = random.uniform(0, WIDTH)
                pygame.draw.line(surface, (180, 200, 230), (p["x"], p["y"]), (p["x"] + p["vx"] * 2, p["y"] + p["len"]), 2)
            elif p["type"] == "snow":
                p["phase"] += 0.05; p["x"] += p["vx"] + math.sin(p["phase"]) * 0.6; p["y"] += p["vy"]
                if p["y"] > HEIGHT:
                    p["y"] = -10; p["x"] = random.uniform(0, WIDTH)
                pygame.draw.circle(surface, (255, 255, 255), (int(p["x"]), int(p["y"])), p["size"])
            elif p["type"] == "fog":
                p["x"] += p["vx"]
                if p["x"] < -p["r"]: p["x"] = WIDTH + p["r"]
                if p["x"] > WIDTH + p["r"]: p["x"] = -p["r"]
                fog_surf = pygame.Surface((p["r"] * 2, p["r"] * 2), pygame.SRCALPHA)
                pygame.draw.circle(fog_surf, (230, 235, 245, p["alpha"]), (p["r"], p["r"]), p["r"])
                surface.blit(fog_surf, (p["x"] - p["r"], p["y"] - p["r"]))


# ============================================================
# 主程序
# ============================================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("城市天气与未来预报")
    clock = pygame.time.Clock()

    font_name = find_chinese_font()
    font_title     = make_font(font_name, 64, bold=True)
    font_date      = make_font(font_name, 32, bold=False)  # 新增大号日期字体
    font_city      = make_font(font_name, 72, bold=True)
    font_temp      = make_font(font_name, 110, bold=True) 
    font_degree    = make_font(font_name, 55, bold=True)
    font_weather   = make_font(font_name, 40, bold=True)
    font_label     = make_font(font_name, 24, bold=True)
    font_value     = make_font(font_name, 30, bold=True)
    font_small     = make_font(font_name, 22)
    font_btn       = make_font(font_name, 30, bold=True)
    font_exit      = make_font(font_name, 28, bold=True)
    font_panel_t   = make_font(font_name, 32, bold=True)
    font_forecast_d= make_font(font_name, 28, bold=True)
    font_forecast_t= make_font(font_name, 24, bold=True)

    # 加载背景图
    background_img = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background_img = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print(f"背景图加载失败: {e}")

    # 天气半透明滤镜缓存
    weather_overlay_cache = {}
    def get_weather_overlay(weather):
        if weather not in weather_overlay_cache:
            top, bottom = WEATHER_COLORS.get(weather, ((40, 50, 80), (80, 100, 140)))
            surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for y in range(0, HEIGHT, 2):
                t = y / max(1, HEIGHT - 1)
                c = lerp_color(top, bottom, t)
                pygame.draw.rect(surf, (*c, 160), (0, y, WIDTH, 2))
            weather_overlay_cache[weather] = surf.convert_alpha()
        return weather_overlay_cache[weather]

    def init_data():
        for c in CITIES_CONFIG:
            CITIES_DATA[c["name"]] = {"status": "loading", "name": c["name"]}
            t = threading.Thread(target=fetch_and_update, args=(c,), daemon=True)
            t.start()
    
    selected_idx = 0
    def refresh_current_city():
        city = CITIES_CONFIG[selected_idx]
        CITIES_DATA[city["name"]] = {"status": "loading", "name": city["name"]}
        t = threading.Thread(target=fetch_and_update, args=(city,), daemon=True)
        t.start()

    init_data()
    
    # 布局参数 (整体下移至 160，留出顶部空间)
    city_panel_x, city_panel_y = 40, 160
    city_panel_w, city_panel_h = 300, HEIGHT - city_panel_y - 60

    city_buttons = []
    for i, c in enumerate(CITIES_CONFIG):
        rect = (city_panel_x + 10, city_panel_y + 60 + i * 66, 280, 56)
        city_buttons.append(CityButton(rect, c["name"], font_btn, i))

    info_x, info_y = city_panel_x + city_panel_w + 30, city_panel_y
    info_w, info_h = WIDTH - info_x - 40, city_panel_h

    exit_btn = Button((WIDTH - 180, 40, 140, 60), "退出", lambda: sys.exit(), font_exit, color=(180, 60, 60, 150), hover_color=(235, 87, 87, 220))
    refresh_btn = Button((WIDTH - 340, 40, 140, 60), "刷新", refresh_current_city, font_exit, color=(60, 130, 200, 150), hover_color=(86, 196, 255, 220))

    particles = ParticleSystem()
    particles.init(WEATHER_OVERCAST)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        now = datetime.now()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_UP and selected_idx > 0:
                    selected_idx -= 1
                elif event.key == pygame.K_DOWN and selected_idx < len(CITIES_CONFIG) - 1:
                    selected_idx += 1
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if exit_btn.click(event.pos): continue
                if refresh_btn.click(event.pos): continue
                for cb in city_buttons:
                    if cb.is_clicked(event.pos):
                        selected_idx = cb.idx
                        break

        city_cfg = CITIES_CONFIG[selected_idx]
        data = CITIES_DATA.get(city_cfg["name"], {"status": "loading"})
        
        cur_weather = data.get("weather", WEATHER_OVERCAST) if data.get("status") == "ok" else WEATHER_OVERCAST
        particles.init(cur_weather)

        # ===== 背景及天气特效叠加 =====
        # 1. 底层背景图
        if background_img:
            screen.blit(background_img, (0, 0))
        else:
            screen.fill((20, 24, 34))

        # 2. 叠加天气颜色滤镜 (半透明渐变)
        screen.blit(get_weather_overlay(cur_weather), (0, 0))

        # 3. 整体暗化遮罩，增强前景文字对比度
        dark_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dark_overlay.fill((0, 0, 0, 45))
        screen.blit(dark_overlay, (0, 0))

        # 4. 绘制天气动态粒子 (雨/雪/雾) 放在最顶层，效果最明显
        particles.update_and_draw(screen)

        # ===== 顶部标题 =====
        # 拉开 Y 轴距离，消除重叠
        draw_text(screen, "城市天气与未来预报", font_title, WHITE, (WIDTH // 2, 25), anchor="midtop")
        date_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
        draw_text(screen, date_str, font_date, (235, 235, 235), (WIDTH // 2, 105), anchor="midtop")

        # ===== 左侧城市列表面板 =====
        panel = pygame.Surface((city_panel_w, city_panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 110))
        screen.blit(panel, (city_panel_x, city_panel_y))
        pygame.draw.rect(screen, ACCENT, (city_panel_x, city_panel_y, city_panel_w, city_panel_h), 2, border_radius=12)
        draw_text(screen, "城市列表", font_panel_t, GOLD, (city_panel_x + city_panel_w // 2, city_panel_y + 15), anchor="midtop")

        for cb in city_buttons:
            cb.update(mouse_pos, selected_idx)
            cb.draw(screen)

        # ===== 右侧主信息面板 =====
        main_panel = pygame.Surface((info_w, info_h), pygame.SRCALPHA)
        main_panel.fill((0, 0, 0, 90))
        screen.blit(main_panel, (info_x, info_y))
        pygame.draw.rect(screen, ACCENT, (info_x, info_y, info_w, info_h), 2, border_radius=12)

        draw_text(screen, city_cfg["name"], font_city, WHITE, (info_x + 50, info_y + 20), anchor="topleft")
        draw_text(screen, "更新于 " + now.strftime("%H:%M"), font_small, (210, 210, 210), (info_x + info_w - 25, info_y + 30), anchor="topright", shadow=False)

        if data.get("status") == "ok":
            temp_str = str(data["temp"])
            weather_str = data["weather"]
            feel_str = f"最高 {data['high']}°   最低 {data['low']}°   体感 {data['feel']}°C"
            detail_items = [
                ("湿度",     f"{data['humidity']}%"),
                ("风力",     data["wind"]),
                ("气压",     f"{data['pressure']} hPa"),
                ("能见度",   f"{data['visibility']} km"),
                ("紫外线",   data["uv"]),
                ("空气质量", f"{data['aqi']} {data['quality']}"),
                ("日出",     data["sunrise"]),
                ("日落",     data["sunset"]),
            ]
            forecast_list = data.get("forecast", [])
        else:
            temp_str = "--"
            weather_str = "获取中..." if data.get("status") == "loading" else "获取失败"
            feel_str = "请检查网络或点击右上方刷新按钮重试"
            detail_items = [("提示", "暂无数据")] * 8
            forecast_list = []

        # ===== 当天信息区 =====
        # 1. 温度大字
        temp_surf = font_temp.render(temp_str, True, WHITE)
        temp_shadow = font_temp.render(temp_str, True, (0, 0, 0))
        temp_rect = temp_surf.get_rect(topleft=(info_x + 50, info_y + 80))
        for dx, dy in [(-2,-2),(-2,2),(2,-2),(2,2),(-2,0),(2,0),(0,-2),(0,2)]:
            screen.blit(temp_shadow, (temp_rect.x + dx, temp_rect.y + dy))
        screen.blit(temp_surf, temp_rect)

        # 2. 度数符号
        deg_surf = font_degree.render("°C", True, GOLD)
        screen.blit(deg_surf, (temp_rect.right + 8, temp_rect.y + 20))

        # 3. 天气大图标
        icon_center = (info_x + info_w - 120, info_y + 130)
        draw_weather_icon(screen, cur_weather, icon_center, 60)

        # 4. 天气状况与体感
        draw_text(screen, weather_str, font_weather, GOLD, (info_x + 50, info_y + 200), anchor="topleft")
        draw_text(screen, feel_str, font_value, (235, 235, 235), (info_x + 50, info_y + 250), anchor="topleft", shadow=False)

        # ===== 详细信息卡片网格（8 个）=====
        detail_y = info_y + 310
        n = len(detail_items)
        card_gap = 12
        card_w = (info_w - 40 - (n - 1) * card_gap) // n
        card_h = 100

        for i, (label, value) in enumerate(detail_items):
            cx = info_x + 20 + i * (card_w + card_gap)
            cy = detail_y
            card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            card_surf.fill((255, 255, 255, 35))
            screen.blit(card_surf, (cx, cy))
            pygame.draw.rect(screen, ACCENT, (cx, cy, card_w, card_h), 2, border_radius=10)
            
            draw_text(screen, label, font_label, (200, 220, 240), (cx + card_w // 2, cy + 18), anchor="midtop", shadow=False)
            
            test = font_value.render(value, True, WHITE)
            vfont = font_value if test.get_width() <= card_w - 14 else font_label
            draw_text(screen, value, vfont, WHITE, (cx + card_w // 2, cy + 55), anchor="midtop")

        # ===== 未来5日预报区 =====
        f_title_y = info_y + 430
        draw_text(screen, "未来5日预报", font_panel_t, GOLD, (info_x + 25, f_title_y), anchor="topleft")
        pygame.draw.line(screen, ACCENT, (info_x + 25, f_title_y + 45), (info_x + info_w - 25, f_title_y + 45), 2)

        f_card_y = f_title_y + 65
        f_n = 5
        f_gap = 15
        f_card_w = (info_w - 40 - (f_n - 1) * f_gap) // f_n
        f_card_h = 400

        if not forecast_list:
            draw_text(screen, "预报数据获取中...", font_value, (210, 210, 210), 
                      (info_x + info_w // 2, f_card_y + f_card_h // 2), anchor="center")
        else:
            for i, fc in enumerate(forecast_list):
                fcx = info_x + 20 + i * (f_card_w + f_gap)
                fcy = f_card_y
                
                fc_surf = pygame.Surface((f_card_w, f_card_h), pygame.SRCALPHA)
                fc_surf.fill((255, 255, 255, 25))
                screen.blit(fc_surf, (fcx, fcy))
                pygame.draw.rect(screen, ACCENT, (fcx, fcy, f_card_w, f_card_h), 2, border_radius=12)
                
                draw_text(screen, fc["date"], font_forecast_d, WHITE, (fcx + f_card_w // 2, fcy + 30), anchor="midtop")
                draw_text(screen, fc["week"], font_forecast_t, GOLD, (fcx + f_card_w // 2, fcy + 70), anchor="midtop")
                
                draw_weather_icon(screen, fc["weather"], (fcx + f_card_w // 2, fcy + 170), 45)
                
                draw_text(screen, fc["weather"], font_value, WHITE, (fcx + f_card_w // 2, fcy + 240), anchor="midtop")
                
                high_str = f"{fc['high']}°"
                low_str = f"{fc['low']}°"
                draw_text(screen, high_str, font_forecast_t, TEMP_HOT, (fcx + f_card_w // 2, fcy + 290), anchor="midtop")
                draw_text(screen, low_str, font_forecast_t, TEMP_COLD, (fcx + f_card_w // 2, fcy + 330), anchor="midtop")

        # 底部提示
        draw_text(screen, "点击左侧城市切换  |  ↑↓ 切换城市  |  点击右上角刷新  |  ESC 退出", font_small, (220, 220, 220), (WIDTH // 2, HEIGHT - 28), anchor="center", shadow=False)

        exit_btn.update(mouse_pos)
        exit_btn.draw(screen)
        refresh_btn.update(mouse_pos)
        refresh_btn.draw(screen)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
