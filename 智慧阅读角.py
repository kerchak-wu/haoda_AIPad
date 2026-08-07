# -*- coding: utf-8 -*-
"""
智慧阅读角 - 好搭AI派案例
=====================================
功能说明：
1. 欢迎屏幕：显示"欢迎来到智慧阅读角，享受阅读时光"，含退出按钮
2. 人体红外传感器(io1)检测到人 → 切换到功能选择界面
3. 功能选择：馆藏图书 / 图书视频 / 智能导读，30秒无人自动返回欢迎屏
4. 馆藏图书：点击书名，语音+文字介绍图书
5. 图书视频：西游记/三国演义/红楼梦，点击播放对应视频
6. 智能导读：USB摄像头OCR识别文字 + 按住说话语音对话
7. RGB灯带(io2, 11灯珠)：全程配合不同灯效

硬件接线：
- IO1: 人体红外传感器(PIR)
- IO2: WS2812 RGB灯带(11灯珠，需接上拉扩展模块)
- USB摄像头: 用于智能导读OCR识别

依赖文件：
- videos/1.mp4  videos/2.mp4  videos/3.mp4 (图书视频)
"""

# ====== 注意：text_recognition 必须最先导入，否则OCR会报错 ======
from text_recognition import TextRecognizer

import pygame
import cv2
import time
import math
import threading
import os
import logging
import queue
import wave
import struct
import numpy as np
from datetime import datetime

from ESP32 import *
from voice_api import VoiceAPI
from audio_player import AudioPlayer
from audio_recorder import AudioRecorder
from camera_vision_system_v3 import create_vision_system_v3

# ==================== 配置参数 ====================
WINDOW_W, WINDOW_H = 1920, 1080
PIR_PIN = GPIO_IO_01
RGB_PIN = GPIO_IO_02
NUM_LEDS = 11
MENU_TIMEOUT = 30  # 功能选择界面无人操作超时(秒)

# 语音AI认证信息（请替换为自己的好好搭搭账号密码）
VOICE_USERNAME = '用户名'
VOICE_PASSWORD = '密码'
