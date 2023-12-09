from typing import Tuple
from collections import namedtuple
import os
from wcferry import Wcf, WxMsg
import common
from common import WxMsgType
import threading
import xml.etree.ElementTree as ET

class WcfWrapper:
    """ 处理wechatFerry操作的类 """
    def __init__(self) -> None:
        self.wcf = Wcf(debug=True)   # 创建WechatFerry实例，用于控制wechat
        self.wxid = self.wcf.get_self_wxid()    #自己的微信ID
        self.msg_types = self.wcf.get_msg_types()
        self.msg_types[49] = '引用,文件,共享链接,..'
        self.msg_dict:dict[str, WxMsg] = {}
        self.wcf_lock = threading.Lock()
        
        self.wcf.enable_receiving_msg() # 开始接收消息
        
    def __del__(self):
        self.wcf.cleanup()  # 退出清理，否则微信客户端会异常
    
    def msg_preview_str(self, msg:WxMsg) -> str:
        """ 返回消息预览字符串 """        
        sender = self.wxid_to_nickname(msg.sender)
        if msg.from_group():
            name = self.wxid_to_nickname(msg.roomid) + "|" + sender
        else:
            name = sender
        
        if msg.is_text():
            preview =  f"({name}, {msg.id}): {msg.content}"
        else:
            type_str = self.msg_types.get(msg.type,"未知类型")
            preview =  f"(From={name}, 消息ID={msg.id}): 类型={msg.type}({type_str})/{self.get_content_type(msg)}"
            
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
        """ 获取消息并缓存到列表 
        
        Returns:
            WxMsg: 消息对象        
        """
        msg = self.wcf.get_msg()
        self.msg_dict[msg.id] = msg
        
        if len(self.msg_dict) > 2000:
            common.logger().info("消息缓存过多, 清理删除一半")
            keys_to_remove = list(self.msg_dict)[:len(self.msg_dict)//2]  # 获取前一半的键
            for key in keys_to_remove:
                del self.msg_dict[key]  # 删除这些键
                
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
        
    
    def get_refer_content(self, msg:WxMsg) -> Tuple[WxMsgType, str]:
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
                return (WxMsgType.text, refermsg_xml.find('content').text)
            elif type == 3: #图片 下载图片
                refer_msg:WxMsg = self.msg_dict.get(refer_id, None)
                if refer_msg:
                    dl_file = self.wcf.download_image(refer_msg.id, refer_msg.extra, common.temp_dir())
                    if dl_file:
                        return WxMsgType.image, dl_file
                else:
                    common.logger().warn("无法获得被引用消息中的图片, 消息id=%s", str(refer_id))
                    return None, None
                
            elif type == 49:        # 文件，链接，公众号文章，或另一个引用. 需要进一步判断                
                refer_content_xml = ET.fromstring(refermsg_xml.find('content').text)
                content_type = int(refer_content_xml.find('appmsg/type').text)
                if content_type in [4,5]:   # 链接或公众号文章
                    title = refer_content_xml.find('appmsg/title').text
                    des = refer_content_xml.find('appmsg/des').text
                    url = refer_content_xml.find('appmsg/url').text
                    text = f"Title: {title}\nDescription: {des}\nURL:{url}"
                    return WxMsgType.link, text
                
                elif content_type == 6:     #文件
                    refer_msg = self.msg_dict.get(refer_id, None)
                    if refer_msg:
                        dl_file = refer_msg.extra
                        if os.path.exists(dl_file):
                            return WxMsgType.file, dl_file
                    else:
                        common.logger().warn("无法获得被引用消息中的文件, 消息id=%s", str(refer_id))
                        return None, None
                elif content_type == 57:     # 另一引用 输出文本部分
                    refer_title = refer_content_xml.find('appmsg/title').text
                    return (WxMsgType.text, refer_title)
                else:
                    common.logger().warn("未实现该消息类型的处理, type=%s, content_type=%s", str(type), str(content_type))
                    return None, None
            else:           # 其他引用 暂时不处理 TBA 视频，文章等
                common.logger().warn("未实现该消息类型的处理, type=%s", str(type))
                return None, None
            
        except Exception as e:
            common.logger().error("读取引用消息发生错误: %s", str(e))    
            return None, None    

    
    def send_message(self, tp:WxMsgType, payload:str, receiver:str, at_list:str="") -> int:
        """ Universal 通过微信发送各种类型消息
        Args:
            tp (WxMsgType): 消息类型
            payload (str): 消息内容, 文本消息为文本本身, 图片/文件等是文件路径
            receiver (str): 接收人的 roomid(群聊) 或 wxid(单聊)
            at_list (str): 消息要@的人的列表
        Returns:
            int: 结果。0=成功, 其他数字失败
        """
        if tp == WxMsgType.text:
            return self.send_text(payload, receiver, at_list)
        elif tp == WxMsgType.image:
            return self.send_image(payload, receiver)
        elif tp == WxMsgType.file:
            return self.send_file(payload, receiver)        

    def send_text(self, msg: str, receiver: str, at_list: str = "") -> int:
        """ 微信发送文字消息
        :param msg: 消息字符串
        :param receiver: 接收人wxid或者群id
        :param at_list: 要@的wxid, @所有人的wxid为'notify@all'
        返回 0 成功，其他失败 
        """
        log_text = f"微信发送文字给({self.wxid_to_nickname(receiver)}): {msg}"
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
        common.logger().info("微信发送图片给(%s): %s", self.wxid_to_nickname(receiver), file)
        with self.wcf_lock:
            return self.wcf.send_image(file, receiver)
        
    def send_file(self, file:str, receiver:str) -> int:
        """ 微信发送文件"""
        common.logger().info("微信发送文件给(%s): %s", self.wxid_to_nickname(receiver), file)   
        with self.wcf_lock:
            return self.wcf.send_file(file, receiver)