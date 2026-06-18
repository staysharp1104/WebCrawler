"""数据库 CRUD 操作层 —— 对齐五张数据表"""
from typing import Optional
from database import get_connection

# ==================== 榜单操作 (rank_books) ====================


def _is_garbled(text: str) -> bool:
    """检测文本是否含字体加密乱码（Unicode 私用区字符 U+E000 ~ U+F8FF）"""
    if not text:
        return True
    return any(0xE000 <= ord(ch) <= 0xF8FF for ch in text)


def cleanup_garbled_rank_books(source: str) -> dict:
    """
    清理 rank_books 中指定平台的乱码记录（字体加密导致）。
    同时删除关联的 books 表中尚未开始爬取 (crawl_status=0) 的对应书籍。

    返回:
        {"rank_deleted": N, "books_deleted": N, "book_ids": [...]}
    """
    result = {"rank_deleted": 0, "books_deleted": 0, "book_ids": []}
    conn = get_connection()
    if not conn:
        return result
    try:
        cursor = conn.cursor(dictionary=True)

        # 1. 查找所有乱码记录
        cursor.execute(
            "SELECT id, book_id, title FROM rank_books WHERE source=%s",
            (source,)
        )
        rows = cursor.fetchall()
        garbled_ids = []
        garbled_book_ids = []
        for row in rows:
            if _is_garbled(row.get("title", "")):
                garbled_ids.append(row["id"])
                garbled_book_ids.append(row["book_id"])

        if not garbled_ids:
            print(f"  [DB] {source} 无乱码记录，无需清理")
            return result

        # 2. 删除 rank_books 中的乱码记录
        placeholders = ",".join(["%s"] * len(garbled_ids))
        cursor.execute(
            f"DELETE FROM rank_books WHERE id IN ({placeholders})",
            garbled_ids
        )
        result["rank_deleted"] = cursor.rowcount

        # 3. 删除 books 表中尚未开始爬取的对应记录 (crawl_status=0)
        book_placeholders = ",".join(["%s"] * len(garbled_book_ids))
        cursor.execute(
            f"DELETE FROM books WHERE book_id IN ({book_placeholders}) "
            f"AND source=%s AND crawl_status=0",
            garbled_book_ids + [source]
        )
        result["books_deleted"] = cursor.rowcount
        result["book_ids"] = garbled_book_ids

        conn.commit()
        print(f"  [DB] {source} 清理完成: "
              f"rank_books 删除 {result['rank_deleted']} 条, "
              f"books 删除 {result['books_deleted']} 条")
    except Exception as e:
        conn.rollback()
        print(f"  [DB] 清理乱码记录失败: {e}")
    finally:
        cursor.close()
        conn.close()
    return result

