""" 主程序入口"""
import logging
import logging.config
from argparse import ArgumentParser
import signal
import os
import sys
import atexit
import ctypes

import chatbot
import config
import wcf_wrapper
import openai_wrapper
import common
from tools import toolbase

def main(cfg:str):
    """ 主程序入口"""
    the_config = config.Config(cfg)    # 初始化配置

    common.logger().info("初始化OpenAI API...")
    oaiw = openai_wrapper.OpenAIWrapper(the_config)
    tool_list = load_tools(the_config, oaiw)
    oaiw.add_tools(tool_list)

    common.logger().info("正在创建WechatFerry实例, 请登录微信...")
    wcfw = wcf_wrapper.WcfWrapper()

    # 在退出时清理
    def on_exit():
        del wcfw
        common.logger().info("完成退出清理")
    # 注册退出处理函数
    atexit.register(on_exit)

    # 设置控制台关闭事件处理程序
    def console_handler(event):
        if event == 2:  # CTRL_CLOSE_EVENT
            on_exit()
        return True
    ctypes.windll.kernel32.SetConsoleCtrlHandler(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)(console_handler), True)

    # 创建机器人并运行
    common.logger().info("启动微信机器人...")
    bot = chatbot.Chatbot(the_config, wcfw, oaiw)
    common.logger().info("开始运行并接收消息")
    bot.start_main_loop()


def load_tools(cfg:config.Config, oaiw:openai_wrapper.OpenAIWrapper) -> dict:
    """ 读取工具列表
    return (dict): 工具字典, key=工具名, value=工具对象"""
    # 把你的Tool类对象加入这个列表, 会载入使用
    from tools import tool_text_to_image
    from tools import tool_browse_link
    from tools import tool_text_to_speech
    from tools import tool_bing_search
    from tools import tool_audio_transcript
    from tools import tool_mahjong_agari

    tool_list:list[toolbase.ToolBase] = [
        tool_text_to_image.Tool_text_to_image(cfg, oaiw),
        tool_text_to_speech.Tool_text_to_speech(cfg, oaiw),
        tool_browse_link.Tool_browse_link(cfg),
        tool_bing_search.Tool_bing_search(cfg),
        tool_audio_transcript.Tool_audio_transcript(cfg, oaiw),
        tool_mahjong_agari.Tool_mahjong_agari(cfg),
    ]

    tools = {}
    for t in tool_list:
        if t.validate_config(): # 检查配置, 启用通过检查的工具
            common.logger().info("载入工具 %s (%s)", t.name, t.desc)
            tools[t.name] = t
        else:
            common.logger().info("忽略工具 %s (%s)", t.name, t.desc)
    return tools

if __name__ == "__main__":
    try:
        parser = ArgumentParser()
        parser.add_argument('-c', type=str, default=common.DEFAULT_CONFIG, help='使用的配置文件路径')
        c = parser.parse_args().c
        main(c)
    except Exception as e:
        print(f"主程序发生错误: {common.error_trace(e)}")
        common.logger().fatal("主程序发生错误, 即将退出: %s", common.error_trace(e))
        os.system("pause")

