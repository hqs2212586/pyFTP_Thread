# -*- coding:utf-8 -*-
__author__ = 'Qiushi Huang'

import os
import optparse  # sys.argv的功能类似
# python ftp_client.py -h 192.168.22.33 -p 8091
# user:
# password
import socket
import json
import shelve   # 解决断点续传


class FTPClient(object):
    """ftp客户端"""
    MSG_SIZE = 1024   # 客户端收取消息最长1024

    def __init__(self):
        self.username = None   # 先占位，后期赋值
        self.terminal_display = None   # 定义一个用户登录后的命令行提示
        # 断点续传属性
        self.shelve_obj = shelve.open(".luffy_db")   # .开头的隐藏文件
        self.current_dir = None

        parser = optparse.OptionParser()
        parser.add_option("-s", "--server", dest="server", help="ftp server ip_addr")
        parser.add_option("-P", "--port", type="int", dest="port", help="ftp server port")
        parser.add_option("-u", "--username", dest="username", help="username info")
        parser.add_option("-p", "--password", dest= "password", help= "password info")
        self.options, self.args = parser.parse_args()

        # print(self.options, self.args)
        # print(type(self.options), type(self.args))  # <class 'optparse.Values'> <class 'list'>
        """
        执行程序，提示信息
        # python3 ftp_client.py 1  324
        {'server': None, 'port': None, 'username': None, 'password': None} ['1', '324']
        # python3 -s 127.0.0.1 -P 3308 -u admin -p admin
        {'server': '127.0.0.1', 'port': 3308, 'username': 'admin', 'password': 'admin'} []
        """
        self.argv_verification()  # 调用参数检查
        self.make_connection()  # 创建链接

    def argv_verification(self):
        """检查参数合法性，必须有-s -p"""
        # dict.get(key, default=None)  # 返回字典中key对应的值，若key不存在字典中，则返回default的值（default默认为None）
        # self.option虽然打印出来的形式是字典，但实际是类
        # if not self.options.get('server') or not self.options.get('port'):
        if not self.options.server or not self.options.port:
            exit("Error: must supply server and port parameters")

    def make_connection(self):
        """创建socket链接"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.options.server, self.options.port))

    def get_response(self):
        """
        收到的每个消息都需要序列化
        获取服务器端返回
        :return:
        """
        data = self.sock.recv(self.MSG_SIZE)
        return json.loads(data.decode('utf-8'))

    def auth(self):
        """用户认证"""
        count = 0
        while count < 3:
            username = input("username: ").strip()
            if not username: continue
            password = input("passwrod: ").strip()
            cmd = {
                "action_type": "auth",
                "username": username,
                "password": password
            }
            self.sock.send(json.dumps(cmd).encode('utf-8'))
            # self.sock.recv(1024)
            response = self.get_response()  # 拿到返回数据
            print('response: ', response)
            """  后面的0是zfill的效果
            response:  "{"filesize": 1024, "status_code": 200, "status_msg": 
            "Passed authentication!", "fill": "000000...000"}"
            """
            if response.get('status_code') == 200:  # 通过认证
                self.username = username   # 给username赋值，方便后期使用
                self.terminal_display = "[%s]>>:" % self.username    # 设置为全局变量
                self.current_dir = "/"   # 认证成功保存当前目录（断点续传） win版本用"\\"
                return True
            else:
                print(response.get("status_msg"))
            count += 1

    def unfinished_file_check(self):
        """检查shelve db，把正常传完的文件列表打印，按用户的指令决定是否重传"""
        if list(self.shelve_obj.keys()):
            print("Unfinished file list".center(40, '-'))
            for index, abs_file in enumerate(self.shelve_obj.keys()):
                received_file_size = os.path.getsize(self.shelve_obj[abs_file][1])   # 文件名——》得出大小
                print("%s. %s    %s   %s  %s" % (index, abs_file,
                                                 self.shelve_obj[abs_file][0],  # 文件总大小
                                                 received_file_size,  # 已经接收的文件大小
                                                 received_file_size / self.shelve_obj[abs_file][0]*100
                                                 ))
            while True:
                choice = input("select file index to re-download")
                if not choice: continue
                if choice == 'back': break  # 返回正常交互
                if choice.isdigit():
                    choice = int(choice)
                    if choice >= 0 and choice <= index:   # for循环后index会仍保存最后一次的值
                        selected_file = list(self.shelve_obj.keys())[choice]  # 由key找到对应的文件
                        already_received_size = os.path.getsize(self.shelve_obj[selected_file][1])

                        print("tell server to read file ", selected_file)
                        """下次用户登录时会显示如下信息：
                        ----------Unfinished file list----------
                        0. /BD1280.mp4    241406615   183454223  75.99386744228198
                        select file index to re-download
                        """
                        # abs_filename + size + received_size  发给服务器端
                        self.send_msg("re_get", file_size=self.shelve_obj[selected_file][0],
                                      received_size=already_received_size,
                                      abs_filename=selected_file)
                        # 收响应
                        response = self.get_response()
                        if response.get('status_code') == 401:  # 判断状态码，401：File exist, ready to re_send
                            local_filename = self.shelve_obj[selected_file][1]
                            f = open(local_filename, 'ab')
                            total_size = self.shelve_obj[selected_file][0]
                            recv_size = already_received_size   # 再赋值一个新变量是为了循环
                            """断点续传进度条"""
                            current_percent = int(recv_size / total_size * 100)
                            progress_generator = self.process_bar(total_size, current_percent, current_percent)
                            progress_generator.__next__()

                            while  recv_size < total_size:
                                if total_size - recv_size < 8192:   # 最后一次
                                    data = self.sock.recv(total_size - recv_size)
                                else:
                                    data = self.sock.recv(8192)
                                recv_size += len(data)
                                f.write(data)

                                progress_generator.send(recv_size)   # 断点续传
                                # progeress_generator.send(receoved_size)
                            else:
                                print("file re-get done")
                        else:
                            print(response.get("status_msg"))

    def interactive(self):
        """处理与FTPserver的所有交互"""
        if self.auth():  # 代表验证成功
            # 监测没有传完的函数（断点续传）
            self.unfinished_file_check()

            """验证通过过，进行下一步交互"""
            while True:
                # user_input = input("[%s]:>>" % self.username).strip()
                user_input = input(self.terminal_display).strip()
                if not user_input:continue

                cmd_list = user_input.split()   # ['get', 'a.txt']
                if hasattr(self, "_%s" % cmd_list[0]):
                    func = getattr(self, "_%s" % cmd_list[0])
                    func(cmd_list[1:])  # 对列表切片，处理更多参数
                    # get fill --md5

    def parameter_check(self, args, min_args=None, max_args=None, exact_args=None):   # 不为None时则设置了值
        """解决命令参数合法性检查"""
        if min_args:   # 如果设置了最小参数数量
            if len(args) < min_args:
                print("must provide at least %s parameters but %s received" % (min_args, len(args)))
                return False
        if max_args:   # 如果设置了最大参数数量
            if len(args) > max_args:
                print("need at most %s parameters but %s received." % (max_args, len(args)))
                return False
        if exact_args:  # 如果设置了参数数量
            if len(args) != exact_args:
                print("need exactly %s parameters but %s received." % (exact_args, len(args)))
                return False
        return True  # 上述情况都没发生return True

    def send_msg(self, action_type, **kwargs):
        """打包消息发送到远程"""
        msg_data = {
            'action_type': action_type,
            'fill': ''
        }
        msg_data.update(kwargs)   # 字典update方法把两个字典合在一起

        bytes_msg = json.dumps(msg_data).encode()
        if self.MSG_SIZE > len(bytes_msg):  # 少于定长时，需要补位
            msg_data['fill'] = msg_data['fill'].zfill(self.MSG_SIZE - len(bytes_msg))
            bytes_msg = json.dumps(msg_data).encode()

        self.sock.send(bytes_msg)

    def _ls(self, cmd_args):
        """
        显示当前目录文件列表
        :param cmd_args:
        :return:
        """
        self.send_msg(action_type='ls')
        response = self.get_response()   # 等待服务端给响应：1024定长，内容还包含结果长度
        print(response)
        if response.get('status_code') == 302:   # 准备好发送长消息
            cmd_result_size = response.get('cmd_result_size')
            # 循环接收
            received_size = 0
            cmd_result = b''   # 将消息拼接后，打印在客户端上
            while received_size < cmd_result_size:
                if cmd_result_size - received_size < 8192:   # 最后一次的接收
                    data = self.sock.recv(cmd_result_size - received_size)
                else:
                    data = self.sock.recv(8192)
                cmd_result += data
                received_size += len(data)
            else:
                print(cmd_result.decode("UTF-8"))   # window系统用gbk

    def _pwd(self, cmd_args):
        """查看当前系统目录"""
        self.send_msg(action_type='pwd')
        response = self.get_response()   # 等待服务端给响应：1024定长，内容还包含结果长度
        print(response)
        if response.get('status_code') == 302:  # This msg include the msg size
            cmd_result_size = response.get('cmd_result_size')
            # 循环接收
            received_size = 0
            cmd_result = b''  # 将消息拼接后打印在客户端上
            while received_size < cmd_result_size:
                if cmd_result_size - received_size < 8192:   # 最后接收完所有数据
                    data = self.sock.recv(cmd_result_size - received_size)
                else:
                    data = self.sock.recv(8192)
                cmd_result += data
                received_size += len(data)
            else:
                print(cmd_result.decode("UTF-8"))

    def _cd(self, cmd_args):
        """切换到目标目录"""
        if self.parameter_check(cmd_args, exact_args=1):  # 参数检查,必须为一个,返回True则继续操作
            target_dir = cmd_args[0]
            self.send_msg('cd', target_dir=target_dir)
            response = self.get_response()
            print(response)
            if response.get("status_code") == 350:   # 目录切换
                self.terminal_display = "[/%s]" % response.get("current_dir")
                # 每次切换目录都存客户端都存一次当前目录信息（断点续传）
                self.current_dir = response.get("current_dir")

    def _mkdir(self, cmd_args):
        """增加目录  mkdir test 在当前目录创建子目录"""
        if self.parameter_check(cmd_args, exact_args=1):   # 参数检查，必须为一个
            child_dir = cmd_args[0]   # mkdir后第一个参数，子目录名称
            self.send_msg(action_type='mkdir', child_dir=child_dir)
            response = self.get_response()  # 等待消息
            print(response)
            if response.get("status_code") == 351:  # 目录创建成功
                self.terminal_display = "[/%s]" % response.get("child_dir")

    def _rm(self, cmd_args):
        """删除指定的文件，或者文件夹"""
        if self.parameter_check(cmd_args, exact_args=1):
            target_file_or_dir = cmd_args[0]
            self.send_msg(action_type='rm', target_file_or_dir=target_file_or_dir)
            response = self.get_response()
            print(response)
            if response.get("status_code") == 352:  # 目录或文件已经删除
                self.terminal_display = "[/%s]" % response.get("target_file_or_dir")

    def _get(self, cmd_args):
        """
        从FTP服务端下载文件
        1.拿到文件名
        2.发送到远程
        3.等待服务器相应返回消息
            3.1 如果文件存在，同时发回文件大小
                3.1.1 循环接收
            3.2 文件如果不存在
                print status_msg
        :param cmd_args:
        :return:
        """
        if self.parameter_check(cmd_args, min_args=1):  # 参数检查,返回True则继续操作
            """
            [alex]>>:get
            must provide at least 1 parameters but 0 received
            [alex]:>>get 123 213
            [alex]:>>
            """
            filename = cmd_args[0]  # 文件名
            self.send_msg(action_type='get', filename=filename)   # 发送消息，操作命令和文件名
            response = self.get_response()   # 等待服务端返回消息
            if response.get('status_code') == 301:   # file exist, ready to receive
                file_size = response.get('file_size')
                # 打开文件，循环收
                received_size = 0

                # 调用进度条生成器
                progress_generator = self.process_bar(file_size)
                progress_generator.__next__()

                # 保存到shelve db中（断点续传）
                file_abs_path = os.path.join(self.current_dir, filename)  # 文件绝对路径
                self.shelve_obj[file_abs_path] = [file_size, "%s.download" % filename]  # 以列表方式保存

                f = open("%s.download" % filename, 'wb')   # 下载中，这个文件名后缀加download
                while received_size < file_size:
                    if file_size - received_size < 8192:   # 最后一次可收取完文件内容
                        data = self.sock.recv(file_size - received_size)
                    else:  # 其他情况正常收
                        data = self.sock.recv(8192)
                    received_size += len(data)
                    f.write(data)
                    # 没写完一次，调用一次生成器
                    progress_generator.send(received_size)
                    # print(received_size, file_size)
                else:
                    print("----file [%s] recv done, received size [%s]----" % (filename, file_size))
                    del self.shelve_obj[file_abs_path]  # 收完文件删除这个临时文件（断点续传）
                    f.close()
                    os.rename("%s.download" % filename, filename)   # 下载完成后，后缀取消
            else:
                print('\n')
                print(response.get('status_msg'))
                """
                [alex]:>>get test.mp4
                File does not exist!
                """

    def process_bar(self, total_size, current_percent=0, last_percent=0):
        """进度条优化,生成器"""
        # current_percent = 0
        # last_percent = 0
        while True:
            received_size = yield current_percent
            current_percent = int(received_size / total_size * 100)

            if current_percent > last_percent:
                print('#' * int(current_percent / 2) + "{percent}%".format(percent=current_percent),
                      end='\r', flush=True)
                last_percent = current_percent

    def _put(self, cmd_args):
        """上传本地文件到服务器
        1.确保本地文件存在
        2.拿到本地文件名、大小放进消息头里发给远程
        3.打开文件，发送内容
        """
        if self.parameter_check(cmd_args, exact_args=1):   # 一次只能传一个文件
            local_file = cmd_args[0]
            if os.path.isfile(local_file):
                total_size = os.path.getsize(local_file)
                self.send_msg(action_type='put', file_size=total_size, filename=local_file)
                f = open(local_file, 'rb')
                uploaded_size = 0   # 上传文件大小，用于打印进度条
                # last_percent = 0  # 定义一个变量表示上一次的文件百分比
                progress_generator = self.process_bar(total_size)
                progress_generator.__next__()
                for line in f:
                    self.sock.send(line)
                    """进度条功能，但下述实现方法严重影响效率"""
                    uploaded_size += len(line)

                    # current_percent = int(uploaded_size / total_size * 100)  # int取整
                    # if current_percent > last_percent:
                    #     # end='\r' ，一直在同一行打印
                    #     print("#" * int(current_percent/2) + "{percent}%".format(percent=current_percent), end='\r',
                    #           flush=True)
                    #     last_percent = current_percent  # 新循环的百分比赋值给last
                    progress_generator.send(uploaded_size)
                else:
                    print('\n')   # 强制换行
                    print('file upload done'.center(50, '-'))
                    f.close()


if __name__ == '__main__':
    client = FTPClient()   # 实例化
    client.interactive()  # 用户交互
