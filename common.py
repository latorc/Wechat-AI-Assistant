""" 常量和公共函数"""
import logging
from typing import Callable
import requests
import pathlib
import sys
import traceback
from enum import Enum
from datetime import datetime
import openai

DEFAULT_CONFIG = "config.yaml"
FILE_CONFIG_LOGGING = 'config_logging.yaml'
TEMP_DIR = 'temp'
LOGGING_DIR = 'logs'
PRESET_DIR = 'presets'
class ContentType(Enum):
    """ 表示用微信发送的消息的类型"""
    text = 1        # 文字
    image = 3       # 图片
    link = 4        # 链接
    file = 6        # 文件
    voice = 34      # 语音
    video = 43      # 视频
    ERROR = 9000    # 错误
    UNSUPPORTED = 9001  # 不支持类型

class ChatMsg:
    """ 代表某种类型的消息, 用于内部数据传递 """
    def __init__(self, type:ContentType, content:str) -> None:
        """ 初始化
        Args:
            type (ContentType): 附件类型
            content (str): 附件内容
        """
        self.type = type
        self.content = content

MSG_CALLBACK = Callable[[ChatMsg], int]     # 消息回调函数类型

def now_str() -> str:
    return str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def timestamp() -> str:
    """ 时间戳字符串: YYmmdd_HHMMDD"""
    return str(datetime.now().strftime("%Y%m%d_%H%M%S"))

def logger() -> logging.Logger:
    """ 获取全局logger """
    return logging.getLogger("wcf_gpt_bot")

def get_path(folder:str) -> pathlib.Path:
    """ 返回文件夹 Path对象. 若不存在, 创建文件夹。"""
    py_dir = pathlib.Path(__file__).resolve().parent
    temp_dir = py_dir / folder

    if not temp_dir.exists():
        temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir

def temp_file(name:str) -> str:
    """ 返回临时文件名 """
    return str((get_path(TEMP_DIR) / name).resolve())

def temp_dir() -> str:
    """ 返回临时文件夹 """
    return str(get_path(TEMP_DIR).resolve())

def download_file(url:str, filename:str, proxy:str = None) -> int:
    """ 从网址下载文件 
    
    Args:
        url (str): 网址
        filename (str): 保存的文件名, 带路径
        proxy (str): 代理服务器，例如 "http://1.2.3.4:555". 默认None不适用
    
    Returns:
        int: 0=成功, 其他数字=失败    
    """
    # 代理
    if proxy:
        proxies = {"http": proxy, "https": proxy}
    else:
        proxies = None

    try:
        response = requests.get(url, proxies=proxies)
        if response.status_code == 200:
            with open(filename, "wb") as file:
                file.write(response.content)
                return 0
        else:
            return 1
    except requests.exceptions.RequestException as e:
        return 2
    except Exception as e:
        return 3

        
def error_info(e:Exception) -> str:
    """ 返回给用户解释异常的说明文字 """
    if isinstance(e, openai.AuthenticationError):
        return "OpenAI API错误 - 认证失败"
    if isinstance(e, openai.RateLimitError):
        return "OpenAI API错误 - 速率限制"
    if isinstance(e, openai.APITimeoutError):
        return "OpenAI API错误 - 响应超时"
    else:
        return str(e)
    
def error_trace(e:Exception) -> str:
    """ 显示异常追踪信息 Log用
    
    Args:
        e (Exception): 异常
    
    Returns:
        str: 异常信息的追踪文本
    """        
    exc_type, exc_value, exc_traceback = sys.exc_info()
    trace_list = traceback.format_exception(exc_type, exc_value, exc_traceback)
    trace_text = ''.join(trace_list)
    return trace_text


if __name__ == "__main__":
    # Test
    print(timestamp())
    print(temp_dir())
    print(temp_file("temp_file.xxx"))
    pass

