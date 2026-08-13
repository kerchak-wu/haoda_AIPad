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
  3. 逐个尝试 delete_object_recognition_class(class_name=xxx) 删除类别
  4. 验证数据库是否清空（get_object_database_info）
  5. 删除应用层 object_records.json
  6. 删除磁盘上的物体特征数据库目录（含整个 object_database 文件夹）

注意（基于 camera_vision_system_v3_API分析报告 v2.1）：
  - 报告 2.4 节确认 V3 库本身没有 delete_face 方法，故本工具的删除路径
    与人脸侧不同，仅依赖 delete_object_recognition_class 与磁盘清理两路。
  - 报告 2.5 节指出 delete_object_recognition_class「存在但签名未反射」，
    本脚本使用 class_name= 关键字（与 add_object_recognition_class 同名参数
    推测一致）；若调用失败会跳过并在末尾通过删除磁盘文件兜底。
  - 报告 8.3 节强调 object_db_path 默认 'object_database'，工作目录会影响
    数据库位置，故优先读取 detection_config.object_db_path 作为目标路径。
  - 报告 8.7 节建议「删除整个文件夹后重启程序才能彻底重置」，本脚本会
    用 shutil.rmtree 直接删除整个 object_database 目录。
"""

import os
import json
import shutil

from camera_vision_system_v3 import create_vision_system_v3


# 应用层物体记录文件（由 物体学习.py 生成）
OBJECT_DATA_FILE = 'object_records.json'

# 视觉系统物体特征数据库文件可能位置
# 注：detection_config.object_db_path（默认 'object_database'）会作为运行时
# 实际路径，本列表仅作为兜底候选；运行时会把配置值插入到列表最前面。
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

    # 优先读取 detection_config.object_db_path 作为运行时实际路径
    # 报告 8.3 节：object_db_path 默认 'object_database'，工作目录会影响位置
    configured_db_path = None
    try:
        configured_db_path = vision_system.detection_config.object_db_path
    except Exception as e:
        print('  读取 detection_config.object_db_path 失败: %s' % e)
    if configured_db_path:
        print('  当前 detection_config.object_db_path = %s' % configured_db_path)
        # 把配置值插入候选列表最前，并去重
        if configured_db_path not in OBJECT_DB_PATHS:
            OBJECT_DB_PATHS.insert(0, configured_db_path)
        else:
            OBJECT_DB_PATHS.remove(configured_db_path)
            OBJECT_DB_PATHS.insert(0, configured_db_path)

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
    delete_method_error = None  # 记录方法签名/不存在类错误，末尾用于提示
    for name in class_names:
        try:
            result = vision_system.delete_object_recognition_class(class_name=name)
            print('  ✓ 删除 [%s] 结果: %s' % (name, str(result)))
            deleted_count += 1
        except TypeError as e:
            # 报告 8.2 节参数名陷阱：若 class_name 不是正确参数名会抛 TypeError
            delete_method_error = e
            print('  ✗ 删除 [%s] 失败（TypeError）: %s' % (name, e))
        except AttributeError as e:
            delete_method_error = e
            print('  ✗ 删除 [%s] 失败（AttributeError）: %s' % (name, e))
        except Exception as e:
            print('  ✗ 删除 [%s] 失败: %s' % (name, e))

    print('已尝试删除 %d/%d 个类别' % (deleted_count, len(class_names)))
    if delete_method_error is not None and deleted_count == 0 and class_names:
        print('\n⚠ delete_object_recognition_class 全部失败（%s）' % str(delete_method_error))
        print('  报告 2.5 节确认该方法存在但签名未反射，本脚本猜测参数名 class_name。')
        print('  请直接依赖步骤 6 的磁盘清理方式重置（推荐）。')

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
    print('\n[6/6] 删除应用层记录与磁盘特征目录...')

    # 删除 object_records.json
    if os.path.exists(OBJECT_DATA_FILE):
        os.remove(OBJECT_DATA_FILE)
        print('  ✓ 已删除 %s' % OBJECT_DATA_FILE)
    else:
        print('  %s 不存在，跳过' % OBJECT_DATA_FILE)

    # 删除磁盘特征数据库目录（整个文件夹）
    # 报告 8.7 节：删除整个文件夹后重启程序才能彻底重置
    for db_path in OBJECT_DB_PATHS:
        if os.path.isdir(db_path):
            try:
                shutil.rmtree(db_path)
                print('  ✓ 已删除整个目录 %s' % db_path)
            except Exception as e:
                print('  ✗ 删除目录 %s 失败: %s' % (db_path, e))
        else:
            print('  目录 %s 不存在，跳过' % db_path)

    # ---- 完成 ----
    print('\n' + '=' * 50)
    print('清空完成！')
    print('=' * 50)
    print('\n下一步操作：')
    print('  1. 【重要】先关闭/退出当前 Python 进程，释放对特征文件的占用')
    print('  2. 重新运行「物体学习.py」学习物体')
    print('  3. 学习完成后再运行「物体识别播报.py」')
    print('\n注意（基于报告 8.7 节）：')
    print('  - 已用 shutil.rmtree 删除整个 object_database 目录，重新学习时')
    print('    视觉系统会自动重建该目录，类别计数从 0 开始。')
    print('  - 必须重启 Python 进程后再学习，否则内存中可能仍残留旧模型状态，')
    print('    导致类别 ID 从旧值继续递增。')


if __name__ == '__main__':
    main()
