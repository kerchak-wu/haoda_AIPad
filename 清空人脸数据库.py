# -*- coding: utf-8 -*-
"""
清空人脸数据库工具
==================
用途：当人脸识别功能失效（检测到人脸但 get_face_id 返回 None 或匹配异常）时，
      可能是特征数据库损坏或应用层记录与视觉系统内部状态不一致。运行本脚本
      可清空视觉系统的人脸数据库，然后重新运行「人脸学习.py」学习人脸即可
      恢复识别功能。

使用方法：
  python3 清空人脸数据库.py

操作内容：
  1. 调用 vision_system.clear_face_database() 清空视觉系统内部数据库
  2. 删除应用层 face_records.json（会被人脸学习程序重新生成）
  3. 删除 face_effect_map.json 中的映射（face_id 会变，旧映射无效）
  4. 删除磁盘上的 face_database 目录（含 face_features.npy / face_ids.npy）

注意（基于 camera_vision_system_v3_API分析报告 v2.1）：
  - 报告 2.4 节确认 V3 库本身【没有】 delete_face 方法；旧记忆中
    「delete_face 破坏模型」的现象来自应用层私有实现，非 V3 库接口。
    本脚本只用 V3 官方 clear_face_database() + 删除磁盘特征目录两路清理。
  - 报告 2.4 节确认 clear_face_database() / get_face_database_info() 均存在。
  - 报告 8.3 节强调 face_db_path 默认 'face_database'，工作目录会影响位置，
    故优先读取 detection_config.face_db_path 作为目标路径。
  - 报告 8.7 节明确：clear_face_database() 之后立即 learn_new_face() 可能
    face_id 从旧值继续递增；如需彻底从 0 开始，应删除 face_database/ 整个
    文件夹后重启程序。本脚本使用 shutil.rmtree 直接删除整个目录。
"""

import os
import json
import shutil

from camera_vision_system_v3 import create_vision_system_v3


# 人脸记录文件（与 V3 SDK 的 face_database/ 目录统一管理）
FACE_DATA_DIR = 'face_database'
FACE_DATA_FILE = os.path.join(FACE_DATA_DIR, 'face_records.json')
FACE_EFFECT_MAP_FILE = 'face_effect_map.json'

# 视觉系统人脸特征数据库文件可能位置
# 注：detection_config.face_db_path（默认 'face_database'）会作为运行时
# 实际路径，本列表仅作为兜底候选；运行时会把配置值插入到列表最前面。
FACE_DB_PATHS = [
    '/home/cxdz/jupyter/user/face_database',
    '/home/cxdz/jupyter/user/ai/face_database',
    'face_database',
]


def main():
    print('=' * 50)
    print('清空人脸数据库工具')
    print('=' * 50)

    # ---- 1. 初始化视觉系统并清空数据库 ----
    print('\n[1/4] 初始化视觉系统...')
    vision_system = create_vision_system_v3(
        camera_id=-1, width=1280, height=720,
        enable_basic=False, enable_advanced=False
    )
    vision_system.detection_config.enable_face_recognition = True
    vision_system._init_detectors()
    print('视觉系统初始化完成')

    # 优先读取 detection_config.face_db_path 作为运行时实际路径
    # 报告 8.3 节：face_db_path 默认 'face_database'，工作目录会影响位置
    configured_db_path = None
    try:
        configured_db_path = vision_system.detection_config.face_db_path
    except Exception as e:
        print('  读取 detection_config.face_db_path 失败: %s' % e)
    if configured_db_path:
        print('  当前 detection_config.face_db_path = %s' % configured_db_path)
        # 把配置值插入候选列表最前，并去重
        if configured_db_path not in FACE_DB_PATHS:
            FACE_DB_PATHS.insert(0, configured_db_path)
        else:
            FACE_DB_PATHS.remove(configured_db_path)
            FACE_DB_PATHS.insert(0, configured_db_path)

    # 查看清前数据库信息
    try:
        before_info = vision_system.get_face_database_info()
        print('清空前数据库信息: %s' % str(before_info))
    except Exception as e:
        print('获取数据库信息失败: %s' % e)

    print('\n[2/4] 调用 clear_face_database() 清空视觉系统数据库...')
    try:
        vision_system.clear_face_database()
        print('✓ 视觉系统人脸数据库已清空')
    except Exception as e:
        print('✗ clear_face_database 调用失败: %s' % e)

    # 查看清后数据库信息
    try:
        after_info = vision_system.get_face_database_info()
        print('清空后数据库信息: %s' % str(after_info))
    except Exception as e:
        print('获取数据库信息失败: %s' % e)

    # 清理视觉系统
    try:
        vision_system.cleanup()
    except Exception:
        pass

    # ---- 2. 删除应用层 JSON 文件 ----
    print('\n[3/4] 删除应用层记录文件...')
    for f in [FACE_DATA_FILE, FACE_EFFECT_MAP_FILE]:
        if os.path.exists(f):
            os.remove(f)
            print('✓ 已删除 %s' % f)
        else:
            print('  %s 不存在，跳过' % f)

    # ---- 3. 删除磁盘特征数据库目录（整个文件夹）----
    # 报告 8.7 节：删除 face_database/ 整个文件夹后重启程序才能彻底重置
    print('\n[4/4] 删除磁盘特征数据库目录...')
    for db_path in FACE_DB_PATHS:
        if os.path.isdir(db_path):
            try:
                shutil.rmtree(db_path)
                print('✓ 已删除整个目录 %s' % db_path)
            except Exception as e:
                print('✗ 删除目录 %s 失败: %s' % (db_path, e))
        else:
            print('  目录 %s 不存在，跳过' % db_path)

    print('\n' + '=' * 50)
    print('清空完成！')
    print('=' * 50)
    print('\n下一步操作：')
    print('  1. 【重要】先关闭/退出当前 Python 进程，释放对特征文件的占用')
    print('  2. 重新运行「人脸学习.py」学习人脸')
    print('  3. 学习完成后再运行「人脸识别灯效.py」')
    print('\n注意（基于报告 8.7 节）：')
    print('  - 已用 shutil.rmtree 删除整个 face_database 目录，重新学习时')
    print('    视觉系统会自动重建该目录，新学习的 face_id 从 0 开始。')
    print('  - 必须重启 Python 进程后再学习，否则 clear_face_database() 之后')
    print('    立即 learn_new_face() 可能出现 face_id 从旧值继续递增的情况。')


if __name__ == '__main__':
    main()
