import os
import pprint
import yaml
import pathlib
import logging.config
from enum import Enum, auto
import common
import preset
class AdminCmd(Enum):
    """ 微信机器人管理员命令, 与配置项目名称对应 """
    help = auto()
    reload_config = auto()
    clear_chat = auto()
    load_preset = auto()
    reset_preset = auto()
    list_preset = auto()
    chat_id = auto()
    
    @property
    def description(self):
        """ 返回命令的描述说明 """
        texts = {
            AdminCmd.help: "显示帮助信息",
            AdminCmd.reload_config: "重新载入配置文件",
            AdminCmd.clear_chat: "清除当前对话记忆",
            AdminCmd.load_preset: "预设名 为当前对话载入预设",
            AdminCmd.reset_preset: "为当前对话清除预设",
            AdminCmd.list_preset: "列出当前可用预设",
            AdminCmd.chat_id: "显示当前对话(群聊或单聊)的id"           
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
    """ 管理员命令. {命令:枚举类型} """
    
    OPENAI:dict = {}
    """ OPENAI 使用的配置项字典 """
    
    BOT:dict = {}
    """ 机器人配置选项 """
    
    TOOLS:dict[str, dict] = {}
    """ 工具插件使用的配置项字典 """
    
    def __init__(self, cfg:str) -> None:
        """ 初始化配置 
        args:
            cfg(str): yaml配置文件
        """
        self.config_file = cfg
        
        # 配置 logging
        pathlib.Path(common.LOGGING_DIR).mkdir(parents=True, exist_ok=True)    # 创建logs目录
        self.config_logging = self._load_file(common.FILE_CONFIG_LOGGING)
        logging.config.dictConfig(self.config_logging)        
        
        # 读取配置        
        self.config_dict = None
        self.load_config()

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
        
        self.admins = admin.get('admins', [])   # 管理员微信号列表
        
        # 生成字典： '管理员命令':AdminCmd        
        for c in AdminCmd:
            if c.name in admin:
                cmd = str(admin[c.name]).strip()
                self.admin_cmds[cmd] = c
    
    def load_config(self):
        """
        重新读取机器人config放到成员变量
        读取所有变量, 并设置默认值
        """
        config_dict:dict = self._load_file(self.config_file)
        self.config_dict = config_dict                
        self.OPENAI:dict = config_dict["openai"]
        self.TOOLS:dict = config_dict.get("tools",{})
        self.BOT:dict = config_dict.get('bot', {})
        
        self.group_whitelist = self.BOT.get('group_whitelist', ['$all'])
        self.single_chat_whitelist = self.BOT.get('single_chat_whitelist', ['$all'])
        self.self_prefix = self.BOT.get('self_prefix', [])
        self.single_chat_prefix = self.BOT.get('single_chat_prefix', ['$ai'])
        self.accept_friend:bool = self.BOT.get('accpet_friend', False)
        
        self.default_preset:preset.Preset = preset.get_default_preset()
                
        self._load_admin_config()
        
        
if __name__ == "__main__":
    # Test
    cfg = Config('config_template.yaml')
    cfg