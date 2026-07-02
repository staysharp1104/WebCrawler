"""
🔧 数据工具 Blueprint [新增]

API：
    POST /api/tools/verify-files      -> 文件完整性校验
        ?source=fanqie
        ?type=cover|chapter
    POST /api/tools/export            -> 批量导出数据
        { tables: ["books", "rank_books", "tasks"] }
        返回 xlsx 下载链接
"""
import os
import json
from flask import Blueprint, jsonify, request
from .common import query, query_one, DATA_DIR

bp = Blueprint("tools_api", __name__)


@bp.route("/tools/verify-files", methods=["POST"])
def api_verify_files():
    """文件完整性校验"""
    body = request.get_json() or {}
    source = body.get("source", "")
    verify_type = body.get("type", "chapter")  # chapter | cover

    if not source:
        return jsonify({"code": 1, "msg": "缺少 source 参数"})

    results = {
        "total": 0,
        "ok": 0,
        "missing": 0,
        "size_mismatch": 0,
        "errors": [],
    }

    if verify_type == "chapter":
        # 校验 chapters 表 content_path
        sql = "SELECT id, content_path, content_size FROM chapters WHERE source=%s"
        rows = query(sql, [source])
        results["total"] = len(rows)
        for r in rows:
            if not r["content_path"]:
                results["missing"] += 1
                results["errors"].append({
                    "id": r["id"], "type": "missing_path",
                    "path": r["content_path"],
                })
                continue
            full_path = os.path.join(DATA_DIR, r["content_path"])
            if not os.path.exists(full_path):
                results["missing"] += 1
                results["errors"].append({
                    "id": r["id"], "type": "file_not_found",
                    "path": r["content_path"],
                })
                continue
            actual_size = os.path.getsize(full_path)
            if r["content_size"] and actual_size != r["content_size"]:
                results["size_mismatch"] += 1
                results["errors"].append({
                    "id": r["id"], "type": "size_mismatch",
                    "path": r["content_path"],
                    "expected": r["content_size"],
                    "actual": actual_size,
                })
                continue
            results["ok"] += 1

    elif verify_type == "cover":
        # 校验 books 表 cover_path（封面）
        sql = "SELECT book_id, cover_path, source FROM books WHERE source=%s"
        rows = query(sql, [source])
        results["total"] = len(rows)
        for r in rows:
            if not r["cover_path"]:
                continue
            full_path = os.path.join(DATA_DIR, r["cover_path"])
            if not os.path.exists(full_path):
                results["missing"] += 1
                results["errors"].append({
                    "book_id": r["book_id"], "type": "cover_not_found",
                    "path": r["cover_path"],
                })
                continue
            results["ok"] += 1
        results["ok"] = results["total"] - results["missing"]

    else:
        return jsonify({"code": 1, "msg": f"不支持的校验类型: {verify_type}"})

    return jsonify({"code": 0, "data": results})


@bp.route("/tools/export", methods=["POST"])
def api_export():
    """批量导出数据为 xlsx"""
    body = request.get_json() or {}
    tables = body.get("tables", [])

    if not tables:
        return jsonify({"code": 1, "msg": "缺少 tables 参数"})

    try:
        import pandas as pd
    except ImportError:
        return jsonify({"code": 1, "msg": "服务端缺少 pandas 依赖"})

    try:
        import openpyxl  # noqa: F401
    except ImportError:
        return jsonify({"code": 1, "msg": "服务端缺少 openpyxl 依赖"})

    export_dir = os.path.join(DATA_DIR, "exports")
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(export_dir, "data_export.xlsx")

    table_map = {
        "books": "SELECT * FROM books",
        "rank_books": "SELECT * FROM rank_books",
        "tasks": "SELECT * FROM crawl_tasks",
        "chapters": "SELECT * FROM chapters",
    }

    with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
        for t in tables:
            if t not in table_map:
                continue
            rows = query(table_map[t])
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name=t, index=False)

    return jsonify({
        "code": 0,
        "data": {
            "path": export_path,
            "tables": tables,
            "message": f"已导出 {len(tables)} 个表到 {export_path}",
        }
    })
