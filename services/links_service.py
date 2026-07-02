"""链接驱动单书采集服务层 —— URL解析、任务下发、后台采集流水线"""

import re
import threading
import traceback
from typing import Optional
import config
from db_ops import (
    insert_book, update_book_crawl_status,
    update_book_cover_path, insert_chapter,
    create_task, update_task_status, update_task_target_id, add_book_log,
    get_book_exists,
)
from services.file_manager import save_chapter_content, download_cover, ensure_dirs
from crawlers.fanqie import FanqieCrawler
from crawlers.feilu import FeiluCrawler
from crawlers.qimao import QimaoCrawler
from crawlers.qidian import QidianCrawler

# 爬虫类映射
CRAWLER_MAP = {
    "fanqie": FanqieCrawler,
    "feilu": FeiluCrawler,
    "qimao": QimaoCrawler,
    "qidian": QidianCrawler,
}

# ==================== 平台识别规则（域名正则） ====================

PLATFORM_RULES = [
    (r"book\.qidian\.com/info/(\d+)", "qidian"),
    (r"www\.qidian\.com/book/(\d+)", "qidian"),
    (r"fanqienovel\.com/page/(\d+)", "fanqie"),
    (r"b\.faloo\.com/(\d+)", "feilu"),
    (r"www\.qimao\.com/shuku/(\d+)", "qimao"),
]


def parse_url(url: str) -> dict:
    """
    解析单个 URL，识别平台、提取 book_id

    返回:
        {
            "url": str,
            "status": "ok" | "unsupported" | "duplicate",
            "platform": str | None,
            "book_id": str | None,
            "exists": bool,
        }
    """
    url = url.strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return {"url": url, "status": "unsupported", "platform": None,
                "book_id": None, "exists": False}

    for pattern, platform in PLATFORM_RULES:
        m = re.search(pattern, url)
        if m:
            book_id = m.group(1)
            exists = get_book_exists(book_id)
            return {
                "url": url,
                "status": "duplicate" if exists else "ok",
                "platform": platform,
                "book_id": book_id,
                "exists": exists,
            }

    return {"url": url, "status": "unsupported", "platform": None,
            "book_id": None, "exists": False}


def parse_urls(urls: list) -> list:
    """批量解析 URL"""
    return [parse_url(u) for u in urls]


# ==================== 任务提交与后台执行 ====================


def submit_link_collection(items: list) -> list:
    """
    提交链接采集任务

    items: [{"url": str, "platform": str, "book_id": str}, ...]
    返回: [task_id, ...]
    """
    ensure_dirs()
    task_ids = []
    for item in items:
        tid = create_task(
            "crawl_single_book",
            item["platform"],
            target_id=item["book_id"],
            priority=80,
        )
        if tid:
            task_ids.append(tid)

    if task_ids:
        # 启动后台线程执行采集
        t = threading.Thread(
            target=_run_batch,
            args=(task_ids, items),
            daemon=True,
        )
        t.start()

    return task_ids


def _run_batch(task_ids: list, items: list):
    """按顺序执行批量采集"""
    for tid, item in zip(task_ids, items):
        _run_single_book(tid, item["platform"], item["url"], item["book_id"])


