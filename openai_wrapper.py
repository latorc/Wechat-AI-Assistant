from typing import Callable, Tuple
import openai
from openai import OpenAI
import httpx
import pathlib
import base64
import time
import cv2
import common
import config
from common import ContentType, ChatMsg, MSG_CALLBACK


# 导入tools
from tools import toolbase



ASSISTANT_NAME = 'wechat_assistant'
ASSISTANT_DESC = "用于微信机器人的assistant"

class OpenAIWrapper:
    """ 用于处理OpenAI交互的类 
    参考: openai API 文档: https://platform.openai.com/docs/api-reference
    assistant api cookbook: https://cookbook.openai.com/examples/assistants_api_overview_python"""    
    
    _default_prompt:str
    """ 默认系统提示词 """
    
    def __init__(self, config:config.Config) -> None:
        """ 初始化 OpenAI API
        
        Args:
            config (dict): 从yaml读取的配置对象
            default_prompt (str): 默认提示词
        """        
        self.chat_threads = {}          # 定义每个chat对应的thread
        self.chat_promprts = {}         # 定义每个chat的预设prompt
        self.uploaded_files:dict[str,str] = {}        # 已上传文件. file_id:硬盘文件名
        
        self.config = config
        self.load_config()
    
    def load_config(self):
        """ 初始化: 
        载入config选项, 如有必要, 生成默认值
        生成 client / assistant """
        openai_config = self.config.OPENAI
        self.chat_model = openai_config["chat_model"]
        self.proxy = openai_config.get("proxy", None)
        self.api_key = openai_config['api_key']
        self.base_url = openai_config.get("base_url", None)
        
        self.image_model = openai_config.get("image_model", "dall-e-3")
        self.image_quality = openai_config.get("image_quality", "standard")
        self.image_size = openai_config.get("image_size", "1024x1024")
        
        self.voice:str = openai_config.get("voice", "alloy")
        self.voice_speed:float = openai_config.get("voice_speed", 1.0)
        self.transcript_prompt:str = openai_config.get("transcript_prompt", "请将语音消息转录成文本")
        
        self._default_prompt = self.config.default_preset.sys_prompt    # 默认prompt来自default        
        self.tools:dict[str, toolbase.ToolBase] = self._register_tools()     # 工具列表 {名字:Tool}
        self.client = self.create_openai_client()
        self.assist_id = self.get_assistant()
        
    def _register_tools(self) -> dict:
        """ 注册所有工具 """
        # 把你的Tool类对象加入这个列表, 会载入使用
        from tools import tool_image_to_text
        from tools import tool_text_to_image
        from tools import tool_browse_link
        from tools import tool_text_to_speech
        from tools import tool_bing_search
        from tools import tool_audio_transcript
        from tools import tool_video_analysis
        
        tool_list:list[toolbase.ToolBase] = [
            tool_image_to_text.Tool_image_to_text(self.config, self.image_to_text),
            tool_text_to_image.Tool_text_to_image(self.config, self.text_to_image),
            tool_text_to_speech.Tool_text_to_speech(self.config, self.tts),
            tool_browse_link.Tool_browse_link(self.config),
            tool_bing_search.Tool_bing_search(self.config),
            tool_audio_transcript.Tool_audio_transcript(self.config, self.audio_trans),
            tool_video_analysis.Tool_video_analysis(self.config, self.video_description)            
        ]
        
        tools = {}
        for t in tool_list:
            if t.validate_config(): # 检查配置, 启用通过检查的工具
                common.logger().info("启用工具 %s (%s)", t.name, t.desc)
                tools[t.name] = t
            else:
                common.logger().info("禁用工具 %s (%s)", t.name, t.desc)
        return tools
    
    def tools_help(self) -> str:
        """ 显示已启用工具的帮助信息 """
        lines = []
        for t in self.tools.values():
            lines.append(f"{t.name}({t.desc})")
        text = ', '.join(lines)
        return text
            
    def create_openai_client(self) -> OpenAI:
        """ 创建openai客户端 """

        if self.proxy:
            http_client = httpx.Client(proxies=self.proxy)
        else:
            http_client = httpx.Client()

        openai_client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=http_client,
            timeout=60            
        )
        return openai_client

    
    def get_assistant(self) -> str:
        """ 获取用于处理微信消息的assistant
        
        Returns: 
            str: assistant_id
        """
        # 首先寻找已存在同名assistant, 若不存在则创建。之后更新配置        
        id = None
        
        # 寻找名称符合的assistant
        assistants = self.client.beta.assistants.list(order='desc', limit=100)
        if assistants.data:
            for a in assistants.data:
                if a.name == ASSISTANT_NAME:
                    id = a.id
                    break
            
        if id is None:  # 未找到: 创建新的assistant            
            assistant = self.client.beta.assistants.create(model=self.chat_model)
            id = assistant.id
        
        # 更新assistant 配置
        tools = [
            {"type": "code_interpreter"},
            {"type": "retrieval"}
            ]
        for t in self.tools.values():
            tools.append({"type": "function", "function": t.function_json})
            
        assistant = self.client.beta.assistants.update(
                id,
                name=ASSISTANT_NAME,
                description=ASSISTANT_DESC,
                instructions=self._default_prompt,
                model=self.chat_model,
                tools=tools
            )        
        return assistant.id
    
    def get_thread(self, chatid:str) -> str:
        """根据chatid(wxid或roomid)获得对应的thread id
        
        Returns:
            str: thread_id        
        """
        
        if chatid not in self.chat_threads:
            thread = self.client.beta.threads.create()
            self.chat_threads[chatid] = thread.id
        
        return self.chat_threads[chatid]
    
    def set_chat_prompt(self, chatid:str, prompt:str):
        """ 为指定对话设置预设prompt"""
        self.chat_promprts[chatid] = prompt
    
    def clear_chat_prompt(self, chatid:str):
        """ 为指定对话清除 prompt"""
        self.chat_promprts.pop(chatid, None)
    
    def clear_chat_thread(self, chatid:str):
        """ 删除chat对应thread"""
        thread_id = self.chat_threads.pop(chatid, None)
        if thread_id:
            self.client.beta.threads.delete(thread_id)
        return
    
    def upload_file(self, filename:str) -> str:
        """ 上传文件到OpenAI 并返回file id. 如果失败返回None
        
        Args:
            filename (str): 文件名
            
        Returns:
            str: openai file id. 如果上传失败返回 None
        """
        fo = self.client.files.create(
            file=open(filename, "rb"),
            purpose="assistants"
        )
        self.uploaded_files[fo.id] = filename
        return fo.id
        
    def run_audio_msg(self, chatid:str, msg:str, audio_file:str,
        callback_msg:MSG_CALLBACK):
        """ 将语音消息传给 openai 处理, 发送返回的结果 """
        audio_trans = self.audio_trans(audio_file)
        msg += f"\n(语音消息:\"\n{audio_trans}\")"
        self.run_msg(chatid, msg, [], callback_msg)
    
    def run_msg(self, chatid:str, msg:str, files:list[str],
        callback_msg:MSG_CALLBACK):
        """ 将消息传给 openai 处理, 发送返回的结果消息和文件, 并响应中途的工具函数调用
        阻塞进程直到所有结果返回并处理完毕。
        
        Args:        
            chatid (str): 单聊或群聊的id, 每个id对应一个thread
            msg (str): 需要处理的消息文本
            files (list): 消息附件文件
            callback_msg (WxMsgType, str) -> int: 回调函数, 用于发送一条微信消息。(类型, 内容) -> 结果
        """      
        
        thread_id = self.get_thread(chatid)
        log_msg = f"调用Assistant处理(Thread={thread_id}): {msg}"
        if files:
            log_msg += f" (附件:{', '.join(files)})"
        common.logger().info(log_msg)
                
        # 上传文件
        file_ids = []
        for f in files:
            try:
                fid = self.upload_file(f)
                file_ids.append(fid)
            except Exception as e:
                note = "无法上传该文件到OpenAI"
                common.logger().error(note + common.error_trace(e))
                callback_msg(ChatMsg(ContentType.text, note))
                return
                
            
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
        
        try:
            # 运行run, 并处理结果, 直到停止
            while run.status in ('queued','in_progress', 'requires_action', 'cancelling'):
                if run.status == 'requires_action':     # 调用tool call
                    last_msg_id = self._process_new_msgs(thread_id, last_msg_id, callback_msg)
                    tool_outputs = []
                    
                    # 处理每个tool call, 提交结果
                    for tc in run.required_action.submit_tool_outputs.tool_calls:
                        output = self._call_tool(tc.function.name, tc.function.arguments, callback_msg)
                        tool_outputs.append({"tool_call_id": tc.id, "output":output})
                    run = self.client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread_id,
                        run_id=run.id,
                        tool_outputs=tool_outputs,
                    )
                    
                else:   # 其他运行状态: 重新pull run的状态        
                    time.sleep(0.1)
                    run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id,timeout=10)
                
            # run 运行结束(complete / failed / ...)，处理新消息
            last_msg_id = self._process_new_msgs(thread_id, last_msg_id, callback_msg)
            if run.status == 'failed':
                common.logger().warning('run id %s 运行失败:%s', run.id, str(run.last_error))
                callback_msg(ChatMsg(ContentType.text, f"API运行失败: {run.last_error.code}"))
        finally: 
            if run.status == 'requires_action': # 若中途出错退出, 需要取消运行, 避免thread被锁住
                common.logger().warning("Run状态=reuires_action, 取消运行以解锁thread")
                self.client.beta.threads.runs.cancel(run.id, thread_id=thread_id)
    

    def _process_new_msgs(self, thread_id, last_msg_id, callback_msg:MSG_CALLBACK) -> str:
        """ 处理所有在last_msg_id之后的新消息, 返回最后一条消息id"""
        msgs = self.client.beta.threads.messages.list(thread_id=thread_id, order="asc", after=last_msg_id)
        for m in msgs:
            last_msg_id = m.id                
            for c in m.content:     # 处理 message 的每个 content
                if c.type == 'text':
                    text = c.text.value
                    for a in c.text.annotations:            # 去掉所有注释
                        text = text.replace(a.text, "")     
                    text = text.replace('\n\n', '\n')       #去掉多余空行
                    callback_msg(ChatMsg(ContentType.text, text))
                elif c.type == 'image_file':
                    dl_image = self.download_openai_file(c.image_file.file_id)                      
                    callback_msg(ChatMsg(ContentType.text, dl_image))
            
            for f in m.file_ids:
                dl_file = self.download_openai_file(f)
                callback_msg(ChatMsg(ContentType.file, dl_file))
        
        return last_msg_id
    
    
    def _call_tool(self, name:str, arguments:str, callback_msg:MSG_CALLBACK) -> str:
        """ 处理工具调用, 返回结果 """
        tool = self.tools.get(name, None)
        if tool is None:
            return f"调用函数失败. 未定义函数: {name}"
       
        try:
            common.logger().info(f"调用函数{name}, 参数:{arguments}")
            result =  tool.process_toolcall(arguments, callback_msg)
        except Exception as e:
            result = f"调用函数失败. 错误: {common.error_info(e)}"
            common.logger().error("调用工具失败: %s", common.error_trace(e))
        finally: 
            # log 结果.           
            common.logger().info("提交Toolcall(%s)结果(长度=%d): %s", name, len(result), result[0:250])
            return result            
    
    def text_to_image(self, prompt:str, quality:str=None) -> str:
        """ 调用dall-e作图, 并下载图片到本地
        
        Args:
            prompt (str): 作图提示词
            quality (str): 图片质量 standard / hd
        
        Returns:
            str,str : 图片的url, 修改过的prompt
        """
        if not quality:
            quality = self.image_quality
            
        res = self.client.images.generate(
            model=self.image_model,
            prompt=prompt,
            size=self.image_size,
            quality=quality,
            n=1,
        )
        revised_prompt = res.data[0].revised_prompt
        url = res.data[0].url
        return url, revised_prompt
        

        
    def tts(self, text:str) -> str:
        """ 调用 api 生成语音并下载文件
        
        Args:
            text (str): 文本内容
            
        Returns: 
            str: 语音文件路径
        """
            
        speech_file = common.temp_file(f"tts_{common.timestamp()}.mp3")
        response = self.client.audio.speech.create(
            model="tts-1-hd",
            voice=self.voice,
            speed=self.voice_speed,
            input=text
        )
        response.stream_to_file(speech_file)
        return str(speech_file)
        
    def image_to_text(self, file_id:str, instructions:str) -> str:
        """ 从图片生成文字描述(调用 gpt4-vision) 
        Args:
            file_id (str): OpenAI的file id
            instructions (str): 用户消息
            
        Returns:
            str: 文字描述
        """
        local_file = self.uploaded_files.get(file_id, None)    # 查找本地文件
        if local_file is None:              # 没有本地文件, 从openai下载
            local_file = self.download_openai_file(file_id)
        
        with open(local_file, "rb") as image_file:    # base64编码
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        PROMPT_MESSAGES = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text":instructions},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ],
            },        
        ]
        params = {
            "model": "gpt-4-vision-preview",
            "messages": PROMPT_MESSAGES,
            "max_tokens": 1000
        }
        # 调用api
        result = self.client.chat.completions.create(**params)
        return result.choices[0].message.content
    
    def audio_trans(self, file:str) -> str:
        """ 把音频转化成文字 
        
        Args:
            file (str): 音频文件名
            
        Return:
            str: 输出文字        
        """
        with open(file, "rb") as f:
            transcript = self.client.audio.transcriptions.create(
                file = f,
                model="whisper-1",
                response_format="text",
                prompt=self.transcript_prompt,
            )
        return str(transcript).strip()
    
    
    def video_description(self, video_file:str, instructions:str) -> str:
        """ 视频的文字描述
        Args:
            video_file (str): 视频文件名
            instructions (str): 用户指示消息
        
        Returns:
            str: 视频的文字描述
        
        """
        
        frames = []

        # extract n_frames from video
        cap = cv2.VideoCapture(video_file)
        if not cap.isOpened():
            raise("Unable to open video")
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        # duration of the video n_frames = 上传截图数量
        duration = frame_count / fps
        if frame_count <= 20:
            n_frames = frame_count // 2
        elif frame_count <= 220:
            n_frames = 10 + (frame_count - 20) // 20
        else:
            n_frames = 20
        
        # print(f"frame_count={frame_count}, fps={fps}, duration={duration:.2f}")
        for i in range(n_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i * frame_count / n_frames)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
            else:
                raise("Unable to read frame")
        cap.release()
        
        # code each frame using base64
        frames_base64 = []
        for frame in frames:
            _, buffer = cv2.imencode('.jpg', frame)
            frames_base64.append(base64.b64encode(buffer).decode('utf-8'))
        content = []
        prompt = f"Attached are screenshots taken from a video. These are {n_frames} frames taken from the video at regular time intervals. The video is {duration} seconds long. Analyze the content of these images. " + instructions
        content.append({"type": "text", "text": prompt})
        for f in frames_base64:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{f}"}}) 
        
        messages = [
            {
                "role": "user",
                "content": content
            },        
        ]        
        params = {
            "model": "gpt-4-vision-preview",
            "messages": messages,
            "max_tokens": 1000
        }
        common.logger().info(f"调用gpt4-vision分析视频, prompt = {prompt}")
        result = self.client.chat.completions.create(**params)
        return result.choices[0].message.content
        
        
    
    def download_openai_file(self, file_id:str, name_override:str = None) -> str:
        """ 下载 OpenAI 文件保存到临时目录
        
        Args:
            file_id (str): OpenAI file id
            name_override (str): 指定文件名. 否则使用默认 fileid_filename
            
        Returns:
            str: 保存的本地文件名        
        """
        file_data = self.client.files.content(file_id)
        file = self.client.files.retrieve(file_id)        

        if name_override:
            save_name = common.temp_file(name_override)
        else:
            filename = pathlib.Path(file.filename).name
            save_name = common.temp_file(file.id + "_" + filename)     
        
        file_data_bytes = file_data.read()        
        with open(save_name, "wb") as file:
            file.write(file_data_bytes)
            
        return save_name
    
    
if __name__ == "__main__":
    # Test
    cfg = config.Config(common.DEFAULT_CONFIG)
    oaiw = OpenAIWrapper(cfg)
    video_file = common.temp_dir() + '/' + 'test.mp4'
    print(f"upload: {video_file}")
    # file_id = oaiw.upload_file(video_file)
    text = oaiw.video_description(video_file, "分析视频的内容。")
    print(text)