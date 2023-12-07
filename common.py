""" 常量和公共函数"""
import logging
from typing import Tuple
import requests
import pathlib
from enum import Enum, auto
from datetime import datetime

from bs4 import BeautifulSoup


TEMP_DIR = 'temp'
LOG_DIR = 'log'


def now_str() -> str:
    return str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def timestamp() -> str:
    return str(datetime.now().strftime("%Y%m%d_%H%M%S"))


class CompletionType(Enum):
    """ assistant 运行返回的结果类型"""
    MESSAGE = auto()        # 文本消息
    TOOL_CALL = auto()      # 工具调用
    FAILED = auto()         # 运行失败
    EXCEPTION = auto()      # 发生异常
    UNDEFINED = auto()      # 其他未定义





def logger() -> logging.Logger:
    return logging.getLogger("wcf_gpt_bot")

def get_path(folder:str) -> pathlib.Path:
    """ 返回文件夹 Path, create if not exist"""
    py_dir = pathlib.Path(__file__).resolve().parent
    temp_dir = py_dir / folder

    if not temp_dir.exists():
        temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir

def download_file(url:str, filename:str, proxy:str = None) -> int:
    """ 下载文件, 返回文件名. 下载失败则返回 None 
    
    Args:
        url (str): 网址
        filename (str): 保存的文件名, 带路径
        proxy (str): 代理服务器，例如 "http://1.2.3.4:555"        
    Returns:
        int: 0=成功, 其他数字=失败
    
    """
    # 代理
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy,
        }
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
    
def web_page_text(url:str, proxy:str = None) -> Tuple[int, str]:
    """ 返回网页内容原文
    Args:
        url (str): 网址
        proxy (str): 代理服务器，例如 "http://1.2.3.4:555" 
    Return (int, str): status code, 网页文本
    """
    # 代理
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy,
        }
    else:
        proxies = None
    
    response = requests.get(url, proxies=proxies)
    code = response.status_code
    if  code == 200:
        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        text = soup.get_text()            
        return code, text
    else:
        return code, None
    
if __name__ == "__main__":
    # t = temp_dir()
    # print(t)
    pass