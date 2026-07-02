"""
🕐 定时任务配置 Blueprint

迁入自 webapp.py：
    GET  /api/scheduler/config        -> 获取定时配置
    POST /api/scheduler/config        -> 更新定时配置（含调度器重启）
    POST /api/scheduler/trigger       -> 手动触发每周刷新
    GET  /api/scheduler/history       -> 最近10次执行记录
"""
import threading
from flask import Blueprint, jsonify, request
from .common import query_one
from webapp import scheduler, scheduler_started, init_scheduler, _run_weekly_refresh_background

bp = Blueprint("scheduler_api", __name__)


@bp.route("/scheduler/config", methods=["GET"])
def api_get_scheduler_config():
    """获取定时任务配置"""
    from db_ops import get_scheduler_config
    cfg = get_scheduler_config()
    return jsonify({"code": 0, "data": cfg})


@bp.route("/scheduler/config", methods=["POST"])
def api_update_scheduler_config():
    """更新定时任务配置"""
    from db_ops import update_scheduler_config
    data = request.get_json()
    if not data:
        return jsonify({"code": 1, "msg": "参数为空"})
    ok = update_scheduler_config(data)
    if ok:
        # 重启调度器
        if scheduler_started:
            scheduler.remove_all_jobs()
        import webapp
        webapp.scheduler_started = False
        init_scheduler()
        return jsonify({"code": 0, "msg": "配置已更新"})
    return jsonify({"code": 1, "msg": "更新失败"})


@bp.route("/scheduler/trigger", methods=["POST"])
def api_trigger_weekly_refresh():
    """手动触发每周榜单刷新"""
    t = threading.Thread(target=_run_weekly_refresh_background, daemon=True)
    t.start()
    return jsonify({"code": 0, "msg": "每周刷新任务已启动"})


@bp.route("/scheduler/history")
def api_scheduler_history():
    """获取最近 10 次每周刷新记录"""
    from services.task_manager import get_weekly_refresh_tasks
    rows = get_weekly_refresh_tasks(10)
    return jsonify({"code": 0, "data": rows})
