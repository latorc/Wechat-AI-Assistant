from config import Config
from tools.toolbase import *

class Tool_image_to_text(ToolBase):
    """
    工具: image_to_text
    调用openai 图像转文字描述
    """

    
    def __init__(self, config:Config,
        callback_openai_image_to_text:Callable) -> None:
        """_summary_

        Args:
            openai_wrapper (openai_wrapper.OpenAIWrapper): _openai_warpper对象_
        """
        
        super().__init__(config)
        self.callback_openai_image_to_text = callback_openai_image_to_text
    
    @property
    def name(self) -> str:
        return "image_to_text"
    
    @property
    def desc(self) -> str:
        return "获取图像的文字描述"
    
    @property
    def function_json(self) -> dict:
        FUNCTION_IMAGE_TO_TEXT = {
            "name": "image_to_text",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "OpenAI file id of the image file"
                    },
                    "instructions":{
                        "type": "string",
                        "description": "User's instructions or questions regarding this image"    
                    }
                },
                "required": ["file_id", "instructions"]
            },
            "description": "根据图片和用户的指示, 分析图片内容并产生文本描述. Analyze the image content based on user instructions, and generate text description."
        }
        return FUNCTION_IMAGE_TO_TEXT

    def process_toolcall(self, arguments:str, callback_msg:Callable[[WxMsgType,str],None]) -> str:
        """ 根据图片内容生成文字 """
        args = json.loads(arguments)
        fileid = args["file_id"]
        instructions = args["instructions"]
        callback_msg(WxMsgType.text, f"正在分析图片: {instructions}")
        common.logger().info("正在分析图片内容, file_id=%s, instructions=%s", fileid, instructions)
        try:
            text = self.callback_openai_image_to_text(fileid, instructions)
            return text
        except Exception as e:
            return f"分析图片内失败, 错误: {str(e)}"