#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盲点探测 A: V3 回调系统验证（交互式 + 语音提示）

目的: 验证 V3 库 add_detection_callback / add_frame_callback / add_error_callback
      是否真正触发、回调参数格式是什么

运行前: 在下方 USERNAME / PASSWORD 填入好搭AI派账号
运行: python3 探测_盲点_A_回调系统.py
日志: logs/logs_探测_盲点A_回调系统_YYYYMMDD.txt
需要: 摄像头 + 用户配合做动作（露脸/挥手/出示二维码/出示颜色物体）
交互: pygame 窗口显示实时画面 + 倒计时 + 指引文字 + 回调触发状态 + 语音提示
"""

# ============================================================
# ★★★ 用户配置区：请填入好搭AI派用户名和密码 ★★★
USERNAME = 'your_username'
PASSWORD = 'your_password'
# ============================================================

import os
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'

# text_recognition 必须在 cv2/pygame/V3 之前导入（utils 命名空间冲突）
try:
    import text_recognition
except Exception:
    pass

import sys
import time
import datetime
import traceback

# 日志统一输出到 logs/ 目录，避免散落在项目根目录
_log_dir = 'logs'
if not os.path.exists(_log_dir):
    try:
        os.makedirs(_log_dir)
    except Exception:
        pass
LOG_FILE = '%s/logs_探测_盲点A_回调系统_%s.txt' % (
    _log_dir, datetime.datetime.now().strftime('%Y%m%d'))
_log_fp = None


def log(msg=''):
    line = str(msg) if msg else ''
    print(line)
    if _log_fp:
        _log_fp.write(line + '\n')
        _log_fp.flush()


# ============================================================
# TTS 语音提示（使用好搭AI派 VoiceAPI + AudioPlayer）
# ============================================================
_tts_api = None
_tts_player = None
_tts_counter = 0

def init_tts():
    """初始化 TTS — 使用好搭AI派 VoiceAPI（需用户名密码登录）"""
    global _tts_api, _tts_player

    from voice_api import VoiceAPI
    from audio_player import AudioPlayer

    recordings_dir = 'recordings'
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)

    _tts_api = VoiceAPI('http://www.haohaodada.com/project/voiceAI/ApiZNBW.php')
    _tts_player = AudioPlayer()

    token_result = _tts_api.get_token(USERNAME, PASSWORD)
    if not token_result:
        log('  ❌ VoiceAPI 认证失败！请检查 USERNAME / PASSWORD')
        raise RuntimeError('VoiceAPI get_token 失败')

    log('  ✅ VoiceAPI 认证成功，TTS 可用')


def speak(text):
    """语音播报，同时输出日志"""
    global _tts_counter
    log('  🔊 %s' % text)

    if _tts_api is None:
        time.sleep(1.5)
        return

    wav_path = '%s/tts_%d.wav' % ('recordings', _tts_counter)
    _tts_counter += 1
    try:
        audio_data = _tts_api.tts_synthesize(text, wav_path)
        if audio_data:
            _tts_player.play_file(wav_path)
            time.sleep(0.5)
        else:
            log('    (TTS 合成返回空)')
    except Exception as e:
        log('    (TTS 播报失败: %s)' % str(e)[:100])
    finally:
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except:
            pass


def section(title):
    log('')
    log('=' * 70)
    log('  ' + title)
    log('=' * 70)


def main():
    import camera_vision_system_v3 as v3
    import pygame
    import cv2
    import numpy as np

    section('A: V3 回调系统验证（交互式 + 语音提示）')

    # 初始化 TTS
    log('\n  0. 初始化语音提示...')
    try:
        init_tts()
    except Exception as e:
        log('  ⚠️ TTS 初始化失败: %s' % e)
        log('  ⚠️ 脚本将继续运行但无语音提示，请同时看屏幕指引')
        global _tts_api
        _tts_api = None

    log('  本脚本验证 V3 库的回调系统是否真正触发。')
    log('  pygame 窗口将显示实时画面和倒计时。')
    log('  请在倒计时结束后做以下动作（15秒）：')
    log('    - 露脸（测试人脸识别回调）')
    log('    - 出示二维码（测试 qr_code 回调）')
    log('    - 出示颜色物体（测试 color 回调）')
    log('  按 ESC 可随时退出')
    log('')

    speak('V3回调系统测试即将开始，请在提示后做动作')

    # 1. 创建视觉系统（按范例代码参数）
    log('\n  1. 创建视觉系统（按范例代码: enable_basic=False, camera_id=-1, 1280x720）')
    vs = v3.create_vision_system_v3(
        camera_id=-1, width=1280, height=720,
        enable_basic=False, enable_advanced=False
    )
    log('  ✅ 视觉系统创建成功')

    # 2. 打开摄像头
    log('\n  2. 打开摄像头')
    cam_ok = vs.open_camera()
    log('  open_camera() 返回: %s' % cam_ok)
    if not cam_ok:
        log('  ❌ 摄像头打开失败')
        return

    # 3. 按范例代码方式启用各算法 + _init_detectors()
    log('\n  3. 启用检测算法（每启用一个都调 _init_detectors()）')

    # 人脸识别
    vs.detection_config.enable_face_recognition = True
    log('  enable_face_recognition = True')

    # 二维码
    vs.detection_config.enable_qr_code = True
    log('  enable_qr_code = True')

    # 颜色识别 + 区域
    vs.detection_config.enable_color_recognition = True
    # 注意: 内部处理分辨率是 640x480 (从回调 color_recognition.image_info.width/height 确认)
    #       color_recognition_regions 必须用 640x480 坐标, 否则报"无效的区域坐标"
    vs.detection_config.color_recognition_regions.append((50, 100, 200, 200))
    vs.detection_config.color_recognition_regions.append((390, 100, 200, 200))
    log('  enable_color_recognition = True, 添加2个区域 [640x480空间]')

    # 颜色块
    vs.detection_config.enable_color_block = True
    log('  enable_color_block = True')

    # 关键步骤: _init_detectors()
    log('  调用 _init_detectors()...')
    try:
        vs._init_detectors()
        log('  ✅ _init_detectors() 成功')
    except Exception as e:
        log('  ❌ _init_detectors() 失败: %s' % e)

    ts = vs.threaded_system

    # 4. 反射查找回调方法
    log('\n  4. 反射查找回调方法')
    all_ts = [m for m in dir(ts) if not m.startswith('_') and callable(getattr(ts, m, None))]
    cb_ts = [m for m in all_ts if 'callback' in m.lower()]
    log('  threaded_system 回调方法(%d): %s' % (len(cb_ts), cb_ts))

    # 5. 注册回调
    log('\n  5. 注册回调')
    cb_data = {}
    cb_latest = {}  # 存储最新的回调数据用于界面显示

    def make_cb(name):
        def cb(*args, **kwargs):
            e = cb_data.setdefault(name, {'count': 0, 'types': [], 'args': None})
            e['count'] += 1
            if e['count'] == 1:
                e['types'] = [type(a).__name__ for a in args]
                e['args'] = repr(args)[:500]
            # 更新最新数据供界面显示
            cb_latest[name] = args
        return cb

    for mname in cb_ts:
        if mname.startswith('add_') and mname != 'remove_callback':
            short = mname.replace('add_', '').replace('_callback', '')
            try:
                getattr(ts, mname)(make_cb(short))
                log('  ✅ 注册: %s' % mname)
            except Exception as e:
                log('  ❌ 注册失败: %s - %s' % (mname, e))

    # 6. 启动后台检测（按范例代码 show_preview=True）
    log('\n  6. 启动后台检测（show_preview=True）...')
    try:
        ts.start_background_detection(show_preview=True)
        log('  ✅ 后台检测已启动')
    except Exception as e:
        log('  ⚠️ show_preview=True 失败，尝试无参数: %s' % e)
        try:
            ts.start_background_detection()
            log('  ✅ 后台检测已启动（无 show_preview）')
        except Exception as e2:
            log('  ❌ 启动失败: %s' % e2)
        try:
            vs.cleanup()
        except:
            pass
        return

    # 7. 初始化 pygame 窗口
    log('\n  7. 初始化 pygame 显示...')
    # 按工程约定: 只初始化 display + font，避免音频子系统异常
    pygame.display.init()
    pygame.font.init()
    # 画面 640x480 + 顶部标题(36) + 底部指引(28) + 底部状态区(3×18=54) ≈ 640×598，取整 640×620
    screen = pygame.display.set_mode((640, 620))
    pygame.display.set_caption('V3 回调系统探测 - 按 ESC 退出')
    font_big = pygame.font.Font(None, 36)
    font_mid = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 22)

    # 7. 预热 + 准备倒计时（3秒）
    log('  预热 3 秒...')
    speak('准备开始，三秒后开始采集')
    warmup_start = time.time()
    early_exit = False
    while time.time() - warmup_start < 3:
        remaining = 3 - int(time.time() - warmup_start)
        try:
            frame = vs.capture_frame()
            if frame is not None and frame.ndim == 3:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                surf = pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), 'RGB')
                screen.blit(surf, (0, 0))
            else:
                screen.fill((40, 40, 40))
        except:
            screen.fill((40, 40, 40))

        txt = font_big.render('  Starting in %d...  ' % max(remaining, 0), True, (255, 255, 0), (0, 0, 0))
        screen.blit(txt, (180, 230))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                early_exit = True
                break
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                early_exit = True
                break
        if early_exit:
            break
        time.sleep(0.05)

    # 8. 正式采集 — 分 3 个阶段，每段 5 秒，分别语音提示
    if not early_exit:
        log('\n  8. 开始回调采集（分 3 个阶段，每段 5 秒）...')

        phases = [
            (5, '请露脸', 'Phase 1: Show Face [5s]'),
            (5, '请出示二维码', 'Phase 2: Show QR Code [5s]'),
            (5, '请出示颜色物体', 'Phase 3: Show Colored Object [5s]'),
        ]

        for phase_idx, (phase_dur, phase_speak, phase_title) in enumerate(phases):
            if early_exit:
                break

            log('\n  --- 阶段 %d: %s ---' % (phase_idx + 1, phase_title))
            speak(phase_speak)

            phase_start = time.time()
            while time.time() - phase_start < phase_dur:
                elapsed = time.time() - phase_start
                remaining = phase_dur - int(elapsed)

                # 获取帧
                frame = None
                try:
                    frame = vs.capture_frame()
                except:
                    pass

                # 统计回调触发
                triggered = dict((k, v['count']) for k, v in cb_data.items() if v['count'] > 0)

                # 日志（每秒一次）
                if int(elapsed) > int(elapsed - 0.5) or elapsed < 0.5:
                    log('    [%d/%ds] %s' % (int(elapsed) + 1, phase_dur,
                        triggered if triggered else '(无)'))

                # 显示画面
                screen.fill((0, 0, 0))
                if frame is not None and frame.ndim == 3:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    surf = pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), 'RGB')
                    screen.blit(surf, (0, 0))
                else:
                    screen.fill((40, 40, 40))

                # 叠加文字 — 阶段标题 + 倒计时
                txt_phase = font_big.render('%s  [%ds]' % (phase_title, remaining),
                                             True, (255, 255, 0), (0, 0, 0))
                screen.blit(txt_phase, (10, 6))

                # 底部指引（当前阶段对应动作）
                txt_guide = font_mid.render(phase_speak, True, (0, 255, 0), (0, 0, 0))
                screen.blit(txt_guide, (10, 492))

                # 回调状态
                y_stat = 520
                for name in sorted(cb_data.keys()):
                    info = cb_data[name]
                    if info['count'] > 0:
                        status_text = '%s: %d times ✅' % (name, info['count'])
                        color = (0, 255, 0)
                    else:
                        status_text = '%s: 0 (waiting...)' % name
                        color = (200, 200, 200)
                    txt_stat = font_small.render(status_text, True, color, (0, 0, 0))
                    screen.blit(txt_stat, (10, y_stat))
                    y_stat += 18

                pygame.display.flip()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        early_exit = True
                        break
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        early_exit = True
                        break
                if early_exit:
                    break
                time.sleep(0.1)

            # 阶段间语音过渡
            if not early_exit and phase_idx < len(phases) - 1:
                speak('换下一个')

    # 9. 停止检测
    log('\n  9. 停止后台检测...')
    speak('采集结束，感谢配合')
    log('  停止 background_detection...')
    try:
        ts.stop_background_detection()
        log('  ✅ 已停止')
    except:
        try:
            vs.stop_background_detection()
            log('  ✅ 已停止(vs)')
        except:
            log('  ⚠️ 停止失败（忽略）')
    log('  cleanup...')
    try:
        vs.cleanup()
        log('  ✅ cleanup 完成')
    except:
        log('  ⚠️ cleanup 失败（忽略）')
    try:
        pygame.quit()
    except:
        pass

    # 10. 结果统计
    section('A: 回调触发统计结果')

    if not cb_data:
        log('  （无回调注册成功）')
    else:
        for name, info in sorted(cb_data.items()):
            status = '✅ 触发' if info['count'] > 0 else '❌ 未触发'
            log('  %s: %s (%d次)' % (name, status, info['count']))
            if info['count'] > 0:
                log('    参数类型: %s' % info['types'])
                log('    首次参数: %s' % info['args'])

        not_triggered = [k for k, v in cb_data.items() if v['count'] == 0]
        if not_triggered:
            log('\n  未触发回调: %s' % not_triggered)
            log('  注意: 可能是摄像头前没有对应目标，或该回调类型需要额外配置')

        # 特别分析 detection 回调的 dict 结构
        if 'detection' in cb_data and cb_data['detection']['count'] > 0:
            log('\n  ========== detection 回调 dict 结构分析 ==========')
            latest = cb_latest.get('detection', (None,))[0]
            if isinstance(latest, dict):
                log('  keys (%d): %s' % (len(latest), list(latest.keys())))
                for k, v in latest.items():
                    vtype = type(v).__name__
                    if isinstance(v, list):
                        log('    %s: %s (len=%d, empty=%s)' % (k, vtype, len(v), len(v) == 0))
                    elif isinstance(v, dict):
                        log('    %s: %s (keys=%s, empty=%s)' % (k, vtype, list(v.keys()), len(v) == 0))
                    else:
                        log('    %s: %s = %s' % (k, vtype, repr(v)[:100]))

        if 'frame' in cb_data and cb_data['frame']['count'] > 0:
            log('\n  ========== frame 回调参数分析 ==========')
            latest = cb_latest.get('frame', (None, None))
            if len(latest) >= 2:
                log('  参数1: %s, shape=%s' % (type(latest[0]).__name__,
                    latest[0].shape if hasattr(latest[0], 'shape') else 'N/A'))
                log('  参数2: %s' % type(latest[1]).__name__)
                if isinstance(latest[1], dict):
                    log('  参数2 keys: %s' % list(latest[1].keys()))


if __name__ == '__main__':
    _log_fp = open(LOG_FILE, 'w', encoding='utf-8')
    log('盲点探测 A（V3回调系统，交互式）开始 - %s' % datetime.datetime.now())
    log('日志文件: %s' % LOG_FILE)
    log('Python: %s' % sys.version)

    try:
        main()
    except Exception as e:
        log('❌ 整体异常: %s' % e)
        traceback.print_exc()
        if _log_fp:
            traceback.print_exc(file=_log_fp)
        try:
            import pygame
            pygame.quit()
        except:
            pass

    log('\n盲点探测 A 完成 - %s' % datetime.datetime.now())
    log('日志文件: %s' % LOG_FILE)
    _log_fp.close()
