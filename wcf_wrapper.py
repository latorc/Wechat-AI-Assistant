from typing import Tuple
from collections import namedtuple
import os
import re
import pathlib
from wcferry import Wcf, WxMsg
import common
from common import ContentType, ChatMsg
import threading
import xml.etree.ElementTree as ET

class WcfWrapper:
    """ 通过 WechatFerry 操作微信 """
    def __init__(self) -> None:
        self.wcf = Wcf(debug=True)   # 创建WechatFerry实例，用于控制wechat
        # self.wxid = self.wcf.get_self_wxid()    #自己的微信ID
        self.userinfo = self.wcf.get_user_info()
        self.my_name = self.userinfo['name']
        self.msg_types = self.wcf.get_msg_types()
        self.msg_types[49] = '引用,文件,共享链接,..'
        self.contacts = self.read_contacts()
        self.wcf_lock = threading.Lock()
        common.logger().info("Wechat Ferry 初始化完成。登录微信=%s",self.userinfo['name'])
        self.wcf.enable_receiving_msg() # 开始接收消息

    def __del__(self):
        self.wcf.cleanup()  # 退出清理，否则微信客户端会异常

    def read_contacts(self) -> dict:
        """ 读取联系人列表, 存到dict {wxid:contact_dict}"""
        contact_list = self.wcf.get_contacts()
        contact_dict = {}
        for contact in contact_list:
            contact_dict[contact['wxid']] = contact
        return contact_dict

    def msg_preview_str(self, msg:WxMsg) -> str:
        """ 返回消息预览字符串 """
        sender = self.wxid_to_nickname(msg.sender)
        if msg.from_group():
            name = self.wxid_to_nickname(msg.roomid) + "|" + sender
            chatid = msg.roomid
        else:
            name = sender
            chatid = msg.sender

        if msg.is_text():
            content = msg.content
        else:
            content = f"类型={msg.type}({self.msg_types.get(msg.type,'未知类型')})/{self.get_content_type(msg)}"
        preview =  f"({msg.id},{chatid},{name}): {content}"
        return preview

    def wxid_to_contact(self, wxid:str) -> dict:
        """ 根据 wxid 返回联系人 dict。如果找不到返回 None"""
        if wxid in self.contacts:
            return self.contacts[wxid]
        else:
            # 重试读取最新联系人
            self.contacts = self.read_contacts()
            return self.contacts.get(wxid, None)

    def wxid_to_nickname(self, wxid:str) -> str:
        """ 返回wxid对应的昵称, 或者None """
        c = self.wxid_to_contact(wxid)
        if c:
            return c['name']
        else:
            return None
        # # sender = self.wcf.get_info_by_wxid(wxid)['name']
        # if wxid in self.contacts:
        #     sender = self.contacts[wxid]['name']
        # return sender

    def wxid_to_wxcode(self, wxid:str) -> str:
        """ 返回wxid对应的微信号, 或者None """
        c = self.wxid_to_contact(wxid)
        if c:
            return c['code']
        else:
            return None

    def get_msg(self) -> WxMsg:
        """ 从wechat ferry获取消息, 无消息抛异常

        Returns:
            WxMsg: 消息对象
        """
        msg = self.wcf.get_msg()
        # if self.msg_dict is None:
        #     self.msg_dict:dict = {}
        # self.msg_dict[msg.id] = msg

        # if len(self.msg_dict) > 2000:
        #     common.logger().info("消息缓存过多, 清理删除一半")
        #     keys_to_remove = list(self.msg_dict)[:len(self.msg_dict)//2]  # 获取前一半的键
        #     for key in keys_to_remove:
        #         del self.msg_dict[key]  # 删除这些键
        return msg

    def is_msg_at_me(self, msg:WxMsg) -> bool:
        """ 判断消息是否@自己"""
        members = self.wcf.get_chatroom_members(msg.roomid)
        my_wxid = next((k for k, v in members.items() if v == self.my_name), None)
        if not my_wxid:
            common.logger().warning("无法找到自己的wxid, 无法判断是否@自己")
            return False
        if re.findall(r"@(?:所有人|all|All)", msg.content):
            return False  # 排除 @ 所有人
        if re.findall(f"<atuserlist>[\s|\S]*({my_wxid})[\s|\S]*</atuserlist>", msg.xml):
            return True  # 在 @ 清单里
        else:
            return False

    def get_msg_text(self, msg:WxMsg) -> str:
        """ 返回消息的文字部分, 没有则返回空字符串"""
        if msg.type == 1:
            return msg.content
        elif msg.type == 49:    # 引用
            content = ET.fromstring(msg.content)
            title = content.find('appmsg/title')
            if title is not None:
                return title.text
            else:
                return ""
        else:
            return ""


    def get_content_type(self, msg:WxMsg) -> int:
        """ 返回content xml中的type, 没有的话返回None"""
        try:
            content_xml = ET.fromstring(msg.content)
            t = int(content_xml.find('appmsg/type').text)
            return t
        except Exception as e:
            return None

    def get_refer_content(self, msg:WxMsg) -> ChatMsg:
        """返回被引用的内容, 如果没有返回None
        Args:
            msg (WxMsg): 微信消息对象

        Returns:
            (WxMsgType, str): 类型, 内容(文本或路径)
        """
        # 找到引用的消息
        if msg.type != 49:  #非49 不是引用
            return None

        try:
            content = ET.fromstring(msg.content)
            refermsg_xml = content.find('appmsg/refermsg')
            if refermsg_xml is None:
                return None

            # 判断refermsg类型
            refer_type = int(refermsg_xml.find('type').text)  # 被引用消息type
            refer_id = int(refermsg_xml.find('svrid').text)

            if refer_type == 1:   #文本
                return ChatMsg(ContentType.text, refermsg_xml.find('content').text)

            elif refer_type == 3: #图片 下载图片
                refer_extra = self.get_msg_extra(refer_id, msg.extra)
                if refer_extra:
                    dl_file = self.get_image(refer_id, refer_extra)
                    if dl_file:
                        return ChatMsg(ContentType.image, dl_file)
                common.logger().warning("无法获取引用图片, 消息id=%s", str(refer_id))
                return ChatMsg(ContentType.ERROR, None)

            elif refer_type == 34:    # 语音: 下载语音文件
                audio_file = self.wcf.get_audio_msg(refer_id, common.temp_dir())
                if audio_file:
                    return ChatMsg(ContentType.voice, audio_file)
                else:
                    common.logger().warning("无法获取引用语音, 消息ID=%s", str(refer_id))
                    return ChatMsg(ContentType.ERROR, None)

            elif refer_type == 43: # 视频: 下载视频
                video_file = self.get_video(refer_id, msg.extra)
                if video_file:
                    return ChatMsg(ContentType.video, video_file)
                else:
                    common.logger().warning("无法获取引用的视频, 引用消息id=%s", str(refer_id))
                    return ChatMsg(ContentType.ERROR, None)

            elif refer_type == 49:        # 文件，链接，公众号文章，或另一个引用. 需要进一步判断
                refer_content_xml = ET.fromstring(refermsg_xml.find('content').text)
                content_type = int(refer_content_xml.find('appmsg/type').text)
                if content_type in [4,5]:   # 链接或公众号文章
                    texts = []
                    title = refer_content_xml.find('appmsg/title')
                    if title is not None:
                        texts.append(f"标题: {title.text}")
                    des = refer_content_xml.find('appmsg/des')
                    if des is not None:
                        texts.append(f"描述: {des.text}")
                    url = refer_content_xml.find('appmsg/url')
                    if url is not None:
                        texts.append(f"URL: {url.text}")
                    text = '\n'.join(texts)
                    return ChatMsg(ContentType.link, text)

                elif content_type == 6:     #文件
                    # refer_msg = self.msg_dict.get(refer_id, None)
                    refer_extra = self.get_msg_extra(refer_id, msg.extra)
                    if refer_extra:
                        dl_file = refer_extra
                        # self.wcf.download_attach() 会崩溃
                        if os.path.exists(dl_file):
                            return ChatMsg(ContentType.file, dl_file)

                    common.logger().warning("无法获得被引用消息中的文件, 消息id=%s", str(refer_id))
                    return ChatMsg(ContentType.ERROR, None)

                elif content_type == 57:     # 另一引用 输出文本部分
                    refer_title = refer_content_xml.find('appmsg/title').text
                    return ChatMsg(ContentType.text, refer_title)

                else:
                    common.logger().warning("不支持该类型引用, type=%s, content_type=%s", str(refer_type), str(content_type))
                    return ChatMsg(ContentType.UNSUPPORTED, None)
            else:           # 其他引用 TBA 视频，文章等
                common.logger().warning("不支持该类型引用, type=%s", str(refer_type))
                return ChatMsg(ContentType.UNSUPPORTED, None)

        except Exception as e:
            common.logger().error("读取引用消息发生错误: %s", common.error_trace(e))
            return ChatMsg(ContentType.ERROR, None)

    def get_msg_extra(self, msgid:str, sample_extra:str) -> str:
        """ 获取历史消息的extra

        Args:
            msgid (str): WxMsg的id
            sample_extra (str): 同个微信号正常消息的extra

        Returns:
            str: 消息extra, 若无法获取返回None
        """

        query = f"SELECT * FROM MSG WHERE MsgSvrID={msgid}"
        msg_data = self.wcf.query_sql('MSG0.db', query)
        if not msg_data:
            return None
        bextra = msg_data[0].get('BytesExtra')

        # 多种pattern搜索
        patterns = [
            b'\x08\x04\x12.(.*?)\x1a',          # 图片
            b'\x08\x04\x12.(.*?)$',    # 文件
            b'\x08\x04\x12.(.*?)\x1a'           # 自己发的文件
            ]
        match = None
        for p in patterns:
            match = re.compile(p).search(bextra)
            if match:
                break
        if not match:
            return None

        extra = match.group(1)
        new_extra:str = extra.decode('utf-8')
        # 拼接new_extra和sample_extra获得文件路径
        keyword = "FileStorage"
        # 获取sample_extra keyword之前的部分
        part1 = sample_extra.split(keyword)[0]
        # 获取new_extra中，第一个keyword之后的部分
        key_index = new_extra.find(keyword)
        if key_index == -1: #没找到
            part2 = new_extra
        else:
            part2 = new_extra[key_index:]

        # 拼接 part1 part2 得到完整path
        full_path = (pathlib.Path(part1) / pathlib.Path(part2)).resolve().as_posix()
        return full_path


    def downloaded_image(self, main_name:str) -> str:
        """ 如果图片已经下载，返回路径。否则返回 None"""

        tmp = common.get_path(common.TEMP_DIR)
        for file in tmp.iterdir():
            if file.is_file() and file.name.startswith(f"{main_name}."):
                return file
        return None

    def get_image(self, msgid:str, extra:str) -> str:
        """ 下载图片。若已经下载，直接返回已经存在的文件。

        Args:
            msgid (str): 消息id
            extra (str): 消息extra

        Returns:
            str: 下载的文件路径。若失败返回None
        """

        """extra =  'C:/Users/georg/Documents/WeChat Files/wxid_72tjp7ciphuj22/FileStorage/Cache/2024-01/423aed714661dde93e21118c29ac4b2f/\x01C:/Users/georg/Documents/WeChat Files/wxid_72tjp7ciphuj22/FileStorage/MsgAttach/4fe37a8489e1619c6ffdbf24c8fdd6b0/Image/2024-01/4bb051cafb2e98281f2da671c255e1f6.dat'"""
        # 获得文件主名
        pattern = r'/([^/]+)\.[^\.]+$'
        match = re.search(pattern, extra)
        if not match:
            return None
        main_name = match.group(1)

        # 判断文件是否已经下载。如果已经下载，直接返回存在的文件
        dl_file = self.downloaded_image(main_name)
        if dl_file:
            return dl_file

        # 若不存在，调用wcf下载图片
        dl_file = self.wcf.download_image(msgid, extra, common.temp_dir())
        if dl_file:
            return dl_file
        return None

    def get_video(self, msgid:str, extra:str) -> str:
        """ 下载消息附件（视频、文件）
        Args:
            msgid (str): 消息id
            extra (str): 正常消息的extra

        Returns:
            str: 下载的文件路径, 若失败返回None
        """
        filename = self.get_msg_extra(msgid, extra)
        if filename: # 原来下载过
            if os.path.exists(filename): # 文件还存在
                return filename
            else:
                pass
        else:
            filename = common.temp_file(f"Wechat_video_{common.timestamp()}.mp4")

        # 需要重新下载
        res = self.wcf.download_attach(msgid, filename, "")
        if res == 0:
            return filename
        else:
            return None

    def send_message(self, chat_msg:ChatMsg, receiver:str, at_list:str="") -> int:
        """ Universal 通过微信发送各种类型消息
        Args:
            chat_msg (ChatMsg): 消息对象
            receiver (str): 接收人的 roomid(群聊) 或 wxid(单聊)
            at_list (str): 消息要@的人的列表
        Returns:
            int: 结果。0=成功, 其他数字失败
        """
        if chat_msg.type == ContentType.text:
            return self.send_text(chat_msg.content, receiver, at_list)
        elif chat_msg.type == ContentType.image:
            return self.send_image(chat_msg.content, receiver)
        elif chat_msg.type in (ContentType.file, ContentType.voice, ContentType.video):
            return self.send_file(chat_msg.content, receiver)
        else:
            return 99

    # def send_message(self, tp:ContentType, payload:str, receiver:str, at_list:str="") -> int:
    #     """ Universal 通过微信发送各种类型消息
    #     Args:
    #         tp (WxMsgType): 消息类型
    #         payload (str): 消息内容, 文本消息为文本本身, 图片/文件等是文件路径
    #         receiver (str): 接收人的 roomid(群聊) 或 wxid(单聊)
    #         at_list (str): 消息要@的人的列表
    #     Returns:
    #         int: 结果。0=成功, 其他数字失败
    #     """
    #     if tp == ContentType.text:
    #         return self.send_text(payload, receiver, at_list)
    #     elif tp == ContentType.image:
    #         return self.send_image(payload, receiver)
    #     elif tp == ContentType.file:
    #         return self.send_file(payload, receiver)

    def send_text(self, msg: str, receiver: str, at_list: str = "") -> int:
        """ 微信发送文字消息
        :param msg: 消息字符串
        :param receiver: 接收人wxid或者群id
        :param at_list: 要@的wxid, @所有人的wxid为'notify@all'
        返回 0 成功，其他失败
        """
        log_text = f"发送文字给{receiver}({self.wxid_to_nickname(receiver)}): {msg}"
        common.logger().info(log_text)
        # 构造'@...前缀'
        # msg 中需要有 @ 名单中一样数量的 @
        at_str = ""
        if at_list:
            if at_list == "notify@all":  # @所有人
                at_str = " @所有人"
            else:
                wxids = at_list.split(",")
                for wxid in wxids:
                    # 根据 wxid 查找群昵称
                    at_str += f" @{self.wcf.get_alias_in_chatroom(wxid, receiver)}"

        # 发送消息
        if at_str == "":
            res = self.wcf.send_text(f"{msg}", receiver, at_list)
        else:
            res = self.wcf.send_text(f"{at_str} {msg}", receiver, at_list)

        return res

    def send_image(self, file:str, receiver:str) -> int:
        """ 微信发送图片 """
        common.logger().info("发送图片给%s(%s): %s", receiver, self.wxid_to_nickname(receiver), file)
        with self.wcf_lock:
            return self.wcf.send_image(file, receiver)

    def send_file(self, file:str, receiver:str) -> int:
        """ 微信发送文件"""
        common.logger().info("发送文件给%s(%s): %s", receiver, self.wxid_to_nickname(receiver), file)
        with self.wcf_lock:
            return self.wcf.send_file(file, receiver)

    def search_msg(self):
        """ 测试历史消息 """

        msgs = self.wcf.query_sql('MSG0.db', 'SELECT * FROM MSG LIMIT 50')
        # for msg in msgs:
        #     wxmsg = WxMsg()

        #     wxmsg._is_self =
        #     wxmsg._is_group =
        #     wxmsg.type = msg['Type']
        #     wxmsg.id = msg['MsgSvrID']
        #     wxmsg.ts = msg['CreateTime']
        #     wxmsg.sign =
        #     wxmsg.xml =
        #     wxmsg.sender =
        #     wxmsg.roomid =
        #     wxmsg.content =
        #     wxmsg.thumb =
        #     wxmsg.extra =
