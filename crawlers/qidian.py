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
        聚合起点所有榜单类型：综合榜单(10个子榜) + 三江推荐 + 强推推荐 + 推荐榜(周榜)

        综合榜单来自 m.qidian.com/rank (月票/热销/阅读/推荐/新书/更新/收藏/新人/签约/新粉丝)，
        每榜取 RANK_PAGE_SIZE 本。三江/强推/推荐榜通过独立 SSR 页面获取。
        """
        results = []

        # ====== 1. 综合榜单（10个子榜） ======
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

            if page_data:
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
                            "rank": str(bk.get("rankNum", "")),
                            "title": bk.get("bName", ""),
                            "author": bk.get("bAuth", ""),
                            "book_url": f"{QIDIAN_M_DOMAIN}/book/{bid}",
                            "description": bk.get("desc", ""),
                            "status": "连载",
                            "reader_count": str(bk.get("rankCnt", "")),
                            "category_label": f"综合榜单/{rank_label}/{bk.get('cat', '')}",
                            "cover_url": self._make_cover_url(bid),
                            "source": "qidian",
                        })
            else:
                print("  [qidian] 综合榜单页未找到 pageData")

        except Exception as e:
            print(f"  [qidian] 综合榜单爬取异常: {e}")

        print(f"  [qidian] 综合榜单(10子榜): {len(results)} 条")

        # ====== 2. 三江推荐 ======
        try:
            sj_results = self.crawl_sanjiang()
            # crawl_sanjiang 返回格式与 crawl_rankings 一致，直接合并
            for r in sj_results:
                # 重新标记 category_label 统一前缀
                r["category_label"] = f"三江推荐/{r.get('category_label','').replace('三江推荐/','')}"
            results.extend(sj_results)
        except Exception as e:
            print(f"  [qidian] 三江榜单爬取异常: {e}")

        # ====== 3. 强推推荐 ======
        try:
            sr_results = self.crawl_strongrec()
            for r in sr_results:
                r["category_label"] = f"强推推荐/{r.get('category_label','').replace('强推推荐/','')}"
            results.extend(sr_results)
        except Exception as e:
            print(f"  [qidian] 强推榜单爬取异常: {e}")

        # ====== 4. 推荐榜（三周期：周/月/总） ======
        for period, period_label in [(3, "周"), (2, "月"), (1, "总")]:
            try:
                rr_results = self.crawl_rank_rec(rank_period=period)
                for r in rr_results:
                    r["category_label"] = f"推荐榜({period_label})/{r.get('category_label','').replace('推荐榜/','')}"
                results.extend(rr_results)
                print(f"    [qidian] 推荐榜({period_label}榜): {len(rr_results)} 条")
            except Exception as e:
                print(f"    [qidian] 推荐榜({period_label}榜)爬取异常: {e}")

        print(f"  [qidian] 起点榜单总计: {len(results)} 条数据")
        return results

    def crawl_sanjiang(self) -> list:
        """
        从 m.qidian.com/sanjiang/ 提取三江榜单数据

        三江榜单每周推荐 17 本新书，SSR JSON 的 records 包含每本书详情。
        与 crawl_rankings() 返回相同格式，category_label 固定为 "三江推荐"。
        """
        results = []

        try:
            resp = self.session.get(
                f"{QIDIAN_M_DOMAIN}/sanjiang/",
                timeout=config.REQUEST_TIMEOUT,
            )
            data = self._extract_ssr_json(resp.text)
            page_data = (
                data.get("pageContext", {})
                .get("pageProps", {})
                .get("pageData", {})
            )

            if not page_data:
                print("  [qidian] 三江页未找到 pageData")
                return results

            records = page_data.get("records", [])
            for i, bk in enumerate(records):
                bid = str(bk.get("bid", ""))
                if not bid:
                    continue

                results.append({
                    "book_id": f"qidian_{bid}",
                    "rank": str(i + 1),
                    "title": bk.get("bName", ""),
                    "author": bk.get("bAuth", ""),
                    "book_url": f"{QIDIAN_M_DOMAIN}/book/{bid}",
                    "description": bk.get("desc", ""),
                    "status": "连载",
                    "reader_count": str(bk.get("cnt", "")),
                    "category_label": f"三江推荐/{bk.get('cat', '')}",
                    "cover_url": self._make_cover_url(bid),
                    "source": "qidian",
                })

        except Exception as e:
            print(f"  [qidian] 三江榜单爬取异常: {e}")

        print(f"  [qidian] 三江榜单: {len(results)} 本书")
        return results

    def crawl_strongrec(self, cat_id: int = -1) -> list:
        """
        从 m.qidian.com/strongrec/ 提取强推榜单数据

        强推榜单每周推荐约 17 本精选新书，SSR records 中嵌入时间槽（isTime=True），
        需过滤后提取真实书籍。支持分类筛选（catId），分页参数在 SSR 中无效
        （服务端始终返回第 1 页数据）。
        """
        results = []

        try:
            url = f"{QIDIAN_M_DOMAIN}/strongrec/?catId={cat_id}"
            resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
            data = self._extract_ssr_json(resp.text)
            page_data = (
                data.get("pageContext", {})
                .get("pageProps", {})
                .get("pageData", {})
            )

            if not page_data:
                print("  [qidian] 强推页未找到 pageData")
                return results

            records = page_data.get("records", [])
            for bk in records:
                if bk.get("isTime"):
                    continue  # 跳过时间槽占位符
                bid = str(bk.get("bid", ""))
                if not bid:
                    continue

                results.append({
                    "book_id": f"qidian_{bid}",
                    "rank": str(bk.get("_index", len(results) + 1)),
                    "title": bk.get("bName", ""),
                    "author": bk.get("bAuth", ""),
                    "book_url": f"{QIDIAN_M_DOMAIN}/book/{bid}",
                    "description": bk.get("desc", ""),
                    "status": bk.get("state", "连载"),
                    "reader_count": str(bk.get("cnt", "")),
                    "category_label": f"强推推荐/{bk.get('cat', '')}",
                    "cover_url": self._make_cover_url(bid),
                    "source": "qidian",
                })

        except Exception as e:
            print(f"  [qidian] 强推榜单爬取异常: {e}")

        print(f"  [qidian] 强推榜单: {len(results)} 本书 (catId={cat_id})")
        return results

    def crawl_rank_rec(self, cat_id: int = -1, rank_period: int = 3) -> list:
        """
        从 m.qidian.com/rank/rec 提取推荐榜数据

        推荐榜按推荐票排序，总榜最多 500 本。SSR 仅返回第 1 页（约 20 本），
        分页参数由客户端 JavaScript 控制，服务端 SSR 固定返回首页。
        rankPeriod: 3=周榜, 2=月榜, 1=总榜
        """
        results = []

        try:
            url = f"{QIDIAN_M_DOMAIN}/rank/rec?catId={cat_id}&rankPeriod={rank_period}"
            resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
            data = self._extract_ssr_json(resp.text)
            page_data = (
                data.get("pageContext", {})
                .get("pageProps", {})
                .get("pageData", {})
            )

            if not page_data:
                print("  [qidian] 推荐榜未找到 pageData")
                return results

            records = page_data.get("records", [])
            for bk in records:
                bid = str(bk.get("bid", ""))
                if not bid:
                    continue

                results.append({
                    "book_id": f"qidian_{bid}",
                    "rank": str(bk.get("rankNum", "")),
                    "title": bk.get("bName", ""),
                    "author": bk.get("bAuth", ""),
                    "book_url": f"{QIDIAN_M_DOMAIN}/book/{bid}",
                    "description": bk.get("desc", ""),
                    "status": "连载",
                    "reader_count": str(bk.get("rankCnt", "")),
                    "category_label": f"推荐榜/{bk.get('cat', '')}",
                    "cover_url": self._make_cover_url(bid),
                    "source": "qidian",
                })

            total = page_data.get("total", 0)
            print(f"  [qidian] 推荐榜: {len(results)}/共{total} 本 (catId={cat_id}, period={rank_period})")

        except Exception as e:
            print(f"  [qidian] 推荐榜爬取异常: {e}")

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
        m = re.search(r"/(?:book|info)/(\d+)", book_url)
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
        m = re.search(r"/(?:book|info)/(\d+)", book_url)
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


