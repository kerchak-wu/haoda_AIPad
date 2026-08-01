# -*- coding: utf-8 -*-
"""
智能风扇控制系统
功能：
  - 屏幕显示当前档位、电机转速值、舵机角度、风扇状态
  - 触摸屏幕上的按钮切换风扇档位
  - ma口（电机接口）接电机带动风扇转动
  - p1口（GPIO_IO_01）接舵机指示风扇档位
接线说明：
  - 电机接扩展板 ma 口（motor_MA）
  - 舵机接扩展板 p1 口（GPIO_IO_01）
"""

from ESP32 import *
import pygame
import math
import time

# ==================== 硬件初始化 ====================
board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

# ==================== 档位配置 ====================
# 每个档位对应：电机转速值(0-1023)、舵机角度(0-180)、档位名称、显示颜色
GEAR_CONFIG = [
    {"motor": 0,    "servo": 0,   "name": "0档", "label": "关闭", "color": (120, 120, 120)},  # 0档 关闭
    {"motor": 256,  "servo": 45,  "name": "1档", "label": "低速", "color": (102, 204, 0)},    # 1档 低速
    {"motor": 512,  "servo": 90,  "name": "2档", "label": "中速", "color": (0, 204, 204)},    # 2档 中速
    {"motor": 768,  "servo": 135, "name": "3档", "label": "高速", "color": (255, 153, 0)},    # 3档 高速
    {"motor": 1023, "servo": 180, "name": "4档", "label": "最高", "color": (255, 51, 51)},    # 4档 最高
]

current_gear = 0  # 当前档位，默认 0档（关闭）
SERVO_PIN = GPIO_IO_01  # p1 口对应 GPIO_IO_01

# ==================== 应用风扇档位 ====================
def apply_gear(gear_index):
    """根据档位索引设置电机转速和舵机角度"""
    global current_gear
    config = GEAR_CONFIG[gear_index]
    try:
        board.motor_MA(config["motor"])           # ma 口电机控制
        board.servo(SERVO_PIN, config["servo"])    # p1 口舵机指示
        current_gear = gear_index
        print(("切换到" + config["name"] + " " + config["label"] +
               " | 电机转速值:" + str(config["motor"]) +
               " | 舵机角度:" + str(config["servo"]) + "°"))
    except:
        print('出现异常：设置档位失败')

# 初始化为 0 档（关闭状态）
apply_gear(0)

# ==================== Pygame 界面初始化 ====================
pygame.init()
pygame.font.init()
screen = pygame.display.set_mode(size=(1920, 1080), flags=0, depth=0)
pygame.display.set_caption('智能风扇控制系统')

# 中文字体（平台自带）
font_title = pygame.font.Font('/home/cxdz/jupyter/assets/simhei.ttf', 80)
font_big   = pygame.font.Font('/home/cxdz/jupyter/assets/simhei.ttf', 120)
font_mid   = pygame.font.Font('/home/cxdz/jupyter/assets/simhei.ttf', 56)
font_small = pygame.font.Font('/home/cxdz/jupyter/assets/simhei.ttf', 40)

# 背景图片（缩放至窗口尺寸）
background_img = pygame.image.load('images/1.jpg')
background_img = pygame.transform.scale(background_img, (1920, 1080))

# 档位按钮区域配置（5个按钮横向排列在底部）
BUTTON_Y = 820
BUTTON_W = 320
BUTTON_H = 180
BUTTON_GAP = 30
BUTTON_START_X = (1920 - (BUTTON_W * 5 + BUTTON_GAP * 4)) // 2

def get_button_rect(index):
    """获取第 index 个档位按钮的矩形区域"""
    x = BUTTON_START_X + index * (BUTTON_W + BUTTON_GAP)
    return pygame.Rect(x, BUTTON_Y, BUTTON_W, BUTTON_H)

# 退出按钮区域配置（右上角）
EXIT_BUTTON_RECT = pygame.Rect(1720, 50, 160, 90)

# ==================== 风扇动画参数 ====================
fan_angle = 0.0  # 风扇叶片旋转角度

# ==================== 绘制函数 ====================
def draw_background():
    """绘制背景图片"""
    screen.blit(background_img, (0, 0))

def draw_rounded_rect_alpha(color, rect, alpha=160, border_radius=0):
    """绘制半透明圆角矩形（color 为 RGB 元组，alpha 控制透明度 0-255）"""
    # 兼容 tuple (x, y, w, h) 和 pygame.Rect 两种入参
    rect = pygame.Rect(rect)
    s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(s, (color[0], color[1], color[2], alpha), s.get_rect(), border_radius=border_radius)
    screen.blit(s, rect.topleft)

