"""
起点爬虫监控脚本 — 每隔 600 秒（10 分钟）展示一次数据库状态
用法：
    python3 -u monitor_qidian.py                # 前台循环监控
    python3 -u monitor_qidian.py --once          # 仅输出一次后退出
"""
import sys
import time
import argparse
from datetime import datetime
from database import get_connection


def query_stats() -> dict:
    """查询数据库各表统计和爬虫状态"""
    stats = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rank_books": 0,
        "books": 0,
        "chapters": 0,
        "crawl_status": {"待爬": 0, "爬取中": 0, "已完成": 0, "失败": 0},
        "tasks": {"待执行": 0, "执行中": 0, "成功": 0, "失败": 0},
        "task_errors": [],
        "distinct_books_with_chapters": 0,
    }

    conn = get_connection()
    if not conn:
        return stats

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. 总记录数
        cursor.execute("SELECT COUNT(*) AS cnt FROM rank_books WHERE source='qidian'")
        stats["rank_books"] = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM books WHERE source='qidian'")
        stats["books"] = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM chapters WHERE source='qidian'")
        stats["chapters"] = cursor.fetchone()["cnt"]

        # 2. 书籍爬取状态分布
        cursor.execute(
            "SELECT crawl_status, COUNT(*) AS cnt FROM books "
            "WHERE source='qidian' GROUP BY crawl_status"
        )
        for row in cursor.fetchall():
            status = int(row["crawl_status"])
            label = {0: "待爬", 1: "爬取中", 2: "已完成", 3: "失败"}.get(status, f"未知({status})")
            stats["crawl_status"][label] = row["cnt"]

        # 3. 有章节的书籍数
        cursor.execute(
            "SELECT COUNT(DISTINCT book_id) AS cnt FROM chapters WHERE source='qidian'"
        )
        stats["distinct_books_with_chapters"] = cursor.fetchone()["cnt"]

        # 4. 任务状态分布
        cursor.execute(
            "SELECT status, COUNT(*) AS cnt FROM crawl_tasks "
            "WHERE source='qidian' GROUP BY status"
        )
        for row in cursor.fetchall():
            status = int(row["status"])
            label = {0: "待执行", 1: "执行中", 2: "成功", 3: "失败"}.get(status, f"未知({status})")
            stats["tasks"][label] = row["cnt"]

        # 5. 最近失败任务
        cursor.execute(
            "SELECT id, task_type, target_id, error_msg, created_at "
            "FROM crawl_tasks WHERE source='qidian' AND status=3 "
            "AND error_msg IS NOT NULL AND error_msg != '' "
            "ORDER BY created_at DESC LIMIT 10"
        )
        stats["task_errors"] = cursor.fetchall()

    except Exception as e:
        print(f"  [MONITOR] 查询异常: {e}")
    finally:
        cursor.close()
        conn.close()

    return stats


def print_stats(stats: dict):
    """格式化打印监控数据"""
    print()
    print("=" * 60)
    print(f"📊 起点爬虫数据监控 @ {stats['time']}")
    print("=" * 60)
    print(f"  榜单记录(rank_books):   {stats['rank_books']} 条")
    print(f"  书籍记录(books):        {stats['books']} 本")
    print(f"  章节记录(chapters):     {stats['chapters']} 章")
    print(f"  有章节的书籍:          {stats['distinct_books_with_chapters']} 本")
    print("-" * 60)
    print(f"  书籍爬取状态分布:")
    for label, cnt in stats["crawl_status"].items():
        print(f"    {label}: {cnt} 本")
    print("-" * 60)
    print(f"  任务状态分布:")
    for label, cnt in stats["tasks"].items():
        print(f"    {label}: {cnt} 个")
    if stats["task_errors"]:
        print("-" * 60)
        print(f"  ⚠️ 最近失败任务 (至多10个):")
        for t in stats["task_errors"]:
            err = t.get("error_msg", "")
            if len(err) > 80:
                err = err[:80] + "..."
            print(f"    [{t['task_type']}] {t['target_id']}: {err} (ID={t['id']})")
    print("=" * 60)
    print()


def main():
    parser = argparse.ArgumentParser(description="起点爬虫监控")
    parser.add_argument("--once", action="store_true", help="仅输出一次后退出")
    args = parser.parse_args()

    if args.once:
        stats = query_stats()
        print_stats(stats)
        return

    print("🔁 起点爬虫监控启动 — 每 600 秒（10 分钟）刷新一次")
    print("按 Ctrl+C 停止\n")

    interval = 600  # 10 分钟
    next_run = time.time()

    try:
        while True:
            now = time.time()
            if now >= next_run:
                stats = query_stats()
                print_stats(stats)
                next_run = now + interval
            time_left = max(0, next_run - time.time())
            sys.stdout.write(
                f"\r⏳ 下次刷新: {int(time_left)} 秒后... (Ctrl+C 停止)  "
            )
            sys.stdout.flush()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n\n🛑 监控已停止")


if __name__ == "__main__":
    main()
