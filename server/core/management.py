# -*- coding:utf-8 -*-
__author__ = 'Qiushi Huang'

from core import main

class ManagementTool(object):
    """对用户输入的指令进行解析并调用相应模块进行处理"""
    def __init__(self, sys_argv):
        """构造函数"""
        self.sys_argv = sys_argv   # [createuser alex]
        print(self.sys_argv)
        self.verify_argv()

    def verify_argv(self):
        """
        验证指令是否合法
        python  ftp_server.py  start
        """
        """验证指令数量"""
        if len(self.sys_argv) < 2:
            self.help_msg()   # 打印帮助信息
        cmd = self.sys_argv[1]
        # 反射的理解
        if not hasattr(self, cmd):  # 判断obj内有没有cmd属性
            """没有sys_argv[1]对应的这个命令，打印报错和帮助信息"""
            print('invalid argument')
            self.help_msg()

    def help_msg(self):
        """帮助信息"""
        msg = """
        start     start  FTP server
        stop      stop   FTP server
        restart   restart FTP server
        createuser username   create FTP user
        """
        exit(msg)  # 退出并打印

    def execute(self):
        """解析并执行指令"""
        cmd = self.sys_argv[1]
        func = getattr(self, cmd)
        func()

    def start(self):
        """start ftp server"""
        server = main.FTPServer(self)  # 传参self实现management对象传入FTPServer类
        server.run_forever()

    def createuser(self):
        print(self.sys_argv)  # 直接拿数据，不需要传参数
