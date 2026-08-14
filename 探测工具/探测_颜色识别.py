#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
颜色识别探测脚本（基于范例代码，带完整调试日志）

严格按范例代码流程:
1. create_vision_system_v3(camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False)
2. open_camera()
3. detection_config.enable_color_recognition = True
4. _init_detectors()  ← 之前遗漏的关键步骤
5. detection_config.color_recognition_regions.append(...)
6. threaded_system.start_background_detection(show_preview=True)
7. result_accessor.refresh_results() + get_color_recognition_count()

同时测试 color_block 算法。
日志输出到 logs/ 目录。

运行: python3 探测_颜色识别.py
"""

import os
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'

try:
    import text_recognition
except Exception:
    pass

import sys
import time
import datetime
import traceback

# 日志输出到 logs/ 目录
_log_dir = 'logs'
if not os.path.exists(_log_dir):
    os.makedirs(_log_dir)
LOG_FILE = '%s/logs_探测_颜色识别_%s.txt' % (_log_dir, datetime.datetime.now().strftime('%Y%m%d'))
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


def main():
    from camera_vision_system_v3 import create_vision_system_v3
    import cv2

    section('颜色识别探测（基于范例代码）')

    # ============================================================
    # 步骤 1: 创建视觉系统（完全照抄范例代码参数）
    # ============================================================
    log('\n  步骤1: 创建视觉系统')
    log('  参数: camera_id=-1, width=1280, height=720, enable_basic=False, enable_advanced=False')
    vision_system = create_vision_system_v3(
        camera_id=-1, width=1280, height=720,
        enable_basic=False, enable_advanced=False
    )
    log('  ✅ 视觉系统创建成功')
    log('  vision_system 类型: %s' % type(vision_system).__name__)

    # 调试: 打印 vision_system 的关键属性
    log('\n  --- 调试: vision_system 关键属性 ---')
    for attr in ['camera_config', 'detection_config', 'threaded_system', 'result_accessor']:
        val = getattr(vision_system, attr, '<不存在>')
        log('  vision_system.%s = %s' % (attr, type(val).__name__ if val != '<不存在>' else '<不存在>'))

    # ============================================================
    # 步骤 2: 打开摄像头
    # ============================================================
    log('\n  步骤2: 打开摄像头')
    cam_ok = vision_system.open_camera()
    log('  open_camera() 返回: %s' % cam_ok)
    if cam_ok:
        log('  ✅ 摄像头已打开')
    else:
        log('  ❌ 摄像头打开失败')
        return

    # ============================================================
    # 步骤 3: 启用 color_recognition（范例代码方式）
    # ============================================================
    log('\n  步骤3: 启用 color_recognition 算法')
    vision_system.detection_config.enable_color_recognition = True
    log('  detection_config.enable_color_recognition = True ✅')
    log('  当前 enable_color_recognition: %s' % vision_system.detection_config.enable_color_recognition)

    # ============================================================
    # 步骤 4: _init_detectors() ← 之前遗漏的关键步骤
    # ============================================================
    log('\n  步骤4: _init_detectors()（关键步骤）')
    try:
        vision_system._init_detectors()
        log('  ✅ _init_detectors() 调用成功')
    except Exception as e:
        log('  ❌ _init_detectors() 失败: %s' % e)
        log('  %s' % traceback.format_exc()[:500])

    # ============================================================
    # 步骤 5: 添加颜色识别区域（范例代码方式）
    # ============================================================
    log('\n  步骤5: 添加颜色识别区域')
    # 注意: 尽管 create_vision_system_v3 传 width=1280 height=720,
    #       但实际内部处理分辨率是 640x480 (从回调 color_recognition.image_info 确认)
    #       color_recognition_regions 必须用 640x480 坐标, 否则报"无效的区域坐标"
    # 区域用 (x, y, w, h) 格式, 需保证 x+w<=640, y+h<=480
    vision_system.detection_config.color_recognition_regions.append((50, 100, 200, 200))
    log('  添加区域0: (50, 100, 200, 200)  [640x480空间, 左侧]')
    vision_system.detection_config.color_recognition_regions.append((390, 100, 200, 200))
    log('  添加区域1: (390, 100, 200, 200)  [640x480空间, 右侧]')
    log('  当前区域数: %d' % len(vision_system.detection_config.color_recognition_regions))

    # 调试: 打印 detection_config 所有启用的算法
    log('\n  --- 调试: detection_config 已启用的算法 ---')
    dc = vision_system.detection_config
    for attr in dir(dc):
        if attr.startswith('enable_'):
            val = getattr(dc, attr, None)
            if val:
                log('  %s = %s ✅' % (attr, val))

    # ============================================================
    # 步骤 6: 同时启用 color_block（第二个算法）
    # ============================================================
    log('\n  步骤6: 同时启用 color_block 算法')
    try:
        vision_system.detection_config.enable_color_block = True
        vision_system._init_detectors()
        log('  ✅ color_block 已启用并重新初始化检测器')
    except Exception as e:
        log('  ⚠️ color_block 启用失败: %s' % e)

    # ============================================================
    # 步骤 7: 启动后台检测
    # ============================================================
    log('\n  步骤7: 启动后台检测')
    try:
        vision_system.threaded_system.start_background_detection(show_preview=True)
        log('  ✅ 后台检测已启动 (show_preview=True)')
    except Exception as e:
        log('  ❌ 启动失败: %s' % e)
        try:
            vision_system.threaded_system.start_background_detection()
            log('  ✅ 后台检测已启动 (无 show_preview)')
        except Exception as e2:
            log('  ❌ 再次启动失败: %s' % e2)
            return

    # ============================================================
    # 步骤 8: 等待 3 秒预热
    # ============================================================
    log('\n  步骤8: 预热 3 秒...')
    time.sleep(3)
    log('  ✅ 预热完成')

    # ============================================================
    # 步骤 9: 采集 15 秒，每秒读取一次结果
    # ============================================================
    log('\n  步骤9: 开始采集 15 秒（请在摄像头前出示颜色物体）')
    log('  将每秒读取 color_recognition 和 color_block 结果')

    ra = vision_system.result_accessor
    log('  result_accessor 类型: %s' % type(ra).__name__)

    # 调试: 打印 result_accessor 所有 color 相关方法
    log('\n  --- 调试: result_accessor color 相关方法 ---')
    all_methods = [m for m in dir(ra) if not m.startswith('_') and callable(getattr(ra, m, None))]
    color_methods = [m for m in all_methods if 'color' in m.lower()]
    log('  color 相关方法(%d): %s' % (len(color_methods), color_methods))

    for sec in range(15):
        try:
            ra.refresh_results()
        except Exception as e:
            log('  refresh_results() 失败: %s' % e)

        # 读取 color_recognition
        cr_count = 0
        try:
            cr_count = ra.get_color_recognition_count()
        except Exception as e:
            log('  get_color_recognition_count() 失败: %s' % e)

        # 读取 color_block
        cb_count = 0
        try:
            cb_count = ra.get_color_block_count()
        except Exception as e:
            log('  get_color_block_count() 失败: %s' % e)

        # 读取 face_count（对比测试）
        fc = -1
        try:
            fc = ra.get_face_count()
        except:
            pass

        log('\n  [%d/15s] color_recognition_count=%d, color_block_count=%d, face_count=%s' % (
            sec + 1, cr_count, cb_count, fc))

        # 如果有 color_recognition 结果，打印详细信息
        if cr_count > 0:
            for i in range(min(cr_count, 2)):
                log('  --- color_recognition 区域 %d ---' % i)
                # 先取 color，判断是否识别成功；None 表示坐标错误或无有效颜色
                cr_color = None
                try:
                    cr_color = ra.get_color_recognition_color(i)
                except Exception as e:
                    log('    color: <读取异常: %s>' % e)
                if cr_color is None:
                    log('    color: 未识别 (可能区域越界/无目标)')
                    # color 为 None 时 rgb 也必定是 None，不调用 get_rgb 避免异常信息
                    log('    rgb:   未识别')
                else:
                    log('    color: %s' % cr_color)
                    try:
                        cr_rgb = ra.get_color_recognition_rgb(i)
                        log('    rgb:   %s' % str(cr_rgb))
                    except Exception as e:
                        log('    rgb:   <读取异常: %s>' % e)
                try:
                    log('    name:  %s' % ra.get_color_recognition_name(i))
                except Exception as e:
                    log('    name:  <错误: %s>' % e)

        # 如果有 color_block 结果，打印详细信息
        if cb_count > 0:
            for i in range(min(cb_count, 2)):
                log('  --- color_block %d ---' % i)
                try:
                    log('    color:    %s' % ra.get_color_block_color(i))
                except Exception as e:
                    log('    color:    <错误: %s>' % e)
                try:
                    log('    position: %s' % str(ra.get_color_block_position(i)))
                except Exception as e:
                    log('    position: <错误: %s>' % e)
                try:
                    log('    center:   %s' % str(ra.get_color_block_center(i)))
                except Exception as e:
                    log('    center:   <错误: %s>' % e)
                try:
                    log('    area:     %s' % str(ra.get_color_block_area(i)))
                except Exception as e:
                    log('    area:     <错误: %s>' % e)

        time.sleep(1)

    # ============================================================
    # 步骤 10: 同时测试检测回调中的字段
    # ============================================================
    log('\n  步骤10: 检查回调 dict 中的 color 字段')

    callback_color_rec = {}
    callback_color_block = {}

    def test_callback(detection_dict):
        cr = detection_dict.get('color_recognition', {})
        cb = detection_dict.get('color_block', {})
        if cr:
            callback_color_rec.update(cr)
        if cb:
            callback_color_block.update(cb)

    try:
        vision_system.threaded_system.add_detection_callback(test_callback)
        log('  ✅ 回调已注册，等待 3 秒...')
        time.sleep(3)
        log('  回调中 color_recognition: %s' % (repr(callback_color_rec)[:300] if callback_color_rec else '空'))
        log('  回调中 color_block: %s' % (repr(callback_color_block)[:300] if callback_color_block else '空'))
    except Exception as e:
        log('  ⚠️ 回调测试失败: %s' % e)

    # ============================================================
    # 清理
    # ============================================================
    log('\n  清理资源...')
    try:
        vision_system.threaded_system.stop_background_detection()
        log('  ✅ 后台检测已停止')
    except:
        log('  ⚠️ 停止失败（忽略）')
    try:
        vision_system.cleanup()
        log('  ✅ cleanup 完成')
    except:
        log('  ⚠️ cleanup 失败（忽略）')

    # ============================================================
    # 总结
    # ============================================================
    section('总结')
    log('  关键发现:')
    log('  1. _init_detectors() 是否成功: 见步骤4')
    log('  2. color_recognition 是否有结果: 见步骤9 各秒 count')
    log('  3. color_block 是否有结果: 见步骤9 各秒 count')
    log('  4. 回调中 color 字段: 见步骤10')


if __name__ == '__main__':
    _log_fp = open(LOG_FILE, 'w', encoding='utf-8')
    log('颜色识别探测开始 - %s' % datetime.datetime.now())
    log('日志文件: %s' % LOG_FILE)
    log('Python: %s' % sys.version)

    try:
        main()
    except Exception as e:
        log('❌ 整体异常: %s' % e)
        traceback.print_exc()
        if _log_fp:
            traceback.print_exc(file=_log_fp)

    log('\n颜色识别探测完成 - %s' % datetime.datetime.now())
    log('日志文件: %s' % LOG_FILE)
    _log_fp.close()
