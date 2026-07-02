"""
Flask 应用工厂 + APScheduler 集成

职责：
- create_app()：应用工厂，注册 Blueprints、API 路由、初始化调度器
- APScheduler 初始化：init_scheduler()
- /api/stats：App 级别的核心统计 API（不归入任一 Blueprint）
"""
import os
import threading

from flask import Flask, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .common import query, query_one, execute

scheduler = BackgroundScheduler()
scheduler_started = False


def _run_weekly_refresh_background():
    """后台线程执行每周刷新（避免阻塞 Flask）"""
    from main import step_weekly_refresh
    import config
    try:
        sources = list(config.PLATFORM_LABELS.keys())
        step_weekly_refresh(sources)
    except Exception as e:
        print(f"[Scheduler] 每周刷新异常: {e}")


def init_scheduler():
    """根据数据库配置初始化 APScheduler"""
    global scheduler_started
    if scheduler_started:
        return
    try:
        from db_ops import get_scheduler_config
        cfg = get_scheduler_config()
        if not cfg or not cfg.get("enabled"):
            print("[Scheduler] 定时任务未启用")
            return
        cron = cfg.get("cron_expr", "0 2 * * 0")
        trigger = CronTrigger.from_crontab(cron)
        scheduler.add_job(
            _run_weekly_refresh_background,
            trigger=trigger,
            id="weekly_refresh",
            replace_existing=True,
        )
        scheduler.start()
        scheduler_started = True
        print(f"[Scheduler] 定时任务已启动: cron={cron}")
    except Exception as e:
        print(f"[Scheduler] 初始化失败: {e}")


def _register_blueprints(app):
    """注册所有 Blueprint 模块"""
    from .pages import bp as pages_bp
    from .books_api import bp as books_bp
    from .rank_books_api import bp as rank_bp
    from .chapters_api import bp as chapters_bp
    from .tasks_api import bp as tasks_bp
    from .scheduler_api import bp as scheduler_bp
    from .logs_api import bp as logs_bp
    from .tools_api import bp as tools_bp
    from .links_api import bp as links_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(books_bp, url_prefix="/api")
    app.register_blueprint(rank_bp, url_prefix="/api")
    app.register_blueprint(chapters_bp, url_prefix="/api")
    app.register_blueprint(tasks_bp, url_prefix="/api")
    app.register_blueprint(scheduler_bp, url_prefix="/api")
    app.register_blueprint(logs_bp, url_prefix="/api")
    app.register_blueprint(tools_bp, url_prefix="/api")
    app.register_blueprint(links_bp, url_prefix="/api")


def create_app():
    """Flask 应用工厂"""
    app = Flask(__name__, template_folder="../templates")

    # 注册 Blueprints
    _register_blueprints(app)

    # ── 数据目录静态文件服务 ────────────────────────────────────────
    @app.route("/data/<path:filename>")
    def serve_data_file(filename):
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        return send_from_directory(data_dir, filename)

    # ── App 级别的 API ─────────────────────────────────────────────
    @app.route("/api/stats")
    def api_stats():
        """核心统计数据"""
        data = {}

        row = query_one("SELECT COUNT(*) AS cnt FROM books")
        data["total_books"] = row["cnt"] if row else 0

        rows = query("SELECT source, COUNT(*) AS cnt FROM books GROUP BY source")
        data["books_by_source"] = {r["source"]: r["cnt"] for r in rows}

        row = query_one("SELECT COUNT(*) AS cnt FROM books WHERE crawl_status=2")
        data["completed_books"] = row["cnt"] if row else 0

        row = query_one("SELECT COUNT(*) AS cnt FROM books WHERE crawl_status=3")
        data["failed_books"] = row["cnt"] if row else 0

        row = query_one("SELECT COUNT(*) AS cnt FROM chapters")
        data["total_chapters"] = row["cnt"] if row else 0

        row = query_one("SELECT SUM(content_size) AS total_size FROM chapters")
        data["total_chapter_size"] = row["total_size"] if row and row["total_size"] else 0

        row = query_one("SELECT COUNT(*) AS cnt FROM crawl_tasks WHERE status=3")
        data["failed_tasks"] = row["cnt"] if row else 0

        row = query_one("SELECT COUNT(*) AS cnt FROM rank_books")
        data["total_rankings"] = row["cnt"] if row else 0

        row = query_one(
            "SELECT COUNT(*) AS cnt FROM books "
            "WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
        )
        data["weekly_new_books"] = row["cnt"] if row else 0

        row = query_one("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status=2 THEN 1 ELSE 0 END) AS success
            FROM crawl_tasks
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """)
        if row and row.get("total", 0) > 0:
            data["weekly_task_success_rate"] = round(
                row["success"] / row["total"] * 100, 1
            )
        else:
            data["weekly_task_success_rate"] = 0.0

        from db_ops import get_scheduler_config
        sc = get_scheduler_config()
        data["scheduler_enabled"] = bool(sc.get("enabled", False)) if sc else False
        data["scheduler_next_run"] = str(sc.get("next_run_at", "") or "") if sc else ""
        data["scheduler_last_run"] = str(sc.get("last_run_at", "") or "") if sc else ""
        data["scheduler_last_status"] = sc.get("last_run_status", "") if sc else ""

        return jsonify({"code": 0, "data": data})

    # 初始化调度器
    init_scheduler()

    return app