def insert_rank_book(data: dict) -> bool:
    """插入榜单数据（source+book_id 去重）"""
    sql = """INSERT IGNORE INTO rank_books
             (book_id, `rank`, title, author, book_url, description,
              status, reader_count, category_label, source, cover_url)
             VALUES (%(book_id)s, %(rank)s, %(title)s, %(author)s, %(book_url)s,
                     %(description)s, %(status)s, %(reader_count)s,
                     %(category_label)s, %(source)s, %(cover_url)s)"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(sql, data)
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"[DB] 插入榜单失败: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def batch_insert_rank_books(records: list) -> int:
    """批量插入榜单数据"""
    sql = """INSERT IGNORE INTO rank_books
             (book_id, `rank`, title, author, book_url, description,
              status, reader_count, category_label, source, cover_url)
             VALUES (%(book_id)s, %(rank)s, %(title)s, %(author)s, %(book_url)s,
                     %(description)s, %(status)s, %(reader_count)s,
                     %(category_label)s, %(source)s, %(cover_url)s)"""
    conn = get_connection()
    if not conn:
        return 0
    try:
        cursor = conn.cursor()
        cursor.executemany(sql, records)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        print(f"[DB] 批量插入榜单失败: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()


def get_distinct_books_from_rank(source: str) -> list:
    """从榜单中获取某平台的所有去重 book_id"""
    sql = "SELECT DISTINCT book_id, title, author, source, book_url, cover_url, description FROM rank_books WHERE source=%s"
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (source,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ==================== 书籍操作 (books) ====================

def insert_book(data: dict) -> bool:
    """插入书籍（book_id 为主键，REPLACE 实现去重更新）"""
    # 安全钳位：防止 MySQL int 溢出
    for key in ("total_chapters", "word_count", "chapter_count"):
        if key in data:
            try:
                v = int(data[key])
                if v < 0:
                    v = 0
                if v > 999999999:
                    v = 0
                data[key] = v
            except (ValueError, TypeError):
                data[key] = 0
    sql = """REPLACE INTO books
             (book_id, title, author, book_url, intro, category,
              word_count, status, source, chapter_count, total_chapters,
              crawl_status, cover_url, cover_path)
             VALUES (%(book_id)s, %(title)s, %(author)s, %(book_url)s, %(intro)s,
                     %(category)s, %(word_count)s, %(status)s, %(source)s,
                     %(chapter_count)s, %(total_chapters)s, %(crawl_status)s,
                     %(cover_url)s, %(cover_path)s)"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(sql, data)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB] 插入书籍失败: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def init_book_from_rank(rank_data: dict) -> bool:
    """从榜单数据初始化书籍到 books 表"""
    book = {
        "book_id": rank_data["book_id"],
        "title": rank_data.get("title", ""),
        "author": rank_data.get("author", ""),
        "book_url": rank_data.get("book_url", ""),
        "intro": rank_data.get("description", ""),
        "category": rank_data.get("category_label", ""),
        "word_count": 0,
        "status": rank_data.get("status", ""),
        "source": rank_data["source"],
        "chapter_count": 0,
        "total_chapters": 0,
        "crawl_status": 0,
        "cover_url": rank_data.get("cover_url", ""),
        "cover_path": "",
    }
    return insert_book(book)


def get_pending_crawl_books(source: Optional[str] = None) -> list:
    """获取待爬取章节的书籍列表"""
    sql = "SELECT * FROM books WHERE crawl_status=0"
    params = []
    if source:
        sql += " AND source=%s"
        params.append(source)
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def update_book_crawl_status(book_id: str, status: int, chapter_count: int = None):
    """更新书籍爬取状态"""
    sql = "UPDATE books SET crawl_status=%s"
    params = [status]
    if chapter_count is not None:
        sql += ", chapter_count=%s"
        params.append(chapter_count)
    sql += " WHERE book_id=%s"
    params.append(book_id)
    conn = get_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[DB] 更新书籍状态失败: {e}")
    finally:
        cursor.close()
        conn.close()


