""" 工具 text_to_image 画图"""
from tools.toolbase import *
from openai_wrapper import OpenAIWrapper

class Tool_text_to_image(ToolBase):
    """ 工具:text_to_image
    调用openai 作图"""

    def __init__(self, config:Config, oaiw:OpenAIWrapper) -> None:
        """初始化 """
        super().__init__(config)
        self.oaiw = oaiw

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
            "description": "Generate image or photo based on user text prompt when user explicitly requests to generate iamge or photo",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "User's text description of the desired image."
                    },
                    "quality":{
                        "type": "string",
                        "description": "The quality of the image that will be generated. hd creates images with finer details and greater consistency across the image.",
                        "enum": ["standard", "hd"]
                    }

                },
                "required": ["prompt", "quality"]
            }
        }
        return FUNCTION_TEXT_TO_IMAGE

    def process_toolcall(self, arguments:str, callback_msg:MSG_CALLBACK) -> str:
        """ 作图 """
        args = json.loads(arguments)
        prompt = args['prompt']
        quality = args['quality']
        callback_msg(ChatMsg(ContentType.text, f"正在为您生成图片({quality})"))
        # common.logger().info("调用OpenAI生成图片(%s): %s", quality, prompt)
        url, revised_prompt = self.oaiw.text_to_image(prompt, quality)

        # common.logger().info("下载图片: %s", url)
        tempfile = common.temp_file(f"openai_image_{common.timestamp()}.png")
        proxy = self.config.OPENAI.get('proxy', None)   # 使用openai proxy
        res = common.download_file(url, tempfile, proxy)
        if res == 0:    #下载成功:
            callback_msg(ChatMsg(ContentType.image, tempfile))
            return f"成功生成图片并已发送给用户。修改后的提示词: {revised_prompt}"
        else:           #下载失败
            return f"下载图片失败。图片地址:{url}, 修改后的提示词: {revised_prompt}"