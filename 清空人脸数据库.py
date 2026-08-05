# -*- coding: utf-8 -*-
"""
清空人脸数据库工具
==================
用途：当人脸识别功能失效（检测到人脸但 get_face_id 返回 None）时，
      可能是之前调用 delete_face 破坏了特征数据库。运行本脚本可清空
      视觉系统的人脸数据库，然后重新运行「人脸学习.py」学习人脸即可
      恢复识别功能。

使用方法：
  python3 清空人脸数据库.py

操作内容：
  1. 调用 vision_system.clear_face_database() 清空视觉系统内部数据库
  2. 删除应用层 face_records.json（会被人脸学习程序重新生成）
  3. 删除 face_effect_map.json 中的映射（face_id 会变，旧映射无效）
  4. 删除磁盘上的 face_database 特征文件（face_features.npy / face_ids.npy）
"""

import os
import json

from camera_vision_system_v3 import create_vision_system_v3


# 人脸记录文件
FACE_DATA_FILE = 'face_records.json'
FACE_EFFECT_MAP_FILE = 'face_effect_map.json'

# 视觉系统人脸特征数据库文件（两个可能的位置）
FACE_DB_PATHS = [
    '/home/cxdz/jupyter/user/face_database',
    '/home/cxdz/jupyter/user/ai/face_database',
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

    # ---- 3. 删除磁盘特征文件 ----
    print('\n[4/4] 删除磁盘特征数据库文件...')
    for db_path in FACE_DB_PATHS:
        if os.path.exists(db_path):
            for fname in os.listdir(db_path):
                fpath = os.path.join(db_path, fname)
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    print('✓ 已删除 %s' % fpath)
            print('  目录 %s 已清空' % db_path)
        else:
            print('  目录 %s 不存在，跳过' % db_path)

    print('\n' + '=' * 50)
    print('清空完成！')
    print('=' * 50)
    print('\n下一步操作：')
    print('  1. 运行「人脸学习.py」重新学习人脸')
    print('  2. 学习完成后再运行「人脸识别灯效.py」')
    print('\n注意：新学习的人脸 ID 会从 0 或 1 开始（不再是 7、8、9...）')


if __name__ == '__main__':
    main()
