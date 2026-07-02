"""
⚙️ 任务调度 Blueprint

迁入自 webapp.py：
    GET  /api/tasks                   -> 任务列表（分页+筛选）
    POST /api/tasks/<id>/retry        -> 任务重试

新增：
    POST /api/tasks/<id>/stop         -> 终止执行中任务
"""
from flask import Blueprint, jsonify, request
from .common import query, query_one, execute

bp = Blueprint("tasks_api", __name__)


@bp.route("/tasks")
def api_tasks():
    task_type = request.args.get("task_type", "")
    source = request.args.get("source", "")
    status = request.args.get("status", "")
    keyword = request.args.get("keyword", "")
    priority = request.args.get("priority", "")
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 20))
    offset = (page - 1) * size

    where = []
    params = []
    if task_type:
        where.append("task_type=%s")
        params.append(task_type)
    if source:
        where.append("source=%s")
        params.append(source)
    if status:
        where.append("status=%s")
        params.append(int(status))
    if priority:
        where.append("priority=%s")
        params.append(int(priority))
    if keyword:
        where.append("(target_id LIKE %s OR error_msg LIKE %s)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])

    w_sql = "WHERE " + " AND ".join(where) if where else ""

    count_row = query_one(f"SELECT COUNT(*) AS cnt FROM crawl_tasks {w_sql}", params)
    total = count_row["cnt"] if count_row else 0

    sql = f"""SELECT * FROM crawl_tasks {w_sql}
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


@bp.route("/tasks/<int:task_id>/retry", methods=["POST"])
def api_retry_task(task_id):
    """重置任务状态为待执行"""
    row = query_one("SELECT * FROM crawl_tasks WHERE id=%s", [task_id])
    if not row:
        return jsonify({"code": 1, "msg": "任务不存在"})
    new_retry = (row["retry_count"] or 0) + 1
    execute(
        "UPDATE crawl_tasks SET status=0, retry_count=%s WHERE id=%s",
        [new_retry, task_id]
    )
    return jsonify({"code": 0, "msg": "任务已重置"})
