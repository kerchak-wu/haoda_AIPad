# 好搭AI派系统环境探测程序
# 在好搭AI派设备上运行：python3 探测_系统环境.py
# 作用：一次性收集操作系统、Python、pip、磁盘、CPU、NPU/RKNN、
#       已预装三方库、V4L2设备、音频设备、关键环境变量、核心库版本等
#       17 项环境信息，便于后续兼容性判断与排障。
# 输出：同时打印到控制台并追加写入 logs/探测_系统环境_YYYYMMDD.log

import os
import sys
import platform
import subprocess
import shutil
import glob
from datetime import datetime

# ---------- 日志输出配置 ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

PROGRAM_NAME = "探测_系统环境"
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


def run(cmd, timeout=15, strip=True, check_exitcode=False):
    """运行 shell 命令并返回 (stdout, stderr, returncode)。"""
    try:
        p = subprocess.run(
            cmd, shell=True, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace"
        )
        out = p.stdout.strip() if strip else p.stdout
        err = p.stderr.strip() if strip else p.stderr
        return out, err, p.returncode
    except subprocess.TimeoutExpired:
        return "", "[超时]", -1
    except FileNotFoundError as e:
        return "", f"[命令不存在] {e}", 127
    except Exception as e:
        return "", f"[执行异常] {type(e).__name__}: {e}", -2


def print_run(label, cmd, expected_code=None, show_stderr=False):
    out, err, code = run(cmd)
    ok_marker = "[OK]" if (expected_code is None or code == expected_code) else f"[ERR code={code}]"
    print(f"  {ok_marker} {label}")
    if out:
        # 最多显示 50 行
        lines = out.splitlines()
        for line in lines[:50]:
            print(f"      {line}")
        if len(lines) > 50:
            print(f"      ... 共 {len(lines)} 行，省略后 {len(lines)-50} 行")
    if show_stderr and err:
        print(f"      [stderr] {err[:500]}")
    return out, err, code


def check_file(path):
    exists = os.path.exists(path)
    if exists:
        size = os.path.getsize(path)
        print(f"  [存在] {path}  大小={size:,} 字节")
    else:
        print(f"  [  ] {path}")
    return exists


def check_glob(pattern, label, max_show=20):
    files = sorted(glob.glob(pattern))
    print(f"  glob: {pattern}  -> 匹配 {len(files)} 个")
    for f in files[:max_show]:
        try:
            size = os.path.getsize(f)
            print(f"      {f}  ({size:,} 字节)")
        except OSError:
            print(f"      {f}")
    if len(files) > max_show:
        print(f"      ... 省略 {len(files) - max_show} 个")
    return files


def try_import(name):
    try:
        mod = __import__(name)
        ver = getattr(mod, "__version__", "未知")
        path = getattr(mod, "__file__", "未知")
        print(f"  [OK] import {name:30s}  版本={ver}  路径={path}")
        return True, mod
    except Exception as e:
        print(f"  [  ] import {name:30s}  失败: {type(e).__name__}: {e}")
        return False, None


