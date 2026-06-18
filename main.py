"""
多平台小说榜单及章节爬取系统 — 主入口

用法：
    python main.py --help              查看帮助
    python main.py rank-only           仅爬取榜单
    python main.py chapter-only        仅爬取章节
    python main.py                     全流程执行
    python main.py --source fanqie     指定平台
"""
import argparse
import time
import traceback
import config
from services.file_manager import ensure_dirs, save_chapter_content
from services.task_manager import *
from db_ops import *
from crawlers.fanqie import FanqieCrawler
from crawlers.feilu import FeiluCrawler
from crawlers.qimao import QimaoCrawler
from crawlers.qidian import QidianCrawler

# 爬虫映射
CRAWLER_MAP = {
    "fanqie": FanqieCrawler,
    "feilu": FeiluCrawler,
    "qimao": QimaoCrawler,
    "qidian": QidianCrawler,
}


def get_crawler(source: str):
    cls = CRAWLER_MAP.get(source)
    if cls:
        return cls()
    raise ValueError(f"未知平台: {source}")


# ==================== 步骤一：爬取榜单 ====================

def step_crawl_rank(sources: list):
    """爬取所有平台的新书榜榜单数据"""
    print("\n" + "=" * 60)
    print("🚀 Step 1: 爬取榜单数据")
    print("=" * 60)
    for src in sources:
        print(f"\n--- 平台: {config.PLATFORM_LABELS.get(src, src)} ---")
        try:
            crawler = get_crawler(src)
            records = crawler.crawl_rankings()
            if records:
                inserted = batch_insert_rank_books(records)
                print(f"  ✅ 榜单数据入库 {inserted}/{len(records)} 条 (已去重)")
                # 写入日志
                for r in records[:5]:
                    add_book_log(r["book_id"],
                                 f"榜单爬取: {r['category_label']} 排名 {r['rank']}",
                                 source=src)
            else:
                print(f"  ⚠️ 未获取到榜单数据")
            crawler.close_driver()
        except Exception as e:
            print(f"  ❌ 平台 {src} 爬取失败: {e}")
            traceback.print_exc()
    print("\n✅ Step 1 完成")


# ==================== 清理乱码记录 ====================

def step_clean_garbled(sources: list):
    """清理 rank_books 中字体加密导致的乱码记录"""
    print("\n" + "=" * 60)
    print("🧹 清理乱码记录")
    print("=" * 60)
    from db_ops import cleanup_garbled_rank_books
    total_rank = 0
    total_books = 0
    for src in sources:
        print(f"\n--- 平台: {config.PLATFORM_LABELS.get(src, src)} ---")
        result = cleanup_garbled_rank_books(src)
        total_rank += result["rank_deleted"]
        total_books += result["books_deleted"]
    print(f"\n✅ 清理完成: rank_books 删除 {total_rank} 条, books 删除 {total_books} 条")


# ==================== 步骤二：榜单→书籍初始化 ====================

def step_init_books(sources: list):
    """从榜单数据中提取书籍信息初始化到 books 表"""
    print("\n" + "=" * 60)
    print("📚 Step 2: 初始化书籍信息")
    print("=" * 60)
    total = 0
    for src in sources:
        books = get_distinct_books_from_rank(src)
        for b in books:
            ok = init_book_from_rank(b)
            if ok:
                total += 1
        print(f"  [{src}] 初始化 {len(books)} 本书")
        # 创建书籍爬取任务
        task_count = create_book_init_tasks(src)
        print(f"  [{src}] 创建 {task_count} 个书籍详情爬取任务")
    print(f"\n✅ Step 2 完成，共初始化 {total} 本书")


# ==================== 步骤三：爬取书籍详情 ====================

