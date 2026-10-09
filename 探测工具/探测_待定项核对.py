# -*- coding: utf-8 -*-
"""
探测_待定项核对.py —— 好搭AI派「待定口径」实机探测程序

用途：一次性核对我方文档里仍未定案的设备事实，结果写入 logs/ 下的 .log 文件，发回即可。

运行方式（二选一）：
  1) 把本文件复制到设备 /home/cxdz/jupyter/user/ 下，在程序管理器里点「运行」
  2) SSH：
     cd /home/cxdz/jupyter/user && PYTHONPATH=/home/cxdz/jupyter/lib python3 探测_待定项核对.py

输出：
  logs/探测_待定项核对_YYYYMMDD_HHMMSS.log   ← 把这个文件发回
  同时打印在终端 / 管理器右侧输出窗口

安全性（只读探测）：
  - 不写、不清空 face_database / object_database 里任何记录（只读文件名与条数；
    启用 V3 人脸算法时可能自动创建空的数据库目录，不会新增记录）
  - 不调用 delete_face / delete_object_recognition_class / clear_* / learn_new_face
  - 不播放声音；只在 I 节做一次 2 秒录音落盘测试（把 _TEST_AUDIO_RECORD 改成 False 可跳过）
  - 不改系统设置、不改串口参数（串口只做"能否打开"测试并立即关闭）

预计耗时：1~3 分钟（PaddleOCR 导入 + 6 秒回调计数 + 摄像头节点逐个探测）
"""

import os
import sys

# ===== 红线：LIBGL 必须在所有 GL 相关库导入之前设置（赋值式）=====
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'

import datetime
import json
import subprocess
import time
import traceback

# ---------- 日志（Tee：终端 + logs/xxx.log，追加模式）----------
_LOG_DIR = 'logs'
try:
    if not os.path.exists(_LOG_DIR):
        os.makedirs(_LOG_DIR, exist_ok=True)
except Exception:
    _LOG_DIR = '.'

_TAG = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
_LOG_FILE = os.path.join(_LOG_DIR, '探测_待定项核对_%s.log' % _TAG)

_ORIG_OUT = sys.stdout
_ORIG_ERR = sys.stderr


class _Tee(object):
    def __init__(self, path, stream):
        self.stream = stream
        self.fp = open(path, 'a', buffering=-1, encoding='utf-8')

    def write(self, data):
        try:
            self.stream.write(data)
        except Exception:
            pass
        try:
            self.fp.write(data)
        except Exception:
            pass

    def flush(self):
        for obj in (self.stream, self.fp):
            try:
                obj.flush()
            except Exception:
                pass


_TEE = _Tee(_LOG_FILE, _ORIG_OUT)
sys.stdout = _TEE
sys.stderr = _TEE

_RESULT = []          # 结论速览（KEY | VALUE）
_TEST_AUDIO_RECORD = True   # 想跳过 2 秒录音测试就改成 False
_AUDIO_RECORD_SECONDS = 2

# ===== 红线：text_recognition 必须在 cv2 / pygame / camera_vision_system_v3 之前导入 =====
# 若排在它们之后，ppocr_system 会因 sys.modules['utils'] 被注册为非包模块而报
# "'utils' is not a package"。这里先抢注册，后面章节只做反射、不再重复导入。
_TEXT_RECOGNITION_MOD = None
_TEXT_RECOGNITION_ERR = None
try:
    import text_recognition as _TEXT_RECOGNITION_MOD
except Exception as _e:
    _TEXT_RECOGNITION_ERR = '%s: %s' % (type(_e).__name__, _e)


def log(msg=''):
    print(msg)


def section(title):
    log('')
    log('=' * 68)
    log('== %s' % title)
    log('=' * 68)


def key(name, value):
    _RESULT.append((name, value))
    log('  [KEY] %s = %s' % (name, value))


def run_cmd(cmd, timeout=8):
    """执行 shell 命令，返回 (ok, 输出文本)。失败也返回文本（含错误），不抛异常。"""
    try:
        p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        out = p.stdout.decode('utf-8', 'replace').strip()
        if len(out) > 4000:
            out = out[:4000] + '\n...（截断）'
        return True, out
    except subprocess.TimeoutExpired:
        return False, '<超时 %ss>' % timeout
    except Exception as e:
        return False, '<执行失败: %s: %s>' % (type(e).__name__, e)


