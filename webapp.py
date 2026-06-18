"""
小说爬虫数据可视化看板 — Flask 后端 API 服务

启动方式:
    python webapp.py          # 默认 127.0.0.1:5000
    python webapp.py --port 8080   # 自定义端口

访问:
    http://127.0.0.1:5000/     # 前端看板页面
"""
import argparse
import json
import os
from flask import Flask, jsonify, request, render_template
from database import get_connection

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ================================================================
# DB 查询辅助
# ================================================================

def query(sql: str, params=None, dictionary=True):
    """执行查询，返回 dict 列表"""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=dictionary)
        cur.execute(sql, params or [])
        rows = cur.fetchall()
        return rows
    finally:
        cur.close()
        conn.close()


def query_one(sql: str, params=None):
    """执行查询，返回单条 dict"""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=None):
    """执行写入操作"""
    conn = get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        conn.commit()
        return cur.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


# ================================================================
# API: 统计概览
# ================================================================

@app.route("/api/stats")
def api_stats():
    """核心统计数据"""
    data = {}

    # 总爬取书籍数
    row = query_one("SELECT COUNT(*) AS cnt FROM books")
    data["total_books"] = row["cnt"] if row else 0

    # 各平台书籍数
    rows = query("SELECT source, COUNT(*) AS cnt FROM books GROUP BY source")
    data["books_by_source"] = {r["source"]: r["cnt"] for r in rows}

    # 已完成爬取的书籍数
    row = query_one("SELECT COUNT(*) AS cnt FROM books WHERE crawl_status=2")
    data["completed_books"] = row["cnt"] if row else 0

    # 失败书籍数
    row = query_one("SELECT COUNT(*) AS cnt FROM books WHERE crawl_status=3")
    data["failed_books"] = row["cnt"] if row else 0

    # 总章节数
    row = query_one("SELECT COUNT(*) AS cnt FROM chapters")
    data["total_chapters"] = row["cnt"] if row else 0

    # 不同章节存储大小
    row = query_one("SELECT SUM(content_size) AS total_size FROM chapters")
    data["total_chapter_size"] = row["total_size"] if row and row["total_size"] else 0

    # 失败任务数
    row = query_one("SELECT COUNT(*) AS cnt FROM crawl_tasks WHERE status=3")
    data["failed_tasks"] = row["cnt"] if row else 0

    # 榜单数据总数
    row = query_one("SELECT COUNT(*) AS cnt FROM rank_books")
    data["total_rankings"] = row["cnt"] if row else 0

    return jsonify({"code": 0, "data": data})


# ================================================================
# API: 榜单数据 (rank_books)
# ================================================================

@app.route("/api/rank-books")
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


# ================================================================
# API: 书籍数据 (books)
# ================================================================

@app.route("/api/books")
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


@app.route("/api/books/<book_id>")
def api_book_detail(book_id):
    row = query_one("SELECT * FROM books WHERE book_id=%s", [book_id])
    if not row:
        return jsonify({"code": 1, "msg": "书籍不存在"})
    # 章节统计
    ch_row = query_one("SELECT COUNT(*) AS cnt, SUM(content_size) AS total_size FROM chapters WHERE book_id=%s", [book_id])
    row["chapter_count_real"] = ch_row["cnt"] if ch_row else 0
    row["chapter_size_total"] = ch_row["total_size"] if ch_row else 0
    return jsonify({"code": 0, "data": row})


# ================================================================
# API: 章节数据 (chapters)
# ================================================================

@app.route("/api/chapters")
def api_chapters():
    source = request.args.get("source", "")
    book_id = request.args.get("book_id", "")
    keyword = request.args.get("keyword", "")
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 30))
    offset = (page - 1) * size

    where = []
    params = []
    if source:
        where.append("ch.source=%s")
        params.append(source)
    if book_id:
        where.append("ch.book_id=%s")
        params.append(book_id)
    if keyword:
        where.append("ch.chapter_title LIKE %s")
        params.append(f"%{keyword}%")

    w_sql = "WHERE " + " AND ".join(where) if where else ""

    count_row = query_one(
        f"SELECT COUNT(*) AS cnt FROM chapters ch {w_sql}", params
    )
    total = count_row["cnt"] if count_row else 0

    sql = f"""SELECT ch.*, b.title AS book_title, b.author AS book_author
              FROM chapters ch
              LEFT JOIN books b ON ch.book_id = b.book_id
              {w_sql}
              ORDER BY ch.book_id, ch.chapter_index
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


@app.route("/api/chapters/<int:ch_id>/content")
def api_chapter_content(ch_id):
    """读取章节正文文件内容"""
    row = query_one("SELECT content_path, book_id FROM chapters WHERE id=%s", [ch_id])
    if not row or not row["content_path"]:
        return jsonify({"code": 1, "msg": "章节或文件不存在"})
    filepath = os.path.join(DATA_DIR, row["content_path"])
    if not os.path.exists(filepath):
        return jsonify({"code": 1, "msg": "正文文件不存在"})
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"code": 0, "data": {"content": content, "book_id": row["book_id"]}})
    except Exception as e:
        return jsonify({"code": 1, "msg": f"读取失败: {e}"})


# ================================================================
# API: 任务数据 (crawl_tasks)
# ================================================================

@app.route("/api/tasks")
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


@app.route("/api/tasks/<int:task_id>/retry", methods=["POST"])
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


# ================================================================
# 前端页面
# ================================================================

@app.route("/")
def index():
    return render_template("dashboard.html")


# ================================================================
# 启动
# ================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="爬虫数据看板")
    parser.add_argument("--port", "-p", type=int, default=5000, help="端口号")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址")
    args = parser.parse_args()
    print(f"📊 爬虫数据看板启动: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True)
