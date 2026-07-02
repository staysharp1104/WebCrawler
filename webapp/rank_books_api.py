"""
📋 榜单快照 Blueprint

迁入自 webapp.py：
    GET  /api/rank-books      -> 榜单列表（分页+筛选）

新增：
    GET  /api/rank-books/export -> 榜单导出 xlsx
"""
from flask import Blueprint, jsonify, request
from .common import query, query_one

bp = Blueprint("rank_books_api", __name__)


@bp.route("/rank-books")
def api_rank_books():
    source = request.args.get("source", "")
    keyword = request.args.get("keyword", "")
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 20))
    offset = (page - 1) * size

    where = []
    params = []
    if source:
        where.append("r.source=%s")
        params.append(source)
    if keyword:
        where.append("(r.title LIKE %s OR r.author LIKE %s)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])

    w_sql = "WHERE " + " AND ".join(where) if where else ""

    count_row = query_one(f"SELECT COUNT(*) AS cnt FROM rank_books r {w_sql}", params)
    total = count_row["cnt"] if count_row else 0

    sql = f"""SELECT r.*, b.crawl_status AS book_crawl_status, b.chapter_count, b.total_chapters
              FROM rank_books r
              LEFT JOIN books b ON r.book_id = b.book_id
              {w_sql}
              ORDER BY r.source, r.created_at DESC, r.id
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

# TODO: 新增 GET /api/rank-books/export
