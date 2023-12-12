from tools.toolbase import *
from urllib.parse import urljoin
import requests

class Tool_bing_search(ToolBase):
    """ Bing搜索 """
        
    @property
    def name(self) -> str:
        return "bing_search"
    
    @property
    def desc(self) -> str:
        return "用必应搜索网络内容"
    
    @property
    def function_json(self) -> dict:
        FUNCTION_BING_SEARCH = {
            "name": "bing_search",
            "description": """Search Internet for web results using Bing Search engine. 使用必应搜索引擎, 搜索互联网上的内容.  
                当用户需要互联网上的最新内容是, 调用这个函数。
                Use this function when:
                - User is asking about current events or something that requires real-time information (weather, sports scores, etc.)
                - User is asking about some term you are totally unfamiliar with (it might be new)""",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "Query term or keywords for the search. 提交给搜索引擎的搜索关键词。"
                    }
                },
                "required": ["search_query"]
            }            
        }
        return FUNCTION_BING_SEARCH
    
    def validate_config(self) -> bool:
        """ 验证config, OK返回 True, 失败返回 False"""
        try:
            my_cfg:dict = self.config.TOOLS[self.name]
            api_key:str = my_cfg.get("api_key", None)
            if not api_key:
                return False
            return True
        except Exception as e:
            return False            
    
    def process_toolcall(self, arguments:str, callback_msg:Callable[[ContentType,str],None]) -> str:
        """ 通过Bing搜索获得结果 
        参考: https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/quickstarts/rest/python
        """
        my_config:dict = self.config.TOOLS.get(self.name, {})
        api_key:str = my_config.get("api_key", None)
        if not api_key:
            raise Exception("未提供 Bing search API key")
        endpoint:str = my_config.get("endpoint", None)
        if not endpoint:
            endpoint = "https://api.bing.microsoft.com"
        endpoint = endpoint.removesuffix(r'/') + '/v7.0/search'
        
        args = json.loads(arguments)
        query = args["search_query"]
        note = f"正在通过Bing搜索: {query}"
        callback_msg(ContentType.text, note)
        common.logger().info(note)
                
        # 组建参数
        # 参考: https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/reference/query-parameters
        params = {
                    "q": query,
                    "count": 5,
                    # "textDecorations": True,  # 是否含有字体标签等
                    "textFormat": "HTML",   
                    "mkt": 'zh-CN',
                    "freshness": "Week"
                }
        headers = { 'Ocp-Apim-Subscription-Key': api_key }

        # Call the API        
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        results = response.json()
        
        # 精简内容
        web_results = results['webPages']['value']
        keys_to_del = ['id', 'isFamilyFriendly', 'displayUrl', 'cachedPageUrl', 'language', 'isNavigational']
        for r in web_results:
            for k in keys_to_del:
                del r[k]
                
        return str(web_results)