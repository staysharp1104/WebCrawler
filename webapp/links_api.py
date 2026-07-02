"""
链接驱动采集 Blueprint

负责：
    POST /api/links/parse      -> 批量解析 URL（平台识别+去重校验）
    POST /api/links/submit     -> 提交解析项，下发采集任务
    GET  /api/links/tasks      -> 单书采集任务列表
    GET  /api/links/tasks/<id> -> 单任务详情+进度
    GET  /api/links/tasks/<id>/log -> 实时采集日志
"""
from flask import Blueprint, jsonify, request
from .common import query, query_one
from services.links_service import parse_urls, submit_link_collection

bp = Blueprint("links_api", __name__)


@bp.route("/links/parse", methods=["POST"])
def api_links_parse():
    """批量解析 URL"""
    data = request.get_json(force=True)
    urls = data.get("urls", [])
    if not urls or not isinstance(urls, list):
        return jsonify({"code": 1, "msg": "请提供 urls 列表"})
    if len(urls) > 50:
        return jsonify({"code": 1, "msg": "单次最多解析 50 条"})

    results = parse_urls(urls)
    return jsonify({"code": 0, "data": results})


@bp.route("/links/submit", methods=["POST"])
def api_links_submit():
    """提交解析项，下发采集任务"""
    data = request.get_json(force=True)
    items = data.get("items", [])
    if not items or not isinstance(items, list):
        return jsonify({"code": 1, "msg": "请提供 items 列表"})
    if len(items) > 50:
        return jsonify({"code": 1, "msg": "单次最多提交 50 条"})

    # 校验每个 item 的必填字段
    valid_items = []
    for item in items:
        if item.get("book_id") and item.get("platform") and item.get("url"):
            valid_items.append(item)

    if not valid_items:
        return jsonify({"code": 1, "msg": "无有效采集项"})

    task_ids = submit_link_collection(valid_items)
    return jsonify({
        "code": 0,
        "data": {
            "task_ids": task_ids,
            "count": len(task_ids),
        }
    })


@bp.route("/links/tasks")
def api_links_tasks():
    """单书采集任务列表（分页）"""
    source = request.args.get("source", "")
    status = request.args.get("status", "")
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 20))
    offset = (page - 1) * size

    where = ["task_type='crawl_single_book'"]
    params = []
    if source:
        where.append("source=%s")
        params.append(source)
    if status:
        where.append("status=%s")
        params.append(int(status))

    w_sql = "WHERE " + " AND ".join(where)

    count_row = query_one(
        f"SELECT COUNT(*) AS cnt FROM crawl_tasks {w_sql}", params
    )
    total = count_row["cnt"] if count_row else 0

    sql = f"""SELECT t.*, b.title AS book_title, b.author AS book_author,
                     b.chapter_count, b.crawl_status AS book_crawl_status
              FROM crawl_tasks t
              LEFT JOIN books b ON t.target_id = b.book_id
              {w_sql}
              ORDER BY t.created_at DESC
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


@bp.route("/links/tasks/<int:task_id>")
def api_links_task_detail(task_id):
    """单任务详情 + 关联书籍 + 章节进度"""
    task = query_one(
        "SELECT t.*, b.title AS book_title, b.author AS book_author, "
        "b.intro, b.category, b.word_count, b.status AS book_status, "
        "b.cover_path, b.chapter_count, b.crawl_status AS book_crawl_status "
        "FROM crawl_tasks t "
        "LEFT JOIN books b ON t.target_id = b.book_id "
        "WHERE t.id=%s", [task_id]
    )
    if not task:
        return jsonify({"code": 1, "msg": "任务不存在"})

    # 关联章节
    book_id = task.get("target_id")
    chapters = []
    if book_id:
        chapters = query(
            "SELECT id, chapter_index, chapter_title, chapter_url, "
            "content_path, content_size FROM chapters "
            "WHERE book_id=%s ORDER BY chapter_index", [book_id]
        )

    return jsonify({
        "code": 0,
        "data": {
            "task": task,
            "chapters": chapters,
        }
    })


@bp.route("/links/tasks/<int:task_id>/log")
def api_links_task_log(task_id):
    """实时采集日志（按 task 关联的 book_id 从 chat_history 查询）"""
    task = query_one("SELECT target_id FROM crawl_tasks WHERE id=%s", [task_id])
    if not task:
        return jsonify({"code": 1, "msg": "任务不存在"})

    book_id = task.get("target_id")
    if not book_id:
        return jsonify({"code": 0, "data": []})

    logs = query(
        "SELECT id, role, content, source, create_time "
        "FROM chat_history WHERE book_id=%s "
        "ORDER BY id ASC", [book_id]
    )
    return jsonify({"code": 0, "data": logs})
