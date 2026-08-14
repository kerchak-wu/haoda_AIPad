# 非视觉官方库功能探测程序
# 在好搭AI派设备上运行：python3 探测_非视觉官方库.py
# 作用：反射枚举 ESP32（含 GPIO/ADC 常量）、voice_api、audio_recorder、
#       audio_player、text_recognition、Line_Sensor 六个官方库的全部
#       模块成员、类方法签名、常量列表，不实际操作硬件（仅实例化/读取签名）。
# 输出：同时打印到控制台并追加写入 logs/探测_非视觉官方库_YYYYMMDD.log

import os
import sys
import inspect
import traceback
from datetime import datetime

# ---------- 日志输出配置 ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

PROGRAM_NAME = "探测_非视觉官方库"
TODAY_STR = datetime.now().strftime("%Y%m%d")
LOG_FILE = os.path.join(LOG_DIR, f"{PROGRAM_NAME}_{TODAY_STR}.log")


class Tee:
    """同时写入控制台与日志文件（追加模式）。"""
    def __init__(self, log_path):
        self._console = sys.stdout
        self._file = open(log_path, "a", encoding="utf-8")

    def write(self, msg):
        self._console.write(msg)
        self._file.write(msg)
        self._file.flush()

    def flush(self):
        self._console.flush()
        self._file.flush()

    def close(self):
        try:
            self._file.close()
        except Exception:
            pass


_tee = Tee(LOG_FILE)
sys.stdout = _tee


def log_section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def safe_import(module_name):
    """安全导入模块，失败返回 None 并打印错误。"""
    try:
        mod = __import__(module_name)
        print(f"  [成功] import {module_name}")
        return mod
    except Exception as e:
        print(f"  [失败] import {module_name}: {type(e).__name__}: {e}")
        return None


def list_members(obj, label):
    """列出 obj 的公共成员与私有成员。"""
    public = [m for m in dir(obj) if not m.startswith("_")]
    private = [m for m in dir(obj) if m.startswith("_") and not m.startswith("__")]
    print(f"{label} 公共成员（{len(public)} 个）：")
    print("  ", public)
    if private:
        print(f"{label} 私有成员（_ 开头，{len(private)} 个）：")
        print("  ", private)
    return public, private


def dump_callable_signatures(obj, member_list, prefix=""):
    """对 member_list 中的可调用成员逐一打印签名。"""
    for name in member_list:
        attr = getattr(obj, name, None)
        if attr is None:
            continue
        if callable(attr):
            try:
                sig = inspect.signature(attr)
                print(f"  {prefix}{name}{sig}")
            except (ValueError, TypeError):
                print(f"  {prefix}{name}(...)  [签名不可获取]")
        else:
            # 属性：打印值（如果可字符串化）
            try:
                val_repr = repr(attr)
                if len(val_repr) > 200:
                    val_repr = val_repr[:197] + "..."
                print(f"  {prefix}{name} = {val_repr}  (type={type(attr).__name__})")
            except Exception:
                print(f"  {prefix}{name}  [属性，不可打印]")


def dump_class_from_module(mod, class_name, try_init=False, init_kwargs=None):
    """从模块中找到类名，枚举其成员与方法签名；可选实例化后再枚举实例属性。"""
    if mod is None:
        print(f"  跳过 {class_name}：模块未导入")
        return None, None
    cls = getattr(mod, class_name, None)
    if cls is None:
        print(f"  模块中不存在类 {class_name}")
        return None, None
    print(f"  找到类 {class_name}，类型={type(cls)}")
    cls_members = [m for m in dir(cls) if not m.startswith("__")]
    dump_callable_signatures(cls, cls_members, prefix=f"{class_name}.")

    instance = None
    if try_init:
        print()
        print(f"  尝试实例化 {class_name} ...")
        try:
            kwargs = init_kwargs or {}
            instance = cls(**kwargs)
            print(f"    [成功] 实例: {instance}")
            # 枚举实例独有属性（不在类中的）
            inst_attrs = [a for a in dir(instance)
                          if not a.startswith("__") and not hasattr(cls, a)]
            if inst_attrs:
                print(f"    实例新增属性（类中无）: {inst_attrs}")
                dump_callable_signatures(instance, inst_attrs, prefix=f"  {class_name}实例.")
        except Exception as e:
            print(f"    [失败] 实例化错误: {type(e).__name__}: {e}")
    return cls, instance


