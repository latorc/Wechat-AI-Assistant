""" 微信机器人类。"""
import queue
import re
import os
import time
from typing import Tuple
from functools import partial

import cv2
from wcferry import WxMsg

from wcf_wrapper import WcfWrapper
import config
import common
from common import ContentType, ChatMsg
import openai_wrapper
import preset
from tools import toolbase
import live_tools


class Chatbot():
    """ 管理微信机器人逻辑. 管理与微信客户端 (如Wechat Ferry) 和 AI 客户端 (如 OpenAI )的交互逻辑 """

    def __init__(self, config: config.Config, wcfw: WcfWrapper, oaiw: openai_wrapper.OpenAIWrapper) -> None:
        """ 初始化
        args:
            config (Config): Config对象
            wcfw (WcfWrapper): Wechat Ferry Wrapper对象
            oaiw (OpenAIWrapper): AI Wrapper对象
        """

        self.config = config
        self.wcfw = wcfw
        self.openai_wrapper = oaiw
        self.chat_presets:dict[str, preset.Preset] = {}     # 每个对话的预设 {roomid或wxid: 预设}

        # 读取config中的对话预设
        if self.config.group_presets:
            for k,bili_rid in self.config.group_presets.items():
                res = self.set_preset(k, bili_rid)
                if res:
                    common.logger().info("加载群聊预设: %s,%s -> %s", k, self.wcfw.wxid_to_nickname(k), bili_rid)
                else:
                    common.logger().warning("无法为群聊加载预设: %s,%s -> %s", k, self.wcfw.wxid_to_nickname(k), bili_rid)

        # 直播通知工具
        self.live_tools = live_tools.LiveMonitor(self.config.live_tools, self.wcfw)



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
                time.sleep(0.001)
                continue  # 无消息，继续
            except Exception as e:
                common.logger().error("接收微信消息错误: %s", common.error_trace(e))

            try:
                self.run_wxmsg(msg)
            except Exception as e:
                common.logger().error("处理消息错误:%s", common.error_trace(e))


    def run_wxmsg(self, msg:WxMsg):
        """ 读取并处理一条消息

        args:
            msg (WxMsg): 消息对象. 群号: msg.roomid, 发送者微信ID: msg.sender, 消息内容: msg.content
        """

        content = self._filter_preprocess_wxmsg(msg)
        if content is None:
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
                    common.logger().error("执行管理员命令错误: %s",common.error_trace(e))
                    self.wcfw.send_text(f"执行管理员命令'{content}'发生错误", receiver, at_list)
                return

        # 根据预设加上格式
        preset = self.chat_presets.get(receiver, self.config.default_preset)
        text = preset.construct_msg(content, self.wcfw.wxid_to_wxcode(msg.sender), self.wcfw.wxid_to_nickname(msg.sender))

        ### 调用 AI 处理消息
        # 回调函数, 处理 AI 返回消息
        def callback_msg(msg:ChatMsg) -> int:
            return self.wcfw.send_message(msg, receiver, at_list)

        try:
            # 获取引用消息及附件
            images = []
            files = []
            refer_msg = self.wcfw.get_refer_content(msg)
            if refer_msg:  # 无引用内容
                match refer_msg.type:   # 根据引用类型处理
                    case ContentType.text:
                        # 引用文本
                        text = text + f"\n(引用文本:\n{refer_msg.content})"
                    case ContentType.link:
                        # 引用链接
                        text = text + f"\n(引用链接:\n{refer_msg.content})"
                    case ContentType.image:
                        # 图片
                        images.append(refer_msg.content)
                    case ContentType.file | ContentType.voice:
                        # 文件，语音
                        files.append(refer_msg.content)
                        # text += f"\n(语音文件: {refer_msg.content})"
                        # self.openai_wrapper.run_audio_msg(receiver, text, refer_msg.content, callback_msg)
                    case ContentType.video:
                        # 视频
                        instructions, images = self.preprocess_video(refer_msg.content)
                        text += instructions
                        # self.openai_wrapper.run_video_msg(receiver, text, refer_msg.content, callback_msg)
                    case ContentType.ERROR:
                        # 处理错误
                        self.wcfw.send_text("获取引用内容发生错误", receiver, at_list)
                        return
                    case _:
                        # 其他
                        # tp == WxMsgType.UNSUPPORTED
                        self.wcfw.send_text("抱歉, 不支持引用这类消息", receiver, at_list)
                        return

            # 调用 OpenAI 运行消息 (阻塞直到全部消息处理结束)
            self.openai_wrapper.run_msg(receiver, text, images, files, callback_msg)

        except Exception as e:
            common.logger().error("响应消息时发生错误: %s", common.error_trace(e))
            self.wcfw.send_text(f"对不起, 响应该消息时发生错误: {common.error_info(e)}", receiver, at_list)


    def _filter_preprocess_wxmsg(self, msg:WxMsg) -> str:
        """ 判断是否响应这条消息
        如果响应, 返回消息原文(去掉前缀)
        如果忽略, 返回None
        """

        # 过滤消息类型
        if msg.type == 1:           # 文本
            pass
        elif msg.type == 34:        # 语音
            pass
        elif msg.type == 49:        # 引用/文件/链接？ 进一步看content type
            ct = self.wcfw.get_content_type(msg)
            if ct == 57:            # 引用
                pass
            else:
                return None
        else:
            return None

        # return None
        def voice_msg_trans(msgid:str):
            ''' 转录语音消息，得到文字'''
            audiofile = self.wcfw.wcf.get_audio_msg(msgid, common.temp_dir())
            text = self.openai_wrapper.audio_trans(audiofile)
            common.logger().info("语音消息转录得到文字：%s", text)
            return text

        # 过滤消息内容
        text_msg = self.wcfw.get_msg_text(msg).strip()
        if msg.from_group():    #群聊消息
            # 白名单过滤
            if "$all" in self.config.group_whitelist:
                pass
            else:
                if msg.roomid not in self.config.group_whitelist:
                    return None

            # 群组语音消息
            if msg.type == 34:
                if self.config.group_voice_msg:
                    return voice_msg_trans(msg.id)
                else:
                    return None

            # 群组中来自自己的消息, 如果有prefix开头, 去掉prefix; 否则忽略
            if msg.from_self() :
                for p in self.config.self_prefix:
                    if text_msg.startswith(p):
                        text_msg = text_msg.removeprefix(p).strip()
                        return text_msg
                return None

            # @我的消息, 处理
            if self.wcfw.is_msg_at_me(msg):
                #去掉@前缀, 获得消息正文
                # 正则匹配: @开头 + 任意字符 + \u2005(1/4空格)或任意空白或结尾
                text_msg = re.sub(r"@.*?([\u2005\s]|$)", "", text_msg).strip()
                return text_msg
            else:   # 其他情况, 忽略
                return None

        else:   #单聊消息
            # 微信号白名单过滤
            wxcode = self.wcfw.wxid_to_wxcode(msg.sender)
            if "$all" in self.config.single_chat_whitelist:
                pass
            else:
                if wxcode in self.config.single_chat_whitelist:
                    pass
                else:
                    return None

            #来自自己的消息, 如果有prefix开头, 去掉prefix; 否则忽略
            if msg.from_self() :
                for p in self.config.self_prefix:
                    if text_msg.startswith(p):
                        text_msg = text_msg.removeprefix(p).strip()
                        return text_msg
                return None

            # 来自对方消息:
            if not self.config.single_chat_prefix:  # 未定义前缀: 响应所有
                if msg.type == 34:  # 语音
                    return voice_msg_trans(msg.id)
                else:
                    return text_msg
            else:
                for p in self.config.single_chat_prefix:    # 已定义前缀: 只响应前缀开头的消息

                    if text_msg.startswith(p):
                        return text_msg.removeprefix(p).strip()
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
        wx_msg = None
        if cmd_enum is None:
            return False

        elif cmd_enum == config.AdminCmd.help:             # 显示帮助
            log_msg = "显示帮助信息"
            wx_msg = self.help_msg(receiver)
        elif cmd_enum == config.AdminCmd.reload_config:    # 重新加载config
            self.config.load_config()
            self.openai_wrapper.load_config()
            log_msg = "已完成命令:重新加载配置"
            wx_msg = log_msg
        elif cmd_enum == config.AdminCmd.clear_chat:       # 清除记忆
            self.openai_wrapper.clear_chat_thread(receiver)
            log_msg = "已完成命令: 清除当前对话记忆"
            wx_msg = log_msg
        elif cmd_enum == config.AdminCmd.load_preset:      # 为当前对话加载预设
            args = content.removeprefix(cmd_str).strip()   #获得命令参数
            res = self.set_preset(receiver, args)
            if res:
                log_msg = f"已完成命令: 加载预设{args}"
            else:
                log_msg = f"无法加载预设{args}"
            wx_msg = log_msg

        elif cmd_enum == config.AdminCmd.reset_preset:   # 为当前对话重置预设
            self.chat_presets.pop(receiver, None)
            self.openai_wrapper.clear_chat_prompt(receiver) #删除对应的对话预设
            log_msg = "已完成重置预设"
            wx_msg = log_msg
        elif cmd_enum == config.AdminCmd.list_preset:  # 预设列表
            log_msg = "列出可用预设"
            wx_msg = preset.list_preset()
        elif cmd_enum == config.AdminCmd.chat_id:  # 显示当前对话的id
            log_msg = f"当前对话id: {receiver}"
            wx_msg = log_msg
        elif cmd_enum == config.AdminCmd.test_msg:  # 发送测试卡片消息
            log_msg = "发送测试卡片消息"
            self.wcfw.send_test_msg(receiver)
        else:
            log_msg = f"未实现命令:{content}({cmd_enum.name})"
            wx_msg = log_msg

        if log_msg:
            common.logger().info(log_msg)
        if wx_msg:
            self.wcfw.send_text(wx_msg, receiver, at_list)
        return True

    def set_preset(self, chatid:str, pr_name:str) -> bool:
        """ 为对话chatid设置预设pr
        args:
            chatid (str): 对话id
            pr_name (str): 预设名字
        returns:
            bool: 是否成功设置预设
        """
        pr = preset.read_preset(pr_name)
        if not pr:
            return False

        self.chat_presets[chatid] = pr
        self.openai_wrapper.set_chat_prompt(chatid, pr.sys_prompt)
        return True

    def help_msg(self, chatid:str) -> str:
        """ 返回帮助信息文本
        args:
            chatid (str): 对话id
        returns:
            str: 帮助信息文本
        """
        msgs = []
        msgs.append("\n# 帮助信息")
        msgs.append(f"默认模型: {self.config.OPENAI['chat_model']}")
        msgs.append(f"是否响应群聊语音消息: {'是' if self.config.group_voice_msg else '否'}")
        txt = str(self.config.single_chat_prefix) if self.config.single_chat_prefix else "(无需前缀)"
        msgs.append(f"单聊触发前缀: {txt}")
        pr = self.chat_presets.get(chatid, self.config.default_preset)
        msgs.append(f"当前对话使用预设: {pr.name}")
        # msgs.append("")
        msgs.append("## 管理员命令：")
        for k,v in self.config.admin_cmds.items():
            msgs.append(f"{k} {v.description}")
        msgs.append("## 已启用工具：")
        msgs.append(self.openai_wrapper.tools_help())
        text = '\n'.join(msgs)
        return text

    def preprocess_video(self, video_file:str) -> tuple[str, list]:
        """ 预处理视频文件, 返回指示文本和图片列表
        args:
            video_file (str): 视频文件路径
        returns:
            (str, list): (指示文本, 图片列表)
        """
        # extract n_frames from video
        # pylint: disable=no-member
        frames = []
        cap = cv2.VideoCapture(video_file)
        # backend = cap.getBackendName()
        # common.logger().info("backend = %s", backend)
        if not cap.isOpened():
            common.logger().warning("错误:%s", cap.get(cv2.CAP_PROP_FOURCC))
            # 获取 cap 打开文件时的错误信息

            raise RuntimeError(f"无法打开视频文件 {video_file}")

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        # 截图数量：最多每秒1张，总数限制MAX_FRAMES
        MAX_FRAMES = 8
        duration = frame_count / fps
        n_frames = min(frame_count, int(duration), MAX_FRAMES)

        # print(f"frame_count={frame_count}, fps={fps}, duration={duration:.2f}")
        for i in range(n_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i * frame_count / n_frames)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
            else:
                raise RuntimeError("Unable to read frame")
        cap.release()

        # 在video_file同一目录，把每个frame写到临时文件，命名为 video_file_0.jpg, video_file_1.jpg, ...
        image_files = []
        for i, frame in enumerate(frames):
            image_file = f"{os.path.splitext(video_file)[0]}_frame_{i}.jpg"
            cv2.imwrite(image_file, frame)
            image_files.append(image_file)

        instructions = "\n_________\n额外指示:请假装你可以查看视频,请根据附带提供的视频截图分析视频内容。" \
            f"视频的长度是{duration:.2f}秒,这里从视频中以固定时间间隔截取帧了{n_frames}帧截图。" \
            "你要假扮作你看到的是一个完整的视频。请把视频作为一个整体分析,不要提及你看到的是单帧截图。"

        return instructions, image_files

# 测试
if __name__ == "__main__":
    pass
