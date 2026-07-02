"""
📄 系统日志 Blueprint [新增]

API：
    GET  /api/logs                    -> 操作日志列表
        ?book_id=     按书籍筛选
        ?source=      按平台筛选
        ?start_time=  按时间范围筛选
        ?end_time=
        ?role=        按角色筛选 (system/user)

数据源：复用 chat_history 表
"""
from flask import Blueprint, jsonify, request
from .common import query, query_one

bp = Blueprint("logs_api", __name__)


@bp.route("/logs")
def api_logs():
    book_id = request.args.get("book_id", "")
    source = request.args.get("source", "")
    role = request.args.get("role", "")
    start_time = request.args.get("start_time", "")
    end_time = request.args.get("end_time", "")
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 20))
    offset = (page - 1) * size

    where = []
    params = []
    if book_id:
        where.append("book_id=%s")
        params.append(book_id)
    if source:
        where.append("source=%s")
        params.append(source)
    if role:
        where.append("role=%s")
        params.append(role)
    if start_time:
        where.append("create_time >= %s")
        params.append(start_time)
    if end_time:
        where.append("create_time <= %s")
        params.append(end_time)

    w_sql = "WHERE " + " AND ".join(where) if where else ""

    count_row = query_one(
        f"SELECT COUNT(*) AS cnt FROM chat_history {w_sql}", params
    )
    total = count_row["cnt"] if count_row else 0

    sql = f"""SELECT * FROM chat_history {w_sql}
              ORDER BY create_time DESC
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
