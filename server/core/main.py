# -*- coding:utf-8 -*-
__author__ = 'Qiushi Huang'

import os
import time
import socket
from conf import settings
from core import utils
from core.logger import set_logger
import logging
import json
import hashlib
import configparser
import subprocess
from threading import Thread,Lock
import queue  # 用queue来实现线程池


run_logger = set_logger('run')
error_logger = set_logger('error')


class FTPServer(object):
    """处理与客户端所有的交互socket server"""
    STATUS_CODE= {   # 状态码，前后端对应
        200: "Passed authentication!",
        201: "Wrong username or password!",
        300: "File does not exist!",
        301: "File exist, and this msg include the file size!",
        302: "This msg include the msg size",
        350: "Dir changed!",
        351: "Dir does't exist!",
        352: "Dir or file deleted!",
        401: "File exist, ready to re-send",
        402: "File exist, but file size doesn't match！"
    }

    MSG_SIZE = 1024   # 消息最长1024，包头定长

    def __init__(self, management_instance):
        """构造函数初始化"""
        self.management_instance = management_instance
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((settings.HOST, settings.PORT))  # ('127.0.0.1', 9999)
        # socket设置为监听模式，监听backlog外来的连接请求
        self.sock.listen(settings.MAX_SOCKET_LISTEN)
        self.q_threadpool = queue.Queue(settings.MAX_CONCURRENT_COUNT)   # 创建队列，最大值为3，先进先出
        self.accounts = self.load_accounts()
        self.user_obj = None
        self.user_current_dir = None   # 临时变量——当前目录，默认为空，用于实现目录切换
        # 日志

    def run_forever(self):
        """启动socket server"""
        print('starting FTP server on %s:%s'.center(50, '-') % (settings.HOST, settings.PORT))
        run_logger.info("starting FTP server on %s:%s" % (settings.HOST, settings.PORT))

        while True:
            # self.request, self.addr = self.sock.accept()   # 赋值conn,addr为全局变量
            request, addr = self.sock.accept()
            print('got a new connection from %s' % (addr,))  # 占位符和元组的应用
            run_logger.info('got a new connection from %s' % (addr,))
            try:   # 防止handle处理中各类异常导致服务端停止
                # self.handle()
                t = Thread(target=self.handle, args=(request, addr))   # 对handle作线程处理
                self.q_threadpool.put(t)      # 线程对象放入队列
                t.start()
            except ConnectionResetError:
                self.q_threadpool.get()
                break
            except Exception as e:
                print("Error happened with client, close connection", e)
                run_logger.error("Error happened with client, close connection", e)
                error_logger.error("Error happened with client, close connection", e)
                request.close()   # 将实例清掉
                # self.q_threadpool.get()    # 从队列中将线程取出

    def handle(self, request, addr):
        """
        处理与用户的所有指令交互
        handle执行完一个链接结束，需要在run_forever开始下一个链接
        :return:
        """
        while True:
            raw_data = request.recv(self.MSG_SIZE)   # 接收数据
            print('----->', raw_data)
            run_logger.info('server receive data----->', raw_data)
            if not raw_data:
                print('connection %s is lost....' % (addr, ))
                run_logger.error('connection %s is lost....' % (addr, ))
                error_logger.error('connection %s is lost....' % (addr, ))
                # 断开一个客户端链接时，清掉request, addr
                del request, addr
                # 从队列中删除
                self.q_threadpool.get()
                break

            data = json.loads(raw_data.decode('utf-8'))   # data赋值非常频繁，因此不赋为全值
            action_type = data.get("action_type")   # 根据类型调用响应的方法
            if action_type:
                """如果有收到消息"""
                if hasattr(self, "_%s" % action_type):   # 利用反射
                    func = getattr(self, "_%s" % action_type)
                    func(data, request, addr)
            else:
                """如果收到的是None或者是不合法的消息"""
                print("invalid command,")
                run_logger.warning("invalid command,")

    def load_accounts(self):
        """加载所有账户的信息"""
        config_obj = configparser.ConfigParser()
        config_obj.read(settings.ACCOUNT_FILE)

        print(config_obj.sections())   # ['alex', 'egon']
        run_logger.info(config_obj.sections())
        return config_obj

    def authenticate(self, username, password):
        """用户认证方法"""
        # 登录计数由客户端完成，服务器只管处理认证
        if username in self.accounts:
            _password = self.accounts[username]['password']
            md5_obj = hashlib.md5()
            md5_obj.update(password.encode('utf-8'))  # 在hash之前必须encode
            md5_password = md5_obj.hexdigest()
            print('password:', _password, md5_password)
            run_logger.info("%s needs to pass authentication" % username)
            if md5_password == _password:
                print("passed authentication")
                run_logger.info("%s passed authentication" % username)
                # 认证成功之后，把用户信息存在当前类里（创建user_obj）
                self.user_obj = self.accounts[username]   # 拿到所有信息
                # 保存用户家目录，将家目录属性保存在对象user_obj中
                self.user_obj['home'] = os.path.join(settings.USER_HOME_DIR, username)
                self.user_current_dir = self.user_obj['home']   # 赋值为家目录
                return True
            else:
                print("wrong username or password")
                run_logger.error("%s 有此用户，密码不正确" % username)
                error_logger.error("%s 有此用户，密码不正确" % username)
                return False
        else:
            print("wrong username pr password11223")
            run_logger.error("无此用户 %s" % username)
            error_logger.error("无此用户 %s" % username)
            return False

    def send_response(self, request, addr, status_code, *args, **kwargs):
        """
        打包发送消息给客户端
        :param status_code:
        :param args:
        :param kwargs:{filename:ddd, filesize:222}
        :return:
        """
        data = kwargs
        data['status_code'] = status_code   # 消息码
        data['status_msg'] = self.STATUS_CODE[status_code]  # 消息内容
        data['fill'] = ''
        bytes_data = json.dumps(data).encode('utf-8')
        # 判断变成byte的数据长度
        if len(bytes_data) < self.MSG_SIZE:
            # zfill() 方法返回指定长度的字符串，原字符串右对齐，前面填充0。
            data['fill'] = data['fill'].zfill(self.MSG_SIZE - len(bytes_data))
            bytes_data = json.dumps(data).encode('utf-8')
        run_logger.info("pack data send to %s" % (addr,))
        request.send(bytes_data)   # request = conn

    def _auth(self, data, request, addr):   # 用下划线区分与客户端交互的指令
        """处理用户认证请求"""
        print("auth", data)
        run_logger.info("handle with user auth,data: %s" % data)
        # 调用用户认证
        if self.authenticate(data.get('username'), data.get('password')):
            # 认证成功，
            # 1、标准化返回信息内容，运用状态码
            # 2、json.dumps
            # 3、 encode
            run_logger.info("%s Passed authentication!" % data.get('username'))
            self.send_response(request, addr, status_code=200, filesize=1024)

        else:
            # 认证失败
            run_logger.error("%s auth failed" % data.get('username'))
            error_logger.error("%s auth failed" % data.get('username'))
            self.send_response(request, addr, status_code=201)
            self.q_threadpool.get()

    def _get(self, data, request, addr):
        """
        客户端从服务器下载文件
        1、拿到文件名
        2、判断文件是否存在
            2.1、如果存在返回状态码和文件大小
                2.1.1 打开文件，发送数据
            2.2、如果不存在，返回状态码

        :param data:
        :return:
        """
        filename = data.get('filename')  # 拿到文件名，data在handle方法中
        # full_path = os.path.join(self.user_obj['home'], filename)  # 家目录和文件名拼起来
        full_path = os.path.join(self.user_current_dir, filename)
        if os.path.isfile(full_path):  # 判断文件是否存在
            filesize = os.stat(full_path).st_size    # os.stat获取文件属性，st_size为文件大小
            self.send_response(request, addr, status_code=301, file_size=filesize)   # 发送文件状态和文件大小
            print("ready to send file")
            run_logger.info("server get ready to send file")

            # 发送文件
            f = open(full_path, 'rb')
            for line in f:
                request.send(line)
            else:
                print('file send done..', full_path)
                run_logger.info("file send done... %s" % full_path)
            f.close()

        else:
            self.send_response(request, addr, status_code=300)
            run_logger.warning("status<300>: File does not exist!")

    def _re_get(self, data, request, addr):
        """re-send file to client
        服务器端接收到的消息：
        '{"file_size": 241406615, "received_file_size": 183454223, "abs_filename": "/BD1280.mp4"}'
        1.拼接文件路径
        2.判断文件是否存在
            2.1 如果存在，判断文件大小是否与客户端发过来的一致
                2.1.1 如果不一致，返回错误信息
                2.1.2 如果一致，告诉客户端准备续传
                2.1.3 打开文件,seek到指定位置，循环发送
            2.2 文件不存在，返回错误
        """
        print("_re_get", data)
        run_logger.info("func<_re_get>: %s" % data)
        abs_filename = data.get('abs_filename')
        full_path = os.path.join(self.user_obj['home'], abs_filename.strip("/"))  # 去除斜杆拼接,win环境是strip('\\')
        # /Users/hqs/PycharmProjects/pyFTP_Linux/server/home/alex/BD1280.mp4
        print("re-get fullpath", full_path)
        run_logger.info("re-get fullpath: %s" % full_path)
        if os.path.isfile(full_path):  # 判断文件是否存在
            # 判断文件大小
            if os.path.getsize(full_path) == data.get("file_size"):  # 一致
                self.send_response(request, addr, status_code=401)
                run_logger.info("status<401>: File exist, ready to re-send")
                f = open(full_path, 'rb')
                f.seek(data.get("received_size"))
                for line in f:
                    request.send(line)
                else:
                    print("----file re-send done -----")
                    run_logger.info("file re-send done")
                    f.close()
            else:   # 不一致
                run_logger.error("status<402>:File exist, but file size doesn't match！%s" % full_path)
                error_logger.error("status<402>:File exist, but file size doesn't match！%s" % full_path)
                self.send_response(request, addr, status_code=402, file_size_on_server=os.path.getsize(full_path))
        else:
            run_logger.error("status<300>:File does not exist! %s" % full_path)
            error_logger.error("status<300>:File does not exist! %s" % full_path)
            self.send_response(request, addr, status_code=300)  # 文件不存在

    def _put(self, data, request, addr):
        """
        客户端上传文件到服务器
        1.拿到local文件名、大小。
        2.检查本地是否已经有相应的文件。self.user_current_dir/local_file
            2.1 if file exist, create a new file with file.timestamp suffix。
            2.2 if not, create a new file named local_file name
        3.start to receive data
        :param data:
        :return:
        """
        local_file = data.get("filename")
        full_path = os.path.join(self.user_current_dir, local_file)  # 文件
        if os.path.isfile(full_path):  # 代表文件已存在，不能覆盖，创建文件名加时间戳
            filename = "%s.%s" % (full_path, time.time())   # 可以把时间格式化
        else:
            filename = full_path   # 如果文件不存在
        f = open(filename, 'wb')
        total_size = data.get('file_size')
        received_size = 0

        while received_size < total_size:
            if total_size - received_size < 8192:  # 最后一次接收
                data = request.recv(total_size - received_size)
            else:
                data = request.recv(8192)
            received_size += len(data)
            f.write(data)
            print(received_size, total_size)
            run_logger.info("received size: %s, total size: %s"(received_size ,total_size))
        else:
            print('file %s recv done' % local_file)
            run_logger.info("file %s received done" % local_file)
            f.close()

    def _ls(self, data, request, addr):
        """执行ls命令并发送结果给客户端"""
        # 客户端直接运行ls，默认显示的是入口程序所在目录
        # cmd_obj = subprocess.Popen('ls', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cmd_obj = subprocess.Popen('ls %s' % self.user_current_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = cmd_obj.stdout.read()
        stderr = cmd_obj.stderr.read()

        cmd_result = stdout + stderr
        # 没有任何文件的情况：
        if not cmd_result:
            cmd_result = b'current dir has no file at all'
        self.send_response(request, addr, status_code=302, cmd_result_size=len(cmd_result))
        request.sendall(cmd_result)
        run_logger.info("ls command result: %s" % cmd_result)

    def _pwd(self, data, request, addr):
        """执行pwd命令并发送结果给客户端"""
        cmd_obj = subprocess.Popen("cd %s && pwd" % self.user_current_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = cmd_obj.stdout.read()
        print(stdout)
        # b'/Users/hqs/PycharmProjects/pyFTP_Linux/server/home/alex\n'
        stdout = stdout.decode('utf-8').replace(settings.USER_HOME_DIR, '').encode('utf-8')
        stderr = cmd_obj.stderr.read()
        cmd_result = stdout + stderr
        self.send_response(request, addr, status_code=302, cmd_result_size=len(cmd_result))
        request.sendall(cmd_result)

    def _mkdir(self, data, request, addr):
        """在当前目录下，增加目录"""
        child_dir = data.get("child_dir")
        cmd_obj = subprocess.Popen("cd %s && mkdir %s" % (self.user_current_dir, child_dir), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = cmd_obj.stdout.read()
        stderr = cmd_obj.stderr.read()  # 应该可以返回重复创建错误

        cmd_result = stdout + stderr
        self.send_response(request, addr, status_code=351, cmd_result_size=len(cmd_result))
        request.sendall(cmd_result)

    def _rm(self, data, request, addr):
        """删除指定的文件，或者文件夹"""
        target_file_or_dir = data.get("target_file_or_dir")
        cmd_obj = subprocess.Popen("cd %s && rm -rf %s" % (self.user_current_dir, target_file_or_dir), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = cmd_obj.stdout.read()
        stderr = cmd_obj.stderr.read()

        cmd_result = stdout + stderr
        self.send_response(request, addr, status_code=352, cmd_result_size=len(cmd_result))
        request.sendall(cmd_result)

    def _cd(self, data, request, addr):
        """根据客户端发过来的目标目录，改变self.user_current_dir 的值
        1.把target_dir 跟 user_current_dir 拼接
        2.检测要切换的目录是否存在
            2.1 如果存在，改变self.user_current_dir的值到新路径
            2.2 如果不存在，返回错误消息
        """
        lock = Lock()
        lock.acquire()
        target_dir = data.get("target_dir")
        # full_path = os.path.join(self.user_current_dir, target_dir)  # 处理不了由cd ..拼接的相对路径alex/test/../../..
        full_path = os.path.abspath(os.path.join(self.user_current_dir, target_dir))  # abspath解决上述问题
        print("full path: ", full_path)
        # 检测目录是否存在
        if os.path.isdir(full_path):
            # 判断是否是以家目录开头的路径，匹配则有权限
            if full_path.startswith(self.user_obj['home']):
                self.user_current_dir = full_path   # 赋值到新目录
                relative_current_dir = self.user_current_dir.replace(self.user_obj['home'], '')
                self.send_response(request, addr, status_code=350, current_dir=relative_current_dir)
                run_logger.info("Dir changed!")
            else:
                self.send_response(request, addr, status_code=351)    # 无权限直接提示目录不存在
                run_logger.warning("351: Dir does't exist!")
        else:
            self.send_response(request, addr, status_code=351)
            run_logger.warning("351: Dir does't exist!")
        lock.release()


