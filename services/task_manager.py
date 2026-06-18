"""任务管理器 —— 爬取任务的全生命周期管理"""
import config
from db_ops import *
from typing import Optional

# ==================== 任务创建 ====================

def create_rank_tasks(sources: list = None):
    """创建榜单爬取任务"""
    if sources is None:
        sources = list(config.PLATFORM_LABELS.keys())
    count = 0
    for src in sources:
        tid = create_task("crawl_rank", src, priority=config.TASK_PRIORITY["crawl_rank"])
        if tid:
            count += 1
    return count


def create_book_init_tasks(source: str):
    """创建榜单 → 书籍初始化任务（对每个平台生成的榜单书籍）"""
    books = get_distinct_books_from_rank(source)
    count = 0
    for b in books:
        tid = create_task("crawl_book", source, b["book_id"],
                          priority=config.TASK_PRIORITY["crawl_book"])
        if tid:
            count += 1
    return count


def create_chapter_tasks(source: str):
    """为指定平台待爬书籍创建章节爬取任务"""
    books = get_pending_crawl_books(source)
    count = 0
    for b in books:
        tid = create_task("crawl_chapter", source, b["book_id"],
                          priority=config.TASK_PRIORITY["crawl_chapter"])
        if tid:
            count += 1
    return count


# ==================== 任务执行 ====================

def mark_task_running(task_id: int):
    """标记任务为执行中"""
    update_task_status(task_id, config.TASK_STATUS_RUNNING)


def mark_task_success(task_id: int):
    """标记任务成功"""
    update_task_status(task_id, config.TASK_STATUS_SUCCESS)


def mark_task_failed(task_id: int, error_msg: str, retry_count: int = None):
    """标记任务失败"""
    if retry_count is None:
        # 读取当前重试次数并+1
        pass
    update_task_status(task_id, config.TASK_STATUS_FAILED,
                       retry_count=retry_count, error_msg=error_msg)


def mark_task_retry(task_id: int, current_retry: int, error_msg: str):
    """重试任务（重试次数+1，状态重置为待执行）"""
    new_retry = current_retry + 1
    if new_retry >= config.MAX_RETRIES:
        update_task_status(task_id, config.TASK_STATUS_FAILED,
                           retry_count=new_retry, error_msg=error_msg)
        return False
    update_task_status(task_id, config.TASK_STATUS_PENDING,
                       retry_count=new_retry, error_msg=error_msg)
    return True


# ==================== 每周刷新任务 ====================


def create_weekly_refresh_task(source: str) -> Optional[int]:
    """创建每周刷新任务"""
    return create_task(
        "rank_weekly_refresh", source,
        priority=config.TASK_PRIORITY.get("rank_weekly_refresh", 90)
    )


def get_weekly_refresh_tasks(limit: int = 10) -> list:
    """获取最近 N 次每周刷新任务记录"""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM crawl_tasks WHERE task_type='rank_weekly_refresh' "
            "ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
