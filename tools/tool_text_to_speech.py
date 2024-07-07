from tools.toolbase import *
from openai_wrapper import OpenAIWrapper

class Tool_text_to_speech(ToolBase):
    """ 工具: text_to_speech 文字转语音"""

    def __init__(self, config:Config, oaiw:OpenAIWrapper) -> None:
        """初始化"""
        super().__init__(config)
        self.oaiw = oaiw

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
            "description": "Generate audio speech according to user provided text, when user wants you to speak, read out loud, or generate audio speech."
        }
        return FUNCTION_TTS

    def process_toolcall(self, arguments:str, callback_msg:MSG_CALLBACK) -> str:
        """ 调用openai TTS"""
        args = json.loads(arguments)
        text = args['text']
        callback_msg(ChatMsg(ContentType.text, f"正在为您生成语音"))
        # common.logger().info("正在生成语音:%s", text)
        speech_file = self.oaiw.tts(text)
        callback_msg(ChatMsg(ContentType.file, speech_file))
        note = "成功生成语音并已发送给用户"

        return note