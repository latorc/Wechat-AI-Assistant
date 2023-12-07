import pathlib
import yaml

class Preset():
    """ 代表一个预设AI人格"""
    name:str
    sys_prompt:str
    msg_format:str
    
    def __init__(self, name:str, sys_prompt:str, msg_format:str) -> None:
        self.name = name
        self.sys_prompt = sys_prompt
        self.msg_format = msg_format

    def construct_msg(self, msg:str, wxcode:str, nickname:str):
        """ 根据预设格式构造发送给AI的消息"""
        # 发送给 AI 的消息格式, 用于对消息进行包装后发送. 省略则发送源消息
        # 可用变量:
        # $message=原消息, $wxcode=发送者微信号, $nickname=发送者微信昵称
        if self.msg_format is None:
            return msg
        
        text = self.msg_format.format(message=msg, wxcode=wxcode, nickname=nickname)
        return text       
        

            
            
def read_preset(name:str) -> Preset:
    """ 读取指定名称preset from yaml file
    Args:
        name (str): 预设名称, 即yaml文件主名
    Returns:
        Preset: preset对象, 如果失败返回None"""
    try:
        file = pathlib.Path('presets') / f"{name}.yaml"
        with open(file, "rb") as f:
            yaml_preset:dict = yaml.safe_load(f)
        sys_prompt = yaml_preset.get("sys_prompt", None)
        msg_format = yaml_preset.get("msg_format", None)
        return Preset(name, sys_prompt, msg_format)
    except Exception as e:
        return None