"""
📝 章节数据 Blueprint

迁入自 webapp.py：
    GET  /api/chapters                -> 章节列表（分页+筛选）
    GET  /api/chapters/<id>/content   -> 章节正文（读取txt文件）

新增：
    POST /api/chapters/<id>/retry     -> 单章重爬
"""
import os
from flask import Blueprint, jsonify, request
from .common import query, query_one, execute, DATA_DIR

bp = Blueprint("chapters_api", __name__)


@bp.route("/chapters")
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


@bp.route("/chapters/<int:ch_id>/content")
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


@bp.route("/chapters/<int:ch_id>/retry", methods=["POST"])
def api_chapter_retry(ch_id):
    """单章重爬：删除章节文件和记录，供重新采集"""
    row = query_one("SELECT id, content_path, book_id FROM chapters WHERE id=%s", [ch_id])
    if not row:
        return jsonify({"code": 1, "msg": "章节不存在"})

    book_id = row["book_id"]
    content_path = row.get("content_path", "")

    # 删除文件
    if content_path:
        import os
        from .common import DATA_DIR
        fpath = os.path.join(DATA_DIR, content_path)
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
        except Exception:
            pass

    # 删除数据库记录
    execute("DELETE FROM chapters WHERE id=%s", [ch_id])

    # 更新书籍已爬章节数
    ch_count = query_one(
        "SELECT COUNT(*) AS cnt FROM chapters WHERE book_id=%s", [book_id]
    )
    cnt = ch_count["cnt"] if ch_count else 0
    execute(
        "UPDATE books SET chapter_count=%s, crawl_status=0 WHERE book_id=%s",
        [cnt, book_id]
    )

    return jsonify({"code": 0, "msg": "章节已删除，书籍已重置为待采集"})
