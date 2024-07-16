""" Bili API 工具"""

import time
import threading
from enum import Enum, auto
from functools import reduce
from hashlib import md5
import urllib.parse

import requests

import wcf_wrapper
import common


class LiveSite(Enum):
    """直播网站"""
    BILI = auto()
    DOUYU = auto()



class BiliApi:
    """API 访问Bili"""

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36 Edg/88.0.705.63"
    mixinKeyEncTab = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
        33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
        61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
        36, 20, 34, 44, 52
    ]

    def get_mixin_key(self, orig: str):
        """对 imgKey 和 subKey 进行字符顺序打乱编码"""
        return reduce(lambda s, i: s + orig[i], self.mixinKeyEncTab, '')[:32]

    def encode_wbi(self, params: dict, img_key: str, sub_key: str):
        """为请求参数进行 wbi 签名"""
        mixin_key = self.get_mixin_key(img_key + sub_key)
        curr_time = round(time.time())
        params['wts'] = curr_time                                   # 添加 wts 字段
        params = dict(sorted(params.items()))                       # 按照 key 重排参数
        # 过滤 value 中的 "!'()*" 字符
        params = {
            k : ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
            for k, v
            in params.items()
        }
        query = urllib.parse.urlencode(params)                      # 序列化参数
        wbi_sign = md5((query + mixin_key).encode()).hexdigest()    # 计算 w_rid
        params['w_rid'] = wbi_sign
        return params

    def get_wbi_keys(self) -> tuple[str, str]:
        """获取最新的 img_key 和 sub_key"""
        headers = {
            'User-Agent': self.ua,
            'Referer': 'https://www.bilibili.com/'
        }
        resp = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=headers, timeout=5)
        resp.raise_for_status()
        json_content = resp.json()
        img_url: str = json_content['data']['wbi_img']['img_url']
        sub_url: str = json_content['data']['wbi_img']['sub_url']
        img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
        return img_key, sub_key

        # img_key, sub_key = self.get_wbi_keys()

        # # signed_params = encode_wbi(
        # #     params={
        # #         'foo': '114',
        # #         'bar': '514',
        # #         'baz': 1919810
        # #     },
        # #     img_key=img_key,
        # #     sub_key=sub_key
        # # )

        #     向原始请求参数中添加 w_rid、wts 字段

        # 将上一步得到的 w_rid 以及前面的 wts 追加到原始请求参数编码得到的 URL Query 后即可，目前看来无需对原始请求参数排序。

        # 如前例最终得到 bar=514&foo=114&zab=1919810&w_rid=8f6f2b5b3d485fe1886cec6a0be8c5d4&wts=1702204169。
    def code_query(self, base_url:str, param_dict:dict) -> str:
        """编码查询参数"""
        img_key, sub_key = self.get_wbi_keys()
        signed_params = self.encode_wbi(param_dict, img_key, sub_key)
        query = urllib.parse.urlencode(signed_params)
        return f"{base_url}?{query}"

    def get_live_data(self, room_id: str) -> dict:
        """获取直播间状态
        参考: https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/live/info.md
        """
        url = f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}"
        headers = {
            'origin': "https://live.bilibili.com",
            'referer': f"https://live.bilibili.com/{room_id}",
            'user-agent': self.ua,
            'Host': "api.live.bilibili.com"
        }

        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        json_data = response.json()
        if 'code' not in json_data:
            raise ValueError("Cannot find 'code' in return Bili API")
        if json_data['code'] != 0:
            raise ValueError(f"Bili API returns error code {json_data['message']}")
        if 'data' not in json_data:
            raise ValueError("Cannot find 'data' in return Bili API")
        return json_data['data']

    def get_user_card(self, uid:str) -> dict:
        """ 获取用户信息
        参考: https://github.com/SocialSisterYi/bilibili-API-collect/blob/8cdf355f7e963168f6237f4fd9a405f13ce036b6/docs/user/info.md#%E7%94%A8%E6%88%B7%E5%90%8D%E7%89%87%E4%BF%A1%E6%81%AF
        https://api.bilibili.com/x/web-interface/card?mid=39890273
        """
        base_url = "https://api.bilibili.com/x/web-interface/card"
        query = self.code_query(base_url, {'mid': uid})
        headers = {
            'user-agent': self.ua,
            'Host': "api.bilibili.com"
        }
        response = requests.get(query, headers=headers, timeout=5)
        response.raise_for_status()
        json_data = response.json()
        return json_data['data']['card']






