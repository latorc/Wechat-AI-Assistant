import time

from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.edge.options import Options as EdgeOptions

from bs4 import BeautifulSoup


class Browser:
    """ 浏览网页"""
    
    def __init__(self, proxy:str=None) -> None:
        self.proxy = proxy
    
    def driver(self):
        edge_options = EdgeOptions()        # 创建Edge选项            
        edge_options.add_argument("--headless")     # 启用无头模式
        edge_options.add_argument('log-level=3')    #INFO = 0 WARNING = 1 LOG_ERROR = 2 LOG_FATAL = 3 default is 0
        edge_options.add_experimental_option('excludeSwitches', ['enable-automation'])#实现了规避监测
        edge_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        if self.proxy:      # 添加代理
            edge_options.add_argument(f'--proxy-server={self.proxy}')
        # 配置浏览器设置以忽略图片
        prefs = {"profile.managed_default_content_settings.images": 2}
        edge_options.add_experimental_option("prefs", prefs)
        
        driver = webdriver.Edge(
            service=EdgeService(EdgeChromiumDriverManager().install()),
            options=edge_options)
        return driver

    
    def webpage_text(self, url:str) -> str:
        """ 访问网页，读取文本内容返回"""
        driver = self.driver()
        driver.get(url)
        time.sleep(2)
        html_content = driver.page_source

        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text()
        driver.quit()

        return text
