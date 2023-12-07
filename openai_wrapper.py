from typing import Tuple
import openai
from openai import OpenAI
import httpx
import pathlib
import time
import common

ASSISTANT_NAME = 'wechat_assistant'
ASSISTANT_DESC = "用于微信机器人的assistant"
FUNCTION_IMAGE = {
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

FUNCTION_WEBPAGE = {
        "name": "browse_web_page",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the web page"
                }
            },
            "required": ["url"]
        },
        "description": "Access url and retrieve web page content. 访问url并获取网页内容. Only call this function when user wants you to access certain url and get web page content."
    }

class OpenAIWrapper:
    """ 用于处理OpenAI交互 
    参考: openai API 文档: https://platform.openai.com/docs/api-reference
    assistant api cookbook: https://cookbook.openai.com/examples/assistants_api_overview_python"""
    
    
    def __init__(self, config_openai:dict, default_prompt:str=None) -> None:
        """
        Args:
            config_openai (dict): 从yaml读取的配置字典, 包含openai api的配置
        """        
        self.sys_prompt = default_prompt
        self.chat_model = config_openai["chat_model"]
        self.proxy = config_openai.get("proxy", None)
        
        self.image_model = config_openai.get("image_model", "dall-e-3")
        self.image_quality = config_openai.get("image_quality", "standard")
        self.image_size = config_openai.get("image_size", "1024x1024")
        
        self.client = self.create_openai_client(config_openai)
        self.assist_id = self.get_assistant()
        self.chat_threads = {}          # 定义每个chat对应的thread
        self.chat_promprts = {}         # 定义每个chat的预设prompt
            
            
    def create_openai_client(self, config_openai:dict) -> OpenAI:
        """创建openai客户端"""

        if self.proxy:
            http_client = httpx.Client(proxies=self.proxy)
        else:
            http_client = httpx.Client()

        openai_client = OpenAI(
            api_key=config_openai["api_key"],
            base_url=config_openai["base_url"],
            http_client=http_client,
            timeout=60            
        )
        return openai_client
    
    def get_assistant(self) -> str:
        """ 获取用于处理微信消息的assistant
        Return: assistant_id"""
        # 首先寻找已存在同名assistant, 若不存在则创建。之后更新配置
        
        id = None
        
        # 寻找名称符合的assistant
        assistants = self.client.beta.assistants.list(order='desc', limit=100)
        for a in assistants.data:
            if a.name == ASSISTANT_NAME:
                id = a.id
                break
            
        if id is None:  # 未找到: 创建新的assistant            
            assistant = self.client.beta.assistants.create(model=self.chat_model)
            id = assistant.id
        
        # 更新assistant 配置
        assistant = self.client.beta.assistants.update(
                id,
                name=ASSISTANT_NAME,
                description=ASSISTANT_DESC,
                instructions=self.sys_prompt,
                model=self.chat_model,
                tools=[
                    {"type": "code_interpreter"},
                    {"type": "retrieval"},
                    {"type": "function", "function": FUNCTION_IMAGE},
                    {"type": "function", "function": FUNCTION_TTS},
                    {"type": "function", "function": FUNCTION_WEBPAGE},
                ]
            )
        
        return assistant.id
    
    def get_thread(self, chatid:str) -> str:
        """根据chatid(wxid或roomid)获得对应的thread
        返回 thread id"""
        
        if chatid not in self.chat_threads:
            thread = self.client.beta.threads.create()
            self.chat_threads[chatid] = thread.id
        
        return self.chat_threads[chatid]
    
    def del_thread(self, chatid:str):
        """ 删除chat对应thread"""
        thread_id = self.chat_threads.pop(chatid, None)
        if thread_id:
            self.client.beta.threads.delete(thread_id)
        return
    
    def run_msg(self, chatid:str, msg:str, files:list[str], message_callback, tool_callback):
        """ 将消息喂给openai处理, 获取结果, 并根据结果响应的callback
        Args:        
            chatid (str): 对应一个thread, 例如每个微信聊天室一个id
            msg (str): 需要处理的消息文本
            files (list): 消息附件文件
            message_callback: 回调聊天机器人, 处理一条消息
            tool_callback: 回调聊天机器人, 处理一条function tool调用
        """      
        
        thread_id = self.get_thread(chatid)
        
        # 上传文件
        file_ids = []
        for f in files:
            fo = self.client.files.create(
                file=open(f, "rb"),
                purpose="assistants"
            )
            file_ids.append(fo.id)
            
        
        # 将消息加入对应的thread
        msg = self.client.beta.threads.messages.create(
            thread_id = thread_id,
            role = "user",
            content = msg,
            file_ids= file_ids)
        last_msg_id = msg.id
        
        # create run
        chat_prompt = self.chat_promprts.get(chatid, None)        
        
        run = self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=self.assist_id,
            instructions=chat_prompt,
            timeout=30
        )
        
        # 读取并输出所有新消息
        def process_new_msgs():
            nonlocal last_msg_id 
            msgs = self.client.beta.threads.messages.list(thread_id=thread_id, order="asc", after=last_msg_id)
            for m in msgs:
                last_msg_id = m.id
                message_callback(m)
        
        try:
            # 运行run, 并处理结果, 直到停止
            while run.status in ('queued','in_progress', 'requires_action', 'cancelling'):
                if run.status == 'requires_action':     # 调用tool call
                    process_new_msgs()
                    tool_outputs = []
                    
                    # 处理每个tool call, 并且返回结果
                    for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                        output = tool_callback(tool_call)
                        tool_outputs.append({"tool_call_id": tool_call.id, "output":output})
                    run = self.client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread_id,
                        run_id=run.id,
                        tool_outputs=tool_outputs,
                    )
                    
                else:   # 其他运行状态，稍等重新pull run的状态        
                    time.sleep(0.1)
                    run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id,timeout=10)
                
            # run 运行结束(complete / failed / ...)，处理新消息
            process_new_msgs()
            if run.status == 'failed':
                # 提示运行失败... TBA
                pass
        finally:
            if run.status == 'requires_action':
                self.client.beta.threads.runs.cancel(run.id, thread_id=thread_id)
            
    
    def generate_image(self, prompt:str) -> Tuple[str, str, str]:
        """调用dall-e作图
        返回: 错误信息(成功为None), 修改过的prompt, 图片url"""
        try:
            res = self.client.images.generate(
                model=self.image_model,
                prompt=prompt,
                size=self.image_size,
                quality=self.image_quality,
                n=1,
            )
            return None, res.data[0].revised_prompt, res.data[0].url, 
        except openai.OpenAIError as e:
            return self.error_to_text(e), None, None
        except Exception as e:
            return str(e), None, None
        
    def tts(self, text:str) -> Tuple[str, str]:
        """ 调用api 产生语音
        Return: 错误信息(成功为None), 语音文件路径"""
        try:
            speech_file = common.get_path(common.TEMP_DIR) / f"tts_{common.timestamp()}.mp3" 
            response = self.client.audio.speech.create(
                model="tts-1-hd",
                voice="echo",
                input=text
            )
            response.stream_to_file(speech_file)
            return None, str(speech_file)
        except Exception as e:
            return str(e), None
            
        
    
    def download_openai_file(self, file_id:str, name_override:str = None):
        """ Download file of given id into folder"""
        file_data = self.client.files.content(file_id)
        file = self.client.files.retrieve(file_id)
        

        if name_override:
            save_name = str(common.get_path(common.TEMP_DIR) / name_override)
        else:
            filename = pathlib.Path(file.filename).name
            save_name = str(common.get_path(common.TEMP_DIR) / (file.id + "_" + filename))     
        
        file_data_bytes = file_data.read()
        
        with open(save_name, "wb") as file:
            file.write(file_data_bytes)
            
        return save_name
    
        
    def error_to_text(self, e:openai.OpenAIError) -> str:
        """ 返回 openai 错误对应的文本说明"""
        if isinstance(e, openai.RateLimitError):
            return "API错误-速率限制"
        
        else:
            return str(e)