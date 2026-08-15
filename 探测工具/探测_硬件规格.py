# -*- coding: utf-8 -*-
"""
探测_硬件规格 - 好搭AI派
功能：核验设备硬件规格参数（SoC/CPU/GPU/NPU/WiFi/蓝牙/屏幕/音频/传感器/电池/ESP32）
目的：用于核对厂商宣传资料与实际硬件是否一致
依赖：仅用标准库（os/sys/platform/subprocess/glob/datetime），无需额外安装
输出：logs/探测_硬件规格_YYYYMMDD.log
"""

import os
import sys
import platform
import subprocess
import glob
import datetime
from datetime import datetime as _dt

# ===== 日志标准模式（追加写 + 块缓冲 + stdout 分路）=====
_LOG_DIR = 'logs'
if not os.path.exists(_LOG_DIR):
    os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(
    _LOG_DIR,
    '探测_硬件规格_%s.log' % _dt.now().strftime('%Y%m%d')
)


class _Tee:
    """同时写入控制台与日志文件（追加模式 + 块缓冲）。"""
    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log = open(file_path, 'a', buffering=-1, encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()


sys.stdout = _Tee(_LOG_FILE)
sys.stderr = sys.stdout  # 重定向 stderr 到 stdout，避免终端标红

# ===== 探测开始 =====
print('=' * 70)
print('好搭AI派 · 硬件规格探测程序')
print('探测时间：%s' % _dt.now().strftime('%Y-%m-%d %H:%M:%S'))
print('日志文件：%s' % _LOG_FILE)
print('Python 版本：%s' % sys.version.split()[0])
print('说明：本脚本仅用于核对厂商宣传资料与实际硬件是否一致')
print('=' * 70)


def run(cmd, timeout=10):
    """运行 shell 命令，返回 (stdout, stderr, returncode)。"""
    try:
        p = subprocess.run(
            cmd, shell=True, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors='replace'
        )
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except subprocess.TimeoutExpired:
        return '', '[超时 %ds]' % timeout, -1
    except FileNotFoundError as e:
        return '', '[命令不存在] %s' % e, 127
    except Exception as e:
        return '', '[异常] %s: %s' % (type(e).__name__, e), -2


def section(title):
    print()
    print('=' * 70)
    print(title)
    print('=' * 70)


def show(label, cmd, timeout=10):
    """运行命令并显示结果。"""
    out, err, code = run(cmd, timeout=timeout)
    print('  $ %s' % cmd)
    if out:
        for line in out.splitlines():
            print('      %s' % line)
    if err:
        print('      [stderr] %s' % err[:500])
    if not out and not err:
        print('      (无输出)')
    print()


# ================================================================
# 【1】SoC 型号（最关键，决定 RK3588 vs RK3566）
# ================================================================
section('【1】SoC 型号 —— 判断是 RK3588 还是 RK3566（决定所有大小核/GPU/NPU/视频参数）')
show('soc_id', 'cat /sys/devices/soc0/soc_id 2>/dev/null || echo "(无 soc_id)"')
show('machine', 'cat /sys/devices/soc0/machine 2>/dev/null || echo "(无 machine)"')
show('compatible (device-tree)', 'cat /proc/device-tree/compatible 2>/dev/null | tr "\\0" "\\n" | head -5 || echo "(无 device-tree)"')
show('revision', 'cat /sys/devices/soc0/revision 2>/dev/null || echo "(无 revision)"')

print('  >>> 解读提示：')
print('      RK3588:  compatible 含 "rockchip,rk3588"')
print('      RK3588S: compatible 含 "rockchip,rk3588s"')
print('      RK3566:  compatible 含 "rockchip,rk3566"')
print('      若是 RK3588，则用户资料的 A76/G610/6TOPS/8K 视频规格全部成立')
print('      若是 RK3566，则用户资料的 A76/G610/6TOPS/8K 视频规格全部错误')
print()


# ================================================================
# 【2】CPU 逐核心架构
# ================================================================
section('【2】CPU 逐核心架构 —— 判断是否有 Cortex-A76 大核（用户资料：4×A76 + 4×A55）')
show('逻辑核数 nproc --all', 'nproc --all')
show('lscpu 摘要', 'lscpu 2>/dev/null | head -30')
show('cpuinfo (CPU implementer/part/variant)', 'grep -E "^(processor|model name|CPU implementer|CPU part|CPU variant|CPU revision|BogoMIPS|Features)" /proc/cpuinfo')

print('  >>> 解读提示：')
print('      A76 = CPU implementer 0x41 / CPU part 0xd0b')
print('      A55 = CPU implementer 0x41 / CPU part 0xd05')
print('      如果只看到 0xd05 而没有 0xd0b，说明纯 A55（与 RK3566 一致）')
print('      如果 A76 + A55 都有，说明大小核异构（与 RK3588 一致，用户资料正确）')
print('      注意：/proc/cpuinfo 在 ARM big.LITTLE 上可能只显示当前在线核，')
print('           若全 A55，请配合第 1 项 compatible 判断')
print()


# ================================================================
# 【3】GPU 型号
# ================================================================
section('【3】GPU 型号 —— 判断是 Mali-G610 MP4 还是 Mali-G52')
show('GPU devfreq compatible', 'for d in /sys/class/devfreq/*gpu*; do echo "[$d]"; echo -n "  compatible: "; cat "$d/device/of_node/compatible" 2>/dev/null | tr "\\0" " "; echo; done')
show('GPU devfreq 列表', 'ls /sys/class/devfreq/ 2>/dev/null | grep -i gpu')
show('mali 节点', 'ls /sys/class/misc/ 2>/dev/null | grep -i mali; ls /dev/mali* 2>/dev/null')
show('dmesg GPU', 'dmesg 2>/dev/null | grep -i -E "mali|gpu" | head -10')

print('  >>> 解读提示：')
print('      Mali-G610: compatible 含 "mali-valhall" 或 "arm,mali-bifrost"')
print('      Mali-G52:  compatible 含 "arm,mali-bifrost" 或 "rockchip,rk3566-mali"')
print('      Mali-G610 MP4 = RK3588 标配；Mali-G52 2EE = RK3566 标配')
print()


# ================================================================
# 【4】NPU 型号 + 频率
# ================================================================
section('【4】NPU 型号 + 频率 —— 判断是 6 TOPS（RK3588）还是 1 TOPS（RK3566）')
show('NPU devfreq', 'for d in /sys/class/devfreq/*npu*; do echo "[$d]"; echo -n "  compatible: "; cat "$d/device/of_node/compatible" 2>/dev/null | tr "\\0" " "; echo; echo -n "  cur_freq: "; cat "$d/cur_freq" 2>/dev/null; echo " Hz"; echo -n "  available_freqs: "; cat "$d/available_frequencies" 2>/dev/null; echo; done')
show('NPU 设备节点', 'ls /dev/rknpu* 2>/dev/null; ls /sys/class/misc/rknpu 2>/dev/null; ls /sys/class/devfreq/ 2>/dev/null | grep -i npu')
show('librknnrt 版本', 'strings /usr/lib/librknnrt.so 2>/dev/null | grep -i -E "rknn|version|target" | head -10')
show('dmesg NPU', 'dmesg 2>/dev/null | grep -i -E "rknpu|npu" | head -10')

print('  >>> 解读提示：')
print('      RK3588 NPU: 6 TOPS @ INT8，3 个 NPU core')
print('      RK3566 NPU: 1 TOPS @ INT8，1 个 NPU core')
print('      NPU 算力无法从 sysfs 直接读出，但可通过 compatible 字符串判断 SoC')
print()


# ================================================================
# 【5】Wi-Fi 型号 & 能力
# ================================================================
section('【5】Wi-Fi 型号 & 能力 —— 判断是否支持 Wi-Fi 6（802.11ax）与 5GHz')
show('iw dev', 'iw dev 2>/dev/null || echo "iw 不可用"')
show('iw phy 摘要', 'iw list 2>/dev/null | grep -E "Wiphy|Frequencies|MHz|HE|VHT|HT capab|PHY name" | head -60')
show('wlan0 驱动', 'ethtool -i wlan0 2>/dev/null || echo "ethtool 不可用或 wlan0 不存在"')
show('lspci 网络', 'lspci -nn 2>/dev/null | grep -i -E "network|wireless|wifi" || echo "无 PCI 网络设备"')
show('lsusb 网络', 'lsusb 2>/dev/null | grep -i -E "wireless|wifi|802\\.11|realtek|rtl|mediatek|mtk|intel" || echo "无 USB 网络设备"')
show('iwlist 频段', 'iwlist wlan0 frequency 2>/dev/null | head -20 || echo "iwlist 不可用"')
show('iwconfig', 'iwconfig wlan0 2>/dev/null || echo "iwconfig 不可用"')
show('dmesg WiFi', 'dmesg 2>/dev/null | grep -i -E "wifi|wlan|rtw|rtl88|rtl81|mt79|ap6|fmac|sd8787" | head -15')

print('  >>> 解读提示：')
print('      Wi-Fi 6 (802.11ax): iw list 输出含 "HE" 字段（High Efficiency）')
print('      Wi-Fi 5 (802.11ac): iw list 输出含 "VHT" 字段（Very High Throughput）')
print('      仅 2.4G: Frequencies 列表只有 2412~2484 MHz，无 5180~5825 MHz')
print('      常见模组型号：')
print('          RTL8852BE / RTL8852BU = Wi-Fi 6')
print('          RTL8188 / RTL8723 = 2.4G only')
print('          AP6256 / AP6398 = Wi-Fi 5 或 Wi-Fi 6（看具体型号）')
print('      注意：若实测仅 2.4G 但 SoC 是 RK3588，可能出厂换装了低成本模组')
print()


# ================================================================
# 【6】蓝牙版本
# ================================================================
section('【6】蓝牙版本 —— 判断是否支持蓝牙 5.0')
show('hciconfig', 'hciconfig -a 2>/dev/null || echo "hciconfig 不可用"')
show('hcitool dev', 'hcitool dev 2>/dev/null || echo "hcitool 不可用"')
show('bluetoothctl show', 'bluetoothctl show 2>/dev/null || echo "bluetoothctl 不可用"')
show('rfkill 状态', 'rfkill list 2>/dev/null || echo "rfkill 不可用"')
show('dmesg 蓝牙', 'dmesg 2>/dev/null | grep -i -E "bluetooth|btusb|hci|btbcm|btrtl" | head -15')

print('  >>> 解读提示：')
print('      BT 5.0: dmesg 出现 "LE 5.0" 或 "Bluetooth: hci0: setting up" + 5.0 字样')
print('      BT 4.2: 较老的 ESP32/BLE 模组')
print('      常见模组：RTL8852BE=BT 5.0；AP6256=BT 4.2；AP6398S=BT 5.0')
print('      注意：蓝牙通常与 WiFi 同模组，WiFi 测出型号即可查蓝牙版本')
print()


# ================================================================
# 【7】屏幕分辨率
# ================================================================
section('【7】屏幕分辨率 —— 核验是 1920×1080 横屏还是 1200×1920 竖屏')
show('xrandr', 'xrandr 2>/dev/null || echo "xrandr 不可用（可能无 X 或不在桌面环境）"')
show('fbset', 'fbset 2>/dev/null || echo "fbset 不可用"')
show('framebuffer 分辨率', 'cat /sys/class/graphics/fb0/virtual_size 2>/dev/null; cat /sys/class/graphics/fb0/modes 2>/dev/null')
show('DRM connector', 'for c in /sys/class/drm/card0-*/; do echo "[$c]"; echo -n "  status: "; cat "$c/status" 2>/dev/null; echo -n "  modes: "; cat "$c/modes" 2>/dev/null | tr "\\n" " "; echo; done')
show('DRM 设备列表', 'ls /sys/class/drm/ 2>/dev/null; ls /sys/class/graphics/ 2>/dev/null')
show('dmesg DRM', 'dmesg 2>/dev/null | grep -i -E "drm|hdmi|panel|dsi|lvds|edp" | head -20')

print('  >>> 解读提示：')
print('      好搭AI派项目代码（weather_app/人脸学习/表情识别等 10+ 个）统一用 1920×1080 横屏')
print('      若实测 1920×1080 横屏：用户资料错误（1200×1920 是另一款好搭 AI Pad 1 的参数）')
print('      若实测 1200×1920 竖屏：用户资料正确，原项目代码需适配旋转')
print()


# ================================================================
# 【8】扬声器 / 音频 codec
# ================================================================
section('【8】扬声器 / 音频 codec —— 核验是否双扬声器（软件层只能看 codec，扬声器数量需现场听音）')
show('aplay 播放设备', 'aplay -l 2>/dev/null || echo "aplay 不可用"')
show('amixer codec', 'amixer 2>/dev/null | head -30')
show('音频 codec 设备树', 'for d in /sys/class/sound/*; do echo "[$d]"; echo -n "  compatible: "; cat "$d/of_node/compatible" 2>/dev/null | tr "\\0" " "; echo; done')
show('proc asound', 'cat /proc/asound/cards 2>/dev/null; cat /proc/asound/card0/pcm0p/info 2>/dev/null')
show('dmesg 音频', 'dmesg 2>/dev/null | grep -i -E "es8323|es8316|es8388|codec|rt5651|alc|rk817" | head -15')

print('  >>> 解读提示：')
print('      实测 codec 已知为 ES8323（探测_系统环境.py 已确认）')
print('      ES8323 是立体声 codec（2 声道 HP-OUT + 2 声道 SPK-OUT）')
print('      软件层无法判定是单/双扬声器，需现场听音或拆机确认')
print()


# ================================================================
# 【9】I2C 传感器扫描
# ================================================================
section('【9】I2C 传感器扫描 —— 核验板载传感器清单（指南针/陀螺仪/G-Sensor/霍尔开关）')
print('  注意：i2cdetect 需 root 权限，若非 root 可能失败')
show('i2c 总线列表', 'ls /dev/i2c-* 2>/dev/null; i2cdetect -l 2>/dev/null || echo "i2cdetect 不可用"')

# 对每个总线都扫一遍（0-9 足够覆盖大多数设备）
for bus in range(0, 10):
    show('i2c-%d 扫描' % bus, 'i2cdetect -y -r %d 2>/dev/null || echo "(无 i2c-%d 或无权限)"' % (bus, bus))

show('dmesg 传感器', 'dmesg 2>/dev/null | grep -i -E "accel|gyro|mag|compass|bma|mpu|icm|lsm|qmi|hall|stk|ltr|apds|iio" | head -20')
show('input 设备', 'for i in /sys/class/input/input*/; do echo "[$i]"; echo -n "  name: "; cat "$i/name" 2>/dev/null; echo -n "  compatible: "; cat "$i/of_node/compatible" 2>/dev/null | tr "\\0" " "; echo; done')
show('iio 设备', 'ls /sys/bus/iio/devices/ 2>/dev/null; for d in /sys/bus/iio/devices/iio:device*/; do echo "[$d]"; echo -n "  name: "; cat "$d/name" 2>/dev/null; echo; done')

print('  >>> 解读提示：')
print('      常见 I2C 地址：')
print('          0x0d = AK8963/QMC7983 指南针')
print('          0x1e = HMC5883L 指南针')
print('          0x68 = MPU6050/ICM42688 陀螺+加速度')
print('          0x6a = LSM6DS3 6 轴')
print('          0x19 / 0x18 = LIS3DH/LSM303 加速度')
print('          0x44 = APDS9960/SGP30 光照/手势')
print('          0x29 = TCS34725 颜色/光照')
print('          0x39 = LTR-553 光照+距离')
print('      实际型号看 dmesg / input 设备名 / iio 设备名')
print('      霍尔开关通常不挂 I2C，而是 GPIO，dmesg 或 /proc/device-tree 中搜 hall')
print()


# ================================================================
# 【10】电池 + 充电
# ================================================================
section('【10】电池 + 充电 —— 核验 5000mAh + 20W 快充')
show('power_supply 列表', 'ls /sys/class/power_supply/ 2>/dev/null || echo "无 power_supply"')
show('电池详细信息', 'for p in /sys/class/power_supply/*; do [ -d "$p" ] || continue; dev=$(basename "$p"); echo "=== [$dev] ==="; for k in capacity status voltage_now current_now power_now technology manufacturer model_name charge_full charge_full_design energy_full energy_full_design cycle_count temp present online type usb_type; do [ -f "$p/$k" ] && echo "  $k = $(cat $p/$k 2>/dev/null)"; done; done', timeout=15)
show('充电控制器 uevent', 'for p in /sys/class/power_supply/*; do echo "=== [$p/uevent] ==="; cat "$p/uevent" 2>/dev/null; done')
show('dmesg 电池', 'dmesg 2>/dev/null | grep -i -E "battery|charger|charging|cw2015|bq2589|rk817|fuel gauge|power" | head -20')

print('  >>> 解读提示：')
print('      charge_full / energy_full = 实际满充电荷量（单位 μAh 或 μWh）')
print('      charge_full_design / energy_full_design = 标称设计容量（若系统有读）')
print('      5000mAh = 5,000,000 μAh')
print('      当前功率 = voltage_now(V) × current_now(A)，20W 快充应接近 20')
print('      注意：charge_full 是实测满充电荷量，会因老化略低于标称容量')
print('           厂商标称容量需看 model_name 或 dmesg')
print()


# ================================================================
# 【11】内存与存储（复核）
# ================================================================
section('【11】内存 + 存储 —— 已知基本正确（8G / 256G），仅复核')
show('内存', 'free -h')
show('内存详情', 'cat /proc/meminfo | head -10')
show('存储分区', 'df -h')
show('eMMC/NVMe 设备', 'ls /dev/mmcblk* /dev/nvme* 2>/dev/null; cat /sys/class/block/mmcblk0/device/name 2>/dev/null; cat /sys/class/block/mmcblk0/device/csd 2>/dev/null; cat /sys/class/block/nvme0n1/device/model 2>/dev/null')

print('  >>> 解读提示：')
print('      内存 MemTotal 约 7.7 GiB = 8 GiB 标称 ✓（用户资料正确）')
print('      存储总容量约 227 GB = 256 GB 标称换算 ✓（用户资料正确）')
print('      此项无需核验，仅记录')
print()


# ================================================================
# 【12】ESP32 小核
# ================================================================
section('【12】ESP32 小核 —— 核验 RISC-V 架构 + 4MB Flash + 串口连接')
show('串口设备', 'ls /dev/ttyS* 2>/dev/null; ls /dev/ttyUSB* 2>/dev/null; ls /dev/ttyACM* 2>/dev/null')
show('ttyS9 详情', 'stty -F /dev/ttyS9 2>/dev/null; udevadm info -q property -n /dev/ttyS9 2>/dev/null | head -10')
show('ESP32 通讯测试（仅打开端口不发数据）', "python3 -c \"import serial; s=serial.Serial('/dev/ttyS9', 115200, timeout=0.5); print('OK 端口可打开', s); s.close()\" 2>&1 || echo \"端口打开失败或 pyserial 未装\"")
show('dmesg ESP32 / 串口', 'dmesg 2>/dev/null | grep -i -E "esp32|cp210|ch340|ftdi|ttyS9|rk805|serial" | head -10')

print('  >>> 解读提示：')
print('      ESP32-S3 是 RISC-V 架构，内置 4MB Flash ✓（用户资料正确）')
print('      连接走 /dev/ttyS9 内部 UART，非 USB 串口芯片 ✓')
print('      Flash 加密、Secure Boot、AES/SHA/RSA 硬件加速是 ESP32-S3 标配 ✓')
print('      注意：探测脚本无法直接读 ESP32 内部架构，只能通过串口确认连接')
print('           架构确认需查 ESP32 SDK 或参考官方文档')
print()


# ================================================================
# 探测完成
# ================================================================
section('探测完成')
print('日志已保存到：%s' % _LOG_FILE)
print()
print('请将日志文件内容复制给我，我来逐项核对厂商宣传资料与实测数据是否一致。')
print('=' * 70)