# ---------- 探测开始 ----------
print(f"\n[探测开始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
print(f"[日志文件] {LOG_FILE}")
print(f"[工作目录] {SCRIPT_DIR}")

# ================================================================
# 第1步：操作系统与内核
# ================================================================
log_section("第1步：操作系统 / 发行版 / 内核 / 架构")
print(f"  platform.system()     = {platform.system()}")
print(f"  platform.release()    = {platform.release()}")
print(f"  platform.version()    = {platform.version()}")
print(f"  platform.machine()    = {platform.machine()}")
print(f"  platform.architecture = {platform.architecture()}")
print(f"  platform.node()       = {platform.node()}")
print(f"  sys.platform          = {sys.platform}")
print_run("uname -a", "uname -a")
print_run("cat /proc/version", "cat /proc/version 2>/dev/null || echo '无 /proc/version'")
for rel in ["/etc/os-release", "/etc/lsb-release", "/etc/issue", "/etc/build.prop"]:
    check_file(rel)
    if os.path.exists(rel) and os.path.getsize(rel) < 20000:
        out, _, _ = run(f"cat {rel}")
        if out:
            for line in out.splitlines():
                print(f"      {line}")

# ================================================================
# 第2步：CPU 信息
# ================================================================
log_section("第2步：CPU / 处理器信息")
print_run("nproc (逻辑核心数)", "nproc --all 2>/dev/null || echo 'nproc不可用'")
print_run("lscpu (精简)", "lscpu 2>/dev/null | head -30 || echo 'lscpu不可用'")
print_run("cat /proc/cpuinfo (前30行)", "cat /proc/cpuinfo 2>/dev/null | head -30 || echo '无 /proc/cpuinfo'")

# ================================================================
# 第3步：内存信息
# ================================================================
log_section("第3步：内存 / 交换区")
print_run("free -h", "free -h 2>/dev/null || echo 'free 不可用'")
print_run("cat /proc/meminfo (前20行)", "cat /proc/meminfo 2>/dev/null | head -20 || echo '无'")

# ================================================================
# 第4步：磁盘空间
# ================================================================
log_section("第4步：磁盘 / 分区空间")
print_run("df -h", "df -h 2>/dev/null || echo 'df 不可用'")
print_run("当前目录所在分区使用情况", f"df -h \"{SCRIPT_DIR}\" 2>/dev/null || echo 'df 不可用'")
print()
print("  关键目录大小估算（前 20 项中的大目录）：")
for d in [SCRIPT_DIR, os.path.expanduser("~"), "/usr/lib", "/opt"]:
    if os.path.isdir(d):
        out, _, _ = run(f"du -sh \"{d}\" 2>/dev/null")
        print(f"    {d}: {out or 'du不可用或无权限'}")

# ================================================================
# 第5步：Python 精确版本 + 编译信息
# ================================================================
log_section("第5步：Python 精确版本 / 可执行路径 / 编译信息")
print(f"  sys.version           = {sys.version}")
print(f"  sys.version_info      = {sys.version_info}")
print(f"  sys.executable        = {sys.executable}")
print(f"  sys.prefix            = {sys.prefix}")
print(f"  sys.base_prefix       = {sys.base_prefix}")
print(f"  sys.path[0..5]        = {sys.path[:6]}")
print(f"  platform.python_ver   = {platform.python_version()}")
print(f"  platform.python_comp  = {platform.python_compiler()}")
print(f"  64位?                 = {sys.maxsize > 2**32}")
print()
print_run("python3 --version", "python3 --version 2>&1")
print_run("which python3", "which python3 2>/dev/null || echo '无 which'")
print_run("有没有 python3.11 等其他版本?", "ls /usr/bin/python* 2>/dev/null; ls /usr/local/bin/python* 2>/dev/null || echo '无其他python'")

# ================================================================
# 第6步：pip 列表（已预装包，前 60 + 关键包筛选）
# ================================================================
log_section("第6步：pip 已安装包（前 60 条）")
out, _, _ = run("python3 -m pip list --format=columns 2>/dev/null || pip list --format=columns 2>/dev/null")
if out:
    lines = out.splitlines()
    print(f"  共 {len(lines)} 行，显示前 60 行：")
    for line in lines[:60]:
        print(f"    {line}")
    if len(lines) > 60:
        print(f"    ... 另有 {len(lines)-60} 个包，请查看日志文件")
else:
    print("  [失败] 无法获取 pip list")

# ================================================================
# 第7步：核心三方库可导入性 + 版本
# ================================================================
log_section("第7步：核心三方库可导入性 / 版本检查")
KEY_LIBS = [
    "pygame", "cv2", "numpy", "mediapipe", "paddleocr", "paddle",
    "ultralytics", "PIL", "aip", "requests", "paho.mqtt",
    "serial", "rknnlite2", "rknn", "onnx", "onnxruntime",
    "torch", "torchvision", "dlib", "face_recognition",
    "scipy", "sklearn", "pandas",
]
for name in KEY_LIBS:
    try_import(name)

# ================================================================
# 第8步：Rockchip RKNN / NPU 相关
# ================================================================
log_section("第8步：Rockchip RKNN 运行库 / NPU 状态")
check_glob("/usr/lib/librknn*", "librknn*")
check_glob("/usr/local/lib/librknn*", "/usr/local/lib/librknn*")
check_glob("/usr/lib/*rknn*.so*", "rknn*.so")
for path in [
    "/dev/rknpu", "/dev/rknpu0", "/dev/rknpu1",
    "/sys/class/misc/rknpu", "/sys/class/devfreq/fdab0000.npu",
]:
    check_file(path)
# rknnlite2 详细探测
ok, mod = try_import("rknnlite2")
if ok and mod is not None:
    try:
        rk = getattr(mod, "RKNNLite", None)
        if rk:
            print(f"    RKNNLite 类存在，公共方法: {[m for m in dir(rk) if not m.startswith('_')][:30]}")
    except Exception as e:
        print(f"    RKNNLite 枚举失败: {e}")
# 检查 rockchip 预转模型目录
for model_dir in [
    "/usr/share/rknn", "/opt/rknn-models",
    os.path.expanduser("~/rknn-models"),
]:
    if os.path.isdir(model_dir):
        print(f"  [发现模型目录] {model_dir}，列出前 20 个文件：")
        try:
            for f in sorted(os.listdir(model_dir))[:20]:
                fp = os.path.join(model_dir, f)
                sz = os.path.getsize(fp) if os.path.isfile(fp) else "<dir>"
                print(f"    {f}  ({sz})")
        except OSError as e:
            print(f"    列表失败: {e}")

# ================================================================
# 第9步：V4L2 视频设备（摄像头）
# ================================================================
log_section("第9步：V4L2 视频设备列表")
check_glob("/dev/video*", "video 设备")
print()
for dev in sorted(glob.glob("/dev/video*")):
    out, err, _ = run(f"v4l2-ctl -d {dev} --info 2>/dev/null || echo 'v4l2-ctl 不可用，尝试 cat 名称'")
    if not out:
        out, _, _ = run(f"udevadm info -q property -n {dev} 2>/dev/null | grep -E 'DEVNAME|ID_V4L|SERIAL' | head -10")
    print(f"  {dev}:")
    for line in (out or "(无信息)").splitlines()[:15]:
        print(f"      {line}")

# ================================================================
# 第10步：音频设备（播放/录音）
# ================================================================
log_section("第10步：音频设备（播放 + 录音）")
print_run("aplay -l (播放设备)", "aplay -l 2>/dev/null || echo 'aplay不可用'")
print_run("arecord -l (录音设备)", "arecord -l 2>/dev/null || echo 'arecord不可用'")
print_run("pactl list sinks short", "pactl list sinks short 2>/dev/null || echo 'pactl不可用'")
print_run("pactl list sources short", "pactl list sources short 2>/dev/null || echo 'pactl不可用'")

# ================================================================
# 第11步：环境变量（关键项）
# ================================================================
log_section("第11步：关键环境变量")
KEY_ENV = [
    "LIBGL_ALWAYS_SOFTWARE", "DISPLAY", "WAYLAND_DISPLAY",
    "SDL_VIDEODRIVER", "SDL_AUDIODRIVER",
    "PYTHONPATH", "LD_LIBRARY_PATH",
    "PATH", "HOME", "USER", "LANG",
    "http_proxy", "https_proxy", "no_proxy",
]
for k in KEY_ENV:
    v = os.environ.get(k)
    if v is None:
        print(f"  [未设置] {k}")
    else:
        # PATH 类太长时截断
        if len(v) > 300:
            v = v[:297] + "..."
        print(f"  [已设置] {k} = {v}")

# ================================================================
# 第12步：好搭 AI 派关键官方库可导入性
# ================================================================
log_section("第12步：好搭AI派官方库可导入性检查")
OFFICIAL_LIBS = [
    "camera_vision_system_v3", "ESP32", "Line_Sensor",
    "voice_api", "audio_recorder", "audio_player", "text_recognition",
]
for name in OFFICIAL_LIBS:
    ok, mod = try_import(name)
    if ok and mod is not None:
        file = getattr(mod, "__file__", "内置")
        print(f"      位置: {file}")

# ================================================================
# 第13步：pygame 子系统版本 / 显示驱动
# ================================================================
log_section("第13步：Pygame / SDL 子系统信息")
ok, pg = try_import("pygame")
if ok and pg is not None:
    try:
        if not hasattr(pg, "display"):
            pg.display.init()
        print(f"    pygame version     = {pg.__version__ if hasattr(pg, '__version__') else '未知'}")
        print(f"    pygame SDL 版本    = {pg.get_sdl_version() if hasattr(pg, 'get_sdl_version') else '未知'}")
        try:
            info = pg.display.Info()
            print(f"    当前显示驱动: {info}")
        except Exception as e:
            print(f"    display.Info() 失败 (可能无显示): {e}")
        # 列出可用显示模式
        try:
            modes = pg.display.list_modes()
            print(f"    list_modes: {modes[:10] if isinstance(modes, list) else modes}")
        except Exception as e:
            print(f"    list_modes 失败: {e}")
    except Exception as e:
        print(f"    pygame 探测失败: {e}")

# ================================================================
# 第14步：网络 / WiFi 状态
# ================================================================
log_section("第14步：网络接口 / 连通性")
print_run("ip -br addr (接口速览)", "ip -br addr 2>/dev/null || ifconfig -s 2>/dev/null || echo 'ip/ifconfig 不可用'")
print_run("路由表（默认网关）", "ip route 2>/dev/null | head -10 || route -n 2>/dev/null || echo '无 route'")
print_run("DNS 解析测试 (baidu.com)", "nslookup baidu.com 2>/dev/null | head -15 || host baidu.com 2>/dev/null | head -15 || echo 'nslookup/host 不可用'")
print_run("外网连通 (baidu.com 80)", "timeout 3 bash -c 'cat < /dev/null > /dev/tcp/baidu.com/80 && echo OK_BAIDU || echo FAIL_BAIDU' 2>&1 || echo 'TCP 测试 shell 不支持'")
print_run("外网连通 (aliyun.com 80)", "timeout 3 bash -c 'cat < /dev/null > /dev/tcp/aliyun.com/80 && echo OK_ALI || echo FAIL_ALI' 2>&1 || echo 'TCP 测试 shell 不支持'")

# ================================================================
# 第15步：系统已装的 CLI 工具（ffmpeg/pip/git/v4l2-ctl 等）
# ================================================================
log_section("第15步：常用 CLI 工具可用性")
CLI_TOOLS = [
    "python3", "pip", "pip3", "ffmpeg", "ffprobe", "git",
    "v4l2-ctl", "aplay", "arecord", "scp", "ssh", "wget", "curl",
    "unzip", "tar", "gzip", "nproc", "lscpu", "df", "free",
]
for tool in CLI_TOOLS:
    path = shutil.which(tool)
    if path:
        print(f"  [OK] {tool:15s} -> {path}")
    else:
        print(f"  [  ] {tool:15s} 未找到")

# ================================================================
# 第16步：关键目录写入权限
# ================================================================
log_section("第16步：关键目录写入权限 / 空间可用性")
test_dirs = [
    SCRIPT_DIR,
    LOG_DIR,
    os.path.expanduser("~"),
    "/tmp",
]
for d in test_dirs:
    probe = os.path.join(d, f".probe_write_{TODAY_STR}_{os.getpid()}.tmp")
    try:
        with open(probe, "w") as f:
            f.write("ok\n")
        os.unlink(probe)
        print(f"  [可写] {d}")
    except Exception as e:
        print(f"  [不可写] {d}: {type(e).__name__}: {e}")

# ================================================================
# 第17步：ESP32 串口 / 设备存在性
# ================================================================
log_section("第17步：ESP32 / 串口设备探测")
check_glob("/dev/ttyUSB*", "串口 USB")
check_glob("/dev/ttyACM*", "串口 ACM")
check_glob("/dev/ttyS*", "板载串口（显示前 5 个）", max_show=5)
out, _, _ = run("ls -l /dev/serial/by-id 2>/dev/null || echo '无 by-id 目录'")
if out and out != "无 by-id 目录":
    print("  /dev/serial/by-id 列表：")
    for line in out.splitlines():
        print(f"    {line}")

# ---------- 收尾 ----------
print()
print("=" * 70)
print(f"探测完成 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
print(f"日志已写入: {LOG_FILE}")
print("=" * 70)

_tee.close()
sys.stdout = _tee._console
