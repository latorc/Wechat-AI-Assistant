from tools.toolbase import *

class Tool_video_analysis(ToolBase):
    """ 工具:video_analysis
    分析视频内容 """
    
    def __init__(self, config: Config, callback_audio_trans:Callable) -> None:
        super().__init__(config)
        
        self.callback_video_analysis = callback_audio_trans
        
    @property
    def name(self) -> str:
        return "video_analysis"
    
    @property
    def desc(self) -> str:
        return "分析视频内容"
    
    @property
    def function_json(self) -> dict:
        FUNCTION = {
            "name": "video_analysis",
            "description": "Analyze video file content based on user instructions, and generate text description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The video file's local path on user's computer"
                    },
                    "instructions":{
                        "type": "string",
                        "description": "User's instructions or questions regarding this video"    
                    }                    
                },
                "required": ["file_path", "instructions"]
            }                
        }
        return FUNCTION
    
    def process_toolcall(self, arguments:str, callback_msg:MSG_CALLBACK) -> str:
        """ 调用 openai gpt-vision 分析视频内容"""
        args = json.loads(arguments)
        file_path = args["file_path"]
        instructions = args["instructions"]
        callback_msg(ChatMsg(ContentType.text, f"正在分析视频"))
        # common.logger().info("正在分析语音: %s", file_path)
        text = self.callback_video_analysis(file_path, instructions)
        return text