def draw_title():
    """绘制顶部标题"""
    title = font_title.render('智能风扇控制系统', True, (255, 255, 255))
    screen.blit(title, ((1920 - title.get_width()) // 2, 40))
    # 标题下方的分隔线
    pygame.draw.line(screen, (80, 100, 140), (200, 150), (1720, 150), 3)

def draw_info_panel():
    """绘制左侧信息显示面板：档位、电机转速值、舵机角度、状态"""
    panel_x = 100
    panel_y = 200
    panel_w = 760
    panel_h = 560
    # 面板背景（半透明）
    draw_rounded_rect_alpha((50, 60, 85), (panel_x, panel_y, panel_w, panel_h), alpha=160, border_radius=20)
    pygame.draw.rect(screen, (100, 130, 180), (panel_x, panel_y, panel_w, panel_h), 3, border_radius=20)

    config = GEAR_CONFIG[current_gear]

    # 当前档位（大字显示）
    label_gear = font_mid.render('当前档位', True, (180, 200, 230))
    screen.blit(label_gear, (panel_x + 60, panel_y + 40))
    gear_text = font_big.render(config["name"], True, config["color"])
    screen.blit(gear_text, (panel_x + 60, panel_y + 110))
    label_sub = font_mid.render(config["label"], True, config["color"])
    screen.blit(label_sub, (panel_x + 60 + gear_text.get_width() + 30, panel_y + 170))

    # 分隔线
    pygame.draw.line(screen, (80, 100, 140),
                     (panel_x + 40, panel_y + 270), (panel_x + panel_w - 40, panel_y + 270), 2)

    # 电机转速值
    label_motor = font_mid.render('电机转速值', True, (180, 200, 230))
    screen.blit(label_motor, (panel_x + 60, panel_y + 300))
    motor_text = font_big.render(str(config["motor"]), True, (255, 255, 255))
    screen.blit(motor_text, (panel_x + 60, panel_y + 370))

    # 舵机角度
    label_servo = font_mid.render('舵机角度', True, (180, 200, 230))
    screen.blit(label_servo, (panel_x + 420, panel_y + 300))
    servo_text = font_big.render((str(config["servo"]) + "°"), True, (255, 255, 255))
    screen.blit(servo_text, (panel_x + 420, panel_y + 370))

    # 运行状态
    if current_gear == 0:
        status_text = '已停止'
        status_color = (180, 180, 180)
    else:
        status_text = '运行中'
        status_color = (102, 204, 0)
    label_status = font_mid.render('状态：', True, (180, 200, 230))
    screen.blit(label_status, (panel_x + 60, panel_y + 490))
    status_render = font_mid.render(status_text, True, status_color)
    screen.blit(status_render, (panel_x + 60 + label_status.get_width() + 20, panel_y + 490))

def draw_fan(center_x, center_y, radius, angle, color):
    """绘制旋转的风扇（叶片数=4），转速由 angle 增量决定"""
    # 外圈
    pygame.draw.circle(screen, (90, 110, 140), (center_x, center_y), radius + 20, 4)
    # 中心轴
    pygame.draw.circle(screen, (60, 70, 95), (center_x, center_y), radius)
    # 4 片叶片
    blade_count = 4
    for i in range(blade_count):
        blade_angle = angle + i * (360.0 / blade_count)
        rad = math.radians(blade_angle)
        # 叶片为一个椭圆形扇区，这里用多边形近似
        points = [(center_x, center_y)]
        blade_len = radius - 10
        blade_width = 0.35  # 弧度宽度的一半
        steps = 8
        for s in range(steps + 1):
            a = rad - blade_width + (2 * blade_width) * s / steps
            points.append((center_x + blade_len * math.cos(a),
                           center_y + blade_len * math.sin(a)))
        pygame.draw.polygon(screen, color, points)
    # 中心圆点
    pygame.draw.circle(screen, (200, 210, 230), (center_x, center_y), 25)
    pygame.draw.circle(screen, (40, 50, 70), (center_x, center_y), 25, 3)

def draw_fan_panel():
    """绘制右侧风扇动画区"""
    panel_x = 900
    panel_y = 200
    panel_w = 920
    panel_h = 560
    # 面板背景（半透明）
    draw_rounded_rect_alpha((50, 60, 85), (panel_x, panel_y, panel_w, panel_h), alpha=160, border_radius=20)
    pygame.draw.rect(screen, (100, 130, 180), (panel_x, panel_y, panel_w, panel_h), 3, border_radius=20)

    center_x = panel_x + panel_w // 2
    center_y = panel_y + panel_h // 2 + 20
    radius = 200

    config = GEAR_CONFIG[current_gear]
    # 风扇叶片颜色随档位变化
    draw_fan(center_x, center_y, radius, fan_angle, config["color"])

    # 风扇区下方提示文字
    tip = font_small.render('风扇转速随档位变化', True, (180, 200, 230))
    screen.blit(tip, (center_x - tip.get_width() // 2, panel_y + panel_h - 60))

def draw_buttons():
    """绘制底部 5 个档位触摸按钮"""
    for i, config in enumerate(GEAR_CONFIG):
        rect = get_button_rect(i)
        # 按钮颜色：当前档位高亮
        if i == current_gear:
            fill_color = config["color"]
            fill_alpha = 200  # 当前档位更不透明
            text_color = (255, 255, 255)
            border_color = (255, 255, 255)
            border_width = 6
        else:
            fill_color = (60, 70, 95)
            fill_alpha = 140
            text_color = config["color"]
            border_color = config["color"]
            border_width = 3
        # 按钮（半透明填充）
        draw_rounded_rect_alpha(fill_color, rect, alpha=fill_alpha, border_radius=15)
        pygame.draw.rect(screen, border_color, rect, border_width, border_radius=15)
        # 档位名称
        name_text = font_mid.render(config["name"], True, text_color)
        screen.blit(name_text, (rect.x + (rect.w - name_text.get_width()) // 2, rect.y + 30))
        # 档位描述
        label_text = font_small.render(config["label"], True, text_color)
        screen.blit(label_text, (rect.x + (rect.w - label_text.get_width()) // 2, rect.y + 110))

def draw_hint():
    """绘制底部操作提示"""
    hint = font_small.render('触摸下方按钮切换风扇档位    p1口舵机指示档位    ma口电机驱动风扇',
                             True, (150, 170, 200))
    screen.blit(hint, ((1920 - hint.get_width()) // 2, 1030))

def draw_exit_button():
    """绘制右上角退出按钮"""
    # 按钮（半透明填充）
    draw_rounded_rect_alpha((180, 60, 60), EXIT_BUTTON_RECT, alpha=180, border_radius=15)
    pygame.draw.rect(screen, (255, 255, 255), EXIT_BUTTON_RECT, 4, border_radius=15)
    exit_text = font_mid.render('退出', True, (255, 255, 255))
    screen.blit(exit_text, (EXIT_BUTTON_RECT.x + (EXIT_BUTTON_RECT.w - exit_text.get_width()) // 2,
                            EXIT_BUTTON_RECT.y + (EXIT_BUTTON_RECT.h - exit_text.get_height()) // 2))

# ==================== 主循环 ====================
clock = pygame.time.Clock()
running = True

if _board_isstarted:
    try:
        while running:
            # ---------- 事件处理 ----------
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # 触摸/鼠标按下，判断点击了哪个按钮
                    pos = event.pos
                    # 优先检测退出按钮
                    if EXIT_BUTTON_RECT.collidepoint(pos):
                        running = False
                    else:
                        # 检测档位按钮
                        for i in range(len(GEAR_CONFIG)):
                            if get_button_rect(i).collidepoint(pos):
                                apply_gear(i)
                                break
                elif event.type == pygame.KEYDOWN:
                    # 数字键 0-4 快捷切换档位
                    if event.unicode in ('0', '1', '2', '3', '4'):
                        apply_gear(int(event.unicode))

            # ---------- 风扇动画角度更新 ----------
            # 档位越高，叶片旋转越快；0档停止
            config = GEAR_CONFIG[current_gear]
            fan_angle = (fan_angle + config["motor"] / 1023.0 * 20.0) % 360

            # ---------- 绘制界面 ----------
            draw_background()
            draw_title()
            draw_info_panel()
            draw_fan_panel()
            draw_buttons()
            draw_hint()
            draw_exit_button()
            pygame.display.flip()

            clock.tick(60)  # 60 FPS
    except:
        print('出现异常')
    finally:
        # 退出前关闭风扇和复位舵机
        try:
            board.motor_MA(0)
            board.servo(SERVO_PIN, 0)
        except:
            pass
        pygame.quit()
else:
    print('扩展板连接失败，程序退出')