def update_book_cover_path(book_id: str, cover_path: str):
    """更新封面本地路径"""
    sql = "UPDATE books SET cover_path=%s WHERE book_id=%s"
    conn = get_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (cover_path, book_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


# ==================== 章节操作 (chapters) ====================

def insert_chapter(data: dict) -> bool:
    """插入章节（book_id+chapter_index 去重）"""
    sql = """INSERT IGNORE INTO chapters
             (book_id, chapter_index, chapter_title, chapter_url,
              content_path, content_size, source)
             VALUES (%(book_id)s, %(chapter_index)s, %(chapter_title)s,
                     %(chapter_url)s, %(content_path)s, %(content_size)s,
                     %(source)s)"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(sql, data)
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"[DB] 插入章节失败: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def count_chapters_by_book(book_id: str) -> int:
    """统计某本书已爬取章节数"""
    sql = "SELECT COUNT(*) FROM chapters WHERE book_id=%s"
    conn = get_connection()
    if not conn:
        return 0
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (book_id,))
        return cursor.fetchone()[0]
    finally:
        cursor.close()
        conn.close()


# ==================== 任务操作 (crawl_tasks) ====================

def create_task(task_type: str, source: str, target_id: str = "",
                priority: int = 0) -> Optional[int]:
    """创建爬取任务"""
    sql = """INSERT INTO crawl_tasks (task_type, source, target_id, status, priority)
             VALUES (%s, %s, %s, %s, %s)"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (task_type, source, target_id, 0, priority))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        conn.rollback()
        print(f"[DB] 创建任务失败: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_pending_tasks(task_type: str = None, source: str = None) -> list:
    """获取待执行任务"""
    sql = "SELECT * FROM crawl_tasks WHERE status=0"
    params = []
    if task_type:
        sql += " AND task_type=%s"
        params.append(task_type)
    if source:
        sql += " AND source=%s"
        params.append(source)
    sql += " ORDER BY priority DESC, created_at ASC"
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def update_task_status(task_id: int, status: int, retry_count: int = None,
                       error_msg: str = ""):
    """更新任务状态"""
    sql = "UPDATE crawl_tasks SET status=%s"
    params = [status]
    if retry_count is not None:
        sql += ", retry_count=%s"
        params.append(retry_count)
    if error_msg:
        sql += ", error_msg=%s"
        params.append(error_msg)
    sql += " WHERE id=%s"
    params.append(task_id)
    conn = get_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
    except Exception as e:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


# ==================== 辅助日志 (chat_history) ====================

def add_book_log(book_id: str, content: str, source: str = "", role: str = "system"):
    """添加书籍辅助日志"""
    sql = """INSERT INTO chat_history (book_id, role, content, source)
             VALUES (%s, %s, %s, %s)"""
    conn = get_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (book_id, role, content, source))
        conn.commit()
    except Exception as e:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


# ==================== 定时任务配置 (scheduler_config) ====================


def get_scheduler_config() -> dict:
    """获取定时任务配置"""
    conn = get_connection()
    if not conn:
        return {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM scheduler_config WHERE id=1")
        row = cursor.fetchone()
        return row or {}
    except Exception:
        return {}
    finally:
        cursor.close()
        conn.close()


def update_scheduler_config(data: dict) -> bool:
    """更新定时任务配置"""
    sql = """UPDATE scheduler_config SET
             cron_expr=%s, enabled=%s, weekday=%s, hour=%s, minute=%s
             WHERE id=1"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (
            data.get("cron_expr", "0 2 * * 0"),
            int(data.get("enabled", 1)),
            int(data.get("weekday", 0)),
            int(data.get("hour", 2)),
            int(data.get("minute", 0)),
        ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB] 更新定时配置失败: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def update_scheduler_run_result(status: str, summary: str = ""):
    """更新定时任务执行结果"""
    sql = """UPDATE scheduler_config SET
             last_run_at=NOW(), next_run_at=NOW(),
             last_run_status=%s, last_run_summary=%s
             WHERE id=1"""
    conn = get_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (status, summary))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def get_book_exists(book_id: str) -> bool:
    """检查书籍是否已存在于 books 表"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM books WHERE book_id=%s LIMIT 1", (book_id,))
        return cursor.fetchone() is not None
    except Exception:
        return False
    finally:
        cursor.close()
        conn.close()


def update_book_info_from_rank(rank_data: dict) -> bool:
    """仅更新书籍信息字段，不改动 crawl_status/chapter_count"""
    sql = """UPDATE books SET
             title=%s, author=%s, book_url=%s, intro=%s,
             category=%s, status=%s, cover_url=%s
             WHERE book_id=%s"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (
            rank_data.get("title", ""),
            rank_data.get("author", ""),
            rank_data.get("book_url", ""),
            rank_data.get("description", ""),
            rank_data.get("category_label", ""),
            rank_data.get("status", ""),
            rank_data.get("cover_url", ""),
            rank_data.get("book_id", ""),
        ))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()
