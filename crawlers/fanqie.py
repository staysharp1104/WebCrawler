"""番茄小说爬虫 (fanqie) — 纯 requests + SSR/API 模式，不依赖 Selenium"""
import re
import json
import time
import requests
import config
from crawlers.base import BaseCrawler

FANQIE_DOMAIN = "https://fanqienovel.com"

FANQIE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": FANQIE_DOMAIN,
}


class FanqieCrawler(BaseCrawler):
    """番茄小说爬虫 — 基于 requests + SSR/API"""

    def __init__(self):
        super().__init__("fanqie")
        self.session = requests.Session()
        self.session.headers.update(FANQIE_HEADERS)

    # ------------------------------------------------------------
    # SSR 工具
    # ------------------------------------------------------------

    @staticmethod
    def _extract_initial_state(html: str) -> dict:
        """从页面 HTML 中提取 __INITIAL_STATE__ JSON"""
        # 定位 __INITIAL_STATE__ 的起始位置
        marker = "window.__INITIAL_STATE__"
        pos = html.find(marker)
        if pos < 0:
            marker = "__INITIAL_STATE__"
            pos = html.find(marker)
        if pos < 0:
            return {}

        # 找到第一个 {
        brace_start = html.find("{", pos)
        if brace_start < 0:
            return {}

        # 括号计数法提取完整 JSON
        depth = 0
        in_str = False
        escape = False
        end = brace_start
        for i in range(brace_start, len(html)):
            ch = html[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        raw_json = html[brace_start:end]

        # 预处理：将 JS undefined/null 替换为 JSON 合法值
        raw_json = re.sub(r':undefined\b', ':null', raw_json)
        raw_json = re.sub(r':\s*undefined\b', ':null', raw_json)

        try:
            return json.loads(raw_json)
        except json.JSONDecodeError as e:
            print(f"  [fanqie] JSON 解析失败 (pos={e.pos}): {str(e)[:80]}")
            return {}

    # ------------------------------------------------------------
    # Step 1: 榜单爬取
    # ------------------------------------------------------------

    def crawl_rankings(self) -> list:
        """
        全量子类目榜单爬取:
        1. 从 SSR 的 rankCategoryTypeList 提取子类目 ID+名称
        2. 从 HTML 解析每个类目的 tab/page 映射
        3. 逐类目分页爬取 (每页10本, 最多MAX_RANK_PAGES页)
        4. 返回全部书籍榜单数据
        """
        results = []
        seen_ids: set = set()

        gender_config = [
            ("male", "男频"),
            ("female", "女频"),
        ]

        for gender, gender_label in gender_config:
            main_url = f"{FANQIE_DOMAIN}/rank?gender={gender}"
            try:
                resp = self.session.get(main_url, timeout=config.REQUEST_TIMEOUT)
                html = resp.text
                data = self._extract_initial_state(html)
                rank = data.get("rank", {})

                # 1. 提取子类目列表 [{id, name}, ...]
                category_list = (
                    rank.get("rankCategoryTypeList", {})
                    .get(gender, [])
                )
                if not category_list:
                    print(f"  [fanqie] {gender_label} 子类目列表为空")
                    continue

                # 2. 从 HTML 解析 {catId: [(tab, page), ...]} 映射
                cat_url_map: dict = {}
                for tab_s, page_s, cid in re.findall(
                    r'/rank/(\d+)_(\d+)_(\d+)', html
                ):
                    cat_url_map.setdefault(cid, set()).add(
                        (int(tab_s), int(page_s))
                    )

                print(f"  [fanqie] {gender_label} {len(category_list)} 个子类目")

                # 3. 遍历每个子类目
                for cat in category_list:
                    cat_id = cat.get("id", "")
                    cat_name = cat.get("name", "")
                    if not cat_id or not cat_name:
                        continue

                    pages = sorted(
                        cat_url_map.get(cat_id, []),
                        key=lambda x: (x[0], x[1]),
                    )

                    for tab, page in pages:
                        if page > config.MAX_RANK_PAGES:
                            continue

                        page_url = (
                            f"{FANQIE_DOMAIN}/rank/{tab}_{page}_{cat_id}"
                        )
                        try:
                            page_resp = self.session.get(
                                page_url,
                                timeout=config.REQUEST_TIMEOUT,
                            )
                            page_data = self._extract_initial_state(
                                page_resp.text
                            )
                            page_bl = (
                                page_data.get("rank", {})
                                .get("book_list", [])
                                or []
                            )

                            for i, bk in enumerate(
                                page_bl[:config.RANK_PAGE_SIZE]
                            ):
                                bid = str(bk.get("bookId", ""))
                                if not bid or bid in seen_ids:
                                    continue
                                seen_ids.add(bid)

                                creation_status = str(
                                    bk.get("creationStatus", "1")
                                )
                                status = (
                                    "完结"
                                    if creation_status == "0"
                                    else "连载"
                                )

                                read_count = str(
                                    bk.get("read_count", "")
                                    or bk.get("readCount", "")
                                )

                                results.append({
                                    "book_id": bid,
                                    "rank": str(len(results) + 1),
                                    "title": bk.get("bookName", ""),
                                    "author": bk.get("author", ""),
                                    "book_url": (
                                        f"{FANQIE_DOMAIN}/page/{bid}"
                                    ),
                                    "description": (
                                        bk.get("abstract") or ""
                                    ),
                                    "status": status,
                                    "reader_count": read_count,
                                    "category_label": (
                                        f"{cat_name}/{gender_label}新书榜"
                                    ),
                                    "cover_url": bk.get("thumbUri", ""),
                                    "source": "fanqie",
                                })
                        except Exception as e:
                            print(
                                f"  [fanqie] {cat_name} tab{tab} "
                                f"page{page} 异常: {e}"
                            )

            except Exception as e:
                print(f"  [fanqie] {gender_label} 主榜单页异常: {e}")

        print(f"  [fanqie] SSR 共获取榜单数据: {len(results)} 条，开始用 API 清洗字体加密字段...")
        self._clean_ranking_titles(results)
        print(f"  [fanqie] 共获取榜单数据: {len(results)} 条")
        return results

    @staticmethod
    def _is_garbled(text: str) -> bool:
        """
        检测文本是否含字体加密乱码特征：
        - 包含 Unicode 私用区字符 (U+E000 ~ U+F8FF)
        - 非空白字符数过少（<2）且含非常见汉字
        """
        if not text:
            return True
        # 私用区字符是字体加密的明确标志
        for ch in text:
            if 0xE000 <= ord(ch) <= 0xF8FF:
                return True
        return False

    def _clean_ranking_titles(self, results: list):
        """
        逐本调用 /api/book/info 接口，用干净文本替换 SSR 中
        可能被字体加密的 bookName / author 等字段。
        API 清洗失败且标题仍含乱码的书，从结果中移除，避免脏数据入库。
        """
        total = len(results)
        success = 0
        for idx, book in enumerate(results, 1):
            bid = book.get("book_id", "")
            if not bid:
                continue
            try:
                resp = self.session.get(
                    f"{FANQIE_DOMAIN}/api/book/info?bookId={bid}",
                    timeout=config.REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    continue
                d = resp.json().get("data", {})
                if not d or not d.get("bookId"):
                    continue

                # 用 API 干净文本覆盖可能被加密的字段
                clean_name = d.get("bookName", "")
                if clean_name:
                    book["title"] = clean_name
                clean_author = d.get("authorName", d.get("author", ""))
                if clean_author:
                    book["author"] = clean_author
                clean_desc = d.get("description", "")
                if clean_desc:
                    book["description"] = clean_desc
                clean_thumb = d.get("thumbUri", "")
                if clean_thumb:
                    book["cover_url"] = clean_thumb

                success += 1
            except Exception as e:
                print(f"  [fanqie] API 清洗 #{idx}/{total} bookId={bid} 失败: {e}")

            # 控制请求频率，避免触发限流
            time.sleep(0.3)

        # 过滤掉 API 清洗失败且标题仍含乱码的书，阻止脏数据入库
        before = len(results)
        results[:] = [
            b for b in results
            if not self._is_garbled(b.get("title", ""))
        ]
        removed = before - len(results)
        print(f"  [fanqie] API 清洗完成: {success}/{total} 本成功")
        if removed:
            print(f"  [fanqie] 已移除 {removed} 本乱码书（API 不可达/已下架）")

    # ------------------------------------------------------------
    # Step 3: 书籍详情
    # ------------------------------------------------------------

    def crawl_book_info(self, book_url: str) -> dict:
        """
        合并 API（干净文本）与 SSR（章节总数）数据
        """
        m = re.search(r"/page/(\d+)", book_url)
        bid = m.group(1) if m else ""
        if not bid:
            m = re.search(r"/(\d+)", book_url)
            bid = m.group(1) if m else ""

        # 优先用 API（干净文本）
        api_info = self._fetch_book_info_api(bid)
        if api_info:
            # 补充 SSR 中的章节总数
            ssr_info = self._fetch_book_info_ssr(bid, book_url)
            if ssr_info and ssr_info.get("total_chapters"):
                api_info["total_chapters"] = ssr_info["total_chapters"]
            return api_info

        return self._fetch_book_info_ssr(bid, book_url)

    def _fetch_book_info_api(self, bid: str) -> dict:
        """通过 /api/book/info 获取书籍详情"""
        try:
            resp = self.session.get(
                f"{FANQIE_DOMAIN}/api/book/info?bookId={bid}",
                timeout=config.REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                return {}
            d = resp.json().get("data", {})
            if not d or not d.get("bookId"):
                return {}

            # 从 categoryV2 提取主分类
            category = ""
            cat_v2 = d.get("categoryV2", "")
            if cat_v2:
                try:
                    cat_list = json.loads(cat_v2)
                    main_cats = [c.get("Name", "") for c in cat_list
                                 if c.get("MainCategory")]
                    category = main_cats[0] if main_cats else cat_list[0].get("Name", "")
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass

            creation_status = str(d.get("creationStatus", "1"))
            status = "完结" if creation_status == "0" else "连载"

            return {
                "book_id": bid,
                "title": d.get("bookName", ""),
                "author": d.get("authorName", d.get("author", "")),
                "intro": d.get("description", ""),
                "category": category,
                "word_count": int(d.get("wordNumber", 0)),
                "status": status,
                "total_chapters": 0,
                "cover_url": d.get("thumbUri", ""),
                "book_url": f"{FANQIE_DOMAIN}/page/{bid}",
            }
        except Exception as e:
            print(f"  [fanqie] API 获取详情失败: {e}")
        return {}

    def _fetch_book_info_ssr(self, bid: str, book_url: str) -> dict:
        """通过书籍页 SSR 获取详情（含章节总数）"""
        try:
            resp = self.session.get(book_url, timeout=config.REQUEST_TIMEOUT)
            data = self._extract_initial_state(resp.text)
            page = data.get("page", {})
            if not page or not page.get("bookId"):
                return {}

            creation_status = str(page.get("creationStatus", "1"))
            status = "完结" if creation_status == "0" else "连载"

            return {
                "book_id": bid,
                "title": page.get("bookName", ""),
                "author": page.get("author", page.get("authorName", "")),
                "intro": page.get("abstract", ""),
                "category": page.get("category", ""),
                "word_count": int(page.get("wordNumber", 0)),
                "status": status,
                "total_chapters": int(page.get("chapterTotal", 0)),
                "cover_url": page.get("thumbUri", page.get("thumbUrl", "")),
                "book_url": book_url,
            }
        except Exception as e:
            print(f"  [fanqie] SSR 获取详情失败: {e}")
        return {}

    # ------------------------------------------------------------
    # Step 4: 章节列表
    # ------------------------------------------------------------

    def crawl_chapter_list(self, book_url: str) -> list:
        """
        从书籍页 SSR 的 chapterListWithVolume 提取前 10 章

        返回 [(chapter_index, chapter_title, chapter_url), ...]
        """
        m = re.search(r"/page/(\d+)", book_url)
        bid = m.group(1) if m else book_url

        chapters: list = []

        try:
            resp = self.session.get(
                f"{FANQIE_DOMAIN}/page/{bid}",
                timeout=config.REQUEST_TIMEOUT,
            )
            data = self._extract_initial_state(resp.text)
            page = data.get("page", {})

            # 方法一：chapterListWithVolume → 有序列表
            ch_vol = page.get("chapterListWithVolume", [])
            if ch_vol and isinstance(ch_vol, list):
                flat: list = []
                for vol in ch_vol:
                    if isinstance(vol, list):
                        flat.extend(vol)
                    elif isinstance(vol, dict):
                        sub = vol.get("chapterList") or vol.get("list") or []
                        if isinstance(sub, list):
                            flat.extend(sub)
                        else:
                            flat.append(vol)
                    else:
                        flat.append(vol)

                for i, ch in enumerate(flat[:config.CHAPTER_MAX]):
                    item_id = ch.get("itemId", "")
                    title = ch.get("title", f"第{i+1}章")
                    ch_url = f"{FANQIE_DOMAIN}/reader/{item_id}"
                    chapters.append((i + 1, title, ch_url))
                if chapters:
                    return chapters

            # 方法二：itemIds（可能会反序——最后一章在前）
            item_ids = page.get("itemIds", [])
            if item_ids:
                # 取最后 CHAPTER_MAX 个（最初的章节）
                target_ids = item_ids[-config.CHAPTER_MAX:]
                for i, item_id in enumerate(target_ids):
                    ch_url = f"{FANQIE_DOMAIN}/reader/{item_id}"
                    chapters.append((i + 1, f"第{i+1}章", ch_url))
                return chapters

        except Exception as e:
            print(f"  [fanqie] 获取章节列表失败: {e}")

        return chapters

    # ------------------------------------------------------------
    # Step 4: 章节正文
    # ------------------------------------------------------------

    def crawl_chapter_content(self, chapter_url: str) -> str:
        """
        从读者页 SSR 的 reader.chapterData.content 提取正文
        """
        try:
            resp = self.session.get(chapter_url, timeout=config.REQUEST_TIMEOUT)
            data = self._extract_initial_state(resp.text)

            # 优先取 reader.chapterData
            reader = data.get("reader", {})
            ch_data = reader.get("chapterData", {})
            content = ch_data.get("content", "")
            if content:
                return self._clean_content(content)

            # 回退到 preview.chapterData
            preview = data.get("preview", {}).get("chapterData", {})
            content = preview.get("content", "")
            if content:
                return self._clean_content(content)

            return ""
        except Exception as e:
            print(f"  [fanqie] 获取章节内容失败: {e}")
            return ""

    # ------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------

    @staticmethod
    def _clean_content(text: str) -> str:
        """清洗正文 HTML"""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.replace("\u3000", "")
        return text.strip()
