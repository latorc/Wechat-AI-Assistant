import os
from typing import NamedTuple
import yaml
from enum import Enum, auto

import common

FILE_CONFIG_LOGGING = 'config_logging.yaml'

class AdminCmd(Enum):
    """ 微信机器人管理员命令 """
    help = auto()
    reload_config = auto()      # 重新载入程序配置文件
    clear_chat = auto()         # 清除当前对话记忆
    load_preset = auto()        # 为当前对话加载预设
    reset_preset = auto()       # 为当前对话重置预设到系统提示词
    
    @property
    def description(self):
        texts = {
            AdminCmd.help: "显示帮助信息",
            AdminCmd.reload_config: "重新载入配置文件",
            AdminCmd.clear_chat: "清除当前对话记忆",
            AdminCmd.load_preset: "预设名 为当前对话载入预设",
            AdminCmd.reset_preset: "为当前对话清除预设"           
        }
        return texts.get(self, "")


class Config(object):
    """
    Config类, 用于读取和储存config
    """
    
    single_chat_prefix:list[str]
    """ 单聊触发前缀 """
    
    group_chat_self_prefix:list[str]
    """ 群聊触发前缀 """
    
    admins:list = []
    """ 管理员微信号列表 """
    
    admin_cmds:dict[str, AdminCmd] = {}
    """ 管理员命令. 命令:枚举类型"""
    
    def __init__(self, cfg:str) -> None:
        # 分别读取 logging config 和 bot config
        self.config_file = cfg
        self.config_logging = self._load_file(FILE_CONFIG_LOGGING)
        self.config_dict = None
        self.reload_config()

    def _load_file(self, file) -> dict:
        """ 从文件读取config, 存到dict"""
        pwd = os.path.dirname(os.path.abspath(__file__))
        with open(f"{pwd}/{file}", "rb") as fp:
            yconfig = yaml.safe_load(fp)
        
        return yconfig
    
    def _load_admin_config(self):
        """ 载入管理员相关配置"""
        admin:dict = self.config_dict.get("admin",{})
        if not admin:
            return
        
        # 生成字典： '管理员命令':AdminCmd
        self.admins = admin.get('admins', [])
        for c in AdminCmd:
            if c.name in admin:
                cmd = str(admin[c.name]).strip()
                self.admin_cmds[cmd] = c        
        
    
    def reload_config(self):
        """ 重新读取机器人config放到成员变量
        Config 应该读取所有变量, 并设置默认值"""        
        
        config_dict:dict = self._load_file(self.config_file)
        self.config_dict = config_dict                
        self.OPENAI:dict = config_dict["openai"]
        
        bot = config_dict.get('bot', {})
        self.group_whitelist = bot.get('group_whitelist', ['$all'])
        self.single_chat_whitelist = bot.get('single_chat_whitelist', ['$all'])
        self.self_prefix = bot.get('self_prefix', [])
        self.single_chat_prefix = bot.get('single_chat_prefix', ['$ai'])
                
        self._load_admin_config()        
        
    def help_msg(self) -> str:
        """ 管理员命令帮助 """
        msgs = []
        msgs.append("帮助信息:")
        msgs.append(f"默认模型: {self.OPENAI['chat_model']}")
        txt = str(self.single_chat_prefix) if self.single_chat_prefix else "(无需前缀)"
        msgs.append(f"单聊触发前缀:{txt}")
        msgs.append("")
        msgs.append("管理员命令:")
        for k,v in self.admin_cmds.items():
            msgs.append(f"{k} {v.description}")
        return str.join("\n ",msgs) 