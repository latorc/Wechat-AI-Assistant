from tools.toolbase import *


class Tool_text_to_speech(ToolBase):
    """ 工具: text_to_speech 文字转语音"""
    
    def __init__(self, config:Config,
        callback_openai_tts:Callable) -> None:
        """初始化
        Args:
            callback_openai_tts: openAI回调合成语音函数
        """        
        super().__init__(config)
        self.callback_openai_tts = callback_openai_tts
    
    @property
    def name(self) -> str:
        return "text_to_speech"
    
    @property
    def desc(self) -> str:
        return "用文字生成语音"
    
    @property
    def function_json(self) -> dict:
        FUNCTION_TTS = {
            "name": "text_to_speech",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "User provided text for generating the speech audio. 用户提供的文本，用于生成语音"
                    }
                },
                "required": ["text"]
            },
            "description": "Generate audio speech according to user provided text. 根据用户提供的文本生成语音. Only call this function when user wants you to speak, read out loud, or generate audio speech."
        }
        return FUNCTION_TTS
    
    def process_toolcall(self, arguments:str, callback_msg:Callable[[WxMsgType,str],None]) -> str:
        """ 调用openai TTS"""
        args = json.loads(arguments)
        text = args['text']
        callback_msg(WxMsgType.text, f"正在为您生成语音")
        common.logger().info("正在生成语音:%s", text)
        error, speech_file = self.callback_openai_tts(text)
        if error is None:
            callback_msg(WxMsgType.file, speech_file)
            note = "成功生成语音并已发送给用户"
        else:
            note = f"生成语音失败: {error}"
        
        return note