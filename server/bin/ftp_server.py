# -*- coding:utf-8 -*-
__author__ = 'Qiushi Huang'

import os
import sys
import platform

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 将系统目录添加到环境变量
sys.path.append(BASE_DIR)

if __name__ == '__main__':
    from core import management
    # sys.argv：命令行参数List，第一个元素是程序本身路径
    argv_parser = management.ManagementTool(sys.argv)
    argv_parser.execute()  # 解析并执行指令
