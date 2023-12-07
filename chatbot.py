import queue
import re
import json
from typing import NamedTuple, Tuple
import xml.etree.ElementTree as ET
import requests
import pathlib
import yaml
from openai.types.beta.threads.thread_message import ThreadMessage
from openai.types.beta.threads.required_action_function_tool_call import RequiredActionFunctionToolCall
from wcf_wrapper import WcfWrapper, WxMsgType
from wcferry import WxMsg
import config
from config import AdminCmd
import common
import openai_wrapper
import browser
import preset


class Chatbot():
    """ 管理微信机器人逻辑. 管理与微信客户端 (如Wechat Ferry) 和 AI 客户端 (如 OpenAI )的互动"""

    def __init__(self, config: config.Config, wcfw: WcfWrapper) -> None:
        self.wcfw = wcfw
        self.config = config
        self.presets:dict[str, preset.Preset] = {}
        self.default_preset:preset.Preset = preset.read_preset('default')
        if self.default_preset is None:
            common.logger().warn('无法读取默认预设default.yaml')
            default_prompt = None
        else:
            default_prompt = self.default_preset.sys_prompt        
        
        common.logger().info("初始化OpenAI API...")        
        self.openai_wrapper = openai_wrapper.OpenAIWrapper(config.OPENAI, default_prompt)
        self.browser = browser.Browser(self.openai_wrapper.proxy)        

        
    def start_main_loop(self) -> None:
        """
        主循环, 接收并处理消息. 
        该函数阻塞进程.
        """
        while self.wcfw.wcf.is_receiving_msg():
            try:
                msg:WxMsg = self.wcfw.get_msg()
                note = f"收到消息: {self.wcfw.msg_preview_str(msg)}"
                common.logger().info(note)
            except queue.Empty:
                continue  # 无消息，继续
            except Exception as e:
                common.logger().error("接收微信消息错误: %s", str(e))
            
            try:    
                self.run_wxmsg(msg)
            except Exception as e:
                common.logger().error("处理消息错误:%s", str(e))
 
    
    def run_wxmsg(self, msg:WxMsg):
        """ 读取并处理一条消息
        群号: msg.roomid  微信ID: msg.sender  消息内容: msg.content
        """
        
        content = self.filter_wxmsg(msg)
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
            if cmd:     # 处理完命令后直接返回
                try:
                    self.process_admin_cmd(content, receiver, at_list)
                except Exception as e:
                    msg = f"执行管理员命令'{content}'发生错误"
                    common.logger().error("%s: %s", msg, str(e))
                    self.wcfw.send_text(msg, receiver, at_list)
                return          
        
        ### 调用 AI 处理消息        
        # 回调函数, 处理 AI 返回消息和工具调用
        def callback_msg(openai_msg:ThreadMessage):
            self.display_ai_msg(openai_msg, receiver, at_list)

        def callback_tool(toolcall:RequiredActionFunctionToolCall) -> str:
            return self.process_ai_toolcall(toolcall, receiver, at_list)
        
        try:
            # 根据预设加上格式
            preset = self.presets.get(receiver, self.default_preset)
            if preset:
                text = preset.construct_msg(content, self.wcfw.wxid_to_wxcode(msg.sender), self.wcfw.wxid_to_nickname(msg.sender))
            else:
                text = content
            
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
            common.logger().info("调用OpenAI处理消息:%s", text)
            self.openai_wrapper.run_msg(receiver, text, files, callback_msg, callback_tool)
        except Exception as e:
            note = f"对不起, 响应该消息时发生错误"
            common.logger().error(note + str(e))
            self.wcfw.send_text(note, receiver, at_list)
        
        return  #
    
    def filter_wxmsg(self, msg:WxMsg) -> str:
        """ 是否响应这条消息
        如果响应, 返回消息原文(去掉前缀)
        如果忽略, 返回None """
        
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
            
            # 来自对方消息: 只响应前缀开头的
            if not self.config.single_chat_prefix:
                return content
            else:
                for p in self.config.single_chat_prefix:
                    if content.startswith(p):
                        return content.removeprefix(p).strip()
                    return None
                
        return None
    
    def _match_admin_cmd(self, content:str) -> Tuple[str, config.AdminCmd]:
        """ 返回消息对应的管理员命令, 如果没有则返回None"""
        for k,v in self.config.admin_cmds.items():
            if content.startswith(k):
                return (k, v)
        return None
    
    def process_admin_cmd(self, content:str, receiver:str, at_list:str):
        """ 处理管理命令"""
        
        # 找到对应命令
        cmd_str, cmd_enum = self._match_admin_cmd(content)        
        
        # 处理命令
        log_msg = None
        if cmd_enum is None:
            return False
        
        elif cmd_enum == AdminCmd.help:
            msg = self.config.help_msg()
            log_msg = msg
        
        elif cmd_enum == AdminCmd.reload_config:    # 重新加载config            
            self.config.reload_config()
            log_msg = "已完成命令:重新加载配置"
            
        elif cmd_enum == AdminCmd.clear_chat:     # 清除记忆
            self.openai_wrapper.del_thread(receiver)
            log_msg = "已完成命令: 清除当前对话记忆"
            
        elif cmd_enum == AdminCmd.load_preset:    # 为当前对话加载预设
            args = content.removeprefix(cmd_str).strip()   #获得命令参数
            # prompt = self.config.presets.get(args, None)
            pr = preset.read_preset(args)
            if pr:
                self.presets[receiver] = pr
                self.openai_wrapper.chat_promprts[receiver] = pr.sys_prompt
                log_msg = f"已完成命令: 加载预设{args}"
            else:
                log_msg = f"无法完成命令: 加载预设{args}"
                
        elif cmd_enum == AdminCmd.reset_preset:   # 为当前对话重置预设
            self.presets.pop(receiver, None)
            self.openai_wrapper.chat_promprts.pop(receiver, None)    #删除对应的对话预设
            log_msg = "已完成重置预设"
            
        else:           
            log_msg = f"未实现命令:{content}({cmd_enum.name})"
            
        if log_msg:
            common.logger().info(log_msg)
            self.wcfw.send_text(log_msg, receiver, at_list)
        return True

    def display_ai_msg(self, message:ThreadMessage, receiver, at_list):
        """ 显示AI返回的消息 """
        for c in message.content:
            if c.type == 'text':
                text = c.text.value    
                # for a in c.text.annotations:
                #     # Gather citations based on annotation attributes
                #     if (file_citation := getattr(a, 'file_citation', None)):
                #         cited_file = self.openai_wrapper.client.files.retrieve(file_citation.file_id)
                #         file_citation.quote
                #         cited_file.filename
                #     elif (file_path := getattr(annotation, 'file_path', None)):
                #         cited_file = client.files.retrieve(file_path.file_id)
                #         citations.append(f'[{index}] Click <here> to download {cited_file.filename}')
                #         # Note: File download functionality not implemented above for brevity
                text = text.replace('\n\n', '\n')       #去掉多余空行
                self.wcfw.send_text(text, receiver, at_list)
            elif c.type == 'image_file':
                dl_image = self.openai_wrapper.download_openai_file(c.image_file.file_id)
                      
                self.wcfw.send_image(dl_image,receiver)
        
        for f in message.file_ids:
            dl_file = self.openai_wrapper.download_openai_file(f)
            self.wcfw.wcf.send_file(dl_file, receiver)
        
    
    def process_ai_toolcall(self, tool_call:RequiredActionFunctionToolCall, receiver, at_list) -> str:
        """ 处理AI提出的工具调用"""
        name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        
        try:
            if name == 'text_to_image':        # 画图
                result = self.toolcall_generate_image(arguments, receiver, at_list)        
            elif name == 'text_to_speech':      # TTS语音
                result = self.toolcall_tts(arguments, receiver, at_list)
            elif name == 'browse_web_page':      # 获取网页内容
                result = self.toolcall_webpage(arguments, receiver, at_list)
            else:
                result = f"调用函数失败. 未定义函数: {name}"
        
        except Exception as e:
            result = f"调用函数失败. 错误: {str(e)}"
        finally: 
            # log 结果. 
            if len(result) > 150:
                log_text = result[0:150] + f"...(str长度={len(result)})"
            else:
                log_text = result                
            common.logger().info(log_text)
            
            # 返回结果 (给openai)
            return result
    
    
    def toolcall_generate_image(self, arguments, receiver, at_list) -> str:
        """ 调用绘画工具
        可以在开始运行时提示用户
        结束时不用通知用户
        返回文字结果"""
        
        prompt = arguments['prompt']
        self.wcfw.send_text(f"正在为您生成图片: {prompt}", receiver, at_list)
        error, revised_prompt, url = self.openai_wrapper.generate_image(prompt)
        
        if error is None: 
            # 绘图成功, 下载并发送
            tempfile = str(common.get_path(common.TEMP_DIR) / f"openai_image_{common.timestamp()}.png")
            res = common.download_file(url, tempfile, self.openai_wrapper.proxy)
            if res == 0:    #下载成功
                common.logger().info("发送图片: %s", url)
                self.wcfw.send_image(tempfile, receiver)
                note = "成功生成图片并发送给用户"
            else:           #下载失败
                note = f"成功生成图片, 但下载图片失败, 请让用户尝试自行下载: {url} "
        
        else:           # 有错误
            note = f"生成图片失败: {error}"
        
        return note

    def toolcall_tts(self, arguments, receiver, at_list) -> str:
        """ 调用语音TTS工具
        Return: 运行结果"""
        text = arguments['text']
        self.wcfw.send_text(f"正在为您生成语音", receiver, at_list)
        common.logger().info("正在生成语音:%s", text)
        error, speech_file = self.openai_wrapper.tts(text)
        if error is None:
            common.logger().info("发送语音文件: %s", speech_file)
            self.wcfw.wcf.send_file(speech_file, receiver)
            note = "成功生成语音并发送给用户"
        else:
            note = f"生成语音失败: {error}"
        
        return note    
    
    def toolcall_webpage(self, arguments, receiver, at_list) -> str:
        """ 工具 网页内容
        Return: 运行结果"""
        url = arguments['url']
        self.wcfw.send_text(f"正在获取网页内容", receiver, at_list)
        common.logger().info("正在获得网页内容: %s", url)
        try:
            text = self.browser.webpage_text(url)
            return text
        except Exception as e:
            return f"获取网页内容失败! Error: {str(e)}"
    
    
# 测试
if __name__ == "__main__":
    pass