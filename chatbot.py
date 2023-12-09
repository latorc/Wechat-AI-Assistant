import queue
import re
from typing import Tuple
from wcf_wrapper import WcfWrapper, WxMsgType
from wcferry import WxMsg
import config
from config import AdminCmd
import common
from common import WxMsgType
import openai_wrapper
import preset

class Chatbot():
    """ 管理微信机器人逻辑. 管理与微信客户端 (如Wechat Ferry) 和 AI 客户端 (如 OpenAI )的交互逻辑 """

    def __init__(self, config: config.Config, wcfw: WcfWrapper) -> None:
        """ 初始化
        args:
            config (Config): Config对象 
            wcfw (WcfWrapper): Wechat Ferry Wrapper对象
        """
        self.wcfw = wcfw
        self.config = config
        
        # 对话预设
        self.chat_presets:dict[str, preset.Preset] = {}     # 每个对话的预设 {roomid或wxid: 预设}
       
        common.logger().info("初始化OpenAI API...")
        self.openai_wrapper = openai_wrapper.OpenAIWrapper(config, self.config.default_preset.sys_prompt)
        
    def start_main_loop(self) -> None:
        """
        主循环, 接收并处理微信消息. 
        该函数阻塞进程.
        """
        while self.wcfw.wcf.is_receiving_msg():
            try:
                msg:WxMsg = self.wcfw.get_msg()
                note = f"收到消息 {self.wcfw.msg_preview_str(msg)}"
                common.logger().info(note)
            except queue.Empty:
                continue  # 无消息，继续
            except Exception as e:
                common.logger().error("接收微信消息错误: %s", common.error_str(e))
            
            try:    
                self.run_wxmsg(msg)
            except Exception as e:
                common.logger().error("处理消息错误:%s", common.error_str(e))
 
    
    def run_wxmsg(self, msg:WxMsg):
        """ 读取并处理一条消息
        
        args:
            msg (WxMsg): 消息对象. 群号: msg.roomid, 发送者微信ID: msg.sender, 消息内容: msg.content
        """
        
        content = self._filter_wxmsg(msg)
        if not content:
            return
        
        # 确定回复对象
        if msg.from_group():
            receiver = msg.roomid
            if msg.from_self():
                at_list = ""
            else:
                at_list = msg.sender
        else:   #单聊
            receiver = msg.sender
            at_list = ""
        
        # 发送者是管理员, 并且是命令时, 处理命令并直接返回
        if self.wcfw.wxid_to_wxcode(msg.sender) in self.config.admins:
            cmd = self._match_admin_cmd(content)
            if cmd:
                try:
                    self.process_admin_cmd(content, receiver, at_list)
                except Exception as e:
                    note = f"执行管理员命令'{content}'发生错误"
                    common.logger().error("%s: %s", note, str(e))
                    self.wcfw.send_text(note, receiver, at_list)
                return
        
        ### 调用 AI 处理消息        
        # 回调函数, 处理 AI 返回消息
        def callback_msg(tp:WxMsgType, payload:str):
            return self.wcfw.send_message(tp, payload,receiver, at_list)
        
        try:
            # 根据预设加上格式
            preset = self.chat_presets.get(receiver, self.config.default_preset)
            text = preset.construct_msg(content, self.wcfw.wxid_to_wxcode(msg.sender), self.wcfw.wxid_to_nickname(msg.sender))
            
            # 获取引用消息及附件
            tp, payload = self.wcfw.get_refer_content(msg)
            files = []
            if tp==WxMsgType.text:
                text = text + f"\n引用文本:\n{payload}\n"
            elif tp == WxMsgType.link:
                text = text + f"\n网页链接:\n{payload}\n"
            elif tp in (WxMsgType.image, WxMsgType.file):
                files.append(payload)
            
            # 调用 OpenAI 运行消息 (阻塞直到全部消息处理结束)
            common.logger().info("调用AI处理:%s", text)
            self.openai_wrapper.run_msg(receiver, text, files, callback_msg)
        except Exception as e:
            note = f"对不起, 响应该消息时发生错误"
            common.logger().error(note + str(e))
            self.wcfw.send_text(note, receiver, at_list)

    
    def _filter_wxmsg(self, msg:WxMsg) -> str:
        """ 判断是否响应这条消息
        如果响应, 返回消息原文(去掉前缀)
        如果忽略, 返回None
        """
        
        # 过滤消息类型
        if msg.type == 1:           # 文本
            pass
        elif msg.type == 49:        # 引用/文件/链接？ 进一步看content type
            ct = self.wcfw.get_content_type(msg)
            if ct == 57:            # 引用
                pass
            else:
                return None
        else:
            return None
        
        # 过滤消息内容
        content = self.wcfw.get_msg_text(msg).strip()     
        if msg.from_group():    #群聊消息
            # 白名单过滤
            if "$all" in self.config.group_whitelist:
                pass
            else:
                if msg.roomid not in self.config.group_whitelist:
                    return None
            
            if msg.from_self() :        #来自自己的消息, 如果有prefix开头, 去掉prefix; 否则忽略
                for p in self.config.self_prefix:
                    if content.startswith(p):
                        content = content.removeprefix(p).strip()
                        return content
                return None

            if msg.is_at(self.wcfw.wxid):   # @我的消息, 处理
                content = re.sub(r"@.*?[\u2005|\s]", "", content).strip() #去掉@前缀, 获得消息正文
                return content
            else:   # 其他情况, 忽略
                return None
            
        else:   #单聊消息            
            # 微信号白名单
            wxcode = self.wcfw.wxid_to_wxcode(msg.sender)
            if "$all" in self.config.single_chat_whitelist:
                pass
            else:
                if wxcode in self.config.single_chat_whitelist:
                    pass
                else:
                    return None

            if msg.from_self() :        #来自自己的消息, 如果有prefix开头, 去掉prefix; 否则忽略
                for p in self.config.self_prefix:
                    if content.startswith(p):
                        content = content.removeprefix(p).strip()
                        return content
                return None
            
            # 来自对方消息:
            if not self.config.single_chat_prefix:  # 未定义前缀: 响应所有
                return content
            else:
                for p in self.config.single_chat_prefix:    # 已定义前缀: 只响应前缀开头的消息
                    if content.startswith(p):
                        return content.removeprefix(p).strip()
                    return None
                
        return None
    
    def _match_admin_cmd(self, content:str) -> Tuple[str, config.AdminCmd]:
        """ 
        判断消息是否是管理员命令
        
        args:
            content (str): 消息文本
            
        returns:
            (str, AdminCmd): (命令, 命令枚举类型) 如果不是命令返回None
        
        返回消息对应的管理员命令, 如果没有则返回None"""
        
        for k,v in self.config.admin_cmds.items():
            if content.startswith(k):
                return (k, v)
        return None
    
    def process_admin_cmd(self, content:str, receiver:str, at_list:str) -> bool:
        """ 处理管理员命令
        args:
            content (str): 命令原文
            receiver (str): 结果发送给
            at_list (str): 结果at_list
        returns:
            bool: 是否成功处理命令 
        """
        
        # 找到对应命令
        cmd_str, cmd_enum = self._match_admin_cmd(content)
        # 处理命令
        log_msg = None
        if cmd_enum is None:
            return False
        
        elif cmd_enum == AdminCmd.help:             # 显示帮助
            log_msg = self.help_msg()       
        elif cmd_enum == AdminCmd.reload_config:    # 重新加载config            
            self.config.load_config()
            self.openai_wrapper.load_config()            
            log_msg = "已完成命令:重新加载配置"            
        elif cmd_enum == AdminCmd.clear_chat:       # 清除记忆
            self.openai_wrapper.clear_chat_thread(receiver)
            log_msg = "已完成命令: 清除当前对话记忆"            
        elif cmd_enum == AdminCmd.load_preset:      # 为当前对话加载预设
            args = content.removeprefix(cmd_str).strip()   #获得命令参数
            pr = preset.read_preset(args)
            if pr:
                self.chat_presets[receiver] = pr
                self.openai_wrapper.set_chat_prompt(receiver, pr.sys_prompt)
                log_msg = f"已完成命令: 加载预设{args}"
            else:
                log_msg = f"无法加载预设{args}"
                
        elif cmd_enum == AdminCmd.reset_preset:   # 为当前对话重置预设
            self.chat_presets.pop(receiver, None)
            self.openai_wrapper.clear_chat_prompt(receiver) #删除对应的对话预设
            log_msg = "已完成重置预设"
        elif cmd_enum == AdminCmd.list_preset:  # 预设列表
            log_msg = preset.list_preset()            
        elif cmd_enum == AdminCmd.chat_id:  # 显示当前对话的id
            log_msg = f"当前对话id: {receiver}"
            
        else:           
            log_msg = f"未实现命令:{content}({cmd_enum.name})"
            
        if log_msg:
            common.logger().info(log_msg)
            self.wcfw.send_text(log_msg, receiver, at_list)
        return True
    
            
    def help_msg(self) -> str:
        """ 返回帮助信息文本 """
        msgs = []
        msgs.append("\n# 帮助信息")
        msgs.append(f"默认模型: {self.config.OPENAI['chat_model']}")
        txt = str(self.config.single_chat_prefix) if self.config.single_chat_prefix else "(无需前缀)"
        msgs.append(f"单聊触发前缀: {txt}")
        msgs.append("")
        msgs.append("## 管理员命令")
        for k,v in self.config.admin_cmds.items():
            msgs.append(f"{k} {v.description}")
        msgs.append("## 已启用工具")
        msgs.append(self.openai_wrapper.tools_help())
        text = '\n'.join(msgs)
        return text
    
# 测试
if __name__ == "__main__":
    pass