def show_cmd(cmd, title=None, timeout=8):
    if title:
        log('  --- %s ---' % title)
    log('  $ %s' % cmd)
    ok, out = run_cmd(cmd, timeout)
    if out:
        for line in out.splitlines():
            log('      %s' % line)
    else:
        log('      <无输出>')
    if not ok:
        log('      <命令未正常完成>')
    return out


def trunc(value, n=300):
    text = repr(value)
    return text if len(text) <= n else text[:n] + '...(截断)'


def public_methods(obj):
    names = []
    for n in dir(obj):
        if n.startswith('_'):
            continue
        try:
            attr = getattr(obj, n)
        except Exception:
            continue
        if callable(attr):
            names.append(n)
    return sorted(names)


def try_sig(obj):
    try:
        import inspect
        return str(inspect.signature(obj))
    except Exception as e:
        return '<签名不可反射: %s>' % type(e).__name__


# =========================================================================
# 启动头
# =========================================================================
log('=' * 68)
log('好搭AI派 · 待定项核对探测')
log('启动时间: %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
log('Python: %s' % sys.version.replace('\n', ' '))
log('工作目录: %s' % os.getcwd())
log('日志文件: %s' % os.path.abspath(_LOG_FILE))
log('=' * 68)

# =========================================================================
# A. 系统 / 版本 / 环境变量 / 包状态
# =========================================================================
section('A. 系统、版本、环境变量、Python 包状态')

show_cmd('uname -a', '内核')
show_cmd('cat /etc/os-release | head -3', '发行版')
show_cmd('python3 -V; which python3', 'Python')
show_cmd('cat /proc/device-tree/compatible 2>/dev/null | tr "\\0" " "; echo', 'device-tree')
show_cmd('free -m | head -3', '内存/Swap')
show_cmd('df -h / | tail -1', '磁盘')
show_cmd('env | grep -iE "libgl|display|pythonpath" || echo "(无相关环境变量)"', '环境变量')
show_cmd('python3 -m pip list 2>/dev/null | grep -iE "opencv|pygame|numpy|pandas|mediapipe|ultralytics|apriltag|paddle|baidu" || echo "(pip list 无匹配)"', '关键包')

log('  --- Python 内省 ---')
for mod, attr in (('cv2', '__version__'), ('numpy', '__version__')):
    try:
        m = __import__(mod)
        key('%s_version' % mod, getattr(m, attr, '<无>'))
    except Exception as e:
        key('%s_version' % mod, '导入失败: %s: %s' % (type(e).__name__, e))

try:
    import pygame
    key('pygame_version', getattr(getattr(pygame, 'version', None), 'ver', '<无>'))
except Exception as e:
    key('pygame_version', '导入失败: %s: %s' % (type(e).__name__, e))

try:
    import cv2 as _cv2
    key('cv2_file', getattr(_cv2, '__file__', '<无>'))
    for sub in ('aruco', 'xfeatures2d', 'ximgproc', 'face', 'dnn', 'ml', 'videoio'):
        key('cv2_has_%s' % sub, hasattr(_cv2, sub))
    try:
        import numpy as _np
        img = _np.zeros((8, 8), dtype=_np.uint8)
        cnts = _cv2.findContours(img, _cv2.RETR_EXTERNAL, _cv2.CHAIN_APPROX_SIMPLE)
        key('cv2_findContours_returns', len(cnts))
    except Exception as e:
        key('cv2_findContours_returns', '异常: %s: %s' % (type(e).__name__, e))
except Exception as e:
    key('cv2_file', '导入失败: %s: %s' % (type(e).__name__, e))

for name in ('pandas', 'rknnlite2', 'rknn', 'dt_apriltags', 'mediapipe'):
    try:
        __import__(name)
        key('import_%s' % name, 'OK')
    except Exception as e:
        key('import_%s' % name, '%s: %s' % (type(e).__name__, e))

# =========================================================================
# B. 目录 / 现有产物 / 日志扩展名现状
# =========================================================================
section('B. 目录结构、数据目录、日志扩展名现状')

show_cmd('ls -l /home/cxdz/jupyter/user/ | head -40', '用户程序目录')
show_cmd('ls /home/cxdz/jupyter/user/*.py 2>/dev/null | wc -l', 'user/ 下 .py 数量')
show_cmd('ls /home/cxdz/jupyter/lib/*.so 2>/dev/null | wc -l', 'lib/ 下 .so 数量')
show_cmd('ls /home/cxdz/jupyter/model/ 2>/dev/null', 'model/ 下模型')
show_cmd('ls /home/cxdz/jupyter/assets/ 2>/dev/null | head -30', 'assets/ 字体等')
show_cmd('ls -d /home/cxdz/jupyter/user/face_database /home/cxdz/jupyter/user/object_database /home/cxdz/jupyter/user/object_data 2>&1', '三个数据目录是否存在')
show_cmd('ls -l /home/cxdz/jupyter/user/face_database/ 2>/dev/null', 'face_database 内容')
show_cmd('ls -l /home/cxdz/jupyter/user/object_database/ 2>/dev/null', 'object_database 内容')
show_cmd('ls -l /home/cxdz/jupyter/user/logs/ 2>/dev/null | head -30', 'logs/ 现有文件')
show_cmd('ls /home/cxdz/jupyter/user/logs/ 2>/dev/null | sed "s/.*\\.//" | sort | uniq -c', 'logs/ 扩展名直方图')

for p, label in (('/home/cxdz/jupyter/user/face_database/face_records.json', 'face_records.json'),
                 ('/home/cxdz/jupyter/user/object_database/object_records.json', 'object_records.json')):
    try:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            if isinstance(data, list) and data:
                key(label, '存在，%d 条，首条字段=%s' % (len(data), sorted(list(data[0].keys()))))
            else:
                key(label, '存在，内容类型=%s，值=%s' % (type(data).__name__, trunc(data, 120)))
        else:
            key(label, '不存在')
    except Exception as e:
        key(label, '读取异常: %s: %s' % (type(e).__name__, e))

# =========================================================================
# C. 串口 / ESP32 连接方式（P0-1）
# =========================================================================
section('C. 串口与 ESP32 连接方式（核对 ttyS9 vs ttyCH341USB*）')

show_cmd('ls -l /dev/ttyS* /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* 2>&1', '串口节点')
show_cmd('stty -F /dev/ttyS9 2>&1 | head -3', 'ttyS9 stty')
show_cmd('udevadm info -q property -n /dev/ttyS9 2>/dev/null | head -8', 'ttyS9 udev')
show_cmd('dmesg 2>/dev/null | grep -iE "ttyS9|ch341|cp210|ftdi|febc0000|serial" | head -12 || echo "(dmesg 无权限或无匹配)"', 'dmesg 串口')
show_cmd('lsmod 2>/dev/null | grep -iE "ch341|cp210|ftdi|usbserial" || echo "(无 USB 转串口驱动模块)"', 'USB 转串口驱动')

try:
    import serial
    for dev in ('/dev/ttyS9', '/dev/ttyCH341USB0', '/dev/ttyCH341USB1', '/dev/ttyUSB0'):
        if not os.path.exists(dev):
            key('serial_open_%s' % dev.replace('/', '_'), '节点不存在')
            continue
        try:
            sp = serial.Serial(dev, 115200, timeout=0.5)
            key('serial_open_%s' % dev.replace('/', '_'), 'OK 可打开（已立即关闭）')
            sp.close()
        except Exception as e:
            key('serial_open_%s' % dev.replace('/', '_'), '打开失败: %s: %s' % (type(e).__name__, e))
except Exception as e:
    key('serial_open', 'pyserial 不可用: %s: %s' % (type(e).__name__, e))

# =========================================================================
# D. 摄像头节点实况（D2 顺序 42→41→40）
# =========================================================================
section('D. 摄像头节点实况（存在性 + 能否读到有效帧）')

show_cmd('ls -l /dev/video* 2>/dev/null | tail -12', 'video 节点尾部')
show_cmd('ls /dev/video* 2>/dev/null | wc -l', 'video 节点总数')
show_cmd('v4l2-ctl --list-devices 2>&1 | head -30 || echo "(v4l2-ctl 未安装)"', 'v4l2-ctl')

try:
    import cv2
    log('  --- 逐个候选节点探测（CAP_V4L2 + 最多 5 帧灰度均值验证）---')
    usable = []
    for n in (42, 41, 40, 43, 0, 1, 2):
        path = '/dev/video%d' % n
        if not os.path.exists(path):
            log('  %-16s 不存在' % path)
            continue
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        opened = cap.isOpened()
        shape = mean = None
        for _ in range(5):
            r, f = cap.read()
            if r and f is not None:
                shape = f.shape
                mean = float(f.mean())
                if mean > 1.0:
                    break
        try:
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        except Exception:
            fourcc = w = h = -1
        cap.release()
        log('  %-16s opened=%-5s shape=%-16s mean=%-8s fourcc=%s %dx%d'
            % (path, opened, shape, mean, fourcc, w, h))
        if opened and mean is not None and mean > 1.0:
            usable.append(path)
    key('camera_usable_nodes', usable if usable else '无（都没读到有效帧）')
    key('camera_first_usable', usable[0] if usable else '无')
except Exception as e:
    key('camera_usable_nodes', '探测异常: %s: %s' % (type(e).__name__, e))

# =========================================================================
# E. V3 反射：工厂签名 / CameraConfig / DetectionConfig 字段真名（P0-9 / P0-10）
# =========================================================================
section('E. camera_vision_system_v3 反射（开关真名、字段真名、默认值）')

vs = None
try:
    import camera_vision_system_v3 as v3mod

    for fn in ('create_vision_system_v3', 'create_ai_detection_system', 'create_full_detection_system_v3'):
        f = getattr(v3mod, fn, None)
        if f is not None:
            log('  %s%s' % (fn, try_sig(f)))

    cfg_cls = getattr(v3mod, 'CameraConfig', None)
    if cfg_cls is not None:
        try:
            cfg = cfg_cls()
            key('CameraConfig_backup_camera_ids', getattr(cfg, 'backup_camera_ids', '<无该属性>'))
        except Exception as e:
            key('CameraConfig_backup_camera_ids', '实例化失败: %s: %s' % (type(e).__name__, e))

    vs = v3mod.create_vision_system_v3(camera_id=-1, width=1280, height=720,
                                       enable_basic=False, enable_advanced=False)
    key('v3_create_ok', True)

    dc = vs.detection_config
    try:
        import dataclasses
        fields = [f.name for f in dataclasses.fields(dc)]
    except Exception:
        fields = sorted([n for n in dir(dc) if not n.startswith('_')])

    enable_fields = sorted([n for n in fields if n.startswith('enable_')])
    key('DetectionConfig_class', type(dc).__name__)
    key('enable_switch_count', len(enable_fields))
    log('  enable_* 真名（%d 个）:' % len(enable_fields))
    for n in enable_fields:
        log('      %-32s = %s' % (n, getattr(dc, n, '<无>')))
    key('enable_has_yolov8', hasattr(dc, 'enable_yolov8'))
    key('enable_has_resnet', hasattr(dc, 'enable_resnet'))
    key('enable_has_object_detection', hasattr(dc, 'enable_object_detection'))
    key('enable_has_image_classification', hasattr(dc, 'enable_image_classification'))

    key('field_color_block_target', hasattr(dc, 'color_block_target'))
    key('field_color_block_target_color', hasattr(dc, 'color_block_target_color'))
    key('field_color_block_similarity', hasattr(dc, 'color_block_similarity'))
    key('color_block_target_value', getattr(dc, 'color_block_target', '<无>'))
    key('field_face_db_path', getattr(dc, 'face_db_path', '<无>'))
    key('field_object_db_path', getattr(dc, 'object_db_path', '<无>'))

    log('  --- 全部 DetectionConfig 字段（截断显示）---')
    for n in sorted(fields):
        try:
            log('      %-34s = %s' % (n, trunc(getattr(dc, n), 80)))
        except Exception:
            log('      %-34s = <读取失败>' % n)

    key('vs_has_cleanup', hasattr(vs, 'cleanup'))
    key('vs_has_stop_background_top', hasattr(vs, 'stop_background_detection'))
    key('open_camera_sig', try_sig(vs.open_camera))
except Exception as e:
    key('v3_create_ok', '失败: %s: %s' % (type(e).__name__, e))
    log(traceback.format_exc())

# =========================================================================
# F. V3 运行实测：初始化 7 步 / 色域坐标 / 回调 / collection 结构
# =========================================================================
section('F. V3 运行实测（7 步流程、640×480 坐标、回调、结果结构）')

if vs is None:
    log('  跳过：V3 实例未创建成功')
else:
    try:
        t0 = datetime.datetime.now()
        cam_ok = vs.open_camera()
        key('open_camera_return', cam_ok)
        key('open_camera_seconds', round((datetime.datetime.now() - t0).total_seconds(), 2))

        vs.detection_config.enable_color_recognition = True
        vs.detection_config.enable_color_block = True
        vs.detection_config.enable_face_recognition = True
        vs._init_detectors()

        # 区域坐标对照：一个 640×480 合法，一个按 1280×720 越界
        vs.detection_config.color_recognition_regions.append((50, 100, 200, 200))    # 合法
        vs.detection_config.color_recognition_regions.append((800, 200, 400, 400))   # 越界对照

        vs.threaded_system.start_background_detection(show_preview=False)
        key('start_background_detection', 'OK')

        ts = vs.threaded_system
        det_count = [0]
        frame_count = [0]
        last = {}

        def _on_det(res):
            det_count[0] += 1
            try:
                last.clear()
                last.update(res)
            except Exception:
                pass

        def _on_frame(frame, res):
            frame_count[0] += 1

        cb_ok = 'OK'
        try:
            ts.add_detection_callback(_on_det)
            ts.add_frame_callback(_on_frame)
        except Exception as e:
            cb_ok = '%s: %s' % (type(e).__name__, e)
        key('callback_register', cb_ok)

        time.sleep(6)
        key('callback_detection_in_6s', det_count[0])
        key('callback_frame_in_6s', frame_count[0])
        key('detection_dict_keys', len(last))
        log('  detection dict keys: %s' % sorted(list(last.keys())))

        try:
            ts.remove_callback('detection', _on_det)
            key('remove_callback_sig', 'remove_callback("detection", cb) 可用')
        except Exception as e1:
            try:
                ts.remove_callback(_on_det)
                key('remove_callback_sig', 'remove_callback(cb) 可用')
            except Exception as e2:
                key('remove_callback_sig', '两种都失败: %s | %s'
                    % (type(e1).__name__, type(e2).__name__))

        ra = vs.result_accessor
        try:
            ra.refresh_results()
        except Exception as e:
            key('refresh_results', '异常: %s: %s' % (type(e).__name__, e))

        try:
            latest = ts.get_latest_results()
            key('get_latest_results_type', type(latest).__name__)
            if isinstance(latest, dict):
                key('get_latest_results_keys', sorted(list(latest.keys())))
                info = latest.get('color_recognition') or {}
                if isinstance(info, dict):
                    key('color_recognition_image_info', info.get('image_info'))
                    regions = info.get('regions') or []
                    key('color_recognition_regions_count', len(regions))
                    for i, rg in enumerate(regions):
                        log('      region[%d] = %s' % (i, trunc(rg, 260)))
                cb = latest.get('color_block') or {}
                if isinstance(cb, dict):
                    key('color_block_detection_params', cb.get('detection_params'))
            else:
                log('      get_latest_results() = %s' % trunc(latest, 300))
        except Exception as e:
            key('get_latest_results_type', '异常: %s: %s' % (type(e).__name__, e))

        try:
            nxt = ts.get_next_result(timeout=0.5)
            key('get_next_result_type', type(nxt).__name__)
        except Exception as e:
            key('get_next_result_type', '异常: %s: %s' % (type(e).__name__, e))

        try:
            pend = ts.get_all_pending_results()
            key('get_all_pending_results_type', '%s len=%s'
                % (type(pend).__name__, len(pend) if hasattr(pend, '__len__') else '?'))
        except Exception as e:
            key('get_all_pending_results_type', '异常: %s: %s' % (type(e).__name__, e))

        log('  --- result_accessor 方法清单 ---')
        methods = public_methods(ra)
        log('      %s' % methods)
        key('result_accessor_method_count', len(methods))
        key('ra_has_get_object_name', 'get_object_name' in methods)
        key('ra_has_get_object_recognition_count', 'get_object_recognition_count' in methods)

        log('  --- 人脸相关 getter 返回值类型（P0-10）---')
        for name in ('get_face_count', 'get_face_id', 'get_face_name',
                     'get_face_confidence', 'get_face_position'):
            f = getattr(ra, name, None)
            if f is None:
                key('ra_has_%s' % name, False)
                continue
            try:
                v = f()
                key('%s_repr' % name, '%s (type=%s)' % (repr(v), type(v).__name__))
            except Exception as e:
                key('%s_repr' % name, '异常: %s: %s' % (type(e).__name__, e))

        try:
            key('has_face_id_return', repr(ra.has_face_id('__probe__')))
        except Exception as e:
            key('has_face_id_return', '异常: %s: %s' % (type(e).__name__, e))

        try:
            key('get_largest_color_block_index', repr(ra.get_largest_color_block_index()))
        except Exception as e:
            key('get_largest_color_block_index', '异常: %s: %s' % (type(e).__name__, e))

        for name in ('get_color_block_center',):
            f = getattr(ra, name, None)
            if f is not None:
                try:
                    key('%s(0)' % name, repr(f(0)))
                except Exception as e:
                    key('%s(0)' % name, '异常: %s: %s' % (type(e).__name__, e))

        log('  --- 清理 ---')
        for step in ('stop_background_detection', 'close_camera', 'cleanup'):
            f = getattr(vs, step, None)
            if f is None:
                f = getattr(ts, step, None)
            if f is None:
                log('      %s: 不存在' % step)
                continue
            try:
                f()
                log('      %s: OK' % step)
            except Exception as e:
                log('      %s: 异常 %s: %s' % (step, type(e).__name__, e))
    except Exception as e:
        key('v3_runtime', '异常: %s: %s' % (type(e).__name__, e))
        log(traceback.format_exc())

# =========================================================================
# G. ESP32 常量与方法（引脚数量、隐藏能力）
# =========================================================================
section('G. ESP32 模块（引脚常量、方法清单、串口连通）')

try:
    import ESP32 as esp
    consts = sorted([n for n in dir(esp) if n.startswith(('GPIO_IO', 'ADC_IO', 'GPIO_BUTTON',
                                                           'MA', 'MB', 'LED', 'SERVO'))])
    key('esp32_constants', consts)
    gpio = [c for c in consts if c.startswith('GPIO_IO')]
    adc = [c for c in consts if c.startswith('ADC_IO')]
    key('esp32_gpio_count', len(gpio))
    key('esp32_adc_count', len(adc))
    key('esp32_gpio_names', gpio)
    key('esp32_adc_names', adc)
    key('esp32_gpio_button', [c for c in consts if 'BUTTON' in c])

    cls = getattr(esp, 'ESP32', None)
    if cls is not None:
        methods = public_methods(cls)
        key('esp32_method_count', len(methods))
        log('  ESP32 方法清单:')
        log('      %s' % methods)
        for m in ('digitalRead', 'digitalWrite', 'analogRead', 'analogWrite', 'servo',
                  'ws2812Init', 'ws2812Write', 'dhtReadTemperature', 'ds18b20Read',
                  'ultrasonicRead', 'bmp280ReadPress', 'i2c_init', 'uart_init',
                  'digitalReadCallback', 'analogReadCallback'):
            key('esp32_has_%s' % m, m in methods)

    try:
        board = cls()
        started = board.start()
        key('esp32_board_start', started)
        try:
            board.stop()
        except Exception:
            pass
    except Exception as e:
        key('esp32_board_start', '异常: %s: %s' % (type(e).__name__, e))
except Exception as e:
    key('esp32_module', '导入失败: %s: %s' % (type(e).__name__, e))

# =========================================================================
# H. Line_Sensor
# =========================================================================
section('H. Line_Sensor 模块')

try:
    import Line_Sensor as ls
    key('line_sensor_module_members', sorted([n for n in dir(ls) if not n.startswith('_')]))
    cls = getattr(ls, 'Line_Sensor', None)
    if cls is None:
        cls = getattr(ls, 'LineSensor', None)
    if cls is not None:
        key('line_sensor_class', cls.__name__)
        key('line_sensor_methods', public_methods(cls))
    else:
        log('  未找到 Line_Sensor / LineSensor 类')
except Exception as e:
    key('line_sensor_module', '导入失败: %s: %s' % (type(e).__name__, e))

# =========================================================================
# I. audio_recorder（含 2 秒录音落盘测试）
# =========================================================================
section('I. audio_recorder（方法、默认参数、录音落盘）')

show_cmd('arecord -l 2>&1 | head -10', 'ALSA 录音设备')
show_cmd('aplay -l 2>&1 | head -10', 'ALSA 播放设备')

try:
    import audio_recorder as ar
    key('audio_recorder_members', sorted([n for n in dir(ar) if not n.startswith('_')]))
    cls = getattr(ar, 'AudioRecorder', None)
    if cls is not None:
        key('audio_recorder_methods', public_methods(cls))
        for m in ('record_fixed_duration', 'start', 'stop', 'save_audio',
                  'set_sample_rate', 'pause', 'is_recording'):
            key('audio_recorder_has_%s' % m, hasattr(cls, m))
        try:
            rec = cls()
            for attr in ('sample_rate', 'channels', 'dtype', 'format'):
                if hasattr(rec, attr):
                    key('audio_recorder_default_%s' % attr, getattr(rec, attr))
            if _TEST_AUDIO_RECORD:
                out_dir = 'recordings'
                try:
                    if not os.path.exists(out_dir):
                        os.makedirs(out_dir, exist_ok=True)
                except Exception:
                    out_dir = '.'
                wav = os.path.join(out_dir, '_probe_%ss.wav' % _AUDIO_RECORD_SECONDS)
                attempts = [
                    ('record_fixed_duration(%d, filename=...)' % _AUDIO_RECORD_SECONDS,
                     lambda: rec.record_fixed_duration(_AUDIO_RECORD_SECONDS, filename=wav)),
                    ('record_fixed_duration(%d, file_path=...)' % _AUDIO_RECORD_SECONDS,
                     lambda: rec.record_fixed_duration(_AUDIO_RECORD_SECONDS, file_path=wav)),
                    ('record_fixed_duration(%d)' % _AUDIO_RECORD_SECONDS,
                     lambda: rec.record_fixed_duration(_AUDIO_RECORD_SECONDS)),
                ]
                done = None
                for label, fn in attempts:
                    try:
                        res = fn()
                        done = label
                        key('audio_record_result', '%s -> 返回类型=%s' % (label, type(res).__name__))
                        break
                    except TypeError as e:
                        log('      %s 参数不匹配: %s' % (label, e))
                    except Exception as e:
                        key('audio_record_result', '%s 失败: %s: %s' % (label, type(e).__name__, e))
                        break
                if done is None:
                    key('audio_record_result', '三种调用方式都不成立（看上方参数不匹配日志）')
                key('audio_record_wav_exists', os.path.exists(wav))
                key('audio_record_wav_size', os.path.getsize(wav) if os.path.exists(wav) else 0)
        except Exception as e:
            key('audio_recorder_instance', '异常: %s: %s' % (type(e).__name__, e))
except Exception as e:
    key('audio_recorder_module', '导入失败: %s: %s' % (type(e).__name__, e))

# =========================================================================
# J. audio_player（确认有无 play()）
# =========================================================================
section('J. audio_player 全反射（确认是否存在 play()）')

try:
    import audio_player as ap
    key('audio_player_members', sorted([n for n in dir(ap) if not n.startswith('_')]))
    cls = getattr(ap, 'AudioPlayer', None)
    if cls is not None:
        methods = public_methods(cls)
        key('audio_player_methods', methods)
        key('audio_player_has_play', 'play' in methods)
        key('audio_player_has_play_file', 'play_file' in methods)
        key('audio_player_has_play_audio', 'play_audio' in methods)
        for m in ('pause', 'resume', 'stop', 'set_volume', 'seek'):
            key('audio_player_has_%s' % m, m in methods)
        for m in methods:
            log('      %-24s %s' % (m, try_sig(getattr(cls, m))))
except Exception as e:
    key('audio_player_module', '导入失败: %s: %s' % (type(e).__name__, e))

# =========================================================================
# K. text_recognition（API 面）
# =========================================================================
section('K. text_recognition（类方法 + 模块级函数）')

try:
    tr = _TEXT_RECOGNITION_MOD
    if tr is None:
        key('text_recognition_module', '导入失败（在 cv2/pygame/V3 之前抢注册时）: %s'
            % _TEXT_RECOGNITION_ERR)
    else:
        key('text_recognition_module', 'OK（已在 cv2/pygame/V3 之前成功导入）')
        key('text_recognition_module_members',
            sorted([n for n in dir(tr) if not n.startswith('_')]))
        cls = getattr(tr, 'TextRecognizer', None)
        if cls is not None:
            methods = public_methods(cls)
            key('text_recognizer_methods', methods)
            for m in ('set_language', 'set_region', 'angle_classify'):
                key('text_recognizer_has_%s' % m, m in methods)
            if hasattr(cls, 'recognize_text'):
                key('text_recognizer_recognize_text_sig', try_sig(getattr(cls, 'recognize_text')))
            try:
                inst = cls()
                key('text_recognizer_instantiate', 'OK')
                try:
                    del inst
                except Exception:
                    pass
            except Exception as e:
                key('text_recognizer_instantiate', '异常: %s: %s' % (type(e).__name__, e))
        else:
            log('  未找到 TextRecognizer 类')
except Exception as e:
    key('text_recognition_section', '异常: %s: %s' % (type(e).__name__, e))

# =========================================================================
# L. voice_api（只反射，不联网）
# =========================================================================
section('L. voice_api 反射（不发起网络请求）')

try:
    import voice_api as va
    key('voice_api_members', sorted([n for n in dir(va) if not n.startswith('_')]))
    cls = getattr(va, 'VoiceAPI', None)
    if cls is not None:
        methods = public_methods(cls)
        key('voice_api_methods', methods)
        for m in ('llm_chat', 'llm_chat_znbw_2025', 'voice_recognition',
                  'tts_synthesize', 'get_token', 'refresh_token'):
            key('voice_api_has_%s' % m, m in methods)
    for const in ('API_BASE_URL', 'API_VOICE_URL', 'TOKEN_FILE_PATH'):
        key('voice_api_%s' % const, getattr(va, const, '<无>'))
    tok = getattr(va, 'TOKEN_FILE_PATH', '/tmp/.system_cache/config.json')
    key('voice_api_token_file_exists', os.path.exists(tok))
except Exception as e:
    key('voice_api_module', '导入失败: %s: %s' % (type(e).__name__, e))

# =========================================================================
# M. 显示能力（1920×1280 上限是否成立）
# =========================================================================
section('M. 显示能力（窗口最大尺寸核对）')

show_cmd('DISPLAY=:0 xrandr 2>&1 | head -20 || echo "(DISPLAY=:0 不可用)"', 'xrandr (DISPLAY=:0)')
show_cmd('xrandr 2>&1 | head -20 || echo "(当前环境无 DISPLAY)"', 'xrandr (继承环境)')
show_cmd('DISPLAY=:0 xdpyinfo 2>/dev/null | grep -E "dimensions|resolution" | head -5 || echo "(xdpyinfo 不可用)"', 'xdpyinfo')

# =========================================================================
# N. 结论速览
# =========================================================================
section('N. 结论速览（便于快速核对）')
for name, value in _RESULT:
    log('  %-38s | %s' % (name, value))

log('')
log('=' * 68)
log('探测结束: %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
log('日志文件（请把这个文件发回）: %s' % os.path.abspath(_LOG_FILE))
log('=' * 68)

try:
    sys.stdout = _ORIG_OUT
    sys.stderr = _ORIG_ERR
    _TEE.flush()
    _TEE.fp.close()
except Exception:
    pass