# ---------- 探测开始 ----------
print(f"\n[探测开始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
print(f"[日志文件] {LOG_FILE}")

# ================================================================
# 第1步：ESP32 模块 + GPIO/ADC 常量
# ================================================================
log_section("第1步：ESP32 模块成员 + GPIO/ADC/PWM 全局常量枚举")
ESP32_mod = safe_import("ESP32")
if ESP32_mod is not None:
    list_members(ESP32_mod, "ESP32 模块")

    print()
    print("  --- 反射枚举 ESP32 模块中的大写常量（GPIO/ADC/PWM 等） ---")
    constants = {}
    for name in dir(ESP32_mod):
        if name.startswith("__"):
            continue
        val = getattr(ESP32_mod, name)
        if not callable(val) and (name.isupper() or name.startswith(("GPIO_", "ADC_", "PWM_", "I2C_", "SPI_", "UART_"))):
            try:
                constants[name] = val
            except Exception:
                pass
    # 分组打印
    groups = {}
    for name, val in constants.items():
        key = "其他常量"
        for prefix in ["GPIO_IO_", "ADC_IO_", "PWM_IO_", "I2C_", "SPI_", "UART_", "BOARD_", "LED_", "BUTTON_", "PIN_"]:
            if name.startswith(prefix):
                key = prefix + "*"
                break
        groups.setdefault(key, []).append((name, val))
    for key in sorted(groups.keys()):
        print(f"\n    【{key}】共 {len(groups[key])} 个：")
        for name, val in sorted(groups[key]):
            print(f"      {name} = {val}")

    print()
    print("  --- 尝试 import * 后的全局命名空间（模拟使用者场景） ---")
    try:
        before = set(globals().keys())
        exec("from ESP32 import *", globals())
        after = set(globals().keys())
        injected = sorted(after - before - {"before", "after"})
        print(f"    from ESP32 import * 注入了 {len(injected)} 个名称：")
        print("     ", injected)
    except Exception as e:
        print(f"    [失败] from ESP32 import *: {type(e).__name__}: {e}")

# ================================================================
# 第2步：ESP32 类实例方法签名（不调用 board.start()）
# ================================================================
log_section("第2步：ESP32 类的全部方法签名（不启动硬件）")
if ESP32_mod is not None:
    try:
        esp_cls, esp_inst = dump_class_from_module(
            ESP32_mod, "ESP32",
            try_init=True, init_kwargs={}
        )
        if esp_inst is not None:
            # 进一步检查 Line_Sensor / board 等属性是否挂在实例上
            sub_attrs = ["Line_Sensor", "board", "ws2812", "dht", "ds18b20",
                         "ultrasonic", "motor", "servo", "adc", "gpio", "pwm"]
            print()
            print("  检查 ESP32 实例子对象：")
            for name in sub_attrs:
                attr = getattr(esp_inst, name, None)
                if attr is None:
                    # 也检查模块级
                    attr = getattr(ESP32_mod, name, None)
                    print(f"    模块.{name}: {'存在' if attr is not None else '不存在'}")
                else:
                    print(f"    实例.{name}: 存在，类型={type(attr).__name__}")
                    sub_members = [m for m in dir(attr) if not m.startswith("_")]
                    dump_callable_signatures(attr, sub_members[:40], prefix=f"      {name}.")
                    if len(sub_members) > 40:
                        print(f"        ... 另有 {len(sub_members)-40} 个成员省略")
    except Exception:
        print(f"  ESP32 类探测异常：\n{traceback.format_exc()}")

# ================================================================
# 第3步：Line_Sensor 模块（如果是独立模块）
# ================================================================
log_section("第3步：Line_Sensor 模块探测（若为独立模块）")
LS_mod = safe_import("Line_Sensor")
if LS_mod is not None:
    list_members(LS_mod, "Line_Sensor 模块")
    # 尝试找 Line_Sensor 类
    dump_class_from_module(LS_mod, "Line_Sensor", try_init=False)
    # 其他候选类名
    for alt in ["LineSensor", "line_sensor", "LineSensorArray"]:
        if hasattr(LS_mod, alt):
            print(f"  发现备选类名 {alt}")
            dump_class_from_module(LS_mod, alt, try_init=False)

# ================================================================
# 第4步：voice_api（VoiceAPI 类 + 顶层方法）
# ================================================================
log_section("第4步：voice_api 模块 + VoiceAPI 类完整签名")
voice_mod = safe_import("voice_api")
if voice_mod is not None:
    list_members(voice_mod, "voice_api 模块")
    # 先枚举顶层函数（不挂在类上的）
    top_funcs = [m for m in dir(voice_mod)
                 if not m.startswith("_") and callable(getattr(voice_mod, m, None))
                 and not inspect.isclass(getattr(voice_mod, m, None))]
    if top_funcs:
        print()
        print("  voice_api 顶层函数：")
        dump_callable_signatures(voice_mod, top_funcs, prefix="  ")
    dump_class_from_module(voice_mod, "VoiceAPI", try_init=False)
    # 候选管理接口检查
    print()
    print("  VoiceAPI 候选管理接口（文档未记录项）：")
    vapi_cls = getattr(voice_mod, "VoiceAPI", None)
    candidates = [
        "get_token", "refresh_token", "check_token_valid", "set_app_key",
        "set_app_secret", "get_quota_info", "get_qps_limit", "tts_synthesize",
        "tts_synthesize_to_file", "tts_get_voices", "voice_recognition",
        "voice_recognition_file", "stream_asr_start", "stream_asr_stop",
        "translate_english", "translate_chinese", "translate_to",
        "llm_chat", "llm_chat_stream", "llm_set_model", "llm_set_system_prompt",
        "set_proxy", "set_timeout", "get_last_error", "close",
    ]
    if vapi_cls:
        for m in candidates:
            exists = hasattr(vapi_cls, m)
            print(f"    VoiceAPI.{m}: {'存在' if exists else '不存在'}")
            if exists:
                try:
                    sig = inspect.signature(getattr(vapi_cls, m))
                    print(f"      签名: {sig}")
                except (ValueError, TypeError):
                    print(f"      签名不可获取")

# ================================================================
# 第5步：audio_recorder.AudioRecorder
# ================================================================
log_section("第5步：audio_recorder 模块 + AudioRecorder 类")
rec_mod = safe_import("audio_recorder")
if rec_mod is not None:
    list_members(rec_mod, "audio_recorder 模块")
    dump_class_from_module(rec_mod, "AudioRecorder", try_init=False)
    # 额外检查：__init__ 签名，sample_rate/channels 默认值
    cls = getattr(rec_mod, "AudioRecorder", None)
    if cls is not None and hasattr(cls, "__init__"):
        try:
            sig = inspect.signature(cls.__init__)
            print(f"  AudioRecorder.__init__{sig}")
        except (ValueError, TypeError):
            pass
    print()
    print("  AudioRecorder 候选管理接口：")
    candidates = [
        "set_output_dir", "set_sample_rate", "set_channels", "set_format",
        "record_fixed_duration", "start_recording", "stop_recording",
        "save_audio", "get_audio_path", "get_audio_data", "pause_recording",
        "resume_recording", "is_recording", "get_duration", "cleanup", "close",
    ]
    if cls:
        for m in candidates:
            exists = hasattr(cls, m)
            print(f"    AudioRecorder.{m}: {'存在' if exists else '不存在'}")

# ================================================================
# 第6步：audio_player.AudioPlayer
# ================================================================
log_section("第6步：audio_player 模块 + AudioPlayer 类")
play_mod = safe_import("audio_player")
if play_mod is not None:
    list_members(play_mod, "audio_player 模块")
    dump_class_from_module(play_mod, "AudioPlayer", try_init=False)
    print()
    print("  AudioPlayer 候选控制接口：")
    cls = getattr(play_mod, "AudioPlayer", None)
    candidates = [
        "play_file", "play_stream", "pause", "resume", "stop",
        "set_volume", "get_volume", "set_position", "get_position",
        "get_duration", "is_playing", "is_paused", "seek",
        "set_speed", "set_pitch", "get_metadata", "set_loop",
        "cleanup", "close",
    ]
    if cls:
        for m in candidates:
            exists = hasattr(cls, m)
            print(f"    AudioPlayer.{m}: {'存在' if exists else '不存在'}")

# ================================================================
# 第7步：text_recognition (PaddleOCR)
# ================================================================
log_section("第7步：text_recognition 模块 + TextRecognizer 类")
ocr_mod = safe_import("text_recognition")
if ocr_mod is not None:
    list_members(ocr_mod, "text_recognition 模块")
    dump_class_from_module(ocr_mod, "TextRecognizer", try_init=False)
    print()
    print("  TextRecognizer 候选接口：")
    cls = getattr(ocr_mod, "TextRecognizer", None)
    candidates = [
        "__init__", "recognize_text", "recognize_image_text",
        "recognize_image", "recognize_file", "set_language", "set_region",
        "set_detection_threshold", "enable_angle_classify",
        "get_last_result", "get_inference_time", "set_model_path",
        "get_supported_languages", "release", "close",
    ]
    if cls:
        for m in candidates:
            exists = hasattr(cls, m)
            print(f"    TextRecognizer.{m}: {'存在' if exists else '不存在'}")
            if exists and m != "__init__":
                try:
                    sig = inspect.signature(getattr(cls, m))
                    print(f"      签名: {sig}")
                except (ValueError, TypeError):
                    pass

# ================================================================
# 第8步：六个库的所有大写常量再汇总（方便查阅）
# ================================================================
log_section("第8步：各模块大写常量汇总表")
modules = [
    ("ESP32", ESP32_mod),
    ("Line_Sensor", LS_mod),
    ("voice_api", voice_mod),
    ("audio_recorder", rec_mod),
    ("audio_player", play_mod),
    ("text_recognition", ocr_mod),
]
for mod_name, mod in modules:
    if mod is None:
        print(f"\n  【{mod_name}】（模块未导入，跳过）")
        continue
    consts = {}
    for name in dir(mod):
        if name.startswith("__"):
            continue
        val = getattr(mod, name)
        if name.isupper() and not callable(val):
            try:
                consts[name] = val
            except Exception:
                pass
    print(f"\n  【{mod_name}】共 {len(consts)} 个大写常量：")
    if consts:
        for name in sorted(consts.keys()):
            val = consts[name]
            val_repr = repr(val)
            if len(val_repr) > 100:
                val_repr = val_repr[:97] + "..."
            print(f"    {name} = {val_repr}")

# ================================================================
# 第9步：补充检查 —— 范例代码出现过的方法/常量是否真实存在
# ================================================================
log_section("第9步：范例代码出现过的方法/常量存在性核对")
checks = {
    "ESP32.start": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "start"),
    "ESP32.digitalRead": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "digitalRead"),
    "ESP32.digitalWrite": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "digitalWrite"),
    "ESP32.analogRead": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "analogRead"),
    "ESP32.analogWrite": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "analogWrite"),
    "ESP32.servo": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "servo"),
    "ESP32.ws2812Init": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "ws2812Init"),
    "ESP32.ws2812Write": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "ws2812Write"),
    "ESP32.dhtReadTemperature": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "dhtReadTemperature"),
    "ESP32.dhtReadHumidity": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "dhtReadHumidity"),
    "ESP32.ds18b20Read": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "ds18b20Read"),
    "ESP32.ultrasonicRead": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "ultrasonicRead"),
    "ESP32.motor_MA": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "motor_MA"),
    "ESP32.motor_MB": lambda: hasattr(getattr(ESP32_mod, "ESP32", lambda: None) or None, "motor_MB"),
    "GPIO_IO_01 常量": lambda: hasattr(ESP32_mod, "GPIO_IO_01"),
    "GPIO_IO_02 常量": lambda: hasattr(ESP32_mod, "GPIO_IO_02"),
    "ADC_IO_02 常量": lambda: hasattr(ESP32_mod, "ADC_IO_02"),
    "VoiceAPI.get_token": lambda: hasattr(getattr(voice_mod, "VoiceAPI", None) or None, "get_token"),
    "VoiceAPI.tts_synthesize": lambda: hasattr(getattr(voice_mod, "VoiceAPI", None) or None, "tts_synthesize"),
    "VoiceAPI.voice_recognition": lambda: hasattr(getattr(voice_mod, "VoiceAPI", None) or None, "voice_recognition"),
    "VoiceAPI.translate_english": lambda: hasattr(getattr(voice_mod, "VoiceAPI", None) or None, "translate_english"),
    "VoiceAPI.llm_chat": lambda: hasattr(getattr(voice_mod, "VoiceAPI", None) or None, "llm_chat"),
    "AudioRecorder.set_output_dir": lambda: hasattr(getattr(rec_mod, "AudioRecorder", None) or None, "set_output_dir"),
    "AudioRecorder.record_fixed_duration": lambda: hasattr(getattr(rec_mod, "AudioRecorder", None) or None, "record_fixed_duration"),
    "AudioRecorder.start_recording": lambda: hasattr(getattr(rec_mod, "AudioRecorder", None) or None, "start_recording"),
    "AudioRecorder.stop_recording": lambda: hasattr(getattr(rec_mod, "AudioRecorder", None) or None, "stop_recording"),
    "AudioRecorder.save_audio": lambda: hasattr(getattr(rec_mod, "AudioRecorder", None) or None, "save_audio"),
    "AudioPlayer.play_file": lambda: hasattr(getattr(play_mod, "AudioPlayer", None) or None, "play_file"),
    "AudioPlayer.cleanup": lambda: hasattr(getattr(play_mod, "AudioPlayer", None) or None, "cleanup"),
    "TextRecognizer.recognize_text": lambda: hasattr(getattr(ocr_mod, "TextRecognizer", None) or None, "recognize_text"),
    "TextRecognizer.recognize_image_text": lambda: hasattr(getattr(ocr_mod, "TextRecognizer", None) or None, "recognize_image_text"),
}
for desc, fn in checks.items():
    try:
        ok = fn()
    except Exception:
        ok = False
    print(f"  {'[OK]' if ok else '[  ]'} {desc}")

# ---------- 收尾 ----------
print()
print("=" * 70)
print(f"探测完成 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
print(f"日志已写入: {LOG_FILE}")
print("=" * 70)

_tee.close()
sys.stdout = _tee._console
