from abc import ABC, abstractmethod, abstractproperty
from typing import Callable
from wcf_wrapper import ContentType
import wcf_wrapper
from config import Config
# 继承类需要用到
import json
import common
from common import ChatMsg, MSG_CALLBACK

class ToolBase(ABC):
    """ 工具的基础接口类. 自定义工具请继承这个类并实现各抽象方法 """

    config:Config
    """ 配置对象, 来自config.yaml"""

    def __init__(self, config:Config) -> None:
        """ 初始化工具
        args:
            config (Config): 配置
        """
        super().__init__()
        self.config = config

    def validate_config(self) -> bool:
        """ 确认配置是否正确。配置不正确的工具将不会被启用
        若config.TOOLS 不包含自己的名字, 则返回False

        returns:
            bool: True=OK, False=配置错误
        """
        if self.name in self.config.TOOLS:
            return True
        else:
            return False

    @property
    @abstractproperty
    def name(self) -> str:
        """ 工具名称, 与openAI function name一致 """
        pass

    @property
    @abstractproperty
    def desc(self) -> str:
        """ 简短帮助说明 """
        pass

    @property
    @abstractproperty
    def function_json(self) -> dict:
        """ OPEN AI Function 定义, json. 参见 https://platform.openai.com/docs/assistants/tools/function-calling"""
        pass

    @abstractmethod
    def process_toolcall(self, arguments:str, callback_msg:MSG_CALLBACK) -> str:
        """ 处理Run中途的toolcall
        参考: https://platform.openai.com/docs/assistants/tools/function-calling

        Args:
            arguments (str): toolcall arguments json
            callback_msg (MSG_CALLBACK): 回调函数, 用于发送微信消息
        Returns:
            str: Toolcall 处理结果

        Raise:
            可以raise Exception, 外层会接住
        """