class DouyuApi:
    """API 访问Douyu"""

    def __init__(self, timeout:int=5) -> None:
        self.timeout = timeout
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36 Edg/88.0.705.63"


    def get_live_data(self, room_id: str) -> dict:
        """获取直播间状态
        参考: https://github.com/nfe-w/aio-dynamic-push/blob/master/query_task/query_douyu.py
        """
        query_url = f'https://www.douyu.com/betard/{room_id}'
        headers = {
            'user-agent': self.ua,
        }
        response = requests.get(query_url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        json_data:dict = response.json()
        if not json_data:
            raise ValueError("Douyu API json_data is None")
        room_info = json_data.get('room', None)
        if room_info is None:
            raise ValueError("Douyu API 找不到直播间 room")
        return room_info


class LiveMonitor:
    """直播 监控通知"""
    def __init__(self, config_dict:dict, wcfw:wcf_wrapper.WcfWrapper):
        self.wcfw = wcfw
        self.interval = config_dict.get("check_interval", 30)

        self.bili_api = BiliApi()
        self.douyu_api = DouyuApi()

        self.monitor_dict: dict[tuple[LiveSite, str], list] = {}  #{(site, roomid): [chatids]}
        self.live_status_dict: dict[tuple[LiveSite, str], bool] = {}   #{(site, roomid): is_live}

        # 加载监视列表
        self.load_config(config_dict)

        self.monitor_thread = threading.Thread(target=self.run_monitor)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()


    def load_config(self, cfg_dict:dict):
        """ 从配置中加载监控列表 """
        douyu_list = cfg_dict.get('DOUYU',None)
        if douyu_list:
            for rid, chat_list in douyu_list.items():
                for chatid in chat_list:
                    self.add_monitor(LiveSite.DOUYU, rid, chatid)

        bili_list = cfg_dict.get('BILI',None)
        if bili_list:
            for rid, chat_list in bili_list.items():
                for chatid in chat_list:
                    self.add_monitor(LiveSite.BILI, rid, chatid)


    def add_monitor(self, site:LiveSite, roomid: str, chatid:str):
        """ 添加直播监控 """
        if (site, roomid) not in self.monitor_dict:
            self.monitor_dict[(site, roomid)] = []
        chat_list = self.monitor_dict[(site, roomid)]

        if chatid not in chat_list:
            chat_list.append(chatid)
            common.logger().info("添加直播通知: %s-%s -> %s", site.name, roomid, chatid)

    def remove_monitor(self, site:LiveSite, roomid: str, chatid:str):
        """ 移除监控 """
        if (site, roomid) in self.monitor_dict:
            chat_list = self.monitor_dict[(site, roomid)]
            if chatid in chat_list:
                chat_list.remove(chatid)


    def run_monitor(self):
        """ 持续监控 blocking"""
        common.logger().info("开始直播监控进程, 查询间隔=%d", self.interval)
        while True:
            for k, chat_list in self.monitor_dict.items():
                site, roomid = k
                try:
                    self.process_monitor(site, roomid, chat_list)
                except Exception as e:
                    common.logger().error("监控直播间 %s 出错: %s", roomid, e, exc_info=True)
            time.sleep(self.interval)

    def process_monitor(self, site:LiveSite, roomid:str, chat_list:list):
        """ 监控某个直播间，发送通知 if needed """
        name = "开播通知"
        account = ""
        title = "开播通知"
        digest = f"{site.name} {roomid} 开播啦~"
        url = "https://douyu.com"
        thumburl = "https://cdn-icons-png.freepik.com/512/8839/8839121.png"

        match site:
            case LiveSite.BILI:
                live_data = self.bili_api.get_live_data(roomid)
                user_name = self.bili_api.get_user_card(live_data['uid'])['name']
                is_live = live_data['live_status'] == 1
                title = live_data['title']
                digest = f"{user_name}-{live_data['area_name']}\n{live_data['description']}\n{live_data['tags']}"
                # url 是b站直播间地址
                url = f"https://live.bilibili.com/{roomid}"
                thumburl = live_data['user_cover']


            case LiveSite.DOUYU:
                live_data = self.douyu_api.get_live_data(roomid)
                is_live = live_data['show_status'] == 1 and live_data.get('videoLoop') == 0
                title = live_data.get('room_name')
                digest = f"{live_data.get('nickname')}-{live_data.get('second_lvl_name')}\n{live_data.get('show_details')}"
                url = f"https://douyu.com/{roomid}"
                thumburl = live_data.get('room_pic')

            case _:
                raise NotImplementedError(f"直播网站 {site}")

        old_live_status = self.live_status_dict.get((site, roomid), None)
        if is_live and is_live != old_live_status:
            # 之前没开播，现在开播了：通知
            common.logger().info("发送开播通知: %s-%s(%s) -> %s", site.name, roomid, title, chat_list)
            for chatid in chat_list:
                self.wcfw.wcf.send_rich_text(
                    name=name,
                    account=account,
                    title=title,
                    digest=digest,
                    url=url,
                    thumburl=thumburl,
                    receiver=chatid,
                )
        self.live_status_dict[(site, roomid)] = is_live


if __name__ == "__main__":
    bili_api = BiliApi()
    douyu_api = DouyuApi()


    query = bili_api.code_query("https://bbbbb.com", {'foo': '114', 'bar': '514'})
    print("Code Bili query with WTS")
    print(query)

    d = bili_api.get_live_data('25136276')
    print("Bili信息")
    print(d)

    user_card = bili_api.get_user_card('39890273')
    print("Bili user card")
    print(user_card)

    d2 = douyu_api.get_live_data('1679664')
    print("斗鱼信息")
    print(d2)

    while True:
        time.sleep(1)  # Keep the main thread alive to allow monitoring to continue
