from tools.toolbase import *

class Tool_audio_transcript(ToolBase):
    """ 工具:audio_transcript
    语音识别成文本 """
    
    def __init__(self, config: Config, callback_audio_trans:Callable) -> None:
        super().__init__(config)
        
        self.callback_audio_trans = callback_audio_trans
        
    @property
    def name(self) -> str:
        return "audio_transcript"
    
    @property
    def desc(self) -> str:
        return "语音转录成文字"
    
    @property
    def function_json(self) -> dict:
        FUNCTION = {
            "name": "audio_transcript",
            "description": "Generate transcript based on audio file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "OpenAI file id of the audio file"
                    }                    
                },
                "required": ["file_id"]
            }                
        }
        return FUNCTION
    
    def process_toolcall(self, arguments:str, callback_msg:Callable[[ContentType,str],None]) -> str:
        """ 调用openai whisper 语音转录文字"""
        args = json.loads(arguments)
        fileid = args["file_id"]
        callback_msg(ContentType.text, f"正在分析语音")
        common.logger().info("正在分析语音, file_id=%s", fileid)
        text = self.callback_audio_trans(fileid)
        return text