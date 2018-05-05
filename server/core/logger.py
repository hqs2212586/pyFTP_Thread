# -*- coding:utf-8 -*-
__author__ = 'Qiushi Huang'

import os
import logging
from conf import settings


def set_logger(log_type):
    # 创建logger
    logger = logging.getLogger(log_type)
    logger.setLevel(settings.LOG_LEVEL)

    log_file = os.path.join(settings.LOG_PATH, settings.LOG_TYPES[log_type])
    fh = logging.FileHandler(log_file, encoding='utf-8')    # 打开文件，向文件输出日志
    formatter = settings.LOG_FORMAT   # 设置统一的日志级别

    # 把formatter绑定到文件handler对象
    fh.setFormatter(formatter)
    # 把handler对象绑定给logger对象
    logger.addHandler(fh)
    # 返回内存对象
    return logger

