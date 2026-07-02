"""
📚 书籍管理 Blueprint

迁入自 webapp.py：
    GET  /api/books           -> 书籍列表（分页+筛选）
    GET  /api/books/<book_id> -> 书籍详情（含章节统计）

新增：
    POST /api/books/parse     -> 解析链接（平台识别+去重校验）
    POST /api/books/import    -> 批量导入（1-50条URL）
    POST /api/books/batch     -> 批量操作（重试/导出/校验/RAG）
"""
from flask import Blueprint, jsonify, request
from .common import query, query_one, execute

from services.file_manager import download_cover
from services.links_service import parse_url, submit_link_collection
from db_ops import update_book_crawl_status, update_book_cover_path, create_task, add_book_log

bp = Blueprint("books_api", __name__)


PLATFORM_LABELS = {
    "qidian": "起点中文网", "fanqie": "番茄小说",
    "feilu": "飞卢小说", "qimao": "七猫小说",
}


@bp.route("/books")
def api_books():
    source = request.args.get("source", "")
    keyword = request.args.get("keyword", "")
    crawl_status = request.args.get("crawl_status", "")
    book_status = request.args.get("book_status", "")
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 20))
    offset = (page - 1) * size

    where = []
    params = []
    if source:
        where.append("source=%s")
        params.append(source)
    if keyword:
        where.append("(title LIKE %s OR author LIKE %s OR book_id LIKE %s)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    if crawl_status:
        where.append("crawl_status=%s")
        params.append(int(crawl_status))
    if book_status:
        where.append("status=%s")
        params.append(book_status)

    w_sql = "WHERE " + " AND ".join(where) if where else ""

    count_row = query_one(f"SELECT COUNT(*) AS cnt FROM books {w_sql}", params)
    total = count_row["cnt"] if count_row else 0

    sql = f"""SELECT * FROM books {w_sql}
              ORDER BY created_at DESC
              LIMIT %s OFFSET %s"""
    rows = query(sql, params + [size, offset])

    return jsonify({
        "code": 0,
        "data": {
            "list": rows,
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size if total > 0 else 0,
        }
    })


@bp.route("/books/<book_id>")
def api_book_detail(book_id):
    row = query_one("SELECT * FROM books WHERE book_id=%s", [book_id])
    if not row:
        return jsonify({"code": 1, "msg": "书籍不存在"})
    ch_row = query_one(
        "SELECT COUNT(*) AS cnt, SUM(content_size) AS total_size "
        "FROM chapters WHERE book_id=%s", [book_id]
    )
    row["chapter_count_real"] = ch_row["cnt"] if ch_row else 0
    row["chapter_size_total"] = ch_row["total_size"] if ch_row else 0
    return jsonify({"code": 0, "data": row})


@bp.route("/books/<book_id>/retry", methods=["POST"])
def api_book_retry(book_id):
    """整书重试：重置书爬取状态，下发新采集任务"""
    book = query_one("SELECT * FROM books WHERE book_id=%s", [book_id])
    if not book:
        return jsonify({"code": 1, "msg": "书籍不存在"})

    # 重置爬取状态
    update_book_crawl_status(book_id, 0)
    add_book_log(book_id, f"整书重试 - 由用户触发", source=book["source"])

    # 发任务
    tid = create_task("crawl_single_book", book["source"], target_id=book_id, priority=80)
    if tid:
        from services.links_service import _run_single_book
        import threading
        t = threading.Thread(
            target=_run_single_book,
            args=(tid, book["source"], book.get("book_url", ""), book_id),
            daemon=True,
        )
        t.start()
        return jsonify({"code": 0, "msg": "已重置并下发采集任务", "task_id": tid})
    return jsonify({"code": 1, "msg": "任务创建失败"})


@bp.route("/books/<book_id>/retry-cover", methods=["POST"])
def api_book_retry_cover(book_id):
    """封面重试：清除封面路径，重新下载"""
    book = query_one("SELECT * FROM books WHERE book_id=%s", [book_id])
    if not book:
        return jsonify({"code": 1, "msg": "书籍不存在"})

    cover_url = book.get("cover_url", "")
    if not cover_url:
        return jsonify({"code": 1, "msg": "无封面地址可重试"})

    try:
        cover_path = download_cover(cover_url, book_id, book["source"])
        if cover_path:
            update_book_cover_path(book_id, cover_path)
            add_book_log(book_id, "封面重试 - 下载成功", source=book["source"])
            return jsonify({"code": 0, "msg": "封面已重新下载", "cover_path": cover_path})
        else:
            return jsonify({"code": 1, "msg": "封面下载失败"})
    except Exception as e:
        return jsonify({"code": 1, "msg": f"封面重试异常: {e}"})


@bp.route("/books/<book_id>/snapshots")
def api_book_snapshots(book_id):
    """书籍榜单快照历史"""
    rows = query(
        "SELECT id, `rank`, source, category_label, created_at AS create_time "
        "FROM rank_books WHERE book_id=%s "
        "ORDER BY created_at DESC", [book_id]
    )
    return jsonify({"code": 0, "data": rows})
