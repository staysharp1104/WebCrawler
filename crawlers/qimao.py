"""七猫小说爬虫 (qimao) — 基于 API + SSR NUXT 数据"""
import re
import json
import subprocess
import requests
from bs4 import BeautifulSoup
import config
from crawlers.base import BaseCrawler

QIMAO_DOMAIN = "https://www.qimao.com"

QIMAO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": QIMAO_DOMAIN,
}

# ------------------------------------------------------------
# 榜单类别
# ------------------------------------------------------------
CHANNEL_TYPES = [
    ("boy", "男生"),
    ("girl", "女生"),
]

RANK_TYPES = [
    ("hot", "大热榜"),
    ("new", "新书榜"),
    ("over", "完结榜"),
    ("collect", "收藏榜"),
    ("update", "更新榜"),
]


class QimaoCrawler(BaseCrawler):
    """七猫小说爬虫 — 基于 API + SSR NUXT 数据"""

    COVER_URL_TPL = "https://cdn.qimao.com/bookimg/zww/upload/readerCover/68/{}_360x480.jpg"

    def __init__(self):
        super().__init__("qimao")
        self.session = requests.Session()
        self.session.headers.update(QIMAO_HEADERS)

    # ------------------------------------------------------------
    # SSR 工具：解析 __NUXT__ 函数包装格式
    # ------------------------------------------------------------

    @staticmethod
    def _extract_nuxt(html: str) -> dict:
        """
        从 HTML 中提取并解析 __NUXT__ 数据。

        七猫使用 Nuxt.js SSR，数据以函数包装格式注入：
          window.__NUXT__=(function(a,b,c,...){return {...}})(val1,val2,...)

        使用 Node.js 直接执行该 JavaScript 表达式得到纯 JSON。
        """
        m = re.search(
            r'window\.__NUXT__\s*=\s*(.*?)</script>', html, re.DOTALL
        )
        if not m:
            return {}
        raw = m.group(1).strip().rstrip("; \n\r\t")

        # 用 Node.js 解析函数包装
        js_code = f"var result = {raw}; console.log(JSON.stringify(result));"
        try:
            proc = subprocess.run(
                ["node", "-e", js_code],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                return json.loads(proc.stdout.strip())
        except Exception:
            pass
        return {}

    # ------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------

    @staticmethod
    def _make_cover_url(original_book_id: str) -> str:
        """构造封面图片 URL"""
        return QimaoCrawler.COVER_URL_TPL.format(original_book_id)

    @staticmethod
    def _extract_book_id(book_url: str) -> str:
        """从 book_url 中提取 book_id"""
        m = re.search(r"/shuku/(\d+)", book_url)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_chapter_ids(chapter_url: str) -> tuple:
        """
        从 chapter_url 中提取 (book_id, chapter_id)
        URL 格式: https://www.qimao.com/shuku/{book_id}-{chapter_id}/
        """
        m = re.search(r"/shuku/(\d+)-(\d+)", chapter_url)
        if m:
            return m.group(1), m.group(2)
        return "", ""

    @staticmethod
    def _clean_content(text: str) -> str:
        """清洗章节正文 HTML -> 纯文本"""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.replace("\u3000", "")
        return text.strip()

    # ------------------------------------------------------------
    # 榜单爬取
    # ------------------------------------------------------------

    def crawl_rankings(self) -> list:
        """
        爬取七猫排行榜全部类别。

        七猫榜单为 SSR 页面，数据在 __NUXT__ 的
        fetch["data-v-cca2d2e4:0"].listData 中。
        支持 channelType: boy/girl, rankType: hot/new/over/collect/update。
        """
        results: list = []

        for ch_type, ch_label in CHANNEL_TYPES:
            for rank_type, rank_label in RANK_TYPES:
                url = (
                    f"{QIMAO_DOMAIN}/paihang"
                    f"?channelType={ch_type}&rankType={rank_type}"
                )
                print(f"  [qimao] 爬取 {ch_label}/{rank_label}...")
                try:
                    resp = self.session.get(
                        url, timeout=config.REQUEST_TIMEOUT
                    )
                    data = self._extract_nuxt(resp.text)
                    if not data:
                        print(f"  [qimao] {ch_label}/{rank_label} NUXT 为空")
                        continue

                    # 从 fetch 中找到 listData
                    fetch = data.get("fetch", {})
                    list_data = None
                    for _key, val in fetch.items():
                        if isinstance(val, dict) and "listData" in val:
                            list_data = val["listData"]
                            break
                    if not list_data:
                        print(
                            f"  [qimao] {ch_label}/{rank_label} 无 listData"
                        )
                        continue

                    for bk in list_data[: config.RANK_PAGE_SIZE]:
                        bid = str(bk.get("book_id", ""))
                        if not bid:
                            continue

                        # 判断作品状态
                        is_over = bk.get("is_over", "0")
                        status = "完结" if is_over == "1" else "连载"

                        # 分类标签
                        cat1 = bk.get("category1_name", "")
                        cat2 = bk.get("category2_name", "")
                        category_label = f"{ch_label}"
                        if cat1:
                            category_label = f"{cat1}"
                        if cat2:
                            category_label = f"{cat1}/{cat2}"
                        category_label = f"{category_label}/{rank_label}"

                        # 封面
                        cover = bk.get("image_link", "")
                        if not cover:
                            orig_id = bk.get("original_book_id", "")
                            if orig_id:
                                cover = self._make_cover_url(orig_id)

                        results.append({
                            "book_id": f"qimao_{bid}",
                            "rank": str(len(results) + 1),
                            "title": bk.get("title", "").strip(),
                            "author": bk.get("author", ""),
                            "book_url": bk.get(
                                "book_url",
                                f"{QIMAO_DOMAIN}/shuku/{bid}/",
                            ),
                            "description": bk.get("intro", "").strip(),
                            "status": status,
                            "reader_count": str(bk.get("number", "")),
                            "category_label": category_label,
                            "cover_url": cover,
                            "source": "qimao",
                        })

                    print(
                        f"  [qimao] {ch_label}/{rank_label} "
                        f"获取 {len(list_data)} 条"
                    )

                except Exception as e:
                    print(
                        f"  [qimao] {ch_label}/{rank_label} "
                        f"异常: {e}"
                    )

                self.delay(0.5)

        print(f"  [qimao] 共获取榜单数据: {len(results)} 条")
        return results

    # ------------------------------------------------------------
    # 书籍详情
    # ------------------------------------------------------------

    def crawl_book_info(self, book_url: str) -> dict:
        """
        爬取书籍详情。

        优先使用 API: /api/book-detail/main-info?book_id={book_id}
        如果 book_url 包含 book_id 则从中提取。
        """
        book_id = self._extract_book_id(book_url)
        if not book_id:
            return {}

        try:
            resp = self.session.get(
                f"{QIMAO_DOMAIN}/api/book-detail/main-info",
                params={"book_id": book_id},
                timeout=config.REQUEST_TIMEOUT,
            )
            data = resp.json()
            bd = data.get("data", {}).get("book_detail", {})
            if not bd or not bd.get("book_id"):
                return self._crawl_book_info_ssr(book_id)

            # 从 /api/book-detail/intro 获取简介
            intro = bd.get("intro", "")
            if not intro:
                try:
                    r2 = self.session.get(
                        f"{QIMAO_DOMAIN}/api/book-detail/intro",
                        params={"book_id": book_id},
                        timeout=config.REQUEST_TIMEOUT,
                    )
                    intro = r2.json().get("data", {}).get("intro", "")
                except Exception:
                    pass

            is_over = bd.get("is_over", "0")
            status = "完结" if is_over == "1" else "连载"
            words_str = bd.get("words_num", "0")
            word_count = 0
            if words_str:
                # "869.95" 单位是万字
                try:
                    word_count = int(float(words_str) * 10000)
                except ValueError:
                    word_count = 0

            cat1 = bd.get("category_1_name", "")
            cat2 = bd.get("category_2_name", "")
            category = cat1
            if cat2:
                category = f"{cat1}/{cat2}"

            cover = bd.get("image_link", "")
            if not cover:
                orig_id = bd.get("original_book_id", "")
                if orig_id:
                    cover = self._make_cover_url(orig_id)

            total = int(bd.get("catalogue_num", 0))

            return {
                "book_id": f"qimao_{book_id}",
                "title": bd.get("title", ""),
                "author": bd.get("author", ""),
                "intro": intro,
                "category": category,
                "word_count": word_count,
                "status": status,
                "total_chapters": total,
                "cover_url": cover,
                "book_url": f"{QIMAO_DOMAIN}/shuku/{book_id}/",
            }

        except Exception as e:
            print(f"  [qimao] 书籍详情 API 异常: {e}")
            return self._crawl_book_info_ssr(book_id)

    def _crawl_book_info_ssr(self, book_id: str) -> dict:
        """回退：从 SSR 书籍详情页解析 __NUXT__ 数据"""
        try:
            resp = self.session.get(
                f"{QIMAO_DOMAIN}/shuku/{book_id}/",
                timeout=config.REQUEST_TIMEOUT,
            )
            data = self._extract_nuxt(resp.text)
            if not data:
                return {}

            # 从 state.common.bookRelatedInfo.bookDetail 提取
            state = data.get("state", {})
            common = state.get("common", {})
            related = common.get("bookRelatedInfo", {})
            bd = related.get("bookDetail", {})
            if not bd:
                return {}

            is_over = bd.get("is_over", "0")
            status = "完结" if is_over == "1" else "连载"
            words_str = bd.get("words_num", "0")
            word_count = 0
            if words_str:
                try:
                    word_count = int(float(words_str) * 10000)
                except ValueError:
                    word_count = 0

            cat1 = bd.get("category_1_name", "")
            cat2 = bd.get("category_2_name", "")
            category = cat1
            if cat2:
                category = f"{cat1}/{cat2}"

            cover = bd.get("image_link", "")
            if not cover:
                orig_id = bd.get("original_book_id", "")
                if orig_id:
                    cover = self._make_cover_url(orig_id)

            total = int(bd.get("catalogue_num", 0))

            return {
                "book_id": f"qimao_{book_id}",
                "title": bd.get("title", ""),
                "author": bd.get("author", ""),
                "intro": bd.get("intro", ""),
                "category": category,
                "word_count": word_count,
                "status": status,
                "total_chapters": total,
                "cover_url": cover,
                "book_url": f"{QIMAO_DOMAIN}/shuku/{book_id}/",
            }

        except Exception as e:
            print(f"  [qimao] 书籍详情 SSR 回退异常: {e}")

        return {}

    # ------------------------------------------------------------
    # 章节列表
    # ------------------------------------------------------------

    def crawl_chapter_list(self, book_url: str) -> list:
        """
        爬取章节列表。

        API: GET /api/book/chapter-list?book_id={book_id}
        返回 chapters 数组，每项包含 id, title, is_vip, words 等。
        章节 URL: /shuku/{book_id}-{chapter_id}/
        """
        book_id = self._extract_book_id(book_url)
        if not book_id:
            return []

        chapters: list = []

        try:
            resp = self.session.get(
                f"{QIMAO_DOMAIN}/api/book/chapter-list",
                params={"book_id": book_id},
                timeout=config.REQUEST_TIMEOUT,
            )
            data = resp.json()
            ch_list = data.get("data", {}).get("chapters", [])
            if not ch_list:
                return chapters

            for ch in ch_list[: config.CHAPTER_MAX]:
                ch_id = str(ch.get("id", ""))
                if not ch_id:
                    continue
                ch_title = ch.get("title", f"第{ch.get('index', '?')}章")
                ch_url = (
                    f"{QIMAO_DOMAIN}/shuku/{book_id}-{ch_id}/"
                )
                ch_idx = int(ch.get("index", len(chapters) + 1))
                chapters.append((ch_idx, ch_title, ch_url))

        except Exception as e:
            print(f"  [qimao] 章节列表爬取异常: {e}")

        return chapters

    # ------------------------------------------------------------
    # 章节正文
    # ------------------------------------------------------------

    def crawl_chapter_content(self, chapter_url: str) -> str:
        """
        爬取章节正文。

        方式 1 (推荐): POST /api/book/chapter
          body: book_id=xxx&chapter_id=xxx
          content 在 data.content 中 (HTML, 含 <p> 标签)

        方式 2 (回退): 从 SSR 阅读页提取正文
          CSS 选择器: .chapter-detail-wrap-content 或 .article
        """
        book_id, chapter_id = self._extract_chapter_ids(chapter_url)
        if not book_id or not chapter_id:
            return ""

        # 方式 1: API
        try:
            resp = self.session.post(
                f"{QIMAO_DOMAIN}/api/book/chapter",
                data={"book_id": book_id, "chapter_id": chapter_id},
                timeout=config.REQUEST_TIMEOUT,
            )
            data = resp.json()
            content = data.get("data", {}).get("content", "")
            if content:
                return self._clean_content(content)
        except Exception as e:
            print(f"  [qimao] 章节内容 API 异常: {e}")

        # 方式 2: SSR 页面回退
        try:
            resp = self.session.get(
                chapter_url, timeout=config.REQUEST_TIMEOUT
            )
            soup = BeautifulSoup(resp.text, "lxml")
            el = soup.select_one(
                ".chapter-detail-wrap-content, "
                ".article, "
                ".chapter-detail-article"
            )
            if el:
                return self._clean_content(el.decode_contents())
        except Exception as e:
            print(f"  [qimao] 章节内容 SSR 回退异常: {e}")

        return ""
