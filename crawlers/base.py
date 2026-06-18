"""爬虫基类 —— 提供 Selenium 驱动管理、通用请求工具"""
import time
import random
import config
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service


CHROMEDRIVER_PATH = "/Users/qianxuyang/PycharmProjects/pythonProject1/chromedriver"


class BaseCrawler:
    """平台爬虫基类"""

    def __init__(self, source: str):
        self.source = source
        self._driver = None

    # ---------- Selenium 驱动 ----------

    def get_driver(self) -> webdriver.Chrome:
        """获取/创建 Chrome 浏览器实例"""
        if self._driver is not None:
            return self._driver
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument(f"user-agent={random.choice(config.USER_AGENTS)}")
        opts.add_argument("--window-size=1920,1080")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        service = Service(executable_path=CHROMEDRIVER_PATH)
        self._driver = webdriver.Chrome(service=service, options=opts)
        self._driver.set_page_load_timeout(config.SELENIUM_TIMEOUT)
        return self._driver

    def close_driver(self):
        """关闭浏览器"""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def safe_get(self, url: str) -> bool:
        """安全打开页面，返回是否成功"""
        driver = self.get_driver()
        try:
            driver.get(url)
            time.sleep(config.PAGE_LOAD_DELAY)
            return True
        except TimeoutException:
            print(f"  [WARN] 页面加载超时: {url}")
            return False
        except WebDriverException as e:
            print(f"  [WARN] 页面加载失败: {e}")
            return False

    def wait_element(self, by, value, timeout=10):
        """等待元素出现"""
        try:
            return WebDriverWait(self._driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except TimeoutException:
            return None

    def wait_elements(self, by, value, timeout=10):
        """等待多个元素出现"""
        try:
            return WebDriverWait(self._driver, timeout).until(
                EC.presence_of_all_elements_located((by, value))
            )
        except TimeoutException:
            return []

    # ---------- 通用工具 ----------

    def delay(self, base: float = None):
        """随机延迟避免被反爬"""
        sec = base or config.BETWEEN_BOOK_DELAY
        time.sleep(sec * random.uniform(0.8, 1.5))

    # ---------- 子类需实现的接口 ----------

    def crawl_rankings(self) -> list:
        """
        爬取新书榜所有分类前20，返回榜单数据列表
        每条数据格式：
        {
            "book_id": str, "rank": str, "title": str, "author": str,
            "book_url": str, "description": str, "status": str,
            "reader_count": str, "category_label": str, "cover_url": str,
            "source": str
        }
        """
        raise NotImplementedError

    def crawl_book_info(self, book_url: str) -> dict:
        """
        爬取书籍详情
        返回：
        {
            "book_id": str, "title": str, "author": str, "intro": str,
            "category": str, "word_count": int, "status": str,
            "total_chapters": int, "cover_url": str, "book_url": str
        }
        """
        raise NotImplementedError

    def crawl_chapter_list(self, book_url: str) -> list:
        """
        爬取书籍章节列表
        返回 [(chapter_index, chapter_title, chapter_url), ...]
        """
        raise NotImplementedError

    def crawl_chapter_content(self, chapter_url: str) -> str:
        """爬取单个章节正文内容"""
        raise NotImplementedError
