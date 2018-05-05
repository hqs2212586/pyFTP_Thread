# -*- coding:utf-8 -*-
__author__ = 'Qiushi Huang'

import os
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HOST = '127.0.0.1'
PORT = 9999

USER_HOME_DIR = os.path.join(BASE_DIR, 'home')

ACCOUNT_FILE = "%s/conf/account.ini" % BASE_DIR

MAX_SOCKET_LISTEN = 5

MAX_CONCURRENT_COUNT = 3

# 日志
LOG_LEVEL = logging.INFO

LOG_TYPES = {
    "run": "run.log",
    "error": "error.log"
}

LOG_PATH = os.path.join(BASE_DIR, "log")

LOG_FORMAT = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
