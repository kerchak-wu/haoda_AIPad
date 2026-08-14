#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盲点探测 B: 人脸表情投入度（engagement）语义验证（交互式 + 语音提示）

v2 修复:
1. result_accessor 用属性访问（vs.result_accessor）而非方法（vs.get_result_accessor()）
2. enable_basic=True 确保人脸检测启动
3. 用 DetectionConfig 预设 enable_facial_expression=True
4. 注册 detection 回调直接获取 facial_expression 字段数据
5. 语音提示（VoiceAPI TTS）— 用户无需看屏幕
6. 人脸检查阶段 — 开始前确认人脸被检测到
7. 大字体显示

运行前: 在下方 USERNAME / PASSWORD 填入好搭AI派账号
运行: python3 探测_盲点_B_表情投入度.py
日志: logs/logs_探测_盲点B_表情投入度_YYYYMMDD.txt
"""

# ============================================================
# ★★★ 用户配置区：请填入好搭AI派用户名和密码 ★★★
USERNAME = 'your_username'
PASSWORD = 'your_password'
# ============================================================

import os
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'

# text_recognition 必须在 cv2/pygame/V3 之前导入
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
LOG_FILE = '%s/logs_探测_盲点B_表情投入度_%s.txt' % (
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

    # 确保录音目录存在（tts_synthesize 需要保存 wav 文件）
    recordings_dir = 'recordings'
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)

    # 范例代码用法：VoiceAPI(url) + get_token(user, password)
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
        log('    (TTS 未初始化，跳过)')
        time.sleep(1.5)
        return

    wav_path = '%s/tts_%d.wav' % ('recordings', _tts_counter)
    _tts_counter += 1
    try:
        # 范例代码用法：tts_synthesize(text, wav_path) -> audio_data
        audio_data = _tts_api.tts_synthesize(text, wav_path)
        if audio_data:
            # 范例代码用法：play_file(wav_path) -> bool
            _tts_player.play_file(wav_path)
            time.sleep(0.5)  # 等播报结束
        else:
            log('    (TTS 合成返回空)')
    except Exception as e:
        log('    (TTS 播报失败: %s)' % str(e)[:100])
    finally:
        # 清理临时文件
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except:
            pass


# ============================================================
# 数据收集
# ============================================================
latest_detection = {}

def detection_callback(result_dict):
    """检测回调，存储最新检测结果"""
    latest_detection.clear()
    latest_detection.update(result_dict)


def _is_valid(val):
    """判断值是否有效（非 None、非空字符串、非空容器）
       注意: face_count=0 是合法值（表示未检测到人脸）, 不被过滤
    """
    if val is None:
        return False
    if isinstance(val, str) and val == '':
        return False
    if isinstance(val, (dict, list)) and len(val) == 0:
        return False
    return True


def get_engagement_data(vs, ts):
    """从多种途径获取表情识别数据"""
    result = {}

    # 方式1: result_accessor 属性（非方法）
    ra = getattr(vs, 'result_accessor', None)
    if ra is None:
        ra = getattr(ts, 'result_accessor', None)

    if ra is not None:
        try:
            ra.refresh_results()
        except Exception:
            pass

        for mname in ['get_facial_expression_engagement',
                       'get_facial_expression_engagement_confidence',
                       'get_facial_expression_emotion',
                       'get_facial_expression_emotions_confidence',
                       'get_facial_expression_success',
                       'get_facial_expression_inference_time',
                       'get_face_count',
                       'get_face_confidence',
                       'get_face_id',
                       'get_face_position']:
            if hasattr(ra, mname):
                try:
                    val = getattr(ra, mname)()
                    # 始终记录，但标记是否有效
                    result[mname] = val
                except Exception:
                    pass

    # 方式2: vs 级别快捷方法
    for mname in ['get_facial_expression_engagement',
                   'get_facial_expression_emotion',
                   'get_face_count']:
        if mname not in result and hasattr(vs, mname):
            try:
                val = getattr(vs, mname)()
                if val is not None:
                    result[mname] = val
            except Exception:
                pass

    # 方式3: 检测回调中的 facial_expression 字段
    fe = latest_detection.get('facial_expression', {})
    if fe:
        result['callback_facial_expression'] = fe

    fr = latest_detection.get('face_recognition', {})
    if fr:
        result['callback_face_recognition'] = fr

    return result if result else None


# ============================================================
# 阶段运行
# ============================================================
def run_phase(vs, ts, screen, font_huge, font_big, font_mid,
              phase_name, instruction, duration=10):
    """运行一个数据采集阶段，返回数据列表"""
    import cv2
    import pygame

    data = []

    # 语音提示
    speak(instruction)
    time.sleep(1)

    # 3 秒倒计时
    for cd in range(3, 0, -1):
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

        txt_cd = font_huge.render(str(cd), True, (255, 255, 0), (0, 0, 0))
        screen.blit(txt_cd, (300, 200))
        txt_inst = font_mid.render(instruction, True, (0, 255, 0), (0, 0, 0))
        screen.blit(txt_inst, (50, 450))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return data, True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return data, True
        time.sleep(1)

    # 正式采集
    start_time = time.time()
    while time.time() - start_time < duration:
        elapsed = time.time() - start_time
        remaining = duration - int(elapsed)

        # 获取帧
        frame = None
        try:
            frame = vs.capture_frame()
        except:
            pass

        # 获取表情数据
        expr_data = get_engagement_data(vs, ts)

        # 记录
        entry = {
            'time': round(elapsed, 2),
            'engagement': None,
            'emotion': None,
            'face_count': None,
            'callback_fe': None,
        }
        if expr_data:
            entry['engagement'] = expr_data.get('get_facial_expression_engagement')
            entry['emotion'] = expr_data.get('get_facial_expression_emotion')
            entry['face_count'] = expr_data.get('get_face_count')
            entry['callback_fe'] = expr_data.get('callback_facial_expression')
        data.append(entry)

        eng_str = str(entry['engagement'])[:20] if _is_valid(entry['engagement']) else 'N/A'
        emo_str = str(entry['emotion'])[:20] if _is_valid(entry['emotion']) else 'N/A'
        fc_str = str(entry['face_count']) if entry['face_count'] is not None else 'N/A'
        fe_str = '有' if entry['callback_fe'] else '无'
        log('    [%.1fs] eng=%s emo=%s face=%s cb_fe=%s' % (
            elapsed, eng_str, emo_str, fc_str, fe_str))

        # 显示
        screen.fill((0, 0, 0))
        if frame is not None and frame.ndim == 3:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            surf = pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), 'RGB')
            screen.blit(surf, (0, 0))
        else:
            screen.fill((40, 40, 40))

        # 大字显示阶段名 + 倒计时
        txt_phase = font_big.render('%s  [%ds]' % (phase_name, remaining),
                                     True, (255, 255, 0), (0, 0, 0))
        screen.blit(txt_phase, (10, 6))
        txt_inst = font_mid.render(instruction, True, (0, 255, 0), (0, 0, 0))
        screen.blit(txt_inst, (10, 490))

        # engagement 实时值
        txt_eng = font_big.render('Engagement: %s' % eng_str,
                                   True, (0, 255, 255), (0, 0, 0))
        screen.blit(txt_eng, (10, 520))
        txt_emo = font_mid.render('Emotion: %s' % emo_str,
                                   True, (255, 255, 0), (0, 0, 0))
        screen.blit(txt_emo, (10, 550))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return data, True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return data, True
        time.sleep(0.5)

    return data, False


def summarize_phase(name, data):
    """汇总一个阶段的数据"""
    from collections import Counter
    log('\n  --- %s 汇总 ---' % name)

    # 用 _is_valid 过滤无效值（None / 空字符串 / 空容器）
    engagements = [d['engagement'] for d in data if _is_valid(d['engagement'])]
    emotions = [d['emotion'] for d in data if _is_valid(d['emotion'])]
    face_counts = [d['face_count'] for d in data if _is_valid(d['face_count'])]
    cb_fes = [d['callback_fe'] for d in data if d['callback_fe']]

    # engagement 是字符串类型（如 'happy'/'neutral'），用 Counter 统计
    if engagements:
        eng_counter = Counter(str(e) for e in engagements)
        log('  engagement 分布: %s (共 %d 次)' % (dict(eng_counter), len(engagements)))
        log('  engagement 全部值: %s' % engagements)
    else:
        log('  engagement: (无有效数据)')

    if emotions:
        emo_counter = Counter(str(e) for e in emotions)
        log('  emotion 分布: %s' % dict(emo_counter))
    else:
        log('  emotion: (无有效数据)')

    if face_counts:
        log('  face_count: min=%s max=%s' % (min(face_counts), max(face_counts)))
    else:
        log('  face_count: (无有效数据)')

    if cb_fes:
        log('  callback_facial_expression: %d 次有数据' % len(cb_fes))
        log('  首次 callback_fe: %s' % repr(cb_fes[0])[:300])
    else:
        log('  callback_facial_expression: (无数据)')

    return {
        'engagement_counter': Counter(str(e) for e in engagements) if engagements else None,
        'emotion_counter': Counter(str(e) for e in emotions) if emotions else None,
        'has_callback_fe': len(cb_fes) > 0,
    }


# ============================================================
# Main
# ============================================================
def main():
    import camera_vision_system_v3 as v3
    import pygame
    import cv2

    section('B: 人脸表情投入度（engagement）语义验证 v2')

    # 初始化 TTS
    log('\n  0. 初始化语音提示...')
    try:
        init_tts()
    except Exception as e:
        log('  ⚠️ TTS 初始化失败: %s' % e)
        log('  ⚠️ 脚本将继续运行但无语音提示，请同时看屏幕指引')
        global _tts_api
        _tts_api = None

    speak('表情投入度测试即将开始')

    log('\n  1. 创建视觉系统（按范例代码: enable_basic=False, camera_id=-1, 1280x720）')
    vs = v3.create_vision_system_v3(
        camera_id=-1, width=1280, height=720,
        enable_basic=False, enable_advanced=False
    )
    log('  ✅ 视觉系统创建成功')

    ts = vs.threaded_system

    # 打开摄像头
    log('\n  2. 打开摄像头...')
    cam_ok = vs.open_camera()
    log('  open_camera() 返回: %s' % cam_ok)
    if not cam_ok:
        log('  ❌ 摄像头打开失败，退出')
        try:
            vs.cleanup()
        except:
            pass
        return

    # 按范例代码方式启用算法 + _init_detectors()
    log('\n  3. 启用算法（face_recognition + facial_expression + _init_detectors）')
    vs.detection_config.enable_face_recognition = True
    log('  enable_face_recognition = True')
    vs.detection_config.enable_facial_expression = True
    log('  enable_facial_expression = True')

    # 关键步骤: _init_detectors()
    log('  调用 _init_detectors()...')
    try:
        vs._init_detectors()
        log('  ✅ _init_detectors() 成功')
    except Exception as e:
        log('  ❌ _init_detectors() 失败: %s' % e)

    # 注册检测回调
    log('\n  4. 注册检测回调...')
    try:
        ts.add_detection_callback(detection_callback)
        log('  ✅ 检测回调已注册')
    except Exception as e:
        log('  ❌ 注册回调失败: %s' % e)

    # 启动后台检测（按范例代码 show_preview=True）
    log('\n  5. 启动后台检测（show_preview=True）...')
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

    # 初始化 pygame
    log('\n  6. 初始化 pygame 显示...')
    # 按工程约定: 只初始化 display + font，避免音频子系统异常
    pygame.display.init()
    pygame.font.init()
    # 画面 640x480 + 顶部标题(36) + 底部指引(28) + engagement(36) + emotion(28) ≈ 640×608，取整 640×620
    screen = pygame.display.set_mode((640, 620))
    pygame.display.set_caption('表情投入度探测 v2 - 按 ESC 退出')
    font_huge = pygame.font.Font(None, 72)
    font_big = pygame.font.Font(None, 36)
    font_mid = pygame.font.Font(None, 28)

    # 人脸检查阶段（5 秒）
    log('\n  7. 人脸检查阶段（5 秒）...')
    speak('请确保脸部在画面中')
    check_start = time.time()
    face_detected = False
    early_exit = False
    while time.time() - check_start < 5:
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

        # 检查是否检测到人脸
        expr_data = get_engagement_data(vs, ts)
        fc = None
        if expr_data:
            fc = expr_data.get('get_face_count')
        # 也检查回调数据
        fr = latest_detection.get('face_recognition', {})
        fe = latest_detection.get('facial_expression', {})

        face_found = (fc is not None and fc > 0) or bool(fr) or bool(fe)
        if face_found:
            face_detected = True

        if face_found:
            txt_face = font_big.render('Face detected! ✅', True, (0, 255, 0), (0, 0, 0))
        else:
            txt_face = font_big.render('No face detected ❌', True, (255, 100, 100), (0, 0, 0))
        screen.blit(txt_face, (180, 250))

        # 显示诊断信息
        diag_lines = [
            'face_count: %s' % fc,
            'face_recognition: %s' % ('有' if fr else '空'),
            'facial_expression: %s' % ('有' if fe else '空'),
            'latest_detection keys: %s' % list(latest_detection.keys()) if latest_detection else '(无回调)',
        ]
        for i, line in enumerate(diag_lines):
            txt = font_mid.render(line, True, (255, 255, 0), (0, 0, 0))
            screen.blit(txt, (10, 420 + i * 30))

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
        time.sleep(0.2)

    # 记录人脸检查结果
    section('B: 人脸检查结果')
    log('  face_detected: %s' % face_detected)
    log('  latest_detection keys: %s' % list(latest_detection.keys()))
    fe = latest_detection.get('facial_expression', {})
    fr = latest_detection.get('face_recognition', {})
    log('  facial_expression: %s' % ('有数据(%s)' % repr(fe)[:200] if fe else '空'))
    log('  face_recognition: %s' % ('有数据(%s)' % repr(fr)[:200] if fr else '空'))

    # 打印 result_accessor 诊断
    ra = getattr(vs, 'result_accessor', None)
    if ra is not None:
        log('  result_accessor 类型: %s' % type(ra).__name__)
        ra_methods = [m for m in dir(ra) if not m.startswith('_') and callable(getattr(ra, m, None))]
        fe_methods = [m for m in ra_methods if 'facial' in m.lower() or 'face' in m.lower() or 'emotion' in m.lower()]
        log('  result_accessor 表情/人脸方法: %s' % fe_methods)
        # 尝试调用
        try:
            ra.refresh_results()
            for mname in fe_methods:
                # has_face_id 需要传 face_id 参数 (takes exactly 2 positional arguments: self, face_id)
                # 此处跳过，避免 TypeError
                if mname == 'has_face_id':
                    log('    %s() -> 跳过 (需传 face_id 参数)' % mname)
                    continue
                try:
                    val = getattr(ra, mname)()
                    log('    %s() = %s' % (mname, repr(val)[:200]))
                except Exception as e:
                    log('    %s() -> 错误: %s' % (mname, str(e)[:100]))
        except Exception as e:
            log('  refresh_results 失败: %s' % e)
    else:
        log('  ❌ vs.result_accessor 不存在')
        log('  vs 属性: %s' % [a for a in dir(vs) if not a.startswith('_') and 'accessor' in a.lower() or 'result' in a.lower()])

    if not face_detected:
        log('\n  ⚠️ 未检测到人脸！可能原因：')
        log('  1. 表情识别 RKNN 模型未加载')
        log('  2. 人脸检测算法未真正启动')
        log('  3. 摄像头角度问题')
        log('  继续运行 3 阶段测试以便收集更多诊断数据...')

    # === 3 阶段数据采集 ===
    all_summaries = {}

    if not early_exit:
        # 阶段 1: 正视屏幕
        data1, early_exit = run_phase(
            vs, ts, screen, font_huge, font_big, font_mid,
            'Phase 1: 正视屏幕',
            '第一阶段，请正对摄像头，保持自然表情',
            duration=10)
        all_summaries['phase1_正视'] = summarize_phase('Phase 1: 正视屏幕', data1)

    if not early_exit:
        speak('休息一下')
        time.sleep(2)

        # 阶段 2: 看向旁边
        data2, early_exit = run_phase(
            vs, ts, screen, font_huge, font_big, font_mid,
            'Phase 2: 看向旁边',
            '第二阶段，请将头转向左侧或右侧，不看屏幕',
            duration=10)
        all_summaries['phase2_看旁'] = summarize_phase('Phase 2: 看向旁边', data2)

    if not early_exit:
        speak('休息一下')
        time.sleep(2)

        # 阶段 3: 闭眼/低头
        data3, early_exit = run_phase(
            vs, ts, screen, font_huge, font_big, font_mid,
            'Phase 3: 闭眼/低头',
            '第三阶段，请闭上眼睛或低头看桌面',
            duration=10)
        all_summaries['phase3_闭眼低头'] = summarize_phase('Phase 3: 闭眼/低头', data3)

    # === 总结 ===
    section('B: 总结 - engagement 语义推断')
    speak('测试完成，感谢配合')

    log('\n  各阶段 engagement 分布对比:')
    log('  ' + '-' * 60)
    for name, s in all_summaries.items():
        ec = s.get('engagement_counter')
        if ec:
            log('  %s: %s' % (name, dict(ec)))
        else:
            log('  %s: (无有效数据)' % name)

    log('\n  各阶段 emotion 分布对比:')
    log('  ' + '-' * 60)
    for name, s in all_summaries.items():
        ec = s.get('emotion_counter')
        if ec:
            log('  %s: %s' % (name, dict(ec)))
        else:
            log('  %s: (无有效数据)' % name)

    log('\n  语义推断:')
    p1 = all_summaries.get('phase1_正视', {}).get('engagement_counter')
    p2 = all_summaries.get('phase2_看旁', {}).get('engagement_counter')
    p3 = all_summaries.get('phase3_闭眼低头', {}).get('engagement_counter')

    if p1 and p2 and p3:
        # engagement 是字符串标签，比较各阶段最常见标签
        p1_top = p1.most_common(1)[0][0]
        p2_top = p2.most_common(1)[0][0]
        p3_top = p3.most_common(1)[0][0]
        log('  各阶段最常见 engagement: 正视=%s, 看旁=%s, 闭眼低头=%s' % (p1_top, p2_top, p3_top))
        log('  engagement 为字符串标签类型，需根据具体标签值推断语义')
    else:
        log('  ❌ 数据不足，无法推断语义')
        log('  可能原因: 表情识别未真正启用 / 无人脸被检测到 / RKNN 模型缺失')
        log('  建议: 检查上方"人脸检查结果"和"result_accessor 诊断"输出')

    # 清理资源
    log('\n  清理资源...')
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
    log('  完成')


if __name__ == '__main__':
    _log_fp = open(LOG_FILE, 'w', encoding='utf-8')
    log('盲点探测 B v2（表情投入度）开始 - %s' % datetime.datetime.now())
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

    log('\n盲点探测 B v2 完成 - %s' % datetime.datetime.now())
    log('日志文件: %s' % LOG_FILE)
    _log_fp.close()
