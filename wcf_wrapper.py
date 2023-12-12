from typing import Tuple
from collections import namedtuple
import os
import re
import pathlib
from wcferry import Wcf, WxMsg
import common
from common import ContentType
import threading
import xml.etree.ElementTree as ET

class WcfWrapper:
    """ 处理wechatFerry操作的类 """
    def __init__(self) -> None:
        self.wcf = Wcf(debug=True)   # 创建WechatFerry实例，用于控制wechat
        self.wxid = self.wcf.get_self_wxid()    #自己的微信ID
        self.msg_types = self.wcf.get_msg_types()
        self.msg_types[49] = '引用,文件,共享链接,..'
        self.wcf_lock = threading.Lock()
        
        self.wcf.enable_receiving_msg() # 开始接收消息
        
    def __del__(self):
        self.wcf.cleanup()  # 退出清理，否则微信客户端会异常
    
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
            
        preview =  f"消息ID={msg.id}, 对话ID={chatid}, 昵称={name}, 消息: {content}"
            
        return preview
    
    def wxid_to_nickname(self, wxid) -> str:
        """ 返回wxid对应的昵称 """
        sender = self.wcf.get_info_by_wxid(wxid)['name']
        return sender
    
    def wxid_to_wxcode(self, wxid) -> str:
        """ 返回wxid对应的微信号 """
        code = self.wcf.get_info_by_wxid(wxid)['code']
        return code
    
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
        
    
    def get_refer_content(self, msg:WxMsg) -> Tuple[ContentType, str]:
        """返回被引用的内容, 如果没有返回None
        Args:
            msg (WxMsg): 微信消息对象
            
        Returns:
            (WxMsgType, str): 类型, 内容(文本或路径)
        """
        # 找到引用的消息
        if msg.type != 49:  #非49 不是引用 
            return None, None
        
        try:                      
            content = ET.fromstring(msg.content)
            refermsg_xml = content.find('appmsg/refermsg')
            if refermsg_xml is None:
                return None, None
            
            # 判断refermsg类型            
            type = int(refermsg_xml.find('type').text)  # 被引用消息type
            refer_id = int(refermsg_xml.find('svrid').text)            
            if type == 1:   #文本
                return (ContentType.text, refermsg_xml.find('content').text)
            elif type == 3: #图片 下载图片
                refer_extra = self.get_msg_extra(refer_id, msg.extra)
                if refer_extra:
                    dl_file = self.wcf.download_image(refer_id, refer_extra, common.temp_dir())
                    if dl_file:
                        return ContentType.image, dl_file
                    
                common.logger().warn("无法获取引用图片, 消息id=%s", str(refer_id))
                return ContentType.ERROR, None
            elif type == 34:    # 语音: 下载语音文件
                audio_file = self.wcf.get_audio_msg(refer_id, common.temp_dir())
                if audio_file:
                    return ContentType.voice, audio_file
                common.logger().warn("无法获取引用语音, 消息ID=%s", str(refer_id))
                return ContentType.ERROR, None
                
            elif type == 49:        # 文件，链接，公众号文章，或另一个引用. 需要进一步判断                
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
                    return ContentType.link, text
                
                elif content_type == 6:     #文件
                    # refer_msg = self.msg_dict.get(refer_id, None)
                    refer_extra = self.get_msg_extra(refer_id, msg.extra)
                    if refer_extra:
                        dl_file = refer_extra
                        # self.wcf.download_attach() 会崩溃
                        if os.path.exists(dl_file):
                            return ContentType.file, dl_file
                    
                    common.logger().warn("无法获得被引用消息中的文件, 消息id=%s", str(refer_id))
                    return ContentType.ERROR, None
                
                elif content_type == 57:     # 另一引用 输出文本部分
                    refer_title = refer_content_xml.find('appmsg/title').text
                    return (ContentType.text, refer_title)
                
                else:
                    common.logger().warn("不支持该类型引用, type=%s, content_type=%s", str(type), str(content_type))
                    return ContentType.UNSUPPORTED, None
            else:           # 其他引用 TBA 视频，文章等
                common.logger().warn("不支持该类型引用, type=%s", str(type))
                return ContentType.UNSUPPORTED, None
            
        except Exception as e:
            common.logger().error("读取引用消息发生错误: %s", common.error_trace(e))    
            return ContentType.ERROR, None
        
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
        wxid = new_extra.split('\\')[0]
        path1 = sample_extra.split(wxid)[0]
        full_path = (pathlib.Path(path1) / pathlib.Path(new_extra)).as_posix()
        return full_path            

    
    def send_message(self, tp:ContentType, payload:str, receiver:str, at_list:str="") -> int:
        """ Universal 通过微信发送各种类型消息
        Args:
            tp (WxMsgType): 消息类型
            payload (str): 消息内容, 文本消息为文本本身, 图片/文件等是文件路径
            receiver (str): 接收人的 roomid(群聊) 或 wxid(单聊)
            at_list (str): 消息要@的人的列表
        Returns:
            int: 结果。0=成功, 其他数字失败
        """
        if tp == ContentType.text:
            return self.send_text(payload, receiver, at_list)
        elif tp == ContentType.image:
            return self.send_image(payload, receiver)
        elif tp == ContentType.file:
            return self.send_file(payload, receiver)        

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