def _run_single_book(task_id: int, platform: str, book_url: str, book_id: str):
    """
    单本书籍采集全流程

    流程:
        1. 标记任务运行中
        2. CRAWLER_MAP[platform].crawl_book_info(book_url) -> insert_book()
        3. download_cover() -> update_book_cover_path()
        4. crawl_chapter_list(book_url) -> 取前 N 章 (N=min(10, total))
        5. 逐章 crawl_chapter_content() -> save_chapter_content() -> insert_chapter()
        6. 更新书籍 crawl_status=2，标记任务成功
    """
    crawler = None
    try:
        # 1. 标记任务运行中
        update_task_status(task_id, config.TASK_STATUS_RUNNING)
        add_book_log(book_id, f"开始采集: {config.PLATFORM_LABELS.get(platform, platform)}",
                     source=platform)

        # 2. 爬取书籍信息
        crawler_cls = CRAWLER_MAP.get(platform)
        if not crawler_cls:
            raise ValueError(f"不支持的平台: {platform}")

        crawler = crawler_cls()
        info = crawler.crawl_book_info(book_url)
        if not info or not info.get("book_id"):
            raise ValueError("书籍信息爬取失败")

        info["source"] = platform
        info["chapter_count"] = 0
        info["cover_path"] = ""
        info["crawl_status"] = config.CRAWL_STATUS_RUNNING
        insert_book(info)

        # 使用爬虫返回的 book_id（含平台前缀）覆盖原始参数
        book_id = info["book_id"]
        # 同步更新任务的 target_id，确保 JOIN 查询能匹配
        update_task_target_id(task_id, book_id)
        add_book_log(book_id, f"书籍信息采集完成: {info.get('title', '')}", source=platform)

        # 3. 下载封面
        cover_url = info.get("cover_url", "")
        if cover_url:
            try:
                cover_path = download_cover(cover_url, book_id, platform)
                if cover_path:
                    update_book_cover_path(book_id, cover_path)
                    add_book_log(book_id, "封面下载完成", source=platform)
            except Exception as e:
                add_book_log(book_id, f"封面下载失败: {e}", source=platform, role="error")

        # 4. 获取章节列表
        chapters = crawler.crawl_chapter_list(book_url)
        if not chapters:
            raise ValueError("章节列表爬取为空")

        # 取前 10 章（或全部）
        chapter_max = min(config.CHAPTER_MAX, len(chapters))
        crawled_count = 0

        for idx in range(chapter_max):
            ch_index, ch_title, ch_url = chapters[idx]
            try:
                content = crawler.crawl_chapter_content(ch_url)
                if content:
                    result = save_chapter_content(book_id, ch_index, content)
                    insert_chapter({
                        "book_id": book_id,
                        "chapter_index": ch_index,
                        "chapter_title": ch_title,
                        "chapter_url": ch_url,
                        "content_path": result["content_path"],
                        "content_size": result["content_size"],
                        "source": platform,
                    })
                    crawled_count += 1
                    add_book_log(book_id, f"第{ch_index}章采集完成: {ch_title}", source=platform)
                else:
                    add_book_log(book_id, f"第{ch_index}章内容为空: {ch_title}",
                                 source=platform, role="error")
            except Exception as e:
                add_book_log(book_id, f"第{ch_index}章采集失败: {e}",
                             source=platform, role="error")

        # 5. 更新状态
        total_to_crawl = min(config.CHAPTER_MAX, len(chapters))
        final_status = (
            config.CRAWL_STATUS_DONE
            if crawled_count >= total_to_crawl
            else config.CRAWL_STATUS_FAILED
        )
        update_book_crawl_status(book_id, final_status, chapter_count=crawled_count)

        if final_status == config.CRAWL_STATUS_DONE:
            update_task_status(task_id, config.TASK_STATUS_SUCCESS)
            add_book_log(book_id, f"采集完成: 成功{crawled_count}/{total_to_crawl}章",
                         source=platform)
        else:
            update_task_status(task_id, config.TASK_STATUS_FAILED,
                               error_msg=f"仅成功{crawled_count}/{total_to_crawl}章")
            add_book_log(book_id, f"采集部分完成: 成功{crawled_count}/{total_to_crawl}章",
                         source=platform)

    except Exception as e:
        err_msg = f"采集异常: {traceback.format_exc()}"
        update_task_status(task_id, config.TASK_STATUS_FAILED, error_msg=str(e))
        update_book_crawl_status(book_id, config.CRAWL_STATUS_FAILED)
        add_book_log(book_id, f"采集失败: {e}", source=platform, role="error")
    finally:
        if crawler:
            try:
                crawler.close_driver()
            except Exception:
                pass
