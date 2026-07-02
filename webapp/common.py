"""
共享工具模块

提取自原 webapp.py：
- query / query_one / execute：DB 查询辅助
- DATA_DIR：数据文件根目录
"""
import os
from database import get_connection

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


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