def step_crawl_books(sources: list):
    """爬取榜单中每本书的详细信息"""
    print("\n" + "=" * 60)
    print("📖 Step 3: 爬取书籍详细信息")
    print("=" * 60)
    tasks = get_pending_tasks("crawl_book")
    if not tasks:
        print("  无待处理的书籍详情爬取任务")
        return

    for t in tasks:
        src = t["source"]
        book_id = t["target_id"]
        task_id = t["id"]
        if src not in sources:
            continue
        print(f"\n  爬取书籍详情: [{src}] {book_id}")
        mark_task_running(task_id)

        # 从 rank_books 获取 book_url
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT book_url FROM rank_books WHERE book_id=%s AND source=%s LIMIT 1",
                       (book_id, src))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row or not row["book_url"]:
            mark_task_failed(task_id, "未找到 book_url")
            add_book_log(book_id, "书籍详情爬取失败: 未找到 book_url", src)
            continue

        try:
            crawler = get_crawler(src)
            info = crawler.crawl_book_info(row["book_url"])
            if info.get("book_id"):
                info["source"] = src
                info["crawl_status"] = config.CRAWL_STATUS_PENDING
                info["chapter_count"] = 0
                info.setdefault("cover_path", "")
                info.setdefault("intro", "")
                info.setdefault("category", "")
                insert_book(info)
                mark_task_success(task_id)
                add_book_log(book_id, "书籍详情爬取成功", src)
                # 创建章节爬取任务
                create_task("crawl_chapter", src, book_id,
                            priority=config.TASK_PRIORITY["crawl_chapter"])
            else:
                mark_task_failed(task_id, "书籍信息解析为空")
            crawler.close_driver()
        except Exception as e:
            mark_task_failed(task_id, str(e))
            add_book_log(book_id, f"书籍详情爬取异常: {e}", src)
            print(f"    ❌ 错误: {e}")
        time.sleep(config.BETWEEN_BOOK_DELAY)
    print("\n✅ Step 3 完成")


# ==================== 步骤四：爬取章节 ====================

def step_crawl_chapters(sources: list):
    """爬取每本书前10章内容"""
    print("\n" + "=" * 60)
    print("📝 Step 4: 爬取章节内容")
    print("=" * 60)
    ensure_dirs()

    books = get_pending_crawl_books()
    books = [b for b in books if b["source"] in sources]
    print(f"  待爬取书籍数: {len(books)}")

    for book in books:
        book_id = book["book_id"]
        src = book["source"]
        book_url = book.get("book_url", "")
        print(f"\n  [{src}] 爬取章节: {book['title']} ({book_id})")

        # 更新状态为爬取中
        update_book_crawl_status(book_id, config.CRAWL_STATUS_RUNNING)
        add_book_log(book_id, "开始爬取章节", src)

        try:
            crawler = get_crawler(src)

            # 获取章节列表
            chapters = crawler.crawl_chapter_list(book_url)
            if not chapters:
                print(f"    ⚠️ 未获取到章节列表")
                update_book_crawl_status(book_id, config.CRAWL_STATUS_FAILED)
                add_book_log(book_id, "章节列表获取失败", src)
                crawler.close_driver()
                continue

            # 只取前10章
            chapters = chapters[:config.CHAPTER_MAX]
            success_count = 0

            for idx, ch_title, ch_url in chapters:
                print(f"    📄 第{idx}章: {ch_title}")
                try:
                    content = crawler.crawl_chapter_content(ch_url)
                    if not content or len(content) < 50:
                        print(f"      ⚠️ 内容过短或为空(可能是付费章)")
                        continue

                    # 保存文件
                    file_info = save_chapter_content(book_id, idx, content)

                    # 入库
                    ch_data = {
                        "book_id": book_id,
                        "chapter_index": idx,
                        "chapter_title": ch_title,
                        "chapter_url": ch_url,
                        "content_path": file_info["content_path"],
                        "content_size": file_info["content_size"],
                        "source": src,
                    }
                    inserted = insert_chapter(ch_data)
                    if inserted:
                        success_count += 1
                except Exception as e:
                    print(f"      ❌ 第{idx}章爬取失败: {e}")

                time.sleep(config.BETWEEN_CHAPTER_DELAY)

            # 更新书籍状态
            update_book_crawl_status(book_id, config.CRAWL_STATUS_DONE, success_count)
            add_book_log(book_id, f"章节爬取完成: 成功{success_count}/{len(chapters)}章", src)
            print(f"    ✅ 完成: 成功 {success_count}/{len(chapters)} 章")

            crawler.close_driver()

        except Exception as e:
            print(f"    ❌ 书籍章节爬取异常: {e}")
            update_book_crawl_status(book_id, config.CRAWL_STATUS_FAILED)
            add_book_log(book_id, f"章节爬取异常: {e}", src)

        time.sleep(config.BETWEEN_BOOK_DELAY)

    print("\n✅ Step 4 完成")


