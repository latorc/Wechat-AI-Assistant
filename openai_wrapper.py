""" OpenAIWrapper 类。管理与OpenAI API 交互"""
import time
import pathlib

from openai import OpenAI
import httpx
import common
import config
from common import ContentType, ChatMsg, MSG_CALLBACK


# 导入tools
from tools import toolbase


ASSISTANT_NAME = 'Wechat_AI_Assistant'
ASSISTANT_DESC = "用于微信机器人的assistant"

class OpenAIWrapper:
    """ 用于处理OpenAI交互的类
    参考: openai API 文档: https://platform.openai.com/docs/api-reference
    assistant api cookbook: https://cookbook.openai.com/examples/assistants_api_overview_python"""

    _default_prompt:str
    """ 默认系统提示词 """

    def __init__(self, cfg:config.Config) -> None:
        """ 初始化 OpenAI API

        Args:
            config (dict): 从yaml读取的配置对象
            default_prompt (str): 默认提示词
        """
        self.chat_threads = {}          # 定义每个chat对应的thread
        self.chat_promprts = {}         # 定义每个chat的预设prompt
        self.uploaded_files:dict[str,str] = {}        # 已上传文件. file_id:硬盘文件名

        self._assistant_id:str = None
        self.tools:dict[str, toolbase.ToolBase] = {}        # 工具列表 {名字:Tool}
        self.config = cfg
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
        self.client = self.create_openai_client()

    def add_tools(self, tools:dict[str, toolbase.ToolBase]):
        """ 添加工具到工具列表 """
        self.tools = tools
        self._assistant_id = None     # 更新 assistant
        common.logger().info("为AssistantID %s 添加工具列表", self.assistant_id)

    def tools_help(self) -> str:
        """ 显示已启用工具的帮助信息 """
        lines = []
        for t in self.tools.values():
            lines.append(f"{t.name}({t.desc})")
        help_text = ', '.join(lines)
        return help_text

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

    @property
    def assistant_id(self) -> str:
        """ 获取用于处理微信消息的assistant_id

        Returns:
            str: assistant_id
        """
        if self._assistant_id is None:
            # 首先寻找已存在同名assistant, 若不存在则创建。之后更新配置
            # 寻找名称符合的assistant
            assistants = self.client.beta.assistants.list(order='desc', limit=100)
            if assistants.data:
                for a in assistants.data:
                    if a.name == ASSISTANT_NAME:
                        self._assistant_id = a.id
                        break

            if self._assistant_id is None:  # 未找到: 创建新的assistant
                assistant = self.client.beta.assistants.create(model=self.chat_model)
                self._assistant_id = assistant.id

            # 更新assistant 配置
            tools = [
                {"type": "code_interpreter"},
                {"type": "file_search"}
                ]
            for t in self.tools.values():
                tools.append({"type": "function", "function": t.function_json})

            assistant = self.client.beta.assistants.update(
                    self._assistant_id,
                    name=ASSISTANT_NAME,
                    description=ASSISTANT_DESC,
                    instructions=self._default_prompt,
                    model=self.chat_model,
                    tools=tools
                )

        return self._assistant_id

    def get_thread(self, chatid:str) -> str:
        """根据chatid(wxid或roomid)获得对应的thread id

        Returns:
            str: thread_id
        """

        if chatid not in self.chat_threads:
            thread = self.client.beta.threads.create()
            self.chat_threads[chatid] = thread.id
            common.logger().info("为新对话 %s 创建新thread %s", chatid, thread.id)

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

    def upload_file(self, filename:str, purpose:str="assistants") -> str:
        """ 上传文件到OpenAI 并返回file id. 如果失败返回None

        Args:
            filename (str): 文件名

        Returns:
            str: openai file id. 如果上传失败返回 None
        """
        fo = self.client.files.create(
            file=open(filename, "rb"),
            purpose=purpose
        )
        self.uploaded_files[fo.id] = filename
        return fo.id

    # def run_audio_msg(self, chatid:str, msg:str, audio_file:str,
    #     callback_msg:MSG_CALLBACK):
    #     """ 将语音消息传给 openai 处理, 发送返回的结果 """
    #     audio_trans = self.audio_trans(audio_file)
    #     msg += f"\n(语音消息:\"\n{audio_trans}\")"
    #     self.run_msg(chatid, msg, [], callback_msg)

    def run_msg(self, chatid:str,
        text_msg:str, images:list[str], files:list[str],
        callback_msg:MSG_CALLBACK):
        """ 将消息传给 openai 处理, 发送返回的结果消息和文件, 并响应中途的工具函数调用
        阻塞进程直到所有结果返回并处理完毕。
        GPT-4o等视觉模型可以上传"图片"类附件。其他文件作为"文件"类附件上传。

        Args:
            chatid (str): 单聊或群聊的id, 每个id对应一个thread
            text (str): 需要处理的消息文本
            images (list): 图片文件列表
            files (list): 附件文件列表
            callback_msg (WxMsgType, str) -> int: 回调函数, 用于发送一条微信消息。(类型, 内容) -> 结果
        """
        for v in (images, files):    # 用空 list 代替 None
            if v is None:
                v = []

        thread_id = self.get_thread(chatid)
        log_msg = f"调用Assistant处理(Thread={thread_id}):\n{text_msg}"
        if images:
            names = [pathlib.Path(image).name for image in images]
            log_msg += f" (图片:{', '.join(names)})"
        if files:
            names = [pathlib.Path(f).name for f in files]
            log_msg += f" (附件:{', '.join(names)})"
        common.logger().info(log_msg)

        # 上传 images
        image_files = []
        for f in images:
            fid = self.upload_file(f,"vision")
            if not fid:
                note = "上传文件到 OpenAI 时发生错误"
                common.logger().error(note)
                callback_msg(ChatMsg(ContentType.text, note))
            image_files.append(fid)

        # 上传文件
        attach_files = []
        for f in files:
            fid = self.upload_file(f)
            if not fid:
                note = "上传文件到 OpenAI 时发生错误"
                common.logger().error(note)
                callback_msg(ChatMsg(ContentType.text, note))
            attach_files.append(fid)

        # 创建附带图片的消息
        if not text_msg:
            text_msg = ""
        content = [{"type":"text", "text":text_msg}]
        for f in image_files:
            content.append({"type":"image_file", "image_file":{"file_id":f, "detail": "high"}})

        # 创建消息到 thread
        tools_object = [{"type": "code_interpreter"}, {"type":"file_search"}]
        attach_object = [{"file_id": file_id, "tools": tools_object} for file_id in attach_files]
        text_msg = self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
            attachments=attach_object
        )
        last_msg_id = text_msg.id

        # create run
        chat_prompt = self.chat_promprts.get(chatid, None)

        run = self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=self.assistant_id,
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
            common.logger().info("Run 完成。token消耗: 输入=%s, 输出=%s, 总token=%s, 估计成本=$%.4f",
                run.usage.prompt_tokens, run.usage.completion_tokens, run.usage.total_tokens,
                run.usage.prompt_tokens/1000*0.005 + run.usage.completion_tokens/1000*0.015)
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
                    msg_text = c.text.value
                    for a in c.text.annotations:            # 去掉所有注释
                        msg_text = msg_text.replace(a.text, "")
                    msg_text = msg_text.replace('\n\n', '\n')       #去掉多余空行
                    callback_msg(ChatMsg(ContentType.text, msg_text))
                elif c.type == 'image_file':
                    dl_image = self.download_openai_file(c.image_file.file_id)
                    callback_msg(ChatMsg(ContentType.image, dl_image))

            for f in m.attachments:     # 处理每个附件
                dl_file = self.download_openai_file(f)
                callback_msg(ChatMsg(ContentType.file, dl_file))

        return last_msg_id


    def _call_tool(self, name:str, arguments:str, callback_msg:MSG_CALLBACK) -> str:
        """ 处理工具调用, 返回结果 """
        tool = self.tools.get(name, None)
        if tool is None:
            return f"调用工具失败. 未定义工具: {name}"

        try:
            common.logger().info("调用工具=%s, 参数=%s:", name, arguments)
            result =  tool.process_toolcall(arguments, callback_msg)
            common.logger().info("提交Toolcall(%s)结果(长度=%d): %s", name, len(result), result[0:250])
        except Exception as e:
            result = f"调用工具失败. 错误: {common.error_info(e)}"
            common.logger().error("调用工具失败: %s", common.error_trace(e))

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