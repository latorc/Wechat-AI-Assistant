""" presets 对话预设"""
import os
import yaml

import common

class Preset():
    """ 代表一个预设AI人格"""
    name:str
    sys_prompt:str
    msg_format:str

    def __init__(self, name:str, desc:str, sys_prompt:str, msg_format:str) -> None:
        self.name = name
        self.desc = desc
        self.sys_prompt = sys_prompt
        self.msg_format = msg_format

    def construct_msg(self, msg:str, wxcode:str, nickname:str) -> str:
        """ 根据预设格式构造发送给AI的消息"""

        # 发送给 AI 的消息格式, 用于对消息进行包装后发送. 省略则发送源消息
        # 可用变量:
        # $message=原消息, $wxcode=发送者微信号, $nickname=发送者微信昵称
        if self.msg_format is None:
            return msg

        text = self.msg_format.format(message=msg, wxcode=wxcode, nickname=nickname)
        return text

def read_preset(name:str) -> Preset:
    """ 从presets目录的yaml配置文件读取指定名称

    Args:
        name (str): 预设名称, 即不包含'.yaml'的文件名

    Returns:
        Preset: preset对象, 如果失败返回None
    """

    try:
        file = common.get_path(common.PRESET_DIR) / f"{name}.yaml"
        with open(file, "rb") as f:
            yaml_preset:dict = yaml.safe_load(f)
        desc = yaml_preset.get("desc", "")
        sys_prompt = yaml_preset.get("sys_prompt", None)
        msg_format = yaml_preset.get("msg_format", None)
        return Preset(name, desc, sys_prompt, msg_format)
    except Exception as e:
        common.logger().error('无法读取预设文件. 错误:%s', common.error_trace(e))
        return None

def list_preset() -> str:
    """ 列出可用预设 """
    text = "可用预设列表"
    for file in os.listdir(common.PRESET_DIR):
        if file.endswith(".yaml"):
            pr_name = file.removesuffix(".yaml")
            pr = read_preset(pr_name)
            if pr:
                text = text + f"\n{pr_name}: {pr.desc}"
    return text

def get_default_preset() -> Preset:
    """ 返回默认preset. 如果没有, 则返回全None Preset"""
    default_preset = read_preset('default')   # 对话默认采用预设
    if default_preset is None:
        common.logger().warn('无法读取默认预设default.yaml, 用None preset代替')
        return Preset("None", None, "你是一个AI助理", None)
    else:
        return default_preset

if __name__ == "__main__":
    # Test
    pr = read_preset('default')
    print(pr.name)
    print(pr.desc)
    print(pr.sys_prompt)
    print(pr.msg_format)