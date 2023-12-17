import time

from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.edge.options import Options as EdgeOptions
from bs4 import BeautifulSoup, NavigableString

class Browser:
    """ 网页浏览器 """
    
    def __init__(self, proxy:str=None) -> None:
        self.proxy = proxy
        self.driver = self.create_driver()
    
    def create_driver(self):
        edge_options = EdgeOptions()        # 创建Edge选项            
        edge_options.add_argument("--headless")     # 启用无头模式
        edge_options.add_argument('log-level=3')    # INFO = 0 WARNING = 1 LOG_ERROR = 2 LOG_FATAL = 3 default is 0
        edge_options.add_experimental_option('excludeSwitches', ['enable-automation'])  # 实现了规避监测
        edge_options.add_experimental_option('excludeSwitches', ['enable-logging'])     # 省略log
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
        self.driver.get(url)
        # self.driver.execute_script(f"window.open('{url}');")
        # self.driver.switch_to.window(self.driver.window_handles[-1])        
        time.sleep(1)
        html_content = self.driver.page_source

        # 使用BeautifulSoup解析HTML        
        soup = BeautifulSoup(html_content, 'html.parser')
        text = self.full_text(soup)
        self.driver.close()
        return text
    
    def full_text(self, soup:BeautifulSoup) -> str:
        fulltext = soup.get_text(separator='\n',strip=True)
        return fulltext
    
    def distill_text(self, soup:BeautifulSoup) -> str:
        tags_to_search = ['title', 'article', 'section', 'div', 'p', 'table', 'tr', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
        tags_needed = soup.find_all(tags_to_search)
        texts = []
        for tag in tags_needed:  # True 匹配所有标签
            direct_texts = [child for child in tag.children if isinstance(child, NavigableString)]
            direct_text = ''.join(direct_texts).strip()
            if direct_text:
                texts.append(direct_text)
        text = '\n'.join(texts)
        return text

    
if __name__ == '__main__':
    browser = Browser()
    url = 'https://latorc.com:888'
    text = browser.webpage_text(url)
    text
