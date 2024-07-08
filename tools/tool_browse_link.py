from tools.toolbase import *
import browser

class Tool_browse_link(ToolBase):
    """ 工具: browse_link
    浏览网页 返回链接内容 """


    @property
    def name(self) -> str:
        return "browse_link"

    @property
    def desc(self) -> str:
        return "访问链接获取内容"

    @property
    def function_json(self) -> dict:
        FUNCTION_BROWSE_LINK = {
            "name": "browse_link",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "User provided URL of the web page"
                    }
                },
                "required": ["url"]
            },
            "description": """Access url and retrieve web page content. 访问url并获取网页内容.
                Call this function if user explicitly asks you to access certain url and get web page content."""
        }
        return FUNCTION_BROWSE_LINK

    def process_toolcall(self, arguments:str, callback_msg:MSG_CALLBACK) -> str:
        """ 浏览网页返回文字内容 """
        args = json.loads(arguments)
        url = args['url']
        callback_msg(ChatMsg(ContentType.text, f"正在获取链接内容"))
        # common.logger().info("正在获得链接内容: %s", url)
        proxy = self.config.OPENAI.get('proxy', None)   # 使用openai proxy
        br = browser.Browser(proxy)
        text = br.webpage_text(url)
        return text
