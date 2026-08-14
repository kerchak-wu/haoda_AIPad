#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盲点探测脚本（非交互式）
覆盖: C(TextRecognizer) / D(AudioPlayer) / E(voice_api.LLM)
      / F(ESP32 BMP280) / G(OpenCV 5.0 API差异) / H(RKNN, 条件)
      / I(性能基准, 条件) / J(Line_Sensor) / K(Swap)

注意: A(V3回调) 和 B(表情投入度) 需要交互，已拆为独立脚本：
  - 探测_盲点_A_回调系统.py（pygame 窗口 + 倒计时 + 指引）
  - 探测_盲点_B_表情投入度.py（pygame 窗口 + 3 阶段动作指引）

运行: python3 探测_盲点_非交互.py
日志: logs/logs_探测_盲点_非交互_YYYYMMDD.txt
依赖: 摄像头(C项)、ESP32扩展板(F,J项)
"""

import os
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'

# text_recognition 必须在 cv2/pygame/V3 之前导入（utils 命名空间冲突）
_tr_ok = False
_tr_err = ''
try:
    import text_recognition
    _tr_ok = True
except Exception as e:
    _tr_err = str(e)

import sys
import time
import datetime
import traceback
import inspect

# 日志统一输出到 logs/ 目录，避免散落在项目根目录
_log_dir = 'logs'
if not os.path.exists(_log_dir):
    try:
        os.makedirs(_log_dir)
    except Exception:
        pass
LOG_FILE = '%s/logs_探测_盲点_非交互_%s.txt' % (
    _log_dir, datetime.datetime.now().strftime('%Y%m%d'))
_log_fp = None


def log(msg=''):
    line = str(msg) if msg else ''
    print(line)
    if _log_fp:
        _log_fp.write(line + '\n')
        _log_fp.flush()


def section(title):
    log('')
    log('=' * 70)
    log('  ' + title)
    log('=' * 70)


def subsection(title):
    log('\n  --- ' + title + ' ---')


def safe_run(name, func):
    try:
        func()
    except Exception as e:
        log('  ❌ [%s] 整体异常: %s' % (name, e))
        traceback.print_exc()
        if _log_fp:
            traceback.print_exc(file=_log_fp)


def get_mem_mb():
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) / 1024.0
    except:
        pass
    return -1


def open_cv2_camera():
    """按 40->41->42 顺序尝试 V4L2 后端打开摄像头，返回 (cap, cam_id) 或 (None, None)"""
    import cv2
    import numpy as np
    for cid in [40, 41, 42]:
        path = '/dev/video%d' % cid
        if not os.path.exists(path):
            continue
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        if cap.isOpened():
            for _ in range(5):
                ret, frame = cap.read()
                if ret and frame is not None and frame.ndim == 3:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    m = float(gray.mean())
                    if 2.0 < m < 253.0:
                        return cap, cid
            cap.release()
        else:
            cap.release()
    return None, None


def generate_text_image():
    """生成包含文字的 640x480 BGR 图像供 OCR 测试"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (640, 480), 'white')
        draw = ImageDraw.Draw(img)
        font = None
        for fp in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']:
            if os.path.exists(fp):
                font = ImageFont.truetype(fp, 36)
                break
        if font is None:
            font = ImageFont.load_default()
        draw.text((80, 100), 'Hello World 12345', fill='black', font=font)
        draw.text((80, 200), 'OCR Test 2026', fill='black', font=font)
        draw.text((80, 300), 'Good Morning', fill='black', font=font)
        import numpy as np
        return np.array(img)
    except Exception:
        import cv2
        import numpy as np
        img = np.ones((480, 640, 3), dtype=np.uint8) * 255
        cv2.putText(img, 'Hello World 12345', (80, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        cv2.putText(img, 'OCR Test 2026', (80, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        cv2.putText(img, 'Good Morning', (80, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        return img


# ============================================================
# A: V3 回调系统验证
# ============================================================
def probe_A_v3_callbacks():
    section('A: V3 回调系统验证')
    import camera_vision_system_v3 as v3

    log('  创建视觉系统...')
    try:
        vs = v3.create_vision_system_v3(enable_basic=True, enable_advanced=True)
    except TypeError:
        vs = v3.create_vision_system_v3(enable_basic=True)

    ts = vs.threaded_system

    # 反射查找所有回调方法
    all_ts = [m for m in dir(ts) if not m.startswith('_') and callable(getattr(ts, m, None))]
    cb_ts = [m for m in all_ts if 'callback' in m.lower() or m.startswith('set_') and 'cb' in m.lower()]
    log('  threaded_system 回调方法(%d): %s' % (len(cb_ts), cb_ts))

    all_vs = [m for m in dir(vs) if not m.startswith('_') and callable(getattr(vs, m, None))]
    cb_vs = [m for m in all_vs if 'callback' in m.lower()]
    if cb_vs:
        log('  vision_system 回调方法(%d): %s' % (len(cb_vs), cb_vs))

    # 注册 dummy 回调
    cb_data = {}

    def make_cb(name):
        def cb(*args, **kwargs):
            e = cb_data.setdefault(name, {'count': 0, 'types': [], 'args': None})
            e['count'] += 1
            if e['count'] == 1:
                e['types'] = [type(a).__name__ for a in args]
                e['args'] = repr(args)[:500]
        return cb

    for mname in cb_ts:
        if mname.startswith('add_') and mname != 'remove_callback':
            short = mname.replace('add_', '').replace('_callback', '')
            try:
                getattr(ts, mname)(make_cb(short))
                log('  ✅ 注册: %s' % mname)
            except Exception as e:
                log('  ❌ 注册失败: %s - %s' % (mname, e))

    # 打开摄像头（open_camera() 无参数，CameraConfig 内部自动按 [40,41,42,43] 探测）
    log('  打开摄像头（open_camera 无参，自动探测 40/41/42）...')
    cam_ok = False
    try:
        ret = vs.open_camera()
        if ret is None or ret:
            cam_ok = True
            log('  ✅ 摄像头已打开')
        else:
            log('  ❌ open_camera() 返回 False')
    except Exception as e:
        log('  ❌ open_camera() 异常: %s' % e)

    if not cam_ok:
        log('  ❌ 摄像头打开失败，跳过回调触发验证')
        try:
            vs.cleanup()
        except:
            pass
        return

    # 启动后台检测
    try:
        ts.start_background_detection()
        log('  ✅ 后台检测已启动')
    except Exception as e:
        log('  ❌ 启动失败: %s' % e)
        try:
            vs.cleanup()
        except:
            pass
        return

    # 等待 15 秒收集回调
    log('  等待 15 秒（请在摄像头前做动作：露脸/挥手/出示二维码/颜色物体）...')
    for i in range(15):
        time.sleep(1)
        triggered = dict((k, v['count']) for k, v in cb_data.items() if v['count'] > 0)
        log('    [%d/15s] %s' % (i + 1, triggered if triggered else '(无)'))

    # 停止
    try:
        ts.stop_background_detection()
    except:
        try:
            vs.stop_background_detection()
        except:
            pass
    try:
        vs.cleanup()
    except:
        pass
    time.sleep(2)

    # 结果
    log('\n  ========== 回调触发统计 ==========')
    if not cb_data:
        log('  （无回调注册成功）')
    for name, info in sorted(cb_data.items()):
        status = '✅ 触发' if info['count'] > 0 else '❌ 未触发'
        log('  %s: %s (%d次)' % (name, status, info['count']))
        if info['count'] > 0:
            log('    参数类型: %s' % info['types'])
            log('    首次参数: %s' % info['args'])

    not_triggered = [k for k, v in cb_data.items() if v['count'] == 0]
    if not_triggered:
        log('\n  未触发回调: %s' % not_triggered)
        log('  注意: 可能是摄像头前没有对应目标')


# ============================================================
# C: TextRecognizer 返回字段结构
# ============================================================
def probe_C_text_recognizer():
    section('C: TextRecognizer 返回字段结构')

    if not _tr_ok:
        log('  ❌ text_recognition 导入失败: %s' % _tr_err)
        return

    import numpy as np

    subsection('反射枚举 TextRecognizer 类')
    tr_cls = text_recognition.TextRecognizer
    all_methods = [m for m in dir(tr_cls) if not m.startswith('_')]
    log('  TextRecognizer 公开方法: %s' % all_methods)

    try:
        sig = inspect.signature(tr_cls.__init__)
        log('  __init__ 签名: %s' % sig)
    except Exception:
        pass

    subsection('实例化')
    try:
        tr = tr_cls()
        log('  ✅ 实例化成功')
    except Exception as e:
        log('  ❌ 实例化失败: %s' % e)
        return

    # 列出实例方法
    inst_methods = [m for m in dir(tr) if not m.startswith('_') and callable(getattr(tr, m))]
    log('  实例方法: %s' % inst_methods)

    subsection('生成测试图像')
    frame = generate_text_image()
    log('  测试图像: shape=%s dtype=%s' % (frame.shape, frame.dtype))

    subsection('调用 recognize_text')
    try:
        result = tr.recognize_text(frame)
    except Exception as e:
        log('  ❌ recognize_text 失败: %s' % e)
        traceback.print_exc()
        return

    log('  返回类型: %s' % type(result).__name__)
    log('  返回值 repr: %s' % repr(result)[:1000])

    if isinstance(result, (list, tuple)):
        log('  元素数量: %d' % len(result))
        if len(result) > 0:
            elem = result[0]
            log('  首元素类型: %s' % type(elem).__name__)
            if isinstance(elem, dict):
                log('  首元素 keys: %s' % list(elem.keys()))
                for k, v in elem.items():
                    log('    %s = %s (type=%s)' % (k, repr(v)[:200], type(v).__name__))
            elif isinstance(elem, str):
                log('  首元素值: %s' % elem)
            else:
                # 对象
                obj_attrs = [a for a in dir(elem) if not a.startswith('_')]
                log('  首元素属性: %s' % obj_attrs)
                for a in obj_attrs:
                    try:
                        val = getattr(elem, a)
                        if not callable(val):
                            log('    %s = %s' % (a, repr(val)[:200]))
                    except:
                        pass
    elif isinstance(result, dict):
        log('  keys: %s' % list(result.keys()))
        for k, v in result.items():
            log('    %s = %s (type=%s)' % (k, repr(v)[:200], type(v).__name__))
    elif hasattr(result, '__dict__'):
        log('  属性: %s' % list(result.__dict__.keys()))
        for k, v in result.__dict__.items():
            log('    %s = %s' % (k, repr(v)[:200]))
    else:
        log('  (非 list/dict/对象，直接打印)')

    # 检查是否有其他方法可获取更详细结果
    subsection('检查其他结果方法')
    for mname in inst_methods:
        if mname == 'recognize_text':
            continue
        try:
            m = getattr(tr, mname)
            sig = inspect.signature(m)
            log('  %s%s' % (mname, sig))
        except:
            log('  %s (无签名)' % mname)


# ============================================================
# D: AudioPlayer 隐藏方法
# ============================================================
def probe_D_audio_player():
    section('D: AudioPlayer 隐藏方法探测')

    try:
        import audio_player as ap_mod
    except Exception as e:
        log('  ❌ import audio_player 失败: %s' % e)
        return

    subsection('模块级内容')
    mod_items = [x for x in dir(ap_mod) if not x.startswith('_')]
    log('  模块属性: %s' % mod_items)

    # 找类
    classes = [x for x in mod_items if inspect.isclass(getattr(ap_mod, x))]
    log('  类: %s' % classes)

    if 'AudioPlayer' not in classes:
        log('  ❌ 未找到 AudioPlayer 类')
        return

    cls = ap_mod.AudioPlayer

    subsection('类级反射')
    class_methods = [m for m in dir(cls) if not m.startswith('_')]
    log('  公开方法/属性(%d): %s' % (len(class_methods), class_methods))

    # 搜索隐藏的播放控制方法
    control_keywords = ['pause', 'resume', 'seek', 'stop', 'position',
                        'volume', 'mute', 'progress', 'duration', 'time',
                        'play', 'restart', 'rewind', 'fast', 'speed']
    found_control = []
    for m in class_methods:
        ml = m.lower()
        for kw in control_keywords:
            if kw in ml:
                found_control.append(m)
                break
    log('  播放控制相关方法: %s' % (found_control if found_control else '(无)'))

    # 打印每个方法的签名
    subsection('方法签名')
    for mname in class_methods:
        attr = getattr(cls, mname, None)
        if callable(attr):
            try:
                sig = inspect.signature(attr)
                log('  %s%s' % (mname, sig))
            except (ValueError, TypeError):
                log('  %s (无法获取签名)' % mname)
        else:
            log('  %s = %s (属性, 非方法)' % (mname, repr(attr)[:100]))

    # 实例级反射
    subsection('实例级反射')
    try:
        sig_init = inspect.signature(cls.__init__)
        log('  __init__ 签名: %s' % sig_init)
    except:
        pass

    try:
        player = cls()
        log('  ✅ 实例化成功')
        inst_methods = [m for m in dir(player) if not m.startswith('_')]
        inst_only = [m for m in inst_methods if m not in class_methods]
        if inst_only:
            log('  实例独有方法: %s' % inst_only)
        else:
            log('  (实例无独有方法)')

        # 检查 __dict__
        if hasattr(player, '__dict__'):
            log('  实例属性: %s' % list(player.__dict__.keys()))
    except Exception as e:
        log('  ❌ 实例化失败: %s' % e)


# ============================================================
# E: voice_api.LLM 真实模型
# ============================================================
def probe_E_voice_api_llm():
    section('E: voice_api.LLM 真实模型探测')

    try:
        import voice_api
    except Exception as e:
        log('  ❌ import voice_api 失败: %s' % e)
        return

    subsection('模块级内容')
    mod_items = [x for x in dir(voice_api) if not x.startswith('_')]
    log('  模块属性: %s' % mod_items)

    classes = [x for x in mod_items if inspect.isclass(getattr(voice_api, x))]
    log('  类: %s' % classes)

    # 检查 LLM 类
    subsection('LLM 类探测')
    if 'LLM' in classes:
        cls = voice_api.LLM
        log('  ✅ 找到 LLM 类')
    elif 'VoiceAPI' in classes:
        cls = voice_api.VoiceAPI
        log('  未找到独立 LLM 类，使用 VoiceAPI')
    else:
        log('  ❌ 未找到 LLM 或 VoiceAPI 类')
        return

    all_methods = [m for m in dir(cls) if not m.startswith('_')]
    log('  公开方法(%d): %s' % (len(all_methods), all_methods))

    # 搜索 LLM/chat 相关方法
    llm_keywords = ['chat', 'llm', 'complet', 'dialog', 'stream', 'message', 'ask', 'generat']
    llm_methods = []
    for m in all_methods:
        ml = m.lower()
        for kw in llm_keywords:
            if kw in ml:
                llm_methods.append(m)
                break
    log('  LLM/对话相关方法: %s' % (llm_methods if llm_methods else '(无)'))

    # 打印签名
    subsection('方法签名')
    for mname in all_methods:
        attr = getattr(cls, mname, None)
        if callable(attr):
            try:
                sig = inspect.signature(attr)
                log('  %s%s' % (mname, sig))
            except (ValueError, TypeError):
                log('  %s (无法获取签名)' % mname)

    # 尝试实例化
    subsection('实例化尝试')
    try:
        sig_init = inspect.signature(cls.__init__)
        log('  __init__ 签名: %s' % sig_init)
    except:
        pass

    instance = None
    try:
        instance = cls()
        log('  ✅ 无参实例化成功')
    except Exception as e:
        log('  ❌ 无参实例化失败: %s' % e)
        # 尝试带参数
        for args in [(), ({},)]:
            try:
                instance = cls(*args)
                log('  ✅ 带参实例化成功: args=%s' % str(args))
                break
            except:
                pass

    # 尝试调用 chat
    if instance and llm_methods:
        subsection('调用 LLM 对话')
        for mname in llm_methods:
            try:
                m = getattr(instance, mname)
                sig = inspect.signature(m)
                params = list(sig.parameters.keys())
                log('  尝试 %s%s, 参数: %s' % (mname, sig, params))
                # 尝试不同调用方式
                for call_args in [('你好',), ({'text': '你好'},), ({'message': '你好'},)]:
                    try:
                        result = m(*call_args)
                        log('  ✅ 调用成功, 返回类型: %s' % type(result).__name__)
                        log('  返回值: %s' % repr(result)[:500])
                        break
                    except TypeError:
                        continue
                    except Exception as e:
                        log('  ❌ 调用失败: %s' % e)
                        break
            except Exception as e:
                log('  ❌ %s 异常: %s' % (mname, e))

    # 检查环境变量中的密钥
    subsection('环境变量检查')
    import os as _os
    env_keys = [k for k in _os.environ if any(kw in k.upper() for kw in
                ['HAODA', 'AI_PAI', 'API_KEY', 'TOKEN', 'VOICE', 'BAIDU', 'LLM', 'OPENAI'])]
    if env_keys:
        for k in env_keys:
            v = _os.environ[k]
            # 只显示前10字符
            log('  %s = %s...' % (k, v[:10]))
    else:
        log('  未找到相关环境变量（可能内置密钥）')


# ============================================================
# F: ESP32 BMP280 方法可调用性
# ============================================================
def probe_F_esp32_bmp280():
    section('F: ESP32 BMP280 方法可调用性')

    try:
        import ESP32 as esp_mod
    except Exception as e:
        log('  ❌ import ESP32 失败: %s' % e)
        return

    subsection('查找 BMP280/气压/温度相关方法')
    # 找类
    classes = [x for x in dir(esp_mod) if inspect.isclass(getattr(esp_mod, x))]
    log('  模块类: %s' % classes)

    if 'ESP32' not in classes:
        log('  ❌ 未找到 ESP32 类')
        return

    cls = esp_mod.ESP32
    all_methods = [m for m in dir(cls) if not m.startswith('_') and callable(getattr(cls, m, None))]

    # 搜索 BMP280/气压/温度/高度相关
    bmp_keywords = ['bmp', 'pressure', 'altitude', 'temp', 'humid', 'i2c', 'uart', 'baro', 'atm']
    bmp_methods = []
    for m in all_methods:
        ml = m.lower()
        for kw in bmp_keywords:
            if kw in ml:
                bmp_methods.append(m)
                break
    log('  BMP280/传感器相关方法(%d): %s' % (len(bmp_methods), bmp_methods))

    # 打印签名
    subsection('方法签名')
    for mname in bmp_methods:
        try:
            sig = inspect.signature(getattr(cls, mname))
            log('  %s%s' % (mname, sig))
        except:
            log('  %s (无签名)' % mname)

    # 实例化并尝试调用
    subsection('实例化 + 调用测试')
    try:
        esp = cls()
        log('  ✅ 实例化成功')
    except Exception as e:
        log('  ❌ 实例化失败: %s' % e)
        return

    # 尝试 open/init
    for mname in ['open', 'init', 'begin', 'start', 'connect']:
        if hasattr(esp, mname):
            try:
                getattr(esp, mname)()
                log('  ✅ %s() 成功' % mname)
            except Exception as e:
                log('  ❌ %s() 失败: %s' % (mname, e))

    # 逐个尝试 BMP280 相关方法
    subsection('逐个调用 BMP280 相关方法')
    for mname in bmp_methods:
        if mname in ['open', 'init', 'begin', 'start', 'connect']:
            continue
        try:
            m = getattr(esp, mname)
            result = m()
            log('  ✅ %s() -> %s (type=%s)' % (mname, repr(result)[:200], type(result).__name__))
        except Exception as e:
            err_str = str(e)
            # 分类异常
            if 'I2C' in err_str or 'i2c' in err_str:
                cat = 'I2C通信失败(硬件未接?)'
            elif 'Not connected' in err_str or 'not open' in err_str:
                cat = '未连接'
            elif 'parameter' in err_str.lower() or 'argument' in err_str.lower():
                cat = '参数缺失'
            elif 'No such file' in err_str or 'No module' in err_str:
                cat = '依赖缺失'
            else:
                cat = '其他错误'
            log('  ❌ %s() -> [%s] %s' % (mname, cat, err_str[:200]))


# ============================================================
# G: OpenCV 5.0.0 API 差异
# ============================================================
def probe_G_opencv5_api():
    section('G: OpenCV 5.0.0 API 差异检测')

    import cv2
    import numpy as np

    log('  cv2.__version__ = %s' % cv2.__version__)
    log('  cv2.__file__ = %s' % cv2.__file__)

    subsection('1. findContours 返回值（4.x vs 5.x 关键差异）')
    test_img = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(test_img, (20, 20), (80, 80), 255, -1)
    try:
        ret = cv2.findContours(test_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        log('  返回值数量: %d' % len(ret))
        for i, part in enumerate(ret):
            log('    [%d] type=%s' % (i, type(part).__name__))
        if len(ret) == 2:
            log('  ✅ 5.x 风格: (contours, hierarchy)')
        elif len(ret) == 3:
            log('  ⚠️ 4.x 风格: (image, contours, hierarchy)')
    except Exception as e:
        log('  ❌ findContours 失败: %s' % e)

    subsection('2. 子模块可用性')
    submodules = ['aruco', 'dnn', 'cuda', 'face', 'xfeatures2d', 'ximgproc',
                  'tracking', 'video', 'videoio', 'ml', 'photo', 'stitching',
                  'calib3d', 'features2d', 'objdetect', 'img_hash', 'phase_unwrapping']
    for sm in submodules:
        has = hasattr(cv2, sm)
        if has:
            try:
                mod = getattr(cv2, sm)
                log('  ✅ cv2.%s (可用, type=%s)' % (sm, type(mod).__name__))
            except:
                log('  ⚠️ cv2.%s (存在但访问异常)' % sm)
        else:
            log('  ❌ cv2.%s (不存在)' % sm)

    subsection('3. 关键常量检查')
    const_groups = {
        'CAP_PROP': ['CAP_PROP_FRAME_WIDTH', 'CAP_PROP_FRAME_HEIGHT', 'CAP_PROP_FPS',
                      'CAP_PROP_FOURCC', 'CAP_PROP_BRIGHTNESS', 'CAP_PROP_EXPOSURE',
                      'CAP_PROP_AUTO_EXPOSURE', 'CAP_PROP_ZOOM', 'CAP_PROP_FOCUS'],
        'COLOR_': ['COLOR_BGR2GRAY', 'COLOR_BGR2RGB', 'COLOR_RGB2BGR', 'COLOR_HSV2BGR'],
        'FONT_': ['FONT_HERSHEY_SIMPLEX', 'FONT_HERSHEY_PLAIN', 'FONT_HERSHEY_DUPLEX'],
        'INTER_': ['INTER_LINEAR', 'INTER_CUBIC', 'INTER_NEAREST', 'INTER_AREA'],
        'THRESH_': ['THRESH_BINARY', 'THRESH_BINARY_INV', 'THRESH_OTSU', 'THRESH_TOZERO'],
        'MORPH_': ['MORPH_RECT', 'MORPH_ELLIPSE', 'MORPH_OPEN', 'MORPH_CLOSE', 'MORPH_GRADIENT'],
        'RETR_': ['RETR_EXTERNAL', 'RETR_TREE', 'RETR_LIST', 'RETR_CCOMP'],
        'CHAIN_': ['CHAIN_APPROX_SIMPLE', 'CHAIN_APPROX_NONE'],
        'CV_': ['CV_8UC1', 'CV_8UC3', 'CV_32FC1', 'CV_64FC1'],
    }
    for group, consts in const_groups.items():
        missing = [c for c in consts if not hasattr(cv2, c)]
        if missing:
            log('  ❌ %s 缺失: %s' % (group, missing))
        else:
            log('  ✅ %s 全部存在(%d)' % (group, len(consts)))

    subsection('4. 常用函数签名检查')
    import inspect as _ins
    funcs_to_check = [
        'cvtColor', 'resize', 'GaussianBlur', 'medianBlur', 'bilateralFilter',
        'threshold', 'adaptiveThreshold', 'Canny', 'Sobel', 'Scharr',
        'dilate', 'erode', 'morphologyEx', 'warpAffine', 'warpPerspective',
        'HoughLinesP', 'HoughCircles', 'matchTemplate', 'connectedComponents',
        'connectedComponentsWithStats', 'boundingRect', 'contourArea',
        'convexHull', 'moments', 'equalizeHist', 'createCLAHE',
        'putText', 'getTextSize', 'rectangle', 'circle', 'line',
        'polylines', 'fillPoly', 'bitwise_and', 'bitwise_or', 'addWeighted',
        'imdecode', 'imencode', 'flip', 'rotate', 'filter2D',
        'getPerspectiveTransform', 'getAffineTransform',
        'VideoWriter_fourcc', 'getStructuringElement',
    ]
    found = 0
    missing = []
    for fname in funcs_to_check:
        if hasattr(cv2, fname):
            found += 1
        else:
            missing.append(fname)
    log('  存在: %d/%d' % (found, len(funcs_to_check)))
    if missing:
        log('  ❌ 缺失函数: %s' % missing)
    else:
        log('  ✅ 全部存在')

    # 检查 findContours 签名
    subsection('5. findContours 签名')
    try:
        sig = _ins.signature(cv2.findContours)
        log('  %s' % sig)
    except:
        log('  (无法获取签名)')

    # 检查 VideoWriter_fourcc
    subsection('6. VideoWriter_fourcc')
    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        log('  ✅ VideoWriter_fourcc(*"mp4v") = %d' % fourcc)
    except Exception as e:
        log('  ❌ %s' % e)

    # 检查 TickCount (性能计时)
    subsection('7. 计时工具')
    timing_tools = ['getTickCount', 'getTickFrequency', 'getCPUTickCount']
    for t in timing_tools:
        log('  cv2.%s: %s' % (t, '✅' if hasattr(cv2, t) else '❌'))


# ============================================================
# H: RKNN 端到端部署（条件执行）
# ============================================================
def probe_H_rknn():
    section('H: RKNN 端到端部署探测（条件执行）')

    subsection('1. rknnlite2 Python 绑定')
    try:
        import rknnlite2
        log('  ✅ rknnlite2 导入成功')
        log('  版本: %s' % getattr(rknnlite2, '__version__', '未知'))
        log('  文件: %s' % rknnlite2.__file__)
    except ImportError:
        log('  ❌ rknnlite2 未安装')
        log('  当前状态: librknnrt.so 已装(C运行时) 但 Python 绑定缺失')
        log('  需要安装 Rockchip 官方 rknn-toolkit2 对应的 aarch64 whl')
        log('  跳过后续 RKNN 推理测试')
        return
    except Exception as e:
        log('  ❌ rknnlite2 导入异常: %s' % e)
        return

    subsection('2. RKNN 运行时 API')
    rknn_classes = [x for x in dir(rknnlite2) if not x.startswith('_')]
    log('  模块属性: %s' % rknn_classes)

    if 'RKNNLite' in rknn_classes:
        cls = rknnlite2.RKNNLite
        methods = [m for m in dir(cls) if not m.startswith('_')]
        log('  RKNNLite 方法: %s' % methods)

        try:
            sig = inspect.signature(cls.__init__)
            log('  __init__ 签名: %s' % sig)
        except:
            pass

    subsection('3. 查找 .rknn 模型文件')
    import glob
    search_paths = [
        os.path.expanduser('~/*.rknn'),
        os.path.expanduser('~/**/*.rknn'),
        '/usr/share/*.rknn',
        '/opt/**/*.rknn',
    ]
    found_models = []
    for sp in search_paths:
        found_models.extend(glob.glob(sp, recursive=True))
    if found_models:
        log('  找到模型文件:')
        for mf in found_models[:10]:
            sz = os.path.getsize(mf) / 1024 / 1024
            log('    %s (%.1f MB)' % (mf, sz))
    else:
        log('  未找到 .rknn 模型文件')
        log('  跳过推理测试（需要 .rknn 模型文件）')

    subsection('4. NPU 硬件状态')
    try:
        with open('/sys/class/devfreq/fdab0000.npu/cur_freq') as f:
            freq = f.read().strip()
        log('  NPU 当前频率: %s Hz' % freq)
    except:
        log('  (无法读取 NPU 频率)')
    try:
        with open('/sys/class/devfreq/fdab0000.npu/load') as f:
            load = f.read().strip()
        log('  NPU 负载: %s' % load)
    except:
        log('  (无法读取 NPU 负载)')


# ============================================================
# I: 第三方库性能基准（条件执行）
# ============================================================
def probe_I_performance():
    section('I: 第三方库性能基准（条件执行）')
    import numpy as np
    import cv2

    # 生成合成帧
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    N = 30  # 帧数

    subsection('1. MediaPipe Hands')
    try:
        import mediapipe as mp
        log('  mediapipe 版本: %s' % mp.__version__)
        hands = mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=1,
                                          model_complexity=0, min_detection_confidence=0.5)
        mem_before = get_mem_mb()
        t0 = time.time()
        for i in range(N):
            results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        elapsed = time.time() - t0
        mem_after = get_mem_mb()
        fps = N / elapsed
        log('  ✅ %d 帧, 耗时 %.2fs, FPS=%.1f' % (N, elapsed, fps))
        log('  内存: %.1f -> %.1f MB (+%.1f)' % (mem_before, mem_after, mem_after - mem_before))
        hands.close()
        del hands
    except Exception as e:
        log('  ❌ MediaPipe Hands 失败: %s' % e)

    subsection('2. MediaPipe Pose')
    try:
        import mediapipe as mp
        pose = mp.solutions.pose.Pose(static_image_mode=False, model_complexity=0,
                                       min_detection_confidence=0.5)
        mem_before = get_mem_mb()
        t0 = time.time()
        for i in range(N):
            results = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        elapsed = time.time() - t0
        mem_after = get_mem_mb()
        fps = N / elapsed
        log('  ✅ %d 帧, 耗时 %.2fs, FPS=%.1f' % (N, elapsed, fps))
        log('  内存: %.1f -> %.1f MB (+%.1f)' % (mem_before, mem_after, mem_after - mem_before))
        pose.close()
        del pose
    except Exception as e:
        log('  ❌ MediaPipe Pose 失败: %s' % e)

    subsection('3. dt-apriltags')
    try:
        from dt_apriltags import Detector
        det = Detector(families='tag36h11', nthreads=2, quad_decimate=2.0)
        mem_before = get_mem_mb()
        t0 = time.time()
        for i in range(N):
            tags = det.detect(gray, estimate_tag_pose=False, camera_params=None, tag_size=None)
        elapsed = time.time() - t0
        mem_after = get_mem_mb()
        fps = N / elapsed
        log('  ✅ %d 帧, 耗时 %.2fs, FPS=%.1f' % (N, elapsed, fps))
        log('  内存: %.1f -> %.1f MB (+%.1f)' % (mem_before, mem_after, mem_after - mem_before))
        del det
    except Exception as e:
        log('  ❌ dt-apriltags 失败: %s' % e)

    subsection('4. cv2.cvtColor 纯开销基准')
    mem_before = get_mem_mb()
    t0 = time.time()
    for i in range(N):
        _ = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    elapsed = time.time() - t0
    mem_after = get_mem_mb()
    fps = N / elapsed
    log('  ✅ %d 帧, 耗时 %.4fs, FPS=%.1f' % (N, elapsed, fps))
    log('  内存: %.1f -> %.1f MB' % (mem_before, mem_after))


# ============================================================
# J: Line_Sensor 实际接线
# ============================================================
def probe_J_line_sensor():
    section('J: Line_Sensor 实际接线探测')

    try:
        import Line_Sensor as ls_mod
    except Exception as e:
        log('  ❌ import Line_Sensor 失败: %s' % e)
        return

    subsection('模块级内容')
    mod_items = [x for x in dir(ls_mod) if not x.startswith('_')]
    log('  模块属性: %s' % mod_items)

    classes = [x for x in mod_items if inspect.isclass(getattr(ls_mod, x))]
    log('  类: %s' % classes)

    if not classes:
        log('  ❌ 未找到任何类')
        return

    cls = getattr(ls_mod, classes[0])
    all_methods = [m for m in dir(cls) if not m.startswith('_') and callable(getattr(cls, m, None))]
    log('  %s 公开方法(%d): %s' % (classes[0], len(all_methods), all_methods))

    # 签名
    subsection('方法签名')
    for mname in all_methods:
        try:
            sig = inspect.signature(getattr(cls, mname))
            log('  %s%s' % (mname, sig))
        except:
            log('  %s (无签名)' % mname)

    # 实例化 + 调用
    subsection('实例化 + 调用测试')
    try:
        ls = cls()
        log('  ✅ 实例化成功')
    except Exception as e:
        log('  ❌ 实例化失败: %s' % e)
        return

    # 逐个尝试读取方法
    subsection('逐个调用读取方法')
    for mname in all_methods:
        if mname in ['open', 'init', 'begin', 'start', 'close', 'cleanup']:
            continue
        try:
            m = getattr(ls, mname)
            result = m()
            log('  ✅ %s() -> %s (type=%s)' % (mname, repr(result)[:200], type(result).__name__))
        except Exception as e:
            err_str = str(e)
            if 'I2C' in err_str or 'i2c' in err_str:
                cat = 'I2C通信失败(硬件未接?)'
            elif 'Not connected' in err_str:
                cat = '未连接'
            else:
                cat = '错误'
            log('  ❌ %s() -> [%s] %s' % (mname, cat, err_str[:200]))


# ============================================================
# K: Swap 分区状态
# ============================================================
def probe_K_swap():
    section('K: Swap 分区状态探测')

    subsection('1. /proc/swaps')
    try:
        with open('/proc/swaps') as f:
            content = f.read().strip()
        lines = content.split('\n')
        if len(lines) <= 1 and not lines[0].strip():
            log('  ❌ 无 Swap 分区')
        else:
            for line in lines:
                log('  %s' % line)
    except Exception as e:
        log('  读取失败: %s' % e)

    subsection('2. /proc/meminfo (关键字段)')
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if any(kw in line for kw in ['MemTotal', 'MemFree', 'MemAvailable',
                        'Buffers', 'Cached', 'SwapTotal', 'SwapFree', 'Shmem']):
                    log('  %s' % line.strip())
    except Exception as e:
        log('  读取失败: %s' % e)

    subsection('3. swap 控制建议')
    log('  当前无 Swap，总内存 7.7 GiB')
    log('  如需开启 Swap（大模型场景）:')
    log('    sudo fallocate -l 4G /swapfile')
    log('    sudo chmod 600 /swapfile')
    log('    sudo mkswap /swapfile')
    log('    sudo swapon /swapfile')
    log('  当前阶段（单程序开发）不建议开启，等遇到 OOM 再处理')

    subsection('4. 当前进程内存')
    log('  本进程 RSS: %.1f MB' % get_mem_mb())


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    _log_fp = open(LOG_FILE, 'w', encoding='utf-8')
    log('盲点探测（非交互）开始 - %s' % datetime.datetime.now())
    log('日志文件: %s' % LOG_FILE)
    log('Python: %s' % sys.version)

    # A(V3回调) 已拆为独立交互脚本 探测_盲点_A_回调系统.py
    safe_run('C', probe_C_text_recognizer)
    safe_run('D', probe_D_audio_player)
    safe_run('E', probe_E_voice_api_llm)
    safe_run('F', probe_F_esp32_bmp280)
    safe_run('G', probe_G_opencv5_api)
    safe_run('H', probe_H_rknn)
    safe_run('I', probe_I_performance)
    safe_run('J', probe_J_line_sensor)
    safe_run('K', probe_K_swap)

    log('\n' + '=' * 70)
    log('盲点探测（非交互）完成 - %s' % datetime.datetime.now())
    log('日志文件: %s' % LOG_FILE)
    log('=' * 70)
    _log_fp.close()
