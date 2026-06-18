"""起点中文网爬虫 (qidian) — 基于移动站 m.qidian.com SSR JSON 数据"""
import re
import json
import requests
from bs4 import BeautifulSoup
import config
from crawlers.base import BaseCrawler

QIDIAN_M_DOMAIN = "https://m.qidian.com"

QIDIAN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/14.0 Mobile/15E148 Safari/604.1"
    ),
    "Referer": QIDIAN_M_DOMAIN,
}


class QidianCrawler(BaseCrawler):
    """起点中文网爬虫 — 基于移动站 SSR/JSON 数据"""

    COVER_URL_TPL = "https://bookcover.yuewen.com/qdbimg/349573/{}/180"

    # 榜单类别映射 (key, label)
    RANK_SECTIONS = [
        ("fyRank", "月票榜"),
        ("hotRank", "热销榜"),
        ("readIndex", "阅读指数榜"),
        ("recRank", "推荐榜"),
        ("newpRank", "新书榜"),
        ("updRank", "更新榜"),
        ("dsRank", "收藏榜"),
        ("newbRank", "新人新书"),
        ("signRank", "签约榜"),
        ("newFans", "新粉丝榜"),
    ]

    def __init__(self):
        super().__init__("qidian")
        self.session = requests.Session()
        self.session.headers.update(QIDIAN_HEADERS)

    # ------------------------------------------------------------
    # SSR 工具
    # ------------------------------------------------------------

    @staticmethod
    def _extract_ssr_json(html: str) -> dict:
        """提取页面中 type=application/json 的 SSR 数据"""
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script"):
            if script.get("type") == "application/json":
                try:
                    return json.loads(script.string)
                except (json.JSONDecodeError, TypeError):
                    continue
        return {}

    @staticmethod
    def _make_cover_url(bid: str) -> str:
        """构造起点封面图片 URL"""
        return QidianCrawler.COVER_URL_TPL.format(bid)

    @staticmethod
    def _clean_content(text: str) -> str:
        """清洗章节正文 HTML"""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.replace("\u3000", "")
        return text.strip()

    # ------------------------------------------------------------
    # Step 1: 榜单爬取
    # ------------------------------------------------------------

    def crawl_rankings(self) -> list:
        """
        从 m.qidian.com/rank 页面提取多类榜单数据

        页面使用 React SSR，数据嵌入在 <script type="application/json"> 中。
        pageData 包含 fyRank(月票), hotRank(热销), readIndex(阅读指数),
        recRank(推荐), newpRank(新书), updRank(更新), dsRank(收藏),
        newbRank(新人), signRank(签约), newFans(新粉丝) 等榜单列表。
        """
        results = []

        try:
            resp = self.session.get(
                f"{QIDIAN_M_DOMAIN}/rank",
                timeout=config.REQUEST_TIMEOUT,
            )
            data = self._extract_ssr_json(resp.text)
            page_data = (
                data.get("pageContext", {})
                .get("pageProps", {})
                .get("pageData", {})
            )

            if not page_data:
                print("  [qidian] 榜单页未找到 pageData")
                return results

            for rank_key, rank_label in self.RANK_SECTIONS:
                book_list = page_data.get(rank_key, [])
                if not book_list:
                    continue

                for bk in book_list[: config.RANK_PAGE_SIZE]:
                    bid = str(bk.get("bid", ""))
                    if not bid:
                        continue

                    results.append({
                        "book_id": f"qidian_{bid}",
                        "rank": str(bk.get("rankNum", len(seen_ids))),
                        "title": bk.get("bName", ""),
                        "author": bk.get("bAuth", ""),
                        "book_url": f"{QIDIAN_M_DOMAIN}/book/{bid}",
                        "description": bk.get("desc", ""),
                        "status": "连载",
                        "reader_count": str(bk.get("rankCnt", "")),
                        "category_label": f"{bk.get('cat', '')}/{rank_label}",
                        "cover_url": self._make_cover_url(bid),
                        "source": "qidian",
                    })

        except Exception as e:
            print(f"  [qidian] 榜单爬取异常: {e}")

        print(f"  [qidian] 共获取榜单数据: {len(results)} 条")
        return results

    # ------------------------------------------------------------
    # Step 3: 书籍详情
    # ------------------------------------------------------------

    def crawl_book_info(self, book_url: str) -> dict:
        """
        从 m.qidian.com/book/{bid} 提取书籍详情

        SSR JSON 的 pageData.bookInfo 包含全部书籍元数据。
        封面通过 bookId 构造标准 URL。
        """
        m = re.search(r"/book/(\d+)", book_url)
        bid = m.group(1) if m else ""
        if not bid:
            return {}

        try:
            resp = self.session.get(
                f"{QIDIAN_M_DOMAIN}/book/{bid}",
                timeout=config.REQUEST_TIMEOUT,
            )
            data = self._extract_ssr_json(resp.text)
            page_data = (
                data.get("pageContext", {})
                .get("pageProps", {})
                .get("pageData", {})
            )
            bi = page_data.get("bookInfo", {})

            if not bi or not bi.get("bookId"):
                return {}

            action_status = bi.get("actionStatus", "")
            status = "完结" if "完" in action_status else "连载"

            category = bi.get("chanName", "")
            sub_cat = bi.get("subCateName", "")
            if sub_cat:
                category = f"{category}/{sub_cat}"

            return {
                "book_id": f"qidian_{bid}",
                "title": bi.get("bookName", ""),
                "author": bi.get("authorName", ""),
                "intro": bi.get("desc", ""),
                "category": category,
                "word_count": int(bi.get("wordsCnt", 0)),
                "status": status,
                "total_chapters": 0,
                "cover_url": self._make_cover_url(bid),
                "book_url": f"{QIDIAN_M_DOMAIN}/book/{bid}",
            }
        except Exception as e:
            print(f"  [qidian] 书籍详情爬取异常: {e}")
        return {}

    # ------------------------------------------------------------
    # Step 4: 章节列表
    # ------------------------------------------------------------

    def crawl_chapter_list(self, book_url: str) -> list:
        """
        从 m.qidian.com/book/{bid}/catalog 提取章节列表

        SSR JSON 的 pageData.vs 是卷数组，每卷有 cs（章节列表）。
        跳过"作品相关"等非正文卷，取前 CHAPTER_MAX 章。
        """
        m = re.search(r"/book/(\d+)", book_url)
        bid = m.group(1) if m else ""
        if not bid:
            return []

        chapters: list = []

        try:
            resp = self.session.get(
                f"{QIDIAN_M_DOMAIN}/book/{bid}/catalog",
                timeout=config.REQUEST_TIMEOUT,
            )
            data = self._extract_ssr_json(resp.text)
            page_data = (
                data.get("pageContext", {})
                .get("pageProps", {})
                .get("pageData", {})
            )
            vs = page_data.get("vs", [])

            idx = 0
            for volume in vs:
                vn = volume.get("vN", "")
                # 跳过"作品相关"等非正文卷
                if "相关" in vn or "公告" in vn:
                    continue
                ch_list = volume.get("cs", [])
                for ch in ch_list:
                    if idx >= config.CHAPTER_MAX:
                        break
                    ch_id = ch.get("id", "")
                    if not ch_id:
                        continue
                    idx += 1
                    ch_title = ch.get("cN", f"第{idx}章")
                    ch_url = f"{QIDIAN_M_DOMAIN}/chapter/{bid}/{ch_id}/"
                    chapters.append((idx, ch_title, ch_url))
                if idx >= config.CHAPTER_MAX:
                    break

        except Exception as e:
            print(f"  [qidian] 章节列表爬取异常: {e}")

        return chapters

    # ------------------------------------------------------------
    # Step 4: 章节正文
    # ------------------------------------------------------------

    def crawl_chapter_content(self, chapter_url: str) -> str:
        """
        从 m.qidian.com/chapter/{bid}/{ch_id}/ 提取章节正文

        SSR JSON 的 pageData.chapterInfo.content 包含 HTML 格式正文。
        清洗掉 HTML 标签后返回纯文本。
        """
        try:
            resp = self.session.get(
                chapter_url,
                timeout=config.REQUEST_TIMEOUT,
            )
            data = self._extract_ssr_json(resp.text)
            page_data = (
                data.get("pageContext", {})
                .get("pageProps", {})
                .get("pageData", {})
            )
            ci = page_data.get("chapterInfo", {})
            content = ci.get("content", "")
            if content:
                return self._clean_content(content)
            return ""
        except Exception as e:
            print(f"  [qidian] 章节内容爬取异常: {e}")
        return ""


