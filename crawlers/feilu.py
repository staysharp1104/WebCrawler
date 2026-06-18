"""飞卢小说爬虫 (feilu) — 修复版"""
import re
import time
import requests
import config
from crawlers.base import BaseCrawler
from bs4 import BeautifulSoup

FEILU_DOMAIN = "https://b.faloo.com"
FEILU_RANK_URL = "https://b.faloo.com/l/0/1.html"


class FeiluCrawler(BaseCrawler):
    """飞卢小说爬虫"""

    def __init__(self):
        super().__init__("feilu")

    def crawl_rankings(self) -> list:
        """爬取飞卢新书榜 — 基于实际HTML结构"""
        results = []
        # 飞卢榜单分类ID
        category_map = {
            "0": "全部",
            "1": "玄幻奇幻", "2": "武侠仙侠", "3": "都市言情",
            "4": "军事历史", "5": "网游竞技", "6": "科幻",
            "7": "女生", "8": "同人",
        }
        headers = {"User-Agent": config.USER_AGENTS[0], "Referer": FEILU_DOMAIN}

        for cat_id, cat_name in category_map.items():
            url = f"{FEILU_DOMAIN}/l/{cat_id}/1.html"
            print(f"  [feilu] 爬取分类 {cat_name} ({cat_id})...")
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "lxml")
                # 飞卢榜单页：每两个书共享一个 .TwoBox02_01 容器
                containers = soup.select(".TwoBox02_01")
                items = []
                for c in containers:
                    links = c.find_all("a", href=True)
                    # 每6个链接为一本书 (cover, title, author, category, desc, chapter)
                    for i in range(0, len(links), 6):
                        grp = links[i:i + 6]
                        if len(grp) < 2:
                            continue
                        items.append(grp)
                seen = set()
                for grp in items:
                    cover_a = grp[0]
                    title_a = grp[1]
                    href = title_a.get("href", "")
                    m = re.search(r"/(\d+)\.html", href)
                    if not m:
                        continue
                    bid = m.group(1)
                    book_id = f"feilu_{bid}"
                    if book_id in seen:
                        continue
                    seen.add(book_id)
                    title = title_a.get("title") or title_a.text.strip()
                    if not title:
                        continue
                    # book_url
                    book_url = href if href.startswith("http") else f"https:{href}"
                    # 作者 — 第3个链接(a[2])通常是作者
                    author = ""
                    if len(grp) >= 3:
                        author = grp[2].text.strip()
                    # 简介 — 第5个链接(a[4])
                    desc = ""
                    if len(grp) >= 5:
                        desc = grp[4].text.strip()
                    # 封面
                    cover = ""
                    img = cover_a.find("img")
                    if img:
                        cover = img.get("src") or img.get("data-src") or ""
                    if cover and not cover.startswith("http"):
                        cover = f"https:{cover}"
                    results.append({
                        "book_id": book_id,
                        "rank": str(len(seen)),
                        "title": title.strip(),
                        "author": author,
                        "book_url": book_url,
                        "description": desc,
                        "status": "连载",
                        "reader_count": "",
                        "category_label": f"{cat_name}/新书榜",
                        "cover_url": cover,
                        "source": "feilu",
                    })
                    if len(seen) >= config.RANK_PAGE_SIZE:
                        break
            except Exception as e:
                print(f"  [feilu] 分类 {cat_name} 爬取失败: {e}")
            time.sleep(1)

        print(f"  [feilu] 共获取榜单数据: {len(results)} 条")
        return results

    def crawl_book_info(self, book_url: str) -> dict:
        """爬取书籍详情 — 基于实际HTML结构"""
        headers = {"User-Agent": config.USER_AGENTS[0], "Referer": FEILU_DOMAIN}
        try:
            resp = requests.get(book_url, headers=headers, timeout=20)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            print(f"    [feilu] 请求失败 {book_url}: {e}")
            return {}

        bid = ""
        m = re.search(r"/(\d+)\.html", book_url)
        if m:
            bid = f"feilu_{m.group(1)}"

        # 标题
        title = ""
        t = soup.select_one("h1")
        if t:
            title = t.text.strip()

        # 作者 — 在 .C-Two 中第二段纯文本
        author = ""
        c_two = soup.select_one(".C-Two")
        if c_two:
            texts = [s.strip() for s in c_two.stripped_strings if s.strip()]
            if len(texts) >= 2:
                author = texts[1]

        # 简介
        intro = ""
        i = soup.select_one(".T-L-Two")
        if i:
            intro = i.text.strip()

        # 分类 — 从面包屑导航
        category = ""
        center = soup.select_one(".center")
        if center:
            parts = [a.text.strip() for a in center.select("a")]
            if len(parts) >= 3:
                category = parts[2]

        # 字数 — 从 "已写 N N N... 个字" 中提取
        word_count = 0
        page_text = soup.get_text()
        wc_match = re.search(r'已写[\s]*(\d[\d\s]*\d)[\s]*个字', page_text)
        if wc_match:
            digits = re.sub(r'\s+', '', wc_match.group(1))
            try:
                word_count = int(digits)
            except ValueError:
                word_count = 0

        # 总章节数 — 从目录中的章节数推断，只算当前书的章节
        total_chapters = 0
        current_bid = ""
        cm = re.search(r"/(\d+)\.html", book_url)
        if cm:
            current_bid = cm.group(1)
        mulu = soup.select_one(".C-Fo-Z-Mulu")
        if mulu:
            for a in mulu.find_all("a"):
                href = a.get("href", "")
                chm = re.search(r"/(\d+)_(\d+)\.html", href)
                if chm and chm.group(1) == current_bid:
                    n = int(chm.group(2))
                    if n > total_chapters:
                        total_chapters = n
        # 安全钳位：最大 99999 章
        if total_chapters > 99999:
            total_chapters = 0

        # 状态
        status = "连载"
        if "完本" in page_text or "已完结" in page_text:
            status = "完结"

        # 封面 — 从详情页找书籍封面
        cover = ""
        for img in soup.select("img[src*='Novel'], img[src*='novel'], img[src*='faloo']"):
            src = img.get("src", "")
            if "bg" not in src.lower() and len(src) > 30:
                cover = src if src.startswith("http") else f"https:{src}"
                break

        return {
            "book_id": bid,
            "title": title,
            "author": author,
            "intro": intro,
            "category": category,
            "word_count": word_count,
            "status": status,
            "total_chapters": total_chapters,
            "cover_url": cover,
            "book_url": book_url,
        }

    def crawl_chapter_list(self, book_url: str) -> list:
        """爬取飞卢章节列表 — 书籍详情页自带目录"""
        chapters = []
        headers = {"User-Agent": config.USER_AGENTS[0], "Referer": FEILU_DOMAIN}
        try:
            resp = requests.get(book_url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception:
            return chapters

        # 书籍详情页的章节目录在 .C-Fo-Z-Mulu 中
        mulu = soup.select_one(".C-Fo-Z-Mulu")
        if not mulu:
            return chapters

        links = mulu.find_all("a")
        # 第一个链接通常是"正文"标题（不含章节序号），跳过
        start_idx = 0
        for i, a in enumerate(links):
            href = a.get("href", "")
            txt = a.text.strip()
            m = re.search(r"/(\d+)_(\d+)\.html", href)
            if m:
                ch_idx = int(m.group(2))
                ch_url = href if href.startswith("http") else f"https:{href}"
                chapters.append((ch_idx, txt, ch_url))
                if len(chapters) >= config.CHAPTER_MAX:
                    break
        return chapters

    def crawl_chapter_content(self, chapter_url: str) -> str:
        """爬取章节正文 — 提取 .nr_center 中的正文文本"""
        headers = {"User-Agent": config.USER_AGENTS[0], "Referer": FEILU_DOMAIN}
        try:
            resp = requests.get(chapter_url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "lxml")
            # 正文区域
            content_div = soup.select_one(".nr_center")
            if not content_div:
                # 备选
                for sel in [".content", ".txt", ".chapter-content", ".c-text", ".novel-content", ".C-Fo-You-Two-Content"]:
                    el = soup.select_one(sel)
                    if el and len(el.text.strip()) > 200:
                        return el.text.strip()
                return ""

            # 提取正文内容（跳过头部导航信息）
            texts = []
            for child in content_div.children:
                if hasattr(child, 'name') and child.name in ['p', 'div', 'br']:
                    txt = child.get_text(strip=True)
                    if txt and len(txt) > 10:
                        texts.append(txt)
            if texts:
                return '\n\n'.join(texts)
            return content_div.text.strip()
        except Exception:
            pass
        return ""