# ==================== 步骤五：下载封面 ====================

def step_download_covers(sources: list):
    """下载书籍封面到本地"""
    print("\n" + "=" * 60)
    print("🖼️ Step 5: 下载封面图片")
    print("=" * 60)
    ensure_dirs()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT book_id, cover_url, source FROM books WHERE cover_url!='' AND (cover_path='' OR cover_path IS NULL)")
    books = cursor.fetchall()
    cursor.close()
    conn.close()

    from services.file_manager import download_cover
    for b in books:
        if b["source"] not in sources:
            continue
        path = download_cover(b["cover_url"], b["book_id"], b["source"])
        if path:
            update_book_cover_path(b["book_id"], path)
            print(f"  ✅ 封面已保存: {b['book_id']} -> {path}")
        time.sleep(0.5)

    print("\n✅ Step 5 完成")


# ==================== 主流程 ====================

def run_full_pipeline(sources: list):
    """全流程执行"""
    start = time.time()
    print("=" * 60)
    print("📊 多平台小说榜单及章节爬取系统")
    print(f"   目标平台: {', '.join(config.PLATFORM_LABELS.get(s,s) for s in sources)}")
    print("=" * 60)

    # Step 1: 创建爬取任务
    task_count = create_rank_tasks(sources)
    print(f"\n已创建 {task_count} 个榜单爬取任务")

    # Step 2-6: 顺序执行
    step_crawl_rank(sources)
    step_clean_garbled(sources)
    step_init_books(sources)
    step_crawl_books(sources)
    step_crawl_chapters(sources)
    step_download_covers(sources)

    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"🎉 全流程执行完毕! 耗时: {elapsed:.1f}s")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="多平台小说榜单及章节爬取系统")
    parser.add_argument("--source", "-s", nargs="+",
                        choices=["fanqie", "feilu", "qimao", "qidian", "all"],
                        default=["all"],
                        help="目标平台 (默认 all)")
    parser.add_argument("--rank-only", action="store_true", help="仅执行榜单爬取")
    parser.add_argument("--book-only", action="store_true", help="仅执行书籍详情爬取")
    parser.add_argument("--chapter-only", action="store_true", help="仅执行章节爬取")
    parser.add_argument("--cover-only", action="store_true", help="仅执行封面下载")
    parser.add_argument("--init-only", action="store_true", help="仅执行榜单→书籍初始化")
    parser.add_argument("--clean-garbled", action="store_true",
                        help="清理 rank_books 中字体加密乱码记录")

    args = parser.parse_args()
    sources = list(config.PLATFORM_LABELS.keys()) if "all" in args.source else args.source

    if args.rank_only:
        step_crawl_rank(sources)
    elif args.book_only:
        step_crawl_books(sources)
    elif args.chapter_only:
        step_crawl_chapters(sources)
    elif args.cover_only:
        step_download_covers(sources)
    elif args.init_only:
        step_init_books(sources)
    elif args.clean_garbled:
        step_clean_garbled(sources)
    else:
        run_full_pipeline(sources)


if __name__ == "__main__":
    main()
