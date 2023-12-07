import httpx
import time
import json
import openai
import requests
from openai import OpenAI
from openai.types.beta.threads.thread_message import Content

SYS_PROMPT = "You are an AI assistant named Doom."
ASSISTANT_NAME = "Doom"
ASSISTANT_DESC = "You are a helpful assistant."
CHAT_MODEL = "gpt-4-1106-preview"

FUNCTION_IMAGE = {
        "name": "text_to_image",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt used for generating or drawing image or photo"
                }
            },
            "required": [
            "prompt"
            ]
        },
        "description": "根据用户文本提示画照片和图片. Draw or generate image or photo according to user text prompt"
    }
FUNCTION_VOICE = {
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
        "description": "Generate audio speech according to user provided text. 根据用户提供的文本生成语音"
    }


def create_client() -> OpenAI:
    proxy = 'http://10.0.0.32:8002'
    
    if proxy:
        http_client = httpx.Client(proxies=proxy)
    else:
        http_client = httpx.Client()

    client = OpenAI(
        api_key="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",
        http_client=http_client            
    )
    return client


def test_chat_completion(client):

    msg_list = []
    msg_list.append({"role": "system", "content": SYS_PROMPT})

    while True:
        
        line = input("You: ")
        msg_list.append({"role": "user", "content": line})   

        stream = client.chat.completions.create(
            messages=msg_list,
            model="gpt-4-1106-preview",
            stream=True
        )

        res_strings = []
        for part in stream:
            res_strings.append(part.choices[0].delta.content or "")

        response = str.join("",res_strings)
        response = response.replace("\n\n", "\n")
        msg_list.append({"role": "assistant", "content": response})
        print("GPT: " + response)


def get_assistant(client:OpenAI) -> str:
    """ 获取用于处理微信消息的assistant
    返回: assistant_id"""
    # 首先寻找已存在同名assistant, 若不存在则创建。之后更新配置
    ASSISTANT_NAME = 'Doom'
    id = None
    
    # 寻找名称符合的assistant
    assistants = client.beta.assistants.list(order='desc', limit=100)
    for a in assistants.data:
        if a.name == ASSISTANT_NAME:
            id = a.id
            break
        
    if id is None:  # 未找到创建新的assistant            
        assistant = client.beta.assistants.create(model=CHAT_MODEL)
        id = assistant.id
    
    # 更新assistant 配置
    assistant = client.beta.assistants.update(
            id,
            name=ASSISTANT_NAME,
            description=ASSISTANT_DESC,
            instructions=ASSISTANT_DESC,
            model=CHAT_MODEL,
            tools=[
                {"type": "code_interpreter"},
                {"type": "re"}
                {"type": "function", "function": FUNCTION_IMAGE}
                {}
            ]
        )
    
    return assistant.id


def test_assistant(client:OpenAI):
   
    assist_id = get_assistant(client)
    
    thread = client.beta.threads.create()
    
    # Upload the file
    file = client.files.create(
        file=open("temp/1.jpg", "rb"),
        purpose="assistants",
    )
       
    while True:
        # get user input and add this message to thread
        line = input("You: ")
        
        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=line,
            file_ids=[file.id])
        
        # create run
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assist_id
        )
        
        # wait for run to finish
        while run.status in ['queued', 'in_progress', 'requires_action']:
            if run.status == 'requires_action':
                # test cancel
                run = client.beta.threads.runs.cancel(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                # tool_outputs = []
                # for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                #     output = process_tool_call(client, tool_call)
                #     tool_outputs.append({"tool_call_id": tool_call.id, "output":output})
                
                # run = client.beta.threads.runs.submit_tool_outputs(
                #     thread_id=thread.id,
                #     run_id=run.id,
                #     tool_outputs=tool_outputs,
                # )
                
            else:
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id,
                )
                time.sleep(0.2)        
        
        messages = client.beta.threads.messages.list(thread_id=thread.id, order="asc", after=message.id)
        for m in messages:
            display_message(m)
            
            
            
def display_message(m):
    print(f"Message with Contents={len(m.content)}, files = {m.file_ids}")
    for c in m.content:
        if c.type=='image_file':
            print(f"Content({c.type}): {c.image_file}")
    
        if c.type == 'text':
            print(f"Content({c.type}): {c.text.value} (Annotations: {c.text.annotations})")

def list_messages(client:OpenAI, thread_id):
    messages = client.beta.threads.messages.list(thread_id=thread_id, order="asc")
    for m in messages:
        print(m.created_at, " ", m.content[0].text.value)
        

def process_tool_call(client:OpenAI, tool_call):
    name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)

    print("Function Name:", name)
    print("Function Arguments:", arguments)
    
    if name == 'generate_image':
        print("使用作图功能画图")
        res, revised_prompt, url = image_generation(client, arguments['prompt'])
        print("结果: ", res)
        print("修改提示词: ", revised_prompt)
        print("URL: ", url)
        return res
    
    
    
    

def image_generation(client:OpenAI, prompt:str) -> (str, str, str):
    """调用dall-e作图
    返回: 结果,修改过的prompt,图片url"""
    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            #quality="hd",
            n=1,
        )
        return "已完成，请重复给用户:'##Done'", res.data[0].revised_prompt, res.data[0].url, 
    except openai.OpenAIError as e:
        return error_to_text(e), None, None
    except Exception as e:
        return str(e), None, None

def error_to_text(e:openai.OpenAIError) -> str:
    """ 错误到str"""
    text = str(e)
    
    return text
    

def test_image(client:OpenAI):
    prompt = input("Image prompt:")
    status, revised_prompt, url = image_generation(client, prompt)
    print(status)
    print(revised_prompt)
    print(url)
    

def test_download():
    proxies = {
        "http://": "http://10.0.0.32:8002",
        "https://": "http://10.0.0.32:8002"
    }
    url = 'https://oaidalleapiprodscus.blob.core.windows.net/private/org-2QwybFmQapXWNUWIyQk6nNtU/user-TNTVxdnPlzQEWo8AHgRjZwEk/img-v6E7raame73VMMs82q4HABB4.png?st=2023-11-27T21%3A31%3A06Z&se=2023-11-27T23%3A31%3A06Z&sp=r&sv=2021-08-06&sr=b&rscd=inline&rsct=image/png&skoid=6aaadede-4fb3-4698-a8f6-684d7786b067&sktid=a48cca56-e6da-484e-a814-9c849652bcb3&skt=2023-11-27T09%3A40%3A21Z&ske=2023-11-28T09%3A40%3A21Z&sks=b&skv=2021-08-06&sig=FhxDiGNiadNuF8k8iBR59M4l%2BG9TbfeKKiTuJEikkk4%3D'
    tempfile = "downloaded_image.png"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

    response = requests.get(url)
    if response.status_code == 200:
        with open(tempfile, "wb") as file:
            file.write(response.content)
        return tempfile 

if __name__ == "__main__":
    client = create_client()
    test_assistant(client)