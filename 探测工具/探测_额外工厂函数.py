# camera_vision_system_v3 额外工厂函数用途探测程序
# 在好搭AI派设备上运行：python3 探测_额外工厂函数.py
# 作用：获取 create_ai_detection_system / create_full_detection_system_v3
#       以及模块中其他 demo_* / test_* 函数的签名、文档字符串和源码，
#       以便准确判断其用途。

import os
import sys
import inspect
from datetime import datetime

# ---------- 日志输出配置 ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

PROGRAM_NAME = "探测_额外工厂函数"
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


def probe_function(func, name):
    """探测单个函数的签名、文档字符串和源码。"""
    print(f"\n>>> 函数名: {name}")
    print(f"    类型: {type(func)}")

    # 1. 签名
    try:
        sig = inspect.signature(func)
        print(f"    签名: {name}{sig}")
        print("    参数详情:")
        for pname, param in sig.parameters.items():
            print(f"      - {pname}: 默认值={param.default}, "
                  f"标注={param.annotation}, kind={param.kind.name}")
    except (ValueError, TypeError) as e:
        print(f"    签名不可获取: {e}")

    # 2. 返回值标注
    try:
        sig = inspect.signature(func)
        print(f"    返回标注: {sig.return_annotation}")
    except Exception:
        pass

    # 3. 文档字符串
    doc = inspect.getdoc(func)
    if doc:
        print("    文档字符串:")
        for line in doc.split("\n"):
            print(f"      | {line}")
    else:
        print("    文档字符串: (无)")

    # 4. 源代码（如果可获取）
    try:
        source = inspect.getsource(func)
        # 限制长度，避免过长
        source_lines = source.split("\n")
        if len(source_lines) > 80:
            print(f"    源代码 (前80行，共{len(source_lines)}行):")
            for line in source_lines[:80]:
                print(f"      | {line}")
            print(f"      | ... (省略 {len(source_lines) - 80} 行)")
        else:
            print(f"    源代码 ({len(source_lines)}行):")
            for line in source_lines:
                print(f"      | {line}")
    except (OSError, TypeError) as e:
        print(f"    源代码不可获取: {e}")

    # 5. 所属模块与文件
    try:
        mod = inspect.getmodule(func)
        if mod:
            print(f"    所属模块: {mod.__name__}")
        file = inspect.getfile(func)
        print(f"    源文件: {file}")
    except (OSError, TypeError) as e:
        print(f"    模块/文件信息不可获取: {e}")


# ---------- 探测开始 ----------
print(f"\n[探测开始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
print(f"[日志文件] {LOG_FILE}")

log_section("第1步：导入库")
import camera_vision_system_v3 as cvs3

log_section("第2步：探测三个 create_* 工厂函数")
factory_funcs = [
    "create_vision_system_v3",
    "create_ai_detection_system",
    "create_full_detection_system_v3",
]
for fname in factory_funcs:
    func = getattr(cvs3, fname, None)
    if func is None:
        print(f"\n>>> {fname}: 不存在")
        continue
    if not callable(func):
        print(f"\n>>> {fname}: 非可调用对象 ({type(func)})")
        continue
    probe_function(func, fname)

log_section("第3步：探测所有 demo_* / test_* / interactive_* 函数")
util_funcs = [
    "demo_ai_detection",
    "demo_basic_detection_v3",
    "demo_comprehensive_detection_v3",
    "demo_people_counter",
    "demo_plate_recognition_detection",
    "interactive_demo_v3",
    "test_all_features_v3",
    "_test_single_camera",
]
for fname in util_funcs:
    func = getattr(cvs3, fname, None)
    if func is None:
        print(f"\n>>> {fname}: 不存在")
        continue
    if not callable(func):
        print(f"\n>>> {fname}: 非可调用对象 ({type(func)})")
        continue
    probe_function(func, fname)

log_section("第4步：探测工具类 CameraConfig / DetectionConfig 的字段")
# CameraConfig
try:
    cc = cvs3.CameraConfig
    print("\n>>> CameraConfig 类:")
    print(f"    类型: {cc}")
    try:
        sig = inspect.signature(cc)
        print(f"    构造签名: {sig}")
    except (ValueError, TypeError) as e:
        print(f"    构造签名不可获取: {e}")
    doc = inspect.getdoc(cc)
    if doc:
        print("    文档字符串:")
        for line in doc.split("\n")[:30]:
            print(f"      | {line}")
    # 尝试创建实例看字段
    try:
        instance = cc()
        fields = [a for a in dir(instance) if not a.startswith("_")]
        print(f"    实例字段: {fields}")
        for f in fields:
            try:
                val = getattr(instance, f)
                print(f"      {f} = {val!r}")
            except Exception:
                pass
    except Exception as e:
        print(f"    无法实例化: {e}")
except Exception as e:
    print(f"CameraConfig 探测失败: {e}")

# DetectionConfig
try:
    dc = cvs3.DetectionConfig
    print("\n>>> DetectionConfig 类:")
    print(f"    类型: {dc}")
    doc = inspect.getdoc(dc)
    if doc:
        print("    文档字符串:")
        for line in doc.split("\n")[:50]:
            print(f"      | {line}")
    try:
        instance = dc()
        fields = [a for a in dir(instance) if not a.startswith("_")]
        print(f"    实例字段: {fields}")
    except Exception as e:
        print(f"    无法实例化: {e}")
except Exception as e:
    print(f"DetectionConfig 探测失败: {e}")

log_section("第5步：探测异常类层级")
exception_classes = [
    "CameraNotFoundError", "CameraStatus",
]
for ename in exception_classes:
    cls = getattr(cvs3, ename, None)
    if cls is None:
        print(f"\n>>> {ename}: 不存在")
        continue
    print(f"\n>>> {ename}:")
    print(f"    类型: {cls}")
    print(f"    MRO: {[c.__name__ for c in cls.__mro__]}")
    doc = inspect.getdoc(cls)
    if doc:
        print(f"    文档: {doc.split(chr(10))[0]}")

log_section("第6步：列出全部模块成员的 callable 分类")
print("\n可调用成员（函数/类）:")
callables = [m for m in dir(cvs3)
             if not m.startswith("__") and callable(getattr(cvs3, m, None))]
for m in callables:
    obj = getattr(cvs3, m)
    kind = "类" if inspect.isclass(obj) else "函数"
    try:
        sig = inspect.signature(obj)
        print(f"  [{kind}] {m}{sig}")
    except (ValueError, TypeError):
        print(f"  [{kind}] {m}(...)  [签名不可获取]")

print("\n非可调用成员（常量/标志）:")
non_callables = [m for m in dir(cvs3)
                 if not m.startswith("__") and not callable(getattr(cvs3, m, None))]
for m in non_callables:
    try:
        val = getattr(cvs3, m)
        print(f"  {m} = {val!r}")
    except Exception as e:
        print(f"  {m}: 读取失败 {e}")

print()
print("=" * 70)
print(f"探测完成 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
print(f"日志已写入: {LOG_FILE}")
print("=" * 70)

_tee.close()
sys.stdout = _tee._console
