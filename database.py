import mysql.connector
from mysql.connector import Error
from typing import Optional

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345678",
    "database": "book_analyzer",
}


def get_connection():
    """获取数据库连接"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"数据库连接失败: {e}")
        return None


def test_connection():
    """测试数据库连接并打印基本信息"""
    conn = get_connection()
    if not conn:
        return

    print(f"✅ 连接成功！MySQL 版本: {conn.server_version}")
    print(f"   数据库: {DB_CONFIG['database']}")

    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print(f"   表数量: {len(tables)}")
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {t[0]}")
        count = cursor.fetchone()[0]
        print(f"     - {t[0]}: {count} 条记录")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    test_connection()
