# -*- coding: utf-8 -*-
"""
杭州天气与本地环境监测 - 好搭AI派
功能：获取杭州实时天气数据并显示，同时读取IO1口DHT11传感器的本地温湿度
硬件：ESP32扩展板 IO1口接DHT11温湿度传感器
依赖：pygame-ce, ESP32官方库, urllib, json

优化要点：
  1. pygame display 最先初始化，立即显示加载画面，杜绝黑屏
  2. ESP32 初始化与 DHT11 读取全部在后台守护线程执行，绝不阻塞主循环
  3. 退出按钮使用 running=False 优雅退出，不再用 sys.exit()
  4. dark_overlay 等可复用 Surface 预创建，消除每帧分配开销
"""

import os
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'  # 必须在 ALL import 之前

import datetime
import sys
import math
import random
import threading
import urllib.request
import json

import pygame
pygame.display.init()
pygame.font.init()

# ===== 日志标准模式（追加写 + 块缓冲 + stdout 分路）=====
_LOG_DIR = 'logs'
if not os.path.exists(_LOG_DIR):
    os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(
    _LOG_DIR,
    'hangzhou_weather_dht11_%s.log' % datetime.datetime.now().strftime('%Y%m%d')
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
print('杭州天气与本地环境监测 启动于 %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print('日志文件: %s' % _LOG_FILE)
print('=' * 60)

# ===== ESP32 硬件初始化（主线程，在加载画面显示之后执行）=====
from ESP32 import ESP32, GPIO_IO_01

board = ESP32()
_board_started = False  # 延迟到 main() 中加载画面后调用 board.start()
DHT11_PIN = GPIO_IO_01  # IO1口

# ===== 配置 =====
WIDTH, HEIGHT = 1920, 1080
BG_IMAGE = os.path.join("images", "1.jpg")
ICON_DIR = "icons"
CITY_LAT = 30.27
CITY_LON = 120.15

# 颜色
WHITE = (255, 255, 255)
ACCENT = (86, 196, 255)
GOLD = (255, 210, 90)
TEMP_HOT = (255, 120, 80)
TEMP_COLD = (120, 180, 255)
GREEN = (102, 204, 0)
ORANGE = (255, 165, 0)
CARD_BG = (255, 255, 255, 35)

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

# 天气图标文件映射
WEATHER_ICONS = {
    WEATHER_SUNNY:       "weather_sunny.png",
    WEATHER_CLOUDY:      "weather_cloudy.png",
    WEATHER_OVERCAST:    "weather_overcast.png",
    WEATHER_LIGHT_RAIN:  "weather_light_rain.png",
    WEATHER_HEAVY_RAIN:  "weather_heavy_rain.png",
    WEATHER_THUNDER:     "weather_thunder.png",
    WEATHER_LIGHT_SNOW:  "weather_light_snow.png",
    WEATHER_HEAVY_SNOW:  "weather_heavy_snow.png",
    WEATHER_FOG:         "weather_fog.png",
}

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

# 天气数据缓存
weather_data = {"status": "loading"}

# DHT11 数据
local_temp = None
local_humi = None
dht11_error = None
_dht11_reading = False  # 标记是否正在读取，防止重入

# ============================================================
# ESP32 初始化（在加载画面显示后，主线程中调用）
# ============================================================
def init_esp32():
    """主线程中初始化ESP32扩展板，board对象已在全局创建，此处只需 start()"""
    global _board_started
    try:
        _board_started = board.start()
        if _board_started:
            print('ESP32扩展板连接成功')
        else:
            print('警告：ESP32扩展板连接失败，DHT11数据将不可用')
    except Exception as e:
        print('ESP32初始化异常: %s' % e)
        _board_started = False

# ============================================================
# 天气API获取（Open-Meteo 免费API）
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

def fetch_weather_data():
    """获取杭州实时天气数据（在后台线程执行）"""
    global weather_data
    try:
        weather_url = (
            "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
            "&current_weather=true"
            "&hourly=relative_humidity_2m,pressure_msl,visibility,apparent_temperature,uv_index"
            "&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset"
            "&timezone=Asia%%2FShanghai"
        ) % (CITY_LAT, CITY_LON)
        req = urllib.request.Request(weather_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        aqi_url = (
            "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=%s&longitude=%s"
            "&current=us_aqi&timezone=Asia%%2FShanghai"
        ) % (CITY_LAT, CITY_LON)
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
        wind_str = "%s风 %s" % (wind_dir_str, wind_scale_str) if wind_scale_str != "微风" else "微风"

        uv_str = "弱"
        try:
            uv_f = float(uv_index)
            if uv_f >= 8: uv_str = "极强"
            elif uv_f >= 6: uv_str = "强"
            elif uv_f >= 3: uv_str = "中"
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

        # 未来5天预报
        forecast_list = []
        d_time = daily.get("time", [])
        d_code = daily.get("weathercode", [])
        d_max = daily.get("temperature_2m_max", [])
        d_min = daily.get("temperature_2m_min", [])

        for i in range(min(5, len(d_time))):
            dt = datetime.datetime.strptime(d_time[i], "%Y-%m-%d")
            week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
            forecast_list.append({
                "date": "%s/%s" % (dt.month, dt.day),
                "week": "今日" if i == 0 else ("明日" if i == 1 else week),
                "weather": parse_weather_code(d_code[i] if i < len(d_code) else 3),
                "high": round(d_max[i] if i < len(d_max) else 0),
                "low": round(d_min[i] if i < len(d_min) else 0),
            })

        weather_data = {
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
        print('杭州天气数据获取成功: %s %d°C' % (weather_type, round(temp)))
    except Exception as e:
        print('获取天气失败: %s' % e)
        weather_data = {"status": "error", "error_msg": str(e)}

def fetch_weather_thread():
    """启动子线程获取天气数据"""
    t = threading.Thread(target=fetch_weather_data, daemon=True)
    t.start()

# ============================================================
# DHT11 本地温湿度读取（后台线程，不阻塞主循环）
# ============================================================
def read_dht11_async():
    """在后台线程中读取DHT11，结果写入全局变量"""
    global local_temp, local_humi, dht11_error, _dht11_reading
    if _dht11_reading:
        return  # 防止重入
    _dht11_reading = True
    try:
        if not _board_started or board is None:
            # ESP32 尚未就绪，等待重试
            dht11_error = 'ESP32扩展板未连接'
        else:
            t = board.dhtReadTemperature(DHT11_PIN, timeout=3)
            h = board.dhtReadHumidity(DHT11_PIN, timeout=3)
            if t is not None and h is not None:
                local_temp = float(t)
                local_humi = float(h)
                dht11_error = None
                print('DHT11读取成功: 温度=%.1f 湿度=%.1f' % (local_temp, local_humi))
            else:
                dht11_error = 'DHT11返回空值'
    except Exception as e:
        dht11_error = str(e)
    finally:
        _dht11_reading = False

def dht11_loop():
    """DHT11 后台循环线程，每3秒读取一次"""
    while True:
        read_dht11_async()
        threading.Event().wait(3.0)  # 非阻塞式延时

def start_dht11_thread():
    """启动 DHT11 后台读取线程"""
    t = threading.Thread(target=dht11_loop, daemon=True)
    t.start()

# ============================================================
# 工具函数
# ============================================================
def find_chinese_font():
    """寻找可用中文字体，优先使用雅黑等更好看的字体"""
    candidates = [
        "microsoftyahei", "msyh", "simhei", "pingfang",
        "notosanscjksc", "notosanscjk", "wenquanyimicrohei",
        "wqymicrohei", "stheiti", "arialunicodems",
    ]
    available = pygame.font.get_fonts()
    for name in candidates:
        if name in available:
            return name
    # 系统字体列表中找不到，尝试已知文件路径
    paths = [
        "/home/cxdz/jupyter/assets/msyh.ttc",
        "/home/cxdz/jupyter/assets/simhei.ttf",
        "/home/cxdz/jupyter/assets/PingFang_Regular.ttf",
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

def draw_rounded_rect_alpha(surface, color, rect, alpha=160, border_radius=0):
    rect = pygame.Rect(rect)
    s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(s, (color[0], color[1], color[2], alpha), s.get_rect(), border_radius=border_radius)
    surface.blit(s, rect.topleft)

# ============================================================
# 天气图标加载与绘制
# ============================================================
_icon_masters = {}
_icon_cache = {}

def load_weather_icons():
    for weather, fname in WEATHER_ICONS.items():
        path = os.path.join(ICON_DIR, fname)
        if not os.path.exists(path):
            continue
        try:
            _icon_masters[weather] = pygame.image.load(path).convert_alpha()
        except Exception as e:
            print('天气图标加载失败 (%s): %s' % (fname, e))

def get_weather_icon(weather, box):
    key = (weather, box)
    if key not in _icon_cache:
        master = _icon_masters.get(weather)
        if master is None:
            return None
        _icon_cache[key] = pygame.transform.smoothscale(master, (box, box))
    return _icon_cache[key]

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
    box = int(size * 2)
    icon = get_weather_icon(weather, box)
    if icon is not None:
        surface.blit(icon, icon.get_rect(center=center))
        return
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
# 粒子系统
# ============================================================
class ParticleSystem:
    def __init__(self):
        self.particles = []
        self.weather = None

    def init(self, weather):
        if self.weather == weather:
            return
        self.weather = weather
        self.particles = []
        if weather in (WEATHER_LIGHT_RAIN, WEATHER_HEAVY_RAIN, WEATHER_THUNDER):
            count = 150 if weather == WEATHER_LIGHT_RAIN else 280
            for _ in range(count):
                self.particles.append({
                    "x": random.uniform(0, WIDTH), "y": random.uniform(0, HEIGHT),
                    "vy": random.randint(9, 14), "vx": -2,
                    "len": random.randint(15, 25), "type": "rain"
                })
        elif weather in (WEATHER_LIGHT_SNOW, WEATHER_HEAVY_SNOW):
            count = 80 if weather == WEATHER_LIGHT_SNOW else 150
            for _ in range(count):
                self.particles.append({
                    "x": random.uniform(0, WIDTH), "y": random.uniform(0, HEIGHT),
                    "vy": random.uniform(1, 2.5), "vx": random.uniform(-0.5, 0.5),
                    "size": random.randint(3, 6), "phase": random.uniform(0, math.pi * 2),
                    "type": "snow"
                })
        elif weather == WEATHER_FOG:
            for _ in range(25):
                self.particles.append({
                    "x": random.uniform(0, WIDTH), "y": random.uniform(0, HEIGHT),
                    "r": random.randint(80, 160), "alpha": random.randint(20, 50),
                    "vx": random.uniform(-0.4, 0.4), "type": "fog"
                })

    def update_and_draw(self, surface):
        for p in self.particles:
            if p["type"] == "rain":
                p["x"] += p["vx"]
                p["y"] += p["vy"]
                if p["y"] > HEIGHT:
                    p["y"] = -p["len"]
                    p["x"] = random.uniform(0, WIDTH)
                pygame.draw.line(surface, (180, 200, 230), (p["x"], p["y"]),
                                 (p["x"] + p["vx"] * 2, p["y"] + p["len"]), 2)
            elif p["type"] == "snow":
                p["phase"] += 0.05
                p["x"] += p["vx"] + math.sin(p["phase"]) * 0.6
                p["y"] += p["vy"]
                if p["y"] > HEIGHT:
                    p["y"] = -10
                    p["x"] = random.uniform(0, WIDTH)
                pygame.draw.circle(surface, (255, 255, 255), (int(p["x"]), int(p["y"])), p["size"])
            elif p["type"] == "fog":
                p["x"] += p["vx"]
                if p["x"] < -p["r"]:
                    p["x"] = WIDTH + p["r"]
                if p["x"] > WIDTH + p["r"]:
                    p["x"] = -p["r"]
                fog_surf = pygame.Surface((p["r"] * 2, p["r"] * 2), pygame.SRCALPHA)
                pygame.draw.circle(fog_surf, (230, 235, 245, p["alpha"]), (p["r"], p["r"]), p["r"])
                surface.blit(fog_surf, (p["x"] - p["r"], p["y"] - p["r"]))

# ============================================================
# 按钮
# ============================================================
class Button:
    def __init__(self, rect, text, action, font, color=(60, 130, 200, 150), hover_color=(86, 196, 255, 220)):
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

# ============================================================
# 主程序
# ============================================================
def main():
    # ===== 第一步：立即创建窗口，显示加载画面 =====
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("杭州天气与本地环境监测")
    clock = pygame.time.Clock()

    # 字体加载（直接用已知路径，快速）
    font_name = find_chinese_font()
    font_title     = make_font(font_name, 60, bold=True)
    font_date      = make_font(font_name, 32, bold=False)
    font_city      = make_font(font_name, 72, bold=True)
    font_temp      = make_font(font_name, 110, bold=True)
    font_degree    = make_font(font_name, 54, bold=True)
    font_weather   = make_font(font_name, 42, bold=True)
    font_label     = make_font(font_name, 26, bold=True)
    font_value     = make_font(font_name, 34, bold=True)
    font_small     = make_font(font_name, 24)
    font_btn       = make_font(font_name, 30, bold=True)
    font_panel_t   = make_font(font_name, 36, bold=True)
    font_forecast_d= make_font(font_name, 30, bold=True)
    font_forecast_t= make_font(font_name, 26, bold=True)
    font_local_temp= make_font(font_name, 76, bold=True)
    font_local_label= make_font(font_name, 32, bold=True)
    font_local_val = make_font(font_name, 50, bold=True)
    font_loading   = make_font(font_name, 40, bold=True)

    # ===== 显示加载画面（第一帧立即输出） =====
    screen.fill((20, 24, 34))
    draw_text(screen, "杭州天气与本地环境监测", font_title, WHITE, (WIDTH // 2, HEIGHT // 2 - 60), anchor="center")
    draw_text(screen, "正在加载，请稍候...", font_loading, (180, 200, 230), (WIDTH // 2, HEIGHT // 2 + 20), anchor="center")
    pygame.display.flip()

    # ===== 第二步：ESP32 初始化（主线程，在加载画面之后执行，不阻塞窗口显示） =====
    init_esp32()

    # ===== 第三步：后台启动天气数据获取 =====
    fetch_weather_thread()

    # ===== 第四步：后台启动 DHT11 读取循环 =====
    start_dht11_thread()

    # ===== 加载背景图与图标（不阻塞太久） =====
    background_img = None
    if os.path.exists(BG_IMAGE):
        try:
            bg = pygame.image.load(BG_IMAGE)
            background_img = pygame.transform.smoothscale(bg, (WIDTH, HEIGHT)).convert()
        except Exception as e:
            print('背景图加载失败: %s' % e)

    load_weather_icons()

    # ===== 预创建可复用 Surface（避免每帧分配） =====
    # 暗化遮罩（固定不变，预创建一次）
    dark_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dark_overlay.fill((0, 0, 0, 45))

    # 天气半透明渐变滤镜缓存
    weather_overlay_cache = {}
    def get_weather_overlay(weather):
        if weather not in weather_overlay_cache:
            top, bottom = WEATHER_COLORS.get(weather, ((40, 50, 80), (80, 100, 140)))
            surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for y in range(0, HEIGHT, 4):  # 步长4，减少循环次数
                t = y / max(1, HEIGHT - 1)
                c = lerp_color(top, bottom, t)
                pygame.draw.rect(surf, (c[0], c[1], c[2], 160), (0, y, WIDTH, 4))
            weather_overlay_cache[weather] = surf.convert_alpha()
        return weather_overlay_cache[weather]

    # ===== 退出标志（用 flag 而非 sys.exit） =====
    running = [True]  # 用列表包装以便闭包修改

    # 退出按钮
    exit_btn = Button((WIDTH - 180, 40, 140, 55), "退出", lambda: running.__setitem__(0, False), font_btn,
                      color=(180, 60, 60, 150), hover_color=(235, 87, 87, 220))
    # 刷新按钮
    def do_refresh():
        global weather_data
        weather_data = {"status": "loading"}
        fetch_weather_thread()
        # DHT11 由后台线程自动读取，无需额外触发
    refresh_btn = Button((WIDTH - 340, 40, 140, 55), "刷新", do_refresh, font_btn)

    particles = ParticleSystem()
    particles.init(WEATHER_OVERCAST)

    # 天气自动刷新计时器
    weather_refresh_timer = 0
    WEATHER_REFRESH_INTERVAL = 600000  # 10分钟自动刷新天气（毫秒）

    while running[0]:
        mouse_pos = pygame.mouse.get_pos()
        now = datetime.datetime.now()
        dt_ms = clock.tick(60)

        # ===== 事件处理（每帧必响应，不被任何阻塞操作卡住） =====
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running[0] = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running[0] = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if exit_btn.click(event.pos):
                    continue
                if refresh_btn.click(event.pos):
                    continue

        # ===== 天气数据自动刷新（10分钟一次） =====
        weather_refresh_timer += dt_ms
        if weather_refresh_timer >= WEATHER_REFRESH_INTERVAL:
            weather_refresh_timer = 0
            fetch_weather_thread()

        cur_weather = weather_data.get("weather", WEATHER_OVERCAST) if weather_data.get("status") == "ok" else WEATHER_OVERCAST
        particles.init(cur_weather)

        # ===== 背景 =====
        if background_img:
            screen.blit(background_img, (0, 0))
        else:
            screen.fill((20, 24, 34))

        screen.blit(get_weather_overlay(cur_weather), (0, 0))
        screen.blit(dark_overlay, (0, 0))  # 预创建的遮罩，零开销
        particles.update_and_draw(screen)

        # ===== 顶部标题 =====
        draw_text(screen, "杭州天气与本地环境监测", font_title, WHITE, (WIDTH // 2, 20), anchor="midtop")
        date_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
        draw_text(screen, date_str, font_date, (235, 235, 235), (WIDTH // 2, 85), anchor="midtop")

        # ===== 左侧：杭州天气面板 =====
        left_x, left_y = 40, 130
        left_w, left_h = 1240, HEIGHT - left_y - 50

        panel = pygame.Surface((left_w, left_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 100))
        screen.blit(panel, (left_x, left_y))
        pygame.draw.rect(screen, ACCENT, (left_x, left_y, left_w, left_h), 2, border_radius=12)

        draw_text(screen, "杭州", font_city, WHITE, (left_x + 40, left_y + 15), anchor="topleft")
        draw_text(screen, "更新于 " + now.strftime("%H:%M"), font_small, (210, 210, 210),
                  (left_x + left_w - 20, left_y + 25), anchor="topright", shadow=False)

        if weather_data.get("status") == "ok":
            temp_str = str(weather_data["temp"])
            weather_str = weather_data["weather"]
            feel_str = "最高 %d°  最低 %d°  体感 %d°C" % (weather_data["high"], weather_data["low"], weather_data["feel"])
            detail_items = [
                ("湿度", "%d%%" % weather_data["humidity"]),
                ("风力", weather_data["wind"]),
                ("气压", "%d hPa" % weather_data["pressure"]),
                ("能见度", "%.1f km" % weather_data["visibility"]),
                ("紫外线", weather_data["uv"]),
                ("空气质量", "%d %s" % (weather_data["aqi"], weather_data["quality"])),
                ("日出", weather_data["sunrise"]),
                ("日落", weather_data["sunset"]),
            ]
            forecast_list = weather_data.get("forecast", [])
        else:
            temp_str = "--"
            weather_str = "获取中..." if weather_data.get("status") == "loading" else "获取失败"
            feel_str = "请检查网络或点击刷新按钮重试"
            detail_items = [("提示", "暂无数据")] * 8
            forecast_list = []

        # 温度大字
        temp_surf = font_temp.render(temp_str, True, WHITE)
        temp_shadow = font_temp.render(temp_str, True, (0, 0, 0))
        temp_rect = temp_surf.get_rect(topleft=(left_x + 40, left_y + 70))
        for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2), (-2, 0), (2, 0), (0, -2), (0, 2)]:
            screen.blit(temp_shadow, (temp_rect.x + dx, temp_rect.y + dy))
        screen.blit(temp_surf, temp_rect)

        # 度数符号
        deg_surf = font_degree.render("°C", True, GOLD)
        screen.blit(deg_surf, (temp_rect.right + 8, temp_rect.y + 15))

        # 天气大图标
        icon_center = (left_x + left_w - 140, left_y + 130)
        draw_weather_icon(screen, cur_weather, icon_center, 62)

        # 天气状况与体感
        draw_text(screen, weather_str, font_weather, GOLD, (left_x + 40, left_y + 200), anchor="topleft")
        draw_text(screen, feel_str, font_value, (235, 235, 235), (left_x + 40, left_y + 255), anchor="topleft", shadow=False)

        # 详细信息卡片网格（8个）
        detail_y = left_y + 315
        n = len(detail_items)
        card_gap = 10
        card_w = (left_w - 40 - (n - 1) * card_gap) // n
        card_h = 105

        for i, (label, value) in enumerate(detail_items):
            cx = left_x + 20 + i * (card_w + card_gap)
            cy = detail_y
            card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            card_surf.fill((255, 255, 255, 35))
            screen.blit(card_surf, (cx, cy))
            pygame.draw.rect(screen, ACCENT, (cx, cy, card_w, card_h), 2, border_radius=10)

            draw_text(screen, label, font_label, (200, 220, 240), (cx + card_w // 2, cy + 18), anchor="midtop", shadow=False)

            test = font_value.render(value, True, WHITE)
            vfont = font_value if test.get_width() <= card_w - 12 else font_label
            draw_text(screen, value, vfont, WHITE, (cx + card_w // 2, cy + 55), anchor="midtop")

        # 未来5日预报区
        f_title_y = left_y + 440
        draw_text(screen, "未来5日预报", font_panel_t, GOLD, (left_x + 20, f_title_y), anchor="topleft")
        pygame.draw.line(screen, ACCENT, (left_x + 20, f_title_y + 45), (left_x + left_w - 20, f_title_y + 45), 2)

        f_card_y = f_title_y + 60
        f_n = 5
        f_gap = 12
        f_card_w = (left_w - 40 - (f_n - 1) * f_gap) // f_n
        f_card_h = 310

        if not forecast_list:
            draw_text(screen, "预报数据获取中...", font_value, (210, 210, 210),
                      (left_x + left_w // 2, f_card_y + f_card_h // 2), anchor="center")
        else:
            for i, fc in enumerate(forecast_list):
                fcx = left_x + 20 + i * (f_card_w + f_gap)
                fcy = f_card_y

                fc_surf = pygame.Surface((f_card_w, f_card_h), pygame.SRCALPHA)
                fc_surf.fill((255, 255, 255, 25))
                screen.blit(fc_surf, (fcx, fcy))
                pygame.draw.rect(screen, ACCENT, (fcx, fcy, f_card_w, f_card_h), 2, border_radius=12)

                draw_text(screen, fc["date"], font_forecast_d, WHITE, (fcx + f_card_w // 2, fcy + 25), anchor="midtop")
                draw_text(screen, fc["week"], font_forecast_t, GOLD, (fcx + f_card_w // 2, fcy + 65), anchor="midtop")

                draw_weather_icon(screen, fc["weather"], (fcx + f_card_w // 2, fcy + 135), 38)

                draw_text(screen, fc["weather"], font_value, WHITE, (fcx + f_card_w // 2, fcy + 195), anchor="midtop")

                draw_text(screen, "%d°" % fc["high"], font_forecast_t, TEMP_HOT,
                          (fcx + f_card_w // 2, fcy + 240), anchor="midtop")
                draw_text(screen, "%d°" % fc["low"], font_forecast_t, TEMP_COLD,
                          (fcx + f_card_w // 2, fcy + 275), anchor="midtop")

        # ===== 右侧：本地DHT11环境监测面板 =====
        right_x = left_x + left_w + 30
        right_y = left_y
        right_w = WIDTH - right_x - 40
        right_h = left_h

        panel2 = pygame.Surface((right_w, right_h), pygame.SRCALPHA)
        panel2.fill((0, 0, 0, 100))
        screen.blit(panel2, (right_x, right_y))
        pygame.draw.rect(screen, ACCENT, (right_x, right_y, right_w, right_h), 2, border_radius=12)

        draw_text(screen, "本地环境监测", font_panel_t, GOLD, (right_x + right_w // 2, right_y + 20), anchor="midtop")
        draw_text(screen, "IO1口 - DHT11传感器", font_small, (200, 200, 200),
                  (right_x + right_w // 2, right_y + 60), anchor="midtop", shadow=False)

        # 分隔线
        pygame.draw.line(screen, ACCENT, (right_x + 20, right_y + 95), (right_x + right_w - 20, right_y + 95), 2)

        # 本地温度显示
        temp_y = right_y + 125
        draw_text(screen, "本地温度", font_local_label, (180, 200, 230), (right_x + right_w // 2, temp_y), anchor="midtop")

        if local_temp is not None:
            lt_str = "%.1f" % local_temp
            lt_surf = font_local_temp.render(lt_str, True, WHITE)
            lt_shadow = font_local_temp.render(lt_str, True, (0, 0, 0))
            lt_rect = lt_surf.get_rect(center=(right_x + right_w // 2 - 25, temp_y + 85))
            for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
                screen.blit(lt_shadow, (lt_rect.x + dx, lt_rect.y + dy))
            screen.blit(lt_surf, lt_rect)
            deg_s = font_degree.render("°C", True, GOLD)
            screen.blit(deg_s, (lt_rect.right + 5, lt_rect.y + 5))
        else:
            err_msg = dht11_error if dht11_error else "读取中..."
            draw_text(screen, "--", font_local_temp, (150, 150, 150), (right_x + right_w // 2, temp_y + 65), anchor="center")
            draw_text(screen, err_msg, font_small, (200, 120, 120), (right_x + right_w // 2, temp_y + 130), anchor="center")

        # 温度状态指示
        if local_temp is not None:
            if local_temp >= 35:
                temp_status = "高温"
                temp_color = (255, 80, 80)
            elif local_temp >= 28:
                temp_status = "偏热"
                temp_color = (255, 165, 0)
            elif local_temp >= 18:
                temp_status = "舒适"
                temp_color = GREEN
            elif local_temp >= 10:
                temp_status = "偏凉"
                temp_color = (100, 200, 255)
            else:
                temp_status = "寒冷"
                temp_color = (80, 150, 255)
            draw_text(screen, temp_status, font_value, temp_color,
                      (right_x + right_w // 2, temp_y + 175), anchor="midtop")

        # 分隔线
        sep_y = temp_y + 225
        pygame.draw.line(screen, ACCENT, (right_x + 20, sep_y), (right_x + right_w - 20, sep_y), 2)

        # 本地湿度显示
        humi_y = sep_y + 35
        draw_text(screen, "本地湿度", font_local_label, (180, 200, 230), (right_x + right_w // 2, humi_y), anchor="midtop")

        if local_humi is not None:
            lh_str = "%.1f" % local_humi
            lh_surf = font_local_temp.render(lh_str, True, WHITE)
            lh_shadow = font_local_temp.render(lh_str, True, (0, 0, 0))
            lh_rect = lh_surf.get_rect(center=(right_x + right_w // 2 - 22, humi_y + 85))
            for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
                screen.blit(lh_shadow, (lh_rect.x + dx, lh_rect.y + dy))
            screen.blit(lh_surf, lh_rect)
            pct_s = font_degree.render("%", True, GOLD)
            screen.blit(pct_s, (lh_rect.right + 5, lh_rect.y + 5))
        else:
            draw_text(screen, "--", font_local_temp, (150, 150, 150), (right_x + right_w // 2, humi_y + 65), anchor="center")

        # 湿度状态指示
        if local_humi is not None:
            if local_humi >= 80:
                humi_status = "潮湿"
                humi_color = (100, 180, 255)
            elif local_humi >= 60:
                humi_status = "湿润"
                humi_color = GREEN
            elif local_humi >= 40:
                humi_status = "适宜"
                humi_color = GREEN
            elif local_humi >= 20:
                humi_status = "干燥"
                humi_color = ORANGE
            else:
                humi_status = "极干"
                humi_color = (255, 100, 100)
            draw_text(screen, humi_status, font_value, humi_color,
                      (right_x + right_w // 2, humi_y + 175), anchor="midtop")

        # 杭州天气与本地对比
        compare_y = humi_y + 225
        pygame.draw.line(screen, ACCENT, (right_x + 20, compare_y), (right_x + right_w - 20, compare_y), 2)
        draw_text(screen, "数据对比", font_local_label, GOLD, (right_x + right_w // 2, compare_y + 18), anchor="midtop")

        compare_y2 = compare_y + 60
        if weather_data.get("status") == "ok" and local_temp is not None:
            w_temp = weather_data["temp"]
            w_humi = weather_data["humidity"]
            t_diff = local_temp - w_temp
            h_diff = local_humi - w_humi if local_humi is not None else 0

            t_sign = "+" if t_diff >= 0 else ""
            h_sign = "+" if h_diff >= 0 else ""

            draw_text(screen, "温度差: %s%.1f°C" % (t_sign, t_diff), font_value, WHITE,
                      (right_x + right_w // 2, compare_y2), anchor="midtop")
            if local_humi is not None:
                draw_text(screen, "湿度差: %s%.1f%%" % (h_sign, h_diff), font_value, WHITE,
                          (right_x + right_w // 2, compare_y2 + 45), anchor="midtop")
        else:
            draw_text(screen, "等待数据...", font_small, (180, 180, 180),
                      (right_x + right_w // 2, compare_y2), anchor="midtop")

        # 底部提示
        draw_text(screen, "点击右上角刷新数据  |  ESC 退出  |  IO1口接DHT11温湿度传感器",
                  font_small, (220, 220, 220), (WIDTH // 2, HEIGHT - 25), anchor="center", shadow=False)

        exit_btn.update(mouse_pos)
        exit_btn.draw(screen)
        refresh_btn.update(mouse_pos)
        refresh_btn.draw(screen)

        pygame.display.flip()

    # ===== 优雅退出 =====
    try:
        if _board_started and board is not None:
            board.close()
            print('ESP32 已关闭')
    except Exception as e:
        print('ESP32关闭异常: %s' % e)
    pygame.quit()
    print('程序结束')

if __name__ == "__main__":
    main()
