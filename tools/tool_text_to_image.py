from tools.toolbase import *


class Tool_text_to_image(ToolBase):
    """ 工具:text_to_image
    调用openai 作图"""
    
    def __init__(self, config:Config,
        callback_openai_text_to_image:Callable) -> None:
        """初始化
        Args:
            callback_openai_text_to_image : 回调openai作图函数
        """        
        super().__init__(config)
        self.callback_openai_text_to_image = callback_openai_text_to_image
    
    @property
    def name(self) -> str:
        return "text_to_image"
    
    @property
    def desc(self) -> str:
        return "用文字描述生成图像"
    
    @property
    def function_json(self) -> dict:
        FUNCTION_TEXT_TO_IMAGE = {
                "name": "text_to_image",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Detailed text prompt used for generating or drawing the image or photo. 详细的文字提示词用于画或生成图片或照片"
                        }
                    },
                    "required": ["prompt"]
                },
                "description": "Draw image or photo from text prompt. 根据用户的文本提示词生成照片或图片. Only call this function when user want you to generate image or photo "
            }
        return FUNCTION_TEXT_TO_IMAGE
    
    def process_toolcall(self, arguments:str, callback_msg:Callable[[WxMsgType,str],None]) -> str:
        """ 作图 """
        args = json.loads(arguments)
        prompt = args['prompt']
        callback_msg(WxMsgType.text, f"正在为您生成图片: {prompt}")
        error, revised_prompt, tempfile = self.callback_openai_text_to_image(prompt)
        
        if error is None:  # 绘图成功: 下载并发送
                callback_msg(WxMsgType.image, tempfile)
                note = f"成功生成图片并已发送给用户。修改后的提示词: {revised_prompt}"
        else:           # 绘图错误
            note = f"失败, 发生错误: {error}"
        
        return note