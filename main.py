import logging
from argparse import ArgumentParser
import logging.config
import signal
import chatbot
import config
import wcf_wrapper
import common 

def main(cfg:str):
    the_config = config.Config(cfg)    # 初始化配置
    
    try:
        common.logger().info("正在创建WechatFerry实例...")
        wcfw = wcf_wrapper.WcfWrapper()
            
        # 在退出信号和Ctrl+C信号时，清理wcf并退出, 否则可能导致微信客户端异常
        def handler(sig, frame):
            logging.info("进行退出清理...")
            wcfw.__del__()
            exit(0)
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)    

        # 创建机器人并运行
        common.logger().info("启动微信机器人...")
        bot = chatbot.Chatbot(the_config, wcfw)
        common.logger().info("开始运行")
        bot.start_main_loop()
        
    except Exception as e:
        common.logger().fatal("程序发生错误, 即将退出: %s", common.error_trace(e))
        return
    

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('-c', type=str, default=common.DEFAULT_CONFIG, help=f'使用配置文件')
    c = parser.parse_args().c
    main(c)