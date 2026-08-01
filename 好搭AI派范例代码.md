# 好搭AI派范例代码集

> 本文档收录了好搭AI派（ESP32 + pygame）平台的范例代码，涵盖外设接口、扩展模块、音频处理、语音AI、AI视觉算法、物联网、OpenCV 和 Pygame 八大模块，共计 65 个示例。

## 目录

- [1.外设接口使用](#1外设接口使用)
  - [1.GPIO-读取数字值](#1外设接口使用-1gpio-读取数字值)
  - [2.GPIO-写入数字值](#1外设接口使用-2gpio-写入数字值)
  - [3.ADC-读取模拟值](#1外设接口使用-3adc-读取模拟值)
  - [4.PWM-写入模拟值](#1外设接口使用-4pwm-写入模拟值)
  - [5.串口打印](#1外设接口使用-5串口打印)
- [2.扩展模块使用](#2扩展模块使用)
  - [1.DHT11温湿度传感器](#2扩展模块使用-1dht11温湿度传感器)
  - [2.DS18B20温度传感器](#2扩展模块使用-2ds18b20温度传感器)
  - [3.超声波传感器](#2扩展模块使用-3超声波传感器)
  - [4.RGB灯](#2扩展模块使用-4rgb灯)
  - [5.舵机](#2扩展模块使用-5舵机)
  - [6.电机](#2扩展模块使用-6电机)
  - [7.按键控制灯光](#2扩展模块使用-7按键控制灯光)
  - [8.温控风扇](#2扩展模块使用-8温控风扇)
- [3.音频处理](#3音频处理)
  - [1.录音5s](#3音频处理-1录音5s)
  - [2.音频播放](#3音频处理-2音频播放)
  - [3.手动控制录音](#3音频处理-3手动控制录音)
  - [4.按键控制录音](#3音频处理-4按键控制录音)
  - [5.音频录制并播放](#3音频处理-5音频录制并播放)
- [4.语音AI](#4语音ai)
  - [1.语音合成](#4语音ai-1语音合成)
  - [2.语音识别](#4语音ai-2语音识别)
  - [3.文本翻译](#4语音ai-3文本翻译)
  - [4.大模型对话一](#4语音ai-4大模型对话一)
  - [5.大模型对话二](#4语音ai-5大模型对话二)
  - [6.大模型对话三](#4语音ai-6大模型对话三)
  - [7.按键大模型对话](#4语音ai-7按键大模型对话)
- [5.AI视觉算法](#5ai视觉算法)
  - [01.标签识别](#5ai视觉算法-01标签识别)
  - [02.标签识别-超市自助收银](#5ai视觉算法-02标签识别-超市自助收银)
  - [03.二维码识别](#5ai视觉算法-03二维码识别)
  - [04.颜色识别](#5ai视觉算法-04颜色识别)
  - [05.颜色识别-自动分拣](#5ai视觉算法-05颜色识别-自动分拣)
  - [06.色块识别](#5ai视觉算法-06色块识别)
  - [07.黑线检测](#5ai视觉算法-07黑线检测)
  - [08.人脸学习1](#5ai视觉算法-08人脸学习1)
  - [09.人脸学习2](#5ai视觉算法-09人脸学习2)
  - [10.人脸识别](#5ai视觉算法-10人脸识别)
  - [11.物体识别学习](#5ai视觉算法-11物体识别学习)
  - [12.物体识别](#5ai视觉算法-12物体识别)
  - [13.车牌识别](#5ai视觉算法-13车牌识别)
  - [14.车牌识别并播放](#5ai视觉算法-14车牌识别并播放)
  - [15.图像分类](#5ai视觉算法-15图像分类)
  - [16.人流计数](#5ai视觉算法-16人流计数)
  - [17.目标检测](#5ai视觉算法-17目标检测)
  - [18.姿态检测](#5ai视觉算法-18姿态检测)
  - [19.文字识别-便捷](#5ai视觉算法-19文字识别-便捷)
  - [20.文字识别-OCR识别器](#5ai视觉算法-20文字识别-ocr识别器)
  - [21.实时文字识别](#5ai视觉算法-21实时文字识别)
- [6.物联网](#6物联网)
  - [1.连接Wi-Fi](#6物联网-1连接wi-fi)
  - [2.MQTT发布](#6物联网-2mqtt发布)
  - [3.MQTT订阅](#6物联网-3mqtt订阅)
- [7.opencv](#7opencv)
  - [1.图片显示与处理](#7opencv-1图片显示与处理)
  - [2.同时显示两张图片](#7opencv-2同时显示两张图片)
  - [3.显示带文字图片](#7opencv-3显示带文字图片)
  - [4.播放视频](#7opencv-4播放视频)
  - [5.播放30s视频](#7opencv-5播放30s视频)
  - [6.播放视频与音频](#7opencv-6播放视频与音频)
- [8.pygame](#8pygame)
  - [1.窗口显示](#8pygame-1窗口显示)
  - [2.表面绘制](#8pygame-2表面绘制)
  - [3.事件检测](#8pygame-3事件检测)
  - [4.字体显示](#8pygame-4字体显示)
  - [5.显示图片](#8pygame-5显示图片)
  - [6.图形绘制](#8pygame-6图形绘制)
  - [7.播放声音](#8pygame-7播放声音)
  - [8.定时器](#8pygame-8定时器)
  - [9.音乐播放](#8pygame-9音乐播放)
  - [10.音乐播放-按钮](#8pygame-10音乐播放-按钮)

---

## 1.外设接口使用

> GPIO 数字/模拟读写、PWM 输出、串口打印等基础外设操作

### 1.外设接口使用 1.GPIO-读取数字值

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        while True:
            IO1_dig = board.digitalRead((GPIO_IO_01))
            print(('当前数字值：' + str(IO1_dig)))
            time.sleep(0.1)
    except:
        print('出现异常')
```

### 1.外设接口使用 2.GPIO-写入数字值

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        while True:
            board.digitalWrite((GPIO_IO_02), (1))
            time.sleep(1)
            board.digitalWrite((GPIO_IO_02), (0))
            time.sleep(1)
    except:
        print('出现异常')
```

### 1.外设接口使用 3.ADC-读取模拟值

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

print('该范例以读取亮度传感器的数值作为模拟值')
if _board_isstarted:
    try:
        while True:
            light = board.analogRead((ADC_IO_02))
            print(('当前亮度值：' + str(light)))
            time.sleep(0.1)
    except:
        print('出现异常')
```

### 1.外设接口使用 4.PWM-写入模拟值

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

print('IO2接小风扇模块，通过PWM调整风扇风速')
if _board_isstarted:
    try:
        while True:
            board.analogWrite((GPIO_IO_02), 1023)
            print('高风速')
            time.sleep(2)
            board.analogWrite((GPIO_IO_02), 512)
            print('低风速')
            time.sleep(2)
            board.analogWrite((GPIO_IO_02), 0)
            print('关闭风扇')
            time.sleep(2)
    except:
        print('出现异常')
```

### 1.外设接口使用 5.串口打印

```python
print('Hello，world！')
print('Hello', 'haohaodada')
```

---

## 2.扩展模块使用

> DHT11 温湿度、DS18B20 温度、超声波、RGB 灯、舵机、电机等扩展模块

### 2.扩展模块使用 1.DHT11温湿度传感器

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        while True:
            temp = board.dhtReadTemperature((GPIO_IO_01))
            print(('当前温度：' + str(temp)))
            time.sleep(2)
            hum = board.dhtReadHumidity((GPIO_IO_01))
            print(('当前湿度：' + str(hum)))
            time.sleep(2)
    except:
        print('出现异常')
```

### 2.扩展模块使用 2.DS18B20温度传感器

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        while True:
            DS18B20 = board.ds18b20Read((GPIO_IO_01))
            print(('当前DS18B20温度：' + str(DS18B20)))
            time.sleep(2)
    except:
        print('出现异常')
```

### 2.扩展模块使用 3.超声波传感器

```python
from ESP32 import *
import math
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

print('超声波传感器接IO1，LED接IO2')
print('超声波传感器数值=-1，说明超出传感器读取范围')
if _board_isstarted:
    try:
        while True:
            ult = math.floor(board.ultrasonicRead((GPIO_IO_01)))
            print((('超声波传感器：' + str(ult)) + 'cm'))
            if ult > 20:
                board.digitalWrite((GPIO_IO_02), (1))
            else:
                board.digitalWrite((GPIO_IO_02), (0))
            time.sleep(1)
    except:
        print('出现异常')
```

### 2.扩展模块使用 4.RGB灯

```python
from ESP32 import *
import time

"""描述该功能...
"""
def wheel(pos):
    global tup3, tup2, tup1, i, color
    if pos < 0 or pos > 255:
        pos %= 256
    if pos < 85:
        tup1= (255 - pos * 3, pos * 3, 0)
        return tup1
    elif pos < 170:
        pos -= 85
        tup2= (0, 255 - pos * 3, pos * 3)
        return tup2
    else:
        pos -= 170
        tup3= (pos * 3, 0, 255 - pos * 3)
        return tup3

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    board.ws2812Init((GPIO_IO_01), 40)
    print('设置颜色')
    board.ws2812Write((GPIO_IO_01), 0, 255, 0, 0)
    board.ws2812Write((GPIO_IO_01), 1, 0, 255, 0)
    board.ws2812Write((GPIO_IO_01), 2, 0, 0, 255)
    board.ws2812Write((GPIO_IO_01), 3, 255, 255, 0)
    time.sleep(2)
    print('关闭所有灯')
    board.ws2812Write((GPIO_IO_01), 255, 0, 0, 0)
    time.sleep(1)
    print('进入流光溢彩模式')
    try:
        i = 0
        while True:
            color = wheel(i % 256)
            board.ws2812Write((GPIO_IO_01), 255, color[0], color[1], color[2])
            i += 2
            time.sleep(0.05)
    except:
        print('出现异常，关闭灯光')
        board.ws2812Write((GPIO_IO_01), 255, 0, 0, 0)
```

### 2.扩展模块使用 5.舵机

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        while True:
            board.servo((GPIO_IO_01), 180)
            time.sleep(2)
            board.servo((GPIO_IO_01), 90)
            time.sleep(2)
            board.servo((GPIO_IO_01), 0)
            time.sleep(2)
            board.servo((GPIO_IO_01), 90)
            time.sleep(2)
    except:
        print('出现异常')
```

### 2.扩展模块使用 6.电机

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        while True:
            board.motor_MA(500)
            board.motor_MB(500)
            time.sleep(2)
            board.motor_MA(0)
            board.motor_MB(0)
            time.sleep(2)
            board.motor_MA(500)
            board.motor_MB(0)
            time.sleep(2)
            board.motor_MA(0)
            board.motor_MB(500)
            time.sleep(2)
    except:
        print('出现异常')
```

### 2.扩展模块使用 7.按键控制灯光

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

if _board_isstarted:
    try:
        while True:
            anjian = board.digitalRead((GPIO_IO_01))
            if anjian == 1:
                board.digitalWrite((GPIO_IO_02), (1))
            else:
                board.digitalWrite((GPIO_IO_02), (0))
            time.sleep(0.01)
    except:
        print('出现异常')
else:
    print('连接失败，程序退出')
```

### 2.扩展模块使用 8.温控风扇

```python
from ESP32 import *
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

print('请在IO1引脚连接DHT11，IO2引脚连接小风扇')
if _board_isstarted:
    try:
        while True:
            temp = board.dhtReadTemperature((GPIO_IO_01))
            print(('当前温度：' + str(temp)))
            if temp > 26:
                board.analogWrite((GPIO_IO_02), 800)
                print('打开风扇')
            else:
                board.analogWrite((GPIO_IO_02), 0)
                print('关闭风扇')
            time.sleep(2)
    except:
        print('出现异常')
```

---

## 3.音频处理

> 录音、播放、手动控制录音、按键控制录音等音频操作

### 3.音频处理 1.录音5s

```python
from audio_recorder import AudioRecorder

print('=== 示例1: 录制5秒音频 ===')
print('采样率可以取8、16、44.1、48、96kHz')
print('声道数1表示单声道，2表示立体声')
print('适合预设时长的录音场景，完全自动化，指令开始即录音')
recorder = AudioRecorder(sample_rate=16000, channels=1)
recorder.set_output_dir('recordings')
file_path = recorder.record_fixed_duration(duration=5, filename='test_5sec.wav')
if file_path:
    print('录音成功！文件保存在：', file_path)
else:
    print('录音失败！')
```

### 3.音频处理 2.音频播放

```python
from audio_player import AudioPlayer

player = AudioPlayer()
success = player.play_file('recordings/test_5sec.wav')
```

### 3.音频处理 3.手动控制录音

```python
from audio_recorder import AudioRecorder
import time

print('=== 示例2: 手动控制录音 ===')
print('采样率可以取8、16、44.1、48、96kHz')
print('声道数1表示单声道，2表示立体声')
print('适合灵活时间的录音场景')
recorder = AudioRecorder(sample_rate=22050, channels=2)
recorder.set_output_dir('recordings')
# 这条指令开始录音
recorder.start_recording(device=None)
print('录音10秒...')
# 这里只是范例需要设置10s，核心是开始录音和结束录音两条指令，录音时间手动控制
time.sleep(10)
# 这条指令结束录音
audio_data = recorder.stop_recording()
if audio_data is not None:
    file_path = recorder.save_audio(audio_data, filename='manual_recording.wav')
    if file_path:
        print('录音成功！文件保存在：', file_path)
    else:
        print('录音失败！')
```

### 3.音频处理 4.按键控制录音

```python
from ESP32 import *
from audio_player import AudioPlayer
from audio_recorder import AudioRecorder
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

"""描述该功能...
"""
def _E6_8C_89_E9_94_AE_E5_88_A4_E6_96_AD():
    global flagB, flagA, recorder, player, audio_data, IO1_dig, file_path
    IO1_dig = board.digitalRead((GPIO_IO_01))
    if IO1_dig == 1:
        flagB = 0
        if flagA == 0:
            flagA = 1
            # 这条指令开始录音
            recorder.start_recording(device=None)
    elif IO1_dig == 0:
        if flagA == 1:
            flagA = 0
            if flagB == 0:
                flagB = 1
                # 这条指令结束录音
                audio_data = recorder.stop_recording()
                _E5_BD_95_E9_9F_B3_E6_96_87_E4_BB_B6_E4_BF_9D_E5_AD_98()
    time.sleep(0.01)

"""描述该功能...
"""
def _E5_BD_95_E9_9F_B3_E6_96_87_E4_BB_B6_E4_BF_9D_E5_AD_98():
    global flagB, flagA, recorder, player, audio_data, IO1_dig, file_path
    if audio_data is not None:
        file_path = recorder.save_audio(audio_data, filename='test_button.wav')
        if file_path:
            print('录音成功！文件保存在：', file_path)
        else:
            print('录音失败！')

print('按键按键开始录音，松开按键结束录音')
if _board_isstarted:
    try:
        player = AudioPlayer()
        recorder = AudioRecorder(sample_rate=16000, channels=1)
        flagA = 0
        flagB = 0
        while True:
            _E6_8C_89_E9_94_AE_E5_88_A4_E6_96_AD()
    except:
        print('出现异常')
```

### 3.音频处理 5.音频录制并播放

```python
from audio_recorder import AudioRecorder
from audio_player import AudioPlayer

print('=== 示例3: 录音控制并播放 ===')
print('录制30s二泉映月，采样率使用48khz，声道使用立体声')
recorder = AudioRecorder(sample_rate=48000, channels=2)
recorder.set_output_dir('recordings')
player = AudioPlayer()
try:
    print('开始录制《二泉映月》')
    file_path = recorder.record_fixed_duration(duration=30, filename='erquan.wav')
    if file_path:
        print('✓ 二泉映月录音已保存到：', file_path)
        print('开始播放二泉映月录音...')
        success = player.play_file(file_path)
        if success:
            print('✓ 播放完成！')
        else:
            print('✗ 播放失败')
    else:
        print('录音失败！')
except:
    print('出现错误')
finally:
    player.cleanup()
    print('程序结束')
```

---

## 4.语音AI

> 语音合成(TTS)、语音识别(ASR)、文本翻译、大模型对话(LLM)

### 4.语音AI 1.语音合成

```python
from audio_player import AudioPlayer
from voice_api import VoiceAPI

print('=== TTS合成功能测试 ===')
print('请输入你已经通过认证的好搭用户名和密码')
player = AudioPlayer()
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
# 需修改用户名和密码
token_result = voice_api.get_token('username', 'password')
if not token_result:
    print('❌ 认证失败，API初始化错误')
print('✅ 认证成功，开始功能测试')
audio_data = voice_api.tts_synthesize('欢迎使用智能博物系统', 'recordings/output.wav')
if audio_data:
    success = player.play_file('recordings/output.wav')
    if success:
        print('✅ 播放完成')
    else:
        print('❌ 播放失败')
else:
    print('❌ 语音合成失败')
```

### 4.语音AI 2.语音识别

```python
from audio_player import AudioPlayer
from voice_api import VoiceAPI

print('===语音识别功能测试 ===')
print('使用语音识别将音频转化成文字并打印出来')
print('这里的音频使用提前录音好的文件，文件名为test_5sec.wav')
print('具体可以先运行范例2.录音与播放-1.录音5s')
print('请输入你已经通过认证的好搭用户名和密码')
player = AudioPlayer()
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
# 需修改用户名和密码
token_result = voice_api.get_token('username', 'password')
if not token_result:
    print('❌ 认证失败，API初始化错误')
print('✅ 认证成功，开始功能测试')
recognition_text = voice_api.voice_recognition(('recordings/' + 'test_5sec.wav'))
if recognition_text:
    print(('语音识别内容：' + recognition_text))
```

### 4.语音AI 3.文本翻译

```python
from audio_player import AudioPlayer
from voice_api import VoiceAPI

print('=== 文本翻译功能测试 ===')
print('请输入你已经通过认证的好搭用户名和密码')
player = AudioPlayer()
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
# 需修改用户名和密码
token_result = voice_api.get_token('username', 'password')
if not token_result:
    print('❌ 认证失败，API初始化错误')
print('✅ 认证成功，开始功能测试，可以修改chinese_text')
chinese_text = '欢迎使用智能博物系统'
english_text = voice_api.translate_english(chinese_text)
print('✅ 开始播报中文')
audio_data = voice_api.tts_synthesize(chinese_text, 'recordings/ch_text.wav')
if audio_data:
    success = player.play_file('recordings/ch_text.wav')
print('✅ 开始播报英文')
audio_data = voice_api.tts_synthesize(english_text, 'recordings/en_text.wav')
if audio_data:
    success = player.play_file('recordings/en_text.wav')
```

### 4.语音AI 4.大模型对话一

```python
from voice_api import VoiceAPI

print('=== LLM大模型功能测试 ===')
print('该测试输入使用固定文本，输出使用串口打印')
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token('username', 'password')
if not token_result:
    print('❌ 认证失败，无法测试LLM功能')
print('✅ 认证成功，开始测试LLM功能')
test_questions = ['你好', '什么是人工智能？', '请介绍智能博物馆的功能', '如何提高语音识别准确率？', '总结一下深度学习的优点']
# 列表中的内容依次赋值给变量question
for question in test_questions:
    print('测试问题：', question)
    try:
        llm_answer = voice_api.llm_chat(question)
        if llm_answer is not None:
            if llm_answer:
                print('✅ 成功 - 回答长度：', len(llm_answer), ' 字符')
                print('回答：', llm_answer)
            else:
                print('⚠️ 成功但回答为空')
        else:
            print('❌ 调用失败')
    except:
        print('❌ 异常')
    print(('-' * 50))
print('=== LLM测试完成 ===')
```

### 4.语音AI 5.大模型对话二

```python
from voice_api import VoiceAPI
from audio_player import AudioPlayer
from audio_recorder import AudioRecorder

print('=== LLM大模型功能测试2 ===')
print('该测试输入使用语音识别，输出使用串口打印')
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token('username', 'password')
if not token_result:
    print('❌ 认证失败，无法测试LLM功能')
print('✅ 认证成功，开始测试LLM功能')
player = AudioPlayer()
recorder = AudioRecorder(sample_rate=16000, channels=1)
file_path = recorder.record_fixed_duration(duration=8, filename='LLM2.wav')
# 如果录音完成
if file_path:
    print('录音成功！文件保存在：', file_path)
else:
    print('录音失败！')
recognition_text = voice_api.voice_recognition(('recordings/' + 'LLM2.wav'))
if recognition_text:
    question = recognition_text
    print('测试问题：', question)
try:
    llm_answer = voice_api.llm_chat(question)
    if llm_answer is not None:
        if llm_answer:
            print('✅ 成功 - 回答长度：', len(llm_answer), ' 字符')
            print('回答：', llm_answer)
        else:
            print('⚠️ 成功但回答为空')
    else:
        print('❌ 调用失败')
except:
    print('❌ 异常')
```

### 4.语音AI 6.大模型对话三

```python
from voice_api import VoiceAPI
from audio_player import AudioPlayer
from audio_recorder import AudioRecorder

print('=== LLM大模型功能测试3 ===')
print('该测试输入使用语音识别，输出并播报')
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token('username', 'password')
if not token_result:
    print('❌ 认证失败，无法测试LLM功能')
print('✅ 认证成功，开始测试LLM功能')
player = AudioPlayer()
recorder = AudioRecorder(sample_rate=16000, channels=1)
file_path = recorder.record_fixed_duration(duration=8, filename='LLM2.wav')
# 如果录音完成
if file_path:
    print('录音成功！文件保存在：', file_path)
else:
    print('录音失败！')
recognition_text = voice_api.voice_recognition(('recordings/' + 'LLM2.wav'))
if recognition_text:
    question = recognition_text
    print('测试问题：', question)
try:
    llm_answer = voice_api.llm_chat(question)
    if llm_answer is not None:
        if llm_answer:
            audio_data = voice_api.tts_synthesize(llm_answer, ('recordings/' + 'answer.wav'))
        if audio_data:
            success = player.play_file(('recordings/' + 'answer.wav'))
            if success:
                print('回答：', llm_answer)
    else:
        print('❌ 调用失败')
except:
    print('❌ 异常')
player.cleanup()
```

### 4.语音AI 7.按键大模型对话

```python
from voice_api import VoiceAPI
from ESP32 import *
from audio_player import AudioPlayer
from audio_recorder import AudioRecorder
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

"""描述该功能...
"""
def _E6_8C_89_E9_94_AE_E5_88_A4_E6_96_AD():
    global flagB, flagA, recorder, player, token_result, voice_api, audio_data, IO1_dig, file_path, question, recognition_text, llm_answer, success, audio_dataa
    IO1_dig = board.digitalRead((GPIO_IO_01))
    if IO1_dig == 1:
        flagB = 0
        if flagA == 0:
            flagA = 1
            # 这条指令开始录音
            recorder.start_recording(device=None)
    elif IO1_dig == 0:
        if flagA == 1:
            flagA = 0
            if flagB == 0:
                flagB = 1
                # 这条指令结束录音
                audio_data = recorder.stop_recording()
                _E5_BD_95_E9_9F_B3_E6_96_87_E4_BB_B6_E4_BF_9D_E5_AD_98()
                _E8_AF_AD_E9_9F_B3_E8_AF_86_E5_88_AB()
                _E5_A4_A7_E6_A8_A1_E5_9E_8B_E6_8F_90_E9_97_AE()
    time.sleep(0.01)

"""描述该功能...
"""
def _E5_BD_95_E9_9F_B3_E6_96_87_E4_BB_B6_E4_BF_9D_E5_AD_98():
    global flagB, flagA, recorder, player, token_result, voice_api, audio_data, IO1_dig, file_path, question, recognition_text, llm_answer, success, audio_dataa
    if audio_data is not None:
        file_path = recorder.save_audio(audio_data, filename='LLM4.wav')
        if file_path:
            print('录音成功！文件保存在：', file_path)
        else:
            print('录音失败！')

"""描述该功能...
"""
def _E8_AF_AD_E9_9F_B3_E8_AF_86_E5_88_AB():
    global flagB, flagA, recorder, player, token_result, voice_api, audio_data, IO1_dig, file_path, question, recognition_text, llm_answer, success, audio_dataa
    recognition_text = voice_api.voice_recognition(('recordings/' + 'LLM4.wav'))
    if recognition_text:
        question = recognition_text
        print('测试问题：', question)

"""描述该功能...
"""
def _E5_A4_A7_E6_A8_A1_E5_9E_8B_E6_8F_90_E9_97_AE():
    global flagB, flagA, recorder, player, token_result, voice_api, audio_data, IO1_dig, file_path, question, recognition_text, llm_answer, success, audio_dataa
    try:
        llm_answer = voice_api.llm_chat((question + '，请尽量简短回答'))
        if llm_answer is not None:
            if llm_answer:
                audio_dataa = voice_api.tts_synthesize(llm_answer, ('recordings/' + 'answer.wav'))
            if audio_dataa:
                success = player.play_file(('recordings/' + 'answer.wav'))
                if success:
                    print('回答：', llm_answer)
        else:
            print('❌ 调用失败')
    except:
        print('❌ 异常')
    player.cleanup()

print('=== LLM大模型功能测试3 ===')
print('该测试输入使用语音识别，输出并播报')
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
# 需修改用户名和密码
token_result = voice_api.get_token('username', 'password')
if not token_result:
    print('❌ 认证失败，无法测试LLM功能')
print('✅ 认证成功，开始测试LLM功能')
if _board_isstarted:
    try:
        player = AudioPlayer()
        recorder = AudioRecorder(sample_rate=16000, channels=1)
        flagA = 0
        flagB = 0
        while True:
            _E6_8C_89_E9_94_AE_E5_88_A4_E6_96_AD()
    except:
        print('出现异常')
```

---

## 5.AI视觉算法

> 标签识别、二维码、颜色识别、人脸识别、物体识别、车牌识别、文字识别(OCR)、目标检测、姿态检测等

### 5.AI视觉算法 01.标签识别

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_apriltag = True
vision_system._init_detectors()
print("apriltag 算法已启用")
while True:
    vision_system.process_one_frame()
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_apriltag_count() > 0:
        print(('ID：' + str((vision_system.result_accessor.get_apriltag_id(0)))))
        time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 02.标签识别-超市自助收银

```python
from audio_player import AudioPlayer
from voice_api import VoiceAPI
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

player = AudioPlayer()
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token('username', 'password')
audio_data = voice_api.tts_synthesize('扫码成功，请将付款二维码对准摄像头', 'recordings/saoma.wav')
# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_apriltag = True
vision_system._init_detectors()
print("apriltag 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_apriltag_count() > 0:
        _E6_A0_87_E7_AD_BEID = vision_system.result_accessor.get_apriltag_id(0)
        if _E6_A0_87_E7_AD_BEID == 27:
            print('这是可乐')
            shangpin_audio = voice_api.tts_synthesize('可乐，3元', 'recordings/shangpin.wav')
            shangpin = player.play_file('recordings/shangpin.wav')
            success = player.play_file('recordings/saoma.wav')
            _E6_A0_87_E7_AD_BEID = -1
        elif _E6_A0_87_E7_AD_BEID == 0:
            print('这是薯片')
            shangpin_audio = voice_api.tts_synthesize('薯片，8元', 'recordings/shangpin.wav')
            shangpin = player.play_file('recordings/shangpin.wav')
            success = player.play_file('recordings/saoma.wav')
            _E6_A0_87_E7_AD_BEID = -1
    time.sleep(0.5)
vision_system.cleanup()
print("系统资源已清理")
player.cleanup()

vision_system.result_accessor.refresh_results()
```

### 5.AI视觉算法 03.二维码识别

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_qr_code = True
vision_system._init_detectors()
print("qr_code 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_qr_code_count() > 0:
        print((vision_system.result_accessor.get_qr_code_content(0)))
        print((vision_system.result_accessor.get_qr_code_type(0)))
        time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 04.颜色识别

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_color_recognition = True
vision_system._init_detectors()
print("color_recognition 算法已启用")
vision_system.detection_config.color_recognition_regions.append((300, 200, 400, 400))
print("颜色识别区域已添加: (300, 200, 400, 400)")
vision_system.detection_config.color_recognition_regions.append((800, 200, 400, 400))
print("颜色识别区域已添加: (800, 200, 400, 400)")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_color_recognition_count() > 0:
        print('第一个区域信息如下：')
        print((vision_system.result_accessor.get_color_recognition_color(0)))
        print((vision_system.result_accessor.get_color_recognition_rgb(0)))
        print((vision_system.result_accessor.get_color_recognition_name(0)))
        print('第二个区域信息如下：')
        print((vision_system.result_accessor.get_color_recognition_color(1)))
        print((vision_system.result_accessor.get_color_recognition_rgb(1)))
        print((vision_system.result_accessor.get_color_recognition_color(1)))
        time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 05.颜色识别-自动分拣

```python
from ESP32 import *
from camera_vision_system_v3 import create_vision_system_v3
import math
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

if _board_isstarted:
    try:
        board.servo((GPIO_IO_01), 0)
        # 视觉系统已初始化 (简化版)
        print("视觉系统初始化完成")
        if vision_system.open_camera():
            print("摄像头已打开")
        vision_system.detection_config.enable_color_recognition = True
        vision_system._init_detectors()
        print("color_recognition 算法已启用")
        vision_system.detection_config.color_recognition_regions.append((300, 200, 400, 400))
        print("颜色识别区域已添加: (300, 200, 400, 400)")
        vision_system.threaded_system.start_background_detection(show_preview=True)
        while True:
            vision_system.result_accessor.refresh_results()
            if vision_system.result_accessor.get_color_recognition_count() > 0:
                print(('RGB:' + str((vision_system.result_accessor.get_color_recognition_rgb(0)))))
                RGBtup = vision_system.result_accessor.get_color_recognition_rgb(0)
                R = int(RGBtup[0])
                G = int(RGBtup[1])
                B = int(RGBtup[2])
                L = math.floor(0.299 * R + (0.587 * G + 0.114 * B))
                print(('L:' + str(L)))
                if L >= 80 and L <= 100:
                    print('绿色，合格')
                elif L >= 40 and L <= 60:
                    print('蓝色，不合格')
                    board.servo((GPIO_IO_01), 90)
                    time.sleep(1)
                    board.servo((GPIO_IO_01), 0)
                else:
                    print('未知，待检测')
                    board.servo((GPIO_IO_01), 90)
                    time.sleep(1)
                    board.servo((GPIO_IO_01), 0)
                time.sleep(2)
        vision_system.cleanup()
        print("系统资源已清理")
    except:
        pass
```

### 5.AI视觉算法 06.色块识别

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_color_block = True
vision_system._init_detectors()
print("color_block 算法已启用")
while True:
    vision_system.process_one_frame()
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_color_block_count() > 0:
        print((vision_system.result_accessor.get_color_block_color(0)))
        print((vision_system.result_accessor.get_color_block_position(0)))
        print((vision_system.result_accessor.get_color_block_center(0)))
        print((vision_system.result_accessor.get_color_block_area(0)))
        time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 07.黑线检测

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_black_line = True
vision_system._init_detectors()
print("black_line 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_line_count() > 0:
        print((vision_system.result_accessor.get_line_angle(0)))
        print((vision_system.result_accessor.get_line_length(0)))
        print((vision_system.result_accessor.get_line_endpoints(0)))
        time.sleep(0.3)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 08.人脸学习1

```python
from ESP32 import *
from camera_vision_system_v3 import create_vision_system_v3
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

if _board_isstarted:
    try:
        # 视觉系统已初始化 (简化版)
        print("视觉系统初始化完成")
        if vision_system.open_camera():
            print("摄像头已打开")
        vision_system.detection_config.enable_face_recognition = True
        vision_system._init_detectors()
        print("face_recognition 算法已启用")
        vision_system.threaded_system.start_background_detection(show_preview=True)
        while True:
            vision_system.result_accessor.refresh_results()
            if board.digitalRead((GPIO_IO_01)) == 0:
                _E4_BA_BA_E8_84_B8_E4_BF_A1_E6_81_AF = vision_system.learn_new_face()
                print(_E4_BA_BA_E8_84_B8_E4_BF_A1_E6_81_AF)
                time.sleep(1)
            time.sleep(1)
    except:
        pass
```

### 5.AI视觉算法 09.人脸学习2

```python
from camera_vision_system_v3 import create_vision_system_v3
import cv2

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_face_recognition = True
vision_system._init_detectors()
print("face_recognition 算法已启用")
_E4_BA_BA_E8_84_B8_E4_BF_A1_E6_81_AF = vision_system.learn_new_face(frame=(cv2.imread('images/Jack.jpg')))
print(_E4_BA_BA_E8_84_B8_E4_BF_A1_E6_81_AF)
```

### 5.AI视觉算法 10.人脸识别

```python
from audio_player import AudioPlayer
from voice_api import VoiceAPI
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)
"""描述该功能...
"""
def _E6_89_93_E5_8D_B0_E5_B9_B6_E6_92_AD_E6_8A_A5():
    global _E5_A7_93_E5_90_8D, _E4_BA_BA_E8_84_B8ID, voice_api, token_result, player, success, audio_data, _E7_BD_AE_E4_BF_A1_E5_BA_A6
    _E7_BD_AE_E4_BF_A1_E5_BA_A6 = round(vision_system.result_accessor.get_face_confidence(), 3)
    audio_data = voice_api.tts_synthesize(((('这是' + _E5_A7_93_E5_90_8D) + '，置信度为') + str(_E7_BD_AE_E4_BF_A1_E5_BA_A6)), 'recordings/renlian.wav')
    if audio_data:
        success = player.play_file('recordings/renlian.wav')

player = AudioPlayer()
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token('username', 'password')
# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_face_recognition = True
vision_system._init_detectors()
print("face_recognition 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_face_count() > 0:
        _E4_BA_BA_E8_84_B8ID = vision_system.result_accessor.get_face_id()
        if _E4_BA_BA_E8_84_B8ID == 28:
            _E5_A7_93_E5_90_8D = '张女士'
            _E6_89_93_E5_8D_B0_E5_B9_B6_E6_92_AD_E6_8A_A5()
        elif _E4_BA_BA_E8_84_B8ID == 29:
            _E5_A7_93_E5_90_8D = '王先生'
            _E6_89_93_E5_8D_B0_E5_B9_B6_E6_92_AD_E6_8A_A5()
        elif _E4_BA_BA_E8_84_B8ID == 27:
            _E5_A7_93_E5_90_8D = '陈先生'
            _E6_89_93_E5_8D_B0_E5_B9_B6_E6_92_AD_E6_8A_A5()
        else:
            print('未知人脸')
    time.sleep(1)
```

### 5.AI视觉算法 11.物体识别学习

```python
from ESP32 import *
from camera_vision_system_v3 import create_vision_system_v3
import cv2
import time

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

if _board_isstarted:
    try:
        # 视觉系统已初始化 (简化版)
        print("视觉系统初始化完成")
        if vision_system.open_camera():
            print("摄像头已打开")
        vision_system.detection_config.enable_object_recognition = True
        vision_system._init_detectors()
        print("object_recognition 算法已启用")
        vision_system.add_object_recognition_class(frame=(cv2.imread('images/shuibei.jpg')), class_name='水杯')
        vision_system.threaded_system.start_background_detection(show_preview=True)
        while True:
            vision_system.result_accessor.refresh_results()
            if board.digitalRead((GPIO_IO_01)) == 1:
                _E7_89_A9_E4_BD_93_E4_BF_A1_E6_81_AF = vision_system.add_object_recognition_sample(class_name='水杯')
                print(_E7_89_A9_E4_BD_93_E4_BF_A1_E6_81_AF)
                time.sleep(1)
            time.sleep(1)
    except:
        pass
```

### 5.AI视觉算法 12.物体识别

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_object_recognition = True
vision_system._init_detectors()
print("object_recognition 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    print((vision_system.result_accessor.get_object_recognition_class_name()))
    print((vision_system.result_accessor.get_object_recognition_confidence()))
    _E7_89_A9_E4_BD_93_E8_AF_86_E5_88_AB_E5_90_8D_E7_A7_B0 = vision_system.result_accessor.get_object_recognition_class_name()
    if _E7_89_A9_E4_BD_93_E8_AF_86_E5_88_AB_E5_90_8D_E7_A7_B0 == '水杯':
        print('识别成功，这是水杯')
    else:
        print('未学习物体')
    time.sleep(1)
```

### 5.AI视觉算法 13.车牌识别

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_plate_recognition = True
vision_system._init_detectors()
print("plate_recognition 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_plate_recognition_count() > 0:
        print((vision_system.result_accessor.get_plate_recognition_text(0)))
        print((vision_system.result_accessor.get_plate_recognition_confidence(0)))
    time.sleep(1)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 14.车牌识别并播放

```python
from voice_api import VoiceAPI
from audio_player import AudioPlayer
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token('username', 'password')
player = AudioPlayer()
# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_plate_recognition = True
vision_system._init_detectors()
print("plate_recognition 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_plate_recognition_count() > 0:
        print((vision_system.result_accessor.get_plate_recognition_text(0)))
        print((vision_system.result_accessor.get_plate_recognition_confidence(0)))
        audio_data = voice_api.tts_synthesize(('车牌号码' + (vision_system.result_accessor.get_plate_recognition_text(0))), 'recordings/chepai.wav')
        if audio_data:
            success = player.play_file('recordings/chepai.wav')
    time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 15.图像分类

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_image_classification = True
vision_system._init_detectors()
print("image_classification 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_image_classification_count() > 0:
        print((vision_system.result_accessor.get_image_classification_class_name(0)))
        print((vision_system.result_accessor.get_image_classification_confidence(0)))
        time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 16.人流计数

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_people_counter = True
vision_system._init_detectors()
print("people_counter 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    print(('进入人数：' + str((vision_system.result_accessor.get_people_counter_in()))))
    print(('离开人数：' + str((vision_system.result_accessor.get_people_counter_out()))))
    time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 17.目标检测

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_object_detection = True
vision_system._init_detectors()
print("object_detection 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_object_detection_count() > 0:
        print((vision_system.result_accessor.get_object_detection_class_name(0)))
        print((vision_system.result_accessor.get_object_detection_confidence(0)))
        print((vision_system.result_accessor.get_object_detection_bbox(0)))
        time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 18.姿态检测

```python
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.detection_config.enable_pose_detection = True
vision_system._init_detectors()
print("pose_detection 算法已启用")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    if vision_system.result_accessor.get_pose_detection_count() > 0:
        print((vision_system.result_accessor.get_pose_detection_box(0)))
        print((vision_system.result_accessor.get_pose_detection_confidence(0)))
        print((vision_system.result_accessor.get_pose_detection_keypoints(0)))
        time.sleep(2)
vision_system.cleanup()
print("系统资源已清理")
```

### 5.AI视觉算法 19.文字识别-便捷

```python
from text_recognition import recognize_image_text

recognized_text = recognize_image_text('images/text_rec.png', confidence_threshold=0.5)
print(recognized_text)
```

### 5.AI视觉算法 20.文字识别-OCR识别器

```python
from text_recognition import TextRecognizer

ocr_recognizer = TextRecognizer()
ocr_result = ocr_recognizer.recognize_text('images/text_rec.png', confidence_threshold=0.5)
success_status = ocr_result["success"]
if success_status:
    text_content = ocr_result["text"]
    print(text_content)
ocr_recognizer.cleanup()
```

### 5.AI视觉算法 21.实时文字识别

```python
from text_recognition import TextRecognizer
from voice_api import VoiceAPI
from audio_player import AudioPlayer
from camera_vision_system_v3 import create_vision_system_v3
import time

vision_system = create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)

ocr_recognizer = TextRecognizer()
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
token_result = voice_api.get_token('username', 'password')
player = AudioPlayer()
# 视觉系统已初始化 (简化版)
print("视觉系统初始化完成")
if vision_system.open_camera():
    print("摄像头已打开")
vision_system.threaded_system.start_background_detection(show_preview=True)
while True:
    vision_system.result_accessor.refresh_results()
    ocr_camera = vision_system.capture_frame()
    ocr_result = ocr_recognizer.recognize_text(ocr_camera, confidence_threshold=0.5)
    success_status = ocr_result["success"]
    if success_status:
        text_content = ocr_result["text"]
        print(('当前文字：' + text_content))
        audio_data = voice_api.tts_synthesize(('当前文字：' + text_content), 'recordings/ocr.wav')
        if audio_data:
            success = player.play_file('recordings/ocr.wav')
    time.sleep(2)
```

---

## 6.物联网

> Wi-Fi 连接、MQTT 发布与订阅

### 6.物联网 1.连接Wi-Fi

```python
from wifi_manager import connect_to_wifi
from wifi_manager import get_ip_address

def main():
    while not connect_to_wifi('username', 'password'):
        print('正在连接WiFi，请稍等')
    print('已成功连接到WiFi')
    print((get_ip_address('wlan0')["ip"]))

if __name__ == "__main__":
    main()
```

### 6.物联网 2.MQTT发布

```python
from paho.mqtt import client as mqtt_client
from ESP32 import *
import json
import time

def on_connect(client, userdata, flags, rc, properties=None):
    pass

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode('utf-8', errors='replace')
    qos = msg.qos
    _msg = {"topic": topic, "payload": payload, "qos": qos}

def connect_mqtt():
    temp_client = mqtt_client.Client(
        client_id='haoda',
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
        clean_session=False
    )
    temp_client.username_pw_set('', '')
    if 1883 == 8883:
        temp_client.tls_set()  # 启用TLS加密
    try:
        temp_client.connect('192.168.2.155', 1883, keepalive=60)
        return temp_client
    except Exception as e:
        print(f"连接过程出错: {str(e)}")
        return None

board = ESP32()
_board_isstarted = board.start()
if not _board_isstarted:
    raise Exception("扩展板连接异常，请检查硬件")

def publish(client, topic, payload):
    if not client:
        return

    if isinstance(payload, dict):
        try:
            payload = json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            print(f"转换错误: {e}")
    else:
        payload = str(payload)

    result, mid = client.publish(topic, payload)
    if result == 0:
        print(f"发送成功: 消息 {payload} 到主题 {topic}")
    else:
        print(f"发送失败到主题 {topic}，错误代码: {result}")


global_client = connect_mqtt()
global_client.on_message = on_message
global_client.on_connect = on_connect
if _board_isstarted:
    try:
        while True:
            if board.digitalRead((GPIO_IO_01)) == 1:

                publish(global_client, 'topic/rgb', 'on')
                time.sleep(1)
    except:
        pass
```

### 6.物联网 3.MQTT订阅

```python
from paho.mqtt import client as mqtt_client

def on_connect(client, userdata, flags, rc, properties=None):
    pass

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode('utf-8', errors='replace')
    qos = msg.qos
    _msg = {"topic": topic, "payload": payload, "qos": qos}

    if topic_matches_sub("topic/rgb", topic):
        client = client
        userdata = userdata
        msg = msg

        print((_msg))
        _E4_B8_BB_E9_A2_98 = _msg['topic']
        _E6_B6_88_E6_81_AF_E5_86_85_E5_AE_B9 = _msg['payload']
        print(('主题：' + _E4_B8_BB_E9_A2_98))
        print(('消息内容：' + _E6_B6_88_E6_81_AF_E5_86_85_E5_AE_B9))

def connect_mqtt():
    temp_client = mqtt_client.Client(
        client_id='haoda',
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
        clean_session=False
    )
    temp_client.username_pw_set('', '')
    if 1883 == 8883:
        temp_client.tls_set()  # 启用TLS加密
    try:
        temp_client.connect('192.168.2.155', 1883, keepalive=60)
        return temp_client
    except Exception as e:
        print(f"连接过程出错: {str(e)}")
        return None

def subscribe(client, topic):
    if not client:
        return
    result, mid = client.subscribe(topic)
    if result == 0:
        print(f"订阅成功: {topic}")
    else:
        print(f"订阅主题 {topic} 失败，错误代码: {result}")

def topic_matches_sub(subscription, topic):
    """
    实现 MQTT 主题匹配
    :param subscription: 订阅主题（可能含通配符 + 或 #）
    :param topic: 消息主题（不含通配符）
    :return: 是否匹配（True/False）
    """
    # 处理多级通配符 #（必须是最后一个字符）
    if subscription.endswith("#"):
        # # 单独作为主题时，匹配所有主题
        if subscription == "#":
            return True
        # 检查 # 前是否为 /（如 sensor/# 合法，sensor# 不合法）
        if not subscription.endswith("/#"):
            return False
        # 去掉末尾的 /#，匹配前缀
        prefix = subscription[:-2]
        return topic == prefix or topic.startswith(prefix + "/")

    # 分割订阅主题和消息主题为层级列表
    sub_levels = subscription.split("/")
    topic_levels = topic.split("/")

    # 层级数量不同，直接不匹配
    if len(sub_levels) != len(topic_levels):
        return False

    # 逐个层级匹配（处理单级通配符 +）
    for sub_level, topic_level in zip(sub_levels, topic_levels):
        if sub_level == "+":
            continue  # + 匹配任意单层级
        if sub_level != topic_level:
            return False  # 层级不匹配

    return True  # 所有层级匹配


global_client = connect_mqtt()
global_client.on_message = on_message
global_client.on_connect = on_connect

subscribe(global_client, 'topic/rgb')
while True:

    global_client.loop_start()
```

---

## 7.opencv

> 图片显示与处理、视频播放、视频与音频同步播放

### 7.opencv 1.图片显示与处理

```python
import cv2

print('请点击软件右上角文件管理，在总目录下的文件夹images中导入图片example.jpeg')
print('程序可以下载到需要的文件夹')
print('opencv支持png、jpg、jpeg、bmp等常见图片格式')
img = cv2.imread('images/example.jpeg',cv2.IMREAD_UNCHANGED)
cv2.namedWindow('tupian', cv2.WINDOW_NORMAL)
cv2.resizeWindow('tupian', 1920, 1080)
cv2.imshow('tupian',img)
if cv2.waitKey(5000) & 0xff:
    pass
cv2.destroyAllWindows()
mytup = img.shape
print(('行数：' + str(mytup[0])))
print(('列数：' + str(mytup[1])))
print(('通道数：' + str(mytup[2])))
outimg = cv2.rotate(img,cv2.ROTATE_180)
outimg = outimg[:,200:600]
outimg = outimg[100:500,:]
cv2.imshow('tupian',outimg)
if cv2.waitKey(5000) & 0xff:
    pass
cv2.destroyAllWindows()
```

### 7.opencv 2.同时显示两张图片

```python
import cv2

print('如果需要修改图片，请点击软件右上角文件管理，将图片导入到images文件夹中')
print('opencv支持png、jpg、jpeg、bmp等常见图片格式')
img1 = cv2.imread('images/example.jpeg',cv2.IMREAD_UNCHANGED)
img2 = cv2.imread('images/example2.png',cv2.IMREAD_UNCHANGED)
cv2.namedWindow('图片一', cv2.WINDOW_NORMAL)
cv2.namedWindow('图片二', cv2.WINDOW_NORMAL)
cv2.resizeWindow('图片一', 720, 360)
cv2.moveWindow('图片一', 150, 50)
cv2.resizeWindow('图片二', 720, 360)
cv2.moveWindow('图片二', 950, 50)
cv2.imshow('图片一',img1)
cv2.imshow('图片二',img2)
while True:
    key = cv2.waitKey(1) & 0xff
    if key == ord('q'):
        break
cv2.destroyAllWindows()
```

### 7.opencv 3.显示带文字图片

```python
import cv2

img = cv2.imread('images/example.jpeg',cv2.IMREAD_UNCHANGED)
cv2.namedWindow('tupian', cv2.WINDOW_NORMAL)
cv2.resizeWindow('tupian', 1280, 720)
cv2.moveWindow('tupian', 50, 50)
cv2.putText(img, 'hello', (120, 60), cv2.FONT_HERSHEY_COMPLEX, 1, (255,51,51), 1)
cv2.circle(img, (60, 60),50, (255,51,51), 2, cv2.FILLED)
cv2.imshow('tupian',img)
while True:
    if cv2.waitKey(1) & 0xff == ord('q'):
        break
cv2.destroyAllWindows()
```

### 7.opencv 4.播放视频

```python
import cv2

print('请点击软件右上角文件管理，在总目录下的文件夹videos中导入视频example.mp4')
print('程序可以下载到需要的文件夹')
print('若没有videos文件夹，请使用右上角文件管理新建')
vd = cv2.VideoCapture()
vd.open('videos/example.mp4')
if not vd.isOpened():
    print('无法打开视频')
else:
    cv2.namedWindow('video player', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('video player', 1080, 720)
    while True:
        ret,grab = vd.read()
        if not ret:
            break
        cv2.imshow('video player',grab)
        if cv2.waitKey(25) & 0xff == ord('q'):
            break
    vd.release()
    cv2.destroyAllWindows()
```

### 7.opencv 5.播放30s视频

```python
import cv2
import time

print('请点击软件右上角文件管理，在总目录下的文件夹videos中导入视频example.mp4')
print('程序可以下载到需要的文件夹')
print('若没有videos文件夹，请使用右上角文件管理新建')
vd = cv2.VideoCapture()
vd.open('videos/example.mp4')
if not vd.isOpened():
    print('无法打开视频')
else:
    cv2.namedWindow('video player', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('video player', 1080, 720)
    start_time = time.time()
    while True:
        ret,grab = vd.read()
        if not ret:
            break
        cv2.imshow('video player',grab)
        if time.time() - start_time > 30 or cv2.waitKey(25) & 0xff == ord('q'):
            break
    vd.release()
    cv2.destroyAllWindows()
```

### 7.opencv 6.播放视频与音频

```python
from voice_api import VoiceAPI
from audio_player import AudioPlayer
from audio_recorder import AudioRecorder
import pygame
import cv2
import time

"""描述该功能...
"""
def _E6_92_AD_E6_94_BE_E8_A7_86_E9_A2_91(videoname, playername, playtime):
    global recorder, player, token_result, voice_api, vd, sound1, start_time, grab, ret, success, audio_data, _E6_96_87_E6_9C_AC_E5_86_85_E5_AE_B9
    pygame.init()
    pygame.mixer.init()
    sound1 = pygame.mixer.Sound(('recordings/' + playername))
    vd = cv2.VideoCapture()
    vd.open(('videos/' + videoname))
    if not vd.isOpened():
        print('无法打开视频')
    else:
        cv2.namedWindow('video player', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('video player', 1620, 1080)
        start_time = time.time()
        sound1.play()
        while True:
            ret,grab = vd.read()
            if not ret:
                break
            cv2.imshow('video player',grab)
            if time.time() - start_time > playtime or cv2.waitKey(25) & 0xff == ord('q'):
                break
        sound1.stop()
        vd.release()
        cv2.destroyAllWindows()

"""描述该功能...
"""
def _E8_AF_AD_E9_9F_B3_E5_90_88_E6_88_90(_E6_96_87_E6_9C_AC_E5_86_85_E5_AE_B9):
    global recorder, player, token_result, voice_api, vd, sound1, playtime, start_time, grab, ret, videoname, playername, success, audio_data
    audio_data = voice_api.tts_synthesize(_E6_96_87_E6_9C_AC_E5_86_85_E5_AE_B9, 'zhishi.wav')
    if audio_data:
        success = player.play_file('zhishi.wav')
        if success:
            print('✅ 播放完成')
    player.cleanup()

print('请在videos文件夹中导入视频文件')
print('请在recordings文件夹中导入音频文件')
print('请修改视频和音频的名称')
print('请输入通过认证的用户名和密码')
voice_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
# 需修改用户名和密码
token_result = voice_api.get_token('username', 'password')
if not token_result:
    print('❌ 认证失败，无法测试LLM功能')
player = AudioPlayer()
recorder = AudioRecorder(sample_rate=16000, channels=1)
_E8_AF_AD_E9_9F_B3_E5_90_88_E6_88_90('马上为您播放')
_E6_92_AD_E6_94_BE_E8_A7_86_E9_A2_91('example.mp4', 'example.mp3', 30)
```

---

## 8.pygame

> 窗口、表面绘制、事件检测、字体、图片、图形、声音、定时器、音乐播放

### 8.pygame 1.窗口显示

```python
import pygame

pygame.init()
window1 = pygame.display.set_mode(size=(800,600), flags=0, depth=0)
pygame.display.set_caption('Pygame基础窗口')
while True:
    pygame.display.flip()
pygame.quit()
```

### 8.pygame 2.表面绘制

```python
import pygame

pygame.init()
window1 = pygame.display.set_mode(size=(800,600), flags=0, depth=0)
s1 = pygame.Surface(size=(400, 600))
s2 = pygame.Surface(size=(400, 600))
s1.fill((255,0,0))
s2.fill((51,102,255))
while True:
    window1.blit(s1,(0,0))
    window1.blit(s2,(400,0))
    pygame.display.flip()
pygame.quit()
```

### 8.pygame 3.事件检测

```python
import pygame

pygame.init()
window1 = pygame.display.set_mode(size=(800,600), flags=0, depth=0)
while True:
    for var in (pygame.event.get()):
        if var.type == pygame.ACTIVEEVENT:
            print('窗口被激活')
        elif var.type == pygame.MOUSEBUTTONDOWN:
            print('鼠标被按下')
        elif var.type == pygame.QUIT:
            print('窗口被关闭')
            pygame.quit()
            break
    pygame.display.flip()
```

### 8.pygame 4.字体显示

```python
import pygame

pygame.init()
pygame.font.init()
window1 = pygame.display.set_mode(size=(800,600), flags=0, depth=0)
font1 = pygame.font.SysFont('freesansbold.ttf', 32)
font2 = pygame.font.Font('/home/cxdz/jupyter/assets/simfang.ttf', 64)
text1 = font1.render('hello',True,(255,0,0,1))
text2 = font2.render('你好',True,(255,0,0,1))
while True:
    window1.blit(text1,(200,200))
    window1.blit(text2,(400,200))
    pygame.display.flip()
```

### 8.pygame 5.显示图片

```python
import pygame

pygame.init()
window1 = pygame.display.set_mode(size=(800,600), flags=0, depth=0)
while True:
    window1.blit((pygame.image.load('images/example.jpeg')),(1,1))
    pygame.display.flip()
pygame.quit()
```

### 8.pygame 6.图形绘制

```python
import pygame

pygame.init()
window1 = pygame.display.set_mode(size=(800,600), flags=0, depth=0)
s1 = pygame.Surface(size=(800, 600))
s1.fill((255,0,0))
while True:
    window1.blit(s1,(0,0))
    pygame.draw.rect(window1,(51,102,255),(50,50,400,300),1)
    pygame.draw.circle(window1, (102,0,204), (100,100), 50, 1)
    pygame.draw.line(window1, (51,204,0), (100,100), (200,200), 1)
    pygame.draw.line(window1, (51,204,0), (100,100), (300,100), 1)
    pygame.display.flip()
pygame.quit()
```

### 8.pygame 7.播放声音

```python
import pygame

pygame.init()
pygame.mixer.init()
sound1 = pygame.mixer.Sound('recordings/example.mp3')
sound1.set_volume(50 / 100)
while True:
    try:
        sound1.play()
    except:
        pass
```

### 8.pygame 8.定时器

```python
import pygame

pygame.init()
pygame.mixer.init()
sound1 = pygame.mixer.Sound('recordings/example.mp3')
sound1.set_volume(50 / 100)
sound1.play()
a = pygame.time.wait(5000)
sound1.stop()
```

### 8.pygame 9.音乐播放

```python
import pygame
import time

pygame.init()
pygame.mixer.music.load('recordings/example.mp3')
pygame.mixer.music.set_volume(50 / 100)
pygame.mixer.music.play()
time.sleep(5)
pygame.mixer.music.stop()
```

### 8.pygame 10.音乐播放-按钮

```python
import pygame

pygame.init()
window1 = pygame.display.set_mode(size=(800,600), flags=0, depth=0)
pygame.font.init()
font1 = pygame.font.Font('/home/cxdz/jupyter/assets/simfang.ttf', 48)
pygame.mixer.music.load('recordings/example.mp3')
pygame.mixer.music.set_volume(50 / 100)
s1 = pygame.Surface(size=(400, 600))
s2 = pygame.Surface(size=(400, 600))
rect1 = pygame.Surface(size=(120, 80))
rect2 = pygame.Surface(size=(120, 80))
s1.fill((255,0,0))
s2.fill((51,102,255))
rect1.fill((51,204,0))
rect2.fill((51,204,0))
text1 = font1.render('播放',True,(153,0,0,0))
text2 = font1.render('停止',True,(153,0,0,0))
while True:
    window1.blit(s1,(0,0))
    window1.blit(s2,(400,0))
    window1.blit(rect1,(140,440))
    window1.blit(rect2,(540,440))
    window1.blit(text1,(152,456))
    window1.blit(text2,(552,456))
    pygame.display.flip()
    for var in (pygame.event.get()):
        if var.type == pygame.ACTIVEEVENT:
            print('窗口被激活')
        elif var.type == pygame.MOUSEBUTTONDOWN:
            print('鼠标被按下')
            _E9_BC_A0_E6_A0_87_E5_9D_90_E6_A0_87 = var.pos
            x = _E9_BC_A0_E6_A0_87_E5_9D_90_E6_A0_87[0]
            y = _E9_BC_A0_E6_A0_87_E5_9D_90_E6_A0_87[1]
            if x >= 140 and x <= 260 and y >= 440 and y <= 520:
                print('音乐播放')
                if not pygame.mixer.music.get_busy():
                    pygame.mixer.music.play()
            elif x >= 540 and x <= 660 and y >= 440 and y <= 520:
                print('音乐停止')
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
        elif var.type == pygame.QUIT:
            print('窗口被关闭')
            pygame.quit()
            break
```

---
