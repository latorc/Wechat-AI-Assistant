""" 网页浏览器,获取网页内容"""
from urllib.parse import urljoin
import requests

from webdriver_manager.microsoft import EdgeChromiumDriverManager

from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup, NavigableString

class Browser:
    """ 网页浏览器 """

    def __init__(self, proxy: str = None) -> None:
        self.proxy = proxy
        self.driver = self.create_driver()

    def create_driver(self):
        """ 创建 Selenium Edge web drive"""
        edge_options = EdgeOptions()        # 创建Edge选项
        edge_options.add_argument("--headless")     # 启用无头模式
        edge_options.add_argument('--disable-gpu')  # 禁用GPU加速
        edge_options.add_argument('--disable-software-rasterizer')  # 禁用软件光栅化器
        edge_options.add_argument('--no-sandbox')  # 解决DevToolsActivePort文件不存在的报错
        edge_options.add_argument('--disable-dev-shm-usage')  # 解决资源有限的问题
        edge_options.add_argument('log-level=3')    # INFO = 0 WARNING = 1 LOG_ERROR = 2 LOG_FATAL = 3 default is 0
        edge_options.add_experimental_option('excludeSwitches', ['enable-automation'])  # 实现了规避监测
        edge_options.add_experimental_option('excludeSwitches', ['enable-logging'])     # 省略log
        edge_options.add_argument('--mute-audio')  # 禁用音频
        edge_options.add_argument('--disable-extensions')  # 禁用扩展
        edge_options.add_argument('--disable-popup-blocking')  # 禁用弹出窗口拦截
        edge_options.add_argument('--disable-plugins')  # 禁用插件
        if self.proxy:      # 添加代理
            edge_options.add_argument(f'--proxy-server={self.proxy}')
        # 配置浏览器设置以忽略图片
        prefs = {"profile.managed_default_content_settings.images": 2}
        edge_options.add_experimental_option("prefs", prefs)

        driver = webdriver.Edge(
            service=EdgeService(EdgeChromiumDriverManager().install()),
            options=edge_options)
        return driver

    def wait_for_page_load(self, timeout=5):
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

    def full_text(self, soup: BeautifulSoup) -> str:
        fulltext = soup.get_text(separator='\n', strip=True)
        return fulltext

    def get_image_file_size(self, img_url: str) -> int:
        """ 获取图片文件大小"""
        try:
            response = requests.head(img_url, allow_redirects=True, timeout=3)
            if 'Content-Length' in response.headers:
                return int(response.headers['Content-Length'])
        except Exception as e:
            print(f"Error fetching image size {img_url}: {e}")
        return 0

    def get_the_image(self, soup: BeautifulSoup, base_url: str) -> str:
        """ 获得网页中最大最具代表性图片 """
        # Define keywords that are usually associated with unwanted images
        unwanted_keywords = ['background', 'banner', 'ad', 'advertisement', 'footer', 'header', 'logo']

        images = soup.find_all('img')

        # 获取每张图片的实际尺寸和URL
        image_data = []
        for img in images:
            src = img.get('src')
            if not src:
                continue

            # Convert relative URL to absolute URL
            full_src = urljoin(base_url, src)

            # Filter out unwanted images based on keywords in their class or id attributes
            if any(keyword in img.get('class', []) for keyword in unwanted_keywords):
                continue
            if any(keyword in img.get('id', '') for keyword in unwanted_keywords):
                continue
            if any(keyword in full_src for keyword in unwanted_keywords):
                continue

            file_size = self.get_image_file_size(full_src)
            if file_size > 0:
                image_data.append((file_size, full_src))

        # 按文件大小排序，并获取最大的图片
        image_data.sort(reverse=True, key=lambda x: x[0])
        if image_data:
            return image_data[0][1]
        return None

    def get_headline_image(self, soup: BeautifulSoup) -> str:
        """ 获取网页meta中的头图URL"""
        meta_tags = soup.find_all('meta', property='og:image')
        if meta_tags:
            return meta_tags[0]['content']
        return None

    def webpage_content(self, url: str, get_image: bool = True) -> tuple:
        """ 访问网页，读取内容返回文本和一张图片 """
        self.driver.get(url)
        # Wait for the page to load completely
        self.wait_for_page_load()

        html_content = self.driver.page_source

        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        text = self.full_text(soup)

        image_url = None
        if get_image:
            image_url = self.get_the_image(soup, url)

        self.driver.close()
        return text, image_url



if __name__ == "__main__":
    # 使用示例测试
    browser = Browser()
    text, image_url = browser.webpage_content('https://mjcopilot.com')
    print(f"Text len = {len(text)}")
    print("Image URL:", image_url)

