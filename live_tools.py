""" Bili API 工具"""
import requests
import time
import threading
from enum import Enum, auto
from typing import Callable, Dict, List

import wcf_wrapper
import common


class LiveSite(Enum):
    """直播网站"""
    BILI = auto()
    DOUYU = auto()



class BiliApi:
    """API 访问Bili"""

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36 Edg/88.0.705.63"

    def get_live_data(self, room_id: str) -> dict:
        """获取直播间状态
        参考: https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/live/info.md
        """
        url = f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}"
        headers = {
            'origin': "https://live.bilibili.com",
            'referer': f"https://live.bilibili.com/{room_id}",
            'user-agent': self.UA,
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


class DouyuApi:
    """API 访问Douyu"""

    def __init__(self, timeout:int=5) -> None:
        self.timeout = timeout
        self.UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36 Edg/88.0.705.63"


    def get_live_data(self, room_id: str) -> dict:
        """获取直播间状态
        参考: https://github.com/nfe-w/aio-dynamic-push/blob/master/query_task/query_douyu.py
        """
        query_url = f'https://www.douyu.com/betard/{room_id}'
        headers = {
            'user-agent': self.UA,
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
        name = "开播通知"
        account = ""
        title = "开播通知"
        digest = f"{site.name} {roomid} 开播啦~"
        url = "https://douyu.com"
        thumburl = "https://cdn-icons-png.freepik.com/512/8839/8839121.png"

        match site:
            case LiveSite.BILI:
                live_data = self.bili_api.get_live_data(roomid)
                is_live = live_data['live_status'] == 1
                title = live_data['title']
                digest = f"{live_data['description']}\n{live_data['tags']}\n{live_data['area_name']}"
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

    d = bili_api.get_live_data('25136276')
    print("Bili信息")
    print(d)

    d2 = douyu_api.get_live_data('1679664')
    print("斗鱼信息")
    print(d2)

    while True:
        time.sleep(1)  # Keep the main thread alive to allow monitoring to continue
