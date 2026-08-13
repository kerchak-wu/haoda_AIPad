# camera_vision_system_v3 库功能探测程序
# 在好搭AI派设备上运行：python3 探测_vision_system_v3.py
# 作用：列出库的工厂函数签名、视觉系统实例的全部属性方法、
#       detection_config / threaded_system / result_accessor 的成员，
#       以便核对文档分析是否完整准确。
# 输出：同时打印到控制台并追加写入 logs/探测_vision_system_v3_YYYYMMDD.log

import os
import sys
import inspect
from datetime import datetime

# ---------- 日志输出配置 ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

PROGRAM_NAME = "探测_vision_system_v3"
TODAY_STR = datetime.now().strftime("%Y%m%d")
LOG_FILE = os.path.join(LOG_DIR, f"{PROGRAM_NAME}_{TODAY_STR}.log")


class Tee:
    """同时写入控制台与日志文件（追加模式）。"""
    def __init__(self, log_path):
        self._console = sys.stdout
        # 追加模式 'a'，符合工程约定
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


# ---------- 探测开始 ----------
print(f"\n[探测开始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
print(f"[日志文件] {LOG_FILE}")

log_section("第1步：导入库并查看模块成员")
import camera_vision_system_v3 as cvs3

module_members = [m for m in dir(cvs3) if not m.startswith("__")]
print("模块级成员：", module_members)

log_section("第2步：create_vision_system_v3 函数签名")
try:
    sig = inspect.signature(cvs3.create_vision_system_v3)
    print("签名：", sig)
    print("参数详情：")
    for name, param in sig.parameters.items():
        print(f"  - {name}: 默认值={param.default}, 类型标注={param.annotation}")
except Exception as e:
    print("无法获取签名：", e)

log_section("第3步：创建视觉系统实例（不打开摄像头）")
try:
    vision_system = cvs3.create_vision_system_v3(
        camera_id=-1, width=1280, height=720,
        enable_basic=False, enable_advanced=False
    )
    print("创建成功:", vision_system)
    print("类型:", type(vision_system))
except Exception as e:
    print("创建失败：", e)
    _tee.close()
    raise SystemExit(1)

log_section("第4步：vision_system 实例的全部公共成员")
vs_members = [m for m in dir(vision_system) if not m.startswith("_")]
print("公共成员：", vs_members)
print()
print("私有成员（以_开头，便于发现内部接口）：")
private_members = [m for m in dir(vision_system) if m.startswith("_") and not m.startswith("__")]
print("  ", private_members)

log_section("第5步：detection_config 的全部属性")
try:
    dc = vision_system.detection_config
    print("detection_config 类型:", type(dc))
    dc_members = [m for m in dir(dc) if not m.startswith("_")]
    print("全部成员：", dc_members)
    print()
    print("当前 enable_* 开关值：")
    for m in dc_members:
        if m.startswith("enable_"):
            try:
                val = getattr(dc, m)
                print(f"  {m} = {val}")
            except Exception as e:
                print(f"  {m}: 读取失败 {e}")
except Exception as e:
    print("detection_config 访问失败：", e)

log_section("第6步：threaded_system 的全部方法")
try:
    ts = vision_system.threaded_system
    print("threaded_system 类型:", type(ts))
    ts_members = [m for m in dir(ts) if not m.startswith("_")]
    print("全部成员：", ts_members)
    print()
    print("方法签名：")
    for m in ts_members:
        attr = getattr(ts, m, None)
        if callable(attr):
            try:
                sig = inspect.signature(attr)
                print(f"  {m}{sig}")
            except (ValueError, TypeError):
                print(f"  {m}(...)  [签名不可获取]")
except Exception as e:
    print("threaded_system 访问失败：", e)

log_section("第7步：result_accessor 的全部方法")
try:
    ra = vision_system.result_accessor
    print("result_accessor 类型:", type(ra))
    ra_members = [m for m in dir(ra) if not m.startswith("_")]
    print("全部成员：", ra_members)
    print()
    print("方法签名：")
    for m in ra_members:
        attr = getattr(ra, m, None)
        if callable(attr):
            try:
                sig = inspect.signature(attr)
                print(f"  {m}{sig}")
            except (ValueError, TypeError):
                print(f"  {m}(...)  [签名不可获取]")
except Exception as e:
    print("result_accessor 访问失败：", e)

log_section("第8步：vision_system 关键方法签名")
key_methods = [
    "open_camera", "capture_frame", "process_one_frame", "cleanup",
    "learn_new_face", "add_object_recognition_class",
    "add_object_recognition_sample",
]
for m in key_methods:
    attr = getattr(vision_system, m, None)
    if attr is None:
        print(f"  {m}: 不存在")
        continue
    if callable(attr):
        try:
            sig = inspect.signature(attr)
            print(f"  {m}{sig}")
        except (ValueError, TypeError):
            print(f"  {m}(...)  [签名不可获取]")
    else:
        print(f"  {m} = {attr} (非方法)")

log_section("第9步：探测是否存在文档未记录的管理接口")
candidate_methods = [
    "delete_face", "clear_face_database", "get_face_database_info",
    "get_face_name", "get_face_list", "set_face_name",
    "delete_object_class", "clear_object_database", "get_object_database_info",
    "stop_background_detection", "stop_detection", "set_camera_resolution",
    "get_camera_frame_rate", "set_detection_threshold",
]
for m in candidate_methods:
    exists = hasattr(vision_system, m)
    print(f"  vision_system.{m}: {'存在' if exists else '不存在'}")
    if exists:
        attr = getattr(vision_system, m)
        if callable(attr):
            try:
                sig = inspect.signature(attr)
                print(f"    签名: {m}{sig}")
            except (ValueError, TypeError):
                print(f"    签名不可获取")

print()
print("=" * 70)
print(f"探测完成 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
print(f"日志已写入: {LOG_FILE}")
print("=" * 70)

_tee.close()
sys.stdout = _tee._console
