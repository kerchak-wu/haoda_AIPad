# -*- coding: utf-8 -*-
"""
清空物体数据库工具
==================
用途：物体识别数据库中残留了旧的测试数据（类别数多于实际学习的物体），
      运行本脚本可清空视觉系统的物体数据库和应用层记录，然后重新运行
      「物体学习.py」学习物体即可恢复干净的识别环境。

使用方法：
  python3 清空物体数据库.py

操作内容：
  1. 初始化视觉系统并打印当前物体数据库信息（探测）
  2. 从 object_records.json 读取已学习的类别名
  3. 逐个调用 delete_object_recognition_class(class_name=xxx) 删除类别
  4. 验证数据库是否清空（get_object_database_info）
  5. 删除应用层 object_records.json
  6. 尝试删除磁盘上的物体特征数据库文件（多个可能路径）

注意：
  - 与人脸 delete_face 不同，delete_object_recognition_class 是按类别名删除，
    设计上支持安全删除单个类别。但为保险起见，本脚本会先打印数据库信息再操作。
  - 若视觉系统内部仍有未知类别名（不在 JSON 中）无法通过 class_name 删除，
    脚本会提示残留类别数，此时可尝试删除磁盘特征文件方式清理。
"""

import os
import json

from camera_vision_system_v3 import create_vision_system_v3


# 应用层物体记录文件（由 物体学习.py 生成）
OBJECT_DATA_FILE = 'object_records.json'

# 视觉系统物体特征数据库文件可能位置
# 参照 face_database 路径推测，以及 skill 中提到的 object_data/ 目录
OBJECT_DB_PATHS = [
    '/home/cxdz/jupyter/user/object_database',
    '/home/cxdz/jupyter/user/ai/object_database',
    '/home/cxdz/jupyter/user/object_data',
    '/home/cxdz/jupyter/user/ai/object_data',
    'object_data',
    'object_database',
]


def load_known_class_names():
    """从 object_records.json 读取已学习的类别名"""
    try:
        with open(OBJECT_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        names = [item['name'] for item in data]
        print('  从 %s 读取到 %d 个类别: %s' % (
            OBJECT_DATA_FILE, len(names), names))
        return names
    except FileNotFoundError:
        print('  %s 不存在，无已知类别名' % OBJECT_DATA_FILE)
        return []
    except Exception as e:
        print('  读取 %s 失败: %s' % (OBJECT_DATA_FILE, e))
        return []


def main():
    print('=' * 50)
    print('清空物体数据库工具')
    print('=' * 50)

    # ---- 1. 初始化视觉系统 ----
    print('\n[1/6] 初始化视觉系统...')
    vision_system = create_vision_system_v3(
        camera_id=-1, width=1280, height=720,
        enable_basic=False, enable_advanced=False
    )
    vision_system.detection_config.enable_object_recognition = True
    vision_system._init_detectors()
    print('视觉系统初始化完成')

    # ---- 2. 打印清空前数据库信息 ----
    print('\n[2/6] 探测当前物体数据库信息...')
    before_info = None
    try:
        before_info = vision_system.get_object_database_info()
        print('清空前数据库信息: %s' % str(before_info))
    except Exception as e:
        print('获取数据库信息失败: %s' % e)
        print('（可能是方法签名不同，跳过探测，继续尝试删除）')

    # ---- 3. 读取已知类别名并逐个删除 ----
    print('\n[3/6] 读取已学习类别名...')
    class_names = load_known_class_names()

    print('\n[4/6] 调用 delete_object_recognition_class 逐个删除...')
    deleted_count = 0
    for name in class_names:
        try:
            result = vision_system.delete_object_recognition_class(class_name=name)
            print('  ✓ 删除 [%s] 结果: %s' % (name, str(result)))
            deleted_count += 1
        except Exception as e:
            print('  ✗ 删除 [%s] 失败: %s' % (name, e))

    print('已尝试删除 %d/%d 个类别' % (deleted_count, len(class_names)))

    # ---- 5. 验证清空结果 ----
    print('\n[5/6] 验证清空结果...')
    try:
        after_info = vision_system.get_object_database_info()
        print('清空后数据库信息: %s' % str(after_info))
        # 如果仍有残留类别，提示用户
        after_str = str(after_info)
        if after_str and after_str != '{}' and after_str != 'None':
            print('\n⚠ 注意：数据库中仍有残留数据。')
            print('  可能原因：视觉系统内部有不在 object_records.json 中的旧类别。')
            print('  解决方案：继续执行步骤 6 删除磁盘特征文件，可彻底清理。')
    except Exception as e:
        print('获取清空后信息失败: %s' % e)

    # 清理视觉系统
    try:
        vision_system.cleanup()
    except Exception:
        pass

    # ---- 6. 删除应用层 JSON 和磁盘特征文件 ----
    print('\n[6/6] 删除应用层记录与磁盘特征文件...')

    # 删除 object_records.json
    if os.path.exists(OBJECT_DATA_FILE):
        os.remove(OBJECT_DATA_FILE)
        print('  ✓ 已删除 %s' % OBJECT_DATA_FILE)
    else:
        print('  %s 不存在，跳过' % OBJECT_DATA_FILE)

    # 删除磁盘特征数据库文件
    for db_path in OBJECT_DB_PATHS:
        if os.path.exists(db_path):
            try:
                for fname in os.listdir(db_path):
                    fpath = os.path.join(db_path, fname)
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                        print('  ✓ 已删除 %s' % fpath)
                print('  目录 %s 已清空' % db_path)
            except Exception as e:
                print('  ✗ 清空目录 %s 失败: %s' % (db_path, e))
        else:
            print('  目录 %s 不存在，跳过' % db_path)

    # ---- 完成 ----
    print('\n' + '=' * 50)
    print('清空完成！')
    print('=' * 50)
    print('\n下一步操作：')
    print('  1. 运行「物体学习.py」重新学习物体')
    print('  2. 学习完成后再运行「物体识别播报.py」')
    print('\n注意：重新学习后物体数据库应从 0 个类别开始计数。')
    print('      若仍有残留数据，请将 debug_log.txt 中的数据库信息反馈以排查。')


if __name__ == '__main__':
    main()
