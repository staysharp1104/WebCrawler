"""
前端页面路由 Blueprint

迁入自原 webapp.py：
- /              -> dashboard.html
- /scheduler     -> scheduler.html
"""
from flask import Blueprint, render_template
from .common import query_one

bp = Blueprint("pages", __name__)


@bp.route("/")
def index():
    return render_template("dashboard.html")


@bp.route("/collect")
def collect_page():
    """链接驱动采集首页"""
    return render_template("collect.html")


@bp.route("/book/<book_id>")
def book_detail_page(book_id):
    """书籍详情页"""
    return render_template("book_detail.html", book_id=book_id)


@bp.route("/scheduler")
def scheduler_page():
    """定时任务配置页面"""
    return render_template("scheduler.